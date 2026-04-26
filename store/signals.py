# from django.db import transaction
# from django.db.models.signals import post_save
# from django.dispatch import receiver

# from .models import Produit


# @receiver(post_save, sender=Produit)
# def generate_qr_after_commit(sender, instance: Produit, created, **kwargs):
#     """
#     Génère le QR code uniquement si:
#     - produit enregistré
#     - slug existe
#     - qr_code est vide
#     Et seulement après COMMIT DB (évite fichiers inutiles si rollback).
#     """
#     if instance.qr_code:
#         return
#     if not instance.slug:
#         return

#     def _do():
#         # Re-check DB pour éviter double génération si plusieurs saves
#         fresh = Produit.objects.filter(pk=instance.pk).only("qr_code", "slug").first()
#         if not fresh or fresh.qr_code or not fresh.slug:
#             return

#         qr_content = fresh.produit_url
#         if not qr_content:
#             return

#         qr_file = Produit.generate_qr_code_image(
#             content=qr_content,
#             filename_hint=fresh.slug,
#         )
#         # save=True -> écrit le fichier + update DB
#         fresh.qr_code.save(qr_file.name, qr_file, save=True)

#     transaction.on_commit(_do)

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Produit


@receiver(post_save, sender=Produit)
def generate_qr_after_commit(sender, instance: Produit, created, **kwargs):
    """
    Génère le QR code POS uniquement si:
    - produit existe
    - qr_code est vide

    Contenu QR:
    - P:ID_PRODUIT
    """
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
    

