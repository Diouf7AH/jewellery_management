from .models import Stock
from django.shortcuts import get_object_or_404
from store.models import Bijouterie
from django.db.models import F

def upsert_stock_increment(produit_id: int, bijouterie_id: int | None, delta_qty: int):
    if delta_qty <= 0:
        return None

    if bijouterie_id is None:
        # réservé
        reservation_key = f"RES-{produit_id}"
        stock, _ = (Stock.objects.select_for_update()
            .get_or_create(
                produit_id=produit_id,
                bijouterie=None,
                reservation_key=reservation_key,
                defaults={"quantite": 0, "is_reserved": True},   # ✅
            ))
    else:
        # attribué
        get_object_or_404(Bijouterie, pk=bijouterie_id)
        stock, _ = (Stock.objects.select_for_update()
            .get_or_create(
                produit_id=produit_id,
                bijouterie_id=bijouterie_id,
                defaults={"quantite": 0, "is_reserved": False},  # ✅
            ))

    Stock.objects.filter(pk=stock.pk).update(quantite=F("quantite") + delta_qty)
    stock.refresh_from_db(fields=["quantite"])
    return stock