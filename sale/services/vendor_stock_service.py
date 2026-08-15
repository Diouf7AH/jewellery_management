# sale/services/vendor_stock_service.py
from __future__ import annotations

from typing import Dict, List

from django.core.exceptions import ValidationError
from django.db.models import ExpressionWrapper, F, IntegerField, Sum
from django.db.models.functions import Coalesce

from stock.models import VendorStock


def _en_stock_expr():
    """
    Stock vendeur disponible :

        quantite_allouee - quantite_vendue
    """
    return ExpressionWrapper(
        Coalesce(F("quantite_allouee"), 0)
        - Coalesce(F("quantite_vendue"), 0),
        output_field=IntegerField(),
    )


def ensure_vendor_stock_available(
    *,
    vendor,
    bijouterie,
    produit,
    quantite: int,
) -> int:
    """
    Vérifie, sans consommer, que le vendeur possède assez de stock.

    Retourne la quantité totale disponible chez ce vendeur
    pour le produit demandé.
    """
    try:
        q = int(quantite)
    except (TypeError, ValueError):
        raise ValidationError({
            "quantite": "La quantité doit être un entier valide."
        })

    if q <= 0:
        raise ValidationError({
            "quantite": "La quantité doit être supérieure ou égale à 1."
        })

    if not vendor:
        raise ValidationError({
            "vendor": "Le vendeur est obligatoire."
        })

    if not bijouterie:
        raise ValidationError({
            "bijouterie": "La bijouterie est obligatoire."
        })

    if not produit:
        raise ValidationError({
            "produit": "Le produit est obligatoire."
        })

    if vendor.bijouterie_id != bijouterie.id:
        raise ValidationError({
            "vendor": (
                "Le vendeur n'appartient pas à la bijouterie sélectionnée."
            )
        })

    qs = (
        VendorStock.objects
        .filter(
            vendor=vendor,
            bijouterie=bijouterie,
            produit_line__produit=produit,
        )
        .annotate(
            stock_disponible=_en_stock_expr()
        )
        .filter(
            stock_disponible__gt=0
        )
    )

    total_disponible = int(
        qs.aggregate(
            total=Coalesce(
                Sum("stock_disponible"),
                0,
                output_field=IntegerField(),
            )
        )["total"] or 0
    )

    if total_disponible < q:
        produit_nom = (
            getattr(produit, "nom", None)
            or f"ID={getattr(produit, 'id', '')}"
        )

        raise ValidationError({
            "stock": (
                f"Stock insuffisant pour le produit '{produit_nom}'. "
                f"Disponible : {total_disponible}, demandé : {q}."
            )
        })

    return total_disponible


def consume_vendor_stock(
    *,
    vendor,
    bijouterie,
    produit,
    quantite: int,
) -> List[Dict[str, int]]:
    """
    Consomme le stock vendeur en FIFO par ProduitLine.

    Cette fonction est appelée lors de la confirmation du paiement.

    Effet :
        VendorStock.quantite_vendue += quantité

    Retour :
        [
            {
                "produit_line_id": 12,
                "qty": 2,
            },
            ...
        ]

    Important :
        Un retour client ne doit jamais appeler cette fonction
        en sens inverse.

        Le retour client utilise RETURN_IN :
            EXTERNAL → BIJOUTERIE
    """
    try:
        q = int(quantite)
    except (TypeError, ValueError):
        raise ValidationError({
            "quantite": "La quantité doit être un entier valide."
        })

    if q <= 0:
        raise ValidationError({
            "quantite": "La quantité doit être supérieure ou égale à 1."
        })

    if not vendor:
        raise ValidationError({
            "vendor": "Le vendeur est obligatoire."
        })

    if not bijouterie:
        raise ValidationError({
            "bijouterie": "La bijouterie est obligatoire."
        })

    if not produit:
        raise ValidationError({
            "produit": "Le produit est obligatoire."
        })

    if vendor.bijouterie_id != bijouterie.id:
        raise ValidationError({
            "vendor": (
                "Le vendeur n'appartient pas à la bijouterie sélectionnée."
            )
        })

    qs = (
        VendorStock.objects
        .select_for_update()
        .select_related(
            "produit_line",
            "produit_line__lot",
            "produit_line__produit",
        )
        .filter(
            vendor=vendor,
            bijouterie=bijouterie,
            produit_line__produit=produit,
        )
        .annotate(
            stock_disponible=_en_stock_expr()
        )
        .filter(
            stock_disponible__gt=0
        )
        .order_by(
            "produit_line__lot__received_at",
            "produit_line_id",
        )
    )

    total_disponible = int(
        qs.aggregate(
            total=Coalesce(
                Sum("stock_disponible"),
                0,
                output_field=IntegerField(),
            )
        )["total"] or 0
    )

    if total_disponible < q:
        produit_nom = (
            getattr(produit, "nom", None)
            or f"ID={getattr(produit, 'id', '')}"
        )

        raise ValidationError({
            "stock": (
                f"Stock insuffisant en FIFO pour '{produit_nom}'. "
                f"Disponible : {total_disponible}, demandé : {q}."
            )
        })

    remaining = q
    consumed: List[Dict[str, int]] = []

    for vendor_stock in qs:
        if remaining <= 0:
            break

        disponible = int(
            vendor_stock.stock_disponible or 0
        )

        take = min(
            disponible,
            remaining,
        )

        updated = (
            VendorStock.objects
            .filter(
                pk=vendor_stock.pk,
                quantite_vendue__lte=(
                    F("quantite_allouee") - take
                ),
            )
            .update(
                quantite_vendue=(
                    F("quantite_vendue") + take
                )
            )
        )

        if updated != 1:
            raise ValidationError({
                "stock": (
                    "Conflit lors de la consommation du stock vendeur. "
                    "Veuillez réessayer."
                )
            })

        consumed.append({
            "produit_line_id": int(
                vendor_stock.produit_line_id
            ),
            "qty": int(take),
        })

        remaining -= take

    if remaining > 0:
        raise ValidationError({
            "stock": (
                "Incohérence FIFO : "
                f"il manque encore {remaining} unité(s)."
            )
        })

    return consumed

