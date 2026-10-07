from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from inventory.models import Bucket, InventoryMovement, MovementType
from purchase.models import ProduitLine
from sale.models import Facture, Vente, VenteProduit
from stock.models import VendorStock

# ============================================================
# SALE_OUT : VENDOR -> EXTERNAL
# ============================================================
# def create_sale_out_consumption(
#     *,
#     facture: Facture,
#     vente: Vente,
#     vente_ligne: VenteProduit,
#     produit_line: ProduitLine,
#     qty: int,
#     by_user,
# ) -> bool:
#     q = int(qty or 0)

#     if q <= 0:
#         raise ValidationError("qty doit être supérieur à 0.")

#     if not facture or not facture.pk:
#         raise ValidationError("facture requise.")

#     if not vente or not vente.pk:
#         raise ValidationError("vente requise.")

#     if not vente_ligne or not vente_ligne.produit_id:
#         raise ValidationError("vente_ligne.produit requis.")

#     if not produit_line or not produit_line.pk:
#         raise ValidationError("produit_line requise.")

#     if not produit_line.lot_id:
#         raise ValidationError("produit_line.lot requis.")

#     if produit_line.produit_id != vente_ligne.produit_id:
#         raise ValidationError(
#             "La ProduitLine ne correspond pas au produit de la ligne de vente."
#         )

#     vendor = (
#         getattr(vente_ligne, "vendor", None)
#         or getattr(vente, "vendor", None)
#     )

#     if not vendor:
#         raise ValidationError("Vendeur requis pour SALE_OUT.")

#     if vente.vendor_id and vendor.id != vente.vendor_id:
#         raise ValidationError(
#             "Le vendeur de la ligne est différent du vendeur de la vente."
#         )

#     if vendor.bijouterie_id != facture.bijouterie_id:
#         raise ValidationError(
#             "Le vendeur n'appartient pas à la bijouterie de la facture."
#         )

#     try:
#         InventoryMovement.objects.create(
#             produit=vente_ligne.produit,
#             produit_line=produit_line,
#             lot=produit_line.lot,

#             movement_type=MovementType.SALE_OUT,
#             qty=q,
#             unit_cost=None,

#             reason=(
#                 f"SALE_OUT | vente={vente.numero_vente} | "
#                 f"facture={facture.numero_facture} | "
#                 f"ligne={vente_ligne.id} | "
#                 f"vendor={vendor.id} | "
#                 f"pl={produit_line.id} | "
#                 f"lot={produit_line.lot_id}"
#             ),

#             # Nouveau cycle :
#             # VENDOR -> EXTERNAL
#             src_bucket=Bucket.VENDOR,
#             src_bijouterie=facture.bijouterie,

#             dst_bucket=Bucket.EXTERNAL,
#             dst_bijouterie=None,

#             facture=facture,
#             vente=vente,
#             vente_ligne=vente_ligne,
#             vendor=vendor,

#             occurred_at=timezone.now(),
#             created_by=by_user,
#         )

#         return True

#     except IntegrityError:
#         # Fonctionne seulement si une contrainte unique en base
#         # empêche réellement le doublon.
#         return False


def create_sale_out_consumption(
    *,
    facture: Facture,
    vente: Vente,
    vente_ligne: VenteProduit,
    produit_line: ProduitLine,
    qty: int,
    by_user,
) -> bool:
    """
    Crée un mouvement SALE_OUT pour une ProduitLine précise.

    Flux :

        ProduitLine
            ↓
        VendorStock
            ↓
        VenteProduit
            ↓
        SALE_OUT
            VENDOR -> EXTERNAL

    Important :
    - produit_line identifie précisément la ligne de lot.
    - ProduitLine.quantite n'est PAS décrémentée ici.
    - La consommation réelle du stock vendeur est gérée
      par VendorStock.
    """

    # =========================================================
    # 1. QUANTITÉ
    # =========================================================

    try:
        q = int(qty)
    except (TypeError, ValueError):
        raise ValidationError(
            "La quantité SALE_OUT est invalide."
        )

    if q <= 0:
        raise ValidationError(
            "La quantité SALE_OUT doit être supérieure à 0."
        )

    # =========================================================
    # 2. OBJETS OBLIGATOIRES
    # =========================================================

    if not facture or not facture.pk:
        raise ValidationError(
            "facture requise."
        )

    if not vente or not vente.pk:
        raise ValidationError(
            "vente requise."
        )

    if not vente_ligne or not vente_ligne.pk:
        raise ValidationError(
            "vente_ligne requise."
        )

    if not vente_ligne.produit_id:
        raise ValidationError(
            "La ligne de vente ne possède pas de produit."
        )

    if not produit_line or not produit_line.pk:
        raise ValidationError(
            "produit_line requise."
        )

    if not produit_line.lot_id:
        raise ValidationError(
            "La ProduitLine doit être rattachée à un lot."
        )

    if not produit_line.produit_id:
        raise ValidationError(
            "La ProduitLine doit être rattachée à un produit."
        )

    # =========================================================
    # 3. COHÉRENCE PRODUIT
    # =========================================================

    if produit_line.produit_id != vente_ligne.produit_id:
        raise ValidationError(
            {
                "produit_line": (
                    "La ProduitLine ne correspond pas "
                    "au produit de la ligne de vente."
                )
            }
        )

    # =========================================================
    # 4. COHÉRENCE PRODUIT_LINE DE LA VENTE
    # =========================================================

    # Si VenteProduit possède maintenant produit_line,
    # on impose qu'elle soit exactement la même.
    if (
        getattr(vente_ligne, "produit_line_id", None)
        and vente_ligne.produit_line_id
        != produit_line.id
    ):
        raise ValidationError(
            {
                "produit_line": (
                    "La ProduitLine du mouvement est différente "
                    "de celle de la ligne de vente."
                )
            }
        )

    # =========================================================
    # 5. VENDEUR
    # =========================================================

    vendor = (
        getattr(vente_ligne, "vendor", None)
        or getattr(vente, "vendor", None)
    )

    if not vendor:
        raise ValidationError(
            "Vendeur requis pour SALE_OUT."
        )

    # =========================================================
    # 6. VENDEUR DE LA LIGNE = VENDEUR DE LA VENTE
    # =========================================================

    if (
        vente.vendor_id
        and vendor.id != vente.vendor_id
    ):
        raise ValidationError(
            "Le vendeur de la ligne est différent "
            "du vendeur de la vente."
        )

    # =========================================================
    # 7. VENDEUR / BIJOUTERIE
    # =========================================================

    if (
        vendor.bijouterie_id
        != facture.bijouterie_id
    ):
        raise ValidationError(
            "Le vendeur n'appartient pas "
            "à la bijouterie de la facture."
        )

    # =========================================================
    # 8. VÉRIFICATION DU VENDOR STOCK
    # =========================================================

    stock = (
        VendorStock.objects
        .select_for_update()
        .filter(
            produit_line_id=produit_line.id,
            vendor_id=vendor.id,
            bijouterie_id=facture.bijouterie_id,
        )
        .first()
    )

    if not stock:
        raise ValidationError(
            {
                "stock": (
                    "Aucun stock vendeur trouvé pour "
                    f"la ProduitLine {produit_line.uuid}."
                )
            }
        )

    disponible = (
        int(stock.quantite_allouee or 0)
        - int(stock.quantite_vendue or 0)
    )

    if disponible < q:
        raise ValidationError(
            {
                "stock": (
                    "Stock vendeur insuffisant pour cette "
                    "ProduitLine."
                ),
                "produit_line_uuid": str(
                    produit_line.uuid
                ),
                "disponible": disponible,
                "demande": q,
            }
        )

    # =========================================================
    # 9. CRÉATION DU SALE_OUT
    # =========================================================

    try:
        InventoryMovement.objects.create(
            produit=produit_line.produit,
            produit_line=produit_line,
            lot=produit_line.lot,

            movement_type=MovementType.SALE_OUT,
            qty=q,
            unit_cost=None,

            reason=(
                f"SALE_OUT | "
                f"vente={vente.numero_vente} | "
                f"facture={facture.numero_facture} | "
                f"ligne={vente_ligne.id} | "
                f"vendor={vendor.id} | "
                f"pl={produit_line.id} | "
                f"pl_uuid={produit_line.uuid} | "
                f"lot={produit_line.lot_id}"
            ),

            # VENDOR -> EXTERNAL
            src_bucket=Bucket.VENDOR,
            src_bijouterie=facture.bijouterie,

            dst_bucket=Bucket.EXTERNAL,
            dst_bijouterie=None,

            facture=facture,
            vente=vente,
            vente_ligne=vente_ligne,
            vendor=vendor,

            occurred_at=timezone.now(),
            created_by=by_user,
        )

        return True

    except IntegrityError:
        # Si une contrainte d'idempotence existe réellement
        # en base, le mouvement existe déjà.
        return False

# ============================================================
# RETURN_IN : EXTERNAL -> BIJOUTERIE
# ============================================================
def create_return_in_consumption(
    *,
    facture: Facture,
    vente: Vente,
    vente_ligne: VenteProduit,
    produit_line: ProduitLine,
    qty: int,
    by_user,
) -> bool:
    q = int(qty or 0)

    if q <= 0:
        raise ValidationError("qty doit être supérieur à 0.")

    if not facture or not facture.pk:
        raise ValidationError("facture requise.")

    if not vente or not vente.pk:
        raise ValidationError("vente requise.")

    if not vente_ligne or not vente_ligne.produit_id:
        raise ValidationError("vente_ligne.produit requis.")

    if not produit_line or not produit_line.pk:
        raise ValidationError("produit_line requise.")

    if not produit_line.lot_id:
        raise ValidationError("produit_line.lot requis.")

    if produit_line.produit_id != vente_ligne.produit_id:
        raise ValidationError(
            "La ProduitLine ne correspond pas au produit de la ligne de vente."
        )

    vendor = (
        getattr(vente_ligne, "vendor", None)
        or getattr(vente, "vendor", None)
    )

    try:
        InventoryMovement.objects.create(
            produit=vente_ligne.produit,
            produit_line=produit_line,
            lot=produit_line.lot,

            movement_type=MovementType.RETURN_IN,
            qty=q,
            unit_cost=None,

            reason=(
                f"RETURN_IN | vente={vente.numero_vente} | "
                f"facture={facture.numero_facture} | "
                f"ligne={vente_ligne.id} | "
                f"vendor={vendor.id if vendor else 'N/A'} | "
                f"pl={produit_line.id} | "
                f"lot={produit_line.lot_id}"
            ),

            # Nouveau cycle :
            # EXTERNAL -> BIJOUTERIE
            src_bucket=Bucket.EXTERNAL,
            src_bijouterie=None,

            dst_bucket=Bucket.BIJOUTERIE,
            dst_bijouterie=facture.bijouterie,

            facture=facture,
            vente=vente,
            vente_ligne=vente_ligne,
            vendor=vendor,

            occurred_at=timezone.now(),
            created_by=by_user,
        )

        return True

    except IntegrityError:
        return False
    

