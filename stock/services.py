from django.db import IntegrityError, transaction
from django.db.models import F
from django.shortcuts import get_object_or_404

from stock.models import Stock
from store.models import Bijouterie


def stock_increment(*, produit_id: int, bijouterie_id: int | None, delta_qty: int, lot_id: int | None = None) -> Stock:
    if delta_qty is None or int(delta_qty) <= 0:
        raise ValueError("delta_qty doit être > 0")
    if bijouterie_id is not None:
        get_object_or_404(Bijouterie, pk=int(bijouterie_id))

    lookup = {
        "produit_id": int(produit_id),
        "bijouterie_id": int(bijouterie_id) if bijouterie_id is not None else None,
        "lot_id": int(lot_id) if lot_id is not None else None,
    }

    with transaction.atomic():
        st = Stock.objects.select_for_update().filter(**lookup).first()
        if st is None:
            try:
                st = Stock.objects.create(**lookup, quantite=int(delta_qty))
            except IntegrityError:
                st = Stock.objects.select_for_update().get(**lookup)
                Stock.objects.filter(pk=st.pk).update(quantite=F("quantite") + int(delta_qty))
                st.refresh_from_db(fields=["quantite"])
        else:
            Stock.objects.filter(pk=st.pk).update(quantite=F("quantite") + int(delta_qty))
            st.refresh_from_db(fields=["quantite"])
        return st

