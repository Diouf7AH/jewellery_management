from stock.models import Stock


def get_ecommerce_products(*, bijouterie_id=None):
    qs = Stock.objects.select_related(
        "produit_line",
        "produit_line__produit",
        "produit_line__produit__categorie",
        "produit_line__produit__marque",
        "produit_line__produit__modele",
        "produit_line__produit__purete",
        "bijouterie",
    ).filter(
        is_reserve=False,
        bijouterie__isnull=False,
        en_stock__gt=0,
    )

    if bijouterie_id:
        qs = qs.filter(bijouterie_id=bijouterie_id)

    return qs.order_by("-updated_at")


def get_ecommerce_product_by_uuid(*, uuid):
    return Stock.objects.select_related(
        "produit_line",
        "produit_line__produit",
        "produit_line__produit__categorie",
        "produit_line__produit__marque",
        "produit_line__produit__modele",
        "produit_line__produit__purete",
        "bijouterie",
    ).get(
        produit_line__produit__uuid=uuid,
        is_reserve=False,
        bijouterie__isnull=False,
        en_stock__gt=0,
    )

