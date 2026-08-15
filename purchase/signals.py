# purchase/signals.py

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Achat, ProduitLine


def schedule_achat_total_update(achat_id):
    """
    Recalcule le montant de l'achat après validation
    de la transaction en cours.

    IMPORTANT :
    ce signal ne touche jamais :
    - Stock
    - VendorStock
    - InventoryMovement
    """

    def _update():
        achat = Achat.objects.filter(pk=achat_id).first()

        if achat:
            achat.update_total(save=True)

    transaction.on_commit(_update)


@receiver(
    post_save,
    sender=ProduitLine,
    dispatch_uid="purchase_produitline_post_save",
)
def produit_line_post_save(sender, instance, **kwargs):
    schedule_achat_total_update(
        instance.lot.achat_id
    )


@receiver(
    post_delete,
    sender=ProduitLine,
    dispatch_uid="purchase_produitline_post_delete",
)
def produit_line_post_delete(sender, instance, **kwargs):
    schedule_achat_total_update(
        instance.lot.achat_id
    )
    

