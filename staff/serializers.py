
from django.contrib.auth import get_user_model
from django.core.validators import EmailValidator
from rest_framework import serializers

from store.models import Bijouterie

from .models import Manager

User = get_user_model()


class ManagerSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = Manager
        fields = ['email', 'bijouterie', 'verifie']


ROLE_VENDOR  = "vendor"
ROLE_CASHIER = "cashier"
ROLE_MANAGER = "manager"


class CreateStaffMemberSerializer(serializers.Serializer):
    email = serializers.EmailField()
    bijouterie = serializers.SlugRelatedField(
        queryset=Bijouterie.objects.all(),
        slug_field="nom",   # on envoie "rio-gold" par exemple
        help_text="Nom de la bijouterie (champ 'nom')"
    )
    role = serializers.ChoiceField(
        choices=[
            (ROLE_VENDOR, "vendor"),
            (ROLE_CASHIER, "cashier"),
            (ROLE_MANAGER, "manager"),
        ],
        help_text="Type de staff à créer: vendor, cashier ou manager"
    )

    def validate_email(self, value):
        return value.strip().lower()


# class CreateStaffMemberSerializer(serializers.Serializer):
#     email = serializers.EmailField(validators=[EmailValidator()],
#         help_text="Email de l’utilisateur existant"
#     )
#     # bijouterie = serializers.PrimaryKeyRelatedField(queryset=Bijouterie.objects.all(),
#     #     help_text="ID de la bijouterie valide"
#     # )
#     bijouterie = serializers.SlugRelatedField(
#         queryset=Bijouterie.objects.all(),
#         slug_field='nom',
#         write_only=True
#     )
#     role = serializers.ChoiceField(choices=[("vendor", "Vendor"), ("cashier", "Cashier")],
#         help_text="Type de staff à créer"
#     )
#     # description = serializers.CharField(
#     #     required=False, allow_blank=True, max_length=255
#     # )



# class UpdateStaffSerializer(serializers.Serializer):
#     email = serializers.EmailField(required=False)

#     # On envoie le NOM de la bijouterie, ça renvoie directement une instance de Bijouterie
#     bijouterie_nom = serializers.SlugRelatedField(
#         queryset=Bijouterie.objects.all(),
#         slug_field='nom',
#         required=False,
#         allow_null=True
#     )

#     verifie = serializers.BooleanField(required=False)
#     raison_desactivation = serializers.CharField(required=False, allow_blank=True, allow_null=True)

#     def validate_email(self, value):
#         email = value.strip().lower()
#         user_id = self.context.get("user_id")
#         if user_id:
#             # L’email ne doit pas être pris par un autre user
#             if User.objects.filter(email=email).exclude(id=user_id).exists():
#                 raise serializers.ValidationError("Cet email est déjà utilisé par un autre utilisateur.")
#         return email


# class UpdateStaffSerializer(serializers.Serializer):
#     """
#     Payload de mise à jour d’un staff (manager / cashier) :

#     {
#       "role": "manager" | "cashier",
#       "email": "nouveau@mail.com",
#       "bijouterie_nom": "Sandaga",
#       "verifie": true,
#       "raison_desactivation": "En congé"
#     }
#     """
#     role = serializers.ChoiceField(
#         choices=[("manager", "Manager"), ("cashier", "Cashier")],
#         help_text="Type de staff à mettre à jour"
#     )
#     email = serializers.EmailField(required=False)

#     # On envoie le NOM de la bijouterie, et SlugRelatedField récupère l’instance
#     bijouterie_nom = serializers.SlugRelatedField(
#         queryset=Bijouterie.objects.all(),
#         slug_field="nom",
#         required=False,
#         allow_null=True,
#         help_text="Nom de la bijouterie (ex: 'Sandaga')"
#     )

#     verifie = serializers.BooleanField(required=False)
#     raison_desactivation = serializers.CharField(
#         required=False,
#         allow_blank=True,
#         allow_null=True
#     )

#     def validate_email(self, value):
#         """
#         Vérifie que l'email n'est pas utilisé par un autre utilisateur.
#         On passe user_id dans le context depuis la vue.
#         """
#         email = value.strip().lower()
#         user_id = self.context.get("user_id")
#         qs = User.objects.filter(email=email)
#         if user_id:
#             qs = qs.exclude(id=user_id)
#         if qs.exists():
#             raise serializers.ValidationError("Cet email est déjà utilisé par un autre utilisateur.")
#         return email
    


class UpdateStaffSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=[("manager", "Manager"), ("cashier", "Cashier")],
        help_text="Type de staff à mettre à jour",
    )
    email = serializers.EmailField(required=False)
    bijouterie_nom = serializers.SlugRelatedField(
        queryset=Bijouterie.objects.all(),
        slug_field='nom',
        required=False,
        allow_null=True,
        help_text="Nom de la bijouterie à rattacher",
    )
    verifie = serializers.BooleanField(required=False)
    raison_desactivation = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    def validate_email(self, value):
        email = value.strip().lower()
        user_id = self.context.get("user_id")
        if user_id:
            if User.objects.filter(email=email).exclude(id=user_id).exists():
                raise serializers.ValidationError("Cet email est déjà utilisé par un autre utilisateur.")
        else:
            if User.objects.filter(email=email).exists():
                raise serializers.ValidationError("Cet email est déjà utilisé.")
        return email

