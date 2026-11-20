from rest_framework import serializers

from administration.models import AdminProfile

# ============================================================
# SERIALIZER DE SORTIE
# ============================================================

class AdminProfileSerializer(serializers.ModelSerializer):

    user_id = serializers.IntegerField(
        source="user.id",
        read_only=True,
    )

    email = serializers.EmailField(
        source="user.email",
        read_only=True,
    )

    first_name = serializers.CharField(
        source="user.first_name",
        read_only=True,
    )

    last_name = serializers.CharField(
        source="user.last_name",
        read_only=True,
    )

    is_active = serializers.BooleanField(
        source="user.is_active",
        read_only=True,
    )

    class Meta:
        model = AdminProfile

        fields = [
            "id",
            "user_id",
            "email",
            "first_name",
            "last_name",
            "niveau",
            "verifie",
            "raison_desactivation",
            "date_desactivation",
            "peut_gerer_bijouteries",
            "peut_voir_finances",
            "is_active",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields


# ============================================================
# CRÉATION
# ============================================================

class CreateAdminSerializer(serializers.Serializer):

    email = serializers.EmailField(
        required=True,
    )


# ============================================================
# MODIFICATION DES PERMISSIONS
# ============================================================

class UpdateAdminPermissionsSerializer(serializers.Serializer):

    peut_gerer_bijouteries = serializers.BooleanField(
        required=False,
    )

    peut_voir_finances = serializers.BooleanField(
        required=False,
    )

    def validate(self, attrs):

        if not attrs:
            raise serializers.ValidationError(
                "Au moins une permission doit être renseignée."
            )

        return attrs


# ============================================================
# DÉSACTIVATION
# ============================================================

class DeactivateAdminSerializer(serializers.Serializer):

    raison_desactivation = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
    )


# ============================================================
# RÉACTIVATION
# ============================================================

class ReactivateAdminSerializer(serializers.Serializer):
    pass


# ============================================================
# RÉPONSE STANDARD AVEC ADMINISTRATEUR
# ============================================================

class AdminActionResponseSerializer(serializers.Serializer):

    message = serializers.CharField()

    administrateur = AdminProfileSerializer(
        read_only=True,
    )
    

