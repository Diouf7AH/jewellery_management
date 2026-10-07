# backend/bijouteries.py

from __future__ import annotations

from django.db.models import QuerySet

from backend.roles import (ROLE_ADMIN, ROLE_BUYER, ROLE_CASHIER, ROLE_MANAGER,
                           ROLE_VENDOR, get_role_name)
from store.models import Bijouterie

# ============================================================
# Helpers internes
# ============================================================

def _empty_bijouteries() -> QuerySet:
    """
    Retourne un queryset vide de Bijouterie.
    """

    return Bijouterie.objects.none()


def _verified_profile(profile) -> bool:
    """
    Retourne True uniquement si le profil existe
    et possède verifie=True.
    """

    return bool(
        profile
        and getattr(
            profile,
            "verifie",
            False,
        )
    )


def _get_single_profile_bijouterie_queryset(
    profile,
) -> QuerySet:
    """
    Retourne la bijouterie d'un profil staff
    possédant une seule bijouterie.

    Utilisé pour :
    - vendor ;
    - cashier ;
    - buyer.
    """

    if not _verified_profile(profile):
        return _empty_bijouteries()

    bijouterie_id = getattr(
        profile,
        "bijouterie_id",
        None,
    )

    if not bijouterie_id:
        return _empty_bijouteries()

    return Bijouterie.objects.filter(
        pk=bijouterie_id,
    )


# ============================================================
# Périmètre principal
# ============================================================

def get_user_bijouteries(user) -> QuerySet:
    """
    Retourne toutes les bijouteries accessibles
    par l'utilisateur.

    Cette fonction constitue la SOURCE UNIQUE
    du périmètre de bijouterie.

    Règles :

    ADMIN
        Toutes les bijouteries.

    MANAGER
        Toutes les bijouteries rattachées
        à son profil manager vérifié.

    VENDOR
        Sa bijouterie uniquement.

    CASHIER
        Sa bijouterie uniquement.

    BUYER
        Sa bijouterie uniquement.

    Aucun rôle valide
        Queryset vide.
    """

    role = get_role_name(user)

    if role is None:
        return _empty_bijouteries()

    # --------------------------------------------------------
    # Admin
    # --------------------------------------------------------

    if role == ROLE_ADMIN:
        return Bijouterie.objects.all().order_by(
            "nom",
            "pk",
        )

    # --------------------------------------------------------
    # Manager
    # --------------------------------------------------------

    if role == ROLE_MANAGER:
        manager = getattr(
            user,
            "staff_manager_profile",
            None,
        )

        if not _verified_profile(manager):
            return _empty_bijouteries()

        return manager.bijouteries.all().order_by(
            "nom",
            "pk",
        )

    # --------------------------------------------------------
    # Vendor
    # --------------------------------------------------------

    if role == ROLE_VENDOR:
        return _get_single_profile_bijouterie_queryset(
            getattr(
                user,
                "staff_vendor_profile",
                None,
            )
        )

    # --------------------------------------------------------
    # Cashier
    # --------------------------------------------------------

    if role == ROLE_CASHIER:
        return _get_single_profile_bijouterie_queryset(
            getattr(
                user,
                "staff_cashier_profile",
                None,
            )
        )

    # --------------------------------------------------------
    # Buyer
    # --------------------------------------------------------

    if role == ROLE_BUYER:
        return _get_single_profile_bijouterie_queryset(
            getattr(
                user,
                "staff_buyer_profile",
                None,
            )
        )

    return _empty_bijouteries()


# ============================================================
# Vérification d'accès
# ============================================================

def user_has_bijouterie_access(
    user,
    bijouterie_or_id,
) -> bool:
    """
    Vérifie si l'utilisateur peut accéder
    à une bijouterie.

    Accepte :
    - un objet Bijouterie ;
    - un identifiant de bijouterie.

    Toute la logique du périmètre passe par
    get_user_bijouteries().
    """

    if bijouterie_or_id is None:
        return False

    raw_id = getattr(
        bijouterie_or_id,
        "pk",
        bijouterie_or_id,
    )

    try:
        bijouterie_id = int(raw_id)
    except (
        TypeError,
        ValueError,
    ):
        return False

    if bijouterie_id <= 0:
        return False

    return (
        get_user_bijouteries(user)
        .filter(pk=bijouterie_id)
        .exists()
    )


# ============================================================
# Récupération sécurisée d'une bijouterie
# ============================================================

def get_accessible_bijouterie(
    user,
    bijouterie_or_id,
):
    """
    Retourne la Bijouterie si elle appartient
    au périmètre de l'utilisateur.

    Retourne None dans les cas suivants :
    - identifiant absent ;
    - identifiant invalide ;
    - bijouterie inexistante ;
    - utilisateur sans accès.
    """

    if bijouterie_or_id is None:
        return None

    raw_id = getattr(
        bijouterie_or_id,
        "pk",
        bijouterie_or_id,
    )

    try:
        bijouterie_id = int(raw_id)
    except (
        TypeError,
        ValueError,
    ):
        return None

    if bijouterie_id <= 0:
        return None

    return (
        get_user_bijouteries(user)
        .filter(pk=bijouterie_id)
        .first()
    )
    