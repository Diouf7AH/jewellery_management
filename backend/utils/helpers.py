# backend/utils/helpers.py
from __future__ import annotations

from decimal import Decimal

ZERO = Decimal("0.00")


def dec(v) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def resolve_bijouterie_for_user(user):
    """
    Retourne UNE bijouterie par défaut pour vendor/cashier/manager.
    Pour manager, retourne la première bijouterie autorisée.
    """
    from backend.roles import (ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR,
                               get_role_name)

    role = (get_role_name(user) or "").lower().strip()

    if role == ROLE_VENDOR:
        profile = getattr(user, "staff_vendor_profile", None)
        if profile and getattr(profile, "verifie", False) and profile.bijouterie_id:
            return profile.bijouterie

    if role == ROLE_CASHIER:
        profile = getattr(user, "staff_cashier_profile", None)
        if profile and getattr(profile, "verifie", False) and profile.bijouterie_id:
            return profile.bijouterie

    if role == ROLE_MANAGER:
        profile = getattr(user, "staff_manager_profile", None)
        if profile and getattr(profile, "verifie", False):
            return profile.bijouteries.first()

    return None


def user_bijouterie(user):
    return resolve_bijouterie_for_user(user)


def ensure_role_and_bijouterie(user):
    from backend.roles import get_role_name

    role = (get_role_name(user) or "").lower().strip()
    bijouterie = resolve_bijouterie_for_user(user)
    return bijouterie, role


def user_can_access_bijouterie(user, bijouterie) -> bool:
    from backend.roles import (ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER,
                               ROLE_VENDOR, get_role_name)

    role = (get_role_name(user) or "").lower().strip()

    if role == ROLE_ADMIN:
        return True

    if not bijouterie:
        return False

    if role == ROLE_VENDOR:
        profile = getattr(user, "staff_vendor_profile", None)
        return bool(
            profile
            and getattr(profile, "verifie", False)
            and profile.bijouterie_id == bijouterie.id
        )

    if role == ROLE_CASHIER:
        profile = getattr(user, "staff_cashier_profile", None)
        return bool(
            profile
            and getattr(profile, "verifie", False)
            and profile.bijouterie_id == bijouterie.id
        )

    if role == ROLE_MANAGER:
        profile = getattr(user, "staff_manager_profile", None)
        return bool(
            profile
            and getattr(profile, "verifie", False)
            and profile.bijouteries.filter(id=bijouterie.id).exists()
        )

    return False


