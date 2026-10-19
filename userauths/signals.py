# # userauths/signals.py
# import logging

# from django.conf import settings
# from django.db.models.signals import post_migrate, post_save
# from django.dispatch import receiver
# from django_rest_passwordreset.signals import reset_password_token_created

# from backend.roles import SYSTEM_ROLES
# from userauths.models import Role

# from .models import Profile
# from .utils import send_password_reset_email

# logger = logging.getLogger(__name__)


# @receiver(
#     reset_password_token_created,
#     dispatch_uid="userauths_password_reset_token_created",
# )
# def password_reset_token_created_handler(
#     sender,
#     instance,
#     reset_password_token,
#     *args,
#     **kwargs,
# ):
#     try:
#         send_password_reset_email(
#             sender=sender,
#             instance=instance,
#             reset_password_token=reset_password_token,
#             *args,
#             **kwargs,
#         )

#     except Exception:
#         logger.exception(
#             (
#                 "Erreur lors de l'envoi de l'email de "
#                 "réinitialisation pour l'utilisateur %s."
#             ),
#             reset_password_token.user_id,
#         )


# @receiver(
#     post_save,
#     sender=settings.AUTH_USER_MODEL,
#     dispatch_uid="userauths_create_profile",
# )
# def create_profile_for_new_user(
#     sender,
#     instance,
#     created,
#     raw=False,
#     **kwargs,
# ):
#     if raw or not created:
#         return

#     Profile.objects.get_or_create(
#         user=instance,
#     )
    

# # Crée automatiquement les rôles système
# #     après les migrations.
# @receiver(
#     post_migrate,
#     dispatch_uid="userauths_create_system_roles",
# )
# def create_system_roles(
#     sender,
#     **kwargs,
# ):
#     """
#     Crée automatiquement les rôles système
#     après les migrations.

#     Cette opération est idempotente :
#     les rôles existants ne sont pas recréés.
#     """

#     if sender.name != "userauths":
#         return

#     for role_name in sorted(SYSTEM_ROLES):
#         Role.objects.get_or_create(
#             role=role_name,
#         )


# userauths/signals.py

import logging

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver
from django_rest_passwordreset.signals import reset_password_token_created

from backend.roles import SYSTEM_ROLES

from .models import Profile, Role
from .utils import send_password_reset_email

logger = logging.getLogger(__name__)


# ============================================================
# 1. RÉINITIALISATION DU MOT DE PASSE
# ============================================================

@receiver(
    reset_password_token_created,
    dispatch_uid="userauths_password_reset_token_created",
)
def password_reset_token_created_handler(
    sender,
    instance,
    reset_password_token,
    **kwargs,
):
    """
    Envoie l'email de réinitialisation du mot de passe
    après validation de la transaction.

    Une erreur SMTP est journalisée sans interrompre
    la création du token.
    """

    token_pk = reset_password_token.pk
    user_id = reset_password_token.user_id

    def send_email():
        try:
            token = type(reset_password_token).objects.get(
                pk=token_pk,
            )

            send_password_reset_email(
                sender=sender,
                instance=instance,
                reset_password_token=token,
                **kwargs,
            )

        except Exception:
            logger.exception(
                "Erreur lors de l'envoi de l'email "
                "de réinitialisation pour user_id=%s.",
                user_id,
            )

    transaction.on_commit(send_email)


# ============================================================
# 2. CRÉATION AUTOMATIQUE DU PROFIL PERSONNEL
# ============================================================

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
    """
    Crée automatiquement un Profile
    lorsqu'un nouvel utilisateur est créé.

    - Ne s'exécute pas lors d'une mise à jour.
    - Ignore les chargements de fixtures.
    - Évite la duplication du profil.
    """

    if raw or not created:
        return

    Profile.objects.get_or_create(
        user=instance,
    )


# ============================================================
# 3. INITIALISATION DES RÔLES SYSTÈME
# ============================================================

@receiver(
    post_migrate,
    dispatch_uid="userauths_create_system_roles",
)
def create_system_roles(
    sender,
    using,
    apps,
    **kwargs,
):
    """
    Initialise les rôles système après les migrations
    de l'application userauths.

    Idempotent :
        un rôle existant n'est pas recréé.

    Compatible avec :
        - les migrations
        - les bases de données multiples
        - les modèles historiques de migration
    """

    if sender.label != "userauths":
        return

    RoleModel = apps.get_model(
        "userauths",
        "Role",
    )

    for role_name in sorted(SYSTEM_ROLES):
        RoleModel.objects.using(using).get_or_create(
            role=role_name,
        )

