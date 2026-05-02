from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Produit


@receiver(post_save, sender=Produit, weak=False)
def generate_qr_after_commit(sender, instance: Produit, created, **kwargs):
    if instance.qr_code and instance.qr_code.name:
        return

    def _do():
        with transaction.atomic():
            fresh = (
                Produit.objects
                .select_for_update()
                .filter(pk=instance.pk)
                .only("id", "qr_code", "slug", "sku", "nom")
                .first()
            )

            if not fresh or (fresh.qr_code and fresh.qr_code.name):
                return

            qr_file = Produit.generate_qr_code_image(
                produit=fresh,
                filename_hint=fresh.sku or fresh.slug or fresh.nom or str(fresh.id),
            )

            fresh.qr_code.save(qr_file.name, qr_file, save=True)

    transaction.on_commit(_do)
    

