from inventory.models import InventoryMovement, Bucket, MovementType

# ---------- Automatisation des inventaires -----------------
def log_move(
    *, produit, qty: int, movement_type: str,
    src_bucket: str | None = None, dst_bucket: str | None = None,
    src_bijouterie_id: int | None = None, dst_bijouterie_id: int | None = None,
    unit_cost=None, achat=None, achat_ligne=None, user=None, reason: str | None = None,
):
    """
    movement_type: "IN" | "OUT" | "MOVE"
    buckets: "reserved" | "bijouterie" (ou None si non applicable)
    """
    return InventoryMovement.objects.create(
        produit=produit,
        movement_type=movement_type,
        qty=qty,
        unit_cost=unit_cost,
        src_bucket=src_bucket,
        src_bijouterie_id=src_bijouterie_id,
        dst_bucket=dst_bucket,
        dst_bijouterie_id=dst_bijouterie_id,
        achat=achat,
        achat_ligne=achat_ligne,
        created_by=user,
        reason=reason,
    )
# ---------- END --------------------------------------------