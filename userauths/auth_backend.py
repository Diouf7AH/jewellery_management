from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
<<<<<<< HEAD
=======
#from django.contrib.auth.hashers import check_password
>>>>>>> 1827c79 (Sauvegarde locale avant pull)
from django.db.models import Q

User = get_user_model()

class EmailPhoneUsernameAuthenticationBackend(BaseBackend):
<<<<<<< HEAD
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = User.objects.get(
                Q(phone=username) | Q(email=username) | Q(username=username)
            )
        except User.DoesNotExist:
            return None

        if user and user.check_password(password) and user.is_active:
            return user

        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
=======
	def authenticate(self, request, username=None, password=None, **kwargs):
		if not username or not password:
			return None
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
>>>>>>> 1827c79 (Sauvegarde locale avant pull)
