from __future__ import annotations

from typing import Optional

from django.db.models import Q

from backend.permissions import ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR


def get_manager_bijouterie_id(user) -> Optional[int]:
    mp = getattr(user, "staff_manager_profile", None)
    if not mp or (hasattr(mp, "verifie") and not mp.verifie):
        return None
    return getattr(mp, "bijouterie_id", None)


def get_vendor_bijouterie_id(user) -> Optional[int]:
    vp = getattr(user, "staff_vendor_profile", None)
    if not vp or (hasattr(vp, "verifie") and not vp.verifie):
        return None
    return getattr(vp, "bijouterie_id", None)


def get_cashier_bijouterie_id(user) -> Optional[int]:
    cp = getattr(user, "staff_cashier_profile", None)
    if not cp or (hasattr(cp, "verifie") and not cp.verifie):
        return None
    return getattr(cp, "bijouterie_id", None)


def vendor_stock_filter(user) -> Q:
    """
    Restreint le stock à la bijouterie du vendor.
    Sécurité: si pas de bijouterie trouvée => aucun résultat.
    """
    bj_id = get_vendor_bijouterie_id(user)
    if bj_id:
        return Q(bijouterie_id=bj_id)
    return Q(pk__in=[])


def get_user_bijouterie_id(user, *, role: Optional[str]) -> Optional[int]:
    """
    Retourne bijouterie_id en fonction du role déjà calculé.
    ⚠️ On passe 'role' en paramètre pour éviter la dépendance à get_role_name().
    """
    if role == ROLE_MANAGER:
        return get_manager_bijouterie_id(user)
    if role == ROLE_VENDOR:
        return get_vendor_bijouterie_id(user)
    if role == ROLE_CASHIER:
        return get_cashier_bijouterie_id(user)
    return None