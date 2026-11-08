# sale/services/client_bijouterie_service.py

from django.core.exceptions import ValidationError

from sale.models import ClientBijouterie


def verifier_client_associe(*, client, bijouterie):
    """
    Vérifie qu'un client est associé à la bijouterie.

    Un client facultatif est accepté.
    """

    if client is None:
        return

    if not ClientBijouterie.objects.filter(
        client_id=client.pk,
        bijouterie_id=bijouterie.pk,
    ).exists():
        raise ValidationError({
            "client": (
                "Ce client n'est pas associé "
                "à cette bijouterie."
            )
        })
        
