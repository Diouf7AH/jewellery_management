from rest_framework.permissions import BasePermission

class IsAdminOrManager(BasePermission):
    message = "Access Denied"  # ce message sera renvoyé en 403

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        # Optionnel : superuser a toujours l'accès
        if getattr(user, "is_superuser", False):
            return True

        # Si tu veux aussi autoriser is_staff, décommente la ligne suivante :
        # if getattr(user, "is_staff", False):
        #     return True

        # Ton modèle de rôle custom : user.user_role.role ∈ {"admin", "manager"}
        role_obj = getattr(user, "user_role", None)
        role = getattr(role_obj, "role", None)
        return role in {"admin", "manager"}