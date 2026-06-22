import logging
import threading
from datetime import datetime

from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags
from django_rest_passwordreset.signals import reset_password_token_created
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)


# ✅ Fonction pour générer un token
def generate_email_token(user):
    serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
    return serializer.dumps(user.email, salt="email-confirmation")


# ✅ Fonction pour valider le token
# def verify_email_token(token, expiration=getattr(settings, 'EMAIL_TOKEN_EXPIRATION', 60)):
#     serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
#     try:
#         email = serializer.loads(token, salt="email-confirmation", max_age=expiration)
#         return {"status": "valid", "email": email}
#     except SignatureExpired:
#         return {"status": "expired", "email": None}
#     except BadSignature:
#         return {"status": "invalid", "email": None}


def verify_email_token(token):
    serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
    expiration = getattr(settings, 'EMAIL_TOKEN_EXPIRATION', 60)

    try:
        email = serializer.loads(
            token,
            salt="email-confirmation",
            max_age=expiration,
        )
        return {"status": "ok", "email": email}
    except SignatureExpired:
        return {"status": "expired", "email": None}
    except BadSignature:
        return {"status": "invalid", "email": None}
    

def send_confirmation_email(user, request=None, *, confirm_url=None, home_url=None):
    if not confirm_url:
        token = generate_email_token(user)

        if request is None:
            frontend = getattr(settings, "FRONTEND_URL", "https://rio-gold.com").rstrip("/")
            confirm_url = f"{frontend}/confirm-email?token={token}"
        else:
            confirm_url = request.build_absolute_uri(
                reverse("verify-email") + f"?token={token}"
            )

    home_url = home_url or getattr(
        settings,
        "FRONTEND_URL",
        "https://rio-gold.com"
    ).rstrip("/")

    subject = "Confirmez votre adresse email"

    html = render_to_string("emails/email_confirmation.html", {
        "user": user,
        "home_url": home_url,
        "confirm_url": confirm_url,
        "year": datetime.now().year,
    })

    email = EmailMultiAlternatives(
        subject,
        "",
        settings.DEFAULT_FROM_EMAIL,
        [user.email]
    )
    email.attach_alternative(html, "text/html")
    email.send()

@receiver(reset_password_token_created)
def send_password_reset_email(sender, instance, reset_password_token, *args, **kwargs):
    sitelink = getattr(settings, "FRONTEND_URL", "https://rio-gold.com/")
    full_link = f"{sitelink.rstrip('/')}/password-reset/{reset_password_token.key}"

    context = {
        'full_link': full_link,
        'email_address': reset_password_token.user.email,
    }

    html_message = render_to_string("backend/email.html", context=context)
    plain_message = strip_tags(html_message)

    try:
        msg = EmailMultiAlternatives(
            subject="Réinitialisation de votre mot de passe",
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[reset_password_token.user.email]
        )
        msg.attach_alternative(html_message, "text/html")
        msg.send(fail_silently=False)
        logger.info("Email de réinitialisation envoyé.")
    except Exception as e:
        logger.error(f"Erreur d'envoi de l'email de réinitialisation : {e}")
