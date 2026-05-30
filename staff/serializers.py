
from django.contrib.auth import get_user_model
from django.core.validators import EmailValidator
from rest_framework import serializers

from backend.roles import ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR
from staff.models import Cashier
from store.models import Bijouterie

from .models import Manager

User = get_user_model()

# class UserSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = User
#         fields = ["id", "slug", "email", "username", "first_name", "last_name", "telephone"]



# class BijouterieMiniSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Bijouterie
#         fields = ["id", "nom"]

# class ManagerSerializer(serializers.ModelSerializer):
#     email = serializers.EmailField(source='user.email', read_only=True)

#     class Meta:
#         model = Manager
#         fields = ['email', 'bijouterie', 'verifie']





# class CreateStaffMemberSerializer(serializers.Serializer):
#     email = serializers.EmailField()
#     bijouterie = serializers.SlugRelatedField(
#         queryset=Bijouterie.objects.all(),
#         slug_field="nom",   # on envoie "rio-gold" par exemple
#         help_text="Nom de la bijouterie (champ 'nom')"
#     )
#     role = serializers.ChoiceField(
#         choices=[
#             (ROLE_VENDOR, "vendor"),
#             (ROLE_CASHIER, "cashier"),
#             (ROLE_MANAGER, "manager"),
#         ],
#         help_text="Type de staff à créer: vendor, cashier ou manager"
#     )

#     def validate_email(self, value):
#         return value.strip().lower()



# class CashierSerializer(serializers.ModelSerializer):
#     email = serializers.EmailField(source='user.email', read_only=True)

#     class Meta:
#         model = Cashier
#         fields = ['email', 'bijouterie', 'verifie']


# class CashierReadSerializer(serializers.ModelSerializer):
#     user = UserSerializer(read_only=True)
#     slug = serializers.CharField(source="user.slug", read_only=True)
#     bijouterie = BijouterieMiniSerializer(read_only=True)

#     # bonus "plats" pour le front
#     user_email = serializers.EmailField(source="user.email", read_only=True)
#     user_full_name = serializers.SerializerMethodField(read_only=True)
#     user_telephone = serializers.CharField(source="user.telephone", read_only=True)

#     # total encaissé (annoté dans la vue)
#     total_encaisse = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True, required=False)

#     class Meta:
#         model = Cashier
#         fields = [
#             "id",
#             "slug",
#             "user", "user_email", "user_full_name", "user_telephone",
#             "bijouterie",
#             "verifie", "raison_desactivation",
#             "total_encaisse",
#         ]

#     def get_user_full_name(self, obj):
#         u = obj.user
#         if not u:
#             return ""
#         fn = (u.first_name or "").strip()
#         ln = (u.last_name or "").strip()
#         return (f"{fn} {ln}").strip() or (u.username or u.email or "")


# class CashierUpdateSerializer(serializers.ModelSerializer):
#     # lier/délier la bijouterie par id
#     bijouterie_id = serializers.PrimaryKeyRelatedField(
#         source="bijouterie",
#         queryset=Bijouterie.objects.all(),
#         write_only=True,
#         required=False,
#         allow_null=True,
#     )
#     # patch des champs basiques du user
#     user = serializers.DictField(write_only=True, required=False)

#     class Meta:
#         model = Cashier
#         fields = ["verifie", "raison_desactivation", "bijouterie_id", "user"]

#     def validate_user(self, data):
#         user = getattr(self.instance, "user", None)
#         if not user:
#             return data

#         email = data.get("email")
#         if email and User.objects.exclude(pk=user.pk).filter(email__iexact=email).exists():
#             raise serializers.ValidationError({"email": "Cet email est déjà utilisé."})

#         username = data.get("username")
#         if username and User.objects.exclude(pk=user.pk).filter(username__iexact=username).exists():
#             raise serializers.ValidationError({"username": "Ce nom d’utilisateur est déjà utilisé."})

#         telephone = data.get("telephone")
#         if telephone and User.objects.exclude(pk=user.pk).filter(telephone__iexact=telephone).exists():
#             raise serializers.ValidationError({"telephone": "Ce téléphone est déjà utilisé."})

#         return data

#     def update(self, instance, validated_data):
#         # Cashier
#         bijouterie = validated_data.pop("bijouterie", serializers.empty)
#         if bijouterie is not serializers.empty:
#             instance.bijouterie = bijouterie

#         instance.verifie = validated_data.get("verifie", instance.verifie)
#         instance.raison_desactivation = validated_data.get("raison_desactivation", instance.raison_desactivation)
#         instance.save()

#         # User
#         user_data = validated_data.pop("user", {})
#         u = instance.user
#         if u and user_data:
#             for field in ("email", "username", "first_name", "last_name", "telephone"):
#                 if field in user_data:
#                     setattr(u, field, user_data[field])
#             u.save()

#         return instance




# class UpdateStaffSerializer(serializers.Serializer):
#     role = serializers.ChoiceField(
#         choices=[("manager", "Manager"), ("cashier", "Cashier")],
#         help_text="Type de staff à mettre à jour",
#     )
#     email = serializers.EmailField(required=False)
#     bijouterie_nom = serializers.SlugRelatedField(
#         queryset=Bijouterie.objects.all(),
#         slug_field='nom',
#         required=False,
#         allow_null=True,
#         help_text="Nom de la bijouterie à rattacher",
#     )
#     verifie = serializers.BooleanField(required=False)
#     raison_desactivation = serializers.CharField(
#         required=False,
#         allow_blank=True,
#         allow_null=True,
#     )

#     def validate_email(self, value):
#         email = value.strip().lower()
#         user_id = self.context.get("user_id")
#         if user_id:
#             if User.objects.filter(email=email).exclude(id=user_id).exists():
#                 raise serializers.ValidationError("Cet email est déjà utilisé par un autre utilisateur.")
#         else:
#             if User.objects.filter(email=email).exists():
#                 raise serializers.ValidationError("Cet email est déjà utilisé.")
#         return email


class CreateStaffUnifiedSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=[
            (ROLE_MANAGER, "Manager"),
            (ROLE_VENDOR, "Vendor"),
            (ROLE_CASHIER, "Cashier"),
        ]
    )

    email = serializers.EmailField()

    bijouterie_nom = serializers.SlugRelatedField(
        queryset=Bijouterie.objects.all(),
        slug_field="nom",
        required=False,
        allow_null=True,
        help_text="Nom de la bijouterie pour vendor/cashier",
    )

    bijouteries = serializers.PrimaryKeyRelatedField(
        queryset=Bijouterie.objects.all(),
        many=True,
        required=False,
        help_text="Liste des IDs des bijouteries pour manager",
    )

    verifie = serializers.BooleanField(required=False, default=True)

    def validate_email(self, value):
        return value.strip().lower()

    def validate(self, attrs):
        role = attrs["role"]
        email = attrs["email"]
        verifie = attrs.get("verifie", True)
        raison_desactivation = attrs.get("raison_desactivation")

        if not User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError({
                "email": (
                    "Aucun utilisateur trouvé avec cet email. "
                    "L'utilisateur doit d'abord créer son compte."
                )
            })

        if verifie is False and not raison_desactivation:
            raise serializers.ValidationError({
                "raison_desactivation": "La raison de désactivation est obligatoire."
            })

        if role == ROLE_MANAGER and not attrs.get("bijouteries"):
            raise serializers.ValidationError({
                "bijouteries": "Le manager doit avoir au moins une bijouterie."
            })

        if role in [ROLE_VENDOR, ROLE_CASHIER] and not attrs.get("bijouterie_nom"):
            raise serializers.ValidationError({
                "bijouterie_nom": "La bijouterie est obligatoire pour vendor/cashier."
            })

        return attrs


class StaffCreatedResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    staff_type = serializers.CharField()
    staff = serializers.DictField()
    user = serializers.DictField()
    

class UpdateStaffUnifiedSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=[
            (ROLE_MANAGER, "Manager"),
            (ROLE_VENDOR, "Vendor"),
            (ROLE_CASHIER, "Cashier"),
        ]
    )

    email = serializers.EmailField(required=False)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)

    # Pour vendor/cashier
    bijouterie_nom = serializers.SlugRelatedField(
        queryset=Bijouterie.objects.all(),
        slug_field="nom",
        required=False,
        allow_null=True,
        help_text="Nom de la bijouterie pour vendor/cashier"
    )

    # Pour manager
    bijouteries = serializers.PrimaryKeyRelatedField(
        queryset=Bijouterie.objects.all(),
        many=True,
        required=False,
        help_text="Liste des IDs des bijouteries pour manager"
    )

    verifie = serializers.BooleanField(required=False)
    raison_desactivation = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True
    )

    def validate_email(self, value):
        email = value.strip().lower()
        user_id = self.context.get("user_id")

        qs = User.objects.filter(email__iexact=email)
        if user_id:
            qs = qs.exclude(id=user_id)

        if qs.exists():
            raise serializers.ValidationError("Cet email est déjà utilisé par un autre utilisateur.")

        return email

    def validate(self, attrs):
        role = attrs.get("role")

        if role == ROLE_MANAGER and attrs.get("bijouterie_nom"):
            raise serializers.ValidationError({
                "bijouterie_nom": "Utilisez 'bijouteries' pour modifier les bijouteries d'un manager."
            })

        if role in [ROLE_VENDOR, ROLE_CASHIER] and attrs.get("bijouteries"):
            raise serializers.ValidationError({
                "bijouteries": "Utilisez 'bijouterie_nom' pour vendor/cashier."
            })

        return attrs

# List
class StaffUnifiedListItemSerializer(serializers.Serializer):
    staff_id = serializers.IntegerField()
    role = serializers.CharField()
    user_id = serializers.IntegerField(allow_null=True)
    email = serializers.EmailField(allow_null=True)
    first_name = serializers.CharField(allow_blank=True)
    last_name = serializers.CharField(allow_blank=True)
    verifie = serializers.BooleanField()
    raison_desactivation = serializers.CharField(allow_null=True, allow_blank=True)
    bijouteries = serializers.ListField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    
    
class StaffDetailUnifiedSerializer(serializers.Serializer):
    staff_id = serializers.IntegerField()
    role = serializers.CharField()

    user = serializers.DictField()
    staff = serializers.DictField()
    

class StaffDashboardSerializer(serializers.Serializer):
    managers_count = serializers.IntegerField()
    vendors_count = serializers.IntegerField()
    cashiers_count = serializers.IntegerField()
    verified_count = serializers.IntegerField()
    disabled_count = serializers.IntegerField()


class StaffDashboardByBijouterieSerializer(serializers.Serializer):
    bijouterie_id = serializers.IntegerField(allow_null=True)
    bijouterie_nom = serializers.CharField(allow_null=True, allow_blank=True)
    managers_count = serializers.IntegerField()
    vendors_count = serializers.IntegerField()
    cashiers_count = serializers.IntegerField()


class StaffDashboardRecentItemSerializer(serializers.Serializer):
    staff_id = serializers.IntegerField()
    role = serializers.CharField()
    email = serializers.EmailField(allow_null=True)
    first_name = serializers.CharField(allow_blank=True)
    last_name = serializers.CharField(allow_blank=True)
    verifie = serializers.BooleanField()
    bijouterie_id = serializers.IntegerField(allow_null=True)
    bijouterie_nom = serializers.CharField(allow_null=True, allow_blank=True)
    created_at = serializers.DateTimeField()


class StaffDashboardResponseSerializer(serializers.Serializer):
    resume = StaffDashboardSerializer()
    by_bijouterie = StaffDashboardByBijouterieSerializer(many=True)
    recent_staff = StaffDashboardRecentItemSerializer(many=True)
    



