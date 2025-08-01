import json
from datetime import timedelta

from django.core.mail import send_mail
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from django.shortcuts import render, redirect
from django.contrib import messages
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives

from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import authenticate

from backend.renderers import UserRenderer

from django.http import Http404 

from .auth_backend import EmailPhoneUsernameAuthenticationBackend as EoP
from .models import Profile, Role
from .serializers import (ProfileSerializer, RoleSerializer, UserChangePasswordSerializer, UserDetailSerializer, UserLoginSerializer, UserRegistrationSerializer)

from django.utils import timezone

from django.conf import settings

from django.core.mail import send_mail
from userauths.utils import verify_email_token, send_confirmation_email
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

User = get_user_model()

allowed_roles = ['admin', 'manager', 'vendeur']
# Create your views here.

# Generate Token Manually
def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

class UserRegistrationView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Inscription d’un nouvel utilisateur avec confirmation email",
        request_body=UserRegistrationSerializer,
        responses={
            201: openapi.Response('Inscription réussie', UserDetailSerializer),
            400: openapi.Response('Requête invalide')
        }
    )
    def post(self, request, format=None):
        serializer = UserRegistrationSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        data = {
            'message': "Inscription réussie ✅. Vérifiez votre email.",
            'user': UserDetailSerializer(user).data,
            'tokens': serializer.tokens
        }
        return Response(data, status=status.HTTP_201_CREATED)

class EmailVerificationView(APIView):
    permission_classes = []

    def get(self, request):
        token = request.GET.get('token')
        result = verify_email_token(token)
        status_token = result.get("status")
        email = result.get("email")

        if status_token == "invalid":
            return render(request, "emails/email_invalid.html", status=400)
        elif status_token == "expired":
            return render(request, "emails/email_expired.html", status=410)

        try:
            user = User.objects.get(email=email)
            if not user.is_email_verified:
                user.is_email_verified = True
                user.save()
            return render(request, "emails/email_confirmed.html")
        except User.DoesNotExist:
            return render(request, "emails/email_invalid.html", status=404)


def resend_confirmation_form(request):
    return render(request, 'emails/resend_confirmation_form.html')

MIN_RESEND_INTERVAL = timedelta(minutes=5)  # ⏱️ délai entre deux renvois
def resend_confirmation_submit(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        try:
            user = User.objects.get(email=email)

            if user.is_email_verified:
                messages.info(request, "Cet email est déjà vérifié.")
                return redirect('resend-confirmation-form')

            # ⏱️ Vérification du délai
            if user.last_confirmation_email_sent:
                since_last = timezone.now() - user.last_confirmation_email_sent
                if since_last < MIN_RESEND_INTERVAL:
                    minutes = int(MIN_RESEND_INTERVAL.total_seconds() // 60)
                    messages.warning(request, f"Veuillez attendre au moins {minutes} minutes entre deux envois.")
                    return redirect('resend-confirmation-form')


            # ✅ Envoi autorisé
            send_confirmation_email(user, request)
            user.last_confirmation_email_sent = timezone.now()
            user.save()

            messages.success(request, "Lien de confirmation renvoyé avec succès.")
        except User.DoesNotExist:
            messages.error(request, "Aucun utilisateur avec cet email.")
        return redirect('resend-confirmation-form')
    return redirect('resend-confirmation-form')

class UserLoginView(APIView):
    @swagger_auto_schema(
        operation_description="Login with email, username, or phone and password",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['user', 'password'],
            properties={
                'user': openapi.Schema(type=openapi.TYPE_STRING, description='Email, username or phone'),
                'password': openapi.Schema(type=openapi.TYPE_STRING, description='Password'),
            },
        ),
        responses={
            200: openapi.Response(
                description="Login successful",
                examples={
                    'application/json': {
                        'access': 'string',
                        'refresh': 'string',
                        'user_id': 1,
                        'email': 'user@example.com',
                        'username': 'username',
                        'role': 'vendeur'
                    }
                },
            ),
            403: openapi.Response(
                description="Email non vérifié",
                examples={'application/json': {'message': "❌ Votre adresse email n’a pas encore été confirmée."}}
            ),
            401: "Identifiants invalides",
        },
    )
    def post(self, request, format=None):
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_input = serializer.validated_data.get('user')
        password = serializer.validated_data.get('password')

        user = authenticate(request, username=user_input, password=password)

        if user:
            if not user.is_email_verified:
                return Response(
                    {"message": "❌ Votre adresse email n’a pas encore été confirmée."},
                    status=status.HTTP_403_FORBIDDEN
                )
            if not user.is_active:
                return Response(
                    {"message": "❌ Votre compte n'est pas active."},
                    status=status.HTTP_403_FORBIDDEN
                )

            # ⏱️ Mise à jour de la date de dernière connexion
            user.last_login = timezone.now()
            user.save(update_fields=["last_login"])

            tokens = get_tokens_for_user(user)

            return Response({
                'refresh': tokens['refresh'],
                'access': tokens['access'],
                'user_id': user.id,
                'email': user.email,
                'username': user.username,
                'role': user.user_role.role if user.user_role else '',
                'msg': 'Login successful ✅'
            }, status=status.HTTP_200_OK)

        return Response(
            {'errors': {'non_field_errors': ['❌ Identifiants invalides (email/téléphone/username ou mot de passe)']}},
            status=status.HTTP_401_UNAUTHORIZED
        )

class UserLogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Déconnexion de l'utilisateur (blacklist du refresh token)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['refresh'],
            properties={
                'refresh': openapi.Schema(type=openapi.TYPE_STRING, description='Refresh token à invalider'),
            },
        ),
        responses={
            200: "Déconnexion réussie",
            400: "Token invalide ou déjà blacklister",
        }
    )
    def post(self, request):
        refresh_token = request.data.get("refresh")

        if not refresh_token:
            return Response({"error": "Refresh token requis."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"message": "Déconnexion réussie ✅"}, status=status.HTTP_200_OK)
        except TokenError as e:
            return Response({"error": f"Token invalide ou expiré: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)




class ValidateTokenView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    def get(self,request):
        return Response({"message": "Success"}, status=status.HTTP_200_OK)

class UserDetailUpdateView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    def get(self,request,pk):
        # if request.user.is_authenticated and request.user.user_role and not request.user.use>
        #     return Response({"message": "Access Denied"})
        if not request.user.user_role or request.user.user_role.role not in allowed_roles:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        detail= User.objects.get(id=pk)
        serializer = UserDetailSerializer(detail)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Mise à jour complète d'un user",
        request_body=UserDetailSerializer,
        responses={
            200: UserDetailSerializer,
            400: "Requête invalide",
            404: "Rôle non trouvé"
        }
    )
    def put(self,request,pk):
        # if request.user.is_authenticated and request.user.user_role and not request.user.use>
        #     return Response({"message": "Access Denied"})
        if not request.user.user_role or request.user.user_role.role not in allowed_roles:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        detail= User.objects.get(id=pk)
        serializer = UserDetailSerializer(detail,request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors,status=status.HTTP_400_BAD_REQUEST)
    
    
    @swagger_auto_schema(
        operation_description="Supprime un user par ID",
        responses={
            204: 'Supprimé avec succès',
            404: 'User non trouvé'
        }
    )
    def delete(self, request, pk):
        # if request.user.is_authenticated and request.user.user_role and not request.user.use>
        #     return Response({"message": "Access Denied"})
        if not request.user.user_role or request.user.user_role.role not in allowed_roles:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        user = User.objects.get(id=pk)
        if user is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# User list
class UsersView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        responses={200: openapi.Response('response description', UserDetailSerializer)},
    )
    def get(self, request):
        # if request.user.is_authenticated and request.user.user_role and not request.user.use>
        #     return Response({"message": "Access Denied"})
        if not request.user.user_role or request.user.user_role.role not in allowed_roles:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        users = User.objects.all()
        serializer = UserDetailSerializer(users, many=True)
        return Response(serializer.data)

class ListRolesAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Liste tous les rôles disponibles",
        responses={200: RoleSerializer(many=True)},
        manual_parameters=[
            openapi.Parameter(
                'search',
                openapi.IN_QUERY,
                description="Filtrer les rôles par nom",
                type=openapi.TYPE_STRING
            )
        ]
    )
    def get(self, request):
        if not request.user.user_role or request.user.user_role.role not in allowed_roles:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        search = request.GET.get('search')
        queryset = Role.objects.all()
        if search:
            queryset = queryset.filter(role__icontains=search)
        serializer = RoleSerializer(queryset, many=True)
        return Response(serializer.data)

class CreateRoleAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Créer un nouveau rôle",
        request_body=RoleSerializer,
        responses={
            201: RoleSerializer,
            400: "Données invalides"
        }
    )
    def post(self, request):
        if not request.user.user_role or request.user.user_role.role not in allowed_roles:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        serializer = RoleSerializer(data=request.data)
        if serializer.is_valid():
            try:
                # Saving the data
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            except Exception as e:
                # Log the error if something goes wrong
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERRO)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GetOneRoleAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    def get_object(self, pk):
        try:
            return Role.objects.get(pk=pk)
        except Role.DoesNotExist:
            return None

    @swagger_auto_schema(
        operation_description="Récupère un rôle par ID",
        responses={200: RoleSerializer, 404: "Rôle non trouvé"}
    )
    def get(self, request, pk):
        if not request.user.user_role or request.user.user_role.role not in allowed_roles:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        role = self.get_object(pk)
        if role is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = RoleSerializer(role)
        return Response(serializer.data)


class UpdateRoleAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    def get_object(self, pk):
        try:
            return Role.objects.get(pk=pk)
        except Role.DoesNotExist:
            raise Http404

    @swagger_auto_schema(
        operation_description="Mise à jour complète d'un rôle",
        request_body=RoleSerializer,
        responses={
            200: RoleSerializer,
            400: "Requête invalide",
            404: "Rôle non trouvé"
        }
    )
    # PUT (mise à jour complète)
    def put(self, request, pk):
        # if request.user.user_role is not None and request.user.user_role.role != 'admin' and>
        #     return Response({"message": "Access Denied"})
        if not request.user.user_role or request.user.user_role.role not in allowed_roles:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        role = self.get_object(pk)
        if role is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = RoleSerializer(role, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
    @swagger_auto_schema(
        operation_description="Mise à jour partielle d'un rôle",
        request_body=RoleSerializer,
        responses={
            200: RoleSerializer,
            400: "Requête invalide",
            404: "Rôle non trouvé"
        }
    )
    # PATCH (mise à jour partielle)
    def patch(self, request, pk):
        role = self.get_object(pk)
        serializer = RoleSerializer(role, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DeleteRoleAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    
    def get_object(self, pk):
        try:
            return Role.objects.get(pk=pk)
        except Role.DoesNotExist:
            return None

    @swagger_auto_schema(
        operation_description="Supprime un rôle par ID",
        responses={
            204: 'Supprimé avec succès',
            404: 'Rôle non trouvé'
        }
    )
    def delete(self, request, pk):
        # if request.user.user_role is not None and request.user.user_role.role != 'admin' and>
        #     return Response({"message": "Access Denied"})
        if not request.user.user_role or request.user.user_role.role not in allowed_roles:
            return Response({"message": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        role = self.get_object(pk)
        if role is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        role.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# profile
class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Récupérer le profil de l'utilisateur connecté.",
        responses={200: openapi.Response('Profil récupéré avec succès', ProfileSerializer)},
    )
    def get(self, request, format=None):
        try:
            profile = Profile.objects.get(user=request.user)
        except Profile.DoesNotExist:
            return Response({"detail": "Profil introuvable."}, status=404)

        serializer = ProfileSerializer(profile)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="Mettre à jour totalement le profil de l'utilisateur connecté.",
        request_body=ProfileSerializer,
        responses={200: openapi.Response('Profil mis à jour avec succès', ProfileSerializer)},
    )
    def put(self, request, format=None):
        try:
            profile = Profile.objects.get(user=request.user)
        except Profile.DoesNotExist:
            return Response({"detail": "Profil introuvable."}, status=404)

        serializer = ProfileSerializer(profile, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    @swagger_auto_schema(
        operation_description="Mettre à jour partiellement le profil de l'utilisateur connecté.",
        request_body=ProfileSerializer,
        responses={200: openapi.Response('Profil partiellement mis à jour', ProfileSerializer)},
    )
    def patch(self, request, format=None):
        try:
            profile = Profile.objects.get(user=request.user)
        except Profile.DoesNotExist:
            return Response({"detail": "Profil introuvable."}, status=404)

        serializer = ProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)





