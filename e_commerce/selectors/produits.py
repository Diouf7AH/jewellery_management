from decimal import Decimal

from django.db.models import (DecimalField, ExpressionWrapper, F, OuterRef,
                              Subquery)

from stock.models import Stock
from store.models import MarquePurete


def get_ecommerce_produits(*, bijouterie_id=None):
    prix_gramme_subquery = (
        MarquePurete.objects
        .filter(
            marque_id=OuterRef("produit_line__produit__marque_id"),
            purete_id=OuterRef("produit_line__produit__purete_id"),
        )
        .values("prix")[:1]
    )

    queryset = (
        Stock.objects
        .select_related(
            "bijouterie",
            "produit_line",
            "produit_line__produit",
            "produit_line__produit__categorie",
            "produit_line__produit__marque",
            "produit_line__produit__modele",
            "produit_line__produit__purete",
        )
        .filter(
            en_stock__gt=0,
            bijouterie__isnull=False,
            produit_line__produit__status="publié",
        )
        .annotate(
            prix_gramme=Subquery(
                prix_gramme_subquery,
                output_field=DecimalField(
                    max_digits=14,
                    decimal_places=2,
                ),
            )
        )
        .annotate(
            prix_produit=ExpressionWrapper(
                F("prix_gramme")
                * F("produit_line__produit__poids"),
                output_field=DecimalField(
                    max_digits=14,
                    decimal_places=2,
                ),
            )
        )
        .order_by("-produit_line__produit__date_ajout")
    )

    if bijouterie_id:
        queryset = queryset.filter(
            bijouterie_id=bijouterie_id
        )

    return queryset

