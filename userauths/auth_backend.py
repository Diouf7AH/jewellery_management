from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.db.models import Q

User = get_user_model()

class EmailPhoneUsernameAuthenticationBackend:
    @staticmethod
    def authenticate(request, email=None, username=None, phone=None, password=None):
        filters = Q()

        if phone:
            filters |= Q(phone=phone)
        if email:
            filters |= Q(email=email)
        if username:
            filters |= Q(username=username)
            
        users = User.objects.filter(filters).distinct()
        print("Utilisateurs trouvés:", users)

        for user in users:
            print("Test utilisateur:", user.email)
            if check_password(password, user.password):
                print("Mot de passe OK")
                return user

        print("Mot de passe incorrect")
        return None

    #     users = User.objects.filter(filters).distinct()

    #     for user in users:
    #         if user.password and check_password(password, user.password):
    #             return user

    #     return None

    # @staticmethod
    # def get_user(user_id):
    #     try:
    #         return User.objects.get(pk=user_id)
    #     except User.DoesNotExist:
    #         return None