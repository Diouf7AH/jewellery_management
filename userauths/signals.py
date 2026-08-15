# userauths/signals.py
import logging

from django.conf import settings
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver
from django_rest_passwordreset.signals import reset_password_token_created

from backend.roles import SYSTEM_ROLES
from userauths.models import Role

from .models import Profile
from .utils import send_password_reset_email

logger = logging.getLogger(__name__)


@receiver(
    reset_password_token_created,
    dispatch_uid="userauths_password_reset_token_created",
)
def password_reset_token_created_handler(
    sender,
    instance,
    reset_password_token,
    *args,
    **kwargs,
):
    try:
        send_password_reset_email(
            sender=sender,
            instance=instance,
            reset_password_token=reset_password_token,
            *args,
            **kwargs,
        )

    except Exception:
        logger.exception(
            (
                "Erreur lors de l'envoi de l'email de "
                "réinitialisation pour l'utilisateur %s."
            ),
            reset_password_token.user_id,
        )


@receiver(
    post_save,
    sender=settings.AUTH_USER_MODEL,
    dispatch_uid="userauths_create_profile",
)
def create_profile_for_new_user(
    sender,
    instance,
    created,
    raw=False,
    **kwargs,
):
    if raw or not created:
        return

    Profile.objects.get_or_create(
        user=instance,
    )
    

# Crée automatiquement les rôles système
#     après les migrations.
@receiver(
    post_migrate,
    dispatch_uid="userauths_create_system_roles",
)
def create_system_roles(
    sender,
    **kwargs,
):
    """
    Crée automatiquement les rôles système
    après les migrations.

    Cette opération est idempotente :
    les rôles existants ne sont pas recréés.
    """

    if sender.name != "userauths":
        return

    for role_name in sorted(SYSTEM_ROLES):
        Role.objects.get_or_create(
            role=role_name,
        )