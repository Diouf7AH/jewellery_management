# sale/services/facture_hash_service.py

from __future__ import annotations

import hashlib
import hmac
import json

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.utils import timezone


def _facture_signature_payload(facture) -> dict:
    """
    Construit les données stables de la facture à signer.

    Attention :
    Les champs signés doivent rester inchangés
    après la génération de la signature.
    """

    vente = facture.vente
    client = getattr(vente, "client", None)

    client_nom = ""

    if client is not None:
        client_nom = str(
            getattr(client, "full_name", "") or ""
        )

    return {
        "numero_facture": str(
            facture.numero_facture
        ),
        "date_creation": (
            facture.date_creation.isoformat()
        ),
        "montant_total": str(
            facture.montant_total
        ),
        "ninea": str(
            getattr(
                facture.bijouterie,
                "ninea",
                "",
            ) or ""
        ),
        "client": client_nom,
    }


def _calculer_signature(facture) -> str:
    """
    Calcule la signature HMAC-SHA256.
    """

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


def generate_facture_hash(facture) -> str:
    """
    Génère la signature d'une facture définitive.

    Refuse de remplacer une signature existante.
    """

    if facture.status != facture.STAT_PAYE:
        raise ValidationError(
            "La facture doit être totalement payée."
        )

    if facture.type_facture != facture.TYPE_FACTURE:
        raise ValidationError(
            "La facture doit être définitive."
        )

    # Ne jamais remplacer silencieusement
    # une signature existante.
    if facture.integrity_hash:
        raise ValidationError(
            "Cette facture possède déjà une signature. "
            "Une nouvelle signature est interdite."
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


def verify_facture_hash(facture) -> bool:
    """
    Vérifie l'intégrité de la facture.

    True  : signature valide.
    False : signature absente ou différente.
    """

    if not facture.integrity_hash:
        return False

    expected = _calculer_signature(facture)

    return hmac.compare_digest(
        str(facture.integrity_hash),
        expected,
    )
