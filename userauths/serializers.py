import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from backend.roles import get_role_name
from userauths.utils import send_confirmation_email

from .models import Profile, Role

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = "__all__"
        extra_kwargs = {
            "password": {
                "write_only": True,
            },
        }


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        min_length=6,
        trim_whitespace=False,
    )

    password2 = serializers.CharField(
        write_only=True,
        min_length=6,
        trim_whitespace=False,
        label="Confirmer le mot de passe",
    )

    class Meta:
        model = User
        fields = [
            "email",
            "username",
            "telephone",
            "password",
            "password2",
        ]
        extra_kwargs = {
            "username": {
                "required": False,
                "allow_blank": True,
                "allow_null": True,
            },
            "telephone": {
                "required": False,
                "allow_blank": True,
                "allow_null": True,
            },
        }

    def validate_email(self, value):
        value = (value or "").strip().lower()

        if not value:
            raise serializers.ValidationError(
                "L'adresse email est obligatoire."
            )

        if User.objects.filter(
            email__iexact=value,
        ).exists():
            raise serializers.ValidationError(
                "Cet email est déjà utilisé."
            )

        return value

    def validate_username(self, value):
        value = (value or "").strip()

        if not value:
            return None

        if User.objects.filter(
            username__iexact=value,
        ).exists():
            raise serializers.ValidationError(
                "Ce nom d'utilisateur est déjà pris."
            )

        return value

    def validate_telephone(self, value):
        value = (
            value or ""
        ).strip().replace(" ", "")

        if not value:
            return None

        if value.startswith("+"):
            value = value[1:]

        if not value.isdigit():
            raise serializers.ValidationError(
                "Le numéro de téléphone doit contenir uniquement des chiffres."
            )

        if not 9 <= len(value) <= 15:
            raise serializers.ValidationError(
                "Le numéro doit contenir entre 9 et 15 chiffres."
            )

        if User.objects.filter(
            telephone=value,
        ).exists():
            raise serializers.ValidationError(
                "Ce numéro de téléphone est déjà utilisé."
            )

        return value

    def validate(self, attrs):
        password = attrs.get("password")
        password2 = attrs.get("password2")

        if password != password2:
            raise serializers.ValidationError(
                {
                    "password2": (
                        "Les mots de passe ne correspondent pas."
                    )
                }
            )

        try:
            validate_password(password)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                {
                    "password": list(exc.messages)
                }
            )

        return attrs

    def _generate_unique_username(self, email):
        base_username = (
            email.split("@")[0]
            .strip()
            .lower()
        )

        base_username = re.sub(
            r"[^a-zA-Z0-9._-]",
            "",
            base_username,
        )

        if not base_username:
            base_username = "user"

        username = base_username
        counter = 1

        while User.objects.filter(
            username__iexact=username,
        ).exists():
            username = f"{base_username}{counter}"
            counter += 1

        return username

    def create(self, validated_data):
        validated_data.pop(
            "password2",
            None,
        )

        password = validated_data.pop(
            "password",
        )

        email = validated_data.pop(
            "email",
        )

        username = validated_data.pop(
            "username",
            None,
        )

        telephone = validated_data.pop(
            "telephone",
            None,
        )

        if not username:
            username = self._generate_unique_username(
                email,
            )

        user = User.objects.create_user(
            email=email,
            username=username,
            telephone=telephone,
            password=password,
            **validated_data,
        )

        return user


class UserLoginSerializer(serializers.Serializer):
    user = serializers.CharField(
        trim_whitespace=True,
    )

    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
    )

    def validate_user(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "L'identifiant est requis."
            )

        return value
    

# change password
class UserChangePasswordSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        trim_whitespace=False,
    )

    class Meta:
        model = User
        fields = ["password"]

    def validate_password(self, value):
        try:
            validate_password(
                value,
                self.instance,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                list(exc.messages)
            )

        return value

    def update(self, instance, validated_data):
        instance.set_password(
            validated_data["password"]
        )

        instance.save(
            update_fields=["password"]
        )

        return instance
    

class UserMiniSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
        ]
        read_only_fields = fields

    def get_full_name(self, obj):
        return (
            f"{obj.first_name or ''} "
            f"{obj.last_name or ''}"
        ).strip()

class UserDetailSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField(
        read_only=True,
    )

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "telephone",
            "first_name",
            "last_name",
            "role",
            "is_active",
            "is_email_verified",
            "date_joined",
            "last_login",
        ]

        read_only_fields = [
            "id",
            "email",
            "role",
            "is_email_verified",
            "date_joined",
            "last_login",
        ]

    def get_role(self, obj):
        return get_role_name(obj)

class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = [
            "id",
            "role",
        ]
        read_only_fields = [
            "id",
        ]

    def validate_role(self, value):
        value = (value or "").strip().lower()

        if not value:
            raise serializers.ValidationError(
                "Le nom du rôle est obligatoire."
            )

        queryset = Role.objects.filter(
            role__iexact=value,
        )

        if self.instance:
            queryset = queryset.exclude(
                pk=self.instance.pk,
            )

        if queryset.exists():
            raise serializers.ValidationError(
                "Ce rôle existe déjà."
            )

        return value

# Profile
class UserProfileMiniSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "telephone",
            "first_name",
            "last_name",
            "full_name",
            "display_name",
            "role",
            "is_email_verified",
            "slug",
            "date_joined",
        ]
        read_only_fields = fields

    def get_role(self, obj):
        return getattr(obj, "role_name", None)

    def get_full_name(self, obj):
        return getattr(obj, "full_name", "") or ""

    def get_display_name(self, obj):
        return getattr(obj, "display_name", "") or ""
    

class ProfileSerializer(serializers.ModelSerializer):
    user = UserProfileMiniSerializer(read_only=True)
    image_url = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = [
            "id",
            "user",
            "image",
            "image_url",
            "bio",
            "country",
            "state",
            "city",
            "address",
            "full_name",
            "role",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "image_url",
            "full_name",
            "role",
            "created_at",
            "updated_at",
        ]

    def get_image_url(self, obj):
        image = getattr(obj, "image", None)

        if not image:
            return None

        try:
            image_url = image.url
        except (ValueError, AttributeError):
            return None

        request = self.context.get("request")

        if request:
            return request.build_absolute_uri(image_url)

        return image_url

    def get_full_name(self, obj):
        user = getattr(obj, "user", None)

        if not user:
            return ""

        return getattr(user, "full_name", "") or ""

    def get_role(self, obj):
        user = getattr(obj, "user", None)

        if not user:
            return None

        return getattr(user, "role_name", None)
    

class ProfileUpdateSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(
        source="user.first_name",
        required=False,
        allow_blank=True,
    )

    last_name = serializers.CharField(
        source="user.last_name",
        required=False,
        allow_blank=True,
    )

    username = serializers.CharField(
        source="user.username",
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    telephone = serializers.CharField(
        source="user.telephone",
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    class Meta:
        model = Profile
        fields = [
            "image",
            "bio",
            "country",
            "state",
            "city",
            "address",
            "first_name",
            "last_name",
            "username",
            "telephone",
        ]

    def validate_username(self, value):
        value = (value or "").strip()

        if not value:
            return None

        user = (
            self.instance.user
            if self.instance
            else None
        )

        queryset = User.objects.filter(
            username__iexact=value,
        )

        if user:
            queryset = queryset.exclude(
                pk=user.pk,
            )

        if queryset.exists():
            raise serializers.ValidationError(
                "Ce nom d'utilisateur est déjà pris."
            )

        return value

    def validate_telephone(self, value):
        value = (
            value or ""
        ).strip().replace(" ", "")

        if not value:
            return None

        if value.startswith("+"):
            value = value[1:]

        if not value.isdigit():
            raise serializers.ValidationError(
                "Le numéro doit contenir uniquement des chiffres."
            )

        if not 9 <= len(value) <= 15:
            raise serializers.ValidationError(
                "Le numéro doit contenir entre 9 et 15 chiffres."
            )

        user = (
            self.instance.user
            if self.instance
            else None
        )

        queryset = User.objects.filter(
            telephone=value,
        )

        if user:
            queryset = queryset.exclude(
                pk=user.pk,
            )

        if queryset.exists():
            raise serializers.ValidationError(
                "Ce numéro de téléphone est déjà utilisé."
            )

        return value

    def update(self, instance, validated_data):
        user_data = validated_data.pop(
            "user",
            {},
        )

        profile_fields = []

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
            profile_fields.append(attr)

        if profile_fields:
            instance.save(
                update_fields=profile_fields + ["updated_at"]
            )

        user = instance.user
        user_fields = []

        for field in [
            "first_name",
            "last_name",
            "username",
            "telephone",
        ]:
            if field in user_data:
                setattr(
                    user,
                    field,
                    user_data[field],
                )
                user_fields.append(field)

        if user_fields:
            user.save(
                update_fields=user_fields
            )

        instance.refresh_from_db()

        return instance
    
# end profile