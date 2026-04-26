# sale/services/facture_hash_service.py
# signature numerique (hash) pour les factures, basée sur des données clés

import hashlib

from django.utils import timezone


def generate_facture_hash(facture):
    """
    Génère une signature numérique (hash SHA256)
    """

    vente = facture.vente
    client = getattr(vente, "client", None)

    raw_string = "|".join([
        str(facture.numero_facture),
        str(facture.date_creation),
        str(facture.montant_total),
        str(facture.bijouterie.ninea or ""),
        str(client.full_name if client else ""),
    ])

    hash_value = hashlib.sha256(raw_string.encode()).hexdigest()

    facture.integrity_hash = hash_value
    facture.signed_at = timezone.now()
    facture.save(update_fields=["integrity_hash", "signed_at"])

    return hash_value

