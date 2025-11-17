# inventory/services.py
from typing import Optional

from inventory.models import Bucket, InventoryMovement, MovementType
from vendor.models import Vendor  # si ce n’est pas déjà importé


def log_move(
    *,
    produit,
    qty: int,
    movement_type: str | MovementType,   # ex. MovementType.PURCHASE_IN, VENDOR_ASSIGN, ...
    src_bucket: Optional[str | Bucket] = None,   # Bucket.EXTERNAL / RESERVED / BIJOUTERIE
    dst_bucket: Optional[str | Bucket] = None,
    src_bijouterie_id: Optional[int] = None,
    dst_bijouterie_id: Optional[int] = None,
    vendor: Optional[Vendor] = None,            # ✅ pour VENDOR_ASSIGN / mouvements vendeur
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
      - VENDOR_ASSIGN    : affectation de stock à un vendeur (bijouterie -> vendor)
      - VENDOR_ADJUST    : ajustement manuel sur stock vendeur (optionnel, si tu le crées)

    Buckets (src/dst) : valeurs de Bucket
      - EXTERNAL, RESERVED, BIJOUTERIE

    Params clés :
      - produit        : instance Produit
      - qty            : quantité *positive* (le signe est géré par les enums/logique métier)
      - vendor         : instance Vendor pour les mouvements vendeur (optionnel)
      - achat          : FK vers Achat (pour lier l'entrée à un achat)
      - achat_ligne    : FK vers ligne d'achat
      - lot            : FK vers Lot si tu veux tracer par lot
      - user           : User ayant déclenché le mouvement
      - reason         : commentaire libre (pour l’audit / journal)

    Notes :
      - qty doit être > 0 (la direction est donnée par movement_type & buckets).
      - Utiliser les enums MovementType/Bucket plutôt que des chaînes libres.
      - `mv.freeze()` permet de verrouiller le mouvement (si tu as implémenté cette logique).
    """
    if qty <= 0:
        raise ValueError("log_move() : qty doit être strictement positive (> 0).")

    mv = InventoryMovement.objects.create(
        produit=produit,
        movement_type=str(movement_type),
        qty=int(qty),
        unit_cost=unit_cost,
        src_bucket=str(src_bucket) if src_bucket else None,
        src_bijouterie_id=src_bijouterie_id,
        dst_bucket=str(dst_bucket) if dst_bucket else None,
        dst_bijouterie_id=dst_bijouterie_id,
        vendor=vendor,               # ✅ important pour les vues d’inventaire vendeur
        lot=lot,
        reason=reason or "",
        achat=achat,
        achat_ligne=achat_ligne,
        created_by=user,
    )
    try:
        mv.freeze(by_user=user)
    except Exception:
        # si freeze échoue (selon ton implémentation), on ne veut pas bloquer la création
        pass

    return mv
  
  