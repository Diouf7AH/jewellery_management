# sale/services/vendor_stock_service.py
from __future__ import annotations

from typing import Dict, List

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import ExpressionWrapper, F, IntegerField, Sum
from django.db.models.functions import Coalesce

from stock.models import VendorStock


def _en_stock_expr():
    """
    Stock disponible SQL :
    quantite_allouee - quantite_vendue
    """
    return ExpressionWrapper(
        Coalesce(F("quantite_allouee"), 0) - Coalesce(F("quantite_vendue"), 0),
        output_field=IntegerField(),
    )


def ensure_vendor_stock_available(*, vendor, bijouterie, produit, quantite: int) -> None:
    """
    Vérifie, sans consommer, que le vendeur a assez de stock
    pour ce produit dans cette bijouterie.
    """
    q = int(quantite or 0)
    if q <= 0:
        raise ValidationError({"quantite": "Doit être >= 1."})

    qs = (
        VendorStock.objects
        .select_for_update()
        .select_related("produit_line", "produit_line__produit", "produit_line__lot")
        .filter(
            vendor=vendor,
            bijouterie=bijouterie,
            produit_line__produit=produit,
        )
        .annotate(stock_disponible=_en_stock_expr())
        .filter(stock_disponible__gt=0)
    )

    total_dispo = int(
        qs.aggregate(total=Coalesce(Sum("stock_disponible"), 0))["total"] or 0
    )

    if total_dispo < q:
        prod_name = getattr(produit, "nom", None) or f"ID={getattr(produit, 'id', '')}"
        raise ValidationError({
            "stock": (
                f"Stock insuffisant. Produit: {prod_name}. "
                f"Disponible: {total_dispo}, demandé: {q}."
            )
        })


def consume_vendor_stock(*, vendor, bijouterie, produit, quantite: int) -> List[Dict]:
    """
    Consomme FIFO sur VendorStock.
    Retour :
    [
        {"produit_line_id": int, "qty": int},
        ...
    ]
    """
    q = int(quantite or 0)
    if q <= 0:
        raise ValidationError({"quantite": "Doit être >= 1."})

    qs = (
        VendorStock.objects
        .select_for_update()
        .select_related("produit_line", "produit_line__lot", "produit_line__produit")
        .filter(
            vendor=vendor,
            bijouterie=bijouterie,
            produit_line__produit=produit,
        )
        .annotate(stock_disponible=_en_stock_expr())
        .filter(stock_disponible__gt=0)
        .order_by("produit_line_id")  # FIFO
    )

    total_dispo = int(
        qs.aggregate(total=Coalesce(Sum("stock_disponible"), 0))["total"] or 0
    )

    if total_dispo < q:
        prod_name = getattr(produit, "nom", None) or f"ID={getattr(produit, 'id', '')}"
        raise ValidationError({
            "stock": (
                f"Stock insuffisant (FIFO). Produit: {prod_name}. "
                f"Disponible: {total_dispo}, demandé: {q}."
            )
        })

    remaining = q
    moves: List[Dict] = []

    for row in qs:
        if remaining <= 0:
            break

        dispo = int(row.stock_disponible)
        take = min(dispo, remaining)

        updated = VendorStock.objects.filter(
            pk=row.pk,
            quantite_vendue__lte=F("quantite_allouee"),
        ).update(
            quantite_vendue=F("quantite_vendue") + take
        )

        if not updated:
            raise ValidationError({
                "stock": "Conflit de mise à jour du stock vendeur. Réessayez."
            })

        moves.append({
            "produit_line_id": int(row.produit_line_id),
            "qty": int(take),
        })
        remaining -= take

    if remaining > 0:
        raise ValidationError({
            "stock": f"Incohérence FIFO: manque {remaining} après consommation."
        })

    return moves


@transaction.atomic
def restore_vendor_stock(*, vendor, bijouterie, produit, quantite: int) -> List[Dict[str, int]]:
    """
    Restaure le stock vendeur (LIFO simple).
    Retour :
    [
        {"produit_line_id": int, "qty": int},
        ...
    ]
    """
    remaining = int(quantite or 0)
    if remaining <= 0:
        return []

    qs = (
        VendorStock.objects
        .select_for_update()
        .select_related("produit_line", "produit_line__lot")
        .filter(
            vendor=vendor,
            bijouterie=bijouterie,
            produit_line__produit=produit,
            quantite_vendue__gt=0,
        )
        .order_by("-produit_line_id")  # LIFO simple
    )

    restored: List[Dict[str, int]] = []

    for vs in qs:
        if remaining <= 0:
            break

        sold = int(vs.quantite_vendue or 0)
        take = min(sold, remaining)

        updated = VendorStock.objects.filter(
            pk=vs.pk,
            quantite_vendue__gte=take
        ).update(
            quantite_vendue=F("quantite_vendue") - take
        )

        if not updated:
            raise ValidationError("Conflit restauration stock, réessayez.")

        restored.append({
            "produit_line_id": int(vs.produit_line_id),
            "qty": int(take),
        })
        remaining -= take

    if remaining > 0:
        raise ValidationError("Impossible de restaurer tout le stock (données incohérentes).")

    return restored

    
    

