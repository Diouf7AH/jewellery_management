# e_commerce/services/create_order.py
from django.db import transaction

from e_commerce.models import (CommandeEcommerce, CommandeEcommerceLigne,
                               PaiementEcommerce)


@transaction.atomic
def create_ecommerce_order(*, validated_data):
    lignes = validated_data.pop("lignes_validees")
    mode_paiement = validated_data.pop("mode_paiement")

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

