import logging
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import update_last_login
from django.core.cache import cache
from django.core.paginator import EmptyPage, Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError, RestrictedError
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
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from backend.bijouteries import get_user_bijouteries
from backend.permissions import IsAdmin, IsAdminOrManager
from backend.renderers import UserRenderer
from backend.roles import SYSTEM_ROLES, get_role_name
from store.serializers import BijouterieMiniSerializer

from .models import Profile, Role
from .serializers import (ProfileSerializer, ProfileUpdateSerializer,
                          RoleSerializer, UserDetailSerializer,
                          UserDetailUpdateSerializer, UserLoginSerializer,
                          UserRegistrationSerializer)
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


logger = logging.getLogger(__name__)
User = get_user_model()

MIN_RESEND_INTERVAL = timedelta(minutes=5)
RESEND_SECONDS = int(MIN_RESEND_INTERVAL.total_seconds())

GENERIC_RESEND_MESSAGE = (
    "Si un compte non vérifié existe avec cet email, "
    "un nouveau lien de confirmation sera envoyé."
)


# ============================================================
# HELPERS
# ============================================================

class RegistrationThrottle(AnonRateThrottle):
    scope = "registration"


class VerificationResendThrottle(AnonRateThrottle):
    scope = "verification_resend"


def build_confirmation_urls(request, user):
    token = generate_email_token(user)

    query = urlencode({"token": token})

    confirm_url = request.build_absolute_uri(
        f"{reverse('verify-email')}?{query}"
    )

    home_url = request.build_absolute_uri("/")

    return confirm_url, home_url


def send_verification_message(user, request):
    confirm_url, home_url = build_confirmation_urls(
        request, user
    )

    send_confirmation_email(
        user,
        request=None,
        confirm_url=confirm_url,
        home_url=home_url,
    )


def resend_lock_key(user):
    return f"email-verification-resend:{user.pk}"


def try_resend_verification(user, request):
    """
    Retourne :
        sent       : email envoyé
        cooldown   : délai de sécurité actif
        failed     : échec d'envoi

    Le cache.add() est atomique avec un backend
    compatible, comme Redis.

    En cas d'échec, le verrou est conservé
    temporairement afin de limiter les abus.
    """

    key = resend_lock_key(user)

    acquired = cache.add(
        key,
        "reserved",
        timeout=RESEND_SECONDS,
    )

    if not acquired:
        return "cooldown"

    try:
        send_verification_message(user, request)

    except Exception:
        logger.exception(
            "Échec de l'envoi de confirmation pour user_id=%s",
            user.pk,
        )
        return "failed"

    User.objects.filter(pk=user.pk).update(
        last_confirmation_email_sent=timezone.now()
    )

    return "sent"


# ============================================================
# 1. INSCRIPTION PUBLIQUE
# ============================================================

class UserRegistrationView(APIView):

    permission_classes = [AllowAny]
    throttle_classes = [RegistrationThrottle]

    @swagger_auto_schema(
        operation_summary="Inscription publique",
        operation_description=(
            "Crée un utilisateur sans rôle staff "
            "et lance la confirmation de son email."
        ),
        request_body=UserRegistrationSerializer,
        responses={
            201: "Compte créé",
            400: "Données invalides",
            429: "Trop de demandes",
        },
    )
    def post(self, request, format=None):

        serializer = UserRegistrationSerializer(
            data=request.data,
            context={"request": request},
        )

        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            user = serializer.save(
                user_role=None,
                is_email_verified=False,
                is_active=False,
            )

        # Important :
        # Pour garantir l'envoi après le commit,
        # cette vue doit être exclue d'une transaction
        # ATOMIC_REQUESTS englobante.
        #
        # Si ATOMIC_REQUESTS est activé, appliquer
        # non_atomic_requests au dispatch de cette vue.

        email_status = "sent"

        try:
            send_verification_message(user, request)

            User.objects.filter(pk=user.pk).update(
                last_confirmation_email_sent=timezone.now()
            )

        except Exception:
            logger.exception(
                "Échec de l'email d'inscription user_id=%s",
                user.pk,
            )
            email_status = "failed"

        message = (
            "Inscription réussie. Vérifiez votre email."
            if email_status == "sent"
            else (
                "Compte créé, mais l'email de confirmation "
                "n'a pas pu être envoyé. "
                "Demandez un nouveau lien."
            )
        )

        return Response(
            {
                "message": message,
                "user": {
                    "id": user.pk,
                    "email": user.email,
                    "username": user.username,
                    "telephone": user.telephone,
                    "role": None,
                    "is_active": False,
                    "is_email_verified": False,
                },
                "email_status": email_status,
            },
            status=status.HTTP_201_CREATED,
        )


# ============================================================
# 2. CONFIRMATION EMAIL
# ============================================================

@method_decorator(require_GET, name="dispatch")
class EmailVerificationView(APIView):

    permission_classes = [AllowAny]

    def get(self, request):

        token = request.query_params.get("token")

        if not token:
            return render(
                request,
                "emails/email_invalid.html",
                status=400,
            )

        result = verify_email_token(token) or {}

        token_status = result.get("status")
        user_id = result.get("user_id")
        email = (result.get("email") or "").strip().lower()

        if token_status == "expired":
            return render(
                request,
                "emails/email_expired.html",
                status=410,
            )

        if token_status != "ok" or not user_id or not email:
            return render(
                request,
                "emails/email_invalid.html",
                status=400,
            )

        with transaction.atomic():

            user = (
                User.objects.select_for_update()
                .filter(
                    pk=user_id,
                    email__iexact=email,
                )
                .first()
            )

            if user is None:
                return render(
                    request,
                    "emails/email_invalid.html",
                    status=404,
                )

            # Le compte est déjà vérifié.
            # Ne jamais réactiver automatiquement.
            if user.is_email_verified:
                if not user.is_active:
                    return render(
                        request,
                        "emails/email_invalid.html",
                        status=403,
                    )

            else:
                # Première confirmation uniquement.
                user.is_email_verified = True
                user.is_active = True

                user.save(
                    update_fields=[
                        "is_email_verified",
                        "is_active",
                    ]
                )

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
            status=200,
        )


# ============================================================
# 3. RENVOI VIA API
# ============================================================

class ResendVerificationEmailView(APIView):

    permission_classes = [AllowAny]
    throttle_classes = [VerificationResendThrottle]

    @swagger_auto_schema(
        operation_summary="Renvoyer la confirmation email",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["email"],
            properties={
                "email": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_EMAIL,
                )
            },
        ),
        responses={
            200: "Demande traitée",
            400: "Email manquant",
            429: "Trop de demandes",
        },
    )
    def post(self, request):

        email = (
            request.data.get("email") or ""
        ).strip().lower()

        if not email:
            return Response(
                {"detail": "L'adresse email est requise."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(
            email__iexact=email,
            is_email_verified=False,
        ).first()

        if user is not None:
            try_resend_verification(user, request)

        # Même réponse pour les comptes inexistants,
        # déjà vérifiés, en cooldown ou en échec SMTP.
        return Response(
            {"detail": GENERIC_RESEND_MESSAGE},
            status=status.HTTP_200_OK,
        )


# ============================================================
# 4. FORMULAIRE DE RENVOI
# ============================================================

@require_GET
def resend_confirmation_form(request):
    return render(
        request,
        "emails/resend_confirmation_form.html",
    )


# ============================================================
# 5. RENVOI DEPUIS LE FORMULAIRE
# ============================================================

@csrf_protect
@require_http_methods(["POST"])
def resend_confirmation_submit(request):

    email = (
        request.POST.get("email") or ""
    ).strip().lower()

    if not email:
        messages.error(
            request,
            "Veuillez saisir une adresse email.",
        )
        return redirect("resend-confirmation-form")

    user = User.objects.filter(
        email__iexact=email,
        is_email_verified=False,
    ).first()

    if user is not None:
        try_resend_verification(user, request)

    messages.success(
        request,
        GENERIC_RESEND_MESSAGE,
    )

    return redirect("resend-confirmation-form")

class LoginThrottle(AnonRateThrottle):
    """
    Limite les tentatives de connexion
    pour les utilisateurs anonymes.
    """

    scope = "login"

class UserLoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

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
                    description="Email, nom d'utilisateur ou téléphone",
                ),
                "password": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_PASSWORD,
                    description="Mot de passe",
                ),
            },
        ),
        responses={
            200: openapi.Response(description="Connexion réussie"),
            400: openapi.Response(description="Données invalides"),
            401: openapi.Response(
                description="Identifiants invalides ou compte désactivé"
            ),
            403: openapi.Response(
                description="Adresse email non vérifiée"
            ),
            429: openapi.Response(description="Trop de tentatives"),
        },
    )
    def post(self, request, format=None):
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        identifier = (
            serializer.validated_data.get("user") or ""
        ).strip()
        password = serializer.validated_data["password"]

        user = authenticate(
            request=request,
            username=identifier,
            password=password,
        )

        if user is None:
            return Response(
                {
                    "errors": {
                        "non_field_errors": [
                            "Identifiants invalides ou compte désactivé."
                        ]
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Ne jamais connecter un compte inactif.
        if not user.is_active:
            return Response(
                {
                    "errors": {
                        "non_field_errors": [
                            "Ce compte est désactivé."
                        ]
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Vérifier la confirmation de l'email.
        if not getattr(user, "is_email_verified", False):
            return Response(
                {
                    "message": (
                        "Votre adresse email n'a pas encore été confirmée."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Générer les tokens uniquement après validation.
        tokens = get_tokens_for_user(user)

        # Identifier le rôle effectif.
        role = get_role_name(user)

        # Récupérer les bijouteries accessibles.
        bijouteries = get_user_bijouteries(user)
        bijouteries_data = BijouterieMiniSerializer(
            bijouteries,
            many=True,
        ).data

        bijouterie_unique = (
            bijouteries_data[0]
            if len(bijouteries_data) == 1
            else None
        )

        update_last_login(None, user)

        return Response(
            {
                "refresh": tokens["refresh"],
                "access": tokens["access"],
                "user": {
                    "id": user.pk,
                    "email": user.email,
                    "username": user.username,
                    "telephone": getattr(user, "telephone", None),
                    "role": role,
                    "is_active": user.is_active,
                    "is_email_verified": user.is_email_verified,
                },
                "bijouteries": bijouteries_data,
                "bijouterie_unique": bijouterie_unique,
                "multiple_bijouteries": (
                    len(bijouteries_data) > 1
                ),
                "message": "Connexion réussie",
            },
            status=status.HTTP_200_OK,
        )


class UserLogoutView(APIView):
    """
    Déconnexion sécurisée d'un utilisateur.

    - Authentification obligatoire.
    - Refresh token obligatoire.
    - Vérification du propriétaire du token.
    - Blacklist du refresh token.
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Déconnexion utilisateur",
        operation_description=(
            "Déconnecte l'utilisateur connecté en ajoutant "
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
                description="Déconnexion réussie"
            ),
            400: openapi.Response(
                description="Refresh token invalide ou non autorisé"
            ),
            401: openapi.Response(
                description="Utilisateur non authentifié"
            ),
        },
    )
    def post(self, request):
        refresh_token = request.data.get("refresh")

        if not isinstance(refresh_token, str) or not refresh_token.strip():
            return Response(
                {
                    "error": "Le refresh token est requis."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        refresh_token = refresh_token.strip()

        try:
            token = RefreshToken(refresh_token)

            # Vérifier le propriétaire du refresh token.
            token_user_id = token.get(
                jwt_settings.USER_ID_CLAIM
            )

            connected_user_id = getattr(
                request.user,
                jwt_settings.USER_ID_FIELD,
            )

            if (
                token_user_id is None
                or str(token_user_id) != str(connected_user_id)
            ):
                return Response(
                    {
                        "error": (
                            "Ce refresh token n'appartient pas "
                            "à l'utilisateur connecté."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Invalider le refresh token.
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
                "message": "Déconnexion réussie ✅"
            },
            status=status.HTTP_200_OK,
        )
class ValidateTokenView(APIView):
    """
    Vérifie l'authentification JWT de l'utilisateur.

    Retourne :
    - user_id
    - role
    - is_active
    - is_email_verified
    """

    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Vérifier le token JWT",
        operation_description=(
            "Vérifie que l'access token est valide "
            "et que le compte utilisateur est autorisé."
        ),
        responses={
            200: openapi.Response(
                description="Token valide"
            ),
            401: openapi.Response(
                description="Token invalide, expiré ou manquant"
            ),
            403: openapi.Response(
                description="Compte non autorisé"
            ),
        },
    )
    def get(self, request):
        user = request.user

        if not user.is_active:
            return Response(
                {
                    "detail": "Ce compte est désactivé."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if not getattr(user, "is_email_verified", False):
            return Response(
                {
                    "detail": "Adresse email non vérifiée."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            {
                "message": "Token valide.",
                "user_id": user.pk,
                "role": get_role_name(user),
                "is_active": user.is_active,
                "is_email_verified": user.is_email_verified,
            },
            status=status.HTTP_200_OK,
        )

class UserDetailUpdateView(APIView):
    """
    Consultation, modification et suppression d'utilisateur.

    ADMIN :
        - Consulte tous les utilisateurs.
        - Modifie les informations générales.
        - Peut demander une suppression définitive.

    MANAGER :
        - Profil vérifié obligatoire.
        - Accès limité aux utilisateurs de ses bijouteries.
        - Peut consulter les profils désactivés.
        - Ne peut pas gérer un administrateur.
        - Ne peut pas supprimer définitivement un utilisateur.

    Les rôles, affectations, statuts et permissions
    sont gérés par des API dédiées.
    """

    renderer_classes = [UserRenderer]

    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]

    # ==================================================
    # CHAMPS MODIFIABLES
    # ==================================================

    ALLOWED_UPDATE_FIELDS = {
        "username",
        "telephone",
        "first_name",
        "last_name",
    }

    # ==================================================
    # CONTRÔLE D'ACCÈS
    # ==================================================

    def _get_target_user(self, request, pk):

        target_user = get_object_or_404(
            User.objects.select_related("user_role"),
            pk=pk,
        )

        requester_role = get_role_name(request.user)
        target_role = get_role_name(target_user)

        # ADMIN : accès global
        if requester_role == "admin":
            return target_user

        # Seuls les managers peuvent accéder
        # aux utilisateurs de leurs bijouteries.
        if requester_role != "manager":
            raise PermissionDenied(
                "Accès refusé."
            )

        # related_name du modèle Manager
        manager_profile = getattr(
            request.user,
            "staff_manager_profile",
            None,
        )

        if (
            manager_profile is None
            or not manager_profile.verifie
        ):
            raise PermissionDenied(
                "Profil manager introuvable ou désactivé."
            )

        # Un manager ne peut jamais gérer
        # un administrateur.
        if (
            target_role == "admin"
            or target_user.is_superuser
        ):
            raise PermissionDenied(
                "Un manager ne peut pas gérer "
                "un administrateur."
            )

        bijouterie_ids = list(
            manager_profile.bijouteries.values_list(
                "id",
                flat=True,
            )
        )

        if not bijouterie_ids:
            raise PermissionDenied(
                "Aucune bijouterie affectée à ce manager."
            )

        # Les noms ci-dessous sont les
        # related_query_name des profils staff.
        #
        # On ne filtre pas sur verifie=True,
        # afin d'inclure les profils désactivés.

        belongs_to_manager_scope = (
            User.objects
            .filter(pk=target_user.pk)
            .filter(
                Q(
                    vendor_profile__bijouterie_id__in=bijouterie_ids
                )
                |
                Q(
                    cashier_profile__bijouterie_id__in=bijouterie_ids
                )
                |
                Q(
                    buyer_profile__bijouterie_id__in=bijouterie_ids
                )
                |
                Q(
                    manager_profile__bijouteries__id__in=bijouterie_ids
                )
            )
            .exists()
        )

        if not belongs_to_manager_scope:
            raise PermissionDenied(
                "Cet utilisateur n'appartient pas "
                "à l'une de vos bijouteries."
            )

        return target_user

    # ==================================================
    # GET : CONSULTER UN UTILISATEUR
    # ==================================================

    @swagger_auto_schema(
        operation_summary="Consulter un utilisateur",
        operation_description=(
            "L'administrateur consulte tous les utilisateurs. "
            "Le manager vérifié consulte les utilisateurs "
            "rattachés à ses bijouteries, y compris "
            "les profils staff désactivés."
        ),
        responses={
            200: UserDetailSerializer,
            401: "Authentification requise",
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

    # ==================================================
    # PUT : MODIFIER UN UTILISATEUR
    # ==================================================

    @swagger_auto_schema(
        operation_summary="Modifier un utilisateur",
        operation_description=(
            "Modifie uniquement les informations générales "
            "autorisées. Les rôles, permissions, mots de passe "
            "et affectations staff sont exclus."
        ),
        request_body=UserDetailUpdateSerializer,
        responses={
            200: UserDetailSerializer,
            400: "Données invalides",
            401: "Authentification requise",
            403: "Accès refusé",
            404: "Utilisateur introuvable",
        },
    )
    def put(self, request, pk):

        user = self._get_target_user(
            request,
            pk,
        )

        # Refuser explicitement tout champ
        # non autorisé, même s'il est normalement
        # ignoré par ModelSerializer.

        unknown_fields = (
            set(request.data.keys())
            - self.ALLOWED_UPDATE_FIELDS
        )

        if unknown_fields:
            return Response(
                {
                    "detail": (
                        "Certains champs ne sont pas "
                        "modifiables via cette API."
                    ),
                    "champs_interdits": sorted(
                        unknown_fields
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = UserDetailUpdateSerializer(
            user,
            data=request.data,
            partial=True,
            context={"request": request},
        )

        serializer.is_valid(
            raise_exception=True,
        )

        with transaction.atomic():
            serializer.save()

        output_serializer = UserDetailSerializer(
            user,
            context={"request": request},
        )

        return Response(
            output_serializer.data,
            status=status.HTTP_200_OK,
        )

    # ==================================================
    # DELETE : SUPPRIMER UN UTILISATEUR
    # ==================================================

    @swagger_auto_schema(
        operation_summary="Supprimer un utilisateur",
        operation_description=(
            "Suppression définitive réservée "
            "aux administrateurs. "
            "Les comptes liés à des données protégées "
            "ne peuvent pas être supprimés."
        ),
        responses={
            204: "Utilisateur supprimé",
            400: "Suppression interdite",
            401: "Authentification requise",
            403: "Accès réservé aux administrateurs",
            404: "Utilisateur introuvable",
            409: "Utilisateur lié à des données existantes",
        },
    )
    def delete(self, request, pk):

        if get_role_name(request.user) != "admin":
            raise PermissionDenied(
                "Seul un administrateur peut "
                "supprimer définitivement un utilisateur."
            )

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

        try:
            with transaction.atomic():
                user.delete()

        except (ProtectedError, RestrictedError):
            return Response(
                {
                    "detail": (
                        "Impossible de supprimer cet utilisateur : "
                        "il est lié à des données existantes. "
                        "Utilisez la désactivation du compte "
                        "ou du profil staff."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            status=status.HTTP_204_NO_CONTENT,
        )


class UsersView(APIView):
    """
    Liste paginée des utilisateurs.

    ADMIN :
        - Consulte tous les utilisateurs.

    MANAGER :
        - Profil manager vérifié obligatoire.
        - Consulte les utilisateurs de ses bijouteries.
        - Voit les profils actifs et désactivés.
        - Ne peut pas consulter les administrateurs.

    PAGINATION :
        - DEFAULT_PAGE_SIZE depuis settings.py
        - MAX_PAGE_SIZE depuis settings.py
    """

    renderer_classes = [UserRenderer]

    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]

    @swagger_auto_schema(
        operation_summary="Liste paginée des utilisateurs",
        operation_description=(
            "L'administrateur consulte tous les utilisateurs. "
            "Le manager vérifié consulte les utilisateurs "
            "rattachés à ses bijouteries, y compris les "
            "profils désactivés, sauf les administrateurs."
        ),
        manual_parameters=[
            openapi.Parameter(
                "page",
                openapi.IN_QUERY,
                description="Numéro de page",
                type=openapi.TYPE_INTEGER,
                required=False,
                default=1,
            ),
            openapi.Parameter(
                "page_size",
                openapi.IN_QUERY,
                description="Nombre d'utilisateurs par page",
                type=openapi.TYPE_INTEGER,
                required=False,
                default=50,
            ),
        ],
        responses={
            200: openapi.Response(
                description="Liste paginée des utilisateurs",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "count": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                        ),
                        "page": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                        ),
                        "page_size": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                        ),
                        "total_pages": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                        ),
                        "users": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(
                                type=openapi.TYPE_OBJECT,
                            ),
                        ),
                    },
                ),
            ),
            400: "Paramètres de pagination invalides",
            401: "Authentification requise",
            403: "Accès refusé",
        },
    )
    def get(self, request):
        role = get_role_name(request.user)

        # ==============================================
        # 1. QUERYSET
        # ==============================================

        queryset = (
            User.objects
            .select_related(
                "user_role",
            )
            .order_by("-id")
        )

        # ==============================================
        # 2. ADMIN : ACCÈS GLOBAL
        # ==============================================

        if role == "admin":
            users = queryset

        # ==============================================
        # 3. MANAGER : ACCÈS LIMITÉ
        # ==============================================

        elif role == "manager":

            # related_name du modèle Manager
            manager_profile = getattr(
                request.user,
                "staff_manager_profile",
                None,
            )

            if (
                manager_profile is None
                or not manager_profile.verifie
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

            bijouterie_ids = list(
                manager_profile.bijouteries.values_list(
                    "id",
                    flat=True,
                )
            )

            if not bijouterie_ids:
                users = queryset.none()

            else:
                # related_query_name des modèles staff.
                # On inclut les profils désactivés.

                users = (
                    queryset
                    .filter(
                        Q(
                            vendor_profile__bijouterie_id__in=bijouterie_ids,
                        )
                        |
                        Q(
                            cashier_profile__bijouterie_id__in=bijouterie_ids,
                        )
                        |
                        Q(
                            buyer_profile__bijouterie_id__in=bijouterie_ids,
                        )
                        |
                        Q(
                            manager_profile__bijouteries__id__in=bijouterie_ids,
                        )
                    )
                    .exclude(
                        Q(is_superuser=True)
                        | Q(user_role__role__iexact="admin")
                    )
                    .distinct()
                )

        # ==============================================
        # 4. AUTRES RÔLES
        # ==============================================

        else:
            return Response(
                {"detail": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # ==============================================
        # 5. PAGINATION
        # ==============================================

        default_page_size = getattr(
            settings,
            "DEFAULT_PAGE_SIZE",
            50,
        )

        max_page_size = getattr(
            settings,
            "MAX_PAGE_SIZE",
            100,
        )

        try:
            page = int(
                request.query_params.get("page", 1)
            )

            page_size = int(
                request.query_params.get(
                    "page_size",
                    default_page_size,
                )
            )

        except (TypeError, ValueError):
            return Response(
                {
                    "detail": (
                        "page et page_size doivent "
                        "être des entiers."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if page < 1:
            return Response(
                {
                    "detail": (
                        "Le numéro de page doit être "
                        "supérieur ou égal à 1."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not 1 <= page_size <= max_page_size:
            return Response(
                {
                    "detail": (
                        "page_size doit être compris "
                        f"entre 1 et {max_page_size}."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        paginator = Paginator(
            users,
            page_size,
        )

        try:
            page_obj = paginator.page(page)

        except EmptyPage:
            return Response(
                {"detail": "Page inexistante."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ==============================================
        # 6. SÉRIALISATION
        # ==============================================

        serializer = UserDetailSerializer(
            page_obj.object_list,
            many=True,
            context={"request": request},
        )

        # ==============================================
        # 7. RÉPONSE
        # ==============================================

        return Response(
            {
                "count": paginator.count,
                "page": page_obj.number,
                "page_size": page_size,
                "total_pages": paginator.num_pages,
                "users": serializer.data,
            },
            status=status.HTTP_200_OK,
        )



class ListRolesAPIView(APIView):
    """
    Liste les rôles disponibles dans le système.

    Accès :
        - Admin
        - Manager vérifié

    Fonctionnalités :
        - Liste des rôles
        - Recherche par nom
        - Tri alphabétique
    """

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
        manual_parameters=[
            openapi.Parameter(
                "search",
                openapi.IN_QUERY,
                description="Rechercher un rôle par nom",
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        responses={
            200: RoleSerializer(many=True),
            401: "Authentification requise",
            403: "Accès refusé",
        },
    )
    def get(self, request):
        search = (
            request.query_params.get("search") or ""
        ).strip()

        queryset = Role.objects.all()

        # Recherche insensible à la casse.
        if search:
            queryset = queryset.filter(
                role__icontains=search,
            )

        queryset = queryset.order_by("role")

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
    """
    Création d'un rôle personnalisé.

    Accès :
        Administrateur uniquement.

    Règles :
        - Nom obligatoire.
        - Nom normalisé en minuscules.
        - Aucun doublon, même avec une casse différente.
        - Rôles système réservés.
    """

    renderer_classes = [UserRenderer]

    permission_classes = [
        IsAuthenticated,
        IsAdmin,
    ]

    @swagger_auto_schema(
        operation_summary="Créer un rôle",
        operation_description=(
            "Crée un rôle personnalisé. "
            "Les rôles système sont réservés. "
            "Accès réservé à l'administrateur."
        ),
        request_body=RoleSerializer,
        responses={
            201: RoleSerializer,
            400: "Données invalides ou rôle déjà existant",
            401: "Authentification requise",
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
            serializer.validated_data.get("role") or ""
        ).strip().lower()

        if not role_name:
            raise ValidationError({
                "role": "Le nom du rôle est obligatoire."
            })

        # Interdire les noms réservés.
        system_roles = {
            str(role).strip().lower()
            for role in SYSTEM_ROLES
        }

        if role_name in system_roles:
            raise ValidationError({
                "role": "Ce nom est réservé à un rôle système."
            })

        # Refuser les doublons, quelle que soit la casse.
        if Role.objects.filter(
            role__iexact=role_name
        ).exists():
            raise ValidationError({
                "role": "Un rôle portant ce nom existe déjà."
            })

        # Enregistrer la valeur normalisée.
        serializer.validated_data["role"] = role_name

        try:
            with transaction.atomic():
                role = serializer.save()

        except IntegrityError:
            raise ValidationError({
                "role": (
                    "Impossible de créer ce rôle : "
                    "un rôle portant ce nom existe peut-être déjà."
                )
            })

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

class ProfileView(APIView):
    """
    Gestion du profil personnel de l'utilisateur connecté.

    GET:
        Consulter son profil complet.

    PATCH:
        Modifier ses informations personnelles.

    Sécurité:
        - Authentification obligatoire.
        - Aucun user_id fourni par le client.
        - Impossible de modifier son rôle.
        - Impossible de modifier son statut staff.
        - Impossible de modifier ses bijouteries.
        - Impossible de modifier son email ici.
    """

    renderer_classes = [UserRenderer]

    permission_classes = [IsAuthenticated]

    parser_classes = [
        JSONParser,
        MultiPartParser,
        FormParser,
    ]

    http_method_names = [
        "get",
        "patch",
        "head",
        "options",
    ]

    STAFF_PROFILE_MAP = {
        "manager": "staff_manager_profile",
        "vendor": "staff_vendor_profile",
        "cashier": "staff_cashier_profile",
        "buyer": "staff_buyer_profile",
    }

    # ============================================================
    # PROFIL PERSONNEL
    # ============================================================

    def get_profile(self, user):
        """
        Récupère ou crée le profil personnel.

        Un utilisateur possède au maximum
        un Profile grâce au OneToOneField.
        """

        profile, _ = Profile.objects.get_or_create(
            user=user,
        )

        return profile

    # ============================================================
    # PROFIL STAFF
    # ============================================================

    def get_staff_data(self, user, role):
        """
        Retourne uniquement :
            - id
            - verifie

        Le rôle effectif est déterminé par
        backend.roles.get_role_name().
        """

        profile_attribute = self.STAFF_PROFILE_MAP.get(
            role,
        )

        if not profile_attribute:
            return None

        staff = getattr(
            user,
            profile_attribute,
            None,
        )

        if staff is None:
            return None

        return {
            "id": staff.pk,
            "verifie": bool(staff.verifie),
        }

    # ============================================================
    # BIJOUTERIES ACCESSIBLES
    # ============================================================

    def get_bijouteries_data(self, user):
        """
        Respecte les permissions multi-bijouteries.

        Admin:
            Toutes les bijouteries.

        Manager:
            Bijouteries affectées.

        Vendor / Cashier / Buyer:
            Bijouterie affectée.

        Utilisateur sans rôle:
            Liste vide.

        Aucune information commerciale n'est exposée.
        """

        return list(
            get_user_bijouteries(user)
            .order_by("nom", "pk")
            .values(
                "id",
                "nom",
            )
        )

    # ============================================================
    # CONSTRUCTION DE LA RÉPONSE
    # ============================================================

    def build_profile_response(self, request, profile):
        """
        Structure identique pour GET et PATCH.
        """

        user = request.user

        role = get_role_name(user)

        serializer = ProfileSerializer(
            profile,
            context={
                "request": request,
            },
        )

        return {
            "profile": serializer.data,
            "staff": self.get_staff_data(
                user,
                role,
            ),
            "bijouteries": self.get_bijouteries_data(
                user,
            ),
        }

    # ============================================================
    # GET - CONSULTER MON PROFIL
    # ============================================================

    @swagger_auto_schema(
        operation_summary="Consulter mon profil",
        operation_description=(
            "Retourne le profil personnel de "
            "l'utilisateur connecté, son statut staff "
            "et les bijouteries auxquelles il a accès. "
            "Les informations commerciales des "
            "bijouteries ne sont pas retournées."
        ),
        responses={
            200: openapi.Response(
                description="Profil récupéré avec succès.",
            ),
            401: "Authentification requise.",
        },
    )
    def get(self, request):
        profile = self.get_profile(
            request.user,
        )

        return Response(
            self.build_profile_response(
                request,
                profile,
            ),
            status=status.HTTP_200_OK,
        )

    # ============================================================
    # PATCH - MODIFIER MON PROFIL
    # ============================================================

    @swagger_auto_schema(
        operation_summary="Modifier mon profil",
        operation_description=(
            "Modifie les informations personnelles "
            "de l'utilisateur connecté : prénom, nom, "
            "nom d'utilisateur, téléphone, photo, "
            "biographie et adresse. "
            "Le rôle, l'email, les informations staff "
            "et les bijouteries ne sont pas modifiables."
        ),
        responses={
            200: openapi.Response(
                description="Profil modifié avec succès.",
            ),
            400: "Données invalides.",
            401: "Authentification requise.",
        },
    )
    @transaction.atomic
    def patch(self, request):
        profile = self.get_profile(
            request.user,
        )

        serializer = ProfileUpdateSerializer(
            profile,
            data=request.data,
            partial=True,
            context={
                "request": request,
            },
        )

        serializer.is_valid(
            raise_exception=True,
        )

        profile = serializer.save()

        return Response(
            self.build_profile_response(
                request,
                profile,
            ),
            status=status.HTTP_200_OK,
        )


class ProfileDetailAdminView(APIView):
    """
    Consultation du profil personnel d'un utilisateur.

    Admin :
        Peut consulter tous les utilisateurs.

    Manager :
        Peut consulter uniquement les utilisateurs
        rattachés à ses bijouteries.

    Aucun utilisateur ne peut modifier un profil
    à travers cette vue.
    """

    renderer_classes = [UserRenderer]

    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]

    http_method_names = [
        "get",
        "head",
        "options",
    ]

    STAFF_PROFILE_MAP = {
        "manager": "staff_manager_profile",
        "vendor": "staff_vendor_profile",
        "cashier": "staff_cashier_profile",
        "buyer": "staff_buyer_profile",
    }

    # ============================================================
    # VÉRIFICATION DES PERMISSIONS
    # ============================================================

    def get_profile(self, request, user_id):

        requester_role = get_role_name(request.user)

        queryset = Profile.objects.select_related(
            "user",
            "user__user_role",
        )

        # ADMIN : accès global
        if requester_role == "admin":
            return get_object_or_404(
                queryset,
                user_id=user_id,
            )

        # MANAGER : profil vérifié obligatoire
        if requester_role != "manager":
            raise PermissionDenied(
                "Accès réservé aux administrateurs et managers."
            )

        manager_profile = getattr(
            request.user,
            "staff_manager_profile",
            None,
        )

        if (
            manager_profile is None
            or not manager_profile.verifie
        ):
            raise PermissionDenied(
                "Profil manager introuvable ou désactivé."
            )

        profile = get_object_or_404(
            queryset,
            user_id=user_id,
        )

        target_user = profile.user

        # Un manager ne peut jamais consulter un admin.
        if (
            target_user.is_superuser
            or get_role_name(target_user) == "admin"
        ):
            raise PermissionDenied(
                "Un manager ne peut pas consulter "
                "le profil d'un administrateur."
            )

        # Bijouteries du manager connecté
        bijouterie_ids = (
            manager_profile.bijouteries.values_list(
                "id",
                flat=True,
            )
        )

        # Vérifier l'appartenance aux bijouteries
        belongs_to_manager_scope = (
            User.objects.filter(
                pk=target_user.pk,
            )
            .filter(
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
            )
            .distinct()
            .exists()
        )

        if not belongs_to_manager_scope:
            raise PermissionDenied(
                "Cet utilisateur ne dépend pas "
                "de l'une de vos bijouteries."
            )

        return profile

    # ============================================================
    # INFORMATIONS STAFF
    # ============================================================

    def get_staff_data(self, user):

        role = get_role_name(user)

        attribute = self.STAFF_PROFILE_MAP.get(role)

        if not attribute:
            return None

        staff = getattr(
            user,
            attribute,
            None,
        )

        if staff is None:
            return None

        return {
            "id": staff.pk,
            "verifie": bool(staff.verifie),
        }

    # ============================================================
    # GET - CONSULTER LE PROFIL
    # ============================================================

    @swagger_auto_schema(
        operation_summary=(
            "Consulter le profil d'un utilisateur"
        ),
        operation_description=(
            "L'administrateur peut consulter tous les profils. "
            "Le manager peut consulter uniquement les profils "
            "des utilisateurs rattachés à ses bijouteries."
        ),
        responses={
            200: "Profil récupéré avec succès.",
            401: "Authentification requise.",
            403: "Accès refusé.",
            404: "Profil introuvable.",
        },
    )
    def get(self, request, user_id):

        profile = self.get_profile(
            request,
            user_id,
        )

        user = profile.user

        serializer = ProfileSerializer(
            profile,
            context={
                "request": request,
            },
        )

        # Bijouteries de l'utilisateur consulté,
        # et non du manager connecté.
        #
        # Pour un manager, limiter aussi les informations
        # aux bijouteries qu'il est autorisé à voir.
        bijouteries = get_user_bijouteries(user)

        if get_role_name(request.user) == "manager":
            manager_bijouteries = get_user_bijouteries(
                request.user
            )

            bijouteries = bijouteries.filter(
                pk__in=manager_bijouteries.values("pk")
            )

        bijouteries_data = list(
            bijouteries.values(
                "id",
                "nom",
            )
        )

        return Response(
            {
                "profile": serializer.data,
                "staff": self.get_staff_data(user),
                "bijouteries": bijouteries_data,
            },
            status=status.HTTP_200_OK,
        )
