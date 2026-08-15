# sale/signals.py

from django.db.models.signals import post_migrate
from django.dispatch import receiver

from sale.models import ModePaiement


@receiver(post_migrate)
def create_default_mode_paiement(sender, **kwargs):
    """
    Crée ou met à jour les modes de paiement par défaut
    après les migrations de l'application sale.
    """

    if sender.name != "sale":
        return

    modes = [
        {
            "code": "cash",
            "nom": "Cash",
            "active": True,
            "ordre_affichage": 1,
            "necessite_reference": False,
            "est_mode_depot": False,
        },
        {
            "code": "wave",
            "nom": "Wave",
            "active": True,
            "ordre_affichage": 2,
            "necessite_reference": True,
            "est_mode_depot": False,
        },
        {
            "code": "orange_money",
            "nom": "Orange Money",
            "active": True,
            "ordre_affichage": 3,
            "necessite_reference": True,
            "est_mode_depot": False,
        },
        {
            "code": "depot",
            "nom": "Compte dépôt",
            "active": True,
            "ordre_affichage": 4,
            "necessite_reference": False,
            "est_mode_depot": True,
        },
        {
            "code": "tpe",
            "nom": "TPE",
            "active": True,
            "ordre_affichage": 5,
            "necessite_reference": True,
            "est_mode_depot": False,
            "description": "Paiement par terminal bancaire",
        },
    ]

    for mode in modes:
        code = mode["code"]

        defaults = {
            key: value
            for key, value in mode.items()
            if key != "code"
        }

        ModePaiement.objects.update_or_create(
            code=code,
            defaults=defaults,
        )


# # mettre à jour le statut de la facture automatiquement
# @receiver(post_save, sender=Paiement)
# def update_facture_status(sender, instance, created, **kwargs):

#     if not created:
#         return

#     facture = instance.facture
#     if not facture:
#         return

#     montant_total = facture.montant_total or Decimal("0.00")

#     PaiementLigne = apps.get_model("sale", "PaiementLigne")

#     total_paye = (
#         PaiementLigne.objects
#         .filter(paiement__facture=facture)
#         .aggregate(total=Sum("montant_paye"))["total"]
#         or Decimal("0.00")
#     )

#     if total_paye <= Decimal("0.00"):
#         new_status = Facture.STAT_NON_PAYE

#     elif total_paye >= montant_total:
#         new_status = Facture.STAT_PAYE

#     else:
#         new_status = Facture.STAT_PARTIEL

#     if facture.status != new_status:
#         facture.status = new_status
#         facture.save(update_fields=["status"])
        




