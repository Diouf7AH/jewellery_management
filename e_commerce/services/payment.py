# e_commerce/services/payment.py

from django.utils import timezone

from e_commerce.models import PaiementEcommerce


def initiate_payment(*, paiement):
    """
    Initialise un paiement e-commerce.

    Pour le moment :
    - simulation du provider ;
    - génération d'un checkout_url ;
    - génération d'une référence provider ;
    - génération d'un token.

    En production, cette fonction appellera réellement
    Wave / Orange Money / prestataire carte.
    """

    paiement.checkout_url = (
        f"https://rio-gold.com/pay/{paiement.uuid}/"
    )

    paiement.provider_reference = (
        f"ECOM-{paiement.uuid}"
    )

    paiement.payment_token = str(
        paiement.uuid
    )

    paiement.raw_response = {
        "message": "Lien de paiement généré",
        "provider": paiement.mode,
        "status": "pending",
    }

    paiement.save(
        update_fields=[
            "checkout_url",
            "provider_reference",
            "payment_token",
            "raw_response",
        ]
    )

    return paiement


def mark_payment_success(
    *,
    paiement,
    payload=None,
):
    """
    Marque localement le paiement comme confirmé.

    IMPORTANT :
    Cette fonction ne vérifie PAS le provider.

    Elle doit être appelée uniquement APRÈS validation
    du webhook / callback par le service de confirmation.
    """

    paiement.status = (
        PaiementEcommerce.STATUS_SUCCESS
    )

    paiement.callback_received = True
    paiement.confirmed_at = timezone.now()

    if payload is not None:
        paiement.raw_response = payload

    paiement.save(
        update_fields=[
            "status",
            "callback_received",
            "confirmed_at",
            "raw_response",
        ]
    )

    return paiement


