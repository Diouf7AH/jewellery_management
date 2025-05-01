from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

class EmailPhoneUsernameAuthenticationBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authentifie un utilisateur via son email, nom d'utilisateur ou téléphone.
        """
        if not username or not password:
            return None

        # Cherche dans email, username, ou téléphone
        user = User.objects.filter(
            Q(email=username) | Q(username=username) | Q(phone=username)
        ).first()

        if user and user.check_password(password) and user.is_active:
            return user

        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

