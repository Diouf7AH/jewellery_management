from rest_framework.permissions import BasePermission

class IsAdminOrManager(BasePermission):
    """
    Autorise uniquement les utilisateurs ayant user_role.role ∈ {admin, manager}.
    """
    message = "Accès refusé (réservé aux rôles admin/manager)."

    def has_permission(self, request, view):
        role = getattr(getattr(request.user, "user_role", None), "role", None)
        return role in {"admin", "manager"}

