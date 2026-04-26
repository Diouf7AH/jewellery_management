import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from userauths.utils import send_confirmation_email

from .models import Profile, Role

User = get_user_model()

# class UserRegistrationSerializer(serializers.Serializer):
#     email = serializers.EmailField()
#     username = serializers.CharField(allow_blank=True, required=False)
#     telephone = serializers.CharField(allow_blank=True, required=False)
#     password = serializers.CharField(write_only=True, min_length=6)
#     password2 = serializers.CharField(write_only=True, label="Confirmer le mot de passe", min_length=6)

#     def validate_email(self, value):
#         if User.objects.filter(email=value).exists():
#             raise serializers.ValidationError("Cet email est déjà utilisé.")
#         return value

#     def validate_telephone(self, value):
#         if value and User.objects.filter(telephone=value).exists():
#             raise serializers.ValidationError("Ce numéro de téléphone est déjà utilisé.")
#         return value

#     def validate_username(self, value):
#         if value and User.objects.filter(username=value).exists():
#             raise serializers.ValidationError("Ce nom d'utilisateur est déjà pris.")
#         return value

#     def validate(self, attrs):
#         if attrs['password'] != attrs['password2']:
#             raise serializers.ValidationError({"password2": "Les mots de passe ne correspondent pas."})
#         try:
#             validate_password(attrs['password'])
#         except DjangoValidationError as e:
#             raise serializers.ValidationError({"password": e.messages})
#         return attrs


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    password2 = serializers.CharField(
        write_only=True,
        min_length=6,
        label="Confirmer le mot de passe"
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

    def validate_email(self, value):
        value = (value or "").strip().lower()

        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Cet email est déjà utilisé.")

        return value

    def validate_username(self, value):
        value = (value or "").strip()

        if not value:
            return None

        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Ce nom d'utilisateur est déjà pris.")

        return value

    def validate_telephone(self, value):
        value = (value or "").strip().replace(" ", "")

        if not value:
            return None

        if value.startswith("+"):
            value = value[1:]

        if not value.isdigit() or not (9 <= len(value) <= 15):
            raise serializers.ValidationError("Le numéro doit contenir 9 à 15 chiffres.")

        if User.objects.filter(telephone=value).exists():
            raise serializers.ValidationError("Ce numéro de téléphone est déjà utilisé.")

        return value

    def validate(self, attrs):
        password = attrs.get("password")
        password2 = attrs.get("password2")

        if password != password2:
            raise serializers.ValidationError({
                "password2": "Les mots de passe ne correspondent pas."
            })

        try:
            validate_password(password)
        except DjangoValidationError as e:
            raise serializers.ValidationError({
                "password": list(e.messages)
            })

        return attrs

    def _generate_unique_username(self, email):
        base_username = email.split("@")[0].strip().lower()
        username = base_username
        counter = 1

        while User.objects.filter(username__iexact=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        return username

    def create(self, validated_data):
        validated_data.pop("password2", None)
        password = validated_data.pop("password")

        email = validated_data.get("email")
        username = validated_data.get("username")
        telephone = validated_data.get("telephone")

        if not username:
            username = self._generate_unique_username(email)

        user = User.objects.create_user(
            email=email,
            username=username,
            telephone=telephone,
            password=password,
        )
        return user
    


class UserLoginSerializer(serializers.Serializer):
    user = serializers.CharField()  # peut être email, username ou telephone
    password = serializers.CharField()


# change password
class UserChangePasswordSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    class Meta:
        model = User
        fields = ['password']
    
    def update(self, instance, validated_data):

        instance.set_password(validated_data['password'])
        instance.save()

        return instance


class UserMiniSerializer(serializers.ModelSerializer):
    fullname = serializers.SerializerMethodField()
    class Meta:
        model = User
        fields = ['id', 'fullname']

    def get_fullname(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()
        

class UserDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'

    def get_role(self, obj):
        role = {}
        if obj.user_role:
            role = {
                "id": obj.user_role.id,
                "name": obj.user_role.role,
            }
        return role

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['user_role'] = self.get_role(instance)
        return data

class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'role']
        

# for profile
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'


class ProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Profile
        fields = [
            "id", "email", "first_name", "last_name", "full_name",
            "image", "bio", "sex", "country", "state", "city", "address",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "email", "first_name", "last_name", "full_name", "created_at", "updated_at"]




