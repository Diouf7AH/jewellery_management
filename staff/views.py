from django.contrib.auth import get_user_model
from django.db import transaction
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import F, Q, Sum
from django.db.models import Sum
from vendor.models import Vendor
from .models import Cashier
from vendor.serializer import (VendorSerializer, CashierSerializer, CreateStaffMemberSerializer, CashierReadSerializer, CashierUpdateSerializer)
from datetime import datetime
from django.utils import timezone
from userauths.serializers import UserSerializer
from rest_framework.permissions import IsAuthenticated
from userauths.models import Role
from django.db import IntegrityError


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
class CreateStaffMemberView(APIView):
    permission_classes = [IsAuthenticated]
    allowed_roles_admin_manager = (ROLE_ADMIN, ROLE_MANAGER)
    MAP = {
        ROLE_VENDOR: (Vendor, VendorSerializer),
        ROLE_CASHIER: (Cashier, CashierSerializer),
    }

    @swagger_auto_schema(
        operation_summary="Créer un staff (vendor ou cashier) à partir d’un utilisateur existant",
        request_body=CreateStaffMemberSerializer,
        responses={201: "Créé", 400: "Erreur", 403: "Accès refusé", 404: "Introuvable", 409: "Conflit"}
    )
    @transaction.atomic
    def post(self, request):
        # 0) Permissions
        caller_role = getattr(getattr(request.user, "user_role", None), "role", None)
        if caller_role not in self.allowed_roles_admin_manager:
            return Response({"error": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

        # 1) Validation
        serializer = CreateStaffMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        email = data["email"].strip()
        bijouterie = data["bijouterie"]                # instance validée par le serializer
        wanted_role = data["role"].lower()

        if wanted_role not in self.MAP:
            return Response({"error": "role doit être 'vendor' ou 'cashier'."}, status=400)
        Model, OutSer = self.MAP[wanted_role]

        # 2) User sous verrou
        user = User.objects.select_for_update().filter(email__iexact=email).first()
        if not user:
            return Response({"error": f"Aucun utilisateur trouvé avec l’email {email}."}, status=404)

        # 3) Rôles présents en base
        role_vendor = Role.objects.filter(role=ROLE_VENDOR).first()
        role_cashier = Role.objects.filter(role=ROLE_CASHIER).first()
        if not role_vendor or not role_cashier:
            return Response({"error": "Les rôles vendor/cashier n’existent pas en base."}, status=400)

        existing_role = getattr(getattr(user, "user_role", None), "role", None)

        # 4) Protections rôle
        if existing_role in self.allowed_roles_admin_manager:
            return Response({"error": f"User déjà {existing_role}, impossible de le transformer."}, status=409)
        if existing_role and existing_role != wanted_role:
            return Response({"error": f"User déjà {existing_role}."}, status=409)

        # 5) Déjà staff ?
        # même type
        if Model.objects.select_for_update().filter(user_id=user.id).exists():
            return Response({"error": f"Ce user est déjà {wanted_role}."}, status=409)
        # autre type
        other_model = Cashier if wanted_role == ROLE_VENDOR else Vendor
        if other_model.objects.select_for_update().filter(user_id=user.id).exists():
            other_name = ROLE_CASHIER if wanted_role == ROLE_VENDOR else ROLE_VENDOR
            return Response({"error": f"Ce user est déjà {other_name}."}, status=409)

        # 6) Assigner le rôle si aucun
        if not existing_role:
            user.user_role = role_vendor if wanted_role == ROLE_VENDOR else role_cashier
            user.save(update_fields=["user_role"])

        # 7) Création (race-safe)
        try:
            staff = Model.objects.create(
                user=user,
                bijouterie=bijouterie,
                # description=data.get("description", "")
            )
        except IntegrityError:
            # création concurrente → conflit explicite
            return Response({"error": "Conflit de création (intégrité)."}, status=409)

        return Response(
            {
                "staff_type": wanted_role,
                "staff": OutSer(staff).data,
                "user": UserSerializer(user).data,
                "message": "✅ Staff créé avec succès"
            },
            status=201
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

