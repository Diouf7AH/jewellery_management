from __future__ import annotations

from datetime import date
from typing import Optional

from dateutil.relativedelta import relativedelta

# ---------- List factures -------------------

def subtract_months(d: date, months: int) -> date:
    return (d - relativedelta(months=months))


ROLE_ADMIN   = "admin"
ROLE_MANAGER = "manager"
ROLE_VENDOR  = "vendor"
ROLE_CASHIER = "cashier"


def _normalize_role(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    return str(v).strip().lower()


def _user_role(user) -> Optional[str]:
    """
    Détermine le rôle métier.
    Priorité:
      1) user.user_role.role
      2) profils (manager/cashier/vendor) si verifie=True
      3) fallback: superuser => admin
    """
    if not user or not getattr(user, "is_authenticated", False):
        return None

    # 1) FK Role
    ur = getattr(user, "user_role", None)
    r = _normalize_role(getattr(ur, "role", None)) if ur else None
    if r in {ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER}:
        return r

    # 2) profils staff (si role FK pas set)
    mp = getattr(user, "staff_manager_profile", None)
    if mp and getattr(mp, "verifie", False):
        return ROLE_MANAGER

    cp = getattr(user, "staff_cashier_profile", None)
    if cp and getattr(cp, "verifie", False):
        return ROLE_CASHIER

    vp = getattr(user, "staff_vendor_profile", None)  # ← ton vendor
    if vp and getattr(vp, "verifie", False):
        return ROLE_VENDOR

    # 3) fallback
    if getattr(user, "is_superuser", False):
        return ROLE_ADMIN

    return None


def _user_bijouterie_facture(user):
    """
    Retourne la bijouterie du profil (vendor/manager/cashier) si verifie=True.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return None

    vp = getattr(user, "staff_vendor_profile", None)
    if vp and getattr(vp, "verifie", False) and getattr(vp, "bijouterie_id", None):
        return vp.bijouterie

    mp = getattr(user, "staff_manager_profile", None)
    if mp and getattr(mp, "verifie", False) and getattr(mp, "bijouterie_id", None):
        return mp.bijouterie

    cp = getattr(user, "staff_cashier_profile", None)
    if cp and getattr(cp, "verifie", False) and getattr(cp, "bijouterie_id", None):
        return cp.bijouterie

    return None

# ---------- End List factures -------------------


# -------------Create facture------------------------------
def _ensure_role_and_bijouterie(user):
    # Vendor
    vp = getattr(user, "staff_vendor_profile", None)
    if vp and getattr(vp, "verifie", False) and vp.bijouterie_id:
        return vp.bijouterie, "vendor"

    # Manager
    mp = getattr(user, "staff_manager_profile", None)
    if mp and getattr(mp, "verifie", False) and mp.bijouterie_id:
        return mp.bijouterie, "manager"

    # Cashier (si tu veux l'autoriser)
    cp = getattr(user, "staff_cashier_profile", None)
    if cp and getattr(cp, "verifie", False) and cp.bijouterie_id:
        return cp.bijouterie, "cashier"

    return None, None
# ------------- End Create facture------------------------------



