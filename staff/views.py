from django.db.models import Count
# staff/views.py
# staff/views.py
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.permissions import IsAdminOrManager, IsAdminOrManagerOrVendor
from backend.roles import (ROLE_ADMIN, ROLE_BUYER, ROLE_CASHIER, ROLE_MANAGER,
                           ROLE_VENDOR, get_role_name)
from staff.models import Buyer, Cashier, Manager
from staff.serializers import (CreateStaffSerializer,
                               StaffDashboardResponseSerializer,
                               StaffDetailSerializer, StaffListItemSerializer,
                               UpdateStaffSerializer)
from staff.services import (create_staff_member, promote_user_to_admin,
                            update_staff_member)
from vendor.models import Vendor

SINGLE_BIJOUTERIE_ROLES = {
    ROLE_VENDOR,
    ROLE_CASHIER,
    ROLE_BUYER,
}


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
            "- Vendor / Cashier / Buyer : utiliser `bijouterie_nom`.\n\n"
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
                bijouterie=data.get("bijouterie_nom"),
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
    permission_classes = [IsAdminOrManager]

    def post(self, request):
        email = (
            request.data.get("email") or ""
        ).strip().lower()

        try:
            user = promote_user_to_admin(
                caller_user=request.user,
                email=email,
            )

        except PermissionError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_403_FORBIDDEN,
            )

        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "message": "Administrateur créé avec succès.",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "role": ROLE_ADMIN,
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
        

