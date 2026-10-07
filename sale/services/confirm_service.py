# sale/services/confirm_service.py
from __future__ import annotations

from typing import Dict, List

from django.core.exceptions import ValidationError
from django.db import transaction

from inventory.models import InventoryMovement, MovementType
from purchase.models import ProduitLine
from sale.models import Facture, VenteProduit
from sale.services.inventory_audit_service import create_sale_out_consumption
from sale.services.vendor_stock_service import consume_vendor_stock

# @transaction.atomic
# def confirm_sale_out_from_vendor(*, facture: Facture, by_user) -> dict:
#     """
#     Consomme le stock vendeur en FIFO et crée les mouvements SALE_OUT
#     uniquement lorsque la facture est totalement payée.

#     Cycle :
#         VENDOR -> SALE_OUT -> EXTERNAL

#     Idempotence :
#     - verrouillage de la facture ;
#     - facture.stock_consumed bloque une nouvelle consommation ;
#     - présence préalable de mouvements SALE_OUT bloque également
#       une nouvelle consommation.
#     """

#     facture = (
#         Facture.objects
#         .select_for_update()
#         .select_related(
#             "vente",
#             "vente__vendor",
#             "bijouterie",
#         )
#         .get(pk=facture.pk)
#     )

#     vente = facture.vente

#     if not vente:
#         raise ValidationError("Facture sans vente liée.")

#     if facture.status != Facture.STAT_PAYE:
#         raise ValidationError(
#             "La consommation du stock est autorisée uniquement "
#             "lorsque la facture est payée."
#         )

#     if facture.stock_consumed:
#         return {
#             "created": 0,
#             "already": 0,
#             "lines_done": 0,
#         }

#     # Protection supplémentaire contre un état incohérent :
#     # mouvements déjà créés mais stock_consumed resté à False.
#     existing_sale_out = InventoryMovement.objects.filter(
#         facture=facture,
#         movement_type=MovementType.SALE_OUT,
#     ).exists()

#     if existing_sale_out:
#         raise ValidationError(
#             "Des mouvements SALE_OUT existent déjà pour cette facture, "
#             "mais stock_consumed est à False. Une vérification manuelle "
#             "de la cohérence du stock est nécessaire."
#         )
    
#     lignes = list(
#         VenteProduit.objects
#         .select_related(
#             "produit",
#             "vendor",
#             "vendor__bijouterie",
#         )
#         .filter(vente_id=vente.id)
#         .order_by("id")
#     )

#     if not lignes:
#         raise ValidationError(
#             "La vente ne contient aucune ligne produit."
#         )

#     created = 0
#     already = 0
#     lines_done = 0

#     all_pl_ids: List[int] = []
#     consumptions_by_lp: Dict[int, List[dict]] = {}

#     # =========================================================
#     # 1. Vérifications avant toute modification du stock
#     # =========================================================
#     for ligne in lignes:
#         if not ligne.vendor_id:
#             raise ValidationError(
#                 f"Ligne de vente {ligne.id} : vendeur manquant."
#             )

#         if not ligne.produit_id:
#             raise ValidationError(
#                 f"Ligne de vente {ligne.id} : produit manquant."
#             )

#         if ligne.vendor.bijouterie_id != facture.bijouterie_id:
#             raise ValidationError(
#                 f"Ligne de vente {ligne.id} : le vendeur n'appartient "
#                 f"pas à la bijouterie de la facture."
#             )

#         if vente.vendor_id and ligne.vendor_id != vente.vendor_id:
#             raise ValidationError(
#                 f"Ligne de vente {ligne.id} : le vendeur de la ligne "
#                 f"est différent du vendeur de la vente."
#             )

#         quantite = int(ligne.quantite or 0)

#         if quantite <= 0:
#             raise ValidationError(
#                 f"Ligne de vente {ligne.id} : quantité invalide."
#             )

#     # =========================================================
#     # 2. Consommer le VendorStock en FIFO
#     # =========================================================
#     for ligne in lignes:
#         if not ligne.produit_line_id:
#             raise ValidationError(
#                 f"Ligne de vente {ligne.id} : "
#                 "ProduitLine obligatoire."
#             )

#         produit_line = (
#             ProduitLine.objects
#             .select_related(
#                 "produit",
#                 "lot",
#             )
#             .get(
#                 pk=ligne.produit_line_id
#             )
#         )

#         if produit_line.produit_id != ligne.produit_id:
#             raise ValidationError(
#                 f"Ligne de vente {ligne.id} : "
#                 "la ProduitLine ne correspond pas au produit."
#             )
            
#         if (
#             vente_ligne.produit_line_id
#             and vente_ligne.produit_line_id != produit_line.id
#         ):
#             raise ValidationError(
#                 "La ProduitLine consommée ne correspond pas "
#                 "à celle de la ligne de vente."
#             )

#         consumptions = consume_vendor_stock(
#             vendor=ligne.vendor,
#             bijouterie=facture.bijouterie,
#             produit_line=produit_line,
#             quantite=int(ligne.quantite),
#         )

#         total_consumed = sum(
#             int(item.get("qty") or 0)
#             for item in consumptions
#         )

#         if total_consumed != int(ligne.quantite):
#             raise ValidationError(
#                 f"Ligne de vente {ligne.id} : quantité FIFO consommée "
#                 f"incohérente. Attendu={ligne.quantite}, "
#                 f"obtenu={total_consumed}."
#             )

#         consumptions_by_lp[ligne.id] = consumptions

#         all_pl_ids.extend(
#             int(item["produit_line_id"])
#             for item in consumptions
#         )

#     if not all_pl_ids:
#         raise ValidationError(
#             "Aucun stock vendeur n'a été consommé."
#         )

#     # =========================================================
#     # 3. Charger les ProduitLine utilisées par le FIFO
#     # =========================================================
#     produit_lines = (
#         ProduitLine.objects
#         .select_related(
#             "produit",
#             "lot",
#             "lot__achat",
#         )
#         .filter(id__in=set(all_pl_ids))
#     )

#     pl_map = {
#         produit_line.id: produit_line
#         for produit_line in produit_lines
#     }

#     missing_ids = set(all_pl_ids) - set(pl_map.keys())

#     if missing_ids:
#         raise ValidationError(
#             "ProduitLine introuvable : "
#             + ", ".join(str(pk) for pk in sorted(missing_ids))
#         )

#     # =========================================================
#     # 4. Créer SALE_OUT : VENDOR -> EXTERNAL
#     # =========================================================
#     for ligne in lignes:
#         consumptions = consumptions_by_lp.get(ligne.id, [])

#         for item in consumptions:
#             produit_line_id = int(item["produit_line_id"])
#             qty = int(item["qty"])

#             if qty <= 0:
#                 raise ValidationError(
#                     f"Quantité SALE_OUT invalide pour la ProduitLine "
#                     f"{produit_line_id}."
#                 )

#             produit_line = pl_map[produit_line_id]

#             movement_created = create_sale_out_consumption(
#                 facture=facture,
#                 vente=vente,
#                 vente_ligne=ligne,
#                 produit_line=produit_line,
#                 qty=qty,
#                 by_user=by_user,
#             )

#             if movement_created:
#                 created += 1
#             else:
#                 # En pratique ce cas ne devrait plus arriver grâce au
#                 # contrôle global effectué avant la consommation.
#                 already += 1

#         lines_done += 1

#     # =========================================================
#     # 5. Marquer la facture consommée
#     # =========================================================
#     facture.stock_consumed = True
#     facture.save(update_fields=["stock_consumed"])

#     return {
#         "created": created,
#         "already": already,
#         "lines_done": lines_done,
#     }


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
            "produit",
            "produit_line",
            "produit_line__lot",
            "vendor",
            "vendor__bijouterie",
        )
        .filter(
            vente_id=vente.id,
        )
        .order_by("id")
    )

    if not lignes:
        raise ValidationError(
            "La vente ne contient aucune ligne produit."
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
    
    