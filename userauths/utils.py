# userauths/utils.py

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)

EMAIL_CONFIRMATION_SALT = "email-confirmation"


# ============================================================
# HELPERS
# ============================================================

def get_frontend_url():
    """
    Retourne l'URL du frontend Angular.
    """
    return getattr(
        settings,
        "FRONTEND_URL",
        "https://rio-gold.com",
    ).rstrip("/")


def get_email_token_serializer():
    """
    Serializer signé avec la clé secrète Django.
    """
    return URLSafeTimedSerializer(
        secret_key=settings.SECRET_KEY,
    )


def invalid_email_token_result(status="invalid"):
    return {
        "status": status,
        "user_id": None,
        "email": None,
    }


# ============================================================
# 1. GÉNÉRATION DU TOKEN DE CONFIRMATION
# ============================================================

def generate_email_token(user):
    """
    Génère un token signé contenant :
        - l'identifiant utilisateur
        - l'adresse email

    Le token est limité dans le temps.
    """

    serializer = get_email_token_serializer()

    payload = {
        "user_id": user.pk,
        "email": user.email.strip().lower(),
    }

    return serializer.dumps(
        payload,
        salt=EMAIL_CONFIRMATION_SALT,
    )


# ============================================================
# 2. VÉRIFICATION DU TOKEN DE CONFIRMATION
# ============================================================

def verify_email_token(token):
    """
    Vérifie :
        - la signature du token
        - son expiration
        - la structure du contenu

    Retourne :
        status = ok | expired | invalid
    """

    if not isinstance(token, str) or not token.strip():
        return invalid_email_token_result()

    serializer = get_email_token_serializer()

    expiration = getattr(
        settings,
        "EMAIL_TOKEN_EXPIRATION",
        60 * 60 * 24,
    )

    try:
        payload = serializer.loads(
            token,
            salt=EMAIL_CONFIRMATION_SALT,
            max_age=expiration,
        )

    except SignatureExpired:
        return invalid_email_token_result("expired")

    except BadSignature:
        return invalid_email_token_result()

    except Exception:
        logger.exception(
            "Erreur inattendue pendant la validation "
            "d'un token de confirmation."
        )
        return invalid_email_token_result()

    if not isinstance(payload, dict):
        return invalid_email_token_result()

    user_id = payload.get("user_id")
    email = payload.get("email")

    if (
        not isinstance(user_id, int)
        or isinstance(user_id, bool)
        or user_id <= 0
        or not isinstance(email, str)
    ):
        return invalid_email_token_result()

    email = email.strip().lower()

    if not email or "@" not in email:
        return invalid_email_token_result()

    return {
        "status": "ok",
        "user_id": user_id,
        "email": email,
    }


# ============================================================
# 3. ENVOI DE L'EMAIL DE CONFIRMATION
# ============================================================

def send_confirmation_email(
    user,
    request=None,
    *,
    confirm_url=None,
    home_url=None,
):
    """
    Envoie un email de confirmation HTML + texte.

    Si confirm_url n'est pas fourni :
        - avec request : lien vers l'API Django
        - sans request : lien vers Angular

    Les URLs peuvent également être transmises
    explicitement par la vue.
    """

    frontend_url = get_frontend_url()

    if not confirm_url:

        token = generate_email_token(user)

        query = urlencode({
            "token": token,
        })

        if request is not None:
            verification_path = reverse(
                "verify-email"
            )

            confirm_url = request.build_absolute_uri(
                f"{verification_path}?{query}"
            )

        else:
            confirm_url = (
                f"{frontend_url}/confirm-email?{query}"
            )

    home_url = (
        home_url or frontend_url
    ).rstrip("/")

    context = {
        "user": user,
        "home_url": home_url,
        "confirm_url": confirm_url,
        "year": timezone.now().year,
    }

    html_message = render_to_string(
        "emails/email_confirmation.html",
        context,
    )

    plain_message = strip_tags(html_message)

    email = EmailMultiAlternatives(
        subject="Confirmez votre adresse email",
        body=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )

    email.attach_alternative(
        html_message,
        "text/html",
    )

    sent_count = email.send(
        fail_silently=False,
    )

    if sent_count != 1:
        raise RuntimeError(
            "L'email de confirmation n'a pas été accepté "
            "par le backend d'envoi."
        )

    logger.info(
        "Email de confirmation accepté pour user_id=%s.",
        user.pk,
    )


# ============================================================
# 4. ENVOI DE L'EMAIL DE RÉINITIALISATION
# ============================================================

def send_password_reset_email(
    sender,
    instance,
    reset_password_token,
    **kwargs,
):
    """
    Envoie un lien de réinitialisation du mot de passe.

    Les erreurs d'envoi remontent au signal,
    qui les journalise.

    Ne journalise jamais la clé du token.
    """

    frontend_url = get_frontend_url()

    reset_user = reset_password_token.user

    full_link = (
        f"{frontend_url}/password-reset/"
        f"{reset_password_token.key}"
    )

    context = {
        "full_link": full_link,
        "email_address": reset_user.email,
    }

    html_message = render_to_string(
        "backend/email.html",
        context=context,
    )

    plain_message = strip_tags(html_message)

    email = EmailMultiAlternatives(
        subject="Réinitialisation de votre mot de passe",
        body=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[reset_user.email],
    )

    email.attach_alternative(
        html_message,
        "text/html",
    )

    sent_count = email.send(
        fail_silently=False,
    )

    if sent_count != 1:
        raise RuntimeError(
            "L'email de réinitialisation n'a pas été "
            "accepté par le backend d'envoi."
        )

    logger.info(
        "Email de réinitialisation accepté "
        "pour user_id=%s.",
        reset_user.pk,
    )

