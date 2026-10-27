# sale/services/confirm_service.py
from __future__ import annotations

from typing import Dict, List

from django.core.exceptions import ValidationError
from django.db import transaction

from inventory.models import InventoryMovement, MovementType
from inventory.services.inventory_audit_service import \
    create_sale_out_consumption
from purchase.models import ProduitLine
from sale.models import Facture, VenteProduit
from sale.services.vendor_stock_service import consume_vendor_stock


@transaction.atomic
def confirm_sale_out_from_vendor(
    *,
    facture: Facture,
    by_user,
) -> dict:
    """
    Consomme le stock vendeur pour les ProduitLine explicitement
    sélectionnées lors de la vente.

    Architecture :

        QR PL:<uuid>
              ↓
        ProduitLine
              ↓
        VenteProduit.produit_line
              ↓
        VendorStock précis
              ↓
        SALE_OUT
        VENDOR -> EXTERNAL

    Important :
        Il n'y a PAS de FIFO ici.

        Le QR code identifie précisément la ProduitLine qui doit
        être vendue.

    Idempotence :
        - verrouillage de la facture ;
        - facture.stock_consumed bloque une seconde consommation ;
        - présence préalable de SALE_OUT est considérée comme
          une incohérence si stock_consumed=False.
    """

    # =========================================================
    # 1. VERROUILLER LA FACTURE
    # =========================================================

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

    if not vente:
        raise ValidationError(
            "Facture sans vente liée."
        )

    # =========================================================
    # 2. FACTURE PAYÉE
    # =========================================================

    if facture.status != Facture.STAT_PAYE:
        raise ValidationError(
            "La consommation du stock est autorisée uniquement "
            "lorsque la facture est payée."
        )

    # =========================================================
    # 3. IDEMPOTENCE
    # =========================================================

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
            "Des mouvements SALE_OUT existent déjà pour cette "
            "facture alors que stock_consumed est à False. "
            "Une vérification manuelle de la cohérence du stock "
            "est nécessaire."
        )

    # =========================================================
    # 4. CHARGER LES LIGNES DE VENTE
    # =========================================================

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
            vente_id=vente.id,
        )
        .order_by("id")
    )

    # =========================================================
    # 5. VARIABLES D'AUDIT
    # =========================================================

    created = 0
    already = 0
    lines_done = 0

    # =========================================================
    # 6. VALIDATION COMPLÈTE AVANT CONSOMMATION
    #
    # Important :
    # On valide toutes les lignes avant de modifier le stock.
    # =========================================================

    for ligne in lignes:

        # -----------------------------------------------------
        # Vendeur
        # -----------------------------------------------------

        if not ligne.vendor_id:
            raise ValidationError(
                f"Ligne de vente {ligne.id} : "
                "vendeur manquant."
            )

        # -----------------------------------------------------
        # Produit
        # -----------------------------------------------------

        if not ligne.produit_id:
            raise ValidationError(
                f"Ligne de vente {ligne.id} : "
                "produit manquant."
            )

        # -----------------------------------------------------
        # ProduitLine obligatoire
        # -----------------------------------------------------

        if not ligne.produit_line_id:
            raise ValidationError(
                f"Ligne de vente {ligne.id} : "
                "ProduitLine obligatoire."
            )

        produit_line = ligne.produit_line

        if not produit_line:
            raise ValidationError(
                f"Ligne de vente {ligne.id} : "
                "ProduitLine introuvable."
            )

        # -----------------------------------------------------
        # ProduitLine -> Produit
        # -----------------------------------------------------

        if produit_line.produit_id != ligne.produit_id:
            raise ValidationError(
                f"Ligne de vente {ligne.id} : "
                "la ProduitLine ne correspond pas "
                "au produit vendu."
            )

        # -----------------------------------------------------
        # Vendeur -> Bijouterie
        # -----------------------------------------------------

        if (
            ligne.vendor.bijouterie_id
            != facture.bijouterie_id
        ):
            raise ValidationError(
                f"Ligne de vente {ligne.id} : "
                "le vendeur n'appartient pas à la "
                "bijouterie de la facture."
            )

        # -----------------------------------------------------
        # Vendeur de la ligne -> vendeur de la vente
        # -----------------------------------------------------

        if (
            vente.vendor_id
            and ligne.vendor_id != vente.vendor_id
        ):
            raise ValidationError(
                f"Ligne de vente {ligne.id} : "
                "le vendeur de la ligne est différent "
                "du vendeur de la vente."
            )

        # -----------------------------------------------------
        # Quantité
        # -----------------------------------------------------

        quantite = int(ligne.quantite or 0)

        if quantite <= 0:
            raise ValidationError(
                f"Ligne de vente {ligne.id} : "
                "quantité invalide."
            )

    # =========================================================
    # 7. CONSOMMER EXACTEMENT LES PRODUITLINE
    # =========================================================

    consumptions_by_line = []

    for ligne in lignes:

        produit_line = ligne.produit_line
        quantite = int(ligne.quantite)

        # -----------------------------------------------------
        # Consommation du VendorStock EXACT
        # -----------------------------------------------------

        consumptions = consume_vendor_stock(
            vendor=ligne.vendor,
            bijouterie=facture.bijouterie,
            produit_line=produit_line,
            quantite=quantite,
        )

        # -----------------------------------------------------
        # Vérification quantité
        # -----------------------------------------------------

        total_consumed = sum(
            int(item.get("qty") or 0)
            for item in consumptions
        )

        if total_consumed != quantite:
            raise ValidationError(
                f"Ligne de vente {ligne.id} : "
                f"quantité consommée incohérente. "
                f"Attendu={quantite}, "
                f"obtenu={total_consumed}."
            )

        # -----------------------------------------------------
        # Vérification ProduitLine
        # -----------------------------------------------------

        for item in consumptions:

            consumed_pl_id = int(
                item["produit_line_id"]
            )

            if consumed_pl_id != produit_line.id:
                raise ValidationError(
                    f"Ligne de vente {ligne.id} : "
                    "le stock consommé ne correspond pas "
                    "à la ProduitLine scannée."
                )

        consumptions_by_line.append(
            (
                ligne,
                consumptions,
            )
        )

    # =========================================================
    # 8. CRÉER LES MOUVEMENTS SALE_OUT
    # =========================================================

    for ligne, consumptions in consumptions_by_line:

        for item in consumptions:

            produit_line_id = int(
                item["produit_line_id"]
            )

            qty = int(
                item["qty"]
            )

            if qty <= 0:
                raise ValidationError(
                    f"Quantité SALE_OUT invalide "
                    f"pour la ProduitLine "
                    f"{produit_line_id}."
                )

            # La consommation doit correspondre
            # exactement à la ProduitLine de la vente.

            if produit_line_id != ligne.produit_line_id:
                raise ValidationError(
                    f"Ligne de vente {ligne.id} : "
                    "ProduitLine SALE_OUT incohérente."
                )

            produit_line = ligne.produit_line

            movement_created = (
                create_sale_out_consumption(
                    facture=facture,
                    vente=vente,
                    vente_ligne=ligne,
                    produit_line=produit_line,
                    qty=qty,
                    by_user=by_user,
                )
            )

            if movement_created:
                created += 1
            else:
                already += 1

        lines_done += 1

    # =========================================================
    # 9. VÉRIFICATION FINALE
    # =========================================================

    if lines_done != len(lignes):
        raise ValidationError(
            "Toutes les lignes de vente n'ont pas "
            "été consommées."
        )

    # =========================================================
    # 10. MARQUER LA FACTURE COMME CONSOMMÉE
    # =========================================================

    facture.stock_consumed = True

    facture.save(
        update_fields=[
            "stock_consumed",
        ]
    )

    # =========================================================
    # 11. AUDIT
    # =========================================================

    return {
        "created": created,
        "already": already,
        "lines_done": lines_done,
    }
    
    