# inventory/services.py
from typing import Optional

from django.core.exceptions import ValidationError

from inventory.models import Bucket, InventoryMovement, MovementType
from vendor.models import Vendor


def _val(x):
    return x.value if hasattr(x, "value") else str(x)


def log_move(
    *,
    produit,
    qty: int,
    movement_type: str | MovementType,
    src_bucket: Optional[str | Bucket] = None,
    dst_bucket: Optional[str | Bucket] = None,
    src_bijouterie_id: Optional[int] = None,
    dst_bijouterie_id: Optional[int] = None,
    vendor: Optional[Vendor] = None,
    unit_cost=None,
    achat=None,
    produit_line=None,
    user=None,
    reason: Optional[str] = None,
    lot=None,
    vente=None,
    vente_ligne=None,
    facture=None,
):
    if int(qty or 0) <= 0:
        raise ValidationError("log_move() : qty doit être > 0.")

    mv = InventoryMovement.objects.create(
        produit=produit,
        movement_type=_val(movement_type),
        qty=int(qty),
        unit_cost=unit_cost,
        src_bucket=_val(src_bucket) if src_bucket else None,
        dst_bucket=_val(dst_bucket) if dst_bucket else None,
        src_bijouterie_id=src_bijouterie_id,
        dst_bijouterie_id=dst_bijouterie_id,
        vendor=vendor,
        produit_line=produit_line,
        lot=lot,          # optionnel (si produit_line, le modèle peut remplir lot)
        achat=achat,      # optionnel
        vente=vente,
        vente_ligne=vente_ligne,
        facture=facture,
        reason=reason,
        created_by=user,
    )

    try:
        mv.freeze(by_user=user)
    except Exception:
        pass

    return mv

