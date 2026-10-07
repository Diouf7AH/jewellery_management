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




