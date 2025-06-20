from rest_framework import serializers
from .models import Profile, Role
from django.contrib.auth import get_user_model
import re
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.password_validation import validate_password
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.mail import send_mail
from django.conf import settings
from userauths.utils import send_confirmation_email

User = get_user_model()

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    password2 = serializers.CharField(write_only=True, label="Confirmer le mot de passe", min_length=6)

    class Meta:
        model = User
        fields = ['email', 'username', 'telephone', 'password', 'password2']

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Cet email est déjà utilisé.")
        return value

    def validate_telephone(self, value):
        if value and User.objects.filter(telephone=value).exists():
            raise serializers.ValidationError("Ce numéro de téléphone est déjà utilisé.")
        return value

    def validate_username(self, value):
        if value and User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Ce nom d'utilisateur est déjà pris.")
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password2": "Les mots de passe ne correspondent pas."})
        try:
            validate_password(attrs['password'])
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": e.messages})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.is_active = True  # ou False si tu veux bloquer l’accès avant confirmation
        # user.is_active = False  # 🔐 bloqué jusqu'à validation email
        user.is_email_verified = False  # 🔐 bloqué jusqu'à validation email
        user.save()

        request = self.context.get('request')
        if request:
            send_confirmation_email(user, request)

        refresh = RefreshToken.for_user(user)
        self.tokens = {
            'access': str(refresh.access_token),
            'refresh': str(refresh)
        }

        return user


# class ResendConfirmationSerializer(serializers.Serializer):
#     email = serializers.EmailField()

#     def validate_email(self, value):
#         try:
#             user = User.objects.get(email=value)
#         except User.DoesNotExist:
#             raise serializers.ValidationError("Aucun utilisateur avec cet email.")

#         if user.is_email_verified:
#             raise serializers.ValidationError("Cet utilisateur a déjà confirmé son email.")

#         self.user = user  # on garde pour plus tard
#         return value


# class UserRegistrationSerializer(serializers.ModelSerializer):
#     password = serializers.CharField(write_only=True, min_length=6)
#     class Meta:
#         model = User
#         fields=['email', 'username', 'first_name', 'last_name', 'telephone', 'password', 'user_role']
#         extra_kwargs={
#             'password':{'write_only':True}
#         }
    
#     def create(self, validated_data):
#         password = validated_data.pop('password')
#         user = User(**validated_data)
#         user.set_password(password)
#         user.save()
#         return user

        

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
    class Meta:
        model = Profile
        fields = '__all__'
        
    def to_representation(self, instance):
        response = super().to_representation(instance)
        response['user'] = UserSerializer(instance.user).data
        return response


