import re

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class EmailPhoneUsernameAuthenticationBackend(ModelBackend):
    """
    Authentification par :

    - adresse email ;
    - nom d'utilisateur ;
    - numéro de téléphone.

    L'email et le username sont insensibles à la casse.
    Le téléphone est normalisé comme dans le modèle User.
    """

    @staticmethod
    def normalize_phone(value: str) -> str:
        """
        Applique la même normalisation que User.clean() et User.save() :

        - suppression des espaces et séparateurs ;
        - suppression du + initial ;
        - conservation des chiffres uniquement.
        """

        phone = re.sub(r"\D", "", value or "")
        return phone

    def authenticate(
        self,
        request,
        username=None,
        password=None,
        **kwargs,
    ):
        identifier = username or kwargs.get(User.USERNAME_FIELD)

        if not identifier or password is None:
            return None

        identifier = str(identifier).strip()

        if not identifier:
            return None

        phone = self.normalize_phone(identifier)

        # On recherche séparément pour éviter qu'un OR retourne
        # plusieurs utilisateurs différents.
        candidates = []

        email_user = (
            User.objects
            .filter(email__iexact=identifier)
            .first()
        )

        if email_user:
            candidates.append(email_user)

        username_user = (
            User.objects
            .filter(username__iexact=identifier)
            .first()
        )

        if (
            username_user
            and username_user.pk not in {
                user.pk for user in candidates
            }
        ):
            candidates.append(username_user)

        if phone:
            phone_user = (
                User.objects
                .filter(telephone=phone)
                .first()
            )

            if (
                phone_user
                and phone_user.pk not in {
                    user.pk for user in candidates
                }
            ):
                candidates.append(phone_user)

        # Vérifie le mot de passe de chaque compte correspondant.
        for user in candidates:
            if (
                user.check_password(password)
                and self.user_can_authenticate(user)
            ):
                return user

        # Protection contre les attaques temporelles lorsqu'aucun
        # utilisateur n'a été trouvé.
        if not candidates:
            dummy_user = User()
            dummy_user.set_password(password)

        return None

    def get_user(self, user_id):
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

        return user if self.user_can_authenticate(user) else None
    

