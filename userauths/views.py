import logging
from datetime import timedelta
from smtplib import (SMTPDataError, SMTPException, SMTPRecipientsRefused,
                     SMTPSenderRefused)

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import update_last_login
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_http_methods
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from backend.permissions import IsAdmin, IsAdminOrManager
from backend.renderers import UserRenderer
from backend.roles import SYSTEM_ROLES, get_role_name

from .models import Profile, Role
from .serializers import (ProfileSerializer, ProfileUpdateSerializer,
                          RoleSerializer, UserDetailSerializer,
                          UserLoginSerializer, UserRegistrationSerializer)
from .utils import (generate_email_token, send_confirmation_email,
                    verify_email_token)

logger = logging.getLogger(__name__)

MIN_RESEND_INTERVAL = timedelta(minutes=5)

User = get_user_model()


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)

    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


class UserRegistrationView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary="Inscription publique avec confirmation email",
        operation_description=(
            "Crée un utilisateur public sans rôle staff. "
            "Le rôle sera affecté plus tard via l'API Staff."
        ),
        request_body=UserRegistrationSerializer,
        responses={
            201: openapi.Response("Inscription réussie"),
            400: openapi.Response("Requête invalide"),
        },
    )
    @transaction.atomic
    def post(self, request, format=None):
        serializer = UserRegistrationSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        user = serializer.save(
            user_role=None,
        )

        token = generate_email_token(user)

        confirm_url = request.build_absolute_uri(
            f"{reverse('verify-email')}?token={token}"
        )

        home_url = request.build_absolute_uri("/")

        email_status = "sent"

        try:
            send_confirmation_email(
                user,
                request=None,
                confirm_url=confirm_url,
                home_url=home_url,
            )

        except (
            SMTPRecipientsRefused,
            SMTPDataError,
            SMTPSenderRefused,
            SMTPException,
        ):
            logger.exception(
                "Erreur SMTP pendant l'inscription de %s.",
                user.email,
            )
            email_status = "failed"

        except Exception:
            logger.exception(
                "Erreur inattendue pendant l'envoi "
                "de l'email de confirmation à %s.",
                user.email,
            )
            email_status = "failed"

        return Response(
            {
                "message": (
                    "Inscription réussie ✅. "
                    "Vérifiez votre email."
                ),
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "telephone": user.telephone,
                    "role": None,
                    "is_active": user.is_active,
                    "is_email_verified": (
                        user.is_email_verified
                    ),
                },
                "email_status": email_status,
            },
            status=status.HTTP_201_CREATED,
        )
        
@method_decorator(require_GET, name="dispatch")
class EmailVerificationView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        token = request.GET.get("token")

        if not token:
            return render(
                request,
                "emails/email_invalid.html",
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = verify_email_token(token) or {}

        token_status = result.get("status")
        user_id = result.get("user_id")
        email = (result.get("email") or "").strip().lower()

        # Token expiré
        if token_status == "expired":
            return render(
                request,
                "emails/email_expired.html",
                status=status.HTTP_410_GONE,
            )

        # Token invalide ou données incomplètes
        if token_status != "ok" or not user_id or not email:
            return render(
                request,
                "emails/email_invalid.html",
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Recherche avec l'ID et l'email contenus dans le token
        try:
            user = User.objects.get(
                pk=user_id,
                email__iexact=email,
            )
        except User.DoesNotExist:
            return render(
                request,
                "emails/email_invalid.html",
                status=status.HTTP_404_NOT_FOUND,
            )

        # Première confirmation uniquement
        if not getattr(user, "is_email_verified", False):
            user.is_email_verified = True

            update_fields = ["is_email_verified"]

            # Activation autorisée uniquement lors de la première confirmation.
            # Un compte déjà vérifié puis désactivé ne sera pas réactivé.
            if not user.is_active:
                user.is_active = True
                update_fields.append("is_active")

            user.save(update_fields=update_fields)

        return render(
            request,
            "emails/email_confirmed.html",
            {
                "frontend_url": getattr(
                    settings,
                    "FRONTEND_URL",
                    "https://rio-gold.com",
                ).rstrip("/"),
            },
            status=status.HTTP_200_OK,
        )

class ResendVerificationEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = (
            request.data.get("email")
            or ""
        ).strip().lower()

        if not email:
            return Response(
                {
                    "detail": (
                        "L'adresse email est requise."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        generic_message = (
            "Si un compte non vérifié existe avec cet email, "
            "un nouveau lien de confirmation a été envoyé."
        )

        try:
            user = User.objects.get(
                email__iexact=email,
            )
        except User.DoesNotExist:
            # Réponse volontairement générique :
            # évite de révéler si un compte existe.
            return Response(
                {"detail": generic_message},
                status=status.HTTP_200_OK,
            )

        # Un compte déjà vérifié ne doit pas recevoir
        # de nouveau lien de confirmation.
        if getattr(user, "is_email_verified", False):
            return Response(
                {"detail": generic_message},
                status=status.HTTP_200_OK,
            )

        last_sent = getattr(
            user,
            "last_confirmation_email_sent",
            None,
        )

        if last_sent:
            elapsed = timezone.now() - last_sent

            if elapsed < MIN_RESEND_INTERVAL:
                remaining_seconds = (
                    MIN_RESEND_INTERVAL - elapsed
                ).total_seconds()

                remaining_minutes = max(
                    1,
                    int(remaining_seconds // 60) + 1,
                )

                return Response(
                    {
                        "detail": (
                            "Veuillez patienter avant "
                            "de demander un nouveau lien."
                        ),
                        "retry_after_minutes": (
                            remaining_minutes
                        ),
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

        try:
            send_confirmation_email(
                user,
                request=request,
            )

        except Exception:
            logger.exception(
                "Erreur lors du renvoi de l'email "
                "de confirmation à %s.",
                user.email,
            )

            return Response(
                {
                    "detail": (
                        "Impossible d'envoyer l'email "
                        "pour le moment."
                    )
                },
                status=(
                    status.HTTP_503_SERVICE_UNAVAILABLE
                ),
            )

        user.last_confirmation_email_sent = (
            timezone.now()
        )

        user.save(
            update_fields=[
                "last_confirmation_email_sent",
            ]
        )

        return Response(
            {"detail": generic_message},
            status=status.HTTP_200_OK,
        )

def resend_confirmation_form(request):
    return render(
        request,
        "emails/resend_confirmation_form.html",
    )


@csrf_protect
@require_http_methods(["POST"])
def resend_confirmation_submit(request):
    email = (
        request.POST.get("email")
        or ""
    ).strip().lower()

    if not email:
        messages.error(
            request,
            "Veuillez saisir une adresse email.",
        )
        return redirect("resend-confirmation-form")

    generic_message = (
        "Si un compte non vérifié existe avec cette adresse, "
        "un nouveau lien de confirmation sera envoyé."
    )

    try:
        user = User.objects.get(
            email__iexact=email,
        )
    except User.DoesNotExist:
        messages.success(
            request,
            generic_message,
        )
        return redirect("resend-confirmation-form")

    # Un compte déjà vérifié ne doit pas recevoir
    # un nouveau lien de confirmation.
    if getattr(user, "is_email_verified", False):
        messages.info(
            request,
            "Cette adresse email est déjà vérifiée.",
        )
        return redirect("resend-confirmation-form")

    # Limitation des renvois successifs.
    last_sent = getattr(
        user,
        "last_confirmation_email_sent",
        None,
    )

    if last_sent:
        elapsed = timezone.now() - last_sent

        if elapsed < MIN_RESEND_INTERVAL:
            remaining = MIN_RESEND_INTERVAL - elapsed

            remaining_minutes = max(
                1,
                int(remaining.total_seconds() // 60) + 1,
            )

            messages.warning(
                request,
                (
                    "Veuillez attendre encore environ "
                    f"{remaining_minutes} minute(s) "
                    "avant un nouvel envoi."
                ),
            )
            return redirect("resend-confirmation-form")

    token = generate_email_token(user)

    verification_path = reverse("verify-email")

    confirm_url = request.build_absolute_uri(
        f"{verification_path}?token={token}"
    )

    home_url = request.build_absolute_uri("/")

    try:
        send_confirmation_email(
            user,
            request=request,
            confirm_url=confirm_url,
            home_url=home_url,
        )

    except Exception:
        logger.exception(
            "Erreur lors du renvoi de l'email "
            "de confirmation pour %s.",
            user.email,
        )

        messages.error(
            request,
            (
                "Une erreur est survenue lors de l'envoi. "
                "Veuillez réessayer plus tard."
            ),
        )

        return redirect("resend-confirmation-form")

    user.last_confirmation_email_sent = timezone.now()

    user.save(
        update_fields=[
            "last_confirmation_email_sent",
        ]
    )

    messages.success(
        request,
        "Lien de confirmation renvoyé avec succès.",
    )

    return redirect("resend-confirmation-form")


class UserLoginView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary="Connexion utilisateur",
        operation_description=(
            "Connexion avec une adresse email, un nom d'utilisateur "
            "ou un numéro de téléphone."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["user", "password"],
            properties={
                "user": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description=(
                        "Adresse email, nom d'utilisateur "
                        "ou numéro de téléphone"
                    ),
                ),
                "password": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Mot de passe",
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="Connexion réussie",
            ),
            401: openapi.Response(
                description=(
                    "Identifiants invalides, compte désactivé "
                    "ou compte non autorisé"
                ),
            ),
            403: openapi.Response(
                description="Adresse email non vérifiée",
            ),
            400: openapi.Response(
                description="Données invalides",
            ),
        },
    )
    def post(self, request, format=None):
        serializer = UserLoginSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        identifier = (
            serializer.validated_data.get("user")
            or ""
        ).strip()

        password = serializer.validated_data.get("password")

        user = authenticate(
            request=request,
            username=identifier,
            password=password,
        )

        # Le backend retourne None si :
        # - identifiants incorrects ;
        # - compte inactif ;
        # - utilisateur introuvable.
        if user is None:
            return Response(
                {
                    "errors": {
                        "non_field_errors": [
                            "❌ Identifiants invalides "
                            "ou compte désactivé."
                        ]
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not getattr(
            user,
            "is_email_verified",
            False,
        ):
            return Response(
                {
                    "message": (
                        "❌ Votre adresse email n’a pas "
                        "encore été confirmée."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        update_last_login(None, user)

        tokens = get_tokens_for_user(user)

        role = get_role_name(user)

        return Response(
            {
                "refresh": tokens["refresh"],
                "access": tokens["access"],
                "user": {
                    "id": user.pk,
                    "email": user.email,
                    "username": user.username,
                    "telephone": getattr(
                        user,
                        "telephone",
                        None,
                    ),
                    "role": role,
                    "is_active": user.is_active,
                    "is_email_verified": (
                        user.is_email_verified
                    ),
                },
                "message": "Connexion réussie ✅",
            },
            status=status.HTTP_200_OK,
        )
        
class UserLogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Déconnexion utilisateur",
        operation_description=(
            "Déconnecte l'utilisateur en ajoutant "
            "son refresh token à la blacklist."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["refresh"],
            properties={
                "refresh": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Refresh token à invalider",
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="Déconnexion réussie",
            ),
            400: openapi.Response(
                description=(
                    "Refresh token manquant, invalide "
                    "ou déjà blacklisté"
                ),
            ),
            401: openapi.Response(
                description="Utilisateur non authentifié",
            ),
        },
    )
    def post(self, request):
        refresh_token = (
            request.data.get("refresh")
            or ""
        ).strip()

        if not refresh_token:
            return Response(
                {
                    "error": (
                        "Le refresh token est requis."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()

        except TokenError:
            return Response(
                {
                    "error": (
                        "Le refresh token est invalide, "
                        "expiré ou déjà blacklisté."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "message": (
                    "Déconnexion réussie ✅"
                )
            },
            status=status.HTTP_200_OK,
        )

class ValidateTokenView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "message": "Token valide.",
                "user_id": request.user.pk,
                "role": get_role_name(request.user),
            },
            status=status.HTTP_200_OK,
        )
        


class UserDetailUpdateView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]

    def _get_target_user(self, request, pk):
        target_user = get_object_or_404(
            User.objects.select_related("user_role"),
            pk=pk,
        )

        requester_role = get_role_name(request.user)
        target_role = get_role_name(target_user)

        # L'administrateur a un accès global.
        if requester_role == "admin":
            return target_user

        # Un manager ne peut jamais gérer un administrateur.
        if target_role == "admin":
            raise PermissionDenied(
                "Un manager ne peut pas gérer un administrateur."
            )

        # Le manager ne peut gérer que les utilisateurs
        # rattachés à l'une de ses bijouteries.
        manager_profile = getattr(
            request.user,
            "staff_manager_profile",
            None,
        )

        if not manager_profile or not getattr(
            manager_profile,
            "verifie",
            False,
        ):
            raise PermissionDenied(
                "Profil manager invalide ou désactivé."
            )

        manager_bijouterie_ids = set(
            manager_profile.bijouteries.values_list(
                "id",
                flat=True,
            )
        )

        belongs_to_manager_scope = User.objects.filter(
            pk=target_user.pk,
        ).filter(
            Q(
                vendor_profile__verifie=True,
                vendor_profile__bijouterie_id__in=manager_bijouterie_ids,
            )
            |
            Q(
                cashier_profile__verifie=True,
                cashier_profile__bijouterie_id__in=manager_bijouterie_ids,
            )
            |
            Q(
                buyer_profile__verifie=True,
                buyer_profile__bijouterie_id__in=manager_bijouterie_ids,
            )
            |
            Q(
                manager_profile__verifie=True,
                manager_profile__bijouteries__id__in=manager_bijouterie_ids,
            )
        ).distinct().exists()

        if not belongs_to_manager_scope:
            raise PermissionDenied(
                "Cet utilisateur ne dépend pas "
                "de l'une de vos bijouteries."
            )
            
        return target_user

    
    @swagger_auto_schema(
        operation_summary="Consulter un utilisateur",
        operation_description=(
            "L'administrateur peut consulter tous les utilisateurs. "
            "Un manager peut uniquement consulter les utilisateurs "
            "de ses bijouteries."
        ),
        responses={
            200: UserDetailSerializer,
            403: "Accès refusé",
            404: "Utilisateur introuvable",
        },
    )
    def get(self, request, pk):
        user = self._get_target_user(
            request,
            pk,
        )

        serializer = UserDetailSerializer(
            user,
            context={"request": request},
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_summary="Modifier un utilisateur",
        operation_description=(
            "Modifie les informations générales d'un utilisateur. "
            "Les rôles staff doivent être gérés via l'API Staff."
        ),
        request_body=UserDetailSerializer,
        responses={
            200: UserDetailSerializer,
            400: "Données invalides",
            403: "Accès refusé",
            404: "Utilisateur introuvable",
        },
    )
    def put(self, request, pk):
        user = self._get_target_user(
            request,
            pk,
        )

        serializer = UserDetailSerializer(
            user,
            data=request.data,
            context={"request": request},
        )

        serializer.is_valid(
            raise_exception=True,
        )
        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_summary="Supprimer un utilisateur",
        operation_description=(
            "Supprime un utilisateur. "
            "Un manager ne peut supprimer que les utilisateurs "
            "de ses bijouteries."
        ),
        responses={
            204: "Utilisateur supprimé",
            400: "Suppression interdite",
            403: "Accès refusé",
            404: "Utilisateur introuvable",
        },
    )
    def delete(self, request, pk):
        user = self._get_target_user(
            request,
            pk,
        )

        if user.pk == request.user.pk:
            return Response(
                {
                    "detail": (
                        "Vous ne pouvez pas supprimer "
                        "votre propre compte."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.delete()

        return Response(
            status=status.HTTP_204_NO_CONTENT,
        )
        


# User list
class UsersView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]

    @swagger_auto_schema(
        operation_summary="Lister les utilisateurs",
        operation_description=(
            "L'administrateur voit tous les utilisateurs. "
            "Le manager voit uniquement les utilisateurs rattachés "
            "à ses bijouteries."
        ),
        responses={
            200: UserDetailSerializer(many=True),
            403: "Accès refusé",
        },
    )
    def get(self, request):
        role = get_role_name(request.user)

        queryset = (
            User.objects
            .select_related(
                "user_role",
                "vendor_profile__bijouterie",
                "cashier_profile__bijouterie",
                "buyer_profile__bijouterie",
            )
            .prefetch_related(
                "staff_manager_profile__bijouteries",
            )
            .order_by("-id")
        )

        # Admin : accès global
        if role == "admin":
            users = queryset

        # Manager : uniquement les utilisateurs de ses bijouteries
        elif role == "manager":
            manager_profile = getattr(
                request.user,
                "staff_manager_profile",
                None,
            )

            if not manager_profile or not getattr(
                manager_profile,
                "verifie",
                False,
            ):
                return Response(
                    {
                        "detail": (
                            "Profil manager introuvable "
                            "ou désactivé."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            bijouterie_ids = manager_profile.bijouteries.values_list(
                "id",
                flat=True,
            )

            users = queryset.filter(
                Q(
                    vendor_profile__verifie=True,
                    vendor_profile__bijouterie_id__in=bijouterie_ids,
                )
                |
                Q(
                    cashier_profile__verifie=True,
                    cashier_profile__bijouterie_id__in=bijouterie_ids,
                )
                |
                Q(
                    buyer_profile__verifie=True,
                    buyer_profile__bijouterie_id__in=bijouterie_ids,
                )
                |
                Q(
                    manager_profile__verifie=True,
                    manager_profile__bijouteries__id__in=bijouterie_ids,
                )
            ).distinct()

        else:
            return Response(
                {"detail": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = UserDetailSerializer(
            users,
            many=True,
            context={"request": request},
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
        

class ListRolesAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]

    @swagger_auto_schema(
        operation_summary="Lister les rôles",
        operation_description=(
            "Retourne la liste des rôles système disponibles. "
            "Accès réservé aux administrateurs et managers."
        ),
        responses={
            200: RoleSerializer(many=True),
            403: "Accès refusé",
        },
        manual_parameters=[
            openapi.Parameter(
                "search",
                openapi.IN_QUERY,
                description="Filtrer les rôles par nom",
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
    )
    def get(self, request):
        search = (
            request.query_params.get("search")
            or ""
        ).strip()

        queryset = Role.objects.all().order_by("role")

        if search:
            queryset = queryset.filter(
                role__icontains=search,
            )

        serializer = RoleSerializer(
            queryset,
            many=True,
            context={"request": request},
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )


class CreateRoleAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [
        IsAuthenticated,
        IsAdmin,
    ]

    @swagger_auto_schema(
        operation_summary="Créer un rôle",
        operation_description=(
            "Crée un nouveau rôle personnalisé. "
            "Les noms des rôles système sont réservés. "
            "Accès réservé à l'administrateur."
        ),
        request_body=RoleSerializer,
        responses={
            201: RoleSerializer,
            400: "Données invalides ou nom réservé",
            403: "Accès refusé",
        },
    )
    def post(self, request):
        serializer = RoleSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        role_name = (
            serializer.validated_data.get("role", "")
            or ""
        ).strip().lower()

        if role_name in SYSTEM_ROLES:
            raise ValidationError(
                {
                    "role": (
                        "Ce nom est réservé à un rôle système."
                    )
                }
            )

        role = serializer.save()

        output = RoleSerializer(
            role,
            context={"request": request},
        )

        return Response(
            output.data,
            status=status.HTTP_201_CREATED,
        )
        

class GetOneRoleAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]

    @swagger_auto_schema(
        operation_summary="Récupérer un rôle",
        operation_description=(
            "Retourne un rôle système par son identifiant. "
            "Accès réservé aux administrateurs et managers."
        ),
        responses={
            200: RoleSerializer,
            403: "Accès refusé",
            404: "Rôle introuvable",
        },
    )
    def get(self, request, pk):
        role = get_object_or_404(
            Role,
            pk=pk,
        )

        serializer = RoleSerializer(
            role,
            context={"request": request},
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )


class UpdateRoleAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [
        IsAuthenticated,
        IsAdmin,
    ]

    def get_role(self, pk):
        return get_object_or_404(
            Role,
            pk=pk,
        )

    def ensure_role_is_editable(self, role):
        role_name = (
            getattr(role, "role", "")
            or ""
        ).strip().lower()

        if role_name in SYSTEM_ROLES:
            raise ValidationError(
                {
                    "role": (
                        "Ce rôle système est protégé "
                        "et ne peut pas être modifié."
                    )
                }
            )

    @swagger_auto_schema(
        operation_summary="Modifier complètement un rôle",
        operation_description=(
            "Modifie complètement un rôle personnalisé. "
            "Les rôles système sont protégés. "
            "Accès réservé à l'administrateur."
        ),
        request_body=RoleSerializer,
        responses={
            200: RoleSerializer,
            400: "Données invalides ou rôle protégé",
            403: "Accès refusé",
            404: "Rôle introuvable",
        },
    )
    def put(self, request, pk):
        role = self.get_role(pk)

        self.ensure_role_is_editable(role)

        serializer = RoleSerializer(
            role,
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        new_role_name = (
            serializer.validated_data.get("role", "")
            or ""
        ).strip().lower()

        if new_role_name in SYSTEM_ROLES:
            raise ValidationError(
                {
                    "role": (
                        "Ce nom est réservé à un rôle système."
                    )
                }
            )

        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_summary="Modifier partiellement un rôle",
        operation_description=(
            "Modifie partiellement un rôle personnalisé. "
            "Les rôles système sont protégés. "
            "Accès réservé à l'administrateur."
        ),
        request_body=RoleSerializer,
        responses={
            200: RoleSerializer,
            400: "Données invalides ou rôle protégé",
            403: "Accès refusé",
            404: "Rôle introuvable",
        },
    )
    def patch(self, request, pk):
        role = self.get_role(pk)

        self.ensure_role_is_editable(role)

        serializer = RoleSerializer(
            role,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        if "role" in serializer.validated_data:
            new_role_name = (
                serializer.validated_data["role"]
                or ""
            ).strip().lower()

            if new_role_name in SYSTEM_ROLES:
                raise ValidationError(
                    {
                        "role": (
                            "Ce nom est réservé à un rôle système."
                        )
                    }
                )

        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

class DeleteRoleAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [
        IsAuthenticated,
        IsAdmin,
    ]

    @swagger_auto_schema(
        operation_summary="Supprimer un rôle",
        operation_description=(
            "Supprime un rôle personnalisé. "
            "Les rôles système sont protégés. "
            "Accès réservé à l'administrateur."
        ),
        responses={
            204: "Rôle supprimé",
            400: "Suppression impossible",
            403: "Accès refusé",
            404: "Rôle introuvable",
        },
    )
    def delete(self, request, pk):
        role = get_object_or_404(
            Role,
            pk=pk,
        )

        role_name = (
            getattr(role, "role", "")
            or ""
        ).strip().lower()

        if role_name in SYSTEM_ROLES:
            raise ValidationError(
                {
                    "role": (
                        "Ce rôle système est protégé "
                        "et ne peut pas être supprimé."
                    )
                }
            )

        role.delete()

        return Response(
            status=status.HTTP_204_NO_CONTENT,
        )

# profile
class MyProfileView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [
        MultiPartParser,
        FormParser,
        JSONParser,
    ]

    def get_profile(self, user):
        profile, _ = Profile.objects.get_or_create(
            user=user,
        )
        return profile

    @swagger_auto_schema(
        operation_id="getMyProfile",
        operation_summary="Récupérer mon profil",
        operation_description=(
            "Retourne le profil complet de l'utilisateur connecté, "
            "avec les informations du compte User et du Profile."
        ),
        tags=["Profil utilisateur"],
        responses={
            200: ProfileSerializer,
            401: "Non authentifié",
        },
    )
    def get(self, request):
        profile = self.get_profile(request.user)

        serializer = ProfileSerializer(
            profile,
            context={"request": request},
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_id="updateMyProfilePut",
        operation_summary="Mettre à jour complètement mon profil",
        operation_description=(
            "Met à jour complètement le profil utilisateur connecté. "
            "Supporte aussi multipart/form-data."
        ),
        tags=["Profil utilisateur"],
        request_body=ProfileUpdateSerializer,
        responses={
            200: openapi.Response(
                description="Profil mis à jour avec succès",
            ),
            400: "Données invalides",
            401: "Non authentifié",
        },
    )
    def put(self, request):
        profile = self.get_profile(request.user)

        serializer = ProfileUpdateSerializer(
            profile,
            data=request.data,
            partial=False,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        output = ProfileSerializer(
            profile,
            context={"request": request},
        )

        return Response(
            {
                "message": "Profil mis à jour avec succès.",
                "data": output.data,
            },
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_id="updateMyProfilePatch",
        operation_summary="Mettre à jour partiellement mon profil",
        operation_description=(
            "Met à jour partiellement le profil utilisateur connecté. "
            "Supporte aussi multipart/form-data."
        ),
        tags=["Profil utilisateur"],
        request_body=ProfileUpdateSerializer,
        responses={
            200: openapi.Response(
                description="Profil mis à jour avec succès",
            ),
            400: "Données invalides",
            401: "Non authentifié",
        },
    )
    def patch(self, request):
        profile = self.get_profile(request.user)

        serializer = ProfileUpdateSerializer(
            profile,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        output = ProfileSerializer(
            profile,
            context={"request": request},
        )

        return Response(
            {
                "message": "Profil mis à jour avec succès.",
                "data": output.data,
            },
            status=status.HTTP_200_OK,
        )


class ProfileDetailAdminView(APIView):
    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]

    def get_profile(self, request, user_id):
        requester_role = get_role_name(request.user)

        queryset = Profile.objects.select_related(
            "user",
            "user__user_role",
        )

        if requester_role == "admin":
            return get_object_or_404(
                queryset,
                user_id=user_id,
            )

        manager_profile = getattr(
            request.user,
            "staff_manager_profile",
            None,
        )

        if not manager_profile or not manager_profile.verifie:
            raise PermissionDenied(
                "Profil manager introuvable ou désactivé."
            )

        bijouterie_ids = manager_profile.bijouteries.values_list(
            "id",
            flat=True,
        )

        profile = get_object_or_404(
            queryset,
            user_id=user_id,
        )

        target_user = profile.user
        target_role = get_role_name(target_user)

        if target_role == "admin":
            raise PermissionDenied(
                "Un manager ne peut pas consulter "
                "le profil d'un administrateur."
            )

        belongs_to_manager_scope = User.objects.filter(
            pk=target_user.pk,
        ).filter(
            Q(
                vendor_profile__verifie=True,
                vendor_profile__bijouterie_id__in=bijouterie_ids,
            )
            |
            Q(
                cashier_profile__verifie=True,
                cashier_profile__bijouterie_id__in=bijouterie_ids,
            )
            |
            Q(
                buyer_profile__verifie=True,
                buyer_profile__bijouterie_id__in=bijouterie_ids,
            )
            |
            Q(
                manager_profile__verifie=True,
                manager_profile__bijouteries__id__in=bijouterie_ids,
            )
        ).distinct().exists()

        if not belongs_to_manager_scope:
            raise PermissionDenied(
                "Cet utilisateur ne dépend pas "
                "de l'une de vos bijouteries."
            )

        return profile
    

