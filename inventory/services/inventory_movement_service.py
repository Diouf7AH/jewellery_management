# Enregistrer et valider les mouvements d'inventaire
# inventory/services/inventory_movement_service.py

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from inventory.models import Bucket, InventoryMovement, MovementType
from vendor.models import Vendor

# ============================================================
# HELPERS
# ============================================================

def _value(value):
    """
    Retourne la valeur d'un Django TextChoices
    ou convertit une chaîne en chaîne normalisée.
    """
    if value is None:
        return None

    if hasattr(value, "value"):
        return value.value

    return str(value).strip()


def _normalize_qty(qty) -> int:
    """
    Valide une quantité strictement positive.

    Refuse notamment :
    - None
    - bool
    - valeurs décimales
    - chaînes non entières
    - quantités négatives ou nulles
    """
    if isinstance(qty, bool):
        raise ValidationError({
            "qty": "La quantité doit être un entier valide."
        })

    if isinstance(qty, int):
        normalized_qty = qty

    elif isinstance(qty, str):
        value = qty.strip()

        if not value.isdecimal():
            raise ValidationError({
                "qty": "La quantité doit être un entier valide."
            })

        normalized_qty = int(value)

    else:
        raise ValidationError({
            "qty": "La quantité doit être un entier valide."
        })

    if normalized_qty <= 0:
        raise ValidationError({
            "qty": "La quantité doit être supérieure à zéro."
        })

    return normalized_qty


def _normalize_unit_cost(unit_cost):
    """
    Normalise le coût unitaire du mouvement.

    Le champ InventoryMovement.unit_cost possède :
    max_digits=12 et decimal_places=2.

    Le coût correspond au coût par unité de qty,
    et non nécessairement au prix par gramme.
    """
    if unit_cost is None:
        return None

    if isinstance(unit_cost, bool):
        raise ValidationError({
            "unit_cost": "Le coût unitaire est invalide."
        })

    try:
        value = Decimal(str(unit_cost))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({
            "unit_cost": "Le coût unitaire est invalide."
        })

    if not value.is_finite():
        raise ValidationError({
            "unit_cost": "Le coût unitaire doit être fini."
        })

    if value < 0:
        raise ValidationError({
            "unit_cost": "Le coût unitaire ne peut pas être négatif."
        })

    # On laisse le DecimalField du modèle vérifier
    # la précision maximale et les décimales.
    return value


# ============================================================
# ENREGISTREMENT DES MOUVEMENTS
# ============================================================

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
    Enregistre un mouvement d'inventaire.

    Flux autorisés :

    PURCHASE_IN
        EXTERNAL -> BIJOUTERIE

    VENDOR_ASSIGN
        BIJOUTERIE -> VENDOR

    SALE_OUT
        VENDOR -> EXTERNAL

    RETURN_IN
        EXTERNAL -> BIJOUTERIE

    CANCEL_PURCHASE
        BIJOUTERIE -> EXTERNAL

    ADJUSTMENT
        EXTERNAL -> BIJOUTERIE
        ou
        BIJOUTERIE -> EXTERNAL

    Les règles détaillées de chaque mouvement
    sont vérifiées par InventoryMovement.clean().

    Ce service ne modifie pas directement les
    quantités de Stock ou VendorStock.
    """

    # ========================================================
    # 1. QUANTITÉ
    # ========================================================

    normalized_qty = _normalize_qty(qty)

    # ========================================================
    # 2. TYPE ET BUCKETS
    # ========================================================

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

    # ========================================================
    # 3. COÛT UNITAIRE
    # ========================================================

    normalized_unit_cost = _normalize_unit_cost(
        unit_cost
    )

    # ========================================================
    # 4. DATE DU MOUVEMENT
    # ========================================================

    if occurred_at is not None:
        if not isinstance(occurred_at, datetime):
            raise ValidationError({
                "occurred_at": (
                    "La date du mouvement est invalide."
                )
            })

        if timezone.is_naive(occurred_at):
            raise ValidationError({
                "occurred_at": (
                    "La date doit contenir un fuseau horaire."
                )
            })

    # ========================================================
    # 5. JUSTIFICATION
    # ========================================================

    if reason is not None and not isinstance(reason, str):
        raise ValidationError({
            "reason": "La justification doit être du texte."
        })

    normalized_reason = (
        reason.strip() or None
        if reason is not None
        else None
    )

    # ========================================================
    # 6. CRÉATION DU MOUVEMENT
    # ========================================================

    movement = InventoryMovement(
        produit=produit,
        movement_type=movement_type_value,
        qty=normalized_qty,
        unit_cost=normalized_unit_cost,

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

        reason=normalized_reason,
        created_by=user,
    )

    if occurred_at is not None:
        movement.occurred_at = occurred_at

    # InventoryMovement.save() exécute full_clean().
    # Les règles propres à PURCHASE_IN, SALE_OUT,
    # VENDOR_ASSIGN, etc. sont donc vérifiées ici.
    movement.save()

    # ========================================================
    # 7. VERROUILLAGE
    # ========================================================

    if lock:
        movement.freeze(by_user=user)

    return movement

