# e_commerce/services/signatures_paiement.py

import hashlib
import hmac
import time

from django.conf import settings
from django.core.exceptions import ValidationError

# ============================================================
# WAVE
# ============================================================

def verifier_signature_wave(request):
    webhook_secret = getattr(
        settings,
        "WAVE_WEBHOOK_SECRET",
        None,
    )

    if not webhook_secret:
        raise ValidationError(
            "WAVE_WEBHOOK_SECRET n'est pas configuré."
        )

    signature_header = request.headers.get(
        "Wave-Signature"
    )

    if not signature_header:
        raise ValidationError(
            "Signature Wave manquante."
        )

    raw_body = request.body

    try:
        raw_body_text = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        raise ValidationError(
            "Le corps du webhook Wave est invalide."
        )

    timestamp = None
    signatures = []

    for part in signature_header.split(","):
        part = part.strip()

        if part.startswith("t="):
            timestamp = part[2:]

        elif part.startswith("v1="):
            signature = part[3:].strip()

            if signature:
                signatures.append(signature)

    if not timestamp:
        raise ValidationError(
            "Timestamp Wave manquant."
        )

    if not signatures:
        raise ValidationError(
            "Signature Wave v1 manquante."
        )

    try:
        timestamp_int = int(timestamp)

    except (TypeError, ValueError):
        raise ValidationError(
            "Timestamp Wave invalide."
        )

    current_timestamp = int(time.time())

    age_seconds = (
        current_timestamp - timestamp_int
    )

    if age_seconds > 300:
        raise ValidationError(
            "Le webhook Wave est expiré."
        )

    if age_seconds < -30:
        raise ValidationError(
            "Le timestamp Wave est trop éloigné "
            "dans le futur."
        )

    signed_payload = (
        timestamp + raw_body_text
    ).encode("utf-8")

    expected_signature = hmac.new(
        key=webhook_secret.encode("utf-8"),
        msg=signed_payload,
        digestmod=hashlib.sha256,
    ).hexdigest()

    signature_valide = any(
        hmac.compare_digest(
            expected_signature,
            signature,
        )
        for signature in signatures
    )

    if not signature_valide:
        raise ValidationError(
            "Signature Wave invalide."
        )

    return True


# ============================================================
# ORANGE MONEY
# ============================================================

def verifier_signature_orange_money(request):
    raise NotImplementedError(
        "La vérification Orange Money "
        "n'est pas encore configurée."
    )


# ============================================================
# CARTE BANCAIRE
# ============================================================

def verifier_signature_carte(request):
    raise NotImplementedError(
        "La vérification du paiement par carte "
        "n'est pas encore configurée."
    )
    

