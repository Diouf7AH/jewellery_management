# e_commerce/services/create_order.py

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction

from e_commerce.models import (CommandeEcommerce, CommandeEcommerceLigne,
                               PaiementEcommerce)


@transaction.atomic
def create_ecommerce_order(*, validated_data):
    lignes = validated_data.pop(
        "lignes_validees"
    )

    mode_paiement = validated_data.pop(
        "mode_paiement"
    )

    if not lignes:
        raise ValueError(
            "Une commande e-commerce doit contenir "
            "au moins une ligne."
        )

    commande = CommandeEcommerce.objects.create(
        **validated_data,
        status=CommandeEcommerce.STATUS_PENDING,
    )

    for ligne in lignes:
        CommandeEcommerceLigne.objects.create(
            commande=commande,
            **ligne,
        )

    paiement = PaiementEcommerce.objects.create(
        commande=commande,
        mode=mode_paiement,
        status=PaiementEcommerce.STATUS_PENDING,
        montant=commande.montant_a_payer,
        frais_transaction=commande.frais_transaction,
    )

    return commande, paiement


def send_ecommerce_order_paid_email(*, commande):
    """
    Envoie un email de confirmation après paiement
    d'une commande e-commerce.

    Cette fonction doit être appelée après le COMMIT
    de la transaction de confirmation du paiement.
    """

    email_client = commande.email_client

    if not email_client:
        return False

    sujet = "Confirmation de votre commande Rio Gold"

    message = (
        f"Bonjour {commande.nom_client},\n\n"
        f"Votre paiement a été confirmé avec succès.\n\n"
        f"Commande : {commande.uuid}\n"
        f"Montant payé : {commande.montant_a_payer} FCFA\n"
        f"Statut : Payée\n\n"
        f"Nous préparons maintenant votre commande.\n\n"
        f"Merci pour votre confiance.\n"
        f"Rio Gold"
    )

    send_mail(
        subject=sujet,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[
            email_client,
        ],
        fail_silently=False,
    )

    return True