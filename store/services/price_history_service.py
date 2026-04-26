from decimal import Decimal

from django.db import transaction

from store.models import MarquePuretePrixHistory


@transaction.atomic
def update_marque_purete_price(*, obj, new_price, user=None, bijouterie=None, source="api", note=None):
    """
    Met à jour le prix courant d'un MarquePurete
    et crée une ligne d'historique si le prix change réellement.
    """
    old_price = Decimal(str(obj.prix or "0.00"))
    new_price = Decimal(str(new_price or "0.00"))

    if new_price < 0:
        raise ValueError("Le nouveau prix ne peut pas être négatif.")

    # Aucun changement -> pas d'historique
    if old_price == new_price:
        return obj, None

    obj.prix = new_price
    obj.save(update_fields=["prix"])

    history = MarquePuretePrixHistory.objects.create(
        marque_purete=obj,
        marque=obj.marque,
        purete=obj.purete,
        bijouterie=bijouterie,
        ancien_prix=old_price,
        nouveau_prix=new_price,
        changed_by=user,
        source=source,
        note=note,
    )

    return obj, history

