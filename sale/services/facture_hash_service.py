# sale/services/facture_hash_service.py

import hashlib
import hmac
import json

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone


def _facture_signature_payload(facture):
    """
    Construit les données stables à signer.
    """

    vente = facture.vente
    client = getattr(vente, "client", None)

    return {
        "numero_facture": str(facture.numero_facture),
        "date_creation": facture.date_creation.isoformat(),
        "montant_total": str(facture.montant_total),
        "ninea": str(
            getattr(facture.bijouterie, "ninea", "") or ""
        ),
        "client": str(
            client.full_name if client else ""
        ),
    }


def _calculer_signature(facture):
    secret = getattr(
        settings,
        "FACTURE_SIGNING_KEY",
        None,
    )

    if not secret:
        raise ImproperlyConfigured(
            "FACTURE_SIGNING_KEY doit être configurée."
        )

    payload = json.dumps(
        _facture_signature_payload(facture),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return hmac.new(
        str(secret).encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def generate_facture_hash(facture):
    """
    Génère l'empreinte HMAC-SHA256 de la facture.

    À appeler lorsque la facture est définitive.
    """

    if facture.status != facture.STAT_PAYE:
        raise ValueError(
            "La facture doit être totalement payée."
        )

    if facture.type_facture != facture.TYPE_FACTURE:
        raise ValueError(
            "La facture doit être définitive."
        )

    signature = _calculer_signature(facture)

    facture.integrity_hash = signature
    facture.signed_at = timezone.now()

    facture.save(
        update_fields=[
            "integrity_hash",
            "signed_at",
        ]
    )

    return signature


def verify_facture_hash(facture):
    """
    Vérifie l'intégrité de la facture enregistrée.
    """

    if not facture.integrity_hash:
        return False

    expected = _calculer_signature(facture)

    return hmac.compare_digest(
        str(facture.integrity_hash),
        expected,
    )
    
    