from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
from django.db.models import Q
import re

User = get_user_model()

# class EmailPhoneUsernameAuthenticationBackend(BaseBackend):
#     def authenticate(self, request, username=None, password=None, **kwargs):
#         if not username or not password:
#             return None

#         try:
#             user = User.objects.get(
#                 Q(email=username) | Q(username=username) | Q(telephone=username)
#             )
#         except User.DoesNotExist:
#             return None

#         if user.check_password(password) and user.is_active:
#             return user

#         return None

#     def get_user(self, user_id):
#         try:
#             return User.objects.get(pk=user_id)
#         except User.DoesNotExist:
#             return None


class EmailPhoneUsernameAuthenticationBackend(BaseBackend):
    """
    Auth par email / username / téléphone.
    - Insensible à la casse (email/username).
    - Normalise basiquement le téléphone (retire espaces, -, .).
    - Anti timing-attack si l'utilisateur n'existe pas.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        ident = str(username).strip()
        # Normalise un peu le téléphone (garde + et chiffres)
        phone_norm = re.sub(r"[^\d+]", "", ident)

        qs = User.objects.filter(
            Q(email__iexact=ident) |
            Q(username__iexact=ident) |
            Q(telephone=ident) |
            Q(telephone=phone_norm)
        )

        user = qs.first()
        # Anti timing-attack: brûle le hash même si l'utilisateur n'existe pas
        if user is None:
            dummy = User()
            dummy.set_password(password)
            return None

        if user.is_active and user.check_password(password):
            return user
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None