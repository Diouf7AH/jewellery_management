from django.db import transaction
from django.utils import timezone

from e_commerce.models import (CommandeEcommerce, LivraisonEcommerce,
                               PaiementEcommerce)
from e_commerce.services.erp_sale import create_erp_sale_from_ecommerce
from e_commerce.services.payment import mark_payment_success
from e_commerce.services.stock import decrease_bijouterie_stock


@transaction.atomic
def confirm_ecommerce_payment(*, paiement, payload=None):
    paiement = PaiementEcommerce.objects.select_for_update().select_related(
        "commande",
        "commande__bijouterie",
    ).get(pk=paiement.pk)

    commande = CommandeEcommerce.objects.select_for_update().get(
        pk=paiement.commande_id
    )

    if commande.status == CommandeEcommerce.STATUS_PAID:
        return commande

    mark_payment_success(
        paiement=paiement,
        payload=payload,
    )

    vente, facture, paiement_erp, lignes_map = create_erp_sale_from_ecommerce(
        commande=commande,
        paiement_ecommerce=paiement,
    )

    decrease_bijouterie_stock(
        commande=commande,
        vente=vente,
        facture=facture,
        vendor=vente.vendor,
        lignes_map=lignes_map,
    )

    commande.status = CommandeEcommerce.STATUS_PAID
    commande.paid_at = timezone.now()
    commande.save(update_fields=["status", "paid_at", "updated_at"])
    
    LivraisonEcommerce.objects.get_or_create(
        commande=commande,
        defaults={
            "adresse_livraison": commande.adresse_livraison,
            "telephone_client": commande.telephone_client,
            "status": LivraisonEcommerce.STATUS_PREPARATION,
        }
    )
    
    # paiement est confirmé, on peut envoyer l'email de confirmation de commande au client
    from e_commerce.services.email import send_ecommerce_order_paid_email
    send_ecommerce_order_paid_email(commande=commande)

    return commande

