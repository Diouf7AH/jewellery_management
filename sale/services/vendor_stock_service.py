from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from stock.models import VendorStock
from store.models import Produit
from vendor.models import Vendor


@transaction.atomic
def consume_vendor_stock(*, vendor: Vendor, produit: Produit, quantite: int):
    """
    Décrément FIFO sur VendorStock (quantite_vendue += qte).
    Retourne une liste de consommation par produit_line.
    """
    remaining = int(quantite or 0)
    if remaining <= 0:
        raise ValidationError("Quantité à consommer doit être > 0.")

    qs = (
        VendorStock.objects
        .select_for_update()
        .select_related("produit_line", "produit_line__lot")
        .filter(
            vendor=vendor,
            produit_line__produit=produit,
            quantite_allouee__gt=F("quantite_vendue"),
        )
        .order_by("produit_line__lot__received_at", "produit_line_id")
    )

    moves = []
    for vs in qs:
        if remaining <= 0:
            break

        dispo = int((vs.quantite_allouee or 0) - (vs.quantite_vendue or 0))
        if dispo <= 0:
            continue

        take = min(dispo, remaining)

        updated = (
            VendorStock.objects
            .filter(pk=vs.pk, quantite_allouee__gte=F("quantite_vendue") + take)
            .update(quantite_vendue=F("quantite_vendue") + take)
        )
        if not updated:
            raise ValidationError("Conflit de stock détecté, réessayez.")

        moves.append({"produit_line_id": vs.produit_line_id, "qty": take})
        remaining -= take

    if remaining > 0:
        raise ValidationError(
            f"Stock vendeur insuffisant pour '{getattr(produit, 'nom', produit.id)}'. Manque {remaining}."
        )

    return moves


@transaction.atomic
def restore_vendor_stock(*, vendor: Vendor, produit: Produit, quantite: int):
    """
    Restaure VendorStock (quantite_vendue -= qte).
    Stratégie: on prend d'abord les plus récents (LIFO) pour éviter négatif.
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
            produit_line__produit=produit,
            quantite_vendue__gt=0,
        )
        .order_by("-produit_line__lot__received_at", "-produit_line_id")
    )

    restored = []
    for vs in qs:
        if remaining <= 0:
            break

        sold = int(vs.quantite_vendue or 0)
        if sold <= 0:
            continue

        take = min(sold, remaining)

        updated = (
            VendorStock.objects
            .filter(pk=vs.pk, quantite_vendue__gte=take)
            .update(quantite_vendue=F("quantite_vendue") - take)
        )
        if not updated:
            raise ValidationError("Conflit restauration stock, réessayez.")

        restored.append({"produit_line_id": vs.produit_line_id, "qty": take})
        remaining -= take

    if remaining > 0:
        raise ValidationError("Impossible de restaurer tout le stock (données incohérentes).")

    return restored

