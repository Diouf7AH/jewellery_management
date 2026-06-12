from textwrap import dedent

from django.core.exceptions import ValidationError
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.permissions import ROLE_ADMIN  # ton permission actuel
from backend.permissions import (ROLE_MANAGER, ROLE_VENDOR, IsAdminOrManager,
                                 IsAdminOrManagerOrVendor, get_role_name)
from backend.query_scopes import scope_bijouterie_q
from backend.roles import ROLE_ADMIN, ROLE_MANAGER, get_role_name
from vendor.models import Vendor

from .models import Stock
from .serializers import (ReserveToVendorInSerializer,
                          ReserveToVendorOutSerializer, StockSerializer)
from .services.reserve_to_vendor_service import transfer_reserve_to_vendor

allowed_roles = ['admin', 'manager', 'vendeur']


# class StockListView(APIView):
#     """
#     GET /api/stock/?status=in_stock|reserved|allocated|all

#     - admin   : voit tout (réserve + bijouteries)
#     - manager : voit uniquement sa bijouterie
#     - vendor  : voit uniquement sa bijouterie
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManagerOrSelfVendor]

#     @swagger_auto_schema(
#         operation_summary="Lister les stocks (admin : tout | manager/vendor : leur bijouterie)",
#         operation_description=dedent("""
#             Retourne les lignes de stock **sans pagination**.

#             **Règles d'accès**
#             - admin   : accès à tout
#             - manager : accès uniquement aux stocks de sa bijouterie
#             - vendor  : accès uniquement aux stocks de sa bijouterie
            
#             * En une phrase :
#             - reserved = stock central non affecté
#             - in_stock = tout ce qui est réellement disponible, où qu’il soit
            
#             **Filtre `status`**
#             - `reserved`  : réserve (bijouterie=NULL, disponible>0, allouée=0) (admin only)
#             - `allocated` : lignes affectées à une bijouterie (bijouterie!=NULL)
#             - `in_stock`  : tout ce qui a disponible>0 (réserve + bijouteries)
#             - `all`       : sans filtre
#         """),
#         manual_parameters=[
#             openapi.Parameter(
#                 name="status",
#                 in_=openapi.IN_QUERY,
#                 required=False,
#                 type=openapi.TYPE_STRING,
#                 enum=list(STATUS_CHOICES),
#                 default="in_stock",
#                 description="Filtre par statut",
#             ),
#         ],
#         responses={200: openapi.Response("Liste des stocks", StockSerializer(many=True))},
#         tags=["Stock"],
#     )
#     def get(self, request, *args, **kwargs):
#         # 1) Paramètre
#         status_param = request.query_params.get("status", "in_stock")
#         if status_param not in STATUS_CHOICES:
#             raise ValidationError({"status": f"Valeur invalide. Choisir parmi {STATUS_CHOICES}."})

#         # 2) Base queryset
#         qs = Stock.objects.select_related("produit_line", "bijouterie").order_by("-id")

#         # 3) Scope par rôle
#         role = get_role_name(request.user)

#         if role == ROLE_MANAGER:
#             bj_id = get_manager_bijouterie_id(request.user)
#             qs = qs.filter(bijouterie_id=bj_id) if bj_id else qs.none()

#         elif role == ROLE_VENDOR:
#             bj_id = get_vendor_bijouterie_id(request.user)
#             qs = qs.filter(bijouterie_id=bj_id) if bj_id else qs.none()


#         # ROLE_ADMIN => pas de filtre

#         # 4) Filtre status
#         if status_param == "reserved":
#             # Réserve = globale => admin only (recommandé)
#             if role != ROLE_ADMIN:
#                 return Response({"detail": "Accès refusé au stock réserve."}, status=403)
#             qs = qs.filter(bijouterie__isnull=True, quantite_disponible__gt=0)

#         elif status_param == "allocated":
#             qs = qs.filter(bijouterie__isnull=False)

#         elif status_param == "in_stock":
#             qs = qs.filter(quantite_disponible__gt=0)

#         # "all" => pas de filtre

#         return Response(StockSerializer(qs, many=True).data)
    


# STATUS_CHOICES = ("in_stock", "reserved", "allocated", "all")


# class StockListView(APIView):
#     """
#     GET /api/stock/?status=in_stock|reserved|allocated|all

#     - admin   : voit tout (réserve + bijouteries)
#     - manager : voit uniquement sa bijouterie
#     - vendor  : voit uniquement sa bijouterie
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManagerOrSelfVendor]

#     @swagger_auto_schema(
#         operation_summary="Lister les stocks (admin : tout | manager/vendor : leur bijouterie)",
#         operation_description=dedent("""
#             Retourne les lignes de stock **sans pagination**.

#             **Règles d'accès**
#             - admin   : accès à tout
#             - manager : accès uniquement aux stocks de sa bijouterie
#             - vendor  : accès uniquement aux stocks de sa bijouterie

#             * En une phrase :
#             - reserved = stock central non affecté
#             - in_stock = tout ce qui est réellement disponible, où qu’il soit

#             **Filtre `status`**
#             - `reserved`  : réserve (bijouterie=NULL, disponible>0, allouée=0) (admin only)
#             - `allocated` : lignes affectées à une bijouterie (bijouterie!=NULL)
#             - `in_stock`  : tout ce qui a disponible>0 (réserve + bijouteries)
#             - `all`       : sans filtre
#         """),
#         manual_parameters=[
#             openapi.Parameter(
#                 name="status",
#                 in_=openapi.IN_QUERY,
#                 required=False,
#                 type=openapi.TYPE_STRING,
#                 enum=list(STATUS_CHOICES),
#                 default="in_stock",
#                 description="Filtre par statut",
#             ),
#         ],
#         responses={200: openapi.Response("Liste des stocks", StockSerializer(many=True))},
#         tags=["Stock"],
#     )
#     def get(self, request, *args, **kwargs):
#         # 1) Paramètre status
#         status_param = request.query_params.get("status", "in_stock")
#         if status_param not in STATUS_CHOICES:
#             raise ValidationError({"status": f"Valeur invalide. Choisir parmi {STATUS_CHOICES}."})

#         # 2) Rôle + règle admin-only pour la réserve (fail fast)
#         role = get_role_name(request.user)
#         if status_param == "reserved" and role != ROLE_ADMIN:
#             return Response({"detail": "Accès refusé au stock réserve."}, status=403)

#         # 3) Base queryset (optimisé)
#         qs = (
#             Stock.objects
#             .select_related(
#                 "produit_line",
#                 "produit_line__lot",
#                 "produit_line__produit",
#                 "bijouterie",
#             )
#             .order_by("-id")
#         )

#         # 4) Scope par rôle (manager/vendor : uniquement leur bijouterie)
#         if role == ROLE_MANAGER:
#             bj_id = get_manager_bijouterie_id(request.user)
#             qs = qs.filter(bijouterie_id=bj_id) if bj_id else qs.none()

#         elif role == ROLE_VENDOR:
#             bj_id = get_vendor_bijouterie_id(request.user)
#             qs = qs.filter(bijouterie_id=bj_id) if bj_id else qs.none()

#         # ROLE_ADMIN => pas de filtre

#         # 5) Filtre status
#         if status_param == "reserved":
#             # Réserve = globale (bijouterie NULL) + dispo>0 + allouée=0
#             # NB: si ton modèle Stock n'a pas quantite_allouee, enlève cette condition.
#             qs = qs.filter(
#                 bijouterie__isnull=True,
#                 quantite_disponible__gt=0,
#                 quantite_allouee=0,
#             )

#         elif status_param == "allocated":
#             qs = qs.filter(bijouterie__isnull=False)

#         elif status_param == "in_stock":
#             qs = qs.filter(quantite_disponible__gt=0)

#         # "all" => pas de filtre

#         return Response(StockSerializer(qs, many=True).data)

STATUS_CHOICES = ("in_stock", "reserved", "allocated", "all")

# class StockListView(APIView):
#     """
#     GET /api/stock/?status=in_stock|reserved|allocated|all

#     - admin   : voit tout (réserve + bijouteries)
#     - manager : voit uniquement ses bijouteries (ManyToMany)
#     - vendor  : voit uniquement sa bijouterie
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManagerOrSelfVendor]
#     tags=["Stock"],
#     def get(self, request, *args, **kwargs):
#         status_param = request.query_params.get("status", "in_stock")
#         if status_param not in STATUS_CHOICES:
#             raise ValidationError({"status": f"Valeur invalide. Choisir parmi {STATUS_CHOICES}."})

#         role = get_role_name(request.user)
#         if status_param == "reserved" and role != ROLE_ADMIN:
#             return Response({"detail": "Accès refusé au stock réserve."}, status=403)

#         qs = (
#             Stock.objects
#             .select_related(
#                 "produit_line",
#                 "produit_line__lot",
#                 "produit_line__produit",
#                 "bijouterie",
#             )
#             .order_by("-id")
#         )

#         # Scope bijouterie (admin => Q() donc pas de filtre)
#         qs = qs.filter(scope_bijouterie_q(request.user, field="bijouterie_id"))

#         if status_param == "reserved":
#             qs = qs.filter(
#                 is_reserve=True,
#                 bijouterie__isnull=True,
#                 en_stock__gt=0,
#             )

#         elif status_param == "allocated":
#             qs = qs.filter(
#                 is_reserve=False,
#                 bijouterie__isnull=False,
#             )

#         elif status_param == "in_stock":
#             qs = qs.filter(en_stock__gt=0)

#         return Response(StockSerializer(qs, many=True).data)



STATUS_CHOICES = ("in_stock", "reserved", "allocated", "all")


class StockListView(APIView):
    """
    GET /api/stock/?status=in_stock|reserved|allocated|all

    - admin   : voit tout (réserve + bijouteries)
    - manager : voit uniquement ses bijouteries (ManyToMany) via scope_bijouterie_q
    - vendor  : voit uniquement sa bijouterie via scope_bijouterie_q
    """
    permission_classes = [IsAuthenticated, IsAdminOrManagerOrVendor]

    @swagger_auto_schema(
        operation_id="listStock",
        operation_summary="Lister le stock (filtre: in_stock/reserved/allocated/all)",
        operation_description=(
            "Retourne les lignes de stock selon le statut.\n\n"
            "**Règles d’accès**\n"
            "- `reserved` (stock réserve) : **admin uniquement**\n"
            "- manager/vendor : limités à leurs bijouteries via `scope_bijouterie_q`\n\n"
            "**Paramètre**\n"
            "- `status` ∈ `in_stock|reserved|allocated|all` (défaut `in_stock`)"
        ),
        tags=["Stock"],
        manual_parameters=[
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
                description="in_stock|reserved|allocated|all (défaut: in_stock)",
                enum=list(STATUS_CHOICES),
            )
        ],
        responses={200: StockSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        status_param = (request.query_params.get("status") or "in_stock").strip().lower()
        if status_param not in STATUS_CHOICES:
            raise ValidationError({"status": f"Valeur invalide. Choisir parmi {STATUS_CHOICES}."})

        role = get_role_name(request.user)

        # 🔒 réserve = admin uniquement
        if status_param == "reserved" and role != ROLE_ADMIN:
            return Response({"detail": "Accès refusé au stock réserve."}, status=403)

        qs = (
            Stock.objects
            .select_related(
                "produit_line",
                "produit_line__lot",
                "produit_line__produit",
                "bijouterie",
            )
            .order_by("-id")
        )

        # ✅ Scope bijouterie (admin => Q() donc pas de filtre)
        qs = qs.filter(scope_bijouterie_q(request.user, field="bijouterie_id"))

        # ✅ Filtres par statut
        if status_param == "reserved":
            qs = qs.filter(is_reserve=True, bijouterie__isnull=True, en_stock__gt=0)

        elif status_param == "allocated":
            qs = qs.filter(is_reserve=False, bijouterie__isnull=False)

        elif status_param == "in_stock":
            qs = qs.filter(en_stock__gt=0)

        # status_param == "all" => pas de filtre supplémentaire

        return Response(StockSerializer(qs, many=True).data)

# VENDOR_STATUS_CHOICES = ("in_stock", "allocated", "all")

# class VendorStockListView(APIView):
#     """
#     GET /api/vendor-stocks/?status=in_stock|allocated|all

#     - admin   : voit tout
#     - manager : voit uniquement sa bijouterie
#     - vendor  : voit uniquement son stock
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManagerOrSelfVendor]

#     @swagger_auto_schema(
#         operation_summary="Lister le stock vendeur (VendorStock)",
#         manual_parameters=[
#             openapi.Parameter(
#                 name="status",
#                 in_=openapi.IN_QUERY,
#                 required=False,
#                 type=openapi.TYPE_STRING,
#                 enum=list(VENDOR_STATUS_CHOICES),
#                 default="in_stock",
#                 description=(
#                     "Filtre:\n"
#                     "- allocated : quantite_allouee > 0\n"
#                     "- in_stock  : quantite_allouee > quantite_vendue\n"
#                     "- all       : sans filtre"
#                 ),
#             ),
#         ],
#         responses={200: openapi.Response("Liste VendorStock", VendorStockSerializer(many=True))},
#         tags=["Stock"],
#     )
#     def get(self, request):
#         status_param = request.query_params.get("status", "in_stock")
#         if status_param not in VENDOR_STATUS_CHOICES:
#             raise ValidationError({"status": f"Valeur invalide. Choisir parmi {VENDOR_STATUS_CHOICES}."})

#         role = get_role_name(request.user)

#         # ✅ Base queryset (c’est ICI que tu mets select_related)
#         qs = (
#             VendorStock.objects
#             .select_related("produit_line", "produit_line__lot", "produit_line__produit", "vendor", "bijouterie")
#             .order_by("-id")
#         )

#         # ✅ Scope par rôle
#         if role == ROLE_MANAGER:
#             bj_id = get_manager_bijouterie_id(request.user)
#             qs = qs.filter(bijouterie_id=bj_id) if bj_id else qs.none()

#         elif role == ROLE_VENDOR:
#             # soit tu filtres par vendor lié à l'user
#             vendor_id = getattr(getattr(request.user, "vendor", None), "id", None)
#             qs = qs.filter(vendor_id=vendor_id) if vendor_id else qs.none()

#         # ✅ Filtre status (c’est ICI que tu mets le F())
#         if status_param == "allocated":
#             qs = qs.filter(quantite_allouee__gt=0)

#         elif status_param == "in_stock":
#             qs = qs.filter(quantite_allouee__gt=F("quantite_vendue"))

#         # all => pas de filtre

#         return Response(VendorStockSerializer(qs, many=True).data)
    


# class ReserveToVendorTransferView(APIView):
#     """
#     POST /api/stocks/transfer/reserve-to-vendor/

#     Payload:
#     {
#       "vendor_email": "vendeur@rio-gold.com",
#       "lignes": [
#         {"produit_line_id": 123, "quantite": 3},
#         {"produit_line_id": 124, "quantite": 2}
#       ],
#       "note": "Affectation directe"
#     }
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManagerOrSelfVendor]
#     http_method_names = ["post"]

#     @swagger_auto_schema(
#         operation_id="transferReserveToVendor",
#         operation_summary="Affecter du stock Réserve → Vendeur (direct, simple)",
#         operation_description=dedent("""
#             Mode simple:
#             - Réserve.quantite_disponible -= qty
#             - VendorStock.quantite_allouee += qty (bijouterie = vendor.bijouterie)
#             - Crée un InventoryMovement(VENDOR_ASSIGN) par ligne, avec lot tracé (FIFO/audit).
#         """),
#         request_body=ReserveToVendorInSerializer,
#         responses={
#             200: openapi.Response("Résumé du transfert"),
#             400: openapi.Response("Erreur de validation"),
#             403: openapi.Response("Accès refusé"),
#         },
#         tags=["Stock"],
#     )
#     def post(self, request):
#         s = ReserveToVendorInSerializer(data=request.data)
#         s.is_valid(raise_exception=True)

#         try:
#             res = transfer_reserve_to_vendor(
#                 vendor_email=s.validated_data["vendor_email"],
#                 lignes=s.validated_data["lignes"],
#                 note=s.validated_data.get("note", ""),
#                 user=request.user,
#             )
#         except ValidationError as e:
#             return Response({"detail": e.message_dict if hasattr(e, "message_dict") else str(e)}, status=status.HTTP_400_BAD_REQUEST)

#         return Response(res, status=status.HTTP_200_OK)
# class ReserveToVendorTransferView(APIView):
#     """
#     POST /api/stocks/transfer/reserve-to-vendor/
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]
#     http_method_names = ["post"]

#     def post(self, request):
#         serializer = ReserveToVendorInSerializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         v = serializer.validated_data

#         role = get_role_name(request.user)

#         # ✅ Scope manager (ManyToMany bijouteries)
#         if role == ROLE_MANAGER:
#             mp = getattr(request.user, "staff_manager_profile", None)
#             if not mp or (hasattr(mp, "verifie") and not mp.verifie):
#                 return Response({"detail": "Profil manager invalide."}, status=403)

#             # récupère le vendeur ciblé
#             vendor = (
#                 Vendor.objects
#                 .select_related("bijouterie", "user")
#                 .filter(user__email=v["vendor_email"])
#                 .first()
#             )
#             if not vendor:
#                 return Response({"detail": "Vendeur introuvable."}, status=400)

#             # ✅ manager ne peut agir que sur ses bijouteries
#             if not mp.bijouteries.filter(id=vendor.bijouterie_id).exists():
#                 return Response(
#                     {"detail": "⛔ Vous ne pouvez pas affecter un vendeur hors de vos bijouteries."},
#                     status=403
#                 )

#         # admin : OK, pas de restriction

#         try:
#             res = transfer_reserve_to_vendor(
#                 vendor_email=v["vendor_email"],
#                 lignes=v["lignes"],
#                 note=v.get("note", ""),
#                 user=request.user,
#             )
#         except ValidationError as e:
#             detail = getattr(e, "message_dict", None) or getattr(e, "messages", None) or str(e)
#             return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)

#         return Response(res, status=status.HTTP_200_OK)


class ReserveToVendorTransferView(APIView):
    """
    POST /api/stocks/transfer/reserve-to-vendor/

    Transfert stock Réserve -> Vendeur :
    - décrémente Stock réserve
    - incrémente VendorStock (quantite_allouee)
    - crée InventoryMovement(VENDOR_ASSIGN) par ligne
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    http_method_names = ["post"]

    @swagger_auto_schema(
        operation_id="reserveToVendorTransfer",
        operation_summary="Transférer du stock Réserve vers un vendeur",
        operation_description=(
            "Effectue un transfert **Réserve → Vendeur**.\n\n"
            "### Effets\n"
            "- Réserve : décrémente `Stock(en_stock)` (et `quantite_totale` si tu le fais aussi)\n"
            "- Vendeur : incrémente `VendorStock.quantite_allouee`\n"
            "- Audit : crée `InventoryMovement` de type **VENDOR_ASSIGN**\n\n"
            "### Sécurité\n"
            "- **admin** : toutes bijouteries\n"
            "- **manager** : uniquement vendeurs appartenant à ses bijouteries (ManyToMany)\n"
        ),
        tags=["Stock"],
        request_body=ReserveToVendorInSerializer,
        responses={
            200: openapi.Response(
                description="Transfert effectué",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "vendor_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "vendor_email": openapi.Schema(type=openapi.TYPE_STRING),
                        "bijouterie_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "bijouterie_nom": openapi.Schema(type=openapi.TYPE_STRING),
                        "movements_created": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "note": openapi.Schema(type=openapi.TYPE_STRING),
                        "lignes": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(type=openapi.TYPE_OBJECT),
                        ),
                    },
                ),
            ),
            400: openapi.Response(description="ValidationError / stock insuffisant"),
            403: openapi.Response(description="Forbidden (scope manager)"),
        },
    )
    def post(self, request):
        serializer = ReserveToVendorInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data

        role = get_role_name(request.user)

        # ✅ Scope manager (ManyToMany bijouteries)
        if role == ROLE_MANAGER:
            mp = getattr(request.user, "staff_manager_profile", None)
            if not mp or (hasattr(mp, "verifie") and not mp.verifie):
                return Response({"detail": "Profil manager invalide."}, status=403)

            vendor = (
                Vendor.objects
                .select_related("bijouterie", "user")
                .filter(user__email=v["vendor_email"])
                .first()
            )
            if not vendor:
                return Response({"detail": "Vendeur introuvable."}, status=400)

            if not mp.bijouteries.filter(id=vendor.bijouterie_id).exists():
                return Response(
                    {"detail": "⛔ Vous ne pouvez pas affecter un vendeur hors de vos bijouteries."},
                    status=403,
                )

        try:
            res = transfer_reserve_to_vendor(
                vendor_email=v["vendor_email"],
                lignes=v["lignes"],
                note=v.get("note", ""),
                user=request.user,
            )
        except ValidationError as e:
            detail = getattr(e, "message_dict", None) or getattr(e, "messages", None) or str(e)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(res, status=status.HTTP_200_OK)




