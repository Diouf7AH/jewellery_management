from django.utils import timezone

from e_commerce.models import PaiementEcommerce


def initiate_payment(*, paiement):
    """
    Ici tu brancheras Wave / Orange Money / Carte.
    Pour l'instant on simule un lien de paiement.
    """

    paiement.checkout_url = f"https://rio-gold.com/pay/{paiement.uuid}/"
    paiement.provider_reference = f"ECOM-{paiement.uuid}"
    paiement.payment_token = str(paiement.uuid)
    paiement.raw_response = {
        "message": "Lien de paiement généré",
        "provider": paiement.mode,
    }
    paiement.save(update_fields=[
        "checkout_url",
        "provider_reference",
        "payment_token",
        "raw_response",
    ])

    return paiement


def mark_payment_success(*, paiement, payload=None):
    paiement.status = PaiementEcommerce.STATUS_SUCCESS
    paiement.callback_received = True
    paiement.confirmed_at = timezone.now()
    paiement.raw_response = payload or {}
    paiement.save(update_fields=[
        "status",
        "callback_received",
        "confirmed_at",
        "raw_response",
    ])
    return paiement

