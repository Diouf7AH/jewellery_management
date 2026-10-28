from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from inventory.models import InventoryMovement, MovementType
from inventory.services.inventory_audit_service import \
    create_sale_out_consumption
from sale.models import Facture, VenteProduit
from sale.services.vendor_stock_service import consume_vendor_stock


@transaction.atomic
def confirm_sale_out_from_vendor(
    *,
    facture: Facture,
    by_user,
) -> dict:
    """
    Consomme le stock vendeur après paiement intégral.

    Règles :
    - Facture entièrement payée.
    - Une seule consommation par facture.
    - ProduitLine exacte sélectionnée lors de la vente.
    - Aucun FIFO.
    - Vérification vendeur / bijouterie.
    - Vérification des quantités consommées.
    - Création des mouvements SALE_OUT.
    - Aucun changement de ProduitLine.quantite.
    """

    # ========================================================
    # 1. VERROUILLAGE DE LA FACTURE
    # ========================================================

    facture = (
        Facture.objects
        .select_for_update()
        .select_related(
            "vente",
            "vente__vendor",
            "bijouterie",
        )
        .get(pk=facture.pk)
    )

    vente = facture.vente

    if vente is None:
        raise ValidationError(
            "Facture sans vente liée."
        )

    if vente.bijouterie_id != facture.bijouterie_id:
        raise ValidationError(
            "La vente et la facture appartiennent "
            "à des bijouteries différentes."
        )

    # ========================================================
    # 2. FACTURE ENTIÈREMENT PAYÉE
    # ========================================================

    if facture.status != Facture.STAT_PAYE:
        raise ValidationError(
            "La consommation du stock est autorisée "
            "uniquement lorsque la facture est payée."
        )

    # ========================================================
    # 3. PROTECTION CONTRE DOUBLE CONSOMMATION
    # ========================================================

    if facture.stock_consumed:
        return {
            "created": 0,
            "already": 0,
            "lines_done": 0,
        }

    existing_sale_out = (
        InventoryMovement.objects
        .filter(
            facture=facture,
            movement_type=MovementType.SALE_OUT,
        )
        .exists()
    )

    if existing_sale_out:
        raise ValidationError(
            "Des mouvements SALE_OUT existent déjà "
            "pour cette facture alors que "
            "stock_consumed=False. "
            "Une vérification manuelle du stock "
            "est nécessaire."
        )

    # ========================================================
    # 4. CHARGER LES LIGNES DE VENTE
    # ========================================================

    lignes = list(
        VenteProduit.objects
        .select_related(
            "produit_line",
            "produit_line__produit",
            "produit_line__lot",
            "vendor",
            "vendor__bijouterie",
        )
        .filter(
            vente_id=vente.pk,
        )
        .order_by("id")
    )

    if not lignes:
        raise ValidationError(
            "La vente ne contient aucun bijou."
        )

    # ========================================================
    # 5. VARIABLES D'AUDIT
    # ========================================================

    created = 0
    already = 0
    lines_done = 0

    # ========================================================
    # 6. VALIDATION AVANT CONSOMMATION
    # ========================================================

    for ligne in lignes:

        # ----------------------------------------------------
        # 6.1. VENDEUR OBLIGATOIRE
        # ----------------------------------------------------

        if not ligne.vendor_id:
            raise ValidationError(
                f"Ligne de vente {ligne.pk} : "
                "vendeur manquant."
            )

        # ----------------------------------------------------
        # 6.2. PRODUITLINE OBLIGATOIRE
        # ----------------------------------------------------

        if not ligne.produit_line_id:
            raise ValidationError(
                f"Ligne de vente {ligne.pk} : "
                "ProduitLine obligatoire."
            )

        produit_line = ligne.produit_line

        # ----------------------------------------------------
        # 6.3. PRODUIT ASSOCIÉ À LA PRODUITLINE
        # ----------------------------------------------------

        if not produit_line.produit_id:
            raise ValidationError(
                f"Ligne de vente {ligne.pk} : "
                "aucun produit associé à la ProduitLine."
            )

        # Le produit vient de ProduitLine.
        # VenteProduit n'a pas de champ produit_id.
        produit = produit_line.produit

        if produit is None:
            raise ValidationError(
                f"Ligne de vente {ligne.pk} : "
                "produit introuvable."
            )

        # ----------------------------------------------------
        # 6.4. VENDEUR / BIJOUTERIE
        # ----------------------------------------------------

        if (
            ligne.vendor.bijouterie_id
            != facture.bijouterie_id
        ):
            raise ValidationError(
                f"Ligne de vente {ligne.pk} : "
                "le vendeur n'appartient pas "
                "à la bijouterie de la facture."
            )

        # ----------------------------------------------------
        # 6.5. VENDEUR DE LA VENTE
        # ----------------------------------------------------

        if (
            vente.vendor_id
            and ligne.vendor_id != vente.vendor_id
        ):
            raise ValidationError(
                f"Ligne de vente {ligne.pk} : "
                "le vendeur de la ligne est différent "
                "du vendeur de la vente."
            )

        # ----------------------------------------------------
        # 6.6. QUANTITÉ
        # ----------------------------------------------------

        quantite = int(ligne.quantite or 0)

        if quantite <= 0:
            raise ValidationError(
                f"Ligne de vente {ligne.pk} : "
                "quantité invalide."
            )

    # ========================================================
    # 7. CONSOMMATION EXACTE DU VENDORSTOCK
    # ========================================================

    consumptions_by_line = []

    for ligne in lignes:

        produit_line = ligne.produit_line
        quantite = int(ligne.quantite)

        consumptions = consume_vendor_stock(
            vendor=ligne.vendor,
            bijouterie=facture.bijouterie,
            produit_line=produit_line,
            quantite=quantite,
        )

        total_consumed = sum(
            int(item.get("qty") or 0)
            for item in consumptions
        )

        if total_consumed != quantite:
            raise ValidationError(
                f"Ligne de vente {ligne.pk} : "
                "quantité consommée incohérente. "
                f"Attendu={quantite}, "
                f"obtenu={total_consumed}."
            )

        # Vérification de la ProduitLine exacte.
        for item in consumptions:

            consumed_pl_id = int(
                item["produit_line_id"]
            )

            if consumed_pl_id != produit_line.pk:
                raise ValidationError(
                    f"Ligne de vente {ligne.pk} : "
                    "le stock consommé ne correspond "
                    "pas à la ProduitLine scannée."
                )

        consumptions_by_line.append(
            (ligne, consumptions)
        )

    # ========================================================
    # 8. MOUVEMENTS INVENTORY SALE_OUT
    # ========================================================

    for ligne, consumptions in consumptions_by_line:

        for item in consumptions:

            produit_line_id = int(
                item["produit_line_id"]
            )

            qty = int(item["qty"])

            if qty <= 0:
                raise ValidationError(
                    "Quantité SALE_OUT invalide pour "
                    f"la ProduitLine {produit_line_id}."
                )

            if produit_line_id != ligne.produit_line_id:
                raise ValidationError(
                    f"Ligne de vente {ligne.pk} : "
                    "ProduitLine SALE_OUT incohérente."
                )

            movement_created = (
                create_sale_out_consumption(
                    facture=facture,
                    vente=vente,
                    vente_ligne=ligne,
                    produit_line=ligne.produit_line,
                    qty=qty,
                    by_user=by_user,
                )
            )

            if movement_created:
                created += 1
            else:
                already += 1

        lines_done += 1

    # ========================================================
    # 9. VÉRIFICATION FINALE
    # ========================================================

    if lines_done != len(lignes):
        raise ValidationError(
            "Toutes les lignes de vente "
            "n'ont pas été consommées."
        )

    # ========================================================
    # 10. MARQUER LA FACTURE COMME CONSOMMÉE
    # ========================================================

    facture.stock_consumed = True

    facture.save(
        update_fields=["stock_consumed"]
    )

    # ========================================================
    # 11. RÉSULTAT D'AUDIT
    # ========================================================

    return {
        "created": created,
        "already": already,
        "lines_done": lines_done,
    }
    
    
    