# e_commerce/selectors/produits.py

from decimal import Decimal, InvalidOperation

from django.db.models import (DecimalField, ExpressionWrapper, F, OuterRef,
                              Subquery)

from stock.models import Stock
from store.models import MarquePurete


def get_ecommerce_produits(
    *,
    bijouterie_id=None,
    prix_min=None,
    prix_max=None,
):
    # ============================================================
    # 1. PRIX DU GRAMME
    # ============================================================

    prix_gramme_subquery = (
        MarquePurete.objects
        .filter(
            marque_id=OuterRef(
                "produit_line__produit__marque_id"
            ),
            purete_id=OuterRef(
                "produit_line__produit__purete_id"
            ),
        )
        .values("prix")[:1]
    )

    # ============================================================
    # 2. CATALOGUE DE BASE
    # ============================================================

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
        # Un produit sans prix configuré
        # ne doit pas apparaître.
        .filter(
            prix_gramme__isnull=False,
            prix_gramme__gt=0,
            prix_produit__gt=0,
        )
    )

    # ============================================================
    # 3. BIJOUTERIE
    # ============================================================

    if bijouterie_id:
        queryset = queryset.filter(
            bijouterie_id=bijouterie_id
        )

    # ============================================================
    # 4. BUDGET MINIMUM
    # ============================================================

    if prix_min not in (None, ""):
        try:
            prix_min = Decimal(str(prix_min))

            if prix_min < 0:
                prix_min = Decimal("0.00")

            queryset = queryset.filter(
                prix_produit__gte=prix_min
            )

        except (InvalidOperation, TypeError, ValueError):
            pass

    # ============================================================
    # 5. BUDGET MAXIMUM
    # ============================================================

    if prix_max not in (None, ""):
        try:
            prix_max = Decimal(str(prix_max))

            if prix_max >= 0:
                queryset = queryset.filter(
                    prix_produit__lte=prix_max
                )

        except (InvalidOperation, TypeError, ValueError):
            pass

    # ============================================================
    # 6. PRODUITS LES PLUS RÉCENTS EN PREMIER
    # ============================================================

    return queryset.order_by(
        "-produit_line__produit__date_ajout"
    )
    
    