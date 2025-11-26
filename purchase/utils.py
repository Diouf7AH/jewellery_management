# from django.db.models import F
# from django.shortcuts import get_object_or_404

# from stock.models import Stock
# from inventory.models import Bucket  # tes enums d’inventaire

# def _res_key(produit_id: int) -> str:
#     return f"RES-{produit_id}"

# def _get_reserved_locked(produit_id: int) -> Stock | None:
#     try:
#         return (Stock.objects
#                 .select_for_update()
#                 .get(produit_id=produit_id, bijouterie=None, reservation_key=_res_key(produit_id)))
#     except Stock.DoesNotExist:
#         return None

# def _get_alloc_locked(produit_id: int, bijouterie_id: int) -> Stock | None:
#     try:
#         return (Stock.objects
#                 .select_for_update()
#                 .get(produit_id=produit_id, bijouterie_id=bijouterie_id))
#     except Stock.DoesNotExist:
#         return None

# def _safe_decrement(stock: Stock, qty: int):
#     """Décrémente de façon atomique avec garde-fou."""
#     if qty <= 0:
#         return
#     # vérif dispo
#     stock.refresh_from_db(fields=["quantite"])
#     if stock.quantite < qty:
#         raise ValueError(f"Stock insuffisant (disponible={stock.quantite}, demandé={qty}).")
#     # décrément atomique
#     updated = (Stock.objects
#             .filter(pk=stock.pk, quantite__gte=qty)
#             .update(quantite=F("quantite") - qty))
#     if updated == 0:
#         # autre concurrent / plus assez de stock
#         raise ValueError("Conflit de mise à jour du stock (réessayez).")

# def _decrement_bucket(produit_id: int, bijouterie_id: int | None, qty: int):
#     if qty <= 0:
#         return
#     if bijouterie_id is None:
#         stock = _get_reserved_locked(produit_id)
#         if not stock:
#             raise ValueError("Aucun stock réservé pour ce produit.")
#         _safe_decrement(stock, qty)
#     else:
#         stock = _get_alloc_locked(produit_id, bijouterie_id)
#         if not stock:
#             raise ValueError(f"Aucun stock attribué pour cette bijouterie (id={bijouterie_id}).")
#         _safe_decrement(stock, qty)


# def _auto_decrement_any_bucket_with_trace(produit_id: int, qty: int):
#     """
#     Retire automatiquement 'qty' en priorisant :
#     1) le stock réservé
#     2) puis les stocks attribués (toutes bijouteries)
#     Retourne une liste de dicts décrivant **d'où** on a retiré :
#     [
#       {"src_bucket": Bucket.RESERVED,   "src_bijouterie_id": None,        "qty": 3},
#       {"src_bucket": Bucket.BIJOUTERIE, "src_bijouterie_id": 2,           "qty": 2},
#       ...
#     ]
#     Lève ValueError si insuffisant.
#     """
#     trace = []
#     if qty <= 0:
#         return trace

#     # 1) réservé
#     reservation_key = f"RES-{produit_id}"
#     reserved = (
#         Stock.objects.select_for_update()
#         .filter(produit_id=produit_id, bijouterie__isnull=True, reservation_key=reservation_key)
#         .first()
#     )
#     if reserved and reserved.quantite > 0:
#         take = min(reserved.quantite, qty)
#         if take > 0:
#             Stock.objects.filter(pk=reserved.pk).update(quantite=F("quantite") - take)
#             qty -= take
#             trace.append({"src_bucket": Bucket.RESERVED, "src_bijouterie_id": None, "qty": take})

#     if qty <= 0:
#         return trace

#     # 2) attribué (toutes bijouteries ayant du stock)
#     buckets = (
#         Stock.objects.select_for_update()
#         .filter(produit_id=produit_id, bijouterie__isnull=False, quantite__gt=0)
#         .order_by("bijouterie_id")
#     )
#     for b in buckets:
#         if qty <= 0:
#             break
#         take = min(b.quantite, qty)
#         if take > 0:
#             Stock.objects.filter(pk=b.pk).update(quantite=F("quantite") - take)
#             qty -= take
#             trace.append({"src_bucket": Bucket.BIJOUTERIE, "src_bijouterie_id": b.bijouterie_id, "qty": take})

#     if qty > 0:
#         raise ValueError(f"Stock global insuffisant pour produit={produit_id}. Reste à retirer={qty}")

#     return trace



from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import Coalesce

from purchase.models import Achat, ProduitLine


def recalc_totaux_achat(achat: Achat, save: bool = True):
    """
    Recalcule :
      base_HT = Σ (quantite * produit.poids * prix_achat_gramme)
      HT      = base_HT + frais_transport + frais_douane
      TTC     = HT (pas de TVA pour l’instant)
    """
    expr_ht = ExpressionWrapper(
        F("quantite")
        * Coalesce(F("produit__poids"), 1)
        * Coalesce(F("prix_achat_gramme"), Decimal("0.00")),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )

    agg = (
        ProduitLine.objects
        .filter(lot__achat=achat)
        .aggregate(base_ht=Coalesce(Sum(expr_ht), Decimal("0.00")))
    )

    base_ht = agg["base_ht"] or Decimal("0.00")
    frais = (achat.frais_transport or Decimal("0.00")) + (achat.frais_douane or Decimal("0.00"))

    achat.montant_total_ht = base_ht + frais
    achat.montant_total_ttc = achat.montant_total_ht

    if save:
        achat.save(update_fields=["montant_total_ht", "montant_total_ttc"])
        