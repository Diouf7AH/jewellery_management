from datetime import datetime

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import F, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import generics, permissions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.permissions import (ROLE_ADMIN, ROLE_MANAGER, IsAdminOrManager,
                                 get_role_name)
from userauths.models import Role
from userauths.serializers import UserSerializer
from vendor.models import Vendor
from vendor.serializer import (CashierReadSerializer, CashierSerializer,
                               CashierUpdateSerializer, VendorSerializer)

from .models import Cashier, Manager
from .serializers import (CreateStaffMemberSerializer, ManagerSerializer,
                          UpdateStaffSerializer)

# Create your views here.
User = get_user_model()
allowed_all_roles = ['admin', 'manager', 'vendeur']
allowed_roles_admin_manager = ['admin', 'manager',]

def _parse_iso_dt(s: str):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # support YYYY-MM-DD
        try:
            dt = datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt

ROLE_ADMIN, ROLE_MANAGER = "admin", "manager"
ROLE_VENDOR, ROLE_CASHIER = "vendor", "cashier"

# class CreateStaffMemberView(APIView):
#     permission_classes = [IsAuthenticated]
#     allowed_roles_admin_manager = (ROLE_ADMIN, ROLE_MANAGER)
#     MAP = {
#         ROLE_VENDOR: (Vendor, VendorSerializer),
#         ROLE_CASHIER: (Cashier, CashierSerializer),
#     }

#     @swagger_auto_schema(
#         operation_summary="Créer un staff (vendor ou cashier) à partir d’un utilisateur existant",
#         request_body=CreateStaffMemberSerializer,
#         responses={201: "Créé", 400: "Erreur", 403: "Accès refusé", 404: "Introuvable", 409: "Conflit"}
#     )
#     @transaction.atomic
#     def post(self, request):
#         # 0) Permissions
#         caller_role = getattr(getattr(request.user, "user_role", None), "role", None)
#         if caller_role not in self.allowed_roles_admin_manager:
#             return Response({"error": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

#         # 1) Validation
#         serializer = CreateStaffMemberSerializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         data = serializer.validated_data

#         email = data["email"].strip()
#         bijouterie = data["bijouterie"]                # instance validée par le serializer
#         wanted_role = data["role"].lower()

#         if wanted_role not in self.MAP:
#             return Response({"error": "role doit être 'vendor' ou 'cashier'."}, status=400)
#         Model, OutSer = self.MAP[wanted_role]

#         # 2) User sous verrou
#         user = User.objects.select_for_update().filter(email__iexact=email).first()
#         if not user:
#             return Response({"error": f"Aucun utilisateur trouvé avec l’email {email}."}, status=404)

#         # 3) Rôles présents en base
#         role_vendor = Role.objects.filter(role=ROLE_VENDOR).first()
#         role_cashier = Role.objects.filter(role=ROLE_CASHIER).first()
#         if not role_vendor or not role_cashier:
#             return Response({"error": "Les rôles vendor/cashier n’existent pas en base."}, status=400)

#         existing_role = getattr(getattr(user, "user_role", None), "role", None)

#         # 4) Protections rôle
#         if existing_role in self.allowed_roles_admin_manager:
#             return Response({"error": f"User déjà {existing_role}, impossible de le transformer."}, status=409)
#         if existing_role and existing_role != wanted_role:
#             return Response({"error": f"User déjà {existing_role}."}, status=409)

#         # 5) Déjà staff ?
#         # même type
#         if Model.objects.select_for_update().filter(user_id=user.id).exists():
#             return Response({"error": f"Ce user est déjà {wanted_role}."}, status=409)
#         # autre type
#         other_model = Cashier if wanted_role == ROLE_VENDOR else Vendor
#         if other_model.objects.select_for_update().filter(user_id=user.id).exists():
#             other_name = ROLE_CASHIER if wanted_role == ROLE_VENDOR else ROLE_VENDOR
#             return Response({"error": f"Ce user est déjà {other_name}."}, status=409)

#         # 6) Assigner le rôle si aucun
#         if not existing_role:
#             user.user_role = role_vendor if wanted_role == ROLE_VENDOR else role_cashier
#             user.save(update_fields=["user_role"])

#         # 7) Création (race-safe)
#         try:
#             staff = Model.objects.create(
#                 user=user,
#                 bijouterie=bijouterie,
#                 # description=data.get("description", "")
#             )
#         except IntegrityError:
#             # création concurrente → conflit explicite
#             return Response({"error": "Conflit de création (intégrité)."}, status=409)

#         return Response(
#             {
#                 "staff_type": wanted_role,
#                 "staff": OutSer(staff).data,
#                 "user": UserSerializer(user).data,
#                 "message": "✅ Staff créé avec succès"
#             },
#             status=201
#         )



class CreateStaffMemberView(APIView):
    """
    Créer un staff (manager, vendor ou cashier) à partir d’un utilisateur existant :
      - Admin : peut créer manager, vendor, cashier
      - Manager : peut créer vendor, cashier (mais PAS manager)
    """
    permission_classes = [IsAuthenticated]

    # mappage rôle -> (Model, Serializer de sortie)
    MAP = {
        ROLE_VENDOR:  (Vendor,  VendorSerializer),
        ROLE_CASHIER: (Cashier, CashierSerializer),
        ROLE_MANAGER: (Manager, ManagerSerializer),  # tu peux créer un ManagerSerializer dédié si tu veux
    }

    # qui peut créer quoi
    ALLOWED_BY_CALLER = {
        ROLE_ADMIN:   {ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER},
        ROLE_MANAGER: {ROLE_VENDOR, ROLE_CASHIER},   # ⚠️ pas manager
    }

    @swagger_auto_schema(
        operation_summary="Créer un staff (manager, vendor, cashier) pour un utilisateur existant",
        operation_description=(
            "- Admin : peut créer manager, vendor, cashier\n"
            "- Manager : peut créer vendor et cashier uniquement\n\n"
            "Le user doit déjà exister (par son email)."
        ),
        request_body=CreateStaffMemberSerializer,
        responses={
            201: "Créé",
            400: "Erreur",
            403: "Accès refusé",
            404: "Utilisateur introuvable",
            409: "Conflit de rôle ou staff déjà existant",
        },
        tags=["Staff"],
    )
    @transaction.atomic
    def post(self, request):
        # 0) Rôle de l'appelant
        caller_role = getattr(getattr(request.user, "user_role", None), "role", None)

        if caller_role not in (ROLE_ADMIN, ROLE_MANAGER):
            return Response(
                {"error": "⛔ Accès réservé aux rôles admin et manager."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 1) Validation du payload
        ser = CreateStaffMemberSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        email = data["email"]
        bijouterie = data["bijouterie"]          # instance Bijouterie
        wanted_role = data["role"].lower()

        # 2) Vérifier si le caller a le droit de créer CE rôle précis
        allowed_targets = self.ALLOWED_BY_CALLER.get(caller_role, set())
        if wanted_role not in allowed_targets:
            return Response(
                {"error": f"⛔ Un {caller_role} ne peut pas créer un staff de type {wanted_role}."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 3) Vérifier que le rôle demandé est bien géré
        if wanted_role not in self.MAP:
            return Response({"error": "role doit être 'vendor', 'cashier' ou 'manager'."}, status=400)

        Model, OutSer = self.MAP[wanted_role]

        # 4) Charger le user sous verrou
        user = User.objects.select_for_update().filter(email__iexact=email).first()
        if not user:
            return Response(
                {"error": f"Aucun utilisateur trouvé avec l’email {email}."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 5) Rôles présents en base
        role_vendor  = Role.objects.filter(role=ROLE_VENDOR).first()
        role_cashier = Role.objects.filter(role=ROLE_CASHIER).first()
        role_manager = Role.objects.filter(role=ROLE_MANAGER).first()

        if not all([role_vendor, role_cashier, role_manager]):
            return Response(
                {"error": "Les rôles vendor/manager/cashier n’existent pas en base."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing_role = getattr(getattr(user, "user_role", None), "role", None)

        # 6) Protection : on ne transforme pas un admin/manager existant
        if existing_role in (ROLE_ADMIN,):
            return Response(
                {"error": f"User déjà {existing_role}, impossible de le transformer en staff."},
                status=status.HTTP_409_CONFLICT,
            )

        # 7) Vérifier qu’il n’a pas déjà un autre staff
        #    - on empêche d’avoir Vendor + Cashier + Manager en même temps

        already_vendor  = Vendor.objects.select_for_update().filter(user_id=user.id).exists()
        already_cashier = Cashier.objects.select_for_update().filter(user_id=user.id).exists()
        already_manager = Manager.objects.select_for_update().filter(user_id=user.id).exists()

        if wanted_role == ROLE_VENDOR and (already_vendor or already_cashier or already_manager):
            return Response({"error": "Ce user a déjà un profil staff (vendor/cashier/manager)."}, status=409)

        if wanted_role == ROLE_CASHIER and (already_vendor or already_cashier or already_manager):
            return Response({"error": "Ce user a déjà un profil staff (vendor/cashier/manager)."}, status=409)

        if wanted_role == ROLE_MANAGER and (already_vendor or already_cashier or already_manager):
            return Response({"error": "Ce user a déjà un profil staff (vendor/cashier/manager)."}, status=409)

        # 8) Assigner le rôle métier si absent
        if not existing_role:
            if wanted_role == ROLE_VENDOR:
                user.user_role = role_vendor
            elif wanted_role == ROLE_CASHIER:
                user.user_role = role_cashier
            else:  # manager
                user.user_role = role_manager
            user.save(update_fields=["user_role"])

        # 9) Création du staff (race-safe)
        try:
            staff = Model.objects.create(
                user=user,
                bijouterie=bijouterie,
            )
        except IntegrityError:
            return Response(
                {"error": "Conflit de création (profil staff déjà existant)."},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            {
                "staff_type": wanted_role,
                "staff": OutSer(staff).data,
                "user": UserSerializer(user).data,
                "message": "✅ Staff créé avec succès",
            },
            status=status.HTTP_201_CREATED,
        )



# class UpdateStaffView(APIView):
#     """
#     Met à jour un staff (manager / vendor / cashier) :
#       - email (User)
#       - bijouterie (via son nom)
#       - verifie / raison_desactivation
#     Accès : admin + manager uniquement.
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]

#     @swagger_auto_schema(
#         operation_summary="Mettre à jour un staff (admin/manager seulement)",
#         request_body=UpdateStaffSerializer,
#         responses={
#             200: openapi.Response("Staff mis à jour"),
#             400: "Requête invalide",
#             403: "Accès refusé",
#             404: "Staff introuvable",
#         },
#         tags=["Staff"],
#     )
#     def put(self, request, staff_id):
#         # 👉 ici j’exemple avec Manager, tu peux adapter pour Vendor/Cashier
#         staff = get_object_or_404(Cashier, pk=staff_id)   # ou Vendor / Cashier / Manager

#         ser = UpdateStaffSerializer(
#             data=request.data,
#             context={"user_id": getattr(staff.user, "id", None)},
#         )
#         ser.is_valid(raise_exception=True)
#         data = ser.validated_data

#         # ---- Email user ----
#         if "email" in data and staff.user:
#             staff.user.email = data["email"]
#             staff.user.save(update_fields=["email"])

#         # ---- Bijouterie via nom ----
#         if "bijouterie_nom" in data:
#             bj = data["bijouterie_nom"]  # instance de Bijouterie ou None
#             staff.bijouterie = bj

#         fields_to_update = ["bijouterie"] if "bijouterie_nom" in data else []

#         # ---- verifie / raison_desactivation ----
#         if "verifie" in data:
#             staff.verifie = data["verifie"]
#             fields_to_update.append("verifie")

#         if "raison_desactivation" in data:
#             staff.raison_desactivation = data["raison_desactivation"]
#             fields_to_update.append("raison_desactivation")

#         if fields_to_update:
#             staff.save(update_fields=fields_to_update)

#         return Response(
#             {
#                 "message": "Staff mis à jour avec succès",
#                 "staff_id": staff.id,
#                 "role": "manager",  # ou "vendor"/"cashier" selon le modèle
#                 "email": staff.user.email if staff.user else None,
#                 "bijouterie_id": staff.bijouterie_id,
#                 "bijouterie_nom": getattr(staff.bijouterie, "nom", None),
#                 "verifie": staff.verifie,
#                 "raison_desactivation": staff.raison_desactivation,
#             },
#             status=status.HTTP_200_OK,
#         )

class UpdateStaffView(APIView):
    """
    Met à jour un staff (manager / cashier) :
      - email (User)
      - bijouterie (via son nom)
      - verifie / raison_desactivation

    Règles d'accès :
      - Admin : peut modifier n'importe quel manager/caissier
      - Manager : ne peut modifier que les staff (manager ou caissier)
                  rattachés à **sa propre bijouterie**
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]

    @swagger_auto_schema(
        operation_summary="Mettre à jour un staff (manager / caissier)",
        operation_description=(
            "Met à jour un staff **manager ou caissier**.\n\n"
            "- `role`: `manager` ou `cashier`\n"
            "- `bijouterie_nom`: nom de la bijouterie à rattacher\n\n"
            "Un **manager** ne peut modifier que les staff de **sa** bijouterie."
        ),
        request_body=UpdateStaffSerializer,
        responses={
            200: openapi.Response("Staff mis à jour"),
            400: "Requête invalide",
            403: "Accès refusé",
            404: "Staff introuvable",
        },
        tags=["Staff"],
    )
    def put(self, request, staff_id: int):
        # 1) On récupère d'abord le rôle ciblé (manager/cashier)
        role_payload = request.data.get("role")
        if role_payload not in ("manager", "cashier"):
            return Response(
                {"error": "Le champ 'role' doit être 'manager' ou 'cashier'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2) On détermine le modèle cible
        if role_payload == "manager":
            StaffModel = Manager
            role_label = "manager"
        else:
            StaffModel = Cashier
            role_label = "cashier"

        # 3) On récupère l'instance (ou 404)
        staff = get_object_or_404(StaffModel, pk=staff_id)

        # 4) Règles d'autorisation sur la bijouterie
        caller_role = get_role_name(request.user)

        if caller_role == ROLE_MANAGER:
            # Manager courant
            caller_mgr = Manager.objects.filter(user=request.user).select_related("bijouterie").first()
            caller_bj_id = getattr(getattr(caller_mgr, "bijouterie", None), "id", None)

            if not caller_bj_id:
                return Response(
                    {"error": "Votre compte manager n'est rattaché à aucune bijouterie."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            # 🔒 Un manager ne peut modifier que les staff de SA bijouterie
            if staff.bijouterie_id != caller_bj_id:
                return Response(
                    {"error": "Vous ne pouvez modifier que les staff de votre bijouterie."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        # si caller_role == ROLE_ADMIN → pas de restriction supplémentaire

        # 5) Sérializer avec contexte pour contrôler l'email
        ser = UpdateStaffSerializer(
            data=request.data,
            context={"user_id": getattr(staff.user, "id", None)},
        )
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        # 6) Mise à jour de l'email (si fourni)
        if "email" in data and staff.user:
            staff.user.email = data["email"]
            staff.user.save(update_fields=["email"])

        fields_to_update = []

        # 7) Mise à jour de la bijouterie via son nom (bijouterie_nom)
        if "bijouterie_nom" in data:
            bj_instance = data["bijouterie_nom"]  # instance de Bijouterie ou None
            staff.bijouterie = bj_instance
            fields_to_update.append("bijouterie")

        # 8) verifie / raison_desactivation
        if "verifie" in data:
            staff.verifie = data["verifie"]
            fields_to_update.append("verifie")

        if "raison_desactivation" in data:
            staff.raison_desactivation = data["raison_desactivation"]
            fields_to_update.append("raison_desactivation")

        if fields_to_update:
            staff.save(update_fields=fields_to_update)

        return Response(
            {
                "message": "Staff mis à jour avec succès",
                "staff_id": staff.id,
                "role": role_label,
                "email": staff.user.email if staff.user else None,
                "bijouterie_id": staff.bijouterie_id,
                "bijouterie_nom": getattr(staff.bijouterie, "nom", None),
                "verifie": staff.verifie,
                "raison_desactivation": staff.raison_desactivation,
            },
            status=status.HTTP_200_OK,
        )
        


class CashierListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CashierReadSerializer

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter("q", openapi.IN_QUERY, description="Recherche (email, username, nom, prénom, téléphone)", type=openapi.TYPE_STRING),
            openapi.Parameter("bijouterie_id", openapi.IN_QUERY, description="Filtrer par bijouterie id", type=openapi.TYPE_INTEGER),
            openapi.Parameter("verifie", openapi.IN_QUERY, description="true/false", type=openapi.TYPE_STRING),
            openapi.Parameter("start_date", openapi.IN_QUERY, description="Filtrer total_encaisse à partir de (YYYY-MM-DD)", type=openapi.TYPE_STRING),
            openapi.Parameter("end_date", openapi.IN_QUERY, description="Filtrer total_encaisse jusqu’à (YYYY-MM-DD)", type=openapi.TYPE_STRING),
        ],
        responses={200: CashierReadSerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        qs = Cashier.objects.select_related("user", "bijouterie").all()

        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(user__email__icontains=q) |
                Q(user__username__icontains=q) |
                Q(user__first_name__icontains=q) |
                Q(user__last_name__icontains=q) |
                Q(user__telephone__icontains=q)
            )

        bijouterie_id = self.request.query_params.get("bijouterie_id")
        if bijouterie_id:
            qs = qs.filter(bijouterie_id=bijouterie_id)

        verifie = self.request.query_params.get("verifie")
        if verifie is not None:
            v = verifie.lower()
            if v in ("true", "1", "yes", "oui"):
                qs = qs.filter(verifie=True)
            elif v in ("false", "0", "no", "non"):
                qs = qs.filter(verifie=False)

        # ⬇️ Correction ici (singulier)
        start = _parse_iso_dt(self.request.query_params.get("start_date"))
        end = _parse_iso_dt(self.request.query_params.get("end_date"))
        filt = Q()
        if start:
            filt &= Q(encaissement__created_at__gte=start)
        if end:
            filt &= Q(encaissement__created_at__lte=end)

        qs = qs.annotate(total_encaisse=Sum("encaissement__montant", filter=filt))
        return qs.order_by("-id")





# -------- DÉTAIL / LECTURE + MÀJ --------
class CashierDetailView(APIView):
    """
    GET  /api/cashiers/<int:id>/
    GET  /api/cashiers/by-slug/<slug:slug>/
    PATCH/PUT idem (CashierUpdateSerializer)
    """
    permission_classes = [permissions.IsAuthenticated]

    def _get_obj(self, **kwargs):
        cashier_id = kwargs.get("id") or kwargs.get("pk")
        slug = kwargs.get("slug") or self.request.query_params.get("slug")
        base_qs = Cashier.objects.select_related("user", "bijouterie")

        # facultatif : annotate total via query params
        start = _parse_iso_dt(self.request.query_params.get("start_date"))
        end = _parse_iso_dt(self.request.query_params.get("end_date"))
        filt = Q()
        if start:
            filt &= Q(encaissements__created_at__gte=start)
        if end:
            filt &= Q(encaissements__created_at__lte=end)
        base_qs = base_qs.annotate(total_encaisse=Sum("encaissements__montant", filter=filt))

        if cashier_id:
            return generics.get_object_or_404(base_qs, pk=cashier_id)
        if slug:
            return generics.get_object_or_404(base_qs, user__slug=slug)
        return generics.get_object_or_404(base_qs, pk=self.request.query_params.get("id"))

    def _can_update(self, request, cashier: Cashier) -> bool:
        role = getattr(getattr(request.user, "user_role", None), "role", None)
        is_admin_or_manager = role in {"admin", "manager"}
        is_owner = cashier.user_id == request.user.id
        return bool(is_admin_or_manager or is_owner)

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter("slug", openapi.IN_QUERY, description="(optionnel) user.slug si pas d'id dans l'URL", type=openapi.TYPE_STRING),
            openapi.Parameter("start_date", openapi.IN_QUERY, description="Filtrer total_encaisse à partir de (YYYY-MM-DD)", type=openapi.TYPE_STRING),
            openapi.Parameter("end_date", openapi.IN_QUERY, description="Filtrer total_encaisse jusqu’à (YYYY-MM-DD)", type=openapi.TYPE_STRING),
        ],
        responses={200: CashierReadSerializer}
    )
    def get(self, request, *args, **kwargs):
        cashier = self._get_obj(**kwargs)
        return Response(CashierReadSerializer(cashier).data)

    @swagger_auto_schema(request_body=CashierUpdateSerializer, responses={200: CashierReadSerializer, 403: "Access Denied"})
    def patch(self, request, *args, **kwargs):
        cashier = self._get_obj(**kwargs)
        if not self._can_update(request, cashier):
            return Response({"detail": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        s = CashierUpdateSerializer(cashier, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(CashierReadSerializer(cashier).data)

    @swagger_auto_schema(request_body=CashierUpdateSerializer, responses={200: CashierReadSerializer, 403: "Access Denied"})
    def put(self, request, *args, **kwargs):
        cashier = self._get_obj(**kwargs)
        if not self._can_update(request, cashier):
            return Response({"detail": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)
        s = CashierUpdateSerializer(cashier, data=request.data, partial=False)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(CashierReadSerializer(cashier).data)

