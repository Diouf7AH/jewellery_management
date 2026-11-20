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


# Alias utile si d'autres fichiers l'utilisent déjà.
SYSTEM_ROLES = ALL_ROLES


ALLOWED_ROLES_ADMIN_MANAGER = frozenset({
    ROLE_ADMIN,
    ROLE_MANAGER,
})


# Ordre de priorité des profils staff.
#
# Important :
# normalement un utilisateur ne doit avoir qu'un seul
# profil staff vérifié.
#
# Cet ordre sert uniquement de sécurité en présence
# d'anciennes données incohérentes.
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

def _normalize(
    value: Optional[str],
) -> Optional[str]:
    """
    Normalise une valeur de rôle.

    Exemples :
        " Manager " -> "manager"
        ""          -> None
        None        -> None
    """

    if value is None:
        return None

    normalized = str(value).strip().lower()

    return normalized or None


def _is_verified_profile(profile) -> bool:
    """
    Retourne True uniquement si :

    - le profil existe ;
    - le profil possède verifie=True.
    """

    return bool(
        profile
        and getattr(
            profile,
            "verifie",
            False,
        )
    )


def _is_active_authenticated_user(user) -> bool:
    """
    Vérifie que l'utilisateur :

    - existe ;
    - est authentifié ;
    - est actif.
    """

    return bool(
        user
        and getattr(
            user,
            "is_authenticated",
            False,
        )
        and getattr(
            user,
            "is_active",
            False,
        )
    )


# ============================================================
# Profils staff
# ============================================================

def get_verified_staff_roles(
    user,
) -> list[str]:
    """
    Retourne tous les rôles staff vérifiés de l'utilisateur.

    En fonctionnement normal, cette liste doit contenir
    au maximum un rôle.

    Exemple :

        ["manager"]

    Une liste contenant plusieurs rôles indique généralement
    une incohérence dans les données.
    """

    if not _is_active_authenticated_user(user):
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


def has_multiple_verified_staff_roles(
    user,
) -> bool:
    """
    Indique si l'utilisateur possède plusieurs
    profils staff vérifiés.

    Cette situation ne devrait normalement jamais arriver.
    """

    return len(
        get_verified_staff_roles(user)
    ) > 1


# ============================================================
# Résolution du rôle
# ============================================================

def get_role_name(
    user,
) -> Optional[str]:
    """
    Retourne le rôle effectif de l'utilisateur.

    Priorité :

    1. Superuser Django actif
        -> admin

    2. Profil staff vérifié
        -> manager / cashier / vendor / buyer

    3. user_role.role == "admin"
        -> admin

    4. Sinon
        -> None


    Règles importantes
    -------------------

    - un utilisateur non authentifié n'a aucun rôle ;

    - un utilisateur désactivé (is_active=False)
      n'a aucun rôle actif ;

    - un profil staff n'est actif que si verifie=True ;

    - les rôles staff sont déterminés par les profils ;

    - user_role est utilisé uniquement pour
      l'administrateur applicatif ;

    - un utilisateur devrait normalement avoir
      au maximum un profil staff vérifié.


    Compatibilité historique
    -------------------------

    Si plusieurs profils staff sont vérifiés par erreur,
    le premier rôle défini dans STAFF_ROLE_PROFILES
    est retenu.

    L'ordre actuel est :

        manager
        cashier
        vendor
        buyer
    """

    if not _is_active_authenticated_user(user):
        return None

    # --------------------------------------------------------
    # Superuser Django
    # --------------------------------------------------------

    if getattr(
        user,
        "is_superuser",
        False,
    ):
        return ROLE_ADMIN

    # --------------------------------------------------------
    # Profils staff
    # --------------------------------------------------------

    verified_staff_roles = get_verified_staff_roles(
        user
    )

    if verified_staff_roles:
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
# Vérifications de rôles
# ============================================================

def has_role(
    user,
    *roles: str,
) -> bool:
    """
    Vérifie si l'utilisateur possède au moins
    l'un des rôles demandés.

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


def is_admin(user) -> bool:
    """
    Vérifie si l'utilisateur est administrateur.
    """

    return has_role(
        user,
        ROLE_ADMIN,
    )


def is_manager(user) -> bool:
    """
    Vérifie si l'utilisateur est manager.
    """

    return has_role(
        user,
        ROLE_MANAGER,
    )


def is_vendor(user) -> bool:
    """
    Vérifie si l'utilisateur est vendeur.
    """

    return has_role(
        user,
        ROLE_VENDOR,
    )


def is_cashier(user) -> bool:
    """
    Vérifie si l'utilisateur est caissier.
    """

    return has_role(
        user,
        ROLE_CASHIER,
    )


def is_buyer(user) -> bool:
    """
    Vérifie si l'utilisateur est responsable rachat.
    """

    return has_role(
        user,
        ROLE_BUYER,
    )


def is_admin_or_manager(user) -> bool:
    """
    Vérifie si l'utilisateur est admin ou manager.
    """

    return has_role(
        user,
        ROLE_ADMIN,
        ROLE_MANAGER,
    )
    

