# backend/roles.py
from __future__ import annotations

from typing import Optional

ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_VENDOR = "vendor"
ROLE_CASHIER = "cashier"

ALL_ROLES = {ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER}


def _normalize(v: Optional[str]) -> Optional[str]:
    return v.strip().lower() if v else None


def get_role_name(user) -> Optional[str]:
    if not user or not user.is_authenticated:
        return None

    if getattr(user, "is_superuser", False):
        return ROLE_ADMIN

    mp = getattr(user, "staff_manager_profile", None)
    if mp and getattr(mp, "verifie", True):
        return ROLE_MANAGER

    cp = getattr(user, "staff_cashier_profile", None)
    if cp and getattr(cp, "verifie", True):
        return ROLE_CASHIER

    vp = getattr(user, "staff_vendor_profile", None)
    if vp and getattr(vp, "verifie", True):
        return ROLE_VENDOR

    role_fk = getattr(user, "user_role", None)
    r = _normalize(getattr(role_fk, "role", None) if role_fk else None)
    if r in ALL_ROLES:
        return r

    try:
        groups = {_normalize(g) for g in user.groups.values_list("name", flat=True)}
        for candidate in ALL_ROLES:
            if candidate in groups:
                return candidate
    except Exception:
        pass

    return None


def has_role(user, *roles: str) -> bool:
    return get_role_name(user) in roles



