from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import (Count, DecimalField, ExpressionWrapper, F, Min,
                              Q, Sum, Value)
from django.db.models.functions import Coalesce, ExtractYear, TruncMonth
from django.utils import timezone
# staff/views.py
# staff/views.py
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.permissions import IsAdmin, IsAdminOrManager
from backend.roles import (ROLE_ADMIN, ROLE_BUYER, ROLE_CASHIER, ROLE_MANAGER,
                           ROLE_VENDOR, get_role_name)
from purchase.models import Achat, Lot
from sale.models import Facture, Vente, VenteProduit
from staff.models import Buyer, Cashier, Manager
from staff.serializers import (CreateStaffSerializer,
                               StaffDashboardResponseSerializer,
                               UpdateStaffSerializer)
from staff.services import (create_staff_member, promote_user_to_admin,
                            update_staff_member)
from stock.models import Stock, VendorStock
from vendor.models import Vendor

SINGLE_BIJOUTERIE_ROLES = {
    ROLE_VENDOR,
    ROLE_CASHIER,
    ROLE_BUYER,
}

from sale.models import Facture, Paiement, PaiementLigne, Vente

ZERO = Decimal("0.00")

class CreateStaffView(APIView):
    """
    API unique de création de staff.

    Règles :
    - Admin :
        - Manager
        - Vendor
        - Cashier
        - Buyer

    - Manager :
        - Vendor
        - Cashier

    - Manager :
        - plusieurs bijouteries

    - Vendor / Cashier / Buyer :
        - une seule bijouterie

    - Un staff est toujours créé actif.
    - La désactivation se fait ensuite via UpdateStaffView.
    """

    permission_classes = [IsAdminOrManager]

    @swagger_auto_schema(
        operation_id="createStaff",
        operation_summary="Créer un staff",
        operation_description=(
            "Crée un profil staff pour un utilisateur existant.\n\n"
            "### Règles\n"
            "- L'utilisateur doit déjà avoir créé son compte.\n"
            "- L'utilisateur doit avoir confirmé son email.\n"
            "- L'utilisateur doit être actif.\n"
            "- Un utilisateur ne peut avoir qu'un seul profil staff.\n\n"
            "### Rôles autorisés\n"
            "- Admin : `manager`, `vendor`, `cashier`, `buyer`\n"
            "- Manager : `vendor`, `cashier`\n\n"
            "### Affectation aux bijouteries\n"
            "- Manager : utiliser `bijouteries` avec une liste d'IDs.\n"
            "- Vendor / Cashier / Buyer : utiliser `bijouterie_id`.\n\n"
            "### Statut\n"
            "- Le staff est toujours créé avec `verifie=true`.\n"
            "- La désactivation se fait via l'API de mise à jour du staff."
        ),
        request_body=CreateStaffSerializer,
        responses={
            201: openapi.Response(
                description="Staff créé avec succès",
                examples={
                    "application/json": {
                        "message": "✅ Staff créé avec succès",
                        "staff_type": "vendor",
                        "staff": {
                            "id": 5,
                            "verifie": True,
                            "bijouteries": [
                                {
                                    "id": 1,
                                    "nom": "RIO GOLD Dakar",
                                }
                            ],
                            "created_at": "2026-05-30T20:00:00Z",
                            "updated_at": "2026-05-30T20:00:00Z",
                        },
                        "user": {
                            "id": 12,
                            "email": "vendeur@riogold.com",
                            "first_name": "Moussa",
                            "last_name": "Fall",
                            "telephone": "771234567",
                            "role": "vendor",
                        },
                    }
                },
            ),
            400: openapi.Response(
                description="Erreur de validation",
                examples={
                    "application/json": {
                        "email": [
                            "Aucun utilisateur trouvé avec cet email. "
                            "L'utilisateur doit d'abord créer son compte."
                        ]
                    }
                },
            ),
            403: openapi.Response(
                description="Accès refusé",
                examples={
                    "application/json": {
                        "error": (
                            "Accès réservé aux rôles admin et manager."
                        )
                    }
                },
            ),
            409: openapi.Response(
                description="Conflit métier",
                examples={
                    "application/json": {
                        "error": (
                            "Cet utilisateur possède déjà un profil staff."
                        )
                    }
                },
            ),
        },
        tags=["Staff"],
    )
    def post(self, request):
        serializer = CreateStaffSerializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        data = serializer.validated_data

        try:
            result = create_staff_member(
                caller_user=request.user,
                target_role=data["role"],
                email=data["email"],
                bijouterie=data.get("bijouterie_id"),
                bijouteries=data.get(
                    "bijouteries",
                    [],
                ),
            )

        except PermissionError as exc:
            return Response(
                {
                    "error": str(exc),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        except ValueError as exc:
            message = str(exc)

            if (
                "Aucun utilisateur" in message
                or "confirmer son email" in message
                or "n'est pas actif" in message
            ):
                response_status = (
                    status.HTTP_400_BAD_REQUEST
                )
            else:
                response_status = (
                    status.HTTP_409_CONFLICT
                )

            return Response(
                {
                    "error": message,
                },
                status=response_status,
            )

        staff = result.staff
        user = result.user

        # ====================================================
        # Bijouteries du staff
        # ====================================================

        if result.staff_type == ROLE_MANAGER:
            bijouteries_data = [
                {
                    "id": bijouterie.id,
                    "nom": bijouterie.nom,
                }
                for bijouterie in staff.bijouteries.all()
            ]

        elif result.staff_type in SINGLE_BIJOUTERIE_ROLES:
            bijouterie = getattr(
                staff,
                "bijouterie",
                None,
            )

            bijouteries_data = (
                [
                    {
                        "id": bijouterie.id,
                        "nom": bijouterie.nom,
                    }
                ]
                if bijouterie
                else []
            )

        else:
            return Response(
                {
                    "detail": (
                        "Rôle staff non pris en charge."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ====================================================
        # Réponse
        # ====================================================

        return Response(
            {
                "message": (
                    "✅ Staff créé avec succès"
                ),
                "staff_type": result.staff_type,
                "staff": {
                    "id": staff.id,
                    "verifie": staff.verifie,
                    "bijouteries": (
                        bijouteries_data
                    ),
                    "created_at": (
                        staff.created_at
                    ),
                    "updated_at": (
                        staff.updated_at
                    ),
                },
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "first_name": (
                        user.first_name
                    ),
                    "last_name": (
                        user.last_name
                    ),
                    "telephone": getattr(
                        user,
                        "telephone",
                        None,
                    ),
                    "role": (
                        result.staff_type
                    ),
                },
            },
            status=status.HTTP_201_CREATED,
        )

class CreateAdminView(APIView):
    """
    Attribue le rôle administrateur à un utilisateur existant.

    Règles :
    - Seul un admin peut créer un autre admin.
    - L'utilisateur doit déjà avoir un compte.
    - Le compte doit être actif.
    - L'email doit être confirmé.
    - L'utilisateur ne doit pas déjà avoir un profil staff.
    - Le nouvel admin devient également super-utilisateur Django.
    """

    permission_classes = [IsAdmin]

    @swagger_auto_schema(
        operation_id="createAdmin",
        operation_summary="Créer un administrateur",
        operation_description=(
            "Attribue le rôle `admin` à un utilisateur existant.\n\n"
            "### Règles\n"
            "- L'utilisateur doit déjà avoir créé son compte.\n"
            "- Le compte utilisateur doit être actif.\n"
            "- L'adresse email doit être confirmée.\n"
            "- L'utilisateur ne doit pas déjà posséder un profil "
            "`manager`, `vendor`, `cashier` ou `buyer`.\n"
            "- Seul un administrateur peut créer un autre administrateur.\n\n"

            "### Droits attribués\n"
            "- `user_role = admin`\n"
            "- `is_staff = true`\n"
            "- `is_superuser = true`\n"
            "- `is_active = true`\n\n"

            "### Important\n"
            "Aucun profil `Manager`, `Vendor`, `Cashier` ou `Buyer` "
            "n'est créé."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["email"],
            properties={
                "email": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_EMAIL,
                    description=(
                        "Adresse email de l'utilisateur "
                        "à transformer en administrateur."
                    ),
                    example="admin@example.com",
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="Administrateur créé avec succès",
                examples={
                    "application/json": {
                        "message": "Administrateur créé avec succès.",
                        "user": {
                            "id": 12,
                            "email": "admin@example.com",
                            "role": "admin",
                            "is_staff": True,
                            "is_superuser": True,
                            "is_active": True,
                        },
                    }
                },
            ),
            400: openapi.Response(
                description="Erreur de validation",
                examples={
                    "application/json": {
                        "detail": "Utilisateur introuvable."
                    }
                },
            ),
            403: openapi.Response(
                description="Accès refusé",
                examples={
                    "application/json": {
                        "detail": (
                            "Seul un administrateur peut créer "
                            "un autre administrateur."
                        )
                    }
                },
            ),
            409: openapi.Response(
                description="Conflit métier",
                examples={
                    "application/json": {
                        "detail": (
                            "Cet utilisateur possède déjà "
                            "un profil staff."
                        )
                    }
                },
            ),
        },
        tags=["Staff"],
    )
    def post(self, request):
        email = (
            request.data.get("email") or ""
        ).strip().lower()

        if not email:
            return Response(
                {
                    "detail": (
                        "L'adresse email est obligatoire."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = promote_user_to_admin(
                caller_user=request.user,
                email=email,
            )

        except PermissionError as exc:
            return Response(
                {
                    "detail": str(exc),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        except ValueError as exc:
            message = str(exc)

            if "profil staff" in message.lower():
                response_status = (
                    status.HTTP_409_CONFLICT
                )
            else:
                response_status = (
                    status.HTTP_400_BAD_REQUEST
                )

            return Response(
                {
                    "detail": message,
                },
                status=response_status,
            )

        return Response(
            {
                "message": (
                    "Administrateur créé avec succès."
                ),
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "role": ROLE_ADMIN,
                    "is_staff": user.is_staff,
                    "is_superuser": user.is_superuser,
                    "is_active": user.is_active,
                },
            },
            status=status.HTTP_200_OK,
        )
        

class UpdateStaffView(APIView):
    """
    API unique de mise à jour de staff.

    Règles :
    - Admin :
        - Manager
        - Vendor
        - Cashier
        - Buyer

    - Manager :
        - Vendor
        - Cashier
        - uniquement dans ses bijouteries

    - Manager :
        - plusieurs bijouteries

    - Vendor / Cashier / Buyer :
        - une seule bijouterie

    - La désactivation agit uniquement sur le profil staff.
    - raison_desactivation est obligatoire si verifie=False.
    """

    permission_classes = [IsAdminOrManager]

    @swagger_auto_schema(
        operation_id="updateStaff",
        operation_summary=(
            "Mettre à jour un staff "
            "(manager, vendeur, caissier, responsable rachat)"
        ),
        operation_description=(
            "Met à jour un profil staff existant.\n\n"
            "### Règles d'accès\n"
            "- Admin : `manager`, `vendor`, `cashier`, `buyer`\n"
            "- Manager : seulement `vendor` et `cashier` "
            "de ses bijouteries\n"
            "- Manager : ne peut pas modifier un autre manager\n\n"

            "### Affectation aux bijouteries\n"
            "- Manager : utiliser `bijouteries`\n"
            "- Vendor / Cashier / Buyer : utiliser `bijouterie_nom`\n\n"

            "### Désactivation\n"
            "- `verifie=false` nécessite `raison_desactivation`\n"
            "- `verifie=true` réactive le profil staff\n"
            "- Le compte utilisateur reste actif\n"
        ),
        manual_parameters=[
            openapi.Parameter(
                name="staff_id",
                in_=openapi.IN_PATH,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="ID du profil staff à mettre à jour",
            )
        ],
        request_body=UpdateStaffSerializer,
        responses={
            200: openapi.Response(
                description="Staff mis à jour avec succès",
            ),
            400: openapi.Response(
                description="Erreur de validation",
            ),
            403: openapi.Response(
                description="Accès refusé",
            ),
            404: openapi.Response(
                description="Staff introuvable",
            ),
            409: openapi.Response(
                description="Conflit métier",
            ),
        },
        tags=["Staff"],
    )
    def put(self, request, staff_id):
        role = (
            request.data.get("role") or ""
        ).strip().lower()

        user_id = self._get_target_user_id(
            role,
            staff_id,
        )

        serializer = UpdateStaffSerializer(
            data=request.data,
            context={
                "user_id": user_id,
            },
        )

        serializer.is_valid(
            raise_exception=True,
        )

        data = serializer.validated_data

        try:
            result = update_staff_member(
                caller_user=request.user,
                staff_id=staff_id,
                target_role=data["role"],
                email=data.get("email"),
                first_name=data.get("first_name"),
                last_name=data.get("last_name"),
                bijouterie=data.get("bijouterie_nom"),
                bijouteries=data.get("bijouteries"),
                verifie=data.get("verifie"),
                raison_desactivation=data.get(
                    "raison_desactivation"
                ),
            )

        except PermissionError as exc:
            return Response(
                {
                    "error": str(exc),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        except ValueError as exc:
            message = str(exc)

            if "introuvable" in message.lower():
                response_status = (
                    status.HTTP_404_NOT_FOUND
                )
            else:
                response_status = (
                    status.HTTP_409_CONFLICT
                )

            return Response(
                {
                    "error": message,
                },
                status=response_status,
            )

        staff = result.staff
        user = result.user

        # ====================================================
        # Bijouteries
        # ====================================================

        if result.staff_type == ROLE_MANAGER:
            bijouteries_data = [
                {
                    "id": bijouterie.id,
                    "nom": bijouterie.nom,
                }
                for bijouterie in staff.bijouteries.all()
            ]

        elif result.staff_type in SINGLE_BIJOUTERIE_ROLES:
            bijouterie = getattr(
                staff,
                "bijouterie",
                None,
            )

            bijouteries_data = (
                [
                    {
                        "id": bijouterie.id,
                        "nom": bijouterie.nom,
                    }
                ]
                if bijouterie
                else []
            )

        else:
            return Response(
                {
                    "detail": (
                        "Rôle staff non pris en charge."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ====================================================
        # Réponse
        # ====================================================

        return Response(
            {
                "message": (
                    "✅ Staff mis à jour avec succès"
                ),
                "staff_type": result.staff_type,
                "staff": {
                    "id": staff.id,
                    "verifie": staff.verifie,
                    "raison_desactivation": (
                        staff.raison_desactivation
                    ),
                    "bijouteries": bijouteries_data,
                    "created_at": staff.created_at,
                    "updated_at": staff.updated_at,
                },
                "user": {
                    "id": (
                        user.id
                        if user
                        else None
                    ),
                    "email": (
                        user.email
                        if user
                        else None
                    ),
                    "first_name": (
                        user.first_name
                        if user
                        else ""
                    ),
                    "last_name": (
                        user.last_name
                        if user
                        else ""
                    ),
                    "role": result.staff_type,
                },
            },
            status=status.HTTP_200_OK,
        )

    def _get_target_user_id(
        self,
        role,
        staff_id,
    ):
        MODEL_MAP = {
            ROLE_MANAGER: Manager,
            ROLE_VENDOR: Vendor,
            ROLE_CASHIER: Cashier,
            ROLE_BUYER: Buyer,
        }

        Model = MODEL_MAP.get(role)

        if not Model:
            return None

        obj = (
            Model.objects
            .select_related("user")
            .filter(pk=staff_id)
            .first()
        )

        return getattr(
            obj,
            "user_id",
            None,
        )


class ListStaffView(APIView):
    """
    GET /api/staff/list/

    Liste unifiée des staff :
    - manager
    - vendor
    - cashier
    """
    permission_classes = [IsAdminOrManager]

    @swagger_auto_schema(
        operation_id="listStaff",
        operation_summary="Lister tous les staff",
        operation_description=(
            "Retourne une liste unifiée des profils staff.\n\n"
            "- Admin : voit tous les staff\n"
            "- Manager : voit uniquement les staff de ses bijouteries\n\n"
            "Filtres disponibles :\n"
            "- role : manager, vendor, cashier\n"
            "- bijouterie_nom : recherche par nom de bijouterie\n"
            "- email : recherche par email utilisateur\n"
        ),
        manual_parameters=[
            openapi.Parameter(
                name="role",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                enum=[ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER],
                required=False,
                description="Filtrer par type de staff",
            ),
            openapi.Parameter(
                name="bijouterie_nom",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
                description="Filtrer par nom de bijouterie",
            ),
            openapi.Parameter(
                name="email",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
                description="Filtrer par email utilisateur",
            ),
        ],
        responses={
            200: openapi.Response(
                description="Liste unifiée des staff",
                examples={
                    "application/json": [
                        {
                            "staff_id": 3,
                            "role": "vendor",
                            "user_id": 15,
                            "email": "vendeur@example.com",
                            "first_name": "Jean",
                            "last_name": "Dupont",
                            "verifie": True,
                            "raison_desactivation": None,
                            "bijouteries": [
                                {
                                    "id": 2,
                                    "nom": "Rio-Gold"
                                }
                            ],
                            "created_at": "2026-04-01T10:15:00Z",
                            "updated_at": "2026-04-01T10:15:00Z"
                        },
                        {
                            "staff_id": 7,
                            "role": "manager",
                            "user_id": 22,
                            "email": "manager@example.com",
                            "first_name": "Awa",
                            "last_name": "Diop",
                            "verifie": True,
                            "raison_desactivation": None,
                            "bijouteries": [
                                {
                                    "id": 1,
                                    "nom": "RIO GOLD Dakar"
                                },
                                {
                                    "id": 2,
                                    "nom": "RIO GOLD Thiès"
                                }
                            ],
                            "created_at": "2026-04-01T11:00:00Z",
                            "updated_at": "2026-04-01T11:30:00Z"
                        }
                    ]
                },
            ),
            403: openapi.Response(
                description="Accès refusé",
                examples={
                    "application/json": {
                        "detail": "Accès réservé aux rôles admin et manager."
                    }
                },
            ),
        },
        tags=["Staff"],
    )
    def get(self, request):
        caller_role = get_role_name(request.user)

        if caller_role not in (ROLE_ADMIN, ROLE_MANAGER):
            return Response(
                {"detail": "Accès réservé aux rôles admin et manager."},
                status=status.HTTP_403_FORBIDDEN,
            )

        role_filter = (request.GET.get("role") or "").strip().lower()
        bijouterie_nom = (request.GET.get("bijouterie_nom") or "").strip()
        email = (request.GET.get("email") or "").strip()

        if role_filter and role_filter not in {
            ROLE_MANAGER,
            ROLE_VENDOR,
            ROLE_CASHIER,
            ROLE_BUYER,
        }:
            return Response(
                {"detail": "Rôle invalide."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        items = []

        manager_bj_ids = []

        if caller_role == ROLE_MANAGER:
            manager_profile = (
                Manager.objects
                .prefetch_related("bijouteries")
                .filter(user=request.user, verifie=True)
                .first()
            )

            if not manager_profile:
                return Response([], status=status.HTTP_200_OK)

            manager_bj_ids = list(
                manager_profile.bijouteries.values_list("id", flat=True)
            )

            if not manager_bj_ids:
                return Response([], status=status.HTTP_200_OK)

        def serialize_manager_queryset(qs):
            rows = []

            for obj in qs.select_related("user").prefetch_related("bijouteries"):
                user = getattr(obj, "user", None)

                bijouteries_data = [
                    {
                        "id": b.id,
                        "nom": b.nom,
                    }
                    for b in obj.bijouteries.all()
                ]

                rows.append({
                    "staff_id": obj.id,
                    "role": ROLE_MANAGER,
                    "user_id": getattr(user, "id", None),
                    "email": getattr(user, "email", None),
                    "first_name": getattr(user, "first_name", "") or "",
                    "last_name": getattr(user, "last_name", "") or "",
                    "verifie": obj.verifie,
                    "raison_desactivation": obj.raison_desactivation,
                    "bijouteries": bijouteries_data,
                    "created_at": obj.created_at,
                    "updated_at": obj.updated_at,
                })

            return rows

        def serialize_single_bijouterie_queryset(qs, role_name):
            rows = []

            for obj in qs.select_related("user", "bijouterie"):
                user = getattr(obj, "user", None)
                bj = getattr(obj, "bijouterie", None)

                rows.append({
                    "staff_id": obj.id,
                    "role": role_name,
                    "user_id": getattr(user, "id", None),
                    "email": getattr(user, "email", None),
                    "first_name": getattr(user, "first_name", "") or "",
                    "last_name": getattr(user, "last_name", "") or "",
                    "verifie": obj.verifie,
                    "raison_desactivation": obj.raison_desactivation,
                    "bijouteries": [
                        {
                            "id": bj.id,
                            "nom": bj.nom,
                        }
                    ] if bj else [],
                    "created_at": obj.created_at,
                    "updated_at": obj.updated_at,
                })

            return rows

        if role_filter in ("", ROLE_MANAGER):
            qs_manager = Manager.objects.all()

            if caller_role == ROLE_MANAGER:
                qs_manager = qs_manager.filter(
                    bijouteries__id__in=manager_bj_ids
                ).distinct()

            if bijouterie_nom:
                qs_manager = qs_manager.filter(
                    bijouteries__nom__icontains=bijouterie_nom
                ).distinct()

            if email:
                qs_manager = qs_manager.filter(
                    user__email__icontains=email
                )

            items.extend(serialize_manager_queryset(qs_manager))

        if role_filter in ("", ROLE_VENDOR):
            qs_vendor = Vendor.objects.all()

            if caller_role == ROLE_MANAGER:
                qs_vendor = qs_vendor.filter(
                    bijouterie__id__in=manager_bj_ids
                )

            if bijouterie_nom:
                qs_vendor = qs_vendor.filter(
                    bijouterie__nom__icontains=bijouterie_nom
                )

            if email:
                qs_vendor = qs_vendor.filter(
                    user__email__icontains=email
                )

            items.extend(
                serialize_single_bijouterie_queryset(
                    qs_vendor,
                    ROLE_VENDOR,
                )
            )

        if role_filter in ("", ROLE_CASHIER):
            qs_cashier = Cashier.objects.all()

            if caller_role == ROLE_MANAGER:
                qs_cashier = qs_cashier.filter(
                    bijouterie__id__in=manager_bj_ids
                )

            if bijouterie_nom:
                qs_cashier = qs_cashier.filter(
                    bijouterie__nom__icontains=bijouterie_nom
                )

            if email:
                qs_cashier = qs_cashier.filter(
                    user__email__icontains=email
                )

            items.extend(
                serialize_single_bijouterie_queryset(
                    qs_cashier,
                    ROLE_CASHIER,
                )
            )

        items.sort(key=lambda x: x["created_at"], reverse=True)

        return Response(items, status=status.HTTP_200_OK)


class StaffDetailView(APIView):
    """
    GET /api/staff/<role>/<staff_id>/

    - admin   : peut voir manager, vendor, cashier
    - manager : peut voir seulement vendor et cashier de ses bijouteries
    """
    permission_classes = [IsAdminOrManager]

    MODEL_MAP = {
        ROLE_MANAGER: Manager,
        ROLE_VENDOR: Vendor,
        ROLE_CASHIER: Cashier,
        ROLE_BUYER: Buyer,
    }

    @swagger_auto_schema(
        operation_id="staffDetail",
        operation_summary="Détail d'un staff",
        operation_description=(
            "Retourne le détail complet d'un staff.\n\n"
            "### URL\n"
            "- `GET /api/staff/<role>/<staff_id>`\n\n"
            "### Exemples\n"
            "- `GET /api/staff/vendor/5`\n"
            "- `GET /api/staff/cashier/8`\n"
            "- `GET /api/staff/manager/2`\n\n"
            "### Règles d'accès\n"
            "- **Admin** : accès à tous les staff\n"
            "- **Manager** : accès seulement aux `vendor` et `cashier` de ses bijouteries\n"
            "- **Manager** : pas d'accès au détail d'un autre manager\n"
        ),
        manual_parameters=[
            openapi.Parameter(
                name="role",
                in_=openapi.IN_PATH,
                type=openapi.TYPE_STRING,
                enum=[ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER],
                required=True,
                description="Type de staff",
            ),
            openapi.Parameter(
                name="staff_id",
                in_=openapi.IN_PATH,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="ID du staff",
            ),
        ],
        responses={
            200: openapi.Response(
                description="Détail du staff",
                examples={
                    "application/json": {
                        "staff_id": 5,
                        "role": "vendor",
                        "user": {
                            "id": 21,
                            "email": "vendeur@example.com",
                            "first_name": "Jean",
                            "last_name": "Dupont",
                            "role": "vendor",
                        },
                        "staff": {
                            "id": 5,
                            "verifie": True,
                            "raison_desactivation": "",
                            "bijouteries": [
                                {
                                    "id": 2,
                                    "nom": "Rio-Gold Centre",
                                }
                            ],
                            "created_at": "2026-04-01T09:00:00Z",
                            "updated_at": "2026-04-01T10:15:00Z",
                        },
                    }
                },
            ),
            403: openapi.Response(
                description="Accès refusé",
                examples={
                    "application/json": {
                        "detail": "Accès refusé."
                    }
                },
            ),
            404: openapi.Response(
                description="Staff introuvable",
                examples={
                    "application/json": {
                        "detail": "Staff introuvable."
                    }
                },
            ),
        },
        tags=["Staff"],
    )
    def get(self, request, role, staff_id):
        role = (role or "").strip().lower()

        Model = self.MODEL_MAP.get(role)
        if not Model:
            return Response(
                {"detail": "Rôle invalide."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        caller_role = get_role_name(request.user)

        if caller_role not in (ROLE_ADMIN, ROLE_MANAGER):
            return Response(
                {"detail": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if role == ROLE_MANAGER:
            staff = (
                Manager.objects
                .select_related("user")
                .prefetch_related("bijouteries")
                .filter(pk=staff_id)
                .first()
            )

        elif role in SINGLE_BIJOUTERIE_ROLES:
            staff = (
                Model.objects
                .select_related("user", "bijouterie")
                .filter(pk=staff_id)
                .first()
            )

        else:
            return Response(
                {"detail": "Rôle staff non pris en charge."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not staff:
            return Response(
                {"detail": "Staff introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if caller_role == ROLE_MANAGER:
            manager_profile = (
                Manager.objects
                .prefetch_related("bijouteries")
                .filter(user=request.user, verifie=True)
                .first()
            )

            if not manager_profile:
                return Response(
                    {"detail": "Profil manager introuvable."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if role == ROLE_MANAGER:
                return Response(
                    {"detail": "Un manager ne peut pas consulter le détail d'un autre manager."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            bj_id = getattr(staff, "bijouterie_id", None)

            if not bj_id or not manager_profile.bijouteries.filter(id=bj_id).exists():
                return Response(
                    {"detail": "Vous ne pouvez consulter que les staff de vos bijouteries."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        user = getattr(staff, "user", None)

        if role == ROLE_MANAGER:
            bijouteries_data = [
                {
                    "id": b.id,
                    "nom": b.nom,
                }
                for b in staff.bijouteries.all()
            ]
        else:
            bj = getattr(staff, "bijouterie", None)
            bijouteries_data = [
                {
                    "id": bj.id,
                    "nom": bj.nom,
                }
            ] if bj else []

        payload = {
            "staff_id": staff.id,
            "role": role,
            "user": {
                "id": getattr(user, "id", None),
                "email": getattr(user, "email", None),
                "first_name": getattr(user, "first_name", "") or "",
                "last_name": getattr(user, "last_name", "") or "",
                "role": role,
            },
            "staff": {
                "id": staff.id,
                "verifie": staff.verifie,
                "raison_desactivation": staff.raison_desactivation,
                "bijouteries": bijouteries_data,
                "created_at": staff.created_at,
                "updated_at": staff.updated_at,
            },
        }

        return Response(payload, status=status.HTTP_200_OK)


class StaffDashboardView(APIView):
    """
    Dashboard global des staff.

    Règles :
    - Admin : voit tous les staff de toutes les bijouteries.
    - Manager : voit les staff rattachés à ses bijouteries.
    """

    permission_classes = [IsAdminOrManager]

    @swagger_auto_schema(
        operation_id="staffDashboard",
        operation_summary="Dashboard des staff",
        operation_description=(
            "Retourne le dashboard global des profils staff.\n\n"
            "### Visibilité\n"
            "- Admin : voit tous les managers, vendeurs, caissiers et "
            "responsables rachats.\n"
            "- Manager : voit uniquement les profils staff rattachés à "
            "ses bijouteries.\n\n"
            "### Réponse\n"
            "- `summary` : compteurs globaux\n"
            "- `by_bijouterie` : répartition des staff par bijouterie\n"
            "- `recent_staff` : 10 derniers profils staff créés\n"
        ),
        responses={
            200: StaffDashboardResponseSerializer(),
        },
        tags=["Staff"],
    )
    def get(self, request):
        caller_role = get_role_name(request.user)

        if caller_role not in {
            ROLE_ADMIN,
            ROLE_MANAGER,
        }:
            return Response(
                {
                    "detail": (
                        "Accès réservé aux rôles admin et manager."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        empty_payload = {
            "summary": {
                "managers_count": 0,
                "vendors_count": 0,
                "cashiers_count": 0,
                "buyers_count": 0,
                "verified_count": 0,
                "disabled_count": 0,
            },
            "by_bijouterie": [],
            "recent_staff": [],
        }

        manager_bijouterie_ids = []

        # ====================================================
        # Périmètre du manager
        # ====================================================

        if caller_role == ROLE_MANAGER:
            manager_profile = (
                Manager.objects
                .prefetch_related("bijouteries")
                .filter(
                    user=request.user,
                    verifie=True,
                )
                .first()
            )

            if not manager_profile:
                serializer = StaffDashboardResponseSerializer(
                    empty_payload
                )

                return Response(
                    serializer.data,
                    status=status.HTTP_200_OK,
                )

            manager_bijouterie_ids = list(
                manager_profile.bijouteries.values_list(
                    "id",
                    flat=True,
                )
            )

            if not manager_bijouterie_ids:
                serializer = StaffDashboardResponseSerializer(
                    empty_payload
                )

                return Response(
                    serializer.data,
                    status=status.HTTP_200_OK,
                )

        # ====================================================
        # Querysets de base
        # ====================================================

        managers_qs = (
            Manager.objects
            .select_related("user")
            .prefetch_related("bijouteries")
        )

        vendors_qs = (
            Vendor.objects
            .select_related(
                "user",
                "bijouterie",
            )
        )

        cashiers_qs = (
            Cashier.objects
            .select_related(
                "user",
                "bijouterie",
            )
        )

        buyers_qs = (
            Buyer.objects
            .select_related(
                "user",
                "bijouterie",
            )
        )

        # ====================================================
        # Filtrage selon les bijouteries du manager
        # ====================================================

        if caller_role == ROLE_MANAGER:
            managers_qs = (
                managers_qs
                .filter(
                    bijouteries__id__in=manager_bijouterie_ids
                )
                .distinct()
            )

            vendors_qs = vendors_qs.filter(
                bijouterie_id__in=manager_bijouterie_ids
            )

            cashiers_qs = cashiers_qs.filter(
                bijouterie_id__in=manager_bijouterie_ids
            )

            buyers_qs = buyers_qs.filter(
                bijouterie_id__in=manager_bijouterie_ids
            )

        # ====================================================
        # Compteurs globaux
        # ====================================================

        managers_count = managers_qs.count()
        vendors_count = vendors_qs.count()
        cashiers_count = cashiers_qs.count()
        buyers_count = buyers_qs.count()

        verified_count = sum([
            managers_qs.filter(verifie=True).count(),
            vendors_qs.filter(verifie=True).count(),
            cashiers_qs.filter(verifie=True).count(),
            buyers_qs.filter(verifie=True).count(),
        ])

        disabled_count = sum([
            managers_qs.filter(verifie=False).count(),
            vendors_qs.filter(verifie=False).count(),
            cashiers_qs.filter(verifie=False).count(),
            buyers_qs.filter(verifie=False).count(),
        ])

        summary = {
            "managers_count": managers_count,
            "vendors_count": vendors_count,
            "cashiers_count": cashiers_count,
            "buyers_count": buyers_count,
            "verified_count": verified_count,
            "disabled_count": disabled_count,
        }

        # ====================================================
        # Répartition des staff par bijouterie
        # ====================================================

        by_bijouterie_map = {}

        def ensure_bijouterie_row(
            bijouterie_id,
            bijouterie_nom,
        ):
            return by_bijouterie_map.setdefault(
                bijouterie_id,
                {
                    "bijouterie_id": bijouterie_id,
                    "bijouterie_nom": bijouterie_nom,
                    "managers_count": 0,
                    "vendors_count": 0,
                    "cashiers_count": 0,
                    "buyers_count": 0,
                },
            )

        # Managers
        managers_grouped = (
            managers_qs
            .values(
                "bijouteries__id",
                "bijouteries__nom",
            )
            .annotate(
                managers_count=Count(
                    "id",
                    distinct=True,
                )
            )
            .order_by("bijouteries__nom")
        )

        for row in managers_grouped:
            bijouterie_id = row["bijouteries__id"]
            bijouterie_nom = row["bijouteries__nom"]

            if bijouterie_id is None:
                continue

            item = ensure_bijouterie_row(
                bijouterie_id,
                bijouterie_nom,
            )

            item["managers_count"] = (
                row["managers_count"] or 0
            )

        # Vendeurs
        vendors_grouped = (
            vendors_qs
            .values(
                "bijouterie_id",
                "bijouterie__nom",
            )
            .annotate(
                vendors_count=Count("id")
            )
            .order_by("bijouterie__nom")
        )

        for row in vendors_grouped:
            bijouterie_id = row["bijouterie_id"]
            bijouterie_nom = row["bijouterie__nom"]

            if bijouterie_id is None:
                continue

            item = ensure_bijouterie_row(
                bijouterie_id,
                bijouterie_nom,
            )

            item["vendors_count"] = (
                row["vendors_count"] or 0
            )

        # Caissiers
        cashiers_grouped = (
            cashiers_qs
            .values(
                "bijouterie_id",
                "bijouterie__nom",
            )
            .annotate(
                cashiers_count=Count("id")
            )
            .order_by("bijouterie__nom")
        )

        for row in cashiers_grouped:
            bijouterie_id = row["bijouterie_id"]
            bijouterie_nom = row["bijouterie__nom"]

            if bijouterie_id is None:
                continue

            item = ensure_bijouterie_row(
                bijouterie_id,
                bijouterie_nom,
            )

            item["cashiers_count"] = (
                row["cashiers_count"] or 0
            )

        # Responsables rachats
        buyers_grouped = (
            buyers_qs
            .values(
                "bijouterie_id",
                "bijouterie__nom",
            )
            .annotate(
                buyers_count=Count("id")
            )
            .order_by("bijouterie__nom")
        )

        for row in buyers_grouped:
            bijouterie_id = row["bijouterie_id"]
            bijouterie_nom = row["bijouterie__nom"]

            if bijouterie_id is None:
                continue

            item = ensure_bijouterie_row(
                bijouterie_id,
                bijouterie_nom,
            )

            item["buyers_count"] = (
                row["buyers_count"] or 0
            )

        by_bijouterie = sorted(
            by_bijouterie_map.values(),
            key=lambda item: (
                item["bijouterie_nom"] or ""
            ).lower(),
        )

        # ====================================================
        # Staff récemment créés
        # ====================================================

        recent_staff = []

        for manager in managers_qs.order_by("-created_at")[:10]:
            user = getattr(manager, "user", None)

            recent_staff.append({
                "staff_id": manager.id,
                "role": ROLE_MANAGER,
                "email": getattr(user, "email", None),
                "first_name": (
                    getattr(user, "first_name", "") or ""
                ),
                "last_name": (
                    getattr(user, "last_name", "") or ""
                ),
                "verifie": manager.verifie,
                "bijouteries": [
                    {
                        "id": bijouterie.id,
                        "nom": bijouterie.nom,
                    }
                    for bijouterie in manager.bijouteries.all()
                ],
                "created_at": manager.created_at,
            })

        single_bijouterie_querysets = (
            (vendors_qs, ROLE_VENDOR),
            (cashiers_qs, ROLE_CASHIER),
            (buyers_qs, ROLE_BUYER),
        )

        for queryset, role_name in single_bijouterie_querysets:
            for staff in queryset.order_by("-created_at")[:10]:
                user = getattr(staff, "user", None)
                bijouterie = getattr(
                    staff,
                    "bijouterie",
                    None,
                )

                recent_staff.append({
                    "staff_id": staff.id,
                    "role": role_name,
                    "email": getattr(
                        user,
                        "email",
                        None,
                    ),
                    "first_name": (
                        getattr(
                            user,
                            "first_name",
                            "",
                        )
                        or ""
                    ),
                    "last_name": (
                        getattr(
                            user,
                            "last_name",
                            "",
                        )
                        or ""
                    ),
                    "verifie": staff.verifie,
                    "bijouteries": (
                        [
                            {
                                "id": bijouterie.id,
                                "nom": bijouterie.nom,
                            }
                        ]
                        if bijouterie
                        else []
                    ),
                    "created_at": staff.created_at,
                })

        recent_staff.sort(
            key=lambda item: item["created_at"],
            reverse=True,
        )

        recent_staff = recent_staff[:10]

        # ====================================================
        # Réponse
        # ====================================================

        payload = {
            "summary": summary,
            "by_bijouterie": by_bijouterie,
            "recent_staff": recent_staff,
        }

        serializer = StaffDashboardResponseSerializer(
            payload
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
        


class ManagerDashboardView(APIView):
    """
    Dashboard du manager connecté.

    Règles :
    - uniquement un manager actif ;
    - uniquement les bijouteries attribuées au manager ;
    - statistiques cumulées sur ses bijouteries ;
    - détail par bijouterie ;
    - historique complet par année/mois.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "options"]

    # ============================================================
    # Helpers
    # ============================================================

    @staticmethod
    def _decimal(value):
        return value or Decimal("0.00")

    @staticmethod
    def _int(value):
        return int(value or 0)

    def _get_manager(self, user):
        """
        Retourne le profil manager actif du user connecté.
        """

        if get_role_name(user) != ROLE_MANAGER:
            return None

        return (
            Manager.objects
            .prefetch_related("bijouteries")
            .filter(
                user=user,
                verifie=True,
            )
            .first()
        )

    # ============================================================
    # Swagger
    # ============================================================

    @swagger_auto_schema(
        operation_id="managerDashboard",
        operation_summary="Dashboard manager connecté",
        operation_description=(
            "Retourne le tableau de bord du manager connecté.\n\n"
            "### Accès\n"
            "- Manager connecté uniquement\n"
            "- Manager actif uniquement\n"
            "- Données limitées à ses bijouteries\n\n"
            "### Données retournées\n"
            "- chiffre d'affaires semaine / mois / année\n"
            "- ventes aujourd'hui / semaine / mois / année\n"
            "- stock magasin\n"
            "- stock vendeurs\n"
            "- quantité totale disponible\n"
            "- poids total disponible\n"
            "- produits en stock faible\n"
            "- performances vendeurs\n"
            "- top produits vendus\n"
            "- achats du mois\n"
            "- derniers arrivages\n"
            "- factures\n"
            "- statistiques par bijouterie\n"
            "- historique annuel et mensuel"
        ),
        responses={
            200: openapi.Response(
                description="Dashboard manager retourné avec succès."
            ),
            403: openapi.Response(
                description="Accès refusé."
            ),
        },
        tags=["Dashboard Manager"],
    )
    def get(self, request):

        # ========================================================
        # Manager connecté
        # ========================================================

        manager = self._get_manager(request.user)

        if not manager:
            return Response(
                {
                    "detail": (
                        "Accès réservé à un manager actif."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # ========================================================
        # Bijouteries du manager
        # ========================================================

        bijouteries = manager.bijouteries.all()

        bijouterie_ids = list(
            bijouteries.values_list(
                "id",
                flat=True,
            )
        )

        if not bijouterie_ids:
            return Response(
                {
                    "detail": (
                        "Aucune bijouterie n'est attribuée "
                        "à ce manager."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # ========================================================
        # Dates
        # ========================================================

        now = timezone.localtime()
        today = now.date()

        start_week = (
            today
            - timezone.timedelta(
                days=today.weekday(),
            )
        )

        start_month = today.replace(
            day=1,
        )

        start_year = today.replace(
            month=1,
            day=1,
        )

        # ========================================================
        # Querysets de base
        # ========================================================

        ventes = (
            Vente.objects
            .filter(
                bijouterie_id__in=bijouterie_ids,
            )
        )

        ventes_produits = (
            VenteProduit.objects
            .filter(
                vente__bijouterie_id__in=bijouterie_ids,
            )
        )

        stocks = (
            Stock.objects
            .filter(
                bijouterie_id__in=bijouterie_ids,
            )
        )

        vendor_stocks = (
            VendorStock.objects
            .filter(
                bijouterie_id__in=bijouterie_ids,
            )
        )

        vendors = (
            Vendor.objects
            .filter(
                bijouterie_id__in=bijouterie_ids,
            )
            .select_related(
                "user",
                "bijouterie",
            )
        )

        factures = (
            Facture.objects
            .filter(
                vente__bijouterie_id__in=bijouterie_ids,
            )
        )

        achats = (
            Achat.objects
            .filter(
                bijouterie_id__in=bijouterie_ids,
            )
        )

        lots = (
            Lot.objects
            .filter(
                achat__bijouterie_id__in=bijouterie_ids,
            )
        )

        # ========================================================
        # Ventes : périodes
        # ========================================================

        ventes_today = ventes.filter(
            created_at__date=today,
        )

        ventes_week = ventes.filter(
            created_at__date__gte=start_week,
            created_at__date__lte=today,
        )

        ventes_month = ventes.filter(
            created_at__date__gte=start_month,
            created_at__date__lte=today,
        )

        ventes_year = ventes.filter(
            created_at__date__gte=start_year,
            created_at__date__lte=today,
        )

        # ========================================================
        # CA semaine
        # ========================================================

        ca_week = self._decimal(
            ventes_week.aggregate(
                total=Coalesce(
                    Sum("montant_total"),
                    Value(
                        Decimal("0.00"),
                        output_field=DecimalField(
                            max_digits=20,
                            decimal_places=2,
                        ),
                    ),
                )
            )["total"]
        )

        # ========================================================
        # CA mois
        # ========================================================

        ca_month = self._decimal(
            ventes_month.aggregate(
                total=Coalesce(
                    Sum("montant_total"),
                    Value(
                        Decimal("0.00"),
                        output_field=DecimalField(
                            max_digits=20,
                            decimal_places=2,
                        ),
                    ),
                )
            )["total"]
        )

        # ========================================================
        # CA année
        # ========================================================

        ca_year = self._decimal(
            ventes_year.aggregate(
                total=Coalesce(
                    Sum("montant_total"),
                    Value(
                        Decimal("0.00"),
                        output_field=DecimalField(
                            max_digits=20,
                            decimal_places=2,
                        ),
                    ),
                )
            )["total"]
        )

        # ========================================================
        # STOCK MAGASIN
        # ========================================================

        stock_magasin = stocks.aggregate(
            total=Coalesce(
                Sum("en_stock"),
                Value(0),
            )
        )["total"]

        # ========================================================
        # STOCK VENDEURS
        # ========================================================

        stock_vendor_data = vendor_stocks.aggregate(
            allouee=Coalesce(
                Sum("quantite_allouee"),
                Value(0),
            ),
            vendue=Coalesce(
                Sum("quantite_vendue"),
                Value(0),
            ),
        )

        stock_vendeurs = (
            self._int(
                stock_vendor_data["allouee"]
            )
            - self._int(
                stock_vendor_data["vendue"]
            )
        )

        # ========================================================
        # Quantité globale restante
        # ========================================================

        quantite_totale = (
            self._int(stock_magasin)
            + stock_vendeurs
        )

        # ========================================================
        # POIDS MAGASIN
        #
        # Stock
        # -> produit_line
        # -> produit
        # -> poids
        # ========================================================

        poids_magasin = stocks.aggregate(
            total=Coalesce(
                Sum(
                    ExpressionWrapper(
                        F("en_stock")
                        * F(
                            "produit_line__produit__poids"
                        ),
                        output_field=DecimalField(
                            max_digits=20,
                            decimal_places=3,
                        ),
                    )
                ),
                Value(
                    Decimal("0.000"),
                    output_field=DecimalField(
                        max_digits=20,
                        decimal_places=3,
                    ),
                ),
            )
        )["total"]

        # ========================================================
        # POIDS VENDEURS
        # ========================================================

        poids_vendor = vendor_stocks.aggregate(
            total=Coalesce(
                Sum(
                    ExpressionWrapper(
                        (
                            F("quantite_allouee")
                            - F("quantite_vendue")
                        )
                        * F(
                            "produit_line__produit__poids"
                        ),
                        output_field=DecimalField(
                            max_digits=20,
                            decimal_places=3,
                        ),
                    )
                ),
                Value(
                    Decimal("0.000"),
                    output_field=DecimalField(
                        max_digits=20,
                        decimal_places=3,
                    ),
                ),
            )
        )["total"]

        poids_total = (
            self._decimal(poids_magasin)
            + self._decimal(poids_vendor)
        )

        # ========================================================
        # Produits stock faible
        #
        # Seuil actuel : <= 2
        # ========================================================

        produits_stock_faible = []

        low_stocks = (
            stocks
            .filter(
                en_stock__gt=0,
                en_stock__lte=2,
            )
            .select_related(
                "bijouterie",
                "produit_line",
                "produit_line__produit",
            )
            .order_by(
                "en_stock",
                "id",
            )[:10]
        )

        for stock_item in low_stocks:

            produit = stock_item.produit_line.produit

            produits_stock_faible.append(
                {
                    "stock_id": stock_item.id,

                    "produit_line_id": (
                        stock_item.produit_line_id
                    ),

                    "produit_id": produit.id,

                    "produit": produit.nom,

                    "sku": produit.sku,

                    "bijouterie_id": (
                        stock_item.bijouterie_id
                    ),

                    "bijouterie": (
                        stock_item.bijouterie.nom
                    ),

                    "quantite": (
                        stock_item.en_stock
                    ),
                }
            )

        # ========================================================
        # VENDEURS
        # ========================================================

        nombre_vendeurs = vendors.count()

        vendeurs_actifs = vendors.filter(
            verifie=True,
        ).count()

        # ========================================================
        # Performance vendeurs du mois
        # ========================================================

        performance_vendeurs = []

        vendor_stats = (
            ventes
            .filter(
                vendor__isnull=False,
                created_at__date__gte=start_month,
                created_at__date__lte=today,
            )
            .values(
                "vendor_id",
                "vendor__user__first_name",
                "vendor__user__last_name",
                "vendor__user__email",
                "vendor__bijouterie__nom",
            )
            .annotate(
                chiffre_affaires=Coalesce(
                    Sum("montant_total"),
                    Value(
                        Decimal("0.00"),
                        output_field=DecimalField(
                            max_digits=20,
                            decimal_places=2,
                        ),
                    ),
                ),

                nombre_ventes=Count(
                    "id",
                    distinct=True,
                ),
            )
            .order_by(
                "-chiffre_affaires"
            )
        )

        # ========================================================
        # Quantités vendues par vendeur
        # ========================================================

        vendor_quantities_qs = (
            ventes_produits
            .filter(
                vendor__isnull=False,
                vente__created_at__date__gte=start_month,
                vente__created_at__date__lte=today,
            )
            .values(
                "vendor_id",
            )
            .annotate(
                quantite=Coalesce(
                    Sum("quantite"),
                    Value(0),
                )
            )
        )

        quantites_vendor = {
            row["vendor_id"]: self._int(
                row["quantite"]
            )
            for row in vendor_quantities_qs
        }

        for item in vendor_stats:

            first_name = (
                item[
                    "vendor__user__first_name"
                ]
                or ""
            )

            last_name = (
                item[
                    "vendor__user__last_name"
                ]
                or ""
            )

            full_name = (
                f"{first_name} {last_name}"
            ).strip()

            email = item[
                "vendor__user__email"
            ]

            performance_vendeurs.append(
                {
                    "vendor_id": (
                        item["vendor_id"]
                    ),

                    "vendor": (
                        full_name
                        or email
                    ),

                    "email": email,

                    "bijouterie": item[
                        "vendor__bijouterie__nom"
                    ],

                    "chiffre_affaires": (
                        item[
                            "chiffre_affaires"
                        ]
                    ),

                    "nombre_ventes": (
                        item[
                            "nombre_ventes"
                        ]
                    ),

                    "quantite_vendue": (
                        quantites_vendor.get(
                            item["vendor_id"],
                            0,
                        )
                    ),
                }
            )

        # ========================================================
        # TOP PRODUITS
        #
        # Mois courant
        # ========================================================

        top_produits_qs = (
            ventes_produits
            .filter(
                vente__created_at__date__gte=start_month,
                vente__created_at__date__lte=today,
            )
            .values(
                "produit_id",
                "produit__nom",
                "produit__sku",
            )
            .annotate(
                quantite_vendue=Coalesce(
                    Sum("quantite"),
                    Value(0),
                ),

                chiffre_affaires=Coalesce(
                    Sum("total_ligne"),
                    Value(
                        Decimal("0.00"),
                        output_field=DecimalField(
                            max_digits=20,
                            decimal_places=2,
                        ),
                    ),
                ),
            )
            .order_by(
                "-quantite_vendue",
                "-chiffre_affaires",
            )[:10]
        )

        top_produits = []

        for item in top_produits_qs:

            top_produits.append(
                {
                    "produit_id": (
                        item["produit_id"]
                    ),

                    "produit": (
                        item["produit__nom"]
                    ),

                    "sku": (
                        item["produit__sku"]
                    ),

                    "quantite_vendue": (
                        self._int(
                            item[
                                "quantite_vendue"
                            ]
                        )
                    ),

                    "chiffre_affaires": (
                        item[
                            "chiffre_affaires"
                        ]
                    ),
                }
            )

        # ========================================================
        # ACHATS MOIS
        # ========================================================

        achats_month = achats.filter(
            created_at__date__gte=start_month,
            created_at__date__lte=today,
        )

        montant_achats_mois = self._decimal(
            achats_month.aggregate(
                total=Coalesce(
                    Sum("montant_total"),
                    Value(
                        Decimal("0.00"),
                        output_field=DecimalField(
                            max_digits=20,
                            decimal_places=2,
                        ),
                    ),
                )
            )["total"]
        )

        # ========================================================
        # DERNIERS ARRIVAGES
        # ========================================================

        derniers_arrivages = []

        lots_qs = (
            lots
            .select_related(
                "achat",
                "achat__fournisseur",
            )
            .order_by(
                "-received_at",
                "-id",
            )[:10]
        )

        for lot in lots_qs:

            fournisseur = None

            if (
                lot.achat
                and lot.achat.fournisseur
            ):
                fournisseur = str(
                    lot.achat.fournisseur
                )

            derniers_arrivages.append(
                {
                    "id": lot.id,

                    "numero_lot": (
                        lot.numero_lot
                    ),

                    "numero_achat": (
                        lot.achat.numero_achat
                        if lot.achat
                        else None
                    ),

                    "fournisseur": fournisseur,

                    "date_arrivage": (
                        lot.received_at
                    ),
                }
            )

        # ========================================================
        # FACTURES
        # ========================================================

        factures_non_payees = (
            factures
            .filter(
                status="non_paye",
            )
            .count()
        )

        factures_partielles = (
            factures
            .filter(
                status="partiel",
            )
            .count()
        )

        factures_payees = (
            factures
            .filter(
                status="paye",
            )
            .count()
        )

        reste_a_encaisser = self._decimal(
            factures
            .exclude(
                status="paye",
            )
            .aggregate(
                total=Coalesce(
                    Sum("reste_a_payer"),
                    Value(
                        Decimal("0.00"),
                        output_field=DecimalField(
                            max_digits=20,
                            decimal_places=2,
                        ),
                    ),
                )
            )["total"]
        )

        # ========================================================
        # PAR BIJOUTERIE
        # ========================================================

        par_bijouterie = []

        for bijouterie in bijouteries:

            # ----------------------------------------------------
            # Ventes année de la bijouterie
            # ----------------------------------------------------

            ventes_bijouterie = (
                ventes_year
                .filter(
                    bijouterie=bijouterie,
                )
            )

            ca_bijouterie = self._decimal(
                ventes_bijouterie.aggregate(
                    total=Coalesce(
                        Sum("montant_total"),
                        Value(
                            Decimal("0.00"),
                            output_field=DecimalField(
                                max_digits=20,
                                decimal_places=2,
                            ),
                        ),
                    )
                )["total"]
            )

            # ----------------------------------------------------
            # Stock magasin
            # ----------------------------------------------------

            stock_bijouterie = self._int(
                stocks
                .filter(
                    bijouterie=bijouterie,
                )
                .aggregate(
                    total=Coalesce(
                        Sum("en_stock"),
                        Value(0),
                    )
                )["total"]
            )

            # ----------------------------------------------------
            # Stock vendeurs
            # ----------------------------------------------------

            vendor_stock_bijouterie = (
                vendor_stocks
                .filter(
                    bijouterie=bijouterie,
                )
                .aggregate(
                    allouee=Coalesce(
                        Sum(
                            "quantite_allouee"
                        ),
                        Value(0),
                    ),

                    vendue=Coalesce(
                        Sum(
                            "quantite_vendue"
                        ),
                        Value(0),
                    ),
                )
            )

            stock_vendor_bijouterie = (
                self._int(
                    vendor_stock_bijouterie[
                        "allouee"
                    ]
                )
                - self._int(
                    vendor_stock_bijouterie[
                        "vendue"
                    ]
                )
            )

            par_bijouterie.append(
                {
                    "bijouterie_id": (
                        bijouterie.id
                    ),

                    "bijouterie": (
                        bijouterie.nom
                    ),

                    "chiffre_affaires": (
                        ca_bijouterie
                    ),

                    "ventes": (
                        ventes_bijouterie.count()
                    ),

                    "stock_magasin": (
                        stock_bijouterie
                    ),

                    "stock_vendeur": (
                        stock_vendor_bijouterie
                    ),

                    "stock_total": (
                        stock_bijouterie
                        + stock_vendor_bijouterie
                    ),
                }
            )

        # ========================================================
        # HISTORIQUE COMPLET
        #
        # Toutes les années disponibles.
        # ========================================================

        historique_qs = (
            ventes
            .annotate(
                year=ExtractYear(
                    "created_at"
                ),

                month=TruncMonth(
                    "created_at"
                ),
            )
            .values(
                "year",
                "month",
            )
            .annotate(
                chiffre_affaires=Coalesce(
                    Sum("montant_total"),
                    Value(
                        Decimal("0.00"),
                        output_field=DecimalField(
                            max_digits=20,
                            decimal_places=2,
                        ),
                    ),
                ),

                nombre_ventes=Count(
                    "id",
                    distinct=True,
                ),
            )
            .order_by(
                "year",
                "month",
            )
        )

        month_names = {
            1: "janvier",
            2: "février",
            3: "mars",
            4: "avril",
            5: "mai",
            6: "juin",
            7: "juillet",
            8: "août",
            9: "septembre",
            10: "octobre",
            11: "novembre",
            12: "décembre",
        }

        historique_map = {}

        for row in historique_qs:

            if not row["year"]:
                continue

            year = int(
                row["year"]
            )

            month_date = row[
                "month"
            ]

            if not month_date:
                continue

            month_number = (
                month_date.month
            )

            if year not in historique_map:

                historique_map[year] = {
                    "annee": year,

                    "chiffre_affaires": (
                        Decimal("0.00")
                    ),

                    "nombre_ventes": 0,

                    "mois": [],
                }

            historique_map[year][
                "chiffre_affaires"
            ] += self._decimal(
                row["chiffre_affaires"]
            )

            historique_map[year][
                "nombre_ventes"
            ] += self._int(
                row["nombre_ventes"]
            )

            historique_map[
                year
            ]["mois"].append(
                {
                    "numero": (
                        month_number
                    ),

                    "mois": (
                        month_names[
                            month_number
                        ]
                    ),

                    "chiffre_affaires": (
                        row[
                            "chiffre_affaires"
                        ]
                    ),

                    "nombre_ventes": (
                        self._int(
                            row[
                                "nombre_ventes"
                            ]
                        )
                    ),
                }
            )

        historique = list(
            historique_map.values()
        )

        historique.sort(
            key=lambda item: (
                item["annee"]
            ),
            reverse=True,
        )

        # ========================================================
        # RESPONSE
        # ========================================================

        return Response(
            {
                # =================================================
                # Manager
                # =================================================

                "manager": {
                    "id": manager.id,

                    "email": (
                        request.user.email
                    ),

                    "first_name": (
                        request.user.first_name
                    ),

                    "last_name": (
                        request.user.last_name
                    ),
                },

                # =================================================
                # Résumé
                # =================================================

                "resume": {
                    "chiffre_affaires_semaine": (
                        ca_week
                    ),

                    "chiffre_affaires_mois": (
                        ca_month
                    ),

                    "chiffre_affaires_annee": (
                        ca_year
                    ),

                    "ventes_semaine": (
                        ventes_week.count()
                    ),

                    "ventes_mois": (
                        ventes_month.count()
                    ),

                    "ventes_annee": (
                        ventes_year.count()
                    ),

                    "nombre_bijouteries": (
                        len(
                            bijouterie_ids
                        )
                    ),
                },

                # =================================================
                # Ventes
                # =================================================

                "ventes": {
                    "aujourd_hui": (
                        ventes_today.count()
                    ),

                    "semaine": (
                        ventes_week.count()
                    ),

                    "mois": (
                        ventes_month.count()
                    ),

                    "annee": (
                        ventes_year.count()
                    ),
                },

                # =================================================
                # Stock
                # =================================================

                "stock": {
                    "stock_magasin": (
                        self._int(
                            stock_magasin
                        )
                    ),

                    "stock_vendeurs": (
                        stock_vendeurs
                    ),

                    "quantite_totale": (
                        quantite_totale
                    ),

                    "poids_magasin": (
                        poids_magasin
                    ),

                    "poids_vendeurs": (
                        poids_vendor
                    ),

                    "poids_total": (
                        poids_total
                    ),

                    "produits_stock_faible": (
                        produits_stock_faible
                    ),
                },

                # =================================================
                # Vendeurs
                # =================================================

                "vendeurs": {
                    "nombre_vendeurs": (
                        nombre_vendeurs
                    ),

                    "vendeurs_actifs": (
                        vendeurs_actifs
                    ),

                    "performance_vendeurs": (
                        performance_vendeurs
                    ),
                },

                # =================================================
                # Top produits
                # =================================================

                "top_produits": (
                    top_produits
                ),

                # =================================================
                # Achats
                # =================================================

                "achats": {
                    "achats_mois": (
                        achats_month.count()
                    ),

                    "montant_achats_mois": (
                        montant_achats_mois
                    ),

                    "derniers_arrivages": (
                        derniers_arrivages
                    ),
                },

                # =================================================
                # Factures
                # =================================================

                "factures": {
                    "non_payees": (
                        factures_non_payees
                    ),

                    "partielles": (
                        factures_partielles
                    ),

                    "payees": (
                        factures_payees
                    ),

                    "reste_a_encaisser": (
                        reste_a_encaisser
                    ),
                },

                # =================================================
                # Bijouteries
                # =================================================

                "par_bijouterie": (
                    par_bijouterie
                ),

                # =================================================
                # Historique
                # =================================================

                "historique": (
                    historique
                ),
            },
            status=status.HTTP_200_OK,
        )


# ///////////////////Caissier dshboard
class CashierDashboardView(APIView):
    """
    Dashboard du caissier connecté.

    Règles :
    - accès uniquement au rôle cashier ;
    - profil Cashier obligatoirement vérifié ;
    - le caissier voit uniquement les données de sa bijouterie ;
    - le CA encaissé est calculé depuis PaiementLigne.montant_paye ;
    - les ventes annulées sont exclues ;
    - historique annuel dynamique à partir de 2026.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get"]

    # ============================================================
    # Helpers
    # ============================================================

    def _get_cashier(self, user):
        """
        Retourne le profil caissier actif de l'utilisateur connecté.
        """

        return (
            Cashier.objects
            .select_related(
                "user",
                "bijouterie",
            )
            .filter(
                user=user,
                verifie=True,
            )
            .first()
        )

    @staticmethod
    def _money(value):
        """
        Normalise un montant Decimal.
        """
        return value or ZERO

    @staticmethod
    def _money_string(value):
        """
        Transforme un montant en chaîne avec 2 décimales.

        Exemple :
            Decimal("150000") -> "150000.00"
        """
        value = value or ZERO
        return f"{Decimal(value):.2f}"

    @staticmethod
    def _payment_sum(queryset):
        """
        Somme des PaiementLigne.montant_paye.
        """

        return (
            queryset.aggregate(
                total=Coalesce(
                    Sum("montant_paye"),
                    Value(
                        ZERO,
                        output_field=DecimalField(
                            max_digits=18,
                            decimal_places=2,
                        ),
                    ),
                )
            )["total"]
            or ZERO
        )

    # ============================================================
    # Swagger
    # ============================================================

    @swagger_auto_schema(
        operation_id="cashierDashboard",
        operation_summary="Dashboard du caissier connecté",
        operation_description=(
            "Retourne le tableau de bord du caissier connecté.\n\n"
            "### Règles d'accès\n"
            "- utilisateur authentifié ;\n"
            "- rôle `cashier` obligatoire ;\n"
            "- profil Cashier vérifié ;\n"
            "- données limitées à la bijouterie du caissier.\n\n"
            "### Données retournées\n"
            "- CA encaissé aujourd'hui ;\n"
            "- CA encaissé semaine courante ;\n"
            "- CA encaissé mois courant ;\n"
            "- CA encaissé année courante ;\n"
            "- nombre et montant des paiements ;\n"
            "- répartition par mode de paiement ;\n"
            "- état des factures ;\n"
            "- ventes de la bijouterie ;\n"
            "- derniers paiements ;\n"
            "- historique annuel depuis 2026."
        ),
        responses={
            200: openapi.Response(
                description="Dashboard caissier",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "cashier": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "id": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    example=2,
                                ),
                                "nom": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="Mamadou Diop",
                                ),
                                "email": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="cashier@rio-gold.com",
                                ),
                                "telephone": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="771234567",
                                    x_nullable=True,
                                ),
                            },
                        ),

                        "bijouterie": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "id": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    example=1,
                                ),
                                "nom": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="Rio Gold Dakar",
                                ),
                            },
                        ),

                        "periode": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "date": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    format=openapi.FORMAT_DATE,
                                    example="2026-08-22",
                                ),
                                "debut_semaine": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    format=openapi.FORMAT_DATE,
                                    example="2026-08-17",
                                ),
                                "fin_semaine": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    format=openapi.FORMAT_DATE,
                                    example="2026-08-23",
                                ),
                                "mois": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    example=8,
                                ),
                                "annee": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    example=2026,
                                ),
                            },
                        ),

                        "ca_encaisse": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "aujourdhui": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="450000.00",
                                ),
                                "semaine": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="2150000.00",
                                ),
                                "mois": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="8750000.00",
                                ),
                                "annee": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="75400000.00",
                                ),
                            },
                        ),

                        "paiements": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "nombre_paiements_jour": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    example=7,
                                ),
                                "montant_paiements_jour": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="450000.00",
                                ),
                                "nombre_paiements_mois": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    example=118,
                                ),
                                "montant_paiements_mois": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="8750000.00",
                                ),
                            },
                        ),

                        "modes_paiement": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "code": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        example="wave",
                                    ),
                                    "nom": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        example="Wave",
                                    ),
                                    "nombre": openapi.Schema(
                                        type=openapi.TYPE_INTEGER,
                                        example=25,
                                    ),
                                    "montant": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        example="2750000.00",
                                    ),
                                },
                            ),
                        ),

                        "factures": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "factures_payees": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    example=82,
                                ),
                                "factures_partielles": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    example=8,
                                ),
                                "factures_non_payees": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    example=13,
                                ),
                                "montant_restant_a_encaisser": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="1850000.00",
                                ),
                            },
                        ),

                        "ventes": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "ventes_jour": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    example=5,
                                ),
                                "ventes_semaine": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    example=27,
                                ),
                                "ventes_mois": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    example=103,
                                ),
                                "ventes_annee": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    example=948,
                                ),
                            },
                        ),

                        "derniers_paiements": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "id": openapi.Schema(
                                        type=openapi.TYPE_INTEGER,
                                        example=21,
                                    ),
                                    "date_paiement": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        format=openapi.FORMAT_DATETIME,
                                    ),
                                    "montant": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        example="250000.00",
                                    ),

                                    "facture": openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            "id": openapi.Schema(
                                                type=openapi.TYPE_INTEGER,
                                                example=15,
                                            ),
                                            "numero_facture": openapi.Schema(
                                                type=openapi.TYPE_STRING,
                                                example="FAC-20260822-0001",
                                            ),
                                            "status": openapi.Schema(
                                                type=openapi.TYPE_STRING,
                                                example="paye",
                                            ),
                                            "type_facture": openapi.Schema(
                                                type=openapi.TYPE_STRING,
                                                example="facture",
                                            ),
                                            "montant_total": openapi.Schema(
                                                type=openapi.TYPE_STRING,
                                                example="250000.00",
                                            ),
                                        },
                                    ),

                                    "client": openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        x_nullable=True,
                                        properties={
                                            "id": openapi.Schema(
                                                type=openapi.TYPE_INTEGER,
                                                example=7,
                                            ),
                                            "nom": openapi.Schema(
                                                type=openapi.TYPE_STRING,
                                                example="Alioune Ndiaye",
                                            ),
                                            "telephone": openapi.Schema(
                                                type=openapi.TYPE_STRING,
                                                example="770000000",
                                                x_nullable=True,
                                            ),
                                        },
                                    ),

                                    "cashier": openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        x_nullable=True,
                                        properties={
                                            "id": openapi.Schema(
                                                type=openapi.TYPE_INTEGER,
                                                example=2,
                                            ),
                                            "nom": openapi.Schema(
                                                type=openapi.TYPE_STRING,
                                                example="Mamadou Diop",
                                            ),
                                        },
                                    ),

                                    "modes_paiement": openapi.Schema(
                                        type=openapi.TYPE_ARRAY,
                                        items=openapi.Schema(
                                            type=openapi.TYPE_OBJECT,
                                            properties={
                                                "code": openapi.Schema(
                                                    type=openapi.TYPE_STRING,
                                                    example="wave",
                                                ),
                                                "nom": openapi.Schema(
                                                    type=openapi.TYPE_STRING,
                                                    example="Wave",
                                                ),
                                                "montant": openapi.Schema(
                                                    type=openapi.TYPE_STRING,
                                                    example="250000.00",
                                                ),
                                                "reference": openapi.Schema(
                                                    type=openapi.TYPE_STRING,
                                                    x_nullable=True,
                                                    example="WAVE-123456",
                                                ),
                                            },
                                        ),
                                    ),
                                },
                            ),
                        ),

                        "historique": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            additional_properties=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "ventes": openapi.Schema(
                                        type=openapi.TYPE_INTEGER,
                                        example=948,
                                    ),
                                    "nombre_paiements": openapi.Schema(
                                        type=openapi.TYPE_INTEGER,
                                        example=1020,
                                    ),
                                    "encaissements": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        example="75400000.00",
                                    ),
                                },
                            ),
                            example={
                                "2026": {
                                    "ventes": 948,
                                    "nombre_paiements": 1020,
                                    "encaissements": "75400000.00",
                                },
                                "2027": {
                                    "ventes": 0,
                                    "nombre_paiements": 0,
                                    "encaissements": "0.00",
                                },
                            },
                        ),
                    },
                ),
            ),

            400: openapi.Response(
                description="Aucune bijouterie associée au caissier",
                examples={
                    "application/json": {
                        "detail": (
                            "Aucune bijouterie n'est associée "
                            "à ce caissier."
                        )
                    }
                },
            ),

            401: openapi.Response(
                description="Utilisateur non authentifié",
                examples={
                    "application/json": {
                        "detail": (
                            "Authentication credentials "
                            "were not provided."
                        )
                    }
                },
            ),

            403: openapi.Response(
                description="Accès interdit",
                examples={
                    "application/json": {
                        "detail": "Accès réservé au caissier."
                    }
                },
            ),
        },
    )
    def get(self, request, *args, **kwargs):

        # ========================================================
        # 1. Vérification rôle
        # ========================================================

        role = get_role_name(request.user)

        if role != ROLE_CASHIER:
            return Response(
                {
                    "detail": (
                        "Accès réservé au caissier."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # ========================================================
        # 2. Profil Cashier
        # ========================================================

        cashier = self._get_cashier(request.user)

        if not cashier:
            return Response(
                {
                    "detail": (
                        "Profil caissier actif introuvable."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if not cashier.bijouterie_id:
            return Response(
                {
                    "detail": (
                        "Aucune bijouterie n'est associée "
                        "à ce caissier."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        bijouterie = cashier.bijouterie

        # ========================================================
        # 3. Dates courantes
        # ========================================================

        today = timezone.localdate()

        # lundi de la semaine courante
        start_week = today - timedelta(
            days=today.weekday()
        )

        end_week = start_week + timedelta(days=6)

        current_month = today.month
        current_year = today.year

        # ========================================================
        # 4. Querysets de base
        # ========================================================

        ventes = (
            Vente.objects
            .filter(
                bijouterie_id=bijouterie.id,
                is_cancelled=False,
            )
        )

        factures = (
            Facture.objects
            .filter(
                bijouterie_id=bijouterie.id,
            )
        )

        paiements = (
            Paiement.objects
            .filter(
                facture__bijouterie_id=bijouterie.id,
            )
        )

        paiement_lignes = (
            PaiementLigne.objects
            .filter(
                paiement__facture__bijouterie_id=bijouterie.id,
            )
        )

        # ========================================================
        # 5. CA encaissé
        # ========================================================
        #
        # IMPORTANT :
        # on utilise PaiementLigne.montant_paye
        # et NON Vente.montant_total.
        #
        # Ainsi :
        # facture = 500 000
        # paiement = 200 000
        #
        # CA encaissé = 200 000
        # et non 500 000.
        # ========================================================

        ca_aujourdhui = self._payment_sum(
            paiement_lignes.filter(
                paiement__date_paiement__date=today,
            )
        )

        ca_semaine = self._payment_sum(
            paiement_lignes.filter(
                paiement__date_paiement__date__range=(
                    start_week,
                    end_week,
                ),
            )
        )

        ca_mois = self._payment_sum(
            paiement_lignes.filter(
                paiement__date_paiement__year=current_year,
                paiement__date_paiement__month=current_month,
            )
        )

        ca_annee = self._payment_sum(
            paiement_lignes.filter(
                paiement__date_paiement__year=current_year,
            )
        )

        # ========================================================
        # 6. Paiements
        # ========================================================

        paiements_jour = paiements.filter(
            date_paiement__date=today,
        )

        paiements_mois = paiements.filter(
            date_paiement__year=current_year,
            date_paiement__month=current_month,
        )

        nombre_paiements_jour = paiements_jour.count()

        nombre_paiements_mois = paiements_mois.count()

        # Les montants sont pris dans PaiementLigne
        montant_paiements_jour = ca_aujourdhui
        montant_paiements_mois = ca_mois

        # ========================================================
        # 7. Répartition modes de paiement
        # ========================================================

        modes_raw = (
            paiement_lignes
            .values(
                "mode_paiement__code",
                "mode_paiement__nom",
            )
            .annotate(
                montant=Coalesce(
                    Sum("montant_paye"),
                    Value(
                        ZERO,
                        output_field=DecimalField(
                            max_digits=18,
                            decimal_places=2,
                        ),
                    ),
                ),
                nombre=Count("id"),
            )
            .order_by(
                "mode_paiement__ordre_affichage",
                "mode_paiement__nom",
            )
        )

        # --------------------------------------------------------
        # Catégories normalisées pour le frontend
        # --------------------------------------------------------

        repartition = {
            "especes": {
                "montant": ZERO,
                "nombre": 0,
            },
            "wave": {
                "montant": ZERO,
                "nombre": 0,
            },
            "orange_money": {
                "montant": ZERO,
                "nombre": 0,
            },
            "carte": {
                "montant": ZERO,
                "nombre": 0,
            },
            "compte_depot": {
                "montant": ZERO,
                "nombre": 0,
            },
            "autres": {
                "montant": ZERO,
                "nombre": 0,
            },
        }

        # Les codes peuvent évoluer légèrement.
        # On accepte plusieurs variantes courantes.
        cash_codes = {
            "cash",
            "espece",
            "especes",
        }

        wave_codes = {
            "wave",
        }

        orange_codes = {
            "orange_money",
            "orange",
            "om",
        }

        card_codes = {
            "card",
            "carte",
            "carte_bancaire",
            "cb",
        }

        depot_codes = {
            "depot",
            "compte_depot",
        }

        for row in modes_raw:

            code = (
                row["mode_paiement__code"]
                or ""
            ).strip().lower()

            montant = row["montant"] or ZERO
            nombre = row["nombre"] or 0

            if code in cash_codes:
                key = "especes"

            elif code in wave_codes:
                key = "wave"

            elif code in orange_codes:
                key = "orange_money"

            elif code in card_codes:
                key = "carte"

            elif code in depot_codes:
                key = "compte_depot"

            else:
                key = "autres"

            repartition[key]["montant"] += montant
            repartition[key]["nombre"] += nombre

        modes_paiement_data = []

        labels = {
            "especes": "Espèces",
            "wave": "Wave",
            "orange_money": "Orange Money",
            "carte": "Carte",
            "compte_depot": "Compte dépôt",
            "autres": "Autres",
        }

        for code, values in repartition.items():
            modes_paiement_data.append(
                {
                    "code": code,
                    "nom": labels[code],
                    "nombre": values["nombre"],
                    "montant": self._money_string(
                        values["montant"]
                    ),
                }
            )

        # ========================================================
        # 8. Factures
        # ========================================================

        factures_payees = factures.filter(
            status=Facture.STAT_PAYE,
        ).count()

        factures_partielles = factures.filter(
            status=Facture.STAT_PARTIEL,
        ).count()

        factures_non_payees = factures.filter(
            status=Facture.STAT_NON_PAYE,
        ).count()

        # --------------------------------------------------------
        # Calcul SQL :
        #
        # reste =
        # montant_total - somme des paiements
        #
        # On calcule uniquement les factures non totalement payées.
        # --------------------------------------------------------

        factures_a_encaisser = (
            factures
            .exclude(
                status=Facture.STAT_PAYE,
            )
            .annotate(
                total_paye_db=Coalesce(
                    Sum(
                        "paiements__lignes__montant_paye"
                    ),
                    Value(
                        ZERO,
                        output_field=DecimalField(
                            max_digits=18,
                            decimal_places=2,
                        ),
                    ),
                )
            )
            .annotate(
                reste_db=ExpressionWrapper(
                    F("montant_total")
                    - F("total_paye_db"),
                    output_field=DecimalField(
                        max_digits=18,
                        decimal_places=2,
                    ),
                )
            )
        )

        montant_restant_a_encaisser = (
            factures_a_encaisser.aggregate(
                total=Coalesce(
                    Sum("reste_db"),
                    Value(
                        ZERO,
                        output_field=DecimalField(
                            max_digits=18,
                            decimal_places=2,
                        ),
                    ),
                )
            )["total"]
            or ZERO
        )

        # Sécurité : jamais de reste négatif
        montant_restant_a_encaisser = max(
            montant_restant_a_encaisser,
            ZERO,
        )

        # ========================================================
        # 9. Nombre de ventes
        # ========================================================

        ventes_jour = ventes.filter(
            created_at__date=today,
        ).count()

        ventes_semaine = ventes.filter(
            created_at__date__range=(
                start_week,
                end_week,
            ),
        ).count()

        ventes_mois = ventes.filter(
            created_at__year=current_year,
            created_at__month=current_month,
        ).count()

        ventes_annee = ventes.filter(
            created_at__year=current_year,
        ).count()

        # ========================================================
        # 10. Derniers paiements
        # ========================================================

        derniers_paiements_qs = (
            paiements
            .select_related(
                "facture",
                "cashier",
                "cashier__user",
                "facture__vente",
                "facture__vente__client",
            )
            .prefetch_related(
                "lignes",
                "lignes__mode_paiement",
            )
            .order_by(
                "-date_paiement"
            )[:10]
        )

        derniers_paiements = []

        for paiement in derniers_paiements_qs:

            lignes = list(paiement.lignes.all())

            total_paye = sum(
                (
                    ligne.montant_paye or ZERO
                    for ligne in lignes
                ),
                ZERO,
            )

            modes = [
                {
                    "code": ligne.mode_paiement.code,
                    "nom": ligne.mode_paiement.nom,
                    "montant": self._money_string(
                        ligne.montant_paye
                    ),
                    "reference": ligne.reference,
                }
                for ligne in lignes
            ]

            facture = paiement.facture

            vente = (
                facture.vente
                if facture
                else None
            )

            client = (
                vente.client
                if vente
                else None
            )

            derniers_paiements.append(
                {
                    "id": paiement.id,

                    "date_paiement": (
                        paiement.date_paiement
                    ),

                    "montant": self._money_string(
                        total_paye
                    ),

                    "facture": {
                        "id": facture.id,
                        "numero_facture": (
                            facture.numero_facture
                        ),
                        "status": facture.status,
                        "type_facture": (
                            facture.type_facture
                        ),
                        "montant_total": (
                            self._money_string(
                                facture.montant_total
                            )
                        ),
                    },

                    "client": (
                        {
                            "id": client.id,
                            "nom": client.full_name,
                            "telephone": (
                                client.telephone
                            ),
                        }
                        if client
                        else None
                    ),

                    "cashier": (
                        {
                            "id": paiement.cashier_id,
                            "nom": (
                                paiement.cashier.full_name
                            ),
                        }
                        if paiement.cashier
                        else None
                    ),

                    "modes_paiement": modes,
                }
            )

        # ========================================================
        # 11. Historique annuel
        # ========================================================
        #
        # À partir de 2026 jusqu'à l'année courante.
        #
        # En 2028 :
        #
        # historique:
        #   2026
        #   2027
        #   2028
        #
        # ========================================================

        HISTORIQUE_START_YEAR = 2026

        ventes_par_annee = {
            row["created_at__year"]: row["total"]
            for row in (
                ventes
                .values(
                    "created_at__year"
                )
                .annotate(
                    total=Count("id")
                )
            )
            if row["created_at__year"]
        }

        encaissements_par_annee = {
            row["paiement__date_paiement__year"]:
                row["montant"]
            for row in (
                paiement_lignes
                .values(
                    "paiement__date_paiement__year"
                )
                .annotate(
                    montant=Coalesce(
                        Sum("montant_paye"),
                        Value(
                            ZERO,
                            output_field=DecimalField(
                                max_digits=18,
                                decimal_places=2,
                            ),
                        ),
                    )
                )
            )
            if row["paiement__date_paiement__year"]
        }

        paiements_par_annee = {
            row["date_paiement__year"]: row["total"]
            for row in (
                paiements
                .values(
                    "date_paiement__year"
                )
                .annotate(
                    total=Count("id")
                )
            )
            if row["date_paiement__year"]
        }

        historique = {}

        for year in range(
            HISTORIQUE_START_YEAR,
            current_year + 1,
        ):
            historique[str(year)] = {
                "ventes": (
                    ventes_par_annee.get(
                        year,
                        0,
                    )
                ),
                "nombre_paiements": (
                    paiements_par_annee.get(
                        year,
                        0,
                    )
                ),
                "encaissements": (
                    self._money_string(
                        encaissements_par_annee.get(
                            year,
                            ZERO,
                        )
                    )
                ),
            }

        # ========================================================
        # 12. Réponse finale
        # ========================================================

        return Response(
            {
                "cashier": {
                    "id": cashier.id,
                    "nom": cashier.full_name,
                    "email": cashier.email,
                    "telephone": cashier.telephone,
                },

                "bijouterie": {
                    "id": bijouterie.id,
                    "nom": bijouterie.nom,
                },

                "periode": {
                    "date": today,
                    "debut_semaine": start_week,
                    "fin_semaine": end_week,
                    "mois": current_month,
                    "annee": current_year,
                },

                # -----------------------------------------------
                # CA réellement encaissé
                # -----------------------------------------------

                "ca_encaisse": {
                    "aujourdhui": (
                        self._money_string(
                            ca_aujourdhui
                        )
                    ),
                    "semaine": (
                        self._money_string(
                            ca_semaine
                        )
                    ),
                    "mois": (
                        self._money_string(
                            ca_mois
                        )
                    ),
                    "annee": (
                        self._money_string(
                            ca_annee
                        )
                    ),
                },

                # -----------------------------------------------
                # Paiements
                # -----------------------------------------------

                "paiements": {
                    "nombre_paiements_jour": (
                        nombre_paiements_jour
                    ),
                    "montant_paiements_jour": (
                        self._money_string(
                            montant_paiements_jour
                        )
                    ),
                    "nombre_paiements_mois": (
                        nombre_paiements_mois
                    ),
                    "montant_paiements_mois": (
                        self._money_string(
                            montant_paiements_mois
                        )
                    ),
                },

                # -----------------------------------------------
                # Modes de paiement
                # -----------------------------------------------

                "modes_paiement": (
                    modes_paiement_data
                ),

                # -----------------------------------------------
                # Factures
                # -----------------------------------------------

                "factures": {
                    "factures_payees": (
                        factures_payees
                    ),
                    "factures_partielles": (
                        factures_partielles
                    ),
                    "factures_non_payees": (
                        factures_non_payees
                    ),
                    "montant_restant_a_encaisser": (
                        self._money_string(
                            montant_restant_a_encaisser
                        )
                    ),
                },

                # -----------------------------------------------
                # Ventes
                # -----------------------------------------------

                "ventes": {
                    "ventes_jour": ventes_jour,
                    "ventes_semaine": (
                        ventes_semaine
                    ),
                    "ventes_mois": ventes_mois,
                    "ventes_annee": ventes_annee,
                },

                # -----------------------------------------------
                # Dernières opérations
                # -----------------------------------------------

                "derniers_paiements": (
                    derniers_paiements
                ),

                # -----------------------------------------------
                # Historique
                # -----------------------------------------------

                "historique": historique,
            },
            status=status.HTTP_200_OK,
        )
# //////////caissier dashboard
