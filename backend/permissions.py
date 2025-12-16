# from rest_framework.permissions import BasePermission


# class IsAdminOrManager(BasePermission):
#     """
#     Autorise si:
#       - user.is_superuser (admin Django)
#       - OU l'utilisateur appartient au groupe 'admin' OU 'manager'
#     """
#     def has_permission(self, request, view):
#         u = request.user
#         if not (u and u.is_authenticated):
#             return False
#         return u.is_superuser or u.groups.filter(name__in=["admin", "manager"]).exists()
    


# class IsAdminOrManagerOrSelfVendor(BasePermission):
#     def has_permission(self, request, view):
#         u = request.user
#         if not (u and u.is_authenticated):
#             return False
#         # admin/manager (via groupes ou superuser)
#         if u.is_superuser or u.groups.filter(name__in=["admin","manager"]).exists():
#             return True
#         # vendor: accès autorisé, ciblage restreint à lui-même (vérif fait dans la vue)
#         return hasattr(u, "staff_vendor_profile")


from __future__ import annotations

from typing import Optional

from rest_framework.permissions import BasePermission

# --- Rôles "business" attendus ---
ROLE_ADMIN   = "admin"
ROLE_MANAGER = "manager"
ROLE_VENDOR  = "vendor"
ROLE_CASHIER = "cashier"


def _normalize_role(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return value.strip().lower()


def get_role_name(user) -> Optional[str]:
    if not user or not user.is_authenticated:
        return None

    # 0) superuser
    if getattr(user, "is_superuser", False):
        return ROLE_ADMIN

    # 1) profils staff (prioritaires)
    mp = getattr(user, "staff_manager_profile", None)
    if mp and getattr(mp, "verifie", True):
        return ROLE_MANAGER

    cp = getattr(user, "staff_cashier_profile", None)
    if cp and getattr(cp, "verifie", True):
        return ROLE_CASHIER

    vp = getattr(user, "vendor_profile", None) or getattr(user, "staff_vendor_profile", None)
    if vp and getattr(vp, "verifie", True):
        return ROLE_VENDOR

    # 2) user_role (FK)
    ur = getattr(user, "user_role", None)
    if ur:
        r = _normalize_role(getattr(ur, "role", None))
        if r in {ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER}:
            return r

    # 3) groupes Django (fallback)
    try:
        group_names = {_normalize_role(n) for n in user.groups.values_list("name", flat=True)}
        for candidate in (ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER):
            if candidate in group_names:
                return candidate
    except Exception:
        pass

    return None


# === Permissions simples ===

class IsAdmin(BasePermission):
    """Accès réservé au rôle admin."""
    message = "Accès réservé au rôle admin."

    def has_permission(self, request, view) -> bool:
        u = getattr(request, "user", None)
        return bool(u and u.is_authenticated and get_role_name(u) == ROLE_ADMIN)


class IsManager(BasePermission):
    """Accès réservé au rôle manager."""
    message = "Accès réservé au rôle manager."

    def has_permission(self, request, view) -> bool:
        u = getattr(request, "user", None)
        return bool(u and u.is_authenticated and get_role_name(u) == ROLE_MANAGER)


class IsVendor(BasePermission):
    """Accès réservé au rôle vendor."""
    message = "Accès réservé au rôle vendor."

    def has_permission(self, request, view) -> bool:
        u = getattr(request, "user", None)
        return bool(u and u.is_authenticated and get_role_name(u) == ROLE_VENDOR)


class IsAdminOrManager(BasePermission):
    """Accès réservé aux rôles admin et manager."""
    message = "Accès réservé aux rôles admin et manager."

    def has_permission(self, request, view) -> bool:
        u = getattr(request, "user", None)
        if not (u and u.is_authenticated):
            return False
        return get_role_name(u) in {ROLE_ADMIN, ROLE_MANAGER}


class IsAdminManagerVendor(BasePermission):
    """Accès réservé aux rôles admin, manager, ou vendor."""
    message = "Accès réservé aux rôles admin, manager ou vendor."

    def has_permission(self, request, view) -> bool:
        u = getattr(request, "user", None)
        if not (u and u.is_authenticated):
            return False
        return get_role_name(u) in {ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR}


class IsAdminOrManagerOrSelfVendor(BasePermission):
    """
    Autorise:
      - admin, manager (accès total)
      - vendor (accès restreint à ses propres données; à valider dans la vue
        ou via has_object_permission ci-dessous).
    """
    message = "Accès réservé aux rôles admin, manager, ou vendor (limité à ses propres données)."

    def has_permission(self, request, view) -> bool:
        u = getattr(request, "user", None)
        if not (u and u.is_authenticated):
            return False
        return get_role_name(u) in {ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR}

    # Active ceci si tu veux aussi un contrôle objet-par-objet:
    # def has_object_permission(self, request, view, obj) -> bool:
    #     role = get_role_name(request.user)
    #     if role in {ROLE_ADMIN, ROLE_MANAGER}:
    #         return True
    #     if role == ROLE_VENDOR:
    #         # Adapte le champ "propriétaire" de l'objet:
    #         # - soit obj.user_id
    #         # - soit obj.vendor_id
    #         owner_id = getattr(obj, "user_id", None) or getattr(obj, "vendor_id", None)
    #         return owner_id == request.user.id
    #     return False


class IsAdminManagerVendorCashier(BasePermission):
    def has_permission(self, request, view):
        role = get_role_name(request.user)
        return role in {"admin", "manager", "vendor", "cashier"}
    
    

