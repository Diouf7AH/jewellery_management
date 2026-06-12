from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from inventory.models import Bucket, InventoryMovement, MovementType
from purchase.models import ProduitLine
from sale.models import Facture, Vente, VenteProduit


# ============================================================
# 🔴 SALE_OUT (VENTE)
# ============================================================
def create_sale_out_consumption(
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
        raise ValidationError("qty doit être > 0.")

    if not vente_ligne or not vente_ligne.produit_id:
        raise ValidationError("vente_ligne.produit requis.")

    if not produit_line or not produit_line.id:
        raise ValidationError("produit_line requis.")

    if not getattr(produit_line, "lot_id", None):
        raise ValidationError("produit_line.lot requis.")

    # ✅ vendor obligatoire (aligné avec constraint DB)
    vendor = getattr(vente, "vendor", None) or getattr(vente_ligne, "vendor", None)

    if not vendor:
        raise ValidationError("Vendeur requis pour SALE_OUT.")

    try:
        InventoryMovement.objects.create(
            produit=vente_ligne.produit,
            movement_type=MovementType.SALE_OUT,
            qty=q,
            unit_cost=None,

            produit_line=produit_line,
            lot=produit_line.lot,

            # 🔥 VERSION ERP PRO
            reason=(
                f"SALE_OUT | vente={vente.numero_vente} | "
                f"facture={facture.numero_facture} | "
                f"ligne={vente_ligne.id} | vendor={vendor.id} | "
                f"pl={produit_line.id} | lot={produit_line.lot_id}"
            ),

            src_bucket=Bucket.BIJOUTERIE,
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
        # idempotence FIFO (déjà créé)
        return False


# ============================================================
# 🟢 RETURN_IN (ANNULATION)
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
        raise ValidationError("qty doit être > 0.")

    if not vente_ligne or not vente_ligne.produit_id:
        raise ValidationError("vente_ligne.produit requis.")

    if not produit_line or not produit_line.id:
        raise ValidationError("produit_line requis.")

    if not getattr(produit_line, "lot_id", None):
        raise ValidationError("produit_line.lot requis.")

    vendor = getattr(vente, "vendor", None) or getattr(vente_ligne, "vendor", None)

    InventoryMovement.objects.create(
        produit=vente_ligne.produit,
        movement_type=MovementType.RETURN_IN,  # ✅ CORRECT
        qty=q,
        unit_cost=None,

        produit_line=produit_line,
        lot=produit_line.lot,

        # 🔥 VERSION PRO
        reason=(
            f"RETURN_IN | vente={vente.numero_vente} | "
            f"facture={facture.numero_facture} | "
            f"ligne={vente_ligne.id} | vendor={vendor.id if vendor else 'N/A'} | "
            f"pl={produit_line.id} | lot={produit_line.lot_id}"
        ),

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