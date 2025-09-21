from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import AchatProduit

@receiver(post_delete, sender=AchatProduit)
def _recalc_apres_delete(sender, instance, **kwargs):
    if instance.achat_id:
        instance.achat.update_total(save=True)