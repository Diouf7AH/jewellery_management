from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.utils import timezone

ZERO = Decimal("0.00")


def dec(v) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def get_role_name(user) -> str:
    ur = getattr(user, "user_role", None)
    if ur and getattr(ur, "role", None):
        return ur.role
    return getattr(user, "role", None) or ""


def user_bijouterie(user):
    """
    Bijouterie pour vendor / manager / cashier (si verifié).
    """
    vp = getattr(user, "staff_vendor_profile", None)
    if vp and getattr(vp, "verifie", False) and vp.bijouterie_id:
        return vp.bijouterie

    mp = getattr(user, "staff_manager_profile", None)
    if mp and getattr(mp, "verifie", False) and mp.bijouterie_id:
        return mp.bijouterie

    cp = getattr(user, "staff_cashier_profile", None)
    if cp and getattr(cp, "verifie", False) and cp.bijouterie_id:
        return cp.bijouterie

    return None


def ensure_role_and_bijouterie(user):
    role = get_role_name(user)
    bij = user_bijouterie(user)
    return bij, role
