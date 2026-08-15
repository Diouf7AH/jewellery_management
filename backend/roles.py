# backend/roles.py

from __future__ import annotations

from typing import Optional

# ============================================================
# Constantes des rôles
# ============================================================

ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_VENDOR = "vendor"
ROLE_CASHIER = "cashier"
ROLE_BUYER = "buyer"


ALL_ROLES = frozenset({
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_VENDOR,
    ROLE_CASHIER,
    ROLE_BUYER,
})

SYSTEM_ROLES = ALL_ROLES

ALLOWED_ROLES_ADMIN_MANAGER = frozenset({
    ROLE_ADMIN,
    ROLE_MANAGER,
})


STAFF_ROLE_PROFILES = (
    (
        ROLE_MANAGER,
        "staff_manager_profile",
    ),
    (
        ROLE_CASHIER,
        "staff_cashier_profile",
    ),
    (
        ROLE_VENDOR,
        "staff_vendor_profile",
    ),
    (
        ROLE_BUYER,
        "staff_buyer_profile",
    ),
)


# ============================================================
# Helpers internes
# ============================================================

def _normalize(value: Optional[str]) -> Optional[str]:
    """
    Normalise une valeur de rôle.

    Exemple :
        " Manager " -> "manager"
    """

    if value is None:
        return None

    normalized = str(value).strip().lower()

    return normalized or None


def _is_verified_profile(profile) -> bool:
    """
    Un profil staff est considéré actif uniquement si :

    - le profil existe ;
    - verifie=True.
    """

    return bool(
        profile
        and getattr(profile, "verifie", False)
    )


def get_verified_staff_roles(user) -> list[str]:
    """
    Retourne les rôles staff vérifiés de l'utilisateur.

    En fonctionnement normal, cette liste doit contenir
    au maximum un rôle.
    """

    if not user:
        return []

    verified_roles: list[str] = []

    for role_name, profile_attribute in STAFF_ROLE_PROFILES:
        profile = getattr(
            user,
            profile_attribute,
            None,
        )

        if _is_verified_profile(profile):
            verified_roles.append(role_name)

    return verified_roles


# ============================================================
# Résolution du rôle
# ============================================================

def get_role_name(user) -> Optional[str]:
    """
    Retourne le rôle effectif de l'utilisateur.

    Priorité :

    1. Superuser Django actif -> admin
    2. Manager vérifié
    3. Cashier vérifié
    4. Vendor vérifié
    5. Buyer vérifié
    6. user_role == admin
    7. Aucun rôle

    Important :

    - un utilisateur désactivé ne possède aucun rôle actif ;
    - un profil staff désactivé ne donne aucun accès ;
    - un utilisateur doit normalement avoir un seul profil
      staff actif ;
    - les rôles staff sont prioritaires sur user_role ;
    - user_role est utilisé uniquement pour l'administrateur.
    """

    if not user:
        return None

    if not getattr(user, "is_authenticated", False):
        return None

    # Un compte désactivé ne doit plus avoir de rôle effectif.
    if not getattr(user, "is_active", False):
        return None

    # --------------------------------------------------------
    # Superuser Django
    # --------------------------------------------------------

    if getattr(user, "is_superuser", False):
        return ROLE_ADMIN

    # --------------------------------------------------------
    # Profils staff vérifiés
    # --------------------------------------------------------

    verified_staff_roles = get_verified_staff_roles(user)

    if verified_staff_roles:
        # En cas d'incohérence historique, l'ordre défini dans
        # STAFF_ROLE_PROFILES détermine le rôle retenu.
        return verified_staff_roles[0]

    # --------------------------------------------------------
    # Administrateur applicatif
    # --------------------------------------------------------

    user_role = getattr(
        user,
        "user_role",
        None,
    )

    role_name = _normalize(
        getattr(
            user_role,
            "role",
            None,
        )
    )

    if role_name == ROLE_ADMIN:
        return ROLE_ADMIN

    return None


# ============================================================
# Vérification de rôle
# ============================================================

def has_role(user, *roles: str) -> bool:
    """
    Vérifie si l'utilisateur possède l'un des rôles demandés.

    Exemple :

        has_role(
            request.user,
            ROLE_ADMIN,
            ROLE_MANAGER,
        )
    """

    if not roles:
        return False

    normalized_roles = {
        normalized_role
        for role in roles
        if (
            normalized_role := _normalize(role)
        ) in ALL_ROLES
    }

    if not normalized_roles:
        return False

    return get_role_name(user) in normalized_roles



    