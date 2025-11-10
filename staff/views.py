from datetime import datetime

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import F, Q, Sum
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import generics, permissions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.permissions import IsAdminOrManager, get_role_name
from staff.models import Cashier, Manager
from store.models import Bijouterie
from userauths.models import Role
from vendor.models import Vendor
from vendor.serializer import CashierReadSerializer, CashierUpdateSerializer

from .models import Cashier
from .serializers import (ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR,
                          AddStaffSerializer)

# Create your views here.

# class AddStaffView(APIView):
#     """
#     POST /api/staff/add-staff
#     Crée (ou met à jour) un staff à partir d’un utilisateur existant.
#     - role: "vendor" | "cashier"
#     - vendor requiert bijouterie_id
#     """
#     permission_classes = [permissions.IsAuthenticated, IsAdminOrManager]

#     @swagger_auto_schema(
#         operation_summary="Créer un staff (admin/manager uniquement)",
#         request_body=AddStaffSerializer,
#         responses={201: "Créé", 400: "Erreur", 403: "Accès refusé"},
#     )
#     def post(self, request, *args, **kwargs):
#         ser = AddStaffSerializer(data=request.data)
#         ser.is_valid(raise_exception=True)
#         try:
#             with transaction.atomic():
#                 result = ser.save()  # {"role": "...", "staff": <Vendor|Cashier>}

#                 if result["role"] == "vendor":
#                     vendor = result["staff"]
#                     payload = {
#                         "message": "Staff créé/mis à jour avec succès",
#                         "role": "vendor",
#                         "vendor": VendorOutSerializer(vendor).data,  # ⇦ détail complet
#                     }
#                 else:
#                     cashier = result["staff"]
#                     payload = {
#                         "message": "Staff créé/mis à jour avec succès",
#                         "role": "cashier",
#                         "cashier": {"id": cashier.id, "user_id": cashier.user_id},
#                     }

#                 return Response(payload, status=status.HTTP_201_CREATED)

#         except Bijouterie.DoesNotExist:
#             return Response({"bijouterie_id": "Bijouterie introuvable."}, status=400)
#         except IntegrityError as e:
#             return Response({"detail": "Contrainte d’intégrité", "error": str(e)}, status=400)
#         except Exception as e:
#             return Response({"detail": "Erreur inattendue", "error": str(e)}, status=400)
    
User = get_user_model()

def _get_role_instances():
    r_admin   = Role.objects.filter(role=ROLE_ADMIN).first()
    r_manager = Role.objects.filter(role=ROLE_MANAGER).first()
    r_vendor  = Role.objects.filter(role=ROLE_VENDOR).first()
    r_cashier = Role.objects.filter(role=ROLE_CASHIER).first()
    if not all([r_admin, r_manager, r_vendor, r_cashier]):
        raise ValueError("Rôles admin/manager/vendor/cashier manquants en base.")
    return r_admin, r_manager, r_vendor, r_cashier


class AddStaffView(APIView):
    """
    POST /api/staff/upsert
    - Admin: crée admin OU manager (manager doit avoir bijouterie_id)
    - Manager: crée vendor/cashier pour SA bijouterie (on ignore bijouterie_id du payload)
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminOrManager]

    @swagger_auto_schema(
        operation_summary="Créer un staff selon règles: Admin→(admin|manager), Manager→(vendor|cashier)",
        operation_description=(
            "**Admin** : 'admin' ou 'manager' (manager avec `bijouterie_id` obligatoire)\n"
            "**Manager** : 'vendor' ou 'cashier' rattachés **automatiquement** à sa bijouterie"
        ),
        request_body=AddStaffSerializer,
        responses={
            201: openapi.Response("Créé / Mis à jour"),
            400: openapi.Response("Erreur"),
            403: openapi.Response("Refusé"),
            409: openapi.Response("Conflit"),
        },
        examples={
            "application/json": {
                "role": "manager",
                "email": "manager@exemple.com",
                "bijouterie_id": 2,
                "verifie": True
            }
        },
        tags=["Staff"],
    )
    @transaction.atomic
    def post(self, request):
        ser = AddStaffSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        wanted_role = data["role"]
        email       = data["email"].strip().lower()
        verifie     = True if data.get("verifie") is None else bool(data.get("verifie"))

        caller_role = get_role_name(request.user)  # "admin" si superuser (via ta permission utilitaire)

        # Matrice métiers
        if caller_role == ROLE_ADMIN:
            if wanted_role not in {ROLE_ADMIN, ROLE_MANAGER}:
                return Response({"error": "Un admin ne crée ici que admin ou manager."}, status=403)
        elif caller_role == ROLE_MANAGER:
            if wanted_role not in {ROLE_VENDOR, ROLE_CASHIER}:
                return Response({"error": "Un manager ne crée ici que vendor ou cashier."}, status=403)
        else:
            return Response({"error": "Accès réservé aux admin/manager."}, status=403)

        # Rôles DB
        try:
            r_admin, r_manager, r_vendor, r_cashier = _get_role_instances()
        except ValueError as e:
            return Response({"error": str(e)}, status=400)

        # Déterminer la bijouterie cible
        bj = None
        if caller_role == ROLE_ADMIN and wanted_role == ROLE_MANAGER:
            bj_id = data.get("bijouterie_id")
            if not bj_id:
                return Response({"bijouterie_id": "Obligatoire pour créer un manager."}, status=400)
            bj = Bijouterie.objects.filter(pk=bj_id).first()
            if not bj:
                return Response({"bijouterie_id": "Bijouterie introuvable."}, status=400)

        if caller_role == ROLE_MANAGER and wanted_role in {ROLE_VENDOR, ROLE_CASHIER}:
            # bijouterie du manager appelant
            mgr = Manager.objects.filter(user=request.user).select_related("bijouterie").first()
            if not mgr or not mgr.bijouterie_id:
                return Response({"error": "Manager non rattaché à une bijouterie."}, status=403)
            bj = mgr.bijouterie

        # Upsert user
        user, created_user = User.objects.get_or_create(email=email)

        # Collision de rôle AVANT assignation
        existing_role = getattr(getattr(user, "user_role", None), "role", None)
        if existing_role and existing_role != wanted_role:
            return Response({"error": f"Utilisateur déjà '{existing_role}', impossible de le transformer."}, status=409)

        profile = None

        # Création/affectation selon rôle demandé
        if wanted_role == ROLE_ADMIN:
            user.user_role = r_admin
            user.is_staff = True
            user.is_superuser = True
            user.save()

        elif wanted_role == ROLE_MANAGER:
            user.user_role = r_manager
            user.is_staff = True
            user.save()
            profile, _ = Manager.objects.get_or_create(
                user=user,
                defaults={"bijouterie": bj, **({"verifie": verifie} if hasattr(Manager, "verifie") else {})}
            )
            fields = []
            if getattr(profile, "bijouterie_id", None) != bj.id:
                profile.bijouterie = bj; fields.append("bijouterie")
            if hasattr(profile, "verifie") and getattr(profile, "verifie", True) != verifie:
                profile.verifie = verifie; fields.append("verifie")
            if fields: profile.save(update_fields=fields)

        elif wanted_role == ROLE_VENDOR:
            user.user_role = r_vendor
            user.save()
            profile, _ = Vendor.objects.get_or_create(
                user=user,
                defaults={"bijouterie": bj, **({"verifie": verifie} if hasattr(Vendor, "verifie") else {})}
            )
            fields = []
            if getattr(profile, "bijouterie_id", None) != bj.id:
                profile.bijouterie = bj; fields.append("bijouterie")
            if hasattr(profile, "verifie") and getattr(profile, "verifie", True) != verifie:
                profile.verifie = verifie; fields.append("verifie")
            if fields: profile.save(update_fields=fields)

        else:  # ROLE_CASHIER
            user.user_role = r_cashier
            user.save()
            profile, _ = Cashier.objects.get_or_create(
                user=user,
                defaults={"bijouterie": bj, **({"verifie": verifie} if hasattr(Cashier, "verifie") else {})}
            )
            fields = []
            if getattr(profile, "bijouterie_id", None) != bj.id:
                profile.bijouterie = bj; fields.append("bijouterie")
            if hasattr(profile, "verifie") and getattr(profile, "verifie", True) != verifie:
                profile.verifie = verifie; fields.append("verifie")
            if fields: profile.save(update_fields=fields)

        # Réponse
        payload = {
            "message": "Créé" if created_user else "Mis à jour",
            "role": wanted_role,
            "user": {
                "id": user.id,
                "email": user.email,
                "user_role": getattr(getattr(user, "user_role", None), "role", None),
                "is_staff": getattr(user, "is_staff", False),
                "is_superuser": getattr(user, "is_superuser", False),
            },
            "profile": ({"id": profile.id, "verifie": profile.verifie,"type": wanted_role} if profile else None),
            "bijouterie": ({"id": bj.id, "nom": getattr(bj, "nom", None)} if bj else None),
        }
        return Response(payload, status=201)
    

# User = get_user_model()
# allowed_all_roles = ['admin', 'manager', 'vendeur']
# allowed_roles_admin_manager = ['admin', 'manager',]

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


# User = get_user_model()

# ROLE_ADMIN, ROLE_MANAGER = "admin", "manager"
# ROLE_VENDOR, ROLE_CASHIER = "vendor", "cashier"


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
#         ser = CreateStaffMemberSerializer(data=request.data)
#         ser.is_valid(raise_exception=True)
#         data = ser.validated_data

#         email = data["email"].strip()
#         wanted_role = data["role"].lower()

#         if wanted_role not in self.MAP:
#             return Response({"error": "role doit être 'vendor' ou 'cashier'."}, status=400)
#         Model, OutSer = self.MAP[wanted_role]

#         # 2) User sous verrou
#         user = User.objects.select_for_update().filter(email__iexact=email).first()
#         if not user:
#             return Response({"error": f"Aucun utilisateur trouvé avec l’email {email}."}, status=404)

#         # 3) Rôles en base
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
#         if Model.objects.select_for_update().filter(user_id=user.id).exists():
#             return Response({"error": f"Ce user est déjà {wanted_role}."}, status=409)
#         other_model = Cashier if wanted_role == ROLE_VENDOR else Vendor
#         if other_model.objects.select_for_update().filter(user_id=user.id).exists():
#             other_name = ROLE_CASHIER if wanted_role == ROLE_VENDOR else ROLE_VENDOR
#             return Response({"error": f"Ce user est déjà {other_name}."}, status=409)

#         # 6) Assigner le rôle si aucun
#         if not existing_role:
#             user.user_role = role_vendor if wanted_role == ROLE_VENDOR else role_cashier
#             user.save(update_fields=["user_role"])

#         # 7) Création safe (ne passe bijouterie que si nécessaire et supporté)
#         create_kwargs = {"user": user}

#         # le serializer a déjà validé/chargé bijouterie en instance si fourni
#         bijouterie = data.get("bijouterie")

#         if wanted_role == ROLE_VENDOR:
#             # Vendor DOIT avoir une bijouterie → on la passe
#             if not bijouterie:
#                 return Response({"error": "bijouterie est requise pour le rôle vendor."}, status=400)

#             # s'assurer que le modèle a bien ce champ (évite TypeError)
#             if hasattr(Model, "_meta") and any(f.name == "bijouterie" for f in Model._meta.get_fields()):
#                 create_kwargs["bijouterie"] = bijouterie
#             else:
#                 return Response({"error": "Le modèle Vendor attendu n’a pas de champ 'bijouterie'."}, status=500)
#         else:
#             # cashier : ne JAMAIS passer bijouterie si le modèle ne la supporte pas
#             if hasattr(Model, "_meta") and any(f.name == "bijouterie" for f in Model._meta.get_fields()):
#                 # au cas où ton Cashier a une bijouterie (rare) et qu’elle est fournie
#                 if bijouterie:
#                     create_kwargs["bijouterie"] = bijouterie

#         try:
#             staff = Model.objects.create(**create_kwargs)
#         except IntegrityError:
#             return Response({"error": "Conflit de création (intégrité)."}, status=409)
#         except TypeError as e:
#             # piège classique: bijouterie passée à un modèle qui ne la supporte pas
#             return Response({"error": "TypeError lors de la création du staff", "detail": str(e)}, status=400)
#         except Exception as e:
#             return Response({"error": "Erreur inattendue", "detail": str(e)}, status=400)

#         return Response(
#             {
#                 "staff_type": wanted_role,
#                 "staff": OutSer(staff).data,
#                 "user": UserSerializer(user).data,
#                 "message": "✅ Staff créé avec succès"
#             },
#             status=201
#         )


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

