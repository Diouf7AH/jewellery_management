# sale/services/client_access_service.py
from django.db.models import Q

from sale.models import Client, Facture, Paiement, Vente


def clients_accessibles(bijouteries_autorisees):
    return Client.objects.filter(
        bijouteries__in=bijouteries_autorisees
    ).distinct()


def ventes_client_accessibles(
    client_id,
    bijouteries_autorisees,
):
    return Vente.objects.filter(
        client_id=client_id,
        bijouterie__in=bijouteries_autorisees,
    )


def factures_client_accessibles(
    client_id,
    bijouteries_autorisees,
):
    return Facture.objects.filter(
        vente__client_id=client_id,
        bijouterie__in=bijouteries_autorisees,
    )


def paiements_client_accessibles(
    client_id,
    bijouteries_autorisees,
):
    return Paiement.objects.filter(
        Q(vente__client_id=client_id)
        | Q(facture__vente__client_id=client_id),
    ).filter(
        Q(vente__bijouterie__in=bijouteries_autorisees)
        | Q(facture__bijouterie__in=bijouteries_autorisees),
    ).distinct()


