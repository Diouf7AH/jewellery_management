import datetime
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO

# NB: on se base sur VenteProduit.vendor et on groupe par vente__created_at
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import (Avg, Count, DecimalField, ExpressionWrapper, F,
                              IntegerField, OuterRef, Q, Subquery, Sum, Value)
from django.db.models.functions import (Coalesce, TruncDay, TruncMonth,
                                        TruncWeek)
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.permissions import (ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR,
                                 IsAdminOrManager,
                                 IsAdminOrManagerOrSelfVendor, get_role_name)
from backend.renderers import UserRenderer
from inventory.models import Bucket, InventoryMovement, MovementType
# ⬇️ aligne le chemin du modèle de lot d’achat
from purchase.models import Lot, ProduitLine
from sale.models import VenteProduit  # 👈 lignes de vente (contient vendor)
from staff.models import Manager
from stock.models import Stock, VendorStock
from store.models import Bijouterie, Marque, Produit
from store.serializers import ProduitSerializer
from userauths.models import Role
from vendor.models import Vendor  # 👈 ton modèle Vendor (app vendor)

from .models import Vendor
from .serializer import (CreateVendorSerializer, VendorListSerializer,
                         VendorProduitGroupedSerializer,
                         VendorProduitLotSerializer, VendorUpdateSerializer)

# Create your views here.
User = get_user_model()
allowed_all_roles = ['admin', 'manager', 'vendeur']
allowed_roles_admin_manager = ['admin', 'manager',]


class CreateVendorView(APIView):
    """
    POST /api/staff/vendor/create

    - Admin  : peut créer un vendeur pour n’importe quelle bijouterie
    - Manager: ne peut créer un vendeur que pour *sa* bijouterie
    - Si l’email existe déjà :
        - refuse si user est admin/manager/cashier ou déjà vendor
        - accepte si le user n’a pas encore de rôle ou déjà role=vendor sans profil Vendor
    - Si l’email n’existe pas : crée User + assigne rôle vendor + crée Vendor
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminOrManager]

    @swagger_auto_schema(
        operation_summary="Créer un vendeur (User + Vendor)",
        operation_description=(
            "Crée un vendeur rattaché à une bijouterie.\n\n"
            "- Admin : n’importe quelle bijouterie\n"
            "- Manager : uniquement sa propre bijouterie\n\n"
            "Champs attendus :\n"
            "- email (obligatoire)\n"
            "- password (optionnel, obligatoire si le user n’existe pas)\n"
            "- first_name / last_name (optionnels)\n"
            "- bijouterie_nom (nom de la bijouterie)\n"
            "- verifie (bool, par défaut True)"
        ),
        request_body=CreateVendorSerializer,
        responses={
            201: openapi.Response(
                description="Vendeur créé",
                examples={
                    "application/json": {
                        "message": "Vendeur créé avec succès.",
                        "vendor": {
                            "id": 5,
                            "first_name": "Jean",
                            "last_name": "Dupont",
                            "email": "vendor@example.com",
                            "verifie": True,
                            "bijouterie": {
                                "id": 2,
                                "nom": "Rio-Gold Centre",
                            },
                        },
                    }
                },
            ),
            400: "Requête invalide",
            403: "Accès refusé",
            404: "Non trouvé",
            409: "Conflit (rôle ou vendor déjà existant)",
        },
        tags=["Staff"],
    )
    @transaction.atomic
    def post(self, request):
        ser = CreateVendorSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        email = data["email"]
        password = data.get("password") or None
        first_name = data.get("first_name") or ""
        last_name = data.get("last_name") or ""
        bijouterie = data["bijouterie_nom"]     # instance Bijouterie
        verifie = data.get("verifie", True)

        # -------- 1) Contrôle périmètre Manager --------
        caller_role = get_role_name(request.user)
        if caller_role == ROLE_MANAGER:
            mgr = (
                Manager.objects
                .filter(user=request.user)
                .select_related("bijouterie")
                .first()
            )
            mgr_bj_id = getattr(getattr(mgr, "bijouterie", None), "id", None)
            if not mgr_bj_id or mgr_bj_id != bijouterie.id:
                return Response(
                    {"detail": "Vous ne pouvez créer un vendeur que pour votre propre bijouterie."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # -------- 2) Rôles en base --------
        role_vendor = Role.objects.filter(role=ROLE_VENDOR).first()
        role_manager = Role.objects.filter(role=ROLE_MANAGER).first()
        role_admin = Role.objects.filter(role=ROLE_ADMIN).first()
        if not role_vendor:
            return Response(
                {"error": "Le rôle 'vendor' n'existe pas en base."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # -------- 3) User existant ? --------
        user = User.objects.select_for_update().filter(email__iexact=email).first()
        created_user = False

        if user is None:
            # Création du user
            if not password:
                return Response(
                    {"error": "Le mot de passe est obligatoire pour un nouvel utilisateur."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user = User(email=email, first_name=first_name, last_name=last_name)
            user.set_password(password)
            user.user_role = role_vendor  # assigne directement le rôle vendor
            user.is_active = True
            user.save()
            created_user = True
        else:
            # User existe déjà → protections
            existing_role = getattr(getattr(user, "user_role", None), "role", None)

            if existing_role in (ROLE_ADMIN, ROLE_MANAGER):
                return Response(
                    {"error": f"Utilisateur déjà {existing_role}, on ne peut pas le transformer en vendor."},
                    status=status.HTTP_409_CONFLICT,
                )

            # déjà vendor ?
            if Vendor.objects.filter(user=user).exists():
                return Response(
                    {"error": "Ce user est déjà vendeur."},
                    status=status.HTTP_409_CONFLICT,
                )

            # s'il n'a pas de rôle, on lui donne vendor
            if not existing_role:
                user.user_role = role_vendor
                user.save(update_fields=["user_role"])

        # -------- 4) Création Vendor --------
        try:
            vendor = Vendor.objects.create(
                user=user,
                bijouterie=bijouterie,
                verifie=verifie,
            )
        except IntegrityError:
            return Response(
                {"error": "Conflit d'intégrité à la création du vendeur."},
                status=status.HTTP_409_CONFLICT,
            )

        # -------- 5) Payload de réponse --------
        bj = vendor.bijouterie
        payload = {
            "message": "Vendeur créé avec succès." if created_user else "Vendeur ajouté à cet utilisateur.",
            "vendor": {
                "id": vendor.id,
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "email": user.email,
                "verifie": vendor.verifie,
                "bijouterie": {
                    "id": bj.id,
                    "nom": bj.nom,
                } if bj else None,
            },
        }
        return Response(payload, status=status.HTTP_201_CREATED)



# Un dashboard riche avec produits, ventes et stats
# Un endpoint PATCH pour que le vendeur mette à jour son profil et son compte
# Un accès admin pour voir n’importe quel vendeur via user_id
# Un admin peut voir n'importe quel vendeur (avec user_id).
# Un manager peut aussi voir n'importe quel vendeur.
# Un vendeur peut uniquement voir son propre dashboard.
# class VendorDashboardView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_id="Dashboard Vendeur reserver pour vendeur seulement",
#         operation_description="Voir les statistiques d’un vendeur (admin, manager ou vendeur connecté).",
#         responses={200: "Statistiques du vendeur"}
#     )
#     def get(self, request):
#         user = request.user
#         role = getattr(user.user_role, 'role', None)
#         is_admin_or_manager_or_vendor = role in ['admin', 'manager', 'vendor']

#         # 🔎 Récupération et validation du user_id
#         user_id = request.GET.get('user_id')
#         if user_id:
#             if not user_id.isdigit():
#                 return Response({"detail": "user_id invalide."}, status=400)
#             if not is_admin_or_manager_or_vendor:
#                 return Response({"detail": "Accès refusé."}, status=403)
#             target_user = get_object_or_404(User, id=int(user_id))
#         else:
#             target_user = user

#         # 🔐 Vérifie que le compte est bien un vendeur
#         if not target_user.user_role or target_user.user_role.role != 'vendor':
#             return Response({"detail": "Ce compte n'est pas un vendeur."}, status=400)

#         try:
#             vendor = Vendor.objects.get(user=target_user)
#         except Vendor.DoesNotExist:
#             return Response({"detail": "Vendeur introuvable."}, status=404)

#         produits = VendorProduit.objects.filter(vendor=vendor)
#         ventes = VenteProduit.objects.filter(produit__in=produits.values('produit'))

#         # 📊 Statistiques globales
#         total_produits = produits.count()
#         total_ventes = ventes.count()
#         total_qte_vendue = ventes.aggregate(total=Sum('quantite'))['total'] or 0
#         total_montant = ventes.aggregate(total=Sum('sous_total_prix_vent'))['total'] or 0
#         stock_total = produits.aggregate(stock=Sum('quantite'))['stock'] or 0
#         total_remise = ventes.aggregate(remise=Sum('remise'))['remise'] or 0

#         # 📆 Regroupement par période
#         group_by = request.GET.get('group_by', 'month')
#         if group_by == 'day':
#             trunc = TruncDay('vente__created_at')
#         elif group_by == 'week':
#             trunc = TruncWeek('vente__created_at')
#         else:
#             trunc = TruncMonth('vente__created_at')

#         stats_grouped = (
#             ventes.annotate(period=trunc)
#             .values('period')
#             .annotate(
#                 total_qte=Sum('quantite'),
#                 total_montant=Sum('sous_total_prix_vent')
#             ).order_by('period')
#         )

#         top_produits = (
#             ventes.values('produit__id', 'produit__nom')
#             .annotate(total_qte=Sum('quantite'))
#             .order_by('-total_qte')[:5]
#         )
        
#         # Générer un tableau de produit
#         produits_tableau = (
#             ventes.values('produit__id', 'produit__slug',  'produit__nom')
#             .annotate(
#                 quantite_vendue=Sum('quantite'),
#                 montant_total=Sum('sous_total_prix_vent'),
#                 remise_totale=Sum('remise')
#             )
#             .order_by('-quantite_vendue')
#         )

#         return Response({
#             "vendeur": VendorSerializer(vendor).data,
#             "user": UserSerializer(target_user).data,
#             "stats": {
#                 "produits": total_produits,
#                 "ventes": total_ventes,
#                 "quantite_totale_vendue": total_qte_vendue,
#                 "stock_restant": stock_total,
#                 "montant_total_ventes": total_montant,
#                 "remise_totale": total_remise,
#             },
#             "stats_groupées": stats_grouped,
#             "top_produits": top_produits,
#             "produits": VendorProduitSerializer(produits, many=True).data,
#             "ventes": VenteProduitSerializer(ventes, many=True).data,
#             "produits_tableau": produits_tableau,
#         })


# class VendorStatsView(APIView):
#     """
#     GET /api/vendors/stats/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&group_by=day|week|month
#     - vendor connecté : son dashboard
#     - admin/manager   : ?user_id=... ou ?vendor_email=...
#     - ?export=excel   : export Excel
#     """
#     permission_classes = [permissions.IsAuthenticated, IsAdminOrManagerOrSelfVendor]

#     @swagger_auto_schema(
#         operation_id="vendorStats",
#         operation_summary="Statistiques d’un vendor",
#         operation_description=(
#             "Un vendor voit son propre dashboard. "
#             "Admin/manager peuvent cibler via ?user_id=... ou ?vendor_email=... "
#             "Filtres: ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&group_by=day|week|month "
#             "Export Excel: ?export=excel"
#         ),
#         manual_parameters=[
#             openapi.Parameter("user_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, required=False),
#             openapi.Parameter("vendor_email", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=False),
#             openapi.Parameter("date_from", openapi.IN_QUERY, type=openapi.TYPE_STRING, format="date", required=False),
#             openapi.Parameter("date_to", openapi.IN_QUERY, type=openapi.TYPE_STRING, format="date", required=False),
#             openapi.Parameter("group_by", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                               enum=["day","week","month"], required=False),
#             openapi.Parameter("export", openapi.IN_QUERY, type=openapi.TYPE_STRING, enum=["excel"], required=False),
#         ],
#         tags=["Analytics"],
#         responses={200: "JSON ou Excel"}
#     )
#     def get(self, request):
#         u = request.user
#         is_admin = u.is_superuser or u.groups.filter(name__in=["admin","manager"]).exists()

#         # -------- 1) cible vendor --------
#         target_vendor = None
#         if is_admin:
#             user_id = request.GET.get("user_id")
#             vendor_email = request.GET.get("vendor_email")
#             if user_id:
#                 target_vendor = Vendor.objects.select_related("user","bijouterie").filter(user_id=user_id).first()
#                 if not target_vendor:
#                     return Response({"detail":"Vendor introuvable pour ce user_id."}, status=404)
#             elif vendor_email:
#                 User = get_user_model()
#                 user = User.objects.filter(email__iexact=vendor_email.strip()).first()
#                 if not user:
#                     return Response({"detail":"Utilisateur introuvable pour cet email."}, status=404)
#                 target_vendor = Vendor.objects.select_related("user","bijouterie").filter(user=user).first()
#                 if not target_vendor:
#                     return Response({"detail":"Aucun profil Vendor lié à cet email."}, status=404)
#             else:
#                 # pas de cible → vide
#                 if request.GET.get("export") == "excel":
#                     return self._export_excel({}, [], "vendor_stats_empty.xlsx")
#                 return Response({"summary": {}, "series": []})
#         else:
#             target_vendor = getattr(u, "staff_vendor_profile", None)
#             if not target_vendor:
#                 return Response({"detail":"Profil vendor non trouvé."}, status=403)

#         # -------- 2) bornes & groupement --------
#         today = timezone.localdate()
#         date_from_str = request.GET.get("date_from")
#         date_to_str   = request.GET.get("date_to")
#         try:
#             date_from = datetime.fromisoformat(date_from_str).date() if date_from_str else (today - timedelta(days=29))
#             date_to   = datetime.fromisoformat(date_to_str).date()   if date_to_str   else today
#         except ValueError:
#             return Response({"detail":"Paramètres date invalides."}, status=400)
#         if date_from > date_to:
#             return Response({"detail":"date_from doit être ≤ date_to."}, status=400)

#         group_by = (request.GET.get("group_by") or "day").lower()
#         if group_by not in ("day","week","month"):
#             group_by = "day"

#         trunc, fmt = {
#             "day":   (TruncDay("vente__created_at"),   "%Y-%m-%d"),
#             "week":  (TruncWeek("vente__created_at"),  "%G-W%V"),
#             "month": (TruncMonth("vente__created_at"), "%Y-%m"),
#         }[group_by]

#         # -------- 3) base: lignes du vendor --------
#         lines = (VenteProduit.objects
#                  .filter(vendor=target_vendor,
#                          vente__created_at__date__gte=date_from,
#                          vente__created_at__date__lte=date_to))

#         # KPI globaux
#         agg_revenue = lines.aggregate(rev=Sum("prix_ttc"))["rev"] or Decimal("0.00")
#         agg_qty     = lines.aggregate(q=Sum("quantite"))["q"] or 0
#         # nb ventes distinctes (commandes)
#         orders_cnt  = (lines.values("vente_id").distinct().count()) or 0
#         avg_ticket  = (agg_revenue / orders_cnt) if orders_cnt else Decimal("0.00")

#         summary = {
#             "vendor": {
#                 "id": target_vendor.id,
#                 "username": getattr(target_vendor.user, "username", None),
#                 "email": getattr(target_vendor.user, "email", None),
#                 "bijouterie": getattr(target_vendor.bijouterie, "nom", None),
#             },
#             "date_from": date_from.isoformat(),
#             "date_to": date_to.isoformat(),
#             "orders_count": orders_cnt,
#             "quantity_sold": int(agg_qty),
#             "revenue_total": str(agg_revenue.quantize(Decimal("0.01"))),
#             "avg_ticket": str(avg_ticket.quantize(Decimal("0.01"))),
#         }

#         # Série temporelle
#         series_qr = (lines
#                      .annotate(bucket=trunc)
#                      .values("bucket")
#                      .annotate(
#                          orders=Count("vente_id", distinct=True),
#                          quantity=Sum("quantite"),
#                          revenue=Sum("prix_ttc"),
#                      )
#                      .order_by("bucket"))

#         series = []
#         for row in series_qr:
#             b = row["bucket"]
#             label = b.strftime(fmt) if hasattr(b, "strftime") else str(b)
#             series.append({
#                 "bucket": label,
#                 "orders": row["orders"] or 0,
#                 "quantity": int(row["quantity"] or 0),
#                 "revenue": str((row["revenue"] or Decimal("0.00")).quantize(Decimal("0.01"))),
#             })

#         # export ?
#         if request.GET.get("export") == "excel":
#             return self._export_excel(summary, series, f"vendor_stats_{target_vendor.id}.xlsx")

#         return Response({"summary": summary, "series": series}, status=200)

#     # ------ helper export ------
#     def _export_excel(self, summary: dict, series: list[dict], filename: str):
#         from io import BytesIO

#         from openpyxl import Workbook

#         wb = Workbook()
#         ws1 = wb.active
#         ws1.title = "Summary"
#         ws1.append(["Clé", "Valeur"])
#         for k, v in summary.items():
#             if isinstance(v, dict):
#                 ws1.append([k, ""])
#                 for sk, sv in v.items():
#                     ws1.append([f"  {sk}", sv if sv is not None else ""])
#             else:
#                 ws1.append([k, v if v is not None else ""])

#         ws2 = wb.create_sheet("Timeseries")
#         ws2.append(["bucket","orders","quantity","revenue"])
#         for r in series:
#             ws2.append([r["bucket"], r["orders"], r["quantity"], float(r["revenue"])])

#         out = BytesIO()
#         wb.save(out)
#         out.seek(0)
#         resp = HttpResponse(
#             out.read(),
#             content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
#         )
#         resp["Content-Disposition"] = f'attachment; filename="{filename}"'
#         return resp


class VendorDashboardView(APIView):
    """
    GET /api/vendors/dashboard/
      - Vendor  : voit son propre dashboard (limité à 1 an)
      - Manager : vendeurs de SA bijouterie (limité à 3 ans)
      - Admin   : global, filtrage par bijouterie + vendor
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        # Rôle logique basé sur Role.role + is_superuser
        role_slug = getattr(getattr(user, "user_role", None), "role", None)
        if user.is_superuser:
            role_slug = "admin"

        vendor_filter = None
        bijouterie_filter = None

        # 1) Période
        date_from, date_to = self._get_date_range(request)
        delta_days = (date_to - date_from).days

        # Limitation de durée
        if role_slug == "vendor" and delta_days > 365:
            return Response(
                {"detail": "Vous ne pouvez consulter que les données sur une période maximale de 12 mois."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if role_slug == "manager" and delta_days > 3 * 365:
            return Response(
                {"detail": "Vous ne pouvez consulter que les données sur une période maximale de 3 ans."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2) Scope selon rôle
        if role_slug == "vendor":
            try:
                vendor_profile = Vendor.objects.select_related("bijouterie").get(user=user)
            except Vendor.DoesNotExist:
                return Response(
                    {"detail": "Profil vendeur introuvable pour cet utilisateur."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            vendor_filter = vendor_profile
            bijouterie_filter = vendor_profile.bijouterie

        elif role_slug == "manager":
            # adapte si tu as un vrai modèle Manager
            manager_bijouterie = getattr(getattr(user, "manager_profile", None), "bijouterie", None)
            if manager_bijouterie is None:
                return Response(
                    {"detail": "Bijouterie du manager introuvable."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            bijouterie_filter = manager_bijouterie

            vendor_id = request.query_params.get("vendor_id")
            if vendor_id:
                try:
                    vendor_filter = Vendor.objects.get(
                        id=vendor_id,
                        bijouterie=manager_bijouterie,
                    )
                except Vendor.DoesNotExist:
                    return Response(
                        {"detail": "Vendor non trouvé dans votre bijouterie."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        elif role_slug == "admin":
            bijouterie_id = request.query_params.get("bijouterie_id")
            vendor_id = request.query_params.get("vendor_id")

            if bijouterie_id:
                try:
                    bijouterie_filter = Bijouterie.objects.get(id=bijouterie_id)
                except Bijouterie.DoesNotExist:
                    return Response(
                        {"detail": "Bijouterie introuvable."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            if vendor_id:
                qs_vendor = Vendor.objects.all()
                if bijouterie_filter:
                    qs_vendor = qs_vendor.filter(bijouterie=bijouterie_filter)
                try:
                    vendor_filter = qs_vendor.get(id=vendor_id)
                except Vendor.DoesNotExist:
                    return Response(
                        {"detail": "Vendor introuvable pour ces filtres."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        else:
            return Response(
                {"detail": "Rôle utilisateur non autorisé pour ce dashboard."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 3) Lignes de vente (⚠️ vendor est sur VenteProduit, pas Vente)
        lignes = (
            VenteProduit.objects.select_related(
                "vente",
                "produit",
                "produit__categorie",
                "produit__marque",
                "produit__purete",
                "vendor",
                "vendor__bijouterie",
            )
            .filter(
                vente__created_at__date__gte=date_from,
                vente__created_at__date__lte=date_to,
            )
        )

        if vendor_filter:
            lignes = lignes.filter(vendor=vendor_filter)
        elif bijouterie_filter:
            lignes = lignes.filter(vendor__bijouterie=bijouterie_filter)

        if not lignes.exists():
            data = self._empty_dashboard(
                request,
                role_slug,
                vendor_filter,
                bijouterie_filter,
                date_from,
                date_to,
            )
            return Response(data, status=status.HTTP_200_OK)

        # 4) Stock vendeur
        stock_by_product, stock_by_marque, stock_by_purete = self._get_vendorstock_maps(
            vendor_filter,
            bijouterie_filter,
        )

        # 5) Réponse finale (SANS courbe)
        data = {
            "filters": self._build_filters_block(
                request,
                role_slug,
                vendor_filter,
                bijouterie_filter,
                date_from,
                date_to,
            ),
            "kpis": self._compute_kpis(lignes),
            "by_purete": self._by_purete(lignes, stock_by_purete),
            "by_marque": self._by_marque(lignes, stock_by_marque),
            "by_categorie": self._by_categorie(lignes),
            "top_products": self._top_products(lignes, stock_by_product),
        }
        return Response(data, status=status.HTTP_200_OK)

    # ---------- Dates & filtres ----------

    def _get_date_range(self, request):
        today = datetime.today().date()
        default_from = today - timedelta(days=30)

        date_from_str = request.query_params.get("date_from")
        date_to_str = request.query_params.get("date_to")

        date_from = parse_date(date_from_str) if date_from_str else default_from
        date_to = parse_date(date_to_str) if date_to_str else today

        if date_from is None:
            date_from = default_from
        if date_to is None:
            date_to = today

        return date_from, date_to

    def _build_filters_block(self, request, role_slug, vendor, bijouterie, date_from, date_to):
        if role_slug == "vendor":
            scope = "self"
        elif role_slug == "manager":
            scope = "bijouterie"
        else:
            scope = "global"

        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "scope": scope,
            "vendor": {
                "id": vendor.id,
                "name": getattr(vendor, "full_name", str(vendor)),
            } if vendor else None,
            "bijouterie": {
                "id": bijouterie.id,
                "name": getattr(bijouterie, "nom", str(bijouterie)),
            } if bijouterie else None,
        }

    def _empty_dashboard(self, request, role_slug, vendor, bijouterie, date_from, date_to):
        return {
            "filters": self._build_filters_block(
                request, role_slug, vendor, bijouterie, date_from, date_to
            ),
            "kpis": {
                "total_amount": 0,
                "currency": "XOF",
                "total_sales_count": 0,
                "total_items_sold": 0,
                "average_ticket": 0,
                "average_items_per_sale": 0,
            },
            "by_purete": [],
            "by_marque": [],
            "by_categorie": [],
            "top_products": [],
        }

    # ---------- VendorStock (avec fallback) ----------

    def _get_vendorstock_maps(self, vendor_filter, bijouterie_filter):
        """
        Renvoie 3 dicts (par produit, par marque, par pureté).
        Si la structure de VendorStock / ProduitLine ne correspond pas,
        on renvoie tout à zéro pour éviter un 500.
        """
        try:
            qs = VendorStock.objects.select_related(
                "produit_line",
                "produit_line__produit",
                "produit_line__produit__marque",
                "produit_line__produit__purete",
                "vendor",
                "vendor__bijouterie",
            )

            if vendor_filter:
                qs = qs.filter(vendor=vendor_filter)
            elif bijouterie_filter:
                qs = qs.filter(vendor__bijouterie=bijouterie_filter)

            # Par produit
            stock_by_product = {}
            for row in qs.values("produit_line__produit_id").annotate(
                total_allouee=Sum("quantite_allouee"),
                total_vendue=Sum("quantite_vendue"),
            ):
                produit_id = row["produit_line__produit_id"]
                if produit_id is None:
                    continue
                total_allouee = row["total_allouee"] or 0
                total_vendue = row["total_vendue"] or 0
                stock_by_product[produit_id] = {
                    "qty_allouee": int(total_allouee),
                    "qty_disponible": max(0, int(total_allouee) - int(total_vendue)),
                }

            # Par marque
            stock_by_marque = {}
            for row in qs.values("produit_line__produit__marque_id").annotate(
                total_allouee=Sum("quantite_allouee"),
                total_vendue=Sum("quantite_vendue"),
            ):
                marque_id = row["produit_line__produit__marque_id"]
                if marque_id is None:
                    continue
                total_allouee = row["total_allouee"] or 0
                total_vendue = row["total_vendue"] or 0
                stock_by_marque[marque_id] = {
                    "qty_allouee": int(total_allouee),
                    "qty_disponible": max(0, int(total_allouee) - int(total_vendue)),
                }

            # Par pureté
            stock_by_purete = {}
            for row in qs.values("produit_line__produit__purete_id").annotate(
                total_allouee=Sum("quantite_allouee"),
                total_vendue=Sum("quantite_vendue"),
            ):
                purete_id = row["produit_line__produit__purete_id"]
                if purete_id is None:
                    continue
                total_allouee = row["total_allouee"] or 0
                total_vendue = row["total_vendue"] or 0
                stock_by_purete[purete_id] = {
                    "qty_allouee": int(total_allouee),
                    "qty_disponible": max(0, int(total_allouee) - int(total_vendue)),
                }

            return stock_by_product, stock_by_marque, stock_by_purete

        except Exception:
            # Si ça ne matche pas, on ne casse pas le dashboard.
            return {}, {}, {}

    # ---------- Agrégations ventes ----------

    def _compute_kpis(self, lignes):
        agg = lignes.aggregate(
            total_amount=Sum("prix_ttc"),            # CA TTC
            total_sales_count=Count("vente", distinct=True),
            total_items_sold=Sum("quantite"),
        )

        total_amount = agg["total_amount"] or 0
        total_sales_count = agg["total_sales_count"] or 0
        total_items_sold = agg["total_items_sold"] or 0

        average_ticket = total_amount / total_sales_count if total_sales_count else 0
        average_items_per_sale = total_items_sold / total_sales_count if total_sales_count else 0

        return {
            "total_amount": float(total_amount),
            "currency": "XOF",
            "total_sales_count": int(total_sales_count),
            "total_items_sold": int(total_items_sold),
            "average_ticket": float(average_ticket),
            "average_items_per_sale": float(average_items_per_sale),
        }

    def _by_purete(self, lignes, stock_by_purete):
        qs = (
            lignes
            .values("produit__purete__id", "produit__purete__purete")
            .annotate(
                total_amount=Sum("prix_ttc"),
                items_sold=Sum("quantite"),
                sales_count=Count("id"),
            )
            .order_by("-total_amount")
        )

        results = []
        for row in qs:
            purete_id = row["produit__purete__id"]
            stock = stock_by_purete.get(
                purete_id,
                {"qty_allouee": 0, "qty_disponible": 0},
            )
            results.append({
                "purete_id": purete_id,
                "purete": row["produit__purete__purete"],
                "total_amount": float(row["total_amount"] or 0),
                "items_sold": int(row["items_sold"] or 0),
                "sales_count": int(row["sales_count"] or 0),
                "stock_qty_allouee": stock["qty_allouee"],
                "stock_qty_disponible": stock["qty_disponible"],
            })
        return results

    def _by_marque(self, lignes, stock_by_marque):
        """
        Agrégations par marque :
        - CA, quantité vendue, nombre de ventes (à partir de VenteProduit)
        - stock alloué / disponible (à partir de VendorStock)

        ⛳ Objectif : afficher TOUTES les marques où le vendeur a du stock,
        même si aucune vente n'a été faite dans la période.
        """
        # 1) Stats de ventes par marque (sur la période)
        ventes_qs = (
            lignes
            .values("produit__marque__id")
            .annotate(
                total_amount=Sum("prix_ttc"),
                items_sold=Sum("quantite"),
                sales_count=Count("id"),
            )
        )

        ventes_par_marque: dict[int, dict] = {}
        for row in ventes_qs:
            marque_id = row["produit__marque__id"]
            if marque_id is None:
                continue
            ventes_par_marque[marque_id] = {
                "total_amount": row["total_amount"] or 0,
                "items_sold": row["items_sold"] or 0,
                "sales_count": row["sales_count"] or 0,
            }

        # 2) Ensemble de toutes les marques concernées :
        #    - celles qui ont du stock
        #    - celles qui ont des ventes
        all_marque_ids = set(stock_by_marque.keys()) | set(ventes_par_marque.keys())
        if not all_marque_ids:
            return []

        # 3) Récupérer les labels des marques
        marques_labels = {
            m["id"]: m["marque"]
            for m in Marque.objects.filter(id__in=all_marque_ids).values("id", "marque")
        }

        # 4) Construire la réponse fusionnée
        results = []
        for marque_id in all_marque_ids:
            vente_data = ventes_par_marque.get(marque_id, {})
            stock_data = stock_by_marque.get(
                marque_id,
                {"qty_allouee": 0, "qty_disponible": 0},
            )

            results.append({
                "marque_id": marque_id,
                "marque": marques_labels.get(marque_id, "—"),
                # ventes
                "total_amount": float(vente_data.get("total_amount") or 0),
                "items_sold": int(vente_data.get("items_sold") or 0),
                "sales_count": int(vente_data.get("sales_count") or 0),
                # stock vendeur pour cette marque
                "stock_qty_allouee": int(stock_data["qty_allouee"]),
                "stock_qty_disponible": int(stock_data["qty_disponible"]),
            })

        # 5) Option : trier par stock alloué (ou par CA, à toi de voir)
        results.sort(key=lambda x: x["stock_qty_allouee"], reverse=True)
        return results

    def _by_categorie(self, lignes):
        qs = (
            lignes
            .values("produit__categorie__id", "produit__categorie__nom")
            .annotate(
                total_amount=Sum("prix_ttc"),
                items_sold=Sum("quantite"),
                sales_count=Count("id"),
            )
            .order_by("-total_amount")
        )

        return [
            {
                "categorie_id": row["produit__categorie__id"],
                "categorie": row["produit__categorie__nom"],
                "total_amount": float(row["total_amount"] or 0),
                "items_sold": int(row["items_sold"] or 0),
                "sales_count": int(row["sales_count"] or 0),
            }
            for row in qs
        ]

    def _top_products(self, lignes, stock_by_product, limit=10):
        qs = (
            lignes
            .values(
                "produit_id",
                "produit__sku",
                "produit__nom",
                "produit__categorie__nom",
                "produit__marque__marque",
                "produit__purete__purete",
            )
            .annotate(
                quantite_vendue=Sum("quantite"),
                ca_total=Sum("prix_ttc"),
            )
            .order_by("-ca_total")[:limit]
        )

        results = []
        for row in qs:
            produit_id = row["produit_id"]
            stock = stock_by_product.get(
                produit_id,
                {"qty_allouee": 0, "qty_disponible": 0},
            )

            results.append({
                "produit_id": produit_id,
                "sku": row["produit__sku"],
                "nom": row["produit__nom"],
                "categorie": row["produit__categorie__nom"],
                "marque": row["produit__marque__marque"],
                "purete": row["produit__purete__purete"],
                "quantite_vendue": int(row["quantite_vendue"] or 0),
                "ca_total": float(row["ca_total"] or 0),
                "stock_qty_allouee": stock["qty_allouee"],
                "stock_qty_disponible": stock["qty_disponible"],
            })
        return results
    

# Un vendeur authentifié peut appeler GET /api/vendor/produits/
# Il recevra la liste des produits associés à son stock
# class VendorProduitListView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request, *args, **kwargs):
#         user = request.user

#         # récupère le profil vendeur de l'utilisateur
#         vendor = getattr(user, "staff_vendor_profile", None)
#         if vendor is None:
#             return Response(
#                 {"detail": "Aucun profil vendeur associé à cet utilisateur."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         # 🔹 on traverse produit_line → produit
#         vendor_stocks = (
#             VendorStock.objects
#             .filter(vendor=vendor)
#             .select_related("produit_line__produit", "vendor")
#         )

#         produits = [vs.produit_line.produit for vs in vendor_stocks]
#         # enlever les doublons
#         produits = list({p.id: p for p in produits}.values())

#         serializer = ProduitSerializer(produits, many=True)
#         return Response(serializer.data, status=status.HTTP_200_OK)
    


# class VendorProduitListView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request, *args, **kwargs):
#         user = request.user
#         vendor = getattr(user, "staff_vendor_profile", None)
#         if vendor is None:
#             return Response(
#                 {"detail": "Aucun profil vendeur associé à cet utilisateur."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         detail = (request.GET.get("detail") or "").strip() in {"1", "true", "yes"}

#         # ✅ DÉTAIL LOT / PRODUITLINE
#         if detail:
#             vendor_stocks = (
#                 VendorStock.objects
#                 .filter(vendor=vendor)
#                 .select_related("produit_line__produit", "produit_line__lot", "vendor")
#                 .order_by("produit_line__lot__received_at", "produit_line_id")
#             )
#             return Response(
#                 {
#                     "mode": "detail",
#                     "results": VendorProduitLotSerializer(vendor_stocks, many=True).data
#                 },
#                 status=status.HTTP_200_OK,
#             )

#         # ✅ REGROUPÉ PAR PRODUIT (par défaut)
#         qs = (
#             VendorStock.objects
#             .filter(vendor=vendor)
#             .select_related("produit_line__produit")
#             .values(
#                 produit_id=F("produit_line__produit_id"),
#                 produit_nom=F("produit_line__produit__nom"),
#                 produit_sku=F("produit_line__produit__sku"),
#             )
#             .annotate(
#                 quantite_allouee=Coalesce(Sum("quantite_allouee"), Value(0), output_field=IntegerField()),
#                 quantite_vendue=Coalesce(Sum("quantite_vendue"), Value(0), output_field=IntegerField()),
#                 quantite_disponible=Coalesce(
#                     Sum(F("quantite_allouee") - F("quantite_vendue")),
#                     Value(0),
#                     output_field=IntegerField(),
#                 ),
#                 quantite_restante=Coalesce(
#                     Sum("produit_line__quantite_restante"),
#                     Value(0),
#                     output_field=IntegerField(),
#                 ),
#             )
#             .order_by("produit_nom")
#         )

#         return Response(
#             {
#                 "mode": "grouped",
#                 "results": VendorProduitGroupedSerializer(qs, many=True).data
#             },
#             status=status.HTTP_200_OK,
#         )


# --------------------------------------------------------------------------
# --- Helpers locaux (adapte si tu les as déjà ailleurs) ---
# def _user_role(user) -> str | None:
#     return getattr(getattr(user, "user_role", None), "role", None)

def _user_bijouterie(user):
    vp = getattr(user, "staff_vendor_profile", None)
    if vp and getattr(vp, "verifie", False) and vp.bijouterie_id:
        return vp.bijouterie
    mp = getattr(user, "staff_manager_profile", None)
    if mp and getattr(mp, "verifie", False) and mp.bijouterie_id:
        return mp.bijouterie
    # cp = getattr(user, "staff_cashier_profile", None)
    # if cp and getattr(cp, "verifie", False) and cp.bijouterie_id:
    #     return cp.bijouterie
    return None

# class VendorProduitListView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Stock vendeur (groupé par produit ou détail FIFO par lot)",
#         operation_description=(
#             "Retourne le stock **VendorStock** d’un vendeur.\n\n"
#             "### Accès & portée\n"
#             "- **vendor** : voit uniquement **son propre** stock.\n"
#             "- **manager/admin** : peut contrôler un vendeur via `vendor_id`.\n\n"
#             "### Modes\n"
#             "- Par défaut : **grouped** (1 ligne par produit) avec totaux `allouee/vendue/disponible/restante`.\n"
#             "- `detail=1` : **detail** (1 ligne par VendorStock / ProduitLine) trié FIFO.\n\n"
#             "### Définitions\n"
#             "- `quantite_disponible = quantite_allouee - quantite_vendue`\n"
#             "- `quantite` = stock global restant du lot (ProduitLine), tous vendeurs confondus.\n"
#         ),
#         manual_parameters=[
#             openapi.Parameter(
#                 name="detail",
#                 in_=openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 required=False,
#                 description="`1|true|yes` pour détail FIFO par lot. Par défaut: grouped."
#             ),
#             openapi.Parameter(
#                 name="vendor_id",
#                 in_=openapi.IN_QUERY,
#                 type=openapi.TYPE_INTEGER,
#                 required=False,
#                 description="(manager/admin) ID du vendeur à contrôler. Ignoré pour vendor."
#             ),
#         ],
#         responses={200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found"},
#         tags=["Vendor / Stock"],
#     )
#     def get(self, request, *args, **kwargs):
#         user = request.user
#         role = get_role_name(user)
#         detail = (request.GET.get("detail") or "").strip().lower() in {"1", "true", "yes"}

#         # 🎯 déterminer le vendeur ciblé (UNE SEULE variable)
#         if role == "vendor":
#             target_vendor = getattr(user, "staff_vendor_profile", None)
#             if not target_vendor:
#                 return Response({"detail": "Aucun profil vendeur associé à cet utilisateur."}, status=400)

#         elif role in {"manager", "admin"}:
#             vendor_id = request.GET.get("vendor_id")
#             if not vendor_id:
#                 return Response({"error": "Paramètre `vendor_id` requis pour manager/admin."}, status=400)

#             try:
#                 vendor_id = int(vendor_id)
#             except ValueError:
#                 return Response({"vendor_id": "Doit être un entier."}, status=400)

#             target_vendor = Vendor.objects.select_related("bijouterie").filter(id=vendor_id).first()
#             if not target_vendor:
#                 return Response({"error": "Vendeur introuvable."}, status=404)

#             # ✅ contrôle bijouterie (manager)
#             if role == "manager":
#                 user_shop = _user_bijouterie(user)
#                 if not user_shop:
#                     return Response({"error": "Manager non rattaché à une bijouterie."}, status=400)
#                 if getattr(target_vendor, "bijouterie_id", None) != user_shop.id:
#                     return Response({"error": "Ce vendeur n’appartient pas à votre bijouterie."}, status=403)

#         else:
#             return Response({"detail": "⛔ Accès refusé"}, status=403)

#         # ✅ DÉTAIL LOT / PRODUITLINE
#         if detail:
#             vendor_stocks = (
#                 VendorStock.objects
#                 .filter(vendor=target_vendor)
#                 .select_related("produit_line__produit", "produit_line__lot", "vendor")
#                 .order_by("produit_line__lot__received_at", "produit_line_id")
#             )
#             return Response(
#                 {"mode": "detail", "results": VendorProduitLotSerializer(vendor_stocks, many=True).data},
#                 status=status.HTTP_200_OK,
#             )

#         # ✅ REGROUPÉ PAR PRODUIT (par défaut)
#         qs = (
#             VendorStock.objects
#             .filter(vendor=target_vendor)  # ✅ ici aussi
#             .values(
#                 produit_id=F("produit_line__produit_id"),
#                 produit_nom=F("produit_line__produit__nom"),
#                 produit_sku=F("produit_line__produit__sku"),
#             )
#             .annotate(
#                 quantite_allouee=Coalesce(Sum("quantite_allouee"), Value(0), output_field=IntegerField()),
#                 quantite_vendue=Coalesce(Sum("quantite_vendue"), Value(0), output_field=IntegerField()),
#                 quantite_lot=Coalesce(Sum("produit_line__quantite"), Value(0), output_field=IntegerField()),
#             )
#             .annotate(
#                 quantite_disponible=ExpressionWrapper(
#                     F("quantite_allouee") - F("quantite_vendue"),
#                     output_field=IntegerField(),
#                 )
#             )
#             .order_by("produit_nom")
#         )

#         return Response(
#             {"mode": "grouped", "results": VendorProduitGroupedSerializer(qs, many=True).data},
#             status=status.HTTP_200_OK,
#         )

# ---- Helpers dates ----
def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(month=2, day=28, year=d.year + years)


def _current_year_bounds_dates():
    today = timezone.localdate()
    y = today.year
    return date(y, 1, 1), date(y, 12, 31)


# class VendorProduitListView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Stock vendeur (groupé ou détail FIFO) + ventes sur période",
#         operation_description=(
#             "Attention : si tu testes avec detail=1, scope est ignoré (tu renvoies toujours le détail stock).\n\n"
#             "Retourne le stock **VendorStock** d’un vendeur.\n\n"
#             "### Accès\n"
#             "- **vendor** : voit uniquement son propre stock\n"
#             "- **manager/admin** : contrôle un vendeur via `vendor_id`\n\n"
#             "### Modes\n"
#             "- **grouped** (défaut) : 1 ligne par produit\n"
#             "- **detail=1** : détail FIFO par lot (VendorStock / ProduitLine)\n\n"
#             "### Scope\n"
#             "- `scope=stock` : stock actuel uniquement\n"
#             "- `scope=sales` : ventes sur période uniquement (`vendue_periode`)\n"
#             "- `scope=both`  : stock + ventes (défaut)\n\n"
#             "### Fenêtre dates (s’applique à `vendue_periode` seulement)\n"
#             "- **vendor** : si aucune date → année en cours\n"
#             "- **manager/admin** : fenêtre max 3 ans\n\n"
#             "### Champs clés\n"
#             "- `quantite_disponible = quantite_allouee - quantite_vendue`\n"
#             "- `vendue_periode` = somme des SALE_OUT sur période\n"
#         ),
#         manual_parameters=[
#             openapi.Parameter(
#                 name="scope",
#                 in_=openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 required=False,
#                 description="`stock|sales|both` (défaut: both)."
#             ),
#             openapi.Parameter(
#                 name="detail",
#                 in_=openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 required=False,
#                 description="`1|true|yes` : détail FIFO par lot. Par défaut: grouped."
#             ),
#             openapi.Parameter(
#                 name="vendor_id",
#                 in_=openapi.IN_QUERY,
#                 type=openapi.TYPE_INTEGER,
#                 required=False,
#                 description="(manager/admin) ID du vendeur à contrôler. Ignoré pour vendor."
#             ),
#             openapi.Parameter(
#                 name="date_from",
#                 in_=openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 required=False,
#                 description="Début période (YYYY-MM-DD) pour `vendue_periode`."
#             ),
#             openapi.Parameter(
#                 name="date_to",
#                 in_=openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 required=False,
#                 description="Fin période (YYYY-MM-DD) pour `vendue_periode`."
#             ),
#             openapi.Parameter(
#                 name="only_sold",
#                 in_=openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 required=False,
#                 description="`1|true|yes` : seulement produits avec `vendue_periode > 0` (scope sales/both)."
#             ),
#         ],
#         responses={200: openapi.Response("OK")},
#         tags=["Vendor / Stock"],
#     )
#     def get(self, request, *args, **kwargs):
#         user = request.user
#         role = get_role_name(user)

#         scope = (request.GET.get("scope") or "both").strip().lower()
#         if scope not in {"stock", "sales", "both"}:
#             scope = "both"

#         detail = (request.GET.get("detail") or "").strip().lower() in {"1", "true", "yes"}
#         only_sold = (request.GET.get("only_sold") or "").strip().lower() in {"1", "true", "yes"}

#         # ✅ déterminer vendeur ciblé
#         if role == "vendor":
#             target_vendor = getattr(user, "staff_vendor_profile", None)
#             if not target_vendor:
#                 return Response({"error": "Profil vendeur introuvable."}, status=403)

#         elif role in {"manager", "admin"}:
#             vendor_id = request.GET.get("vendor_id")
#             if not vendor_id:
#                 return Response({"error": "Paramètre `vendor_id` requis pour manager/admin."}, status=400)
#             try:
#                 vendor_id = int(vendor_id)
#             except ValueError:
#                 return Response({"vendor_id": "Doit être un entier."}, status=400)

#             target_vendor = Vendor.objects.select_related("bijouterie").filter(id=vendor_id).first()
#             if not target_vendor:
#                 return Response({"error": "Vendeur introuvable."}, status=404)

#             # ✅ contrôle bijouterie manager
#             if role == "manager":
#                 user_shop = _user_bijouterie(user)
#                 if not user_shop:
#                     return Response({"error": "Manager non rattaché à une bijouterie."}, status=400)
#                 if getattr(target_vendor, "bijouterie_id", None) != user_shop.id:
#                     return Response({"error": "Ce vendeur n’appartient pas à votre bijouterie."}, status=403)
#         else:
#             return Response({"error": "⛔ Accès refusé"}, status=403)

#         # ✅ Fenêtre dates (pour vendue_periode)
#         df = _parse_date(request.GET.get("date_from"))
#         dt = _parse_date(request.GET.get("date_to"))
#         today = timezone.localdate()

#         if role == "vendor":
#             if not df and not dt:
#                 df, dt = _current_year_bounds_dates()
#             elif df and not dt:
#                 dt = min(_add_years(df, 1) - timedelta(days=1), today)
#             elif dt and not df:
#                 df = date(dt.year, 1, 1)

#             if df and dt and df > dt:
#                 return Response({"error": "`date_from` doit être ≤ `date_to`."}, status=400)

#         else:
#             # manager/admin : max 3 ans si bornes fournies
#             if df and not dt:
#                 dt = min(_add_years(df, 3) - timedelta(days=1), today)

#             if df and dt and df > dt:
#                 return Response({"error": "`date_from` doit être ≤ `date_to`."}, status=400)

#             if df and dt:
#                 max_dt = _add_years(df, 3) - timedelta(days=1)
#                 if dt > max_dt:
#                     return Response({"error": f"Fenêtre max 3 ans. `date_to` ≤ {max_dt}."}, status=400)
#                 dt = min(dt, today)

#         # ✅ Mode detail FIFO (stock actuel uniquement)
#         if detail:
#             vendor_stocks = (
#                 VendorStock.objects
#                 .filter(vendor=target_vendor)
#                 .select_related("produit_line__produit", "produit_line__lot", "vendor")
#                 .order_by("produit_line__lot__received_at", "produit_line_id")
#             )
#             return Response(
#                 {
#                     "mode": "detail",
#                     "scope": "stock",
#                     "period": {"date_from": str(df) if df else None, "date_to": str(dt) if dt else None},
#                     "results": VendorProduitLotSerializer(vendor_stocks, many=True).data,
#                 },
#                 status=200,
#             )

#         # ✅ Subquery vendue_periode seulement si scope inclut sales
#         vendue_subquery = None
#         if scope in {"sales", "both"}:
#             # sale_qs = (
#             #     InventoryMovement.objects
#             #     .filter(
#             #         movement_type=MovementType.SALE_OUT,
#             #         vendor=target_vendor,
#             #         produit_id=OuterRef("produit_id"),
#             #     )
#             # )
#             sale_qs = (
#                 InventoryMovement.objects
#                 .filter(
#                     movement_type=MovementType.SALE_OUT,
#                     vente_ligne__vendor=target_vendor,     # ✅ au lieu de vendor=target_vendor
#                     produit_id=OuterRef("produit_id"),
#                 )
#             )
#             if df:
#                 sale_qs = sale_qs.filter(occurred_at__date__gte=df)
#             if dt:
#                 sale_qs = sale_qs.filter(occurred_at__date__lte=dt)

#             vendue_subquery = (
#                 sale_qs.values("produit_id")
#                 .annotate(total=Coalesce(Sum("qty"), Value(0)))
#                 .values("total")[:1]
#             )

#         # ✅ base grouped
#         qs = (
#             VendorStock.objects
#             .filter(vendor=target_vendor)
#             .values(
#                 produit_id=F("produit_line__produit_id"),
#                 produit_nom=F("produit_line__produit__nom"),
#                 produit_sku=F("produit_line__produit__sku"),
#             )
#         )

#         # ✅ stock fields seulement si scope inclut stock
#         if scope in {"stock", "both"}:
#             qs = qs.annotate(
#                 quantite_allouee=Coalesce(Sum("quantite_allouee"), Value(0), output_field=IntegerField()),
#                 quantite_vendue=Coalesce(Sum("quantite_vendue"), Value(0), output_field=IntegerField()),
#                 quantite_lot=Coalesce(Sum("produit_line__quantite"), Value(0), output_field=IntegerField()),
#             ).annotate(
#                 quantite_disponible=ExpressionWrapper(
#                     F("quantite_allouee") - F("quantite_vendue"),
#                     output_field=IntegerField(),
#                 )
#             )

#         # ✅ sales fields seulement si scope inclut sales
#         if scope in {"sales", "both"}:
#             qs = qs.annotate(
#                 vendue_periode=Coalesce(Subquery(vendue_subquery, output_field=IntegerField()), Value(0)),
#             )

#         qs = qs.order_by("produit_nom")

#         # ✅ only_sold seulement si vendue_periode existe
#         if only_sold and scope in {"sales", "both"}:
#             qs = qs.filter(vendue_periode__gt=0)

#         return Response(
#             {
#                 "mode": "grouped",
#                 "scope": scope,
#                 "period": {"date_from": str(df) if df else None, "date_to": str(dt) if dt else None},
#                 "results": VendorProduitGroupedSerializer(qs, many=True).data,
#             },
#             status=200,
#         )

class VendorStockProduitsView(APIView):
    """
    📦 Stock ACTUEL du vendeur uniquement (VendorStock)

    - grouped (défaut) : 1 ligne par produit
    - detail=1         : détail FIFO par lot
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Stock actuel du vendeur",
        operation_description=(
            "Retourne le **stock actuel** d’un vendeur basé uniquement sur `VendorStock`.\n\n"
            "### Accès\n"
            "- **vendor** : son propre stock\n"
            "- **manager/admin** : stock d’un vendeur via `vendor_id`\n\n"
            "### Modes\n"
            "- **grouped** (défaut) : 1 ligne par produit\n"
            "- **detail=1** : détail FIFO par lot\n\n"
            "❌ Pas de ventes\n"
            "❌ Pas de période\n"
            "❌ Pas de scope\n"
        ),
        manual_parameters=[
            openapi.Parameter(
                name="detail",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
                description="1|true|yes : détail FIFO par lot"
            ),
            openapi.Parameter(
                name="vendor_id",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="(manager/admin) vendeur ciblé"
            ),
        ],
        responses={200: openapi.Response("OK")},
        tags=["Vendor / Stock"],
    )
    def get(self, request):
        user = request.user
        role = get_role_name(user)

        detail = (request.GET.get("detail") or "").lower() in {"1", "true", "yes"}

        # 🔐 Déterminer le vendeur ciblé
        if role == "vendor":
            target_vendor = getattr(user, "staff_vendor_profile", None)
            if not target_vendor:
                return Response({"error": "Profil vendeur introuvable."}, status=403)

        elif role in {"manager", "admin"}:
            vendor_id = request.GET.get("vendor_id")
            if not vendor_id:
                return Response({"error": "`vendor_id` requis."}, status=400)

            try:
                vendor_id = int(vendor_id)
            except ValueError:
                return Response({"vendor_id": "Doit être un entier."}, status=400)

            target_vendor = Vendor.objects.select_related("bijouterie").filter(id=vendor_id).first()
            if not target_vendor:
                return Response({"error": "Vendeur introuvable."}, status=404)

            if role == "manager":
                user_shop = _user_bijouterie(user)
                if not user_shop or target_vendor.bijouterie_id != user_shop.id:
                    return Response({"error": "Vendeur hors de votre bijouterie."}, status=403)

        else:
            return Response({"error": "⛔ Accès refusé"}, status=403)

        # 🔍 MODE DETAIL FIFO
        if detail:
            qs = (
                VendorStock.objects
                .filter(vendor=target_vendor)
                .select_related("produit_line__produit", "produit_line__lot")
                .order_by("produit_line__lot__received_at", "produit_line_id")
            )
            return Response(
                {
                    "mode": "detail",
                    "results": VendorProduitLotSerializer(qs, many=True).data,
                },
                status=200,
            )

        # 📦 MODE GROUPÉ (stock actuel)
        qs = (
            VendorStock.objects
            .filter(vendor=target_vendor)
            .values(
                produit_id=F("produit_line__produit_id"),
                produit_nom=F("produit_line__produit__nom"),
                produit_sku=F("produit_line__produit__sku"),
            )
            .annotate(
                quantite_allouee=Coalesce(Sum("quantite_allouee"), Value(0), output_field=IntegerField()),
                quantite_vendue=Coalesce(Sum("quantite_vendue"), Value(0), output_field=IntegerField()),
                quantite_lot=Coalesce(Sum("produit_line__quantite"), Value(0), output_field=IntegerField()),
            )
            .annotate(
                quantite_disponible=ExpressionWrapper(
                    F("quantite_allouee") - F("quantite_vendue"),
                    output_field=IntegerField(),
                )
            )
            .order_by("produit_nom")
        )

        return Response(
            {
                "mode": "grouped",
                "results": VendorProduitGroupedSerializer(qs, many=True).data,
            },
            status=200,
        )

# class DashboardVendeurStatsAPIView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Dashboard du vendeur connecté.",
#         responses={200: "Données du vendeur et statistiques"}
#     )
#     def get(self, request):
#         user = request.user

#         # Vérifie que c’est bien un vendeur
#         if not user.user_role or user.user_role.role != 'vendor':
#             return Response({"detail": "Accès réservé aux vendeurs."}, status=403)

#         try:
#             vendor = Vendor.objects.get(user=user)
#         except Vendor.DoesNotExist:
#             return Response({"detail": "Profil vendeur introuvable."}, status=404)
        

#         # Produits assignés
#         produits = VendorProduit.objects.filter(vendor=vendor)
#         ventes = VenteProduit.objects.filter(produit__in=produits.values('produit'))

#         # Stats
#         total_produits = produits.count()
#         total_ventes = ventes.count()
#         total_qte_vendue = ventes.aggregate(total=models.Sum('quantite'))['total'] or 0
#         total_ventes_montant = ventes.aggregate(montant=models.Sum('sous_total_prix_vent'))['montant'] or 0
#         stock_total = produits.aggregate(stock=models.Sum('quantite'))['stock'] or 0

#         return Response({
#             "vendeur": VendorSerializer(vendor).data,
#             "produits": total_produits,
#             "ventes": total_ventes,
#             "quantite_totale_vendue": total_qte_vendue,
#             "stock_restant": stock_total,
#             "montant_total_ventes": total_ventes_montant
#         }, status=200)

# endpoint dédié (admin et manager only) pour activer / désactiver un vendeur
# admin puisse activer/désactiver un vendeur depuis un bouton (frontend),
# class ToggleVendorStatusView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]
    
#     @swagger_auto_schema(
#         operation_description="Admin - Mise à jour des statuts du vendeur (verifie).",
#         request_body=VendorSerializer,
#         responses={200: "Statut mis à jour"}
#     )

#     def patch(self, request, user_id):
#         allowed_roles_admin_manager = ['admin', 'manager'] 
#         if not request.user.user_role or request.user.user_role.role not in self.allowed_roles_admin_manager:
#             return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

#         try:
#             target_user = User.objects.get(id=user_id)
#             vendor = Vendor.objects.get(user=target_user)
#             vendor.verifie = not vendor.verifie  # 👈 toggle on/off
#             vendor.save()
#             return Response({
#                 "message": f"✅ Vendeur {'activé' if vendor.verifie else 'désactivé'}.",
#                 "verifie": vendor.verifie
#             })
#         except User.DoesNotExist:
#             return Response({"detail": "Utilisateur introuvable."}, status=404)
#         except Vendor.DoesNotExist:
#             return Response({"detail": "Vendeur introuvable."}, status=404)



# ---------- LISTE / LECTURE ----------
class ListVendorAPIView(APIView):
    """
    GET /api/staff/vendors/

    - Admin  : voit tous les vendeurs
    - Manager: voit uniquement les vendeurs de SA bijouterie

    Filtres (query params) :
      - ?bijouterie_id=...
      - ?bijouterie_nom=...
      - ?verifie=true|false
      - ?q=... (email / prénom / nom)
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminOrManager]

    @swagger_auto_schema(
        operation_summary="Lister les vendeurs (admin / manager)",
        operation_description=(
            "Admin : tous les vendeurs.\n"
            "Manager : uniquement les vendeurs de sa bijouterie.\n\n"
            "Filtres possibles :\n"
            "- `bijouterie_id`\n"
            "- `bijouterie_nom` (contient)\n"
            "- `verifie` = true|false\n"
            "- `q` (recherche email / prénom / nom)\n"
        ),
        manual_parameters=[
            openapi.Parameter("bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, required=False),
            openapi.Parameter("bijouterie_nom", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=False),
            openapi.Parameter("verifie", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=False,
                              description="true ou false"),
            openapi.Parameter("q", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=False,
                              description="Recherche texte (email, prénom, nom)"),
        ],
        tags=["vendeur"],
        responses={200: VendorListSerializer(many=True)},
    )
    def get(self, request):
        user = request.user
        role = get_role_name(user)

        qs = Vendor.objects.select_related("user", "bijouterie")

        # ---- Périmètre selon le rôle ----
        if role == ROLE_MANAGER:
            mgr = (
                Manager.objects
                .filter(user=user)
                .select_related("bijouterie")
                .first()
            )
            bj_id = getattr(getattr(mgr, "bijouterie", None), "id", None)
            if not bj_id:
                return Response([], status=status.HTTP_200_OK)
            qs = qs.filter(bijouterie_id=bj_id)
        elif role == ROLE_ADMIN:
            # admin → pas de restriction
            pass
        else:
            # En théorie IsAdminOrManager bloque déjà, mais on sécurise
            return Response({"detail": "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        # ---- Filtres query params ----
        params = request.query_params

        bj_id = params.get("bijouterie_id")
        if bj_id:
            qs = qs.filter(bijouterie_id=bj_id)

        bj_nom = params.get("bijouterie_nom")
        if bj_nom:
            qs = qs.filter(bijouterie__nom__icontains=bj_nom.strip())

        verifie = params.get("verifie")
        if verifie not in (None, ""):
            v = verifie.lower()
            if v in ("true", "1", "yes", "oui"):
                qs = qs.filter(verifie=True)
            elif v in ("false", "0", "no", "non"):
                qs = qs.filter(verifie=False)

        q = params.get("q")
        if q:
            q = q.strip()
            qs = qs.filter(
                Q(user__email__icontains=q)
                | Q(user__first_name__icontains=q)
                | Q(user__last_name__icontains=q)
            )

        qs = qs.order_by("-created_at")

        ser = VendorListSerializer(qs, many=True)
        return Response(ser.data, status=status.HTTP_200_OK)


# # ---------- DÉTAIL / LECTURE + MÀJ ----------
# class VendorDetailView(APIView):
#     """
#     GET  /api/vendors/<int:id>/
#     GET  /api/vendors/by-slug/<slug:slug>/
#     PATCH/PUT idem (avec VendorUpdateSerializer)
#     """
#     permission_classes = [permissions.IsAuthenticated]

#     def _get_obj(self, **kwargs):
#         vendor_id = kwargs.get("id") or kwargs.get("pk")
#         slug = kwargs.get("slug") or self.request.query_params.get("slug")

#         if vendor_id:
#             return get_object_or_404(
#                 Vendor.objects.select_related("user", "bijouterie"),
#                 pk=vendor_id
#             )
#         if slug:
#             return get_object_or_404(
#                 Vendor.objects.select_related("user", "bijouterie"),
#                 user__slug=slug
#             )
#         # Fallback explicite
#         return get_object_or_404(
#             Vendor.objects.select_related("user", "bijouterie"),
#             pk=self.request.query_params.get("id")
#         )

#     def _can_update(self, request, vendor: Vendor) -> bool:
#         role = getattr(getattr(request.user, "user_role", None), "role", None)
#         is_admin_or_manager = role in {"admin", "manager"}
#         is_owner = vendor.user_id == request.user.id
#         return bool(is_admin_or_manager or is_owner)

#     # --- GET ---
#     @swagger_auto_schema(
#         responses={200: VendorReadSerializer},
#         manual_parameters=[
#             openapi.Parameter("slug", openapi.IN_QUERY, description="(optionnel si non fourni dans l'URL) user.slug", type=openapi.TYPE_STRING),
#             openapi.Parameter("id", openapi.IN_QUERY, description="(optionnel si non fourni dans l'URL) vendor id", type=openapi.TYPE_INTEGER),
#         ],
#     )
#     def get(self, request, *args, **kwargs):
#         vendor = self._get_obj(**kwargs)
#         return Response(VendorReadSerializer(vendor).data)

#     # --- PATCH ---
#     @swagger_auto_schema(
#         request_body=VendorUpdateSerializer,
#         responses={200: VendorReadSerializer, 403: "Access Denied"},
#     )
#     def patch(self, request, *args, **kwargs):
#         vendor = self._get_obj(**kwargs)
#         if not self._can_update(request, vendor):
#             return Response({"detail": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

#         s = VendorUpdateSerializer(vendor, data=request.data, partial=True)
#         s.is_valid(raise_exception=True)
#         s.save()
#         return Response(VendorReadSerializer(vendor).data, status=200)

#     # --- PUT (comportement identique, mais non-partial) ---
#     @swagger_auto_schema(
#         request_body=VendorUpdateSerializer,
#         responses={200: VendorReadSerializer, 403: "Access Denied"},
#     )
#     def put(self, request, *args, **kwargs):
#         vendor = self._get_obj(**kwargs)
#         if not self._can_update(request, vendor):
#             return Response({"detail": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

#         s = VendorUpdateSerializer(vendor, data=request.data, partial=False)
#         s.is_valid(raise_exception=True)
#         s.save()
#         return Response(VendorReadSerializer(vendor).data, status=200)


# class UpdateVendorStatusAPIView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]
#     ALLOWED_ROLES = {"admin", "manager"}

#     @swagger_auto_schema(
#         operation_summary="Mise à jour du statut vendeur (verifie)",
#         operation_description="Active/Désactive un vendeur via le champ booléen 'verifie'. "
#                               "Autorisé: admin, manager.",
#         request_body=VendorStatusInputSerializer,
#         responses={200: "Statut mis à jour", 403: "Accès refusé", 404: "Vendeur introuvable"}
#     )
#     def patch(self, request, user_id: int):
#         # 1) Rôle
#         role = getattr(getattr(request.user, "user_role", None), "role", None)
#         if role not in self.ALLOWED_ROLES:
#             return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

#         # 2) Vendeur
#         vendor = Vendor.objects.select_related("user").filter(user_id=user_id).first()
#         if not vendor:
#             return Response({"detail": "Vendeur introuvable."}, status=status.HTTP_404_NOT_FOUND)

#         # 3) (Optionnel) Si manager, vérifier même bijouterie
#         # my_shop_id = getattr(getattr(request.user, "staff_manager_profile", None), "bijouterie_id", None)
#         # if role == "manager" and my_shop_id and vendor.bijouterie_id != my_shop_id:
#         #     return Response({"detail": "Vendeur d'une autre bijouterie."}, status=status.HTTP_403_FORBIDDEN)

#         # 4) Validation du champ 'verifie'
#         s = VendorStatusInputSerializer(data=request.data)
#         s.is_valid(raise_exception=True)

#         old = bool(vendor.verifie)
#         vendor.verifie = s.validated_data["verifie"]
#         vendor.save(update_fields=["verifie"])

#         return Response({
#             "message": f"✅ Vendeur {'activé' if vendor.verifie else 'désactivé'}.",
#             "vendor_id": vendor.id,
#             "user_id": vendor.user_id,
#             "verifie_avant": old,
#             "verifie_apres": vendor.verifie,
#             "email": getattr(vendor.user, "email", None),
#         }, status=status.HTTP_200_OK)


class VendorUpdateView(APIView):
    """
    PUT /api/staff/vendor/<vendor_id>/update

    - Admin : peut modifier n’importe quel vendeur
    - Manager : ne peut modifier que les vendeurs de SA bijouterie
    - Champs modifiables :
        - email (user.email)
        - bijouterie_nom (rattacher à une autre bijouterie)
        - verifie, raison_desactivation (profil Vendor)
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]

    @swagger_auto_schema(
        operation_summary="Mettre à jour un vendeur (email, bijouterie, statut)",
        manual_parameters=[
            openapi.Parameter(
                name="vendor_id",
                in_=openapi.IN_PATH,
                type=openapi.TYPE_INTEGER,
                description="ID du vendeur à mettre à jour",
                required=True,
            )
        ],
        request_body=VendorUpdateSerializer,
        responses={
            200: openapi.Response(
                description="Vendeur mis à jour",
                examples={
                    "application/json": {
                        "message": "Vendeur mis à jour avec succès.",
                        "vendor": {
                            "id": 3,
                            "full_name": "Jean Dupont",
                            "email": "vendor@example.com",
                            "verifie": True,
                            "raison_desactivation": None,
                            "bijouterie": {
                                "id": 2,
                                "nom": "Bijouterie Centre",
                            },
                        },
                    }
                },
            ),
            400: "Requête invalide",
            403: "Accès refusé",
            404: "Vendeur introuvable",
        },
        tags=["vendeur"],
    )
    def put(self, request, vendor_id):
        # 1) Récupération du vendeur
        vendor = get_object_or_404(
            Vendor.objects.select_related("user", "bijouterie"),
            pk=vendor_id
        )

        # 2) Vérification périmètre manager
        role = get_role_name(request.user)
        if role == ROLE_MANAGER:
            mgr = (
                Manager.objects
                .filter(user=request.user)
                .select_related("bijouterie")
                .first()
            )
            mgr_bj_id = getattr(getattr(mgr, "bijouterie", None), "id", None)
            if not mgr_bj_id or vendor.bijouterie_id != mgr_bj_id:
                return Response(
                    {"detail": "Vous ne pouvez modifier que les vendeurs de votre bijouterie."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # 3) Validation des données
        ser = VendorUpdateSerializer(
            data=request.data,
            context={"user_id": vendor.user_id}
        )
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        user = vendor.user

        # 4) Appliquer les modifications
        # email user
        if "email" in data:
            user.email = data["email"]
            user.save(update_fields=["email"])

        # bijouterie (via bijouterie_nom => instance)
        if "bijouterie_nom" in data:
            bj = data["bijouterie_nom"]  # ici c’est une instance ou None
            vendor.bijouterie = bj

        # verifie / raison_desactivation
        if "verifie" in data:
            vendor.verifie = data["verifie"]
        if "raison_desactivation" in data:
            vendor.raison_desactivation = data["raison_desactivation"]

        vendor.save()

        # 5) Réponse
        bj = vendor.bijouterie
        payload = {
            "message": "Vendeur mis à jour avec succès.",
            "vendor": {
                "id": vendor.id,
                "full_name": getattr(vendor, "full_name", "") or "",
                "email": user.email if user else None,
                "verifie": vendor.verifie,
                "raison_desactivation": vendor.raison_desactivation,
                "bijouterie": {
                    "id": bj.id,
                    "nom": bj.nom,
                } if bj else None,
            },
        }
        return Response(payload, status=status.HTTP_200_OK)


# class VendorProduitAssociationAPIView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]
#     allowed_roles_admin_manager = ['admin', 'manager']

#     @swagger_auto_schema(
#         operation_description="Associer des produits à un vendeur et ajuster les stocks.",
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["email", "produits"],
#             properties={
#                 "email": openapi.Schema(type=openapi.TYPE_STRING),
#                 "produits": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["produit_id", "quantite"],
#                         properties={
#                             "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "quantite": openapi.Schema(type=openapi.TYPE_INTEGER),
#                         }
#                     )
#                 )
#             }
#         ),
#         responses={201: "Produits associés", 400: "Requête invalide", 403: "Accès refusé", 404: "Ressource introuvable"}
#     )
#     @transaction.atomic
#     def post(self, request):
#         if not request.user.user_role or request.user.user_role.role not in self.allowed_roles_admin_manager:
#             return Response({"message": "⛔ Accès refusé"}, status=403)

#         email = request.data.get("email")
#         produits_data = request.data.get("produits", [])

#         if not email:
#             return Response({"error": "L'email du vendeur est requis."}, status=400)

#         try:
#             vendor = Vendor.objects.select_related("user").get(user__email=email)
#         except Vendor.DoesNotExist:
#             return Response({"error": "Vendeur introuvable."}, status=404)

#         if not vendor.active:
#             return Response({"error": "Ce vendeur est désactivé."}, status=403)

#         if not produits_data:
#             return Response({"error": "La liste des produits est vide."}, status=400)

#         produits_associes = []

#         for produit_info in produits_data:
#             produit_id = produit_info.get("produit_id")
#             quantite = produit_info.get("quantite")

#             if not produit_id or quantite is None:
#                 return Response({"error": "Chaque produit doit avoir un `produit_id` et une `quantite`."}, status=400)

#             try:
#                 quantite = int(quantite)
#                 if quantite <= 0:
#                     return Response({"error": "Quantité doit être strictement positive."}, status=400)
#             except Exception:
#                 return Response({"error": "Quantité invalide."}, status=400)

#             try:
#                 produit = Produit.objects.get(id=produit_id)
#             except Produit.DoesNotExist:
#                 return Response({"error": f"Produit ID {produit_id} introuvable."}, status=404)

#             stock = Stock.objects.filter(produit=produit).first()
#             if not stock or stock.quantite < quantite:
#                 return Response({
#                     "error": f"Stock insuffisant pour le produit {produit.nom}. Stock actuel : {stock.quantite if stock else 0}"
#                 }, status=400)

#             vendor_produit, created = VendorProduit.objects.get_or_create(
#                 vendor=vendor,
#                 produit=produit,
#                 defaults={"quantite": quantite}
#             )

#             if not created:
#                 vendor_produit.quantite += quantite
#                 vendor_produit.save()

#             stock.quantite -= quantite
#             stock.save()

#             produits_associes.append({
#                 "produit_id": produit.id,
#                 "nom": produit.nom,
#                 "quantite_attribuee": quantite,
#                 "stock_vendeur": vendor_produit.quantite,
#                 "stock_restant_global": stock.quantite,
#                 "status": "créé" if created else "mis à jour"
#             })

#         return Response({
#             "message": "✅ Produits associés avec succès.",
#             "vendeur": {
#                 "id": vendor.id,
#                 "nom_complet": vendor.user.get_full_name(),
#                 "email": vendor.user.email
#             },
#             "produits": produits_associes
#         }, status=201)


# class VendorProduitAssociationAPIView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]
#     allowed_roles_admin_manager = {"admin", "manager"}

#     @swagger_auto_schema(
#         operation_description="Associer des produits à un vendeur et ajuster les stocks.",
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["email", "produits"],
#             properties={
#                 "email": openapi.Schema(type=openapi.TYPE_STRING),
#                 "produits": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["produit_id", "quantite"],
#                         properties={
#                             "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, description="> 0"),
#                         }
#                     )
#                 )
#             }
#         ),
#         responses={201: "Produits associés", 400: "Requête invalide", 403: "Accès refusé", 404: "Ressource introuvable"}
#     )
#     @transaction.atomic
#     def post(self, request):
#         # 1) Permissions
#         role = getattr(getattr(request.user, "user_role", None), "role", None)
#         if role not in self.allowed_roles_admin_manager:
#             return Response({"message": "⛔ Accès refusé"}, status=403)

#         # 2) Entrées
#         email = request.data.get("email")
#         produits_data = request.data.get("produits", [])

#         if not email:
#             return Response({"error": "L'email du vendeur est requis."}, status=400)
#         if not isinstance(produits_data, list) or not produits_data:
#             return Response({"error": "La liste des produits est vide ou invalide."}, status=400)

#         # 3) Vendeur
#         try:
#             vendor = Vendor.objects.select_related("user").get(user__email=email)
#         except Vendor.DoesNotExist:
#             return Response({"error": "Vendeur introuvable."}, status=404)

#         # ⚠️ Correction ici : 'verifie' (pas 'active')
#         if not vendor.verifie:
#             return Response({"error": "Ce vendeur est désactivé."}, status=403)

#         # 4) Normaliser/agréger les lignes (doublons produit_id -> somme des quantités)
#         demandes = defaultdict(int)
#         for item in produits_data:
#             try:
#                 pid = int(item.get("produit_id"))
#                 qty = int(item.get("quantite"))
#             except Exception:
#                 return Response({"error": "Chaque item doit contenir un produit_id et une quantite (entiers)."}, status=400)
#             if pid <= 0 or qty <= 0:
#                 return Response({"error": "produit_id et quantite doivent être > 0."}, status=400)
#             demandes[pid] += qty

#         # 5) Vérifier l’existence des produits demandés
#         produits = Produit.objects.filter(id__in=demandes.keys())
#         if produits.count() != len(demandes):
#             ids_trouves = set(produits.values_list("id", flat=True))
#             manquants = [pid for pid in demandes.keys() if pid not in ids_trouves]
#             return Response({"error": f"Produit(s) introuvable(s): {manquants}"}, status=404)

#         produits_by_id = {p.id: p for p in produits}

#         # 6) Préparer la réponse
#         produits_associes = []

#         # 7) Traiter chaque produit avec verrouillage ligne par ligne
#         for pid, qty in demandes.items():
#             produit = produits_by_id[pid]

#             # 7.a Stock global verrouillé (évite les races)
#             stock = (
#                 Stock.objects.select_for_update()
#                 .filter(produit_id=pid)
#                 .first()
#             )
#             if not stock:
#                 return Response({"error": f"Aucun stock pour le produit {produit.nom}."}, status=400)

#             if stock.quantite < qty:
#                 return Response(
#                     {"error": f"Stock insuffisant pour {produit.nom}. Stock actuel : {stock.quantite}, demandé : {qty}"},
#                     status=400,
#                 )

#             # 7.b Décrémente atomiquement si assez de stock
#             updated = (
#                 Stock.objects
#                 .filter(pk=stock.pk, quantite__gte=qty)
#                 .update(quantite=F("quantite") - qty)
#             )
#             if not updated:
#                 # Quelqu'un a peut-être pris le stock entre-temps
#                 return Response(
#                     {"error": f"Conflit de stock détecté pour {produit.nom}. Réessayez."},
#                     status=409,
#                 )
#             stock.refresh_from_db()

#             # 7.c Associer au vendeur (verrouiller/mettre à jour la ligne VendorProduit)
#             vp = (
#                 VendorProduit.objects.select_for_update()
#                 .filter(vendor=vendor, produit_id=pid)
#                 .first()
#             )
#             if vp:
#                 vp.quantite = F("quantite") + qty
#                 vp.save(update_fields=["quantite"])
#                 vp.refresh_from_db()
#                 status_item = "mis à jour"
#             else:
#                 vp = VendorProduit.objects.create(vendor=vendor, produit_id=pid, quantite=qty)
#                 status_item = "créé"

#             produits_associes.append({
#                 "produit_id": produit.id,
#                 "nom": produit.nom,
#                 "quantite_attribuee": qty,
#                 "stock_vendeur": vp.quantite,
#                 "stock_restant_global": stock.quantite,
#                 "status": status_item,
#             })

#         # 8) OK
#         return Response({
#             "message": "✅ Produits associés avec succès.",
#             "vendeur": {
#                 "id": vendor.id,
#                 "nom_complet": vendor.user.get_full_name() if vendor.user else "",
#                 "email": vendor.user.email if vendor.user else "",
#             },
#             "produits": produits_associes
#         }, status=201)


# class VendorProduitAssociationAPIView(APIView):
#     permission_classes = [permissions.IsAuthenticated]
#     allowed_roles_admin_manager = {"admin", "manager"}

#     @swagger_auto_schema(
#         operation_description=(
#             "tu peux faire évoluer VendorProduitAssociationAPIView pour gérer deux sources d’affectation :"
#             "Depuis un lot d’achat (affectation par lots) → on prélève sur le lot, on crédite le vendeur, "
#             "et on trace un InventoryMovement de type ALLOCATE (RESERVED → BIJOUTERIE)."
#             "Depuis le stock boutique “libre” (affectation directe) → on décrémente Stock, "
#             "on crédite le vendeur, sans mouvement d’inventaire (sinon tu compterais deux fois).\n\n"
#             "Associer des produits à un vendeur.\n\n"
#             "Deux modes par item :\n"
#             "- **Depuis un lot**: fournir `lot_id` + `quantite` (trace un mouvement ALLOCATE Reserved→Bijouterie).\n"
#             "- **Depuis le stock**: fournir `produit_id` + `quantite` (décrémente Stock, crédite le vendeur).\n"
#             "Ne pas mélanger `lot_id` et `produit_id` dans le même item."
#         ),
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["email", "items"],
#             properties={
#                 "email": openapi.Schema(type=openapi.TYPE_STRING, description="Email du vendeur cible"),
#                 "items": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["quantite"],
#                         properties={
#                             "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, description="> 0"),
#                             "lot_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="Affection par lot (option 1)"),
#                             "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="Affection depuis stock (option 2)"),
#                         }
#                     )
#                 )
#             }
#         ),
#         responses={
#             201: "Produits associés",
#             400: "Requête invalide",
#             403: "Accès refusé",
#             404: "Ressource introuvable"
#         }
#     )
#     @transaction.atomic
#     def post(self, request):
#         # --- 1) Permissions
#         role = getattr(getattr(request.user, "user_role", None), "role", None)
#         if role not in self.allowed_roles_admin_manager:
#             return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

#         # --- 2) Entrées
#         email = (request.data.get("email") or "").strip()
#         items = request.data.get("items") or []
#         if not email:
#             return Response({"error": "L'email du vendeur est requis."}, status=400)
#         if not isinstance(items, list) or not items:
#             return Response({"error": "La liste 'items' est vide ou invalide."}, status=400)

#         # --- 3) Vendeur + bijouterie
#         try:
#             vendor = Vendor.objects.select_related("user", "bijouterie").get(user__email__iexact=email)
#         except Vendor.DoesNotExist:
#             return Response({"error": "Vendeur introuvable."}, status=404)
#         if not vendor.verifie:
#             return Response({"error": "Ce vendeur est désactivé."}, status=403)
#         if not vendor.bijouterie_id:
#             return Response({"error": "Ce vendeur n’est rattaché à aucune bijouterie."}, status=400)
#         bijouterie: Bijouterie = vendor.bijouterie

#         # --- 4) Normalisation / agrégation
#         # On sépare les lignes lot vs stock et on agrège par clé (pour verrouiller une seule fois)
#         demandes_stock = defaultdict(int)   # {produit_id: total_qty}
#         demandes_lot   = defaultdict(int)   # {lot_id: total_qty}
#         lignes_norm    = []                 # pour la réponse

#         for raw in items:
#             try:
#                 qty = int(raw.get("quantite"))
#             except Exception:
#                 return Response({"error": "Chaque item doit contenir 'quantite' entière > 0."}, status=400)
#             if qty <= 0:
#                 return Response({"error": "quantite doit être > 0."}, status=400)

#             lot_id = raw.get("lot_id")
#             pid    = raw.get("produit_id")

#             if bool(lot_id) == bool(pid):
#                 return Response({"error": "Un item doit avoir soit 'lot_id' soit 'produit_id', pas les deux."}, status=400)

#             if lot_id:
#                 try:
#                     lot_id = int(lot_id)
#                 except Exception:
#                     return Response({"error": "lot_id doit être entier."}, status=400)
#                 demandes_lot[lot_id] += qty
#                 lignes_norm.append({"source": "lot", "lot_id": lot_id, "quantite": qty})
#             else:
#                 try:
#                     pid = int(pid)
#                 except Exception:
#                     return Response({"error": "produit_id doit être entier."}, status=400)
#                 demandes_stock[pid] += qty
#                 lignes_norm.append({"source": "stock", "produit_id": pid, "quantite": qty})

#         # --- 5) Préchargements
#         produits = {}
#         if demandes_stock:
#             qs_p = Produit.objects.in_bulk(demandes_stock.keys())
#             if len(qs_p) != len(demandes_stock):
#                 manq = sorted(set(demandes_stock.keys()) - set(qs_p.keys()))
#                 return Response({"error": f"Produit(s) introuvable(s): {manq}"}, status=404)
#             produits = qs_p

#         lots = {}
#         if demandes_lot:
#             # ⚠️ TODO : aligne les noms de champs de lot :
#             # - produit (FK → store.Produit)
#             # - quantite_restante ou available_qty
#             # - achat_produit (FK → AchatProduit) si tu veux tracer la ligne d’achat
#             lots_qs = (
#                 AchatProduitLot.objects
#                 .select_for_update()
#                 .select_related("produit")              # TODO: s'assure que le FK s'appelle bien 'produit'
#                 .filter(id__in=demandes_lot.keys())
#             )
#             lots = {l.id: l for l in lots_qs}
#             if len(lots) != len(demandes_lot):
#                 manq = sorted(set(demandes_lot.keys()) - set(lots.keys()))
#                 return Response({"error": f"Lot(s) introuvable(s): {manq}"}, status=404)

#         # --- 6) Traitement (lot → vendeur)
#         result_items = []
#         now = timezone.now()

#         for lot_id, qty in demandes_lot.items():
#             lot = lots[lot_id]
#             produit = getattr(lot, "produit", None)
#             if not produit:
#                 return Response({"error": f"Le lot #{lot_id} n’a pas de produit."}, status=400)

#             # ⚠️ TODO : remplace 'quantite_restante' par ton champ réel (ex: available_qty, reste, etc.)
#             dispo = getattr(lot, "quantite_restante", None)
#             if dispo is None:
#                 return Response({"error": "Le modèle de lot doit exposer la quantité disponible (ex: 'quantite_restante')."}, status=500)
#             if dispo < qty:
#                 return Response({"error": f"Lot #{lot_id} : quantité disponible insuffisante ({dispo} < {qty})."}, status=400)

#             # Décrément du lot
#             setattr(lot, "quantite_restante", dispo - qty)  # TODO: adapte le champ
#             lot.save(update_fields=["quantite_restante"])    # TODO: idem

#             # Crédit du vendeur (VendorProduit)
#             vp, created = VendorProduit.objects.select_for_update().get_or_create(
#                 vendor=vendor, produit=produit, defaults={"quantite": 0}
#             )
#             VendorProduit.objects.filter(pk=vp.pk).update(quantite=F("quantite") + qty)
#             vp.refresh_from_db(fields=["quantite"])

#             # Mouvement inventaire ALLOCATE (Reserved → Bijouterie)
#             InventoryMovement.objects.create(
#                 produit=produit,
#                 movement_type=MovementType.ALLOCATE,
#                 qty=qty,
#                 unit_cost=getattr(lot, "unit_cost", None),  # si dispo sur ton lot
#                 lot=lot,
#                 reason=f"Affectation lot #{lot_id} → vendeur {vendor.id}",
#                 src_bucket=Bucket.RESERVED,
#                 src_bijouterie=None,
#                 dst_bucket=Bucket.BIJOUTERIE,
#                 dst_bijouterie=bijouterie,
#                 # Liens achat si dispo
#                 achat=getattr(getattr(lot, "achat_produit", None), "achat", None),   # TODO: adapte
#                 achat_ligne=getattr(lot, "achat_produit", None),                     # TODO: adapte
#                 occurred_at=now,
#                 created_by=request.user,
#             )

#             result_items.append({
#                 "source": "lot",
#                 "lot_id": lot_id,
#                 "produit_id": produit.id,
#                 "produit_nom": getattr(produit, "nom", produit.id),
#                 "quantite": qty,
#                 "stock_vendeur": vp.quantite,
#                 "message": "Affecté depuis lot + mouvement ALLOCATE créé"
#             })

#         # --- 7) Traitement (stock → vendeur)
#         if demandes_stock:
#             # lock les lignes de stock correspondantes
#             stocks = {s.produit_id: s for s in
#                       Stock.objects.select_for_update().filter(produit_id__in=demandes_stock.keys())}
#             if len(stocks) != len(demandes_stock):
#                 manq = sorted(set(demandes_stock.keys()) - set(stocks.keys()))
#                 return Response({"error": f"Stock indisponible pour produit(s): {manq}"}, status=400)

#             for pid, qty in demandes_stock.items():
#                 produit = produits[pid]
#                 stock = stocks[pid]

#                 if stock.quantite < qty:
#                     return Response(
#                         {"error": f"Stock insuffisant pour {getattr(produit, 'nom', pid)}. "
#                                   f"Stock actuel: {stock.quantite}, demandé: {qty}"},
#                         status=400
#                     )

#                 # Décrément atomique du stock
#                 updated = Stock.objects.filter(pk=stock.pk, quantite__gte=qty)\
#                                        .update(quantite=F("quantite") - qty)
#                 if not updated:
#                     return Response({"error": f"Conflit de stock pour {getattr(produit, 'nom', pid)}. Réessayez."}, status=409)
#                 stock.refresh_from_db(fields=["quantite"])

#                 # Crédit du vendeur
#                 vp, created = VendorProduit.objects.select_for_update().get_or_create(
#                     vendor=vendor, produit=produit, defaults={"quantite": 0}
#                 )
#                 VendorProduit.objects.filter(pk=vp.pk).update(quantite=F("quantite") + qty)
#                 vp.refresh_from_db(fields=["quantite"])

#                 # Pas de mouvement d’inventaire ici (interne boutique → vendeur)
#                 result_items.append({
#                     "source": "stock",
#                     "produit_id": produit.id,
#                     "produit_nom": getattr(produit, "nom", produit.id),
#                     "quantite": qty,
#                     "stock_vendeur": vp.quantite,
#                     "stock_boutique_restant": stock.quantite,
#                     "message": "Affecté depuis stock (sans mouvement inventaire)"
#                 })

#         # --- 8) Réponse
#         return Response({
#             "message": "✅ Affectations effectuées.",
#             "vendeur": {
#                 "id": vendor.id,
#                 "email": vendor.user.email if vendor.user else None,
#                 "bijouterie_id": bijouterie.id,
#                 "bijouterie": getattr(bijouterie, "nom", None),
#             },
#             "items": result_items
#         }, status=201)



# class VendorProduitAssociationAPIView(APIView):
#     """
#     Affecte des produits d'une **bijouterie source** vers un **vendeur** :
#       - Détermination automatique de la bijouterie via l'email du vendeur si `src_bijouterie_id` n'est pas fourni.
#       - Décrément du stock *de la bijouterie source*.
#       - Mise à jour du stock vendeur (VendorProduit).
#       - Journalisation `VENDOR_ASSIGN` (traçabilité possible via lot_id).
#       Explication:
#       Voici ce que signifie le champ status renvoyé pour chaque ligne de produit :

#     "créé"
#         → C’est la première fois que ce vendeur reçoit ce produit.
#     "mis à jour"
#         → Le vendeur avait déjà ce produit dans son stock.
#         L’API incrémente simplement la quantité existante (quantite = quantite + attribuée) sur la même ligne VendorProduit. 
#         On ne crée pas de nouvelle ligne ; on met à jour la ligne existante.
    
#     Quelques points à bien retenir :

#         Le statut est par paire (vendeur, produit), pas par lot_id.
#         Même si tu fournis un lot_id différent, si le vendeur possède déjà ce produit, ce sera "mis à jour" 
#         (la traçabilité du lot est dans le mouvement InventoryMovement, pas dans VendorProduit).
    
#     En résumé :
#         "créé" = nouvelle ligne VendorProduit(vendor, produit) créée.
#         "mis à jour" = ligne déjà existante, quantité augmentée (ou ajustée).
    
#     Exemple de payload pour “réduction”
#         {
#         "email": "vendeur@exemple.com",
#         "produits": [
#             { "produit_id": 12, "set_stock_vendeur": 5 }
#         ]
#         }
#     Explication du payload:
#     S’il en avait 9, on fait –4 côté vendeur et +4 en bijouterie, 
#     et on journalise un ADJUSTMENT (dst=BIJOUTERIE) pour la traçabilité retour.

#     Remarque lot : le lot_id que tu envoies ici traçera cette opération (nouvelle affectation). 
#     Ça ne remplace pas le lot_id d’un mouvement passé (on ne réécrit pas l’historique).
        
#     """
#     permission_classes = [IsAuthenticated]
#     allowed_roles_admin_manager = {"admin", "manager"}

#     @swagger_auto_schema(
#         operation_summary="Affecter des produits à un vendeur (déduction bijouterie source automatique)",
#         operation_description=(
#             "- Si `src_bijouterie_id` est omis, on le déduit de `vendor.bijouterie_id` (via l'email).\n"
#             "- Si `src_bijouterie_id` est fourni ET que le vendeur a une bijouterie, ils doivent correspondre.\n"
#             "- `lot_id` est **optionnel** (traçabilité). On **ne décrémente pas** le lot d’achat ici.\n"
#             "- Le stock décrémenté est celui de la **bijouterie source**, pas le réservé."
#         ),
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["email", "produits"],
#             properties={
#                 "email": openapi.Schema(type=openapi.TYPE_STRING, description="Email du vendeur"),
#                 "src_bijouterie_id": openapi.Schema(
#                     type=openapi.TYPE_INTEGER,
#                     description="Bijouterie source (optionnel si vend. rattaché)"
#                 ),
#                 "produits": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["produit_id", "quantite"],
#                         properties={
#                             "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, description="> 0"),
#                             "lot_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="Optionnel (traçabilité)"),
#                         }
#                     )
#                 )
#             }
#         ),
#         responses={
#             201: "Produits affectés",
#             400: "Requête invalide",
#             403: "Accès refusé",
#             404: "Ressource introuvable",
#             409: "Conflit de stock",
#         },
#         tags=["vendeur"],
#     )
#     @transaction.atomic
#     def post(self, request):
#         # 1) Permissions
#         role = getattr(getattr(request.user, "user_role", None), "role", None)
#         if role not in self.allowed_roles_admin_manager:
#             return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

#         # 2) Entrées de base
#         email = request.data.get("email")
#         produits_data = request.data.get("produits", [])
#         payload_src_bij = request.data.get("src_bijouterie_id")

#         if not email:
#             return Response({"error": "L'email du vendeur est requis."}, status=400)
#         if not isinstance(produits_data, list) or not produits_data:
#             return Response({"error": "La liste des produits est vide ou invalide."}, status=400)

#         # 3) Vendeur + bijouterie source (déduction si nécessaire)
#         try:
#             vendor = Vendor.objects.select_related("user", "bijouterie").get(user__email=email)
#         except Vendor.DoesNotExist:
#             return Response({"error": "Vendeur introuvable."}, status=404)
#         if not vendor.verifie:
#             return Response({"error": "Ce vendeur est désactivé."}, status=403)

#         vendor_bij = getattr(vendor, "bijouterie_id", None)
#         if payload_src_bij is None and vendor_bij is None:
#             return Response(
#                 {"error": "Impossible de déterminer la bijouterie source. "
#                           "Renseigne 'src_bijouterie_id' ou rattache le vendeur à une bijouterie."},
#                 status=400
#             )

#         if payload_src_bij is not None:
#             try:
#                 src_bijouterie_id = int(payload_src_bij)
#             except Exception:
#                 return Response({"error": "'src_bijouterie_id' doit être un entier."}, status=400)

#             if not Bijouterie.objects.filter(pk=src_bijouterie_id).exists():
#                 return Response({"error": f"Bijouterie #{src_bijouterie_id} introuvable."}, status=404)

#             if vendor_bij and vendor_bij != src_bijouterie_id:
#                 return Response(
#                     {"error": "Incohérence : la bijouterie fournie ne correspond pas à celle du vendeur."},
#                     status=400
#                 )
#         else:
#             src_bijouterie_id = vendor_bij

#         # 4) Validation/chargement des items (on ne regroupe pas pour préserver lot_id par ligne)
#         cleaned_items, produit_ids, lot_ids = [], set(), set()
#         for idx, raw in enumerate(produits_data, start=1):
#             try:
#                 pid = int(raw.get("produit_id"))
#                 qty = int(raw.get("quantite"))
#             except Exception:
#                 return Response(
#                     {"error": f"Item {idx}: 'produit_id' et 'quantite' doivent être des entiers."}, status=400
#                 )
#             if pid <= 0 or qty <= 0:
#                 return Response({"error": f"Item {idx}: 'produit_id' et 'quantite' doivent être > 0."}, status=400)

#             lot_id = raw.get("lot_id")
#             if lot_id is not None:
#                 try:
#                     lot_id = int(lot_id)
#                     if lot_id <= 0:
#                         return Response({"error": f"Item {idx}: 'lot_id' doit être > 0."}, status=400)
#                     lot_ids.add(lot_id)
#                 except Exception:
#                     return Response({"error": f"Item {idx}: 'lot_id' doit être un entier."}, status=400)

#             produit_ids.add(pid)
#             cleaned_items.append({"produit_id": pid, "quantite": qty, "lot_id": lot_id})

#         # 5) Existence produits
#         produits = Produit.objects.filter(id__in=produit_ids)
#         if produits.count() != len(produit_ids):
#             ids_ok = set(produits.values_list("id", flat=True))
#             manquants = [p for p in produit_ids if p not in ids_ok]
#             return Response({"error": f"Produit(s) introuvable(s) : {manquants}"}, status=404)
#         produits_by_id = {p.id: p for p in produits}

#         # 6) Traitement items
#         result = []
#         now = timezone.now()

#         for idx, item in enumerate(cleaned_items, start=1):
#             pid = item["produit_id"]
#             qty = item["quantite"]
#             lot_id = item["lot_id"]
#             produit = produits_by_id[pid]

#             # 6.a Vérrouillage + décrément du stock de la bijouterie source
#             stock = (Stock.objects
#                      .select_for_update()
#                      .filter(produit_id=pid, bijouterie_id=src_bijouterie_id)
#                      .first())
#             if not stock:
#                 return Response(
#                     {"error": f"Aucun stock en bijouterie #{src_bijouterie_id} pour le produit {produit.nom}."}, status=400
#                 )
#             if stock.quantite < qty:
#                 return Response(
#                     {"error": f"Stock insuffisant en bijouterie #{src_bijouterie_id} pour {produit.nom}. "
#                               f"Stock actuel : {stock.quantite}, demandé : {qty}"},
#                     status=400
#                 )
#             updated = (Stock.objects
#                        .filter(pk=stock.pk, quantite__gte=qty)
#                        .update(quantite=F("quantite") - qty))
#             if not updated:
#                 return Response({"error": "Conflit de stock détecté. Réessayez."}, status=409)
#             stock.refresh_from_db(fields=["quantite"])

#             # 6.b Incrément du stock vendeur (VendorProduit)
#             vs = (VendorStock.objects
#                   .select_for_update()
#                   .filter(vendor=vendor, produit_id=pid)
#                   .first())
#             if vs:
#                 VendorStock.objects.filter(pk=vs.pk).update(quantite=F("quantite") + qty)
#                 vs.refresh_from_db(fields=["quantite"])
#                 status_item = "mis à jour"
#             else:
#                 vs = VendorStock.objects.create(vendor=vendor, produit_id=pid, quantite=qty)
#                 status_item = "créé"

#             # 6.c Mouvement VENDOR_ASSIGN (traçabilité + origine bijouterie)
#             InventoryMovement.objects.create(
#                 produit=produit,
#                 movement_type=MovementType.VENDOR_ASSIGN,
#                 qty=qty,
#                 unit_cost=None,              # pas de coût calculé ici
#                 lot_id=lot_id,               # traçabilité (optionnel)
#                 reason=f"Affectation au vendeur #{vendor.id} depuis bijouterie #{src_bijouterie_id}",
#                 src_bucket=Bucket.BIJOUTERIE,
#                 src_bijouterie_id=src_bijouterie_id,
#                 dst_bucket=None,
#                 dst_bijouterie=None,
#                 achat=None, achat_ligne=None,
#                 facture=None, vente=None, vente_ligne=None,
#                 vendor=vendor,
#                 occurred_at=now,
#                 created_by=request.user,
#             )

#             result.append({
#                 "produit_id": produit.id,
#                 "nom": produit.nom,
#                 "quantite_attribuee": qty,
#                 "lot_id": lot_id,
#                 "stock_vendeur": vs.quantite,
#                 "stock_restant_bijouterie": stock.quantite,
#                 "status": status_item,
#             })

#         # 7) OK
#         return Response({
#             "message": "✅ Produits affectés avec succès.",
#             "source_bijouterie_id": src_bijouterie_id,
#             "vendeur": {
#                 "id": vendor.id,
#                 "nom_complet": vendor.user.get_full_name() if vendor.user else "",
#                 "email": vendor.user.email if vendor.user else "",
#             },
#             "lignes": result
#         }, status=201)
        


class VendorProduitAssociationAPIView(APIView):
    """
    Affecte des QUANTITÉS de lignes de produit (ProduitLine) d'une bijouterie vers un vendeur.

    Modèle utilisé :
      - Stock (par ProduitLine + bijouterie) avec quantite_allouee / quantite_disponible
      - VendorStock (par ProduitLine + vendor) avec quantite_allouee / quantite_vendue

    Logique :
      - On décrémente le **stock disponible** de la bijouterie (Stock.quantite_disponible).
      - On incrémente l'alloué du vendeur (VendorStock.quantite_allouee).
      - Une même ProduitLine peut être répartie entre plusieurs vendeurs.

    Important :
      - On utilise les helpers :
          * Stock.decremente_disponible(qte=…)
          * VendorStock.add_allocation(qte=…)
      - On ne touche pas à Stock.quantite_allouee côté bijouterie ici.
    """

    permission_classes = [IsAuthenticated]
    allowed_roles_admin_manager = {"admin", "manager"}

    @swagger_auto_schema(
        operation_summary="Affecter des lignes de produit (ProduitLine) à un vendeur",
        operation_description=(
            "Affecte des quantités de lignes d'achat (ProduitLine) d'une bijouterie vers un vendeur.\n\n"
            "- On décrémente Stock.quantite_disponible pour la bijouterie source.\n"
            "- On incrémente VendorStock.quantite_allouee pour cette même ProduitLine.\n"
            "- Si VendorStock(vendor, produit_line) existe → mise à jour, sinon → création.\n\n"
            "Une même ProduitLine peut être répartie entre plusieurs vendeurs "
            "en appelant plusieurs fois cette API avec des emails de vendeurs différents."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["email", "lignes"],
            properties={
                "email": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Email du vendeur destinataire"
                ),
                "src_bijouterie_id": openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description=(
                        "Bijouterie source. Optionnel si le vendeur est déjà rattaché à une bijouterie. "
                        "Si fourni, doit correspondre à vendor.bijouterie_id."
                    )
                ),
                "lignes": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    description="Liste des lignes de produit à affecter",
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        required=["produit_line_id", "quantite"],
                        properties={
                            "produit_line_id": openapi.Schema(
                                type=openapi.TYPE_INTEGER,
                                description="ID de la ligne d'achat (ProduitLine)"
                            ),
                            "quantite": openapi.Schema(
                                type=openapi.TYPE_INTEGER,
                                description="Quantité > 0 à affecter au vendeur pour cette ligne"
                            ),
                        }
                    )
                ),
            }
        ),
        responses={
            201: "Produits affectés au vendeur",
            400: "Requête invalide",
            403: "Accès refusé",
            404: "Ressource introuvable",
        },
        tags=["vendeur"],
    )
    @transaction.atomic
    def post(self, request):
        # 1) Permissions
        role = getattr(getattr(request.user, "user_role", None), "role", None)
        if role not in self.allowed_roles_admin_manager:
            return Response(
                {"message": "⛔ Accès refusé (admin/manager uniquement)."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 2) Entrées
        email = request.data.get("email")
        lignes_data = request.data.get("lignes", [])
        payload_src_bij = request.data.get("src_bijouterie_id")

        if not email:
            return Response({"error": "L'email du vendeur est requis."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(lignes_data, list) or not lignes_data:
            return Response(
                {"error": "La liste 'lignes' est vide ou invalide."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3) Vendeur
        try:
            vendor = Vendor.objects.select_related("user", "bijouterie").get(user__email=email)
        except Vendor.DoesNotExist:
            return Response({"error": "Vendeur introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if not vendor.verifie:
            return Response({"error": "Ce vendeur est désactivé."}, status=status.HTTP_403_FORBIDDEN)

        vendor_bij = getattr(vendor, "bijouterie_id", None)

        # 4) Détermination de la bijouterie source
        if payload_src_bij is None and vendor_bij is None:
            return Response(
                {
                    "error": (
                        "Impossible de déterminer la bijouterie source. "
                        "Renseigne 'src_bijouterie_id' ou rattache le vendeur à une bijouterie."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if payload_src_bij is not None:
            try:
                src_bijouterie_id = int(payload_src_bij)
            except Exception:
                return Response(
                    {"error": "'src_bijouterie_id' doit être un entier."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not Bijouterie.objects.filter(pk=src_bijouterie_id).exists():
                return Response(
                    {"error": f"Bijouterie #{src_bijouterie_id} introuvable."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if vendor_bij and vendor_bij != src_bijouterie_id:
                return Response(
                    {
                        "error": (
                            "Incohérence : la bijouterie fournie ne correspond pas à celle du vendeur."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            src_bijouterie_id = vendor_bij

        # 5) Validation / chargement des ProduitLine
        cleaned_items = []
        pl_ids = set()

        for idx, raw in enumerate(lignes_data, start=1):
            try:
                pl_id = int(raw.get("produit_line_id"))
                qty = int(raw.get("quantite"))
            except Exception:
                return Response(
                    {
                        "error": (
                            f"Ligne {idx}: 'produit_line_id' et 'quantite' "
                            f"doivent être des entiers."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if pl_id <= 0 or qty <= 0:
                return Response(
                    {
                        "error": (
                            f"Ligne {idx}: 'produit_line_id' et 'quantite' doivent être > 0."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            pl_ids.add(pl_id)
            cleaned_items.append({"produit_line_id": pl_id, "quantite": qty})

        produit_lines = (
            ProduitLine.objects
            .select_related("produit", "lot")
            .filter(id__in=pl_ids)
        )
        if produit_lines.count() != len(pl_ids):
            found_ids = set(produit_lines.values_list("id", flat=True))
            manquants = [pl for pl in pl_ids if pl not in found_ids]
            return Response(
                {"error": f"ProduitLine(s) introuvable(s) : {manquants}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        pl_by_id = {pl.id: pl for pl in produit_lines}

        # 6) Traitement avec verrouillage
        now = timezone.now()
        result = []

        for idx, item in enumerate(cleaned_items, start=1):
            pl_id = item["produit_line_id"]
            qty = item["quantite"]
            pl = pl_by_id[pl_id]
            produit = pl.produit
            lot = getattr(pl, "lot", None)

            # 6.a Stock bijouterie pour cette ProduitLine (quantite_disponible)
            stock = (
                Stock.objects
                .select_for_update()
                .filter(produit_line_id=pl_id, bijouterie_id=src_bijouterie_id)
                .first()
            )
            if not stock:
                return Response(
                    {
                        "error": (
                            f"Ligne {idx}: Aucun stock en bijouterie #{src_bijouterie_id} "
                            f"pour ProduitLine #{pl_id} ({produit.nom})."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # décrémente uniquement le disponible côté bijouterie
            try:
                stock.decremente_disponible(qte=qty, save=True)
            except ValidationError as e:
                return Response(
                    {
                        "error": (
                            f"Ligne {idx}: Stock disponible insuffisant en bijouterie "
                            f"#{src_bijouterie_id} pour {produit.nom}. "
                            f"Détail: {e.messages}"
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 6.b VendorStock (par ProduitLine)
            vs, created = VendorStock.objects.select_for_update().get_or_create(
                vendor=vendor,
                produit_line=pl,
                defaults={"quantite_allouee": 0, "quantite_vendue": 0},
            )

            try:
                vs.add_allocation(qte=qty, save=True)
            except ValidationError as e:
                return Response(
                    {
                        "error": (
                            f"Ligne {idx}: impossible d'allouer au vendeur. "
                            f"Détail: {e.messages}"
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            status_item = "créé" if created else "mis à jour"

            # 6.c Mouvement VENDOR_ASSIGN
            InventoryMovement.objects.create(
                produit=produit,
                movement_type=MovementType.VENDOR_ASSIGN,
                qty=qty,
                unit_cost=None,   # à remplir si tu veux suivre le coût
                lot_id=getattr(lot, "id", None),
                reason=(
                    f"Affectation ProduitLine #{pl_id} au vendeur #{vendor.id} "
                    f"depuis bijouterie #{src_bijouterie_id}"
                ),
                src_bucket=Bucket.BIJOUTERIE,
                src_bijouterie_id=src_bijouterie_id,
                dst_bucket=Bucket.VENDOR if hasattr(Bucket, "VENDOR") else None,
                dst_bijouterie=None,
                achat=None,
                achat_ligne=None,
                facture=None,
                vente=None,
                vente_ligne=None,
                vendor=vendor,
                occurred_at=now,
                created_by=request.user,
            )

            result.append({
                "produit_line_id": pl_id,
                "produit_id": produit.id,
                "produit_nom": produit.nom,
                "lot_id": getattr(lot, "id", None),
                "lot_code": getattr(lot, "numero_lot", None),
                "quantite_attribuee": qty,
                "stock_vendeur_alloue_total": vs.quantite_allouee,
                "stock_restant_disponible_bijouterie": stock.quantite_disponible,
                "status": status_item,   # "créé" ou "mis à jour"
            })

        # 7) OK
        return Response(
            {
                "message": "✅ Lignes de produit affectées avec succès au vendeur.",
                "source_bijouterie_id": src_bijouterie_id,
                "vendeur": {
                    "id": vendor.id,
                    "nom_complet": vendor.user.get_full_name() if vendor.user else "",
                    "email": vendor.user.email if vendor.user else "",
                },
                "lignes": result,
            },
            status=status.HTTP_201_CREATED,
        )


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
