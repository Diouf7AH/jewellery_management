# inventory/services.py

from __future__ import annotations

from datetime import datetime
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction

from inventory.models import Bucket, InventoryMovement, MovementType
from vendor.models import Vendor


def _value(value):
    """
    Retourne la valeur d'un Django TextChoices
    ou convertit la valeur reçue en chaîne.
    """
    if value is None:
        return None

    return value.value if hasattr(value, "value") else str(value)


@transaction.atomic
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
    stock_consumed: bool = False,
    occurred_at: Optional[datetime] = None,
    lock: bool = True,
) -> InventoryMovement:
    """
    Crée un mouvement d'inventaire puis le verrouille.

    Flux actuellement actifs :

    PURCHASE_IN
        EXTERNAL → BIJOUTERIE

    VENDOR_ASSIGN
        BIJOUTERIE → VENDOR

    SALE_OUT
        VENDOR → EXTERNAL

    CANCEL_PURCHASE
        BIJOUTERIE → EXTERNAL

    ADJUSTMENT
        Selon le sens de la correction

    RETURN_IN
        EXTERNAL → BIJOUTERIE
    """

    try:
        normalized_qty = int(qty)
    except (TypeError, ValueError) as exc:
        raise ValidationError({
            "qty": "La quantité doit être un entier valide."
        }) from exc

    if normalized_qty <= 0:
        raise ValidationError({
            "qty": "La quantité doit être supérieure à zéro."
        })

    movement_type_value = _value(movement_type)
    src_bucket_value = _value(src_bucket)
    dst_bucket_value = _value(dst_bucket)

    valid_movement_types = {
        choice.value
        for choice in MovementType
    }

    valid_buckets = {
        choice.value
        for choice in Bucket
    }

    if movement_type_value not in valid_movement_types:
        raise ValidationError({
            "movement_type": (
                f"Type de mouvement invalide : "
                f"{movement_type_value}."
            )
        })

    if (
        src_bucket_value is not None
        and src_bucket_value not in valid_buckets
    ):
        raise ValidationError({
            "src_bucket": (
                f"Bucket source invalide : "
                f"{src_bucket_value}."
            )
        })

    if (
        dst_bucket_value is not None
        and dst_bucket_value not in valid_buckets
    ):
        raise ValidationError({
            "dst_bucket": (
                f"Bucket destination invalide : "
                f"{dst_bucket_value}."
            )
        })

    movement = InventoryMovement(
        produit=produit,
        movement_type=movement_type_value,
        qty=normalized_qty,
        unit_cost=unit_cost,

        src_bucket=src_bucket_value,
        src_bijouterie_id=src_bijouterie_id,

        dst_bucket=dst_bucket_value,
        dst_bijouterie_id=dst_bijouterie_id,

        vendor=vendor,

        achat=achat,
        produit_line=produit_line,
        lot=lot,

        vente=vente,
        vente_ligne=vente_ligne,
        facture=facture,

        stock_consumed=bool(stock_consumed),

        reason=(reason or "").strip() or None,
        created_by=user,
    )

    if occurred_at is not None:
        movement.occurred_at = occurred_at

    movement.save()

    if lock:
        movement.freeze(by_user=user)

    return movement

