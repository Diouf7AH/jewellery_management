from decimal import Decimal

from django.apps import apps
from django.db.models import Sum
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from sale.models import Facture, ModePaiement, Paiement, PaiementLigne


@receiver(post_migrate)
def create_default_mode_paiement(sender, **kwargs):
    if sender.name != "sale":
        return

    ModePaiement.objects.get_or_create(
        code="cash",
        defaults={
            "nom": "Cash",
            "actif": True,
            "ordre_affichage": 1,
            "necessite_reference": False,
            "est_mode_depot": False,
        }
    )

    ModePaiement.objects.get_or_create(
        code="wave",
        defaults={
            "nom": "Wave",
            "actif": True,
            "ordre_affichage": 2,
            "necessite_reference": True,
            "est_mode_depot": False,
        }
    )

    ModePaiement.objects.get_or_create(
        code="orange_money",
        defaults={
            "nom": "Orange Money",
            "actif": True,
            "ordre_affichage": 3,
            "necessite_reference": True,
            "est_mode_depot": False,
        }
    )

    ModePaiement.objects.get_or_create(
        code="depot",
        defaults={
            "nom": "Compte dépôt",
            "actif": True,
            "ordre_affichage": 4,
            "necessite_reference": False,
            "est_mode_depot": True,
        }
    )

# # mettre à jour le statut de la facture automatiquement
# @receiver(post_save, sender=Paiement)
# def update_facture_status(sender, instance, created, **kwargs):
#     if not created:
#         return
#     f = instance.facture
#     total = getattr(f, "montant_total", None)
#     if total is None:
#         return
#     total_paye = f.paiements.aggregate(t=Sum("montant_paye"))["t"] or Decimal("0.00")
#     if total_paye >= total and getattr(Facture, "STAT_PAYE", None):
#         f.status = Facture.STAT_PAYE
#         f.save(update_fields=["status"])



# mettre à jour le statut de la facture automatiquement
@receiver(post_save, sender=Paiement)
def update_facture_status(sender, instance, created, **kwargs):

    if not created:
        return

    facture = instance.facture
    if not facture:
        return

    montant_total = facture.montant_total or Decimal("0.00")

    PaiementLigne = apps.get_model("sale", "PaiementLigne")

    total_paye = (
        PaiementLigne.objects
        .filter(paiement__facture=facture)
        .aggregate(total=Sum("montant_paye"))["total"]
        or Decimal("0.00")
    )

    if total_paye <= Decimal("0.00"):
        new_status = Facture.STAT_NON_PAYE

    elif total_paye >= montant_total:
        new_status = Facture.STAT_PAYE

    else:
        new_status = Facture.STAT_PARTIEL

    if facture.status != new_status:
        facture.status = new_status
        facture.save(update_fields=["status"])
        




