# userauths/utils.py
import logging

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
# Génération du token de confirmation
# ============================================================

def generate_email_token(user):
    serializer = URLSafeTimedSerializer(settings.SECRET_KEY)

    payload = {
        "user_id": user.pk,
        "email": user.email,
    }

    return serializer.dumps(
        payload,
        salt=EMAIL_CONFIRMATION_SALT,
    )


# ============================================================
# Validation du token de confirmation
# ============================================================

def verify_email_token(token):
    serializer = URLSafeTimedSerializer(settings.SECRET_KEY)

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

        if not isinstance(payload, dict):
            return {
                "status": "invalid",
                "user_id": None,
                "email": None,
            }

        user_id = payload.get("user_id")
        email = payload.get("email")

        if not user_id or not email:
            return {
                "status": "invalid",
                "user_id": None,
                "email": None,
            }

        return {
            "status": "ok",
            "user_id": user_id,
            "email": email,
        }

    except SignatureExpired:
        return {
            "status": "expired",
            "user_id": None,
            "email": None,
        }

    except BadSignature:
        return {
            "status": "invalid",
            "user_id": None,
            "email": None,
        }

    except Exception:
        logger.exception(
            "Erreur inattendue pendant la validation "
            "du token de confirmation."
        )

        return {
            "status": "invalid",
            "user_id": None,
            "email": None,
        }


# ============================================================
# Envoi de l’email de confirmation
# ============================================================

def send_confirmation_email(
    user,
    request=None,
    *,
    confirm_url=None,
    home_url=None,
):
    frontend_url = getattr(
        settings,
        "FRONTEND_URL",
        "https://rio-gold.com",
    ).rstrip("/")

    if not confirm_url:
        token = generate_email_token(user)

        if request is None:
            confirm_url = (
                f"{frontend_url}/confirm-email"
                f"?token={token}"
            )
        else:
            confirm_url = request.build_absolute_uri(
                f"{reverse('verify-email')}?token={token}"
            )

    home_url = (home_url or frontend_url).rstrip("/")

    context = {
        "user": user,
        "home_url": home_url,
        "confirm_url": confirm_url,
        "year": timezone.now().year,
    }

    subject = "Confirmez votre adresse email"

    html_message = render_to_string(
        "emails/email_confirmation.html",
        context,
    )

    plain_message = strip_tags(html_message)

    email = EmailMultiAlternatives(
        subject=subject,
        body=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )

    email.attach_alternative(
        html_message,
        "text/html",
    )

    email.send(fail_silently=False)

    logger.info(
        "Email de confirmation envoyé à %s.",
        user.email,
    )


# ============================================================
# Envoi de l’email de réinitialisation du mot de passe
# ============================================================

def send_password_reset_email(
    sender,
    instance,
    reset_password_token,
    *args,
    **kwargs,
):
    frontend_url = getattr(
        settings,
        "FRONTEND_URL",
        "https://rio-gold.com",
    ).rstrip("/")

    full_link = (
        f"{frontend_url}/password-reset/"
        f"{reset_password_token.key}"
    )

    context = {
        "full_link": full_link,
        "email_address": reset_password_token.user.email,
    }

    html_message = render_to_string(
        "backend/email.html",
        context=context,
    )

    plain_message = strip_tags(html_message)

    try:
        email = EmailMultiAlternatives(
            subject="Réinitialisation de votre mot de passe",
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[reset_password_token.user.email],
        )

        email.attach_alternative(
            html_message,
            "text/html",
        )

        email.send(fail_silently=False)

        logger.info(
            "Email de réinitialisation envoyé à %s.",
            reset_password_token.user.email,
        )

    except Exception:
        logger.exception(
            "Erreur lors de l'envoi de l'email "
            "de réinitialisation à %s.",
            reset_password_token.user.email,
        )
        

