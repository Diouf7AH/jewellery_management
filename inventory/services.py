from typing import Optional
from inventory.models import InventoryMovement, Bucket, MovementType

def log_move(
    *,
    produit,
    qty: int,
    movement_type: str | MovementType,   # ex. MovementType.PURCHASE_IN, ...
    src_bucket: Optional[str | Bucket] = None,  # ex. Bucket.EXTERNAL/RESERVED/BIJOUTERIE
    dst_bucket: Optional[str | Bucket] = None,
    src_bijouterie_id: Optional[int] = None,
    dst_bijouterie_id: Optional[int] = None,
    unit_cost=None,
    achat=None,
    achat_ligne=None,
    user=None,
    reason: Optional[str] = None,
    lot=None,
):
    """
    Crée et verrouille un mouvement d'inventaire.

    movement_type (obligatoire) : valeurs de MovementType
      - PURCHASE_IN      : entrée suite à achat (EXTERNAL -> RESERVED/BIJOUTERIE)
      - CANCEL_PURCHASE  : sortie pour annulation d'achat (RESERVED/BIJOUTERIE -> EXTERNAL)
      - ALLOCATE         : allocation du réservé vers une bijouterie (RESERVED -> BIJOUTERIE)
      - TRANSFER         : transfert entre bijouteries (BIJOUTERIE -> BIJOUTERIE)
      - ADJUSTMENT       : ajustement manuel (src OU dst uniquement)
      - SALE_OUT         : sortie vente (BIJOUTERIE -> EXTERNAL ou bucket métier)
      - RETURN_IN        : retour client (EXTERNAL ou source -> RESERVED/BIJOUTERIE)

    Buckets (src/dst) : valeurs de Bucket
      - EXTERNAL, RESERVED, BIJOUTERIE

    Notes :
      - Utiliser les enums MovementType/Bucket plutôt que des chaînes libres.
      - `lot` est optionnel pour tracer les lots.
      - `qty` doit être > 0.
    """
    mv = InventoryMovement.objects.create(
        produit=produit,
        movement_type=str(movement_type),
        qty=int(qty),
        unit_cost=unit_cost,
        src_bucket=str(src_bucket) if src_bucket else None,
        src_bijouterie_id=src_bijouterie_id,
        dst_bucket=str(dst_bucket) if dst_bucket else None,
        dst_bijouterie_id=dst_bijouterie_id,
        lot=lot,
        reason=reason or "",
        achat=achat,
        achat_ligne=achat_ligne,
        created_by=user,
    )
    try:
        mv.freeze(by_user=user)
    except Exception:
        pass
    return mv

# ----------------EXEMPLE-----------------
# Exemples rapides

# Entrée d’achat → réservé (par lot) :
# log_move(
#   produit=p, qty=3,
#   movement_type=MovementType.PURCHASE_IN,
#   src_bucket=Bucket.EXTERNAL, dst_bucket=Bucket.RESERVED,
#   unit_cost=prix, achat=achat, achat_ligne=ligne, lot=lot, user=request.user,
#   reason="Arrivée achat (réservé)"
# )

# Allocation réservé → bijouterie :

# log_move(
#   produit=p, qty=2,
#   movement_type=MovementType.ALLOCATE,
#   src_bucket=Bucket.RESERVED, dst_bucket=Bucket.BIJOUTERIE, dst_bijouterie_id=1,
#   unit_cost=prix, achat=achat, achat_ligne=ligne, lot=lot, user=request.user,
#   reason="Affectation vers bijouterie"
# )