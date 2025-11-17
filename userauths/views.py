from datetime import timedelta
from smtplib import (SMTPDataError, SMTPException, SMTPRecipientsRefused,
                     SMTPSenderRefused)

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_http_methods
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import parsers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from backend.renderers import UserRenderer
from userauths.utils import send_confirmation_email, verify_email_token

from .auth_backend import EmailPhoneUsernameAuthenticationBackend as EoP
from .models import Profile, Role
# (optionnel) si tu mets en place la file d’attente :
from .serializers import (ProfileSerializer, RoleSerializer,
                          UserChangePasswordSerializer, UserDetailSerializer,
                          UserLoginSerializer, UserRegistrationSerializer)
from .utils import generate_email_token, send_confirmation_email

# versio angular
# from userauths.tokens import generate_email_token, verify_email_token
# Dans UserRegistrationView → tu appelles generate_email_token(user)
# Dans EmailVerificationView → tu appelles verify_email_token(token)


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

# class UserRegistrationView(APIView):
#     permission_classes = [AllowAny]

#     @swagger_auto_schema(
#         operation_description="Inscription d’un nouvel utilisateur avec confirmation email",
#         request_body=UserRegistrationSerializer,
#         responses={
#             201: openapi.Response('Inscription réussie', UserRegistrationSerializer),
#             400: openapi.Response('Requête invalide')
#         }
#     )
#     def post(self, request, format=None):
#         serializer = UserRegistrationSerializer(data=request.data, context={'request': request})
#         serializer.is_valid(raise_exception=True)
#         user = serializer.save()
#         data = {
#             'message': "Inscription réussie ✅. Vérifiez votre email.",
#             'user': UserRegistrationSerializer(user).data,
#             'tokens': serializer.tokens
#         }
#         return Response(data, status=status.HTTP_201_CREATED)



# class UserRegistrationView(APIView):
#     permission_classes = [AllowAny]

#     @swagger_auto_schema(
#         operation_summary="Inscription d’un nouvel utilisateur avec confirmation email",
#         operation_description="Crée l'utilisateur, génère les tokens JWT et envoie l'email de confirmation.",
#         request_body=UserRegistrationSerializer,
#         responses={
#             201: openapi.Response('Inscription réussie'),
#             400: openapi.Response('Requête invalide')
#         }
#     )
#     @transaction.atomic
#     def post(self, request, format=None):
#         s = UserRegistrationSerializer(data=request.data)
#         s.is_valid(raise_exception=True)
#         data = s.validated_data

#         # --- Création utilisateur ---
#         email_norm = (data["email"] or "").strip().lower()
#         username = (data.get("username") or "").strip()
#         telephone = (data.get("telephone") or "").strip()

#         try:
#             user = User(
#                 email=email_norm,
#                 username=username,
#                 telephone=telephone,
#                 is_active=False,          # actif après confirmation
#                 is_email_verified=False,
#             )
#             user.set_password(data["password"])
#             user.save()
#         except IntegrityError:
#             return Response(
#                 {"email": ["Cet email est déjà utilisé."]},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         # --- JWT tokens ---
#         refresh = RefreshToken.for_user(user)
#         tokens = {
#             "access": str(refresh.access_token),
#             "refresh": str(refresh),
#         }

#         # --- Lien de confirmation ---
#         token = generate_email_token(user)

#         frontend = (
#             getattr(settings, "FRONTEND_BASE_URL", "")
#             or getattr(settings, "FRONTEND_URL", "")
#             or ""
#         ).rstrip("/")

#         if frontend:
#             # URL front : https://rio-gold.com/confirm-email?token=...
#             confirm_url = f"{frontend}/confirm-email?token={token}"
#             home_url = frontend
#         else:
#             # Fallback backend
#             from django.urls import reverse
#             confirm_url = request.build_absolute_uri(
#                 reverse("verify-email") + f"?token={token}"
#             )
#             home_url = request.build_absolute_uri("/")

#         # --- Envoi direct (pas d'outbox) ---
#         email_status = "sent"
#         try:
#             send_confirmation_email(
#                 user,
#                 request=None,
#                 confirm_url=confirm_url,
#                 home_url=home_url,
#             )
#         except (SMTPRecipientsRefused, SMTPDataError, SMTPSenderRefused, SMTPException) as e:
#             print("ERREUR SMTP >>>", e)  # utile en dev
#             email_status = "failed"
#         except Exception as e:
#             print("ERREUR ENVOI EMAIL >>>", e)
#             email_status = "failed"

#         # --- Réponse ---
#         return Response(
#             {
#                 "message": "Inscription réussie ✅. Vérifiez votre email.",
#                 "user": {
#                     "id": user.id,
#                     "email": user.email,
#                     "username": user.username,
#                     "telephone": user.telephone,
#                     "is_active": user.is_active,
#                     "is_email_verified": getattr(user, "is_email_verified", False),
#                 },
#                 "tokens": tokens,
#                 "email_status": email_status,  # "sent" ou "failed"
#             },
#             status=status.HTTP_201_CREATED,
#         )


class UserRegistrationView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary="Inscription d’un nouvel utilisateur avec confirmation email",
        operation_description="Crée l'utilisateur, génère les tokens JWT et envoie l'email de confirmation.",
        request_body=UserRegistrationSerializer,
        responses={
            201: openapi.Response('Inscription réussie'),
            400: openapi.Response('Requête invalide')
        }
    )
    @transaction.atomic
    def post(self, request, format=None):
        s = UserRegistrationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        # --- Création utilisateur ---
        email_norm = (data["email"] or "").strip().lower()
        username = (data.get("username") or "").strip()
        telephone = (data.get("telephone") or "").strip()

        user = User(
            email=email_norm,
            username=username,
            telephone=telephone,
            is_active=False,
            is_email_verified=False,
        )
        user.set_password(data["password"])
        user.save()

        # --- JWT tokens ---
        refresh = RefreshToken.for_user(user)
        tokens = {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }

        # --- Lien de confirmation (BACKEND) ---
        token = generate_email_token(user)

        confirm_url = request.build_absolute_uri(
            reverse("verify-email") + f"?token={token}"
        )
        home_url = request.build_absolute_uri("/")

        # --- Envoi email direct ---
        email_status = "sent"
        try:
            send_confirmation_email(
                user,
                request=None,
                confirm_url=confirm_url,
                home_url=home_url,
            )
        except (SMTPRecipientsRefused, SMTPDataError, SMTPSenderRefused, SMTPException) as e:
            print("ERREUR SMTP >>>", e)
            email_status = "failed"
        except Exception as e:
            print("ERREUR ENVOI EMAIL >>>", e)
            email_status = "failed"

        return Response(
            {
                "message": "Inscription réussie ✅. Vérifiez votre email.",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "telephone": user.telephone,
                    "is_active": user.is_active,
                    "is_email_verified": getattr(user, "is_email_verified", False),
                },
                "tokens": tokens,
                "email_status": email_status,
            },
            status=status.HTTP_201_CREATED,
        )


@method_decorator(require_GET, name="dispatch")
class EmailVerificationView(APIView):
    permission_classes = []  # public

    def get(self, request):
        token = request.GET.get('token')
        if not token:
            return render(request, "emails/email_invalid.html", status=400)

        result = verify_email_token(token) or {}
        status_token = result.get("status")
        email = result.get("email")

        if status_token == "invalid" or not email:
            return render(request, "emails/email_invalid.html", status=400)

        if status_token == "expired":
            # Lien expiré → template avec explication + éventuellement bouton vers ton front
            return render(request, "emails/email_expired.html", status=410)

        # status == "ok"
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return render(request, "emails/email_invalid.html", status=404)

        if not getattr(user, "is_email_verified", False):
            user.is_email_verified = True
            user.save(update_fields=["is_email_verified"])

        return render(request, "emails/email_confirmed.html", status=200)
    
    

# class EmailVerificationView(APIView):
#     permission_classes = []

#     def get(self, request):
#         token = request.GET.get('token')
#         result = verify_email_token(token)
#         status_token = result.get("status")
#         email = result.get("email")

#         if status_token == "invalid":
#             return render(request, "emails/email_invalid.html", status=400)
#         elif status_token == "expired":
#             return render(request, "emails/email_expired.html", status=410)

#         try:
#             user = User.objects.get(email=email)
#             if not user.is_email_verified:
#                 user.is_active = True
#                 user.is_email_verified = True
#                 user.save()
#             return render(request, "emails/email_confirmed.html")
#         except User.DoesNotExist:
#             return render(request, "emails/email_invalid.html", status=404)

@method_decorator(require_GET, name="dispatch")
class EmailVerificationView(APIView):
    permission_classes = []  # public

    def get(self, request):
        token = request.GET.get('token')
        if not token:
            return render(request, "emails/email_invalid.html", status=400)

        result = verify_email_token(token) or {}
        status_token = result.get("status")
        email = result.get("email")

        # 1️⃣ D'abord : token expiré
        if status_token == "expired":
            return render(request, "emails/email_expired.html", status=410)

        # 2️⃣ Ensuite : token invalide
        if status_token == "invalid":
            return render(request, "emails/email_invalid.html", status=400)

        # 3️⃣ Puis : pas d'email retourné (sécurité)
        if not email:
            return render(request, "emails/email_invalid.html", status=400)

        # 4️⃣ Token OK → on vérifie l'utilisateur
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return render(request, "emails/email_invalid.html", status=404)

        if not getattr(user, "is_email_verified", False):
            user.is_email_verified = True
            user.save(update_fields=["is_email_verified"])

        return render(request, "emails/email_confirmed.html", status=200)


class ResendVerificationEmailView(APIView):
    permission_classes = []  # public

    def post(self, request):
        email = request.data.get("email")

        if not email:
            return Response(
                {"detail": "L'adresse email est requise."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"detail": "Si un compte existe avec cet email, un nouveau lien a été envoyé."},
                status=status.HTTP_200_OK,
            )

        if getattr(user, "is_email_verified", False):
            return Response(
                {"detail": "Ce compte est déjà vérifié."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            send_confirmation_email(user, request=request)
        except Exception:
            return Response(
                {"detail": "Impossible d'envoyer l'email pour le moment."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {"detail": "Un nouveau lien de vérification a été envoyé à cette adresse email."},
            status=status.HTTP_200_OK,
        )


# # version Angular
# class EmailVerificationView(APIView):
#     permission_classes = []  # public

#     def get(self, request):
#         token = request.GET.get("token")
#         if not token:
#             return Response(
#                 {"status": "invalid", "detail": "Token manquant."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         result = verify_email_token(token) or {}
#         status_token = (result.get("status") or "").lower()
#         email = (result.get("email") or "").strip().lower()

#         # Token expiré
#         if status_token == "expired":
#             return Response({"status": "expired"}, status=status.HTTP_410_GONE)

#         # Token invalide
#         if status_token not in ("valid", "ok") or not email:
#             return Response({"status": "invalid"}, status=status.HTTP_400_BAD_REQUEST)

#         # Récupérer l'utilisateur
#         try:
#             user = User.objects.get(email=email)
#         except User.DoesNotExist:
#             return Response({"status": "invalid"}, status=status.HTTP_404_NOT_FOUND)

#         # Déjà vérifié → idempotent
#         if getattr(user, "is_email_verified", False) and getattr(user, "is_active", True):
#             return Response({"status": "ok"}, status=status.HTTP_200_OK)

#         # Marquer vérifié (+ activer si besoin)
#         user.is_email_verified = True
#         update_fields = ["is_email_verified"]
#         if hasattr(user, "is_active") and not user.is_active:
#             user.is_active = True
#             update_fields.append("is_active")
#         user.save(update_fields=update_fields)

#         return Response({"status": "ok"}, status=status.HTTP_200_OK)


# def resend_confirmation_form(request):
#     return render(request, 'emails/resend_confirmation_form.html')

# MIN_RESEND_INTERVAL = timedelta(minutes=5)  # ⏱️ délai entre deux renvois
# def resend_confirmation_submit(request):
#     if request.method == 'POST':
#         email = request.POST.get('email')
#         try:
#             user = User.objects.get(email=email)

#             if user.is_email_verified:
#                 messages.info(request, "Cet email est déjà vérifié.")
#                 return redirect('resend-confirmation-form')

#             # ⏱️ Vérification du délai
#             if user.last_confirmation_email_sent:
#                 since_last = timezone.now() - user.last_confirmation_email_sent
#                 if since_last < MIN_RESEND_INTERVAL:
#                     minutes = int(MIN_RESEND_INTERVAL.total_seconds() // 60)
#                     messages.warning(request, f"Veuillez attendre au moins {minutes} minutes entre deux envois.")
#                     return redirect('resend-confirmation-form')


#             # ✅ Envoi autorisé
#             send_confirmation_email(user, request)
#             user.last_confirmation_email_sent = timezone.now()
#             user.save()

#             messages.success(request, "Lien de confirmation renvoyé avec succès.")
#         except User.DoesNotExist:
#             messages.error(request, "Aucun utilisateur avec cet email.")
#         return redirect('resend-confirmation-form')
#     return redirect('resend-confirmation-form')


MIN_RESEND_INTERVAL = timedelta(minutes=5)

def resend_confirmation_form(request):
    return render(request, "emails/resend_confirmation_form.html")


@csrf_protect
@require_http_methods(["POST"])
def resend_confirmation_submit(request):
    email = (request.POST.get("email") or "").strip().lower()
    if not email:
        messages.error(request, "Veuillez saisir un email.")
        return redirect("resend-confirmation-form")

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        messages.error(request, "Aucun utilisateur avec cet email.")
        return redirect("resend-confirmation-form")

    # Déjà vérifié ?
    if getattr(user, "is_email_verified", False):
        messages.info(request, "Cet email est déjà vérifié.")
        return redirect("resend-confirmation-form")

    # Throttle: délai minimum entre deux envois
    last = getattr(user, "last_confirmation_email_sent", None)
    if last:
        since_last = timezone.now() - last
        if since_last < MIN_RESEND_INTERVAL:
            minutes = int(MIN_RESEND_INTERVAL.total_seconds() // 60)
            messages.warning(request, f"Veuillez attendre au moins {minutes} minutes avant un nouvel envoi.")
            return redirect("resend-confirmation-form")

    # Construire l’URL de confirmation (aligne AVEC TA ROUTE)
    # Route attendue dans urls.py: path('verify-email/', EmailVerificationView.as_view(), name='verify-email')
    token = generate_email_token(user)  # ta fonction existante
    path = reverse("verify-email")      # -> "/verify-email/"
    confirm_url = request.build_absolute_uri(f"{path}?token={token}")
    home_url = request.build_absolute_uri("/")  # utile si ton template email a besoin d'un lien "Accueil"

    try:
        # Envoi de l’email — adapte la signature à ta fonction
        send_confirmation_email(user, request=request, confirm_url=confirm_url, home_url=home_url)
        # Mémoriser le timestamp d’envoi
        user.last_confirmation_email_sent = timezone.now()
        user.save(update_fields=["last_confirmation_email_sent"])
        messages.success(request, "Lien de confirmation renvoyé avec succès.")
    except Exception as e:
        # Log en interne si besoin
        messages.error(request, "Une erreur est survenue lors de l’envoi. Réessayez plus tard.")
    return redirect("resend-confirmation-form")


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
# class ProfileView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Récupérer le profil de l'utilisateur connecté.",
#         responses={200: openapi.Response('Profil récupéré avec succès', ProfileSerializer)},
#     )
#     def get(self, request, format=None):
#         try:
#             profile = Profile.objects.get(user=request.user)
#         except Profile.DoesNotExist:
#             return Response({"detail": "Profil introuvable."}, status=404)

#         serializer = ProfileSerializer(profile)
#         return Response(serializer.data)

#     @swagger_auto_schema(
#         operation_description="Mettre à jour totalement le profil de l'utilisateur connecté.",
#         request_body=ProfileSerializer,
#         responses={200: openapi.Response('Profil mis à jour avec succès', ProfileSerializer)},
#     )
#     def put(self, request, format=None):
#         try:
#             profile = Profile.objects.get(user=request.user)
#         except Profile.DoesNotExist:
#             return Response({"detail": "Profil introuvable."}, status=404)

#         serializer = ProfileSerializer(profile, data=request.data)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data)
#         return Response(serializer.errors, status=400)

#     @swagger_auto_schema(
#         operation_description="Mettre à jour partiellement le profil de l'utilisateur connecté.",
#         request_body=ProfileSerializer,
#         responses={200: openapi.Response('Profil partiellement mis à jour', ProfileSerializer)},
#     )
#     def patch(self, request, format=None):
#         try:
#             profile = Profile.objects.get(user=request.user)
#         except Profile.DoesNotExist:
#             return Response({"detail": "Profil introuvable."}, status=404)

#         serializer = ProfileSerializer(profile, data=request.data, partial=True)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data)
#         return Response(serializer.errors, status=400)


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]
    # ← autorise JSON, form-data et multipart (pour image)
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    @swagger_auto_schema(
        operation_summary="Voir mon profil",
        operation_description="Retourne le profil de l’utilisateur connecté.",
        responses={200: ProfileSerializer, 401: "Non authentifié"},
        tags=["Profil"]
    )
    def get(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        return Response(ProfileSerializer(profile).data)

    @swagger_auto_schema(
        operation_summary="Modifier mon profil (partiel)",
        operation_description=(
            "Met à jour partiellement le profil de l’utilisateur connecté. "
            "Accepte JSON ou multipart/form-data pour l’upload de l’image."
        ),
        request_body=ProfileSerializer,  # champs du serializer; PATCH est partiel
        responses={200: ProfileSerializer, 400: "Requête invalide", 401: "Non authentifié"},
        consumes=['application/json', 'multipart/form-data'],
        tags=["Profil"]
    )
    def patch(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        s = ProfileSerializer(profile, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data, status=status.HTTP_200_OK)

