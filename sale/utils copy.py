# from staff.models import Cashier, Manager
# from vendor.models import Vendor


# def _user_profiles(user):
#     vp = getattr(user, "vendor_profile", None) or getattr(user, "staff_vendor_profile", None)
#     mp = getattr(user, "staff_manager_profile", None)
#     cp = getattr(user, "staff_cashier_profile", None)
#     return vp, mp, cp


# def _ensure_role_and_bijouterie(user):
#     vp, mp, cp = _user_profiles(user)

#     if vp and vp.verifie and vp.bijouterie_id:
#         return vp.bijouterie, "vendor"

#     if mp and mp.verifie and mp.bijouterie_id:
#         return mp.bijouterie, "manager"

#     if cp and cp.verifie and cp.bijouterie_id:
#         return cp.bijouterie, "cashier"

#     return None, None

# def _user_bijouterie(user):
#     v = Vendor.objects.select_related("bijouterie").filter(user=user, verifie=True).first()
#     if v and v.bijouterie_id:
#         return v.bijouterie

#     m = Manager.objects.select_related("bijouterie").filter(user=user, verifie=True).first()
#     if m and m.bijouterie_id:
#         return m.bijouterie

#     c = Cashier.objects.select_related("bijouterie").filter(user=user, verifie=True).first()
#     if c and c.bijouterie_id:
#         return c.bijouterie

#     return None


from __future__ import annotations

from typing import Optional

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

    vp = getattr(user, "vendor_profile", None)  # ← ton vendor
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

    vp = getattr(user, "vendor_profile", None)
    if vp and getattr(vp, "verifie", False) and getattr(vp, "bijouterie_id", None):
        return vp.bijouterie

    mp = getattr(user, "staff_manager_profile", None)
    if mp and getattr(mp, "verifie", False) and getattr(mp, "bijouterie_id", None):
        return mp.bijouterie

    cp = getattr(user, "staff_cashier_profile", None)
    if cp and getattr(cp, "verifie", False) and getattr(cp, "bijouterie_id", None):
        return cp.bijouterie

    return None
