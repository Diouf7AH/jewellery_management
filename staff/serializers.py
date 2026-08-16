from django.contrib.auth import get_user_model
from rest_framework import serializers

from backend.roles import (ROLE_ADMIN, ROLE_BUYER, ROLE_CASHIER, ROLE_MANAGER,
                           ROLE_VENDOR)
from store.models import Bijouterie

User = get_user_model()


# ============================================================
# Création d'un staff
# ============================================================
class CreateStaffSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=[
            (ROLE_ADMIN, "Administrateur"),
            (ROLE_MANAGER, "Manager"),
            (ROLE_VENDOR, "Vendeur"),
            (ROLE_CASHIER, "Caissier"),
            (ROLE_BUYER, "Responsable rachat"),
        ]
    )

    email = serializers.EmailField()

    # Vendor / Cashier / Buyer : une seule bijouterie
    bijouterie_id = serializers.PrimaryKeyRelatedField(
        queryset=Bijouterie.objects.all(),
        required=False,
        allow_null=True,
        help_text=(
            "ID de la bijouterie pour vendor, cashier ou buyer."
        ),
    )

    # Manager : plusieurs bijouteries
    bijouteries = serializers.PrimaryKeyRelatedField(
        queryset=Bijouterie.objects.all(),
        many=True,
        required=False,
        help_text=(
            "Liste des IDs des bijouteries pour un manager."
        ),
    )

    def validate_email(self, value):
        return value.strip().lower()

    def validate(self, attrs):
        role = attrs["role"]
        email = attrs["email"]

        if not User.objects.filter(
            email__iexact=email
        ).exists():
            raise serializers.ValidationError({
                "email": (
                    "Aucun utilisateur trouvé avec cet email. "
                    "L'utilisateur doit d'abord créer son compte."
                )
            })

        # ====================================================
        # Manager
        # ====================================================

        if role == ROLE_MANAGER:
            if not attrs.get("bijouteries"):
                raise serializers.ValidationError({
                    "bijouteries": (
                        "Le manager doit avoir au moins "
                        "une bijouterie."
                    )
                })

            if attrs.get("bijouterie_id"):
                raise serializers.ValidationError({
                    "bijouterie_id": (
                        "Utilisez 'bijouteries' pour un manager."
                    )
                })

        # ====================================================
        # Vendor / Cashier / Buyer
        # ====================================================

        if role in {
            ROLE_VENDOR,
            ROLE_CASHIER,
            ROLE_BUYER,
        }:
            if not attrs.get("bijouterie_id"):
                raise serializers.ValidationError({
                    "bijouterie_id": (
                        "La bijouterie est obligatoire pour "
                        "vendor, cashier et buyer."
                    )
                })

            if attrs.get("bijouteries"):
                raise serializers.ValidationError({
                    "bijouteries": (
                        "Utilisez 'bijouterie_id' pour vendor, "
                        "cashier et buyer."
                    )
                })

        return attrs
    
# ============================================================
# Réponse après création
# ============================================================

class StaffCreatedResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    staff_type = serializers.CharField()
    staff = serializers.DictField()
    user = serializers.DictField()


# ============================================================
# Mise à jour d'un staff
# ============================================================
class UpdateStaffSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=[
            (ROLE_MANAGER, "Manager"),
            (ROLE_VENDOR, "Vendeur"),
            (ROLE_CASHIER, "Caissier"),
            (ROLE_BUYER, "Responsable rachat"),
        ],
        required=True,
    )

    email = serializers.EmailField(required=False)

    first_name = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    last_name = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    bijouterie_nom = serializers.SlugRelatedField(
        queryset=Bijouterie.objects.all(),
        slug_field="nom",
        required=False,
        allow_null=True,
        help_text=(
            "Nom de la bijouterie pour vendor, cashier ou buyer."
        ),
    )

    bijouteries = serializers.PrimaryKeyRelatedField(
        queryset=Bijouterie.objects.all(),
        many=True,
        required=False,
        help_text=(
            "Liste des IDs des bijouteries pour un manager."
        ),
    )

    verifie = serializers.BooleanField(
        required=False,
    )

    raison_desactivation = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    def validate_email(self, value):
        email = value.strip().lower()
        user_id = self.context.get("user_id")

        queryset = User.objects.filter(
            email__iexact=email
        )

        if user_id:
            queryset = queryset.exclude(
                pk=user_id
            )

        if queryset.exists():
            raise serializers.ValidationError(
                "Cet email est déjà utilisé par un autre utilisateur."
            )

        return email

    def validate(self, attrs):
        role = attrs.get("role")
        verifie = attrs.get("verifie")

        raison_desactivation = (
            attrs.get("raison_desactivation") or ""
        ).strip()

        if role == ROLE_MANAGER:
            if attrs.get("bijouterie_nom"):
                raise serializers.ValidationError({
                    "bijouterie_nom": (
                        "Utilisez 'bijouteries' pour modifier "
                        "les bijouteries d'un manager."
                    )
                })

        if role in {
            ROLE_VENDOR,
            ROLE_CASHIER,
            ROLE_BUYER,
        }:
            if attrs.get("bijouteries"):
                raise serializers.ValidationError({
                    "bijouteries": (
                        "Utilisez 'bijouterie_nom' pour vendor, "
                        "cashier et buyer."
                    )
                })

        if verifie is False and not raison_desactivation:
            raise serializers.ValidationError({
                "raison_desactivation": (
                    "La raison de désactivation est obligatoire."
                )
            })

        return attrs


# ============================================================
# Liste unifiée des staff
# ============================================================

class StaffBijouterieSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nom = serializers.CharField()


class StaffListItemSerializer(serializers.Serializer):
    staff_id = serializers.IntegerField()
    role = serializers.CharField()

    user_id = serializers.IntegerField(
        allow_null=True,
    )

    email = serializers.EmailField(
        allow_null=True,
    )

    first_name = serializers.CharField(
        allow_blank=True,
    )

    last_name = serializers.CharField(
        allow_blank=True,
    )

    verifie = serializers.BooleanField()

    raison_desactivation = serializers.CharField(
        allow_null=True,
        allow_blank=True,
    )

    bijouteries = StaffBijouterieSerializer(
        many=True,
    )

    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


# ============================================================
# Détail d'un staff
# ============================================================

class StaffDetailSerializer(serializers.Serializer):
    staff_id = serializers.IntegerField()
    role = serializers.CharField()
    user = serializers.DictField()
    staff = serializers.DictField()


# ============================================================
# Dashboard
# ============================================================

class StaffDashboardSummarySerializer(serializers.Serializer):
    managers_count = serializers.IntegerField()
    vendors_count = serializers.IntegerField()
    cashiers_count = serializers.IntegerField()
    buyers_count = serializers.IntegerField()
    verified_count = serializers.IntegerField()
    disabled_count = serializers.IntegerField()


class StaffDashboardByBijouterieSerializer(
    serializers.Serializer
):
    bijouterie_id = serializers.IntegerField(
        allow_null=True,
    )

    bijouterie_nom = serializers.CharField(
        allow_null=True,
        allow_blank=True,
    )

    managers_count = serializers.IntegerField()
    vendors_count = serializers.IntegerField()
    cashiers_count = serializers.IntegerField()
    buyers_count = serializers.IntegerField()


class StaffDashboardRecentItemSerializer(
    serializers.Serializer
):
    staff_id = serializers.IntegerField()
    role = serializers.CharField()

    email = serializers.EmailField(
        allow_null=True,
    )

    first_name = serializers.CharField(
        allow_blank=True,
    )

    last_name = serializers.CharField(
        allow_blank=True,
    )

    verifie = serializers.BooleanField()

    bijouteries = StaffBijouterieSerializer(
        many=True,
    )

    created_at = serializers.DateTimeField()


class StaffDashboardResponseSerializer(
    serializers.Serializer
):
    summary = StaffDashboardSummarySerializer()

    by_bijouterie = (
        StaffDashboardByBijouterieSerializer(
            many=True,
        )
    )

    recent_staff = StaffDashboardRecentItemSerializer(
        many=True,
    )
    
    