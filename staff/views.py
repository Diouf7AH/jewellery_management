# from datetime import datetime

# from django.contrib.auth import get_user_model
# from django.db import IntegrityError, transaction
# from django.db.models import F, Q, Sum
# from django.shortcuts import get_object_or_404
# from django.utils import timezone
# from drf_yasg import openapi
# from drf_yasg.utils import swagger_auto_schema
# from rest_framework import generics, permissions, status
# from rest_framework.permissions import IsAuthenticated
# from rest_framework.response import Response
# from rest_framework.views import APIView

# from backend.permissions import (ROLE_ADMIN, ROLE_MANAGER, IsAdminOrManager,
#                                  get_role_name)
# from userauths.models import Role
# from userauths.serializers import UserSerializer
# from vendor.models import Vendor
# from vendor.serializer import VendorSerializer

# from .models import Cashier, Manager
# from .serializers import (CashierReadSerializer, CashierSerializer,
#                           CashierUpdateSerializer, CreateStaffMemberSerializer,
#                           ManagerSerializer, UpdateStaffSerializer)

# # Create your views here.
# User = get_user_model()
# allowed_all_roles = ['admin', 'manager', 'vendeur', 'cashier',]
# allowed_roles_admin_manager = ['admin', 'manager',]

# def _parse_iso_dt(s: str):
#     if not s:
#         return None
#     try:
#         dt = datetime.fromisoformat(s)
#     except ValueError:
#         # support YYYY-MM-DD
#         try:
#             dt = datetime.strptime(s, "%Y-%m-%d")
#         except ValueError:
#             return None
#     if timezone.is_naive(dt):
#         dt = timezone.make_aware(dt, timezone.get_current_timezone())
#     return dt

# ROLE_ADMIN, ROLE_MANAGER = "admin", "manager"
# ROLE_VENDOR, ROLE_CASHIER = "vendor", "cashier"


# class CreateStaffMemberView(APIView):
#     """
#     Créer un staff (manager, vendor ou cashier) à partir d’un utilisateur existant :
#       - Admin : peut créer manager, vendor, cashier
#       - Manager : peut créer vendor, cashier (mais PAS manager)
#     """
#     permission_classes = [IsAuthenticated]

#     # mappage rôle -> (Model, Serializer de sortie)
#     MAP = {
#         ROLE_VENDOR:  (Vendor,  VendorSerializer),
#         ROLE_CASHIER: (Cashier, CashierSerializer),
#         ROLE_MANAGER: (Manager, ManagerSerializer),  # tu peux créer un ManagerSerializer dédié si tu veux
#     }

#     # qui peut créer quoi
#     ALLOWED_BY_CALLER = {
#         ROLE_ADMIN:   {ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER},
#         ROLE_MANAGER: {ROLE_VENDOR, ROLE_CASHIER},   # ⚠️ pas manager
#     }

#     @swagger_auto_schema(
#         operation_summary="Créer un staff (manager, vendor, cashier) pour un utilisateur existant",
#         operation_description=(
#             "- Admin : peut créer manager, vendor, cashier\n"
#             "- Manager : peut créer vendor et cashier uniquement\n\n"
#             "Le user doit déjà exister (par son email)."
#         ),
#         request_body=CreateStaffMemberSerializer,
#         responses={
#             201: "Créé",
#             400: "Erreur",
#             403: "Accès refusé",
#             404: "Utilisateur introuvable",
#             409: "Conflit de rôle ou staff déjà existant",
#         },
#         tags=["Staff"],
#     )
#     @transaction.atomic
#     def post(self, request):
#         # 0) Rôle de l'appelant
#         caller_role = getattr(getattr(request.user, "user_role", None), "role", None)

#         if caller_role not in (ROLE_ADMIN, ROLE_MANAGER):
#             return Response(
#                 {"error": "⛔ Accès réservé aux rôles admin et manager."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         # 1) Validation du payload
#         ser = CreateStaffMemberSerializer(data=request.data)
#         ser.is_valid(raise_exception=True)
#         data = ser.validated_data

#         email = data["email"]
#         bijouterie = data["bijouterie"]          # instance Bijouterie
#         wanted_role = data["role"].lower()

#         # 2) Vérifier si le caller a le droit de créer CE rôle précis
#         allowed_targets = self.ALLOWED_BY_CALLER.get(caller_role, set())
#         if wanted_role not in allowed_targets:
#             return Response(
#                 {"error": f"⛔ Un {caller_role} ne peut pas créer un staff de type {wanted_role}."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         # 3) Vérifier que le rôle demandé est bien géré
#         if wanted_role not in self.MAP:
#             return Response({"error": "role doit être 'vendor', 'cashier' ou 'manager'."}, status=400)

#         Model, OutSer = self.MAP[wanted_role]

#         # 4) Charger le user sous verrou
#         user = User.objects.select_for_update().filter(email__iexact=email).first()
#         if not user:
#             return Response(
#                 {"error": f"Aucun utilisateur trouvé avec l’email {email}."},
#                 status=status.HTTP_404_NOT_FOUND,
#             )

#         # 5) Rôles présents en base
#         role_vendor  = Role.objects.filter(role=ROLE_VENDOR).first()
#         role_cashier = Role.objects.filter(role=ROLE_CASHIER).first()
#         role_manager = Role.objects.filter(role=ROLE_MANAGER).first()

#         if not all([role_vendor, role_cashier, role_manager]):
#             return Response(
#                 {"error": "Les rôles vendor/manager/cashier n’existent pas en base."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         existing_role = getattr(getattr(user, "user_role", None), "role", None)

#         # 6) Protection : on ne transforme pas un admin/manager existant
#         if existing_role in (ROLE_ADMIN,):
#             return Response(
#                 {"error": f"User déjà {existing_role}, impossible de le transformer en staff."},
#                 status=status.HTTP_409_CONFLICT,
#             )

#         # 7) Vérifier qu’il n’a pas déjà un autre staff
#         #    - on empêche d’avoir Vendor + Cashier + Manager en même temps

#         already_vendor  = Vendor.objects.select_for_update().filter(user_id=user.id).exists()
#         already_cashier = Cashier.objects.select_for_update().filter(user_id=user.id).exists()
#         already_manager = Manager.objects.select_for_update().filter(user_id=user.id).exists()

#         if wanted_role == ROLE_VENDOR and (already_vendor or already_cashier or already_manager):
#             return Response({"error": "Ce user a déjà un profil staff (vendor/cashier/manager)."}, status=409)

#         if wanted_role == ROLE_CASHIER and (already_vendor or already_cashier or already_manager):
#             return Response({"error": "Ce user a déjà un profil staff (vendor/cashier/manager)."}, status=409)

#         if wanted_role == ROLE_MANAGER and (already_vendor or already_cashier or already_manager):
#             return Response({"error": "Ce user a déjà un profil staff (vendor/cashier/manager)."}, status=409)

#         # 8) Assigner / corriger le rôle métier (IMPORTANT)
#         if wanted_role == ROLE_VENDOR:
#             user.user_role = role_vendor
#         elif wanted_role == ROLE_CASHIER:
#             user.user_role = role_cashier
#         else:  # manager
#             user.user_role = role_manager

#         user.save(update_fields=["user_role"])

#         # 9) Création du staff (race-safe)
#         try:
#             staff = Model.objects.create(
#                 user=user,
#                 bijouterie=bijouterie,
#             )
#         except IntegrityError:
#             return Response(
#                 {"error": "Conflit de création (profil staff déjà existant)."},
#                 status=status.HTTP_409_CONFLICT,
#             )

#         return Response(
#             {
#                 "staff_type": wanted_role,
#                 "staff": OutSer(staff).data,
#                 "user": UserSerializer(user).data,
#                 "message": "✅ Staff créé avec succès",
#             },
#             status=status.HTTP_201_CREATED,
#         )

# # class UpdateStaffView(APIView):
# #     """
# #     Met à jour un staff (manager / cashier) :
# #       - email (User)
# #       - bijouterie (via son nom)
# #       - verifie / raison_desactivation

# #     Règles d'accès :
# #       - Admin : peut modifier n'importe quel manager/caissier
# #       - Manager : ne peut modifier que les staff (manager ou caissier)
# #                   rattachés à **sa propre bijouterie**
# #     """
# #     permission_classes = [IsAuthenticated, IsAdminOrManager]

# #     @swagger_auto_schema(
# #         operation_summary="Mettre à jour un staff (manager / caissier)",
# #         operation_description=(
# #             "Met à jour un staff **manager ou caissier**.\n\n"
# #             "- `role`: `manager` ou `cashier`\n"
# #             "- `bijouterie_nom`: nom de la bijouterie à rattacher\n\n"
# #             "Un **manager** ne peut modifier que les staff de **sa** bijouterie."
# #         ),
# #         request_body=UpdateStaffSerializer,
# #         responses={
# #             200: openapi.Response("Staff mis à jour"),
# #             400: "Requête invalide",
# #             403: "Accès refusé",
# #             404: "Staff introuvable",
# #         },
# #         tags=["Staff"],
# #     )
# #     def put(self, request, staff_id: int):
# #         # 1) On récupère d'abord le rôle ciblé (manager/cashier)
# #         role_payload = request.data.get("role")
# #         if role_payload not in ("manager", "cashier"):
# #             return Response(
# #                 {"error": "Le champ 'role' doit être 'manager' ou 'cashier'."},
# #                 status=status.HTTP_400_BAD_REQUEST,
# #             )

# #         # 2) On détermine le modèle cible
# #         if role_payload == "manager":
# #             StaffModel = Manager
# #             role_label = "manager"
# #         else:
# #             StaffModel = Cashier
# #             role_label = "cashier"

# #         # 3) On récupère l'instance (ou 404)
# #         staff = get_object_or_404(StaffModel, pk=staff_id)

# #         # 4) Règles d'autorisation sur la bijouterie
# #         caller_role = get_role_name(request.user)

# #         if caller_role == ROLE_MANAGER:
# #             # Manager courant
# #             caller_mgr = Manager.objects.filter(user=request.user).select_related("bijouterie").first()
# #             caller_bj_id = getattr(getattr(caller_mgr, "bijouterie", None), "id", None)

# #             if not caller_bj_id:
# #                 return Response(
# #                     {"error": "Votre compte manager n'est rattaché à aucune bijouterie."},
# #                     status=status.HTTP_403_FORBIDDEN,
# #                 )

# #             # 🔒 Un manager ne peut modifier que les staff de SA bijouterie
# #             if staff.bijouterie_id != caller_bj_id:
# #                 return Response(
# #                     {"error": "Vous ne pouvez modifier que les staff de votre bijouterie."},
# #                     status=status.HTTP_403_FORBIDDEN,
# #                 )
# #         # si caller_role == ROLE_ADMIN → pas de restriction supplémentaire

# #         # 5) Sérializer avec contexte pour contrôler l'email
# #         ser = UpdateStaffSerializer(
# #             data=request.data,
# #             context={"user_id": getattr(staff.user, "id", None)},
# #         )
# #         ser.is_valid(raise_exception=True)
# #         data = ser.validated_data

# #         # 6) Mise à jour de l'email (si fourni)
# #         if "email" in data and staff.user:
# #             staff.user.email = data["email"]
# #             staff.user.save(update_fields=["email"])
            
# #         # ✅ Sync du rôle métier dans User.user_role
# #         if staff.user:
# #             role_obj = Role.objects.filter(role=role_payload).first()
# #             if not role_obj:
# #                 return Response(
# #                     {"error": f"Le rôle '{role_payload}' n'existe pas en base."},
# #                     status=status.HTTP_400_BAD_REQUEST,
# #                 )
# #             if getattr(getattr(staff.user, "user_role", None), "role", None) != role_payload:
# #                 staff.user.user_role = role_obj
# #                 staff.user.save(update_fields=["user_role"])

# #         fields_to_update = []

# #         # 7) Mise à jour de la bijouterie via son nom (bijouterie_nom)
# #         if "bijouterie_nom" in data:
# #             bj_instance = data["bijouterie_nom"]  # instance de Bijouterie ou None
# #             staff.bijouterie = bj_instance
# #             fields_to_update.append("bijouterie")

# #         # 8) verifie / raison_desactivation
# #         if "verifie" in data:
# #             staff.verifie = data["verifie"]
# #             fields_to_update.append("verifie")

# #         if "raison_desactivation" in data:
# #             staff.raison_desactivation = data["raison_desactivation"]
# #             fields_to_update.append("raison_desactivation")

# #         if fields_to_update:
# #             staff.save(update_fields=fields_to_update)

# #         return Response(
# #             {
# #                 "message": "Staff mis à jour avec succès",
# #                 "staff_id": staff.id,
# #                 "role": role_label,
# #                 "email": staff.user.email if staff.user else None,
# #                 "bijouterie_id": staff.bijouterie_id,
# #                 "bijouterie_nom": getattr(staff.bijouterie, "nom", None),
# #                 "verifie": staff.verifie,
# #                 "raison_desactivation": staff.raison_desactivation,
# #             },
# #             status=status.HTTP_200_OK,
# #         )


# class UpdateStaffView(APIView):
#     """
#     PUT /api/staff/<staff_id>/
#     Met à jour un staff (manager/cashier) + synchronise user.user_role.
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]

#     @swagger_auto_schema(
#         operation_summary="Mettre à jour un staff (manager / caissier) + sync user_role",
#         operation_description=(
#             "Met à jour un staff **manager ou caissier**.\n\n"
#             "- `role`: `manager` ou `cashier`\n"
#             "- `bijouterie_nom`: nom de la bijouterie\n"
#             "- `verifie`, `raison_desactivation`, `email` optionnels\n\n"
#             "✅ Synchronise automatiquement `user.user_role` selon le type de staff."
#         ),
#         request_body=UpdateStaffSerializer,
#         responses={
#             200: openapi.Response("Staff mis à jour"),
#             400: "Requête invalide",
#             403: "Accès refusé",
#             404: "Staff introuvable",
#         },
#         tags=["Staff"],
#     )
#     @transaction.atomic
#     def put(self, request, staff_id: int):
#         role_payload = (request.data.get("role") or "").strip().lower()
#         if role_payload not in ("manager", "cashier"):
#             return Response(
#                 {"error": "Le champ 'role' doit être 'manager' ou 'cashier'."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         # 1) Modèle ciblé
#         StaffModel = Manager if role_payload == "manager" else Cashier
#         staff = get_object_or_404(StaffModel.objects.select_related("user", "bijouterie"), pk=staff_id)

#         # 2) Règle d'autorisation: un manager ne modifie que sa bijouterie
#         caller_role = get_role_name(request.user)
#         if caller_role == ROLE_MANAGER:
#             caller_mgr = Manager.objects.filter(user=request.user).select_related("bijouterie").first()
#             caller_bj_id = getattr(getattr(caller_mgr, "bijouterie", None), "id", None)

#             if not caller_bj_id:
#                 return Response(
#                     {"error": "Votre compte manager n'est rattaché à aucune bijouterie."},
#                     status=status.HTTP_403_FORBIDDEN,
#                 )
#             if staff.bijouterie_id != caller_bj_id:
#                 return Response(
#                     {"error": "Vous ne pouvez modifier que les staff de votre bijouterie."},
#                     status=status.HTTP_403_FORBIDDEN,
#                 )

#         # 3) Valider payload
#         ser = UpdateStaffSerializer(
#             data=request.data,
#             context={"user_id": getattr(staff.user, "id", None)},
#         )
#         ser.is_valid(raise_exception=True)
#         data = ser.validated_data

#         # 4) Update email
#         if staff.user and "email" in data:
#             staff.user.email = data["email"]
#             staff.user.save(update_fields=["email"])

#         # 5) Update champs staff
#         fields_to_update = []
#         if "bijouterie_nom" in data:
#             staff.bijouterie = data["bijouterie_nom"]
#             fields_to_update.append("bijouterie")

#         if "verifie" in data:
#             staff.verifie = data["verifie"]
#             fields_to_update.append("verifie")

#         if "raison_desactivation" in data:
#             staff.raison_desactivation = data["raison_desactivation"]
#             fields_to_update.append("raison_desactivation")

#         if fields_to_update:
#             staff.save(update_fields=fields_to_update)

#         # ✅ 6) Synchroniser user_role (le point qui te manque)
#         if staff.user:
#             role_obj = Role.objects.filter(role=role_payload).first()
#             if role_obj and staff.user.user_role_id != role_obj.id:
#                 staff.user.user_role = role_obj
#                 staff.user.save(update_fields=["user_role"])

#         return Response(
#             {
#                 "message": "Staff mis à jour avec succès",
#                 "staff_id": staff.id,
#                 "role": role_payload,
#                 "email": staff.user.email if staff.user else None,
#                 "bijouterie_id": staff.bijouterie_id,
#                 "bijouterie_nom": getattr(staff.bijouterie, "nom", None),
#                 "verifie": staff.verifie,
#                 "raison_desactivation": staff.raison_desactivation,
#             },
#             status=status.HTTP_200_OK,
#         )


# class CashierListView(generics.ListAPIView):
#     permission_classes = [permissions.IsAuthenticated]
#     serializer_class = CashierReadSerializer

#     @swagger_auto_schema(
#         manual_parameters=[
#             openapi.Parameter("q", openapi.IN_QUERY, description="Recherche (email, username, nom, prénom, téléphone)", type=openapi.TYPE_STRING),
#             openapi.Parameter("bijouterie_id", openapi.IN_QUERY, description="Filtrer par bijouterie id", type=openapi.TYPE_INTEGER),
#             openapi.Parameter("verifie", openapi.IN_QUERY, description="true/false", type=openapi.TYPE_STRING),
#             openapi.Parameter("start_date", openapi.IN_QUERY, description="Filtrer total_encaisse à partir de (YYYY-MM-DD)", type=openapi.TYPE_STRING),
#             openapi.Parameter("end_date", openapi.IN_QUERY, description="Filtrer total_encaisse jusqu’à (YYYY-MM-DD)", type=openapi.TYPE_STRING),
#         ],
#         responses={200: CashierReadSerializer(many=True)}
#     )
#     def get(self, request, *args, **kwargs):
#         return super().get(request, *args, **kwargs)

#     def get_queryset(self):
#         qs = Cashier.objects.select_related("user", "bijouterie").all()

#         q = self.request.query_params.get("q")
#         if q:
#             qs = qs.filter(
#                 Q(user__email__icontains=q) |
#                 Q(user__username__icontains=q) |
#                 Q(user__first_name__icontains=q) |
#                 Q(user__last_name__icontains=q) |
#                 Q(user__telephone__icontains=q)
#             )

#         bijouterie_id = self.request.query_params.get("bijouterie_id")
#         if bijouterie_id:
#             qs = qs.filter(bijouterie_id=bijouterie_id)

#         verifie = self.request.query_params.get("verifie")
#         if verifie is not None:
#             v = verifie.lower()
#             if v in ("true", "1", "yes", "oui"):
#                 qs = qs.filter(verifie=True)
#             elif v in ("false", "0", "no", "non"):
#                 qs = qs.filter(verifie=False)

#         # ⬇️ Correction ici (singulier)
#         start = _parse_iso_dt(self.request.query_params.get("start_date"))
#         end = _parse_iso_dt(self.request.query_params.get("end_date"))
#         filt = Q()
#         if start:
#             filt &= Q(encaissement__created_at__gte=start)
#         if end:
#             filt &= Q(encaissement__created_at__lte=end)

#         qs = qs.annotate(total_encaisse=Sum("encaissement__montant", filter=filt))
#         return qs.order_by("-id")





# # -------- DÉTAIL / LECTURE + MÀJ --------
# class CashierDetailView(APIView):
#     """
#     GET  /api/cashiers/<int:id>/
#     GET  /api/cashiers/by-slug/<slug:slug>/
#     PATCH/PUT idem (CashierUpdateSerializer)
#     """
#     permission_classes = [permissions.IsAuthenticated]

#     def _get_obj(self, **kwargs):
#         cashier_id = kwargs.get("id") or kwargs.get("pk")
#         slug = kwargs.get("slug") or self.request.query_params.get("slug")
#         base_qs = Cashier.objects.select_related("user", "bijouterie")

#         # facultatif : annotate total via query params
#         start = _parse_iso_dt(self.request.query_params.get("start_date"))
#         end = _parse_iso_dt(self.request.query_params.get("end_date"))
#         filt = Q()
#         if start:
#             filt &= Q(encaissements__created_at__gte=start)
#         if end:
#             filt &= Q(encaissements__created_at__lte=end)
#         base_qs = base_qs.annotate(total_encaisse=Sum("encaissements__montant", filter=filt))

#         if cashier_id:
#             return generics.get_object_or_404(base_qs, pk=cashier_id)
#         if slug:
#             return generics.get_object_or_404(base_qs, user__slug=slug)
#         return generics.get_object_or_404(base_qs, pk=self.request.query_params.get("id"))

#     def _can_update(self, request, cashier: Cashier) -> bool:
#         role = getattr(getattr(request.user, "user_role", None), "role", None)
#         is_admin_or_manager = role in {"admin", "manager"}
#         is_owner = cashier.user_id == request.user.id
#         return bool(is_admin_or_manager or is_owner)

#     @swagger_auto_schema(
#         manual_parameters=[
#             openapi.Parameter("slug", openapi.IN_QUERY, description="(optionnel) user.slug si pas d'id dans l'URL", type=openapi.TYPE_STRING),
#             openapi.Parameter("start_date", openapi.IN_QUERY, description="Filtrer total_encaisse à partir de (YYYY-MM-DD)", type=openapi.TYPE_STRING),
#             openapi.Parameter("end_date", openapi.IN_QUERY, description="Filtrer total_encaisse jusqu’à (YYYY-MM-DD)", type=openapi.TYPE_STRING),
#         ],
#         responses={200: CashierReadSerializer}
#     )
#     def get(self, request, *args, **kwargs):
#         cashier = self._get_obj(**kwargs)
#         return Response(CashierReadSerializer(cashier).data)

#     @swagger_auto_schema(request_body=CashierUpdateSerializer, responses={200: CashierReadSerializer, 403: "Access Denied"})
#     def patch(self, request, *args, **kwargs):
#         cashier = self._get_obj(**kwargs)
#         if not self._can_update(request, cashier):
#             return Response({"detail": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
#         s = CashierUpdateSerializer(cashier, data=request.data, partial=True)
#         s.is_valid(raise_exception=True)
#         s.save()
#         return Response(CashierReadSerializer(cashier).data)

#     @swagger_auto_schema(request_body=CashierUpdateSerializer, responses={200: CashierReadSerializer, 403: "Access Denied"})
#     def put(self, request, *args, **kwargs):
#         cashier = self._get_obj(**kwargs)
#         if not self._can_update(request, cashier):
#             return Response({"detail": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
#         s = CashierUpdateSerializer(cashier, data=request.data, partial=False)
#         s.is_valid(raise_exception=True)
#         s.save()
#         return Response(CashierReadSerializer(cashier).data)

from django.db.models import Count
# staff/views.py
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.permissions import IsAdminOrManagerOrVendor
from backend.roles import (ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR,
                           get_role_name)
from staff.models import Cashier, Manager
from staff.serializers import (CreateStaffUnifiedSerializer,
                               StaffDashboardResponseSerializer,
                               StaffDetailUnifiedSerializer,
                               StaffUnifiedListItemSerializer,
                               UpdateStaffUnifiedSerializer)
from staff.services import create_staff_member, update_staff_member
from vendor.models import Vendor


class CreateStaffUnifiedView(APIView):
    """
    API unique de création de staff.

    - admin   : manager / vendor / cashier
    - manager : vendor / cashier
    """
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Créer un staff (manager, vendor, cashier) via une API unique",
        operation_description=(
            "Crée un staff à partir d'un utilisateur existant ou crée le user si nécessaire.\n\n"
            "- admin   : peut créer manager, vendor, cashier\n"
            "- manager : peut créer vendor, cashier\n"
        ),
        request_body=CreateStaffUnifiedSerializer,
        responses={
            201: openapi.Response("Staff créé"),
            400: "Erreur de validation",
            403: "Accès refusé",
            409: "Conflit",
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
                password=data.get("password"),
                first_name=data.get("first_name", ""),
                last_name=data.get("last_name", ""),
                bijouterie=data["bijouterie_nom"],
                verifie=data.get("verifie", True),
                raison_desactivation=data.get("raison_desactivation"),
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
        bj = getattr(staff, "bijouterie", None)

        return Response(
            {
                "message": "✅ Staff créé avec succès",
                "staff_type": result.staff_type,
                "staff": {
                    "id": staff.id,
                    "verifie": staff.verifie,
                    "raison_desactivation": staff.raison_desactivation,
                    "bijouterie": {
                        "id": bj.id,
                        "nom": bj.nom,
                    } if bj else None,
                    "created_at": staff.created_at,
                    "updated_at": staff.updated_at,
                },
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "role": getattr(getattr(user, "user_role", None), "role", None),
                },
            },
            status=status.HTTP_201_CREATED,
        )
        


class UpdateStaffUnifiedView(APIView):
    """
    API unique de mise à jour de staff.
    """
    permission_classes = [permissions.IsAuthenticated]

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
                            "bijouterie": {
                                "id": 2,
                                "nom": "Rio-Gold Centre"
                            },
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
        bj = getattr(staff, "bijouterie", None)

        return Response(
            {
                "message": "✅ Staff mis à jour avec succès",
                "staff_type": result.staff_type,
                "staff": {
                    "id": staff.id,
                    "verifie": staff.verifie,
                    "raison_desactivation": staff.raison_desactivation,
                    "bijouterie": {
                        "id": bj.id,
                        "nom": bj.nom,
                    } if bj else None,
                    "created_at": staff.created_at,
                    "updated_at": staff.updated_at,
                },
                "user": {
                    "id": user.id if user else None,
                    "email": user.email if user else None,
                    "first_name": user.first_name if user else "",
                    "last_name": user.last_name if user else "",
                    "role": getattr(getattr(user, "user_role", None), "role", None) if user else None,
                },
            },
            status=status.HTTP_200_OK,
        )

    def _get_target_user_id(self, role, staff_id):
        from backend.roles import ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR
        from staff.models import Cashier, Manager
        from vendor.models import Vendor

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
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_id="listUnifiedStaff",
        operation_summary="Lister tous les staff (manager, vendeur, caissier)",
        operation_description=(
            "Cette route retourne une liste unifiée des profils staff.\n\n"

            "### Règles d'accès\n"
            "- **Admin** : voit tous les staff\n"
            "- **Manager** : voit uniquement les staff de ses bijouteries\n\n"

            "### URL principale\n"
            "- `GET /api/staff/list/`\n\n"

            "### Filtres disponibles\n"
            "- `role` : filtrer par type de staff (`manager`, `vendor`, `cashier`)\n"
            "- `bijouterie_nom` : filtrer par nom de bijouterie\n"
            "- `email` : filtrer par email utilisateur\n\n"

            "### Exemples d'utilisation\n"
            "1. **Lister tous les staff**\n"
            "   - `GET /api/staff/list/`\n\n"

            "2. **Lister uniquement les vendeurs**\n"
            "   - `GET /api/staff/list/?role=vendor`\n\n"

            "3. **Lister uniquement les caissiers**\n"
            "   - `GET /api/staff/list/?role=cashier`\n\n"

            "4. **Lister uniquement les managers**\n"
            "   - `GET /api/staff/list/?role=manager`\n\n"

            "5. **Filtrer par bijouterie**\n"
            "   - `GET /api/staff/list/?bijouterie_nom=Rio-Gold`\n\n"

            "6. **Filtrer par email**\n"
            "   - `GET /api/staff/list/?email=test@example.com`\n\n"

            "7. **Combiner plusieurs filtres**\n"
            "   - `GET /api/staff/list/?role=vendor&bijouterie_nom=Rio-Gold&email=vendor@example.com`\n\n"

            "### Structure de réponse\n"
            "Chaque élément contient :\n"
            "- `staff_id`\n"
            "- `role`\n"
            "- `user_id`\n"
            "- `email`\n"
            "- `first_name`\n"
            "- `last_name`\n"
            "- `verifie`\n"
            "- `raison_desactivation`\n"
            "- `bijouterie_id`\n"
            "- `bijouterie_nom`\n"
            "- `created_at`\n"
            "- `updated_at`\n"
        ),
        manual_parameters=[
            openapi.Parameter(
                name="role",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                enum=[ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER],
                required=False,
                description=(
                    "Filtrer par type de staff.\n\n"
                    "- `manager` : retourne seulement les managers\n"
                    "- `vendor` : retourne seulement les vendeurs\n"
                    "- `cashier` : retourne seulement les caissiers"
                ),
            ),
            openapi.Parameter(
                name="bijouterie_nom",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
                description="Filtrer les staff par nom de bijouterie (recherche partielle).",
            ),
            openapi.Parameter(
                name="email",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
                description="Filtrer les staff par email utilisateur (recherche partielle ou exacte selon ta logique).",
            ),
        ],
        responses={
            200: openapi.Response(
                description="Liste unifiée des staff",
                schema=StaffUnifiedListItemSerializer(many=True),
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
                            "raison_desactivation": "",
                            "bijouterie_id": 2,
                            "bijouterie_nom": "Rio-Gold",
                            "created_at": "2026-04-01T10:15:00Z",
                            "updated_at": "2026-04-01T10:15:00Z"
                        },
                        {
                            "staff_id": 4,
                            "role": "cashier",
                            "user_id": 18,
                            "email": "caissier@example.com",
                            "first_name": "Awa",
                            "last_name": "Diop",
                            "verifie": False,
                            "raison_desactivation": "Contrat terminé",
                            "bijouterie_id": 2,
                            "bijouterie_nom": "Rio-Gold",
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

        items = []

        manager_bj_ids = []
        if caller_role == ROLE_MANAGER:
            manager_profile = (
                Manager.objects
                .prefetch_related("bijouteries")
                .filter(user=request.user)
                .first()
            )
            if not manager_profile:
                return Response([], status=status.HTTP_200_OK)
            manager_bj_ids = list(manager_profile.bijouteries.values_list("id", flat=True))
            if not manager_bj_ids:
                return Response([], status=status.HTTP_200_OK)

        def serialize_staff_queryset(qs, role_name):
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
                    "bijouterie_id": getattr(bj, "id", None),
                    "bijouterie_nom": getattr(bj, "nom", None),
                    "created_at": obj.created_at,
                    "updated_at": obj.updated_at,
                })
            return rows

        if role_filter in ("", ROLE_MANAGER):
            qs_manager = Manager.objects.all()
            if caller_role == ROLE_MANAGER:
                qs_manager = qs_manager.filter(bijouterie__id__in=manager_bj_ids)
            if bijouterie_nom:
                qs_manager = qs_manager.filter(bijouterie__nom__icontains=bijouterie_nom)
            if email:
                qs_manager = qs_manager.filter(user__email__icontains=email)
            items.extend(serialize_staff_queryset(qs_manager, ROLE_MANAGER))

        if role_filter in ("", ROLE_VENDOR):
            qs_vendor = Vendor.objects.all()
            if caller_role == ROLE_MANAGER:
                qs_vendor = qs_vendor.filter(bijouterie__id__in=manager_bj_ids)
            if bijouterie_nom:
                qs_vendor = qs_vendor.filter(bijouterie__nom__icontains=bijouterie_nom)
            if email:
                qs_vendor = qs_vendor.filter(user__email__icontains=email)
            items.extend(serialize_staff_queryset(qs_vendor, ROLE_VENDOR))

        if role_filter in ("", ROLE_CASHIER):
            qs_cashier = Cashier.objects.all()
            if caller_role == ROLE_MANAGER:
                qs_cashier = qs_cashier.filter(bijouterie__id__in=manager_bj_ids)
            if bijouterie_nom:
                qs_cashier = qs_cashier.filter(bijouterie__nom__icontains=bijouterie_nom)
            if email:
                qs_cashier = qs_cashier.filter(user__email__icontains=email)
            items.extend(serialize_staff_queryset(qs_cashier, ROLE_CASHIER))

        items.sort(key=lambda x: x["created_at"], reverse=True)

        serializer = StaffUnifiedListItemSerializer(items, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    


class StaffDetailUnifiedView(APIView):
    """
    GET /api/staff/<role>/<staff_id>/

    - admin   : peut voir manager, vendor, cashier
    - manager : peut voir seulement vendor et cashier de ses bijouteries
    """
    permission_classes = [permissions.IsAuthenticated]

    MODEL_MAP = {
        ROLE_MANAGER: Manager,
        ROLE_VENDOR: Vendor,
        ROLE_CASHIER: Cashier,
    }

    @swagger_auto_schema(
        operation_id="staffDetailUnified",
        operation_summary="Détail d'un staff (manager, vendeur, caissier)",
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
                schema=StaffDetailUnifiedSerializer(),
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
                            "bijouterie": {
                                "id": 2,
                                "nom": "Rio-Gold Centre",
                            },
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
            return Response({"detail": "Rôle invalide."}, status=status.HTTP_400_BAD_REQUEST)

        caller_role = get_role_name(request.user)
        if caller_role not in (ROLE_ADMIN, ROLE_MANAGER):
            return Response({"detail": "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        staff = (
            Model.objects
            .select_related("user", "bijouterie")
            .filter(pk=staff_id)
            .first()
        )
        if not staff:
            return Response({"detail": "Staff introuvable."}, status=status.HTTP_404_NOT_FOUND)

        # restriction manager
        if caller_role == ROLE_MANAGER:
            manager_profile = (
                Manager.objects
                .prefetch_related("bijouteries")
                .filter(user=request.user)
                .first()
            )
            if not manager_profile:
                return Response({"detail": "Profil manager introuvable."}, status=status.HTTP_403_FORBIDDEN)

            # un manager ne peut pas voir un autre manager
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
        bj = getattr(staff, "bijouterie", None)

        payload = {
            "staff_id": staff.id,
            "role": role,
            "user": {
                "id": getattr(user, "id", None),
                "email": getattr(user, "email", None),
                "first_name": getattr(user, "first_name", "") or "",
                "last_name": getattr(user, "last_name", "") or "",
                "role": getattr(getattr(user, "user_role", None), "role", None),
            },
            "staff": {
                "id": staff.id,
                "verifie": staff.verifie,
                "raison_desactivation": staff.raison_desactivation,
                "bijouterie": {
                    "id": getattr(bj, "id", None),
                    "nom": getattr(bj, "nom", None),
                } if bj else None,
                "created_at": staff.created_at,
                "updated_at": staff.updated_at,
            },
        }

        serializer = StaffDetailUnifiedSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    
class StaffDashboardView(APIView):
    """
    Dashboard global des staff.

    - admin   : voit tous les staff
    - manager : voit seulement les staff de ses bijouteries
    """
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_id="staffDashboard",
        operation_summary="Dashboard des staff (admin / manager)",
        operation_description=(
            "Retourne un dashboard global des staff.\n\n"
            "### Règles d'accès\n"
            "- **Admin** : voit tous les managers, vendeurs et caissiers\n"
            "- **Manager** : voit seulement les staff de ses bijouteries\n\n"
            "### URL\n"
            "- `GET /api/staff/dashboard/`\n\n"
            "### Réponse\n"
            "- `summary` : compteurs globaux\n"
            "- `by_bijouterie` : répartition des staff par bijouterie\n"
            "- `recent_staff` : derniers staff créés\n"
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

        manager_bj_ids = []

        if caller_role == ROLE_MANAGER:
            manager_profile = (
                Manager.objects
                .prefetch_related("bijouteries")
                .filter(user=request.user)
                .first()
            )
            if not manager_profile:
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
                serializer = StaffDashboardResponseSerializer(empty_payload)
                return Response(serializer.data, status=status.HTTP_200_OK)

            manager_bj_ids = list(manager_profile.bijouteries.values_list("id", flat=True))
            if not manager_bj_ids:
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
                serializer = StaffDashboardResponseSerializer(empty_payload)
                return Response(serializer.data, status=status.HTTP_200_OK)

        # -------------------------
        # Querysets scoped
        # -------------------------
        qs_managers = Manager.objects.select_related("user")
        qs_vendors = Vendor.objects.select_related("user", "bijouterie")
        qs_cashiers = Cashier.objects.select_related("user", "bijouterie")

        if caller_role == ROLE_MANAGER:
            qs_managers = qs_managers.filter(bijouteries__id__in=manager_bj_ids).distinct()
            qs_vendors = qs_vendors.filter(bijouterie__id__in=manager_bj_ids)
            qs_cashiers = qs_cashiers.filter(bijouterie__id__in=manager_bj_ids)

        # -------------------------
        # Summary
        # -------------------------
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

        # -------------------------
        # By bijouterie
        # Pour managers many-to-many:
        # on compte chaque manager dans chaque bijouterie à laquelle il est rattaché
        # -------------------------
        by_bijouterie_map = {}

        # Managers
        managers_grouped = (
            qs_managers
            .values("bijouteries__id", "bijouteries__nom")
            .annotate(managers_count=Count("id", distinct=True))
            .order_by("bijouteries__nom")
        )
        for row in managers_grouped:
            bj_id = row["bijouteries__id"]
            bj_nom = row["bijouteries__nom"]
            if bj_id not in by_bijouterie_map:
                by_bijouterie_map[bj_id] = {
                    "bijouterie_id": bj_id,
                    "bijouterie_nom": bj_nom,
                    "managers_count": 0,
                    "vendors_count": 0,
                    "cashiers_count": 0,
                }
            by_bijouterie_map[bj_id]["managers_count"] = row["managers_count"] or 0

        # Vendors
        vendors_grouped = (
            qs_vendors
            .values("bijouterie_id", "bijouterie__nom")
            .annotate(vendors_count=Count("id"))
            .order_by("bijouterie__nom")
        )
        for row in vendors_grouped:
            bj_id = row["bijouterie_id"]
            bj_nom = row["bijouterie__nom"]
            if bj_id not in by_bijouterie_map:
                by_bijouterie_map[bj_id] = {
                    "bijouterie_id": bj_id,
                    "bijouterie_nom": bj_nom,
                    "managers_count": 0,
                    "vendors_count": 0,
                    "cashiers_count": 0,
                }
            by_bijouterie_map[bj_id]["vendors_count"] = row["vendors_count"] or 0

        # Cashiers
        cashiers_grouped = (
            qs_cashiers
            .values("bijouterie_id", "bijouterie__nom")
            .annotate(cashiers_count=Count("id"))
            .order_by("bijouterie__nom")
        )
        for row in cashiers_grouped:
            bj_id = row["bijouterie_id"]
            bj_nom = row["bijouterie__nom"]
            if bj_id not in by_bijouterie_map:
                by_bijouterie_map[bj_id] = {
                    "bijouterie_id": bj_id,
                    "bijouterie_nom": bj_nom,
                    "managers_count": 0,
                    "vendors_count": 0,
                    "cashiers_count": 0,
                }
            by_bijouterie_map[bj_id]["cashiers_count"] = row["cashiers_count"] or 0

        by_bijouterie = sorted(
            by_bijouterie_map.values(),
            key=lambda x: (x["bijouterie_nom"] or "").lower()
        )

        # -------------------------
        # Recent staff
        # On fusionne managers, vendors, cashiers
        # -------------------------
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
                "bijouterie_id": None,
                "bijouterie_nom": ", ".join(obj.bijouteries.values_list("nom", flat=True)),
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
                "bijouterie_id": getattr(bj, "id", None),
                "bijouterie_nom": getattr(bj, "nom", None),
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
                "bijouterie_id": getattr(bj, "id", None),
                "bijouterie_nom": getattr(bj, "nom", None),
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
    
    
    
