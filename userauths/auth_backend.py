# # userauths/auth_backend.py
# import re

# from django.contrib.auth import get_user_model
# from django.contrib.auth.backends import ModelBackend

# User = get_user_model()


# class EmailPhoneUsernameAuthenticationBackend(ModelBackend):
#     """
#     Authentification par :

#     - adresse email ;
#     - nom d'utilisateur ;
#     - numéro de téléphone.

#     L'email et le username sont insensibles à la casse.
#     Le téléphone est normalisé comme dans le modèle User.
#     """

#     @staticmethod
#     def normalize_phone(value: str) -> str:
#         """
#         Applique la même normalisation que User.clean() et User.save() :

#         - suppression des espaces et séparateurs ;
#         - suppression du + initial ;
#         - conservation des chiffres uniquement.
#         """

#         phone = re.sub(r"\D", "", value or "")
#         return phone

#     def authenticate(
#         self,
#         request,
#         username=None,
#         password=None,
#         **kwargs,
#     ):
#         identifier = username or kwargs.get(User.USERNAME_FIELD)

#         if not identifier or password is None:
#             return None

#         identifier = str(identifier).strip()

#         if not identifier:
#             return None

#         phone = self.normalize_phone(identifier)

#         # On recherche séparément pour éviter qu'un OR retourne
#         # plusieurs utilisateurs différents.
#         candidates = []

#         email_user = (
#             User.objects
#             .filter(email__iexact=identifier)
#             .first()
#         )

#         if email_user:
#             candidates.append(email_user)

#         username_user = (
#             User.objects
#             .filter(username__iexact=identifier)
#             .first()
#         )

#         if (
#             username_user
#             and username_user.pk not in {
#                 user.pk for user in candidates
#             }
#         ):
#             candidates.append(username_user)

#         if phone:
#             phone_user = (
#                 User.objects
#                 .filter(telephone=phone)
#                 .first()
#             )

#             if (
#                 phone_user
#                 and phone_user.pk not in {
#                     user.pk for user in candidates
#                 }
#             ):
#                 candidates.append(phone_user)

#         # Vérifie le mot de passe de chaque compte correspondant.
#         for user in candidates:
#             if (
#                 user.check_password(password)
#                 and self.user_can_authenticate(user)
#             ):
#                 return user

#         # Protection contre les attaques temporelles lorsqu'aucun
#         # utilisateur n'a été trouvé.
#         if not candidates:
#             dummy_user = User()
#             dummy_user.set_password(password)

#         return None

#     def get_user(self, user_id):
#         try:
#             user = User.objects.get(pk=user_id)
#         except User.DoesNotExist:
#             return None

#         return user if self.user_can_authenticate(user) else None
    

# userauths/auth_backend.py

import re

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

User = get_user_model()


class EmailPhoneUsernameAuthenticationBackend(ModelBackend):
    """
    Authentification par :
        - email
        - username
        - téléphone

    Sécurité :
        - email et username insensibles à la casse
        - normalisation du téléphone
        - refus des identifiants ambigus
        - vérification du mot de passe
        - compte actif obligatoire
        - email vérifié obligatoire
    """

    @staticmethod
    def normalize_phone(value):
        """
        Supprime les caractères non numériques.

        Cette règle doit rester identique à celle
        utilisée dans le modèle User.
        """
        return re.sub(r"\D", "", str(value or ""))

    def user_can_authenticate(self, user):
        """
        Refuse les comptes inactifs
        et les emails non vérifiés.
        """
        return bool(
            super().user_can_authenticate(user)
            and user.is_email_verified
        )

    def authenticate(
        self,
        request,
        username=None,
        password=None,
        **kwargs,
    ):
        identifier = username

        if identifier is None:
            identifier = kwargs.get(User.USERNAME_FIELD)

        if identifier is None or password is None:
            return None

        identifier = str(identifier).strip()

        if not identifier:
            return None

        phone = self.normalize_phone(identifier)

        # Recherche email et username.
        conditions = (
            Q(email__iexact=identifier)
            | Q(username__iexact=identifier)
        )

        # Téléphone uniquement si l'identifiant
        # est constitué de chiffres et séparateurs
        # téléphoniques autorisés.
        if (
            phone
            and re.fullmatch(r"\+?[\d\s().-]+", identifier)
        ):
            conditions |= Q(telephone=phone)

        candidates = list(
            User.objects.filter(conditions)
            .distinct()[:2]
        )

        # Aucun compte ou identifiant ambigu.
        if len(candidates) != 1:
            User().set_password(password)
            return None

        user = candidates[0]

        if (
            user.check_password(password)
            and self.user_can_authenticate(user)
        ):
            return user

        return None

    def get_user(self, user_id):
        """
        Recharge uniquement un utilisateur
        autorisé à s'authentifier.
        """
        try:
            user = User.objects.get(pk=user_id)

        except (User.DoesNotExist, ValueError, TypeError):
            return None

        if self.user_can_authenticate(user):
            return user

        return None