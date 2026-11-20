# administration/services/admin_service.py

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from administration.models import AdminProfile
from backend.roles import ROLE_ADMIN, get_role_name

# ============================================================
# HELPERS
# ============================================================

def get_admin_profile(user):
    """
    Retourne le profil administrateur vérifié.
    """

    if not user or not user.is_authenticated:
        return None

    if not user.is_active:
        return None

    if get_role_name(user) != ROLE_ADMIN:
        return None

    return AdminProfile.objects.filter(
        user=user,
        verifie=True,
    ).first()


def ensure_admin_principal(user):
    """
    Vérifie que l'utilisateur est un administrateur principal.
    """

    profile = get_admin_profile(user)

    if (
        profile is None
        or profile.niveau != AdminProfile.Niveau.PRINCIPAL
    ):
        raise PermissionError(
            "Seul l'administrateur principal "
            "peut effectuer cette opération."
        )

    return profile


def ensure_no_staff_profile(user):
    """
    Empêche de transformer en administrateur un utilisateur
    possédant déjà un profil de personnel.
    """

    profile_names = [
        "staff_manager_profile",
        "staff_vendor_profile",
        "staff_cashier_profile",
        "staff_buyer_profile",
    ]

    for name in profile_names:
        if getattr(user, name, None) is not None:
            raise ValueError(
                "Cet utilisateur possède déjà un profil staff."
            )


# ============================================================
# CRÉER UN ADMINISTRATEUR SECONDAIRE
# ============================================================

@transaction.atomic
def promote_user_to_admin(*, caller_user, email):
    """
    Transforme un utilisateur existant en administrateur secondaire.

    Conditions :
    - appelant = administrateur principal ;
    - utilisateur cible existant ;
    - compte actif ;
    - email vérifié ;
    - aucun profil staff ou admin existant.

    Aucun privilège superuser Django n'est attribué.
    """

    ensure_admin_principal(caller_user)

    User = get_user_model()

    email = (email or "").strip().lower()

    if not email:
        raise ValueError(
            "L'adresse email est obligatoire."
        )

    try:
        user = (
            User.objects
            .select_for_update()
            .get(email__iexact=email)
        )
    except User.DoesNotExist:
        raise ValueError(
            "Utilisateur introuvable."
        )
    except User.MultipleObjectsReturned:
        raise ValueError(
            "Plusieurs utilisateurs possèdent cet email."
        )

    if not user.is_active:
        raise ValueError(
            "Le compte utilisateur est désactivé."
        )

    if not user.is_email_verified:
        raise ValueError(
            "L'adresse email doit être confirmée."
        )

    if AdminProfile.objects.filter(user=user).exists():
        raise ValueError(
            "Cet utilisateur possède déjà un profil administrateur."
        )

    ensure_no_staff_profile(user)

    if user.is_superuser:
        raise ValueError(
            "Ce compte possède déjà des privilèges "
            "de superutilisateur Django."
        )

    # À adapter si le champ de rôle de ton modèle User
    # porte un autre nom.
    user.user_role = ROLE_ADMIN

    # Aucun accès automatique au Django Admin.
    user.is_staff = False
    user.is_superuser = False

    user.save(
        update_fields=[
            "user_role",
            "is_staff",
            "is_superuser",
        ]
    )

    AdminProfile.objects.create(
        user=user,
        niveau=AdminProfile.Niveau.SECONDAIRE,
        verifie=True,
        peut_gerer_bijouteries=False,
        peut_voir_finances=False,
        created_by=caller_user,
    )

    return user


# ============================================================
# MODIFIER LES PERMISSIONS D'UN ADMIN SECONDAIRE
# ============================================================

@transaction.atomic
def update_admin_permissions(
    *,
    caller_user,
    admin_id,
    peut_gerer_bijouteries=None,
    peut_voir_finances=None,
):
    """
    Modifie les permissions d'un administrateur secondaire.
    """

    ensure_admin_principal(caller_user)

    try:
        profile = (
            AdminProfile.objects
            .select_for_update()
            .get(pk=admin_id)
        )
    except AdminProfile.DoesNotExist:
        raise ValueError(
            "Administrateur introuvable."
        )

    if profile.niveau != AdminProfile.Niveau.SECONDAIRE:
        raise PermissionError(
            "Impossible de modifier les permissions "
            "de l'administrateur principal."
        )

    if peut_gerer_bijouteries is not None:
        profile.peut_gerer_bijouteries = (
            peut_gerer_bijouteries
        )

    if peut_voir_finances is not None:
        profile.peut_voir_finances = (
            peut_voir_finances
        )

    profile.full_clean()
    profile.save()

    return profile


# ============================================================
# DÉSACTIVER UN ADMINISTRATEUR SECONDAIRE
# ============================================================

@transaction.atomic
def deactivate_admin(
    *,
    caller_user,
    admin_id,
    raison,
):
    """
    Désactive uniquement le profil administrateur.
    Le compte utilisateur reste actif.
    """

    ensure_admin_principal(caller_user)

    raison = (raison or "").strip()

    if not raison:
        raise ValueError(
            "La raison de désactivation est obligatoire."
        )

    try:
        profile = (
            AdminProfile.objects
            .select_for_update()
            .get(pk=admin_id)
        )
    except AdminProfile.DoesNotExist:
        raise ValueError(
            "Administrateur introuvable."
        )

    if profile.niveau == AdminProfile.Niveau.PRINCIPAL:
        raise PermissionError(
            "L'administrateur principal "
            "ne peut pas être désactivé."
        )

    if profile.user_id == caller_user.id:
        raise PermissionError(
            "Vous ne pouvez pas désactiver "
            "votre propre profil."
        )

    profile.verifie = False
    profile.raison_desactivation = raison
    profile.date_desactivation = timezone.now()
    profile.desactive_par = caller_user

    profile.save(
        update_fields=[
            "verifie",
            "raison_desactivation",
            "date_desactivation",
            "desactive_par",
            "updated_at",
        ]
    )

    return profile


# ============================================================
# RÉACTIVER UN ADMINISTRATEUR SECONDAIRE
# ============================================================

@transaction.atomic
def reactivate_admin(*, caller_user, admin_id):
    """
    Réactive un administrateur secondaire.
    """

    ensure_admin_principal(caller_user)

    try:
        profile = (
            AdminProfile.objects
            .select_for_update()
            .get(pk=admin_id)
        )
    except AdminProfile.DoesNotExist:
        raise ValueError(
            "Administrateur introuvable."
        )

    if profile.niveau != AdminProfile.Niveau.SECONDAIRE:
        raise PermissionError(
            "Cette opération concerne uniquement "
            "les administrateurs secondaires."
        )

    if not profile.user.is_active:
        raise ValueError(
            "Le compte utilisateur est désactivé."
        )

    profile.verifie = True
    profile.raison_desactivation = None
    profile.date_desactivation = None
    profile.desactive_par = None

    profile.save(
        update_fields=[
            "verifie",
            "raison_desactivation",
            "date_desactivation",
            "desactive_par",
            "updated_at",
        ]
    )

    return profile

