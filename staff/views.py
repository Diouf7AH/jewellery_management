from django.db.models import Count
# staff/views.py
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from staff.models import Cashier, Manager
from staff.serializers import (CreateStaffUnifiedSerializer,
                               StaffDashboardResponseSerializer,
                               StaffDetailUnifiedSerializer,
                               StaffUnifiedListItemSerializer,
                               UpdateStaffUnifiedSerializer)
from staff.services import create_staff_member, update_staff_member
from vendor.models import Vendor

from backend.permissions import IsAdminOrManager, IsAdminOrManagerOrVendor
from backend.roles import (ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR,
                           get_role_name)


class CreateStaffUnifiedView(APIView):
    """
    API unique de création de staff.

    - admin   : manager / vendor / cashier
    - manager : vendor / cashier
    """
    permission_classes = [IsAdminOrManager]

    @swagger_auto_schema(
        operation_summary="Créer un staff",
        operation_description="""

    Règles :

    - L'utilisateur doit déjà avoir créé son compte.
    - Admin peut créer :
        - Manager
        - Vendor
        - Cashier
    - Manager peut créer :
        - Vendor
        - Cashier
    - Un utilisateur ne peut avoir qu'un seul profil staff.
    - Manager → plusieurs bijouteries.
    - Vendor/Cashier → une seule bijouterie.
    """,
        request_body=CreateStaffUnifiedSerializer,
        responses={
            201: openapi.Response(
                description="Staff créé avec succès",
                examples={
                    "application/json": {
                        "message": "Staff créé avec succès",
                        "staff_type": "vendor",
                        "staff": {
                            "id": 5,
                            "verifie": True,
                            "bijouteries": [
                                {
                                    "id": 1,
                                    "nom": "RIO GOLD Dakar"
                                }
                            ],
                            "created_at": "2026-05-30T20:00:00Z",
                            "updated_at": "2026-05-30T20:00:00Z"
                        },
                        "user": {
                            "id": 12,
                            "email": "vendeur@riogold.com",
                            "first_name": "Moussa",
                            "last_name": "Fall",
                            "telephone": "771234567",
                            "role": "vendor"
                        }
                    }
                }
            ),
            400: openapi.Response(
                description="Erreur de validation",
                examples={
                    "application/json": {
                        "email": [
                            "Aucun utilisateur trouvé avec cet email. L'utilisateur doit d'abord créer son compte."
                        ]
                    }
                }
            ),
            403: openapi.Response(
                description="Accès refusé",
                examples={
                    "application/json": {
                        "error": "Accès réservé aux rôles admin et manager."
                    }
                }
            ),
            409: openapi.Response(
                description="Conflit",
                examples={
                    "application/json": {
                        "error": "Cet utilisateur possède déjà un profil staff."
                    }
                }
            ),
        },
        tags=["Staff"],
    )
    def post(self, request):
        serializer = CreateStaffUnifiedSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            result = create_staff_member(
                caller_user=request.user,
                target_role=data["role"],
                email=data["email"],
                bijouterie=data.get("bijouterie_nom"),
                bijouteries=data.get("bijouteries", []),
                verifie=data.get("verifie", True),
            )
        except PermissionError as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_409_CONFLICT)
        except Exception as e:
            return Response(
                {"detail": "Erreur inattendue", "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        staff = result.staff
        user = result.user

        if result.staff_type == "manager":
            bijouteries_data = [
                {"id": b.id, "nom": b.nom}
                for b in staff.bijouteries.all()
            ]
        else:
            bj = getattr(staff, "bijouterie", None)
            bijouteries_data = [
                {"id": bj.id, "nom": bj.nom}
            ] if bj else []

        return Response(
            {
                "message": "✅ Staff créé avec succès",
                "staff_type": result.staff_type,
                "staff": {
                    "id": staff.id,
                    "verifie": staff.verifie,
                    "bijouteries": bijouteries_data,
                    "created_at": staff.created_at,
                    "updated_at": staff.updated_at,
                },
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "telephone": user.telephone,
                    "role": result.staff_type,
                },
            },
            status=status.HTTP_201_CREATED,
        )
                


class UpdateStaffUnifiedView(APIView):
    """
    API unique de mise à jour de staff.
    """
    permission_classes = [IsAdminOrManager]

    @swagger_auto_schema(
        operation_id="updateUnifiedStaff",
        operation_summary="Mettre à jour un staff (manager, vendeur, caissier)",
        operation_description=(
            "Cette route met à jour un staff existant via une API unifiée.\n\n"

            "### URL\n"
            "- `PUT /api/staff/<staff_id>/update`\n\n"

            "### Règles d'accès\n"
            "- **Admin** : peut modifier `manager`, `vendor`, `cashier`\n"
            "- **Manager** : peut modifier seulement `vendor` et `cashier` de ses bijouteries\n"
            "- **Manager** : ne peut pas modifier un autre `manager`\n\n"

            "### Champs modifiables\n"
            "- `role` : type de staff ciblé (`manager`, `vendor`, `cashier`) **obligatoire**\n"
            "- `email`\n"
            "- `first_name`\n"
            "- `last_name`\n"
            "- `bijouterie_nom`\n"
            "- `verifie`\n"
            "- `raison_desactivation`\n\n"

            "### Exemples d'appels\n"
            "1. **Mettre à jour un vendeur**\n"
            "   - `PUT /api/staff/5/update`\n\n"
            "2. **Mettre à jour un caissier**\n"
            "   - `PUT /api/staff/8/update`\n\n"
            "3. **Mettre à jour un manager**\n"
            "   - `PUT /api/staff/2/update`\n"
        ),
        manual_parameters=[
            openapi.Parameter(
                name="staff_id",
                in_=openapi.IN_PATH,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="ID du staff à mettre à jour",
            )
        ],
        request_body=UpdateStaffUnifiedSerializer,
        responses={
            200: openapi.Response(
                description="Staff mis à jour avec succès",
                examples={
                    "application/json": {
                        "message": "✅ Staff mis à jour avec succès",
                        "staff_type": "vendor",
                        "staff": {
                            "id": 5,
                            "verifie": True,
                            "raison_desactivation": "",
                            "bijouteries": [{
                                    "id": 2,
                                    "nom": "Rio-Gold Centre"
                                }],
                            "created_at": "2026-04-01T09:00:00Z",
                            "updated_at": "2026-04-01T10:15:00Z"
                        },
                        "user": {
                            "id": 21,
                            "email": "vendeur.new@example.com",
                            "first_name": "Jean",
                            "last_name": "Dupont",
                            "role": "vendor"
                        }
                    }
                },
            ),
            400: openapi.Response(
                description="Erreur de validation",
                examples={
                    "application/json": {
                        "email": ["Cet email est déjà utilisé par un autre utilisateur."]
                    }
                },
            ),
            403: openapi.Response(
                description="Accès refusé",
                examples={
                    "application/json": {
                        "error": "Vous ne pouvez modifier que les staff de votre bijouterie."
                    }
                },
            ),
            404: openapi.Response(
                description="Staff introuvable",
                examples={
                    "application/json": {
                        "error": "Staff introuvable."
                    }
                },
            ),
            409: openapi.Response(
                description="Conflit métier",
                examples={
                    "application/json": {
                        "error": "Un manager ne peut pas modifier un autre manager."
                    }
                },
            ),
        },
        tags=["Staff"],
    )
    def put(self, request, staff_id):
        serializer = UpdateStaffUnifiedSerializer(
            data=request.data,
            context={"user_id": None},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        serializer = UpdateStaffUnifiedSerializer(
            data=request.data,
            context={"user_id": self._get_target_user_id(data["role"], staff_id)},
        )
        serializer.is_valid(raise_exception=True)
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
                raison_desactivation=data.get("raison_desactivation"),
            )
        except PermissionError as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as e:
            msg = str(e)
            code = status.HTTP_404_NOT_FOUND if "introuvable" in msg.lower() else status.HTTP_409_CONFLICT
            return Response({"error": msg}, status=code)
        except Exception as e:
            return Response(
                {"detail": "Erreur inattendue", "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        staff = result.staff
        user = result.user

        if result.staff_type == ROLE_MANAGER:
            bijouteries_data = [
                {"id": b.id, "nom": b.nom}
                for b in staff.bijouteries.all()
            ]
        else:
            bj = getattr(staff, "bijouterie", None)
            bijouteries_data = [
                {"id": bj.id, "nom": bj.nom}
            ] if bj else []

        return Response(
            {
                "message": "✅ Staff mis à jour avec succès",
                "staff_type": result.staff_type,
                "staff": {
                    "id": staff.id,
                    "verifie": staff.verifie,
                    "raison_desactivation": staff.raison_desactivation,
                    "bijouteries": bijouteries_data,
                    "created_at": staff.created_at,
                    "updated_at": staff.updated_at,
                },
                "user": {
                    "id": user.id if user else None,
                    "email": user.email if user else None,
                    "first_name": user.first_name if user else "",
                    "last_name": user.last_name if user else "",
                    "role": result.staff_type,
                },
            },
            status=status.HTTP_200_OK,
        )

    def _get_target_user_id(self, role, staff_id):
        from staff.models import Cashier, Manager
        from vendor.models import Vendor

        from backend.roles import ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR

        model_map = {
            ROLE_MANAGER: Manager,
            ROLE_VENDOR: Vendor,
            ROLE_CASHIER: Cashier,
        }
        Model = model_map.get(role)
        if not Model:
            return None

        obj = Model.objects.select_related("user").filter(pk=staff_id).first()
        return getattr(obj, "user_id", None)
    


class ListStaffUnifiedView(APIView):
    """
    GET /api/staff/list/

    Liste unifiée des staff :
    - manager
    - vendor
    - cashier
    """
    permission_classes = [IsAdminOrManager]

    @swagger_auto_schema(
        operation_id="listUnifiedStaff",
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
    }

    @swagger_auto_schema(
        operation_id="staffDetailUnified",
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
        else:
            staff = (
                Model.objects
                .select_related("user", "bijouterie")
                .filter(pk=staff_id)
                .first()
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

    - admin   : voit tous les staff
    - manager : voit seulement les staff de ses bijouteries
    """
    permission_classes = [IsAdminOrManager]

    @swagger_auto_schema(
        operation_id="staffDashboard",
        operation_summary="Dashboard des staff",
        operation_description=(
            "Retourne un dashboard global des staff.\n\n"
            "- Admin : voit tous les managers, vendeurs et caissiers\n"
            "- Manager : voit seulement les staff de ses bijouteries\n\n"
            "Réponse :\n"
            "- summary : compteurs globaux\n"
            "- by_bijouterie : répartition des staff par bijouterie\n"
            "- recent_staff : derniers staff créés\n"
        ),
        responses={200: StaffDashboardResponseSerializer()},
        tags=["Staff"],
    )
    def get(self, request):
        caller_role = get_role_name(request.user)

        if caller_role not in (ROLE_ADMIN, ROLE_MANAGER):
            return Response(
                {"detail": "Accès réservé aux rôles admin et manager."},
                status=status.HTTP_403_FORBIDDEN,
            )

        empty_payload = {
            "summary": {
                "managers_count": 0,
                "vendors_count": 0,
                "cashiers_count": 0,
                "verified_count": 0,
                "disabled_count": 0,
            },
            "by_bijouterie": [],
            "recent_staff": [],
        }

        manager_bj_ids = []

        if caller_role == ROLE_MANAGER:
            manager_profile = (
                Manager.objects
                .prefetch_related("bijouteries")
                .filter(user=request.user, verifie=True)
                .first()
            )

            if not manager_profile:
                serializer = StaffDashboardResponseSerializer(empty_payload)
                return Response(serializer.data, status=status.HTTP_200_OK)

            manager_bj_ids = list(
                manager_profile.bijouteries.values_list("id", flat=True)
            )

            if not manager_bj_ids:
                serializer = StaffDashboardResponseSerializer(empty_payload)
                return Response(serializer.data, status=status.HTTP_200_OK)

        qs_managers = (
            Manager.objects
            .select_related("user")
            .prefetch_related("bijouteries")
        )
        qs_vendors = Vendor.objects.select_related("user", "bijouterie")
        qs_cashiers = Cashier.objects.select_related("user", "bijouterie")

        if caller_role == ROLE_MANAGER:
            qs_managers = qs_managers.filter(
                bijouteries__id__in=manager_bj_ids
            ).distinct()
            qs_vendors = qs_vendors.filter(
                bijouterie__id__in=manager_bj_ids
            )
            qs_cashiers = qs_cashiers.filter(
                bijouterie__id__in=manager_bj_ids
            )

        managers_count = qs_managers.count()
        vendors_count = qs_vendors.count()
        cashiers_count = qs_cashiers.count()

        verified_count = (
            qs_managers.filter(verifie=True).count()
            + qs_vendors.filter(verifie=True).count()
            + qs_cashiers.filter(verifie=True).count()
        )

        disabled_count = (
            qs_managers.filter(verifie=False).count()
            + qs_vendors.filter(verifie=False).count()
            + qs_cashiers.filter(verifie=False).count()
        )

        summary = {
            "managers_count": managers_count,
            "vendors_count": vendors_count,
            "cashiers_count": cashiers_count,
            "verified_count": verified_count,
            "disabled_count": disabled_count,
        }

        by_bijouterie_map = {}

        managers_grouped = (
            qs_managers
            .values("bijouteries__id", "bijouteries__nom")
            .annotate(managers_count=Count("id", distinct=True))
            .order_by("bijouteries__nom")
        )

        for row in managers_grouped:
            bj_id = row["bijouteries__id"]
            bj_nom = row["bijouteries__nom"]

            if bj_id is None:
                continue

            by_bijouterie_map.setdefault(bj_id, {
                "bijouterie_id": bj_id,
                "bijouterie_nom": bj_nom,
                "managers_count": 0,
                "vendors_count": 0,
                "cashiers_count": 0,
            })

            by_bijouterie_map[bj_id]["managers_count"] = row["managers_count"] or 0

        vendors_grouped = (
            qs_vendors
            .values("bijouterie_id", "bijouterie__nom")
            .annotate(vendors_count=Count("id"))
            .order_by("bijouterie__nom")
        )

        for row in vendors_grouped:
            bj_id = row["bijouterie_id"]
            bj_nom = row["bijouterie__nom"]

            if bj_id is None:
                continue

            by_bijouterie_map.setdefault(bj_id, {
                "bijouterie_id": bj_id,
                "bijouterie_nom": bj_nom,
                "managers_count": 0,
                "vendors_count": 0,
                "cashiers_count": 0,
            })

            by_bijouterie_map[bj_id]["vendors_count"] = row["vendors_count"] or 0

        cashiers_grouped = (
            qs_cashiers
            .values("bijouterie_id", "bijouterie__nom")
            .annotate(cashiers_count=Count("id"))
            .order_by("bijouterie__nom")
        )

        for row in cashiers_grouped:
            bj_id = row["bijouterie_id"]
            bj_nom = row["bijouterie__nom"]

            if bj_id is None:
                continue

            by_bijouterie_map.setdefault(bj_id, {
                "bijouterie_id": bj_id,
                "bijouterie_nom": bj_nom,
                "managers_count": 0,
                "vendors_count": 0,
                "cashiers_count": 0,
            })

            by_bijouterie_map[bj_id]["cashiers_count"] = row["cashiers_count"] or 0

        by_bijouterie = sorted(
            by_bijouterie_map.values(),
            key=lambda x: (x["bijouterie_nom"] or "").lower()
        )

        recent_staff = []

        for obj in qs_managers.order_by("-created_at")[:10]:
            user = getattr(obj, "user", None)

            recent_staff.append({
                "staff_id": obj.id,
                "role": ROLE_MANAGER,
                "email": getattr(user, "email", None),
                "first_name": getattr(user, "first_name", "") or "",
                "last_name": getattr(user, "last_name", "") or "",
                "verifie": obj.verifie,
                "bijouteries": [
                    {
                        "id": b.id,
                        "nom": b.nom,
                    }
                    for b in obj.bijouteries.all()
                ],
                "created_at": obj.created_at,
            })

        for obj in qs_vendors.order_by("-created_at")[:10]:
            user = getattr(obj, "user", None)
            bj = getattr(obj, "bijouterie", None)

            recent_staff.append({
                "staff_id": obj.id,
                "role": ROLE_VENDOR,
                "email": getattr(user, "email", None),
                "first_name": getattr(user, "first_name", "") or "",
                "last_name": getattr(user, "last_name", "") or "",
                "verifie": obj.verifie,
                "bijouteries": [
                    {
                        "id": bj.id,
                        "nom": bj.nom,
                    }
                ] if bj else [],
                "created_at": obj.created_at,
            })

        for obj in qs_cashiers.order_by("-created_at")[:10]:
            user = getattr(obj, "user", None)
            bj = getattr(obj, "bijouterie", None)

            recent_staff.append({
                "staff_id": obj.id,
                "role": ROLE_CASHIER,
                "email": getattr(user, "email", None),
                "first_name": getattr(user, "first_name", "") or "",
                "last_name": getattr(user, "last_name", "") or "",
                "verifie": obj.verifie,
                "bijouteries": [
                    {
                        "id": bj.id,
                        "nom": bj.nom,
                    }
                ] if bj else [],
                "created_at": obj.created_at,
            })

        recent_staff.sort(key=lambda x: x["created_at"], reverse=True)
        recent_staff = recent_staff[:10]

        payload = {
            "summary": summary,
            "by_bijouterie": by_bijouterie,
            "recent_staff": recent_staff,
        }

        serializer = StaffDashboardResponseSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)
    


