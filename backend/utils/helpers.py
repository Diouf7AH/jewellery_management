# backend/utils/helpers.py

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

from backend.roles import (ROLE_ADMIN, ROLE_BUYER, ROLE_CASHIER, ROLE_MANAGER,
                           ROLE_VENDOR, get_role_name)

ZERO = Decimal("0.00")


def dec(value) -> Decimal | None:
    """
    Convertit une valeur en Decimal.

    Retourne None si la valeur :
    - est absente ;
    - est vide ;
    - n'est pas convertible.
    """

    if value in {
        None,
        "",
    }:
        return None

    try:
        return Decimal(str(value))
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return None


def _normalize_bijouterie_id(
    bijouterie_or_id,
) -> Optional[int]:
    """
    Normalise un objet Bijouterie ou un identifiant.

    Valeurs acceptées :
    - objet avec attribut pk ;
    - entier ;
    - chaîne numérique.

    Retourne :
    - un entier positif ;
    - None si la valeur est invalide.
    """

    if bijouterie_or_id in {
        None,
        "",
        "null",
    }:
        return None

    raw_id = getattr(
        bijouterie_or_id,
        "pk",
        bijouterie_or_id,
    )

    try:
        normalized_id = int(raw_id)
    except (
        TypeError,
        ValueError,
    ):
        return None

    if normalized_id <= 0:
        return None

    return normalized_id


def resolve_bijouterie_for_user(
    user,
    *,
    bijouterie_id=None,
):
    """
    Retourne une bijouterie accessible à l'utilisateur.

    Vendor :
        retourne automatiquement sa bijouterie.

    Cashier :
        retourne automatiquement sa bijouterie.

    Buyer :
        retourne automatiquement sa bijouterie.

    Manager :
        exige bijouterie_id ;
        vérifie que cette bijouterie fait partie de son M2M.

    Admin :
        exige bijouterie_id ;
        retourne la bijouterie demandée.

    Aucun choix automatique de la première bijouterie
    n'est fait pour le manager.
    """

    from store.models import Bijouterie

    role = get_role_name(user)

    if role == ROLE_VENDOR:
        profile = getattr(
            user,
            "staff_vendor_profile",
            None,
        )

        if (
            profile
            and getattr(profile, "verifie", False)
            and profile.bijouterie_id
        ):
            return profile.bijouterie

        return None

    if role == ROLE_CASHIER:
        profile = getattr(
            user,
            "staff_cashier_profile",
            None,
        )

        if (
            profile
            and getattr(profile, "verifie", False)
            and profile.bijouterie_id
        ):
            return profile.bijouterie

        return None

    if role == ROLE_BUYER:
        profile = getattr(
            user,
            "staff_buyer_profile",
            None,
        )

        if (
            profile
            and getattr(profile, "verifie", False)
            and profile.bijouterie_id
        ):
            return profile.bijouterie

        return None

    requested_id = _normalize_bijouterie_id(
        bijouterie_id
    )

    if requested_id is None:
        return None

    if role == ROLE_MANAGER:
        profile = getattr(
            user,
            "staff_manager_profile",
            None,
        )

        if not (
            profile
            and getattr(profile, "verifie", False)
        ):
            return None

        return (
            profile.bijouteries
            .filter(pk=requested_id)
            .first()
        )

    if role == ROLE_ADMIN:
        return (
            Bijouterie.objects
            .filter(pk=requested_id)
            .first()
        )

    return None


def user_bijouterie(
    user,
    *,
    bijouterie_id=None,
):
    """
    Alias de resolve_bijouterie_for_user().
    """

    return resolve_bijouterie_for_user(
        user,
        bijouterie_id=bijouterie_id,
    )


def ensure_role_and_bijouterie(
    user,
    *,
    bijouterie_id=None,
):
    """
    Retourne le couple :

        (
            bijouterie,
            role,
        )
    """

    role = get_role_name(user)

    bijouterie = resolve_bijouterie_for_user(
        user,
        bijouterie_id=bijouterie_id,
    )

    return bijouterie, role


def user_can_access_bijouterie(
    user,
    bijouterie_or_id,
) -> bool:
    """
    Vérifie que l'utilisateur peut accéder à la bijouterie.

    Accepte :
    - un objet Bijouterie ;
    - un identifiant de bijouterie.
    """

    role = get_role_name(user)

    if role == ROLE_ADMIN:
        return True

    bijouterie_id = _normalize_bijouterie_id(
        bijouterie_or_id
    )

    if bijouterie_id is None:
        return False

    if role == ROLE_VENDOR:
        profile = getattr(
            user,
            "staff_vendor_profile",
            None,
        )

        return bool(
            profile
            and getattr(profile, "verifie", False)
            and profile.bijouterie_id
            == bijouterie_id
        )

    if role == ROLE_CASHIER:
        profile = getattr(
            user,
            "staff_cashier_profile",
            None,
        )

        return bool(
            profile
            and getattr(profile, "verifie", False)
            and profile.bijouterie_id
            == bijouterie_id
        )

    if role == ROLE_BUYER:
        profile = getattr(
            user,
            "staff_buyer_profile",
            None,
        )

        return bool(
            profile
            and getattr(profile, "verifie", False)
            and profile.bijouterie_id
            == bijouterie_id
        )

    if role == ROLE_MANAGER:
        profile = getattr(
            user,
            "staff_manager_profile",
            None,
        )

        return bool(
            profile
            and getattr(profile, "verifie", False)
            and profile.bijouteries.filter(
                pk=bijouterie_id
            ).exists()
        )

    return False
