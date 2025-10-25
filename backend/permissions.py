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


def _normalize_role(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return value.strip().lower()


def get_role_name(user) -> Optional[str]:
    """
    Détermine le rôle métier de l'utilisateur.

    Priorité:
      1) user.user_role.role (FK -> Role.role)
      2) Groupe Django (names: 'admin' / 'manager' / 'vendor')
      3) Fallbacks: is_superuser -> admin, is_staff -> manager

    Note: résultat mémoïsé sur l'instance user (_cached_role_name).
    """
    cached = getattr(user, "_cached_role_name", None)
    if cached is not None:
        return cached

    # 1) via FK Role
    role_obj = getattr(user, "user_role", None)
    if role_obj:
        r = _normalize_role(getattr(role_obj, "role", None))
        if r:
            user._cached_role_name = r
            return r

    # 2) via groupes Django
    try:
        group_names = { _normalize_role(n) for n in user.groups.values_list("name", flat=True) }
        for candidate in (ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR):
            if candidate in group_names:
                user._cached_role_name = candidate
                return candidate
    except Exception:
        pass

    # 3) fallbacks
    if getattr(user, "is_superuser", False):
        user._cached_role_name = ROLE_ADMIN
        return ROLE_ADMIN
    if getattr(user, "is_staff", False):
        user._cached_role_name = ROLE_MANAGER
        return ROLE_MANAGER

    user._cached_role_name = None
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
    