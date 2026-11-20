from __future__ import annotations

from rest_framework.permissions import BasePermission

from administration.models import AdminProfile
from backend.roles import ROLE_ADMIN, get_role_name

# ============================================================
# HELPERS
# ============================================================

def get_admin_profile(user):
    """
    Retourne le profil administrateur actif et vérifié.

    Aucun accès si :
    - utilisateur non authentifié ;
    - compte utilisateur désactivé ;
    - rôle différent de admin ;
    - profil administrateur absent ;
    - profil administrateur désactivé.
    """

    if not user or not user.is_authenticated:
        return None

    if not user.is_active:
        return None

    if get_role_name(user) != ROLE_ADMIN:
        return None

    return (
        AdminProfile.objects
        .filter(
            user=user,
            verifie=True,
        )
        .first()
    )


def is_admin_principal(user):
    profile = get_admin_profile(user)

    return bool(
        profile
        and profile.niveau == AdminProfile.Niveau.PRINCIPAL
    )


def is_admin_secondaire(user):
    profile = get_admin_profile(user)

    return bool(
        profile
        and profile.niveau == AdminProfile.Niveau.SECONDAIRE
    )


# ============================================================
# ADMIN PRINCIPAL UNIQUEMENT
# ============================================================

class IsAdminPrincipal(BasePermission):
    """
    Réservé à l'administrateur principal.

    Exemples :
    - créer un administrateur secondaire ;
    - modifier ses permissions ;
    - désactiver un administrateur secondaire ;
    - transférer le rôle principal.
    """

    message = (
        "Seul l'administrateur principal "
        "peut effectuer cette opération."
    )

    def has_permission(self, request, view):
        return is_admin_principal(request.user)


# ============================================================
# TOUS LES ADMINISTRATEURS ACTIFS
# ============================================================

class IsAdminPrincipalOrSecondaire(BasePermission):
    """
    Accessible aux administrateurs principaux
    et secondaires actifs.
    """

    message = "Accès réservé aux administrateurs actifs."

    def has_permission(self, request, view):
        return get_admin_profile(request.user) is not None


# ============================================================
# GESTION DES BIJOUTERIES
# ============================================================

class CanManageBijouteries(BasePermission):
    """
    Principal : autorisé.
    Secondaire : selon peut_gerer_bijouteries.
    """

    message = (
        "Vous n'êtes pas autorisé "
        "à gérer les bijouteries."
    )

    def has_permission(self, request, view):

        profile = get_admin_profile(request.user)

        if profile is None:
            return False

        if profile.niveau == AdminProfile.Niveau.PRINCIPAL:
            return True

        return bool(profile.peut_gerer_bijouteries)


# ============================================================
# CONSULTATION DES FINANCES
# ============================================================

class CanViewFinances(BasePermission):
    """
    Principal : autorisé.
    Secondaire : selon peut_voir_finances.
    """

    message = (
        "Vous n'êtes pas autorisé "
        "à consulter les rapports financiers."
    )

    def has_permission(self, request, view):

        profile = get_admin_profile(request.user)

        if profile is None:
            return False

        if profile.niveau == AdminProfile.Niveau.PRINCIPAL:
            return True

        return bool(profile.peut_voir_finances)


# ============================================================
# GESTION DU PERSONNEL
# ============================================================

class CanManageStaff(BasePermission):
    """
    Autorise les administrateurs actifs à gérer
    les managers, vendeurs, caissiers et buyers.

    Ne donne aucun droit de gestion
    des autres administrateurs.
    """

    message = (
        "Vous n'êtes pas autorisé "
        "à gérer le personnel."
    )

    def has_permission(self, request, view):
        return get_admin_profile(request.user) is not None
    
    