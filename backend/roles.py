# backend/roles.py

from __future__ import annotations

from typing import Optional

ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_VENDOR = "vendor"
ROLE_CASHIER = "cashier"
ROLE_BUYER = "buyer"

ALL_ROLES = {
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_VENDOR,
    ROLE_CASHIER,
    ROLE_BUYER,
}


def _normalize(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value.strip().lower()


def _is_verified_profile(profile) -> bool:
    """
    Un profil staff est valide uniquement s'il existe
    et qu'il est vérifié (verifie=True).
    """
    return bool(profile and getattr(profile, "verifie", False))


def get_role_name(user) -> Optional[str]:
    """
    Retourne le rôle effectif de l'utilisateur.

    Priorité :
    1. Superuser -> admin
    2. Manager vérifié
    3. Cashier vérifié
    4. Vendor vérifié
    5. Buyer vérifié
    6. user_role == admin
    7. Aucun rôle
    """

    if not user or not user.is_authenticated:
        return None

    # Django superuser
    if user.is_superuser:
        return ROLE_ADMIN

    # Manager
    manager = getattr(user, "staff_manager_profile", None)
    if _is_verified_profile(manager):
        return ROLE_MANAGER

    # Cashier
    cashier = getattr(user, "staff_cashier_profile", None)
    if _is_verified_profile(cashier):
        return ROLE_CASHIER

    # Vendor
    vendor = getattr(user, "staff_vendor_profile", None)
    if _is_verified_profile(vendor):
        return ROLE_VENDOR
    
    buyer = getattr(user, "staff_buyer_profile", None)
    if _is_verified_profile(buyer):
        return ROLE_BUYER

    # Admin via Role
    role = getattr(user, "user_role", None)
    if role:
        role_name = _normalize(getattr(role, "role", None))
        if role_name == ROLE_ADMIN:
            return ROLE_ADMIN

    return None


def has_role(user, *roles: str) -> bool:
    """
    Vérifie si l'utilisateur possède l'un des rôles demandés.
    """
    return get_role_name(user) in roles