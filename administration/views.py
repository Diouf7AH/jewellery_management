from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from administration.models import AdminProfile
from administration.permissions import (IsAdminPrincipal,
                                        IsAdminPrincipalOrSecondaire)
from administration.serializers import (AdminActionResponseSerializer,
                                        AdminProfileSerializer,
                                        CreateAdminSerializer,
                                        DeactivateAdminSerializer,
                                        ReactivateAdminSerializer,
                                        UpdateAdminPermissionsSerializer)
from administration.services.admin_service import (deactivate_admin,
                                                   promote_user_to_admin,
                                                   reactivate_admin,
                                                   update_admin_permissions)

# ============================================================
# HELPERS
# ============================================================

def admin_error_response(exc):
    """
    Convertit les erreurs métier connues en réponses HTTP.

    Les exceptions DRF comme NotFound sont laissées
    à DRF pour conserver leur statut HTTP.
    """

    if isinstance(exc, PermissionError):
        return Response(
            {"detail": str(exc)},
            status=status.HTTP_403_FORBIDDEN,
        )

    return Response(
        {"detail": str(exc)},
        status=status.HTTP_400_BAD_REQUEST,
    )


def admin_success_response(message, profile, http_status=200):
    """
    Réponse standard pour les opérations d'administration.
    """

    return Response(
        {
            "message": message,
            "administrateur": AdminProfileSerializer(
                profile
            ).data,
        },
        status=http_status,
    )


class AdminPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = None


# ============================================================
# 1. CRÉER UN ADMINISTRATEUR SECONDAIRE
# ============================================================

class CreateAdminView(APIView):

    permission_classes = [IsAdminPrincipal]
    http_method_names = ["post", "options"]

    @swagger_auto_schema(
        operation_id="createAdmin",
        operation_summary="Créer un administrateur secondaire",
        operation_description=(
            "Permet à l'administrateur principal de promouvoir "
            "un utilisateur existant en administrateur secondaire.\n\n"
            "### Conditions\n"
            "- Le compte utilisateur doit exister.\n"
            "- Le compte doit être actif.\n"
            "- L'adresse email doit être vérifiée.\n"
            "- Aucun profil staff ou administrateur existant.\n"
            "- L'utilisateur ne doit pas être superuser Django.\n\n"
            "### Droits attribués\n"
            "- Rôle applicatif : `admin`.\n"
            "- Niveau : `secondaire`.\n"
            "- Gestion des bijouteries : `false`.\n"
            "- Consultation des finances : `false`.\n"
            "- Aucun privilège superuser Django.\n\n"
            "Seul l'administrateur principal peut effectuer "
            "cette opération."
        ),
        request_body=CreateAdminSerializer,
        responses={
            201: openapi.Response(
                description="Administrateur secondaire créé",
                schema=AdminActionResponseSerializer(),
            ),
            400: "Erreur de validation",
            403: "Accès refusé",
            409: "Profil déjà existant",
        },
        tags=["Administration"],
    )
    def post(self, request):

        serializer = CreateAdminSerializer(
            data=request.data,
        )

        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data[
            "email"
        ].strip().lower()

        try:
            user = promote_user_to_admin(
                caller_user=request.user,
                email=email,
            )

        except PermissionError as exc:
            return admin_error_response(exc)

        except ValueError as exc:
            message = str(exc)

            conflict = (
                "profil" in message.lower()
                or "déjà" in message.lower()
            )

            return Response(
                {"detail": message},
                status=(
                    status.HTTP_409_CONFLICT
                    if conflict
                    else status.HTTP_400_BAD_REQUEST
                ),
            )

        profile = get_object_or_404(
            AdminProfile.objects.select_related("user"),
            user=user,
            niveau=AdminProfile.Niveau.SECONDAIRE,
        )

        return admin_success_response(
            message="Administrateur secondaire créé avec succès.",
            profile=profile,
            http_status=status.HTTP_201_CREATED,
        )


# ============================================================
# 2. LISTER LES ADMINISTRATEURS
# ============================================================

class ListAdminView(APIView):

    permission_classes = [
        IsAdminPrincipalOrSecondaire,
    ]

    http_method_names = ["get", "options"]

    @swagger_auto_schema(
        operation_id="listAdministrateurs",
        operation_summary="Lister les administrateurs",
        operation_description=(
            "Liste paginée des profils administrateurs.\n\n"
            "Accessible aux administrateurs actifs.\n\n"
            "Filtres disponibles :\n"
            "- `niveau=principal`\n"
            "- `niveau=secondaire`\n"
            "- `verifie=true`\n"
            "- `verifie=false`\n\n"
            "Pagination : 20 administrateurs par page."
        ),
        manual_parameters=[
            openapi.Parameter(
                name="niveau",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                enum=["principal", "secondaire"],
                required=False,
                description="Filtrer par niveau.",
            ),
            openapi.Parameter(
                name="verifie",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_BOOLEAN,
                required=False,
                description="Filtrer les profils actifs ou désactivés.",
            ),
            openapi.Parameter(
                name="page",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="Numéro de page.",
            ),
        ],
        responses={
            200: "Liste paginée des administrateurs",
            400: "Filtre invalide",
            403: "Accès refusé",
        },
        tags=["Administration"],
    )
    def get(self, request):

        queryset = (
            AdminProfile.objects
            .select_related("user")
            .order_by("niveau", "-created_at")
        )

        niveau = (
            request.query_params.get("niveau") or ""
        ).strip().lower()

        if niveau:

            niveaux_autorises = {
                AdminProfile.Niveau.PRINCIPAL,
                AdminProfile.Niveau.SECONDAIRE,
            }

            if niveau not in niveaux_autorises:
                return Response(
                    {"detail": "Niveau invalide."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            queryset = queryset.filter(
                niveau=niveau,
            )

        verifie = request.query_params.get("verifie")

        if verifie is not None:

            valeur = verifie.strip().lower()

            if valeur not in {"true", "false"}:
                return Response(
                    {
                        "detail": (
                            "Le filtre verifie doit être "
                            "'true' ou 'false'."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            queryset = queryset.filter(
                verifie=(valeur == "true"),
            )

        paginator = AdminPagination()

        page = paginator.paginate_queryset(
            queryset,
            request,
            view=self,
        )

        serializer = AdminProfileSerializer(
            page,
            many=True,
        )

        return paginator.get_paginated_response(
            serializer.data,
        )


# ============================================================
# 3. DÉTAIL D'UN ADMINISTRATEUR
# ============================================================

class AdminDetailView(APIView):

    permission_classes = [
        IsAdminPrincipalOrSecondaire,
    ]

    http_method_names = ["get", "options"]

    @swagger_auto_schema(
        operation_id="adminDetail",
        operation_summary="Consulter un administrateur",
        operation_description=(
            "Retourne les informations et les permissions "
            "d'un administrateur.\n\n"
            "Accessible uniquement aux administrateurs actifs."
        ),
        responses={
            200: AdminProfileSerializer(),
            403: "Accès refusé",
            404: "Administrateur introuvable",
        },
        tags=["Administration"],
    )
    def get(self, request, admin_id):

        profile = get_object_or_404(
            AdminProfile.objects.select_related("user"),
            pk=admin_id,
        )

        return Response(
            AdminProfileSerializer(profile).data,
            status=status.HTTP_200_OK,
        )


# ============================================================
# 4. MODIFIER LES PERMISSIONS
# ============================================================

class UpdateAdminView(APIView):

    permission_classes = [IsAdminPrincipal]
    http_method_names = ["patch", "options"]

    @swagger_auto_schema(
        operation_id="updateAdminPermissions",
        operation_summary=(
            "Modifier les permissions d'un administrateur secondaire"
        ),
        operation_description=(
            "Permet à l'administrateur principal de modifier "
            "les permissions d'un administrateur secondaire.\n\n"
            "### Permissions modifiables\n"
            "- `peut_gerer_bijouteries`\n"
            "- `peut_voir_finances`\n\n"
            "Il est impossible de modifier le niveau principal "
            "ou de promouvoir un secondaire via cet endpoint."
        ),
        request_body=UpdateAdminPermissionsSerializer,
        responses={
            200: AdminActionResponseSerializer(),
            400: "Erreur de validation",
            403: "Accès refusé",
            404: "Administrateur introuvable",
        },
        tags=["Administration"],
    )
    def patch(self, request, admin_id):

        serializer = UpdateAdminPermissionsSerializer(
            data=request.data,
        )

        serializer.is_valid(raise_exception=True)

        try:
            profile = update_admin_permissions(
                caller_user=request.user,
                admin_id=admin_id,
                **serializer.validated_data,
            )

        except (PermissionError, ValueError) as exc:
            return admin_error_response(exc)

        return admin_success_response(
            message="Permissions modifiées avec succès.",
            profile=profile,
        )


# ============================================================
# 5. DÉSACTIVER UN ADMINISTRATEUR
# ============================================================

class DeactivateAdminView(APIView):

    permission_classes = [IsAdminPrincipal]
    http_method_names = ["post", "options"]

    @swagger_auto_schema(
        operation_id="deactivateAdmin",
        operation_summary="Désactiver un administrateur secondaire",
        operation_description=(
            "Désactive le profil d'un administrateur secondaire.\n\n"
            "### Règles\n"
            "- Seul le principal peut désactiver un secondaire.\n"
            "- La raison de désactivation est obligatoire.\n"
            "- Le compte utilisateur reste actif.\n"
            "- L'administrateur principal ne peut pas "
            "être désactivé via cet endpoint."
        ),
        request_body=DeactivateAdminSerializer,
        responses={
            200: AdminActionResponseSerializer(),
            400: "Erreur de validation",
            403: "Accès refusé",
            404: "Administrateur introuvable",
        },
        tags=["Administration"],
    )
    def post(self, request, admin_id):

        serializer = DeactivateAdminSerializer(
            data=request.data,
        )

        serializer.is_valid(raise_exception=True)

        try:
            profile = deactivate_admin(
                caller_user=request.user,
                admin_id=admin_id,
                raison=serializer.validated_data[
                    "raison_desactivation"
                ],
            )

        except (PermissionError, ValueError) as exc:
            return admin_error_response(exc)

        return admin_success_response(
            message="Administrateur secondaire désactivé avec succès.",
            profile=profile,
        )


# ============================================================
# 6. RÉACTIVER UN ADMINISTRATEUR
# ============================================================

class ReactivateAdminView(APIView):

    permission_classes = [IsAdminPrincipal]
    http_method_names = ["post", "options"]

    @swagger_auto_schema(
        operation_id="reactivateAdmin",
        operation_summary="Réactiver un administrateur secondaire",
        operation_description=(
            "Réactive le profil d'un administrateur secondaire.\n\n"
            "### Règles\n"
            "- Seul le principal peut réactiver un secondaire.\n"
            "- Le compte utilisateur doit être actif.\n"
            "- Les informations de désactivation "
            "sont réinitialisées."
        ),
        request_body=ReactivateAdminSerializer,
        responses={
            200: AdminActionResponseSerializer(),
            400: "Erreur de validation",
            403: "Accès refusé",
            404: "Administrateur introuvable",
        },
        tags=["Administration"],
    )
    def post(self, request, admin_id):

        try:
            profile = reactivate_admin(
                caller_user=request.user,
                admin_id=admin_id,
            )

        except (PermissionError, ValueError) as exc:
            return admin_error_response(exc)

        return admin_success_response(
            message="Administrateur secondaire réactivé avec succès.",
            profile=profile,
        )

