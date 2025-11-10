from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

# NB: on se base sur VenteProduit.vendor et on groupe par vente__created_at
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.db.models import (Count, DecimalField, F, IntegerField, Q, Sum,
                              Value)
from django.db.models.functions import (Coalesce, TruncDay, TruncMonth,
                                        TruncWeek)
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.permissions import IsAdminOrManagerOrSelfVendor
from backend.renderers import UserRenderer
from inventory.models import Bucket, InventoryMovement, MovementType
# ⬇️ aligne le chemin du modèle de lot d’achat
from purchase.models import Lot
from sale.models import VenteProduit  # 👈 lignes de vente (contient vendor)
from stock.models import Stock, VendorStock
from store.models import Bijouterie, Produit
from store.serializers import ProduitSerializer
from vendor.models import Vendor  # 👈 ton modèle Vendor (app vendor)

from .models import Vendor
from .serializer import (VendorReadSerializer, VendorStatusInputSerializer,
                         VendorUpdateSerializer)

# Create your views here.
User = get_user_model()
allowed_all_roles = ['admin', 'manager', 'vendeur']
allowed_roles_admin_manager = ['admin', 'manager',]


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


class VendorStatsView(APIView):
    """
    GET /api/vendors/stats/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&group_by=day|week|month
    - vendor connecté : son dashboard
    - admin/manager   : ?user_id=... ou ?vendor_email=...
    - ?export=excel   : export Excel
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminOrManagerOrSelfVendor]

    @swagger_auto_schema(
        operation_id="vendorStats",
        operation_summary="Statistiques d’un vendor",
        operation_description=(
            "Un vendor voit son propre dashboard. "
            "Admin/manager peuvent cibler via ?user_id=... ou ?vendor_email=... "
            "Filtres: ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&group_by=day|week|month "
            "Export Excel: ?export=excel"
        ),
        manual_parameters=[
            openapi.Parameter("user_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, required=False),
            openapi.Parameter("vendor_email", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=False),
            openapi.Parameter("date_from", openapi.IN_QUERY, type=openapi.TYPE_STRING, format="date", required=False),
            openapi.Parameter("date_to", openapi.IN_QUERY, type=openapi.TYPE_STRING, format="date", required=False),
            openapi.Parameter("group_by", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              enum=["day","week","month"], required=False),
            openapi.Parameter("export", openapi.IN_QUERY, type=openapi.TYPE_STRING, enum=["excel"], required=False),
        ],
        tags=["Analytics"],
        responses={200: "JSON ou Excel"}
    )
    def get(self, request):
        u = request.user
        is_admin = u.is_superuser or u.groups.filter(name__in=["admin","manager"]).exists()

        # -------- 1) cible vendor --------
        target_vendor = None
        if is_admin:
            user_id = request.GET.get("user_id")
            vendor_email = request.GET.get("vendor_email")
            if user_id:
                target_vendor = Vendor.objects.select_related("user","bijouterie").filter(user_id=user_id).first()
                if not target_vendor:
                    return Response({"detail":"Vendor introuvable pour ce user_id."}, status=404)
            elif vendor_email:
                User = get_user_model()
                user = User.objects.filter(email__iexact=vendor_email.strip()).first()
                if not user:
                    return Response({"detail":"Utilisateur introuvable pour cet email."}, status=404)
                target_vendor = Vendor.objects.select_related("user","bijouterie").filter(user=user).first()
                if not target_vendor:
                    return Response({"detail":"Aucun profil Vendor lié à cet email."}, status=404)
            else:
                # pas de cible → vide
                if request.GET.get("export") == "excel":
                    return self._export_excel({}, [], "vendor_stats_empty.xlsx")
                return Response({"summary": {}, "series": []})
        else:
            target_vendor = getattr(u, "staff_vendor_profile", None)
            if not target_vendor:
                return Response({"detail":"Profil vendor non trouvé."}, status=403)

        # -------- 2) bornes & groupement --------
        today = timezone.localdate()
        date_from_str = request.GET.get("date_from")
        date_to_str   = request.GET.get("date_to")
        try:
            date_from = datetime.fromisoformat(date_from_str).date() if date_from_str else (today - timedelta(days=29))
            date_to   = datetime.fromisoformat(date_to_str).date()   if date_to_str   else today
        except ValueError:
            return Response({"detail":"Paramètres date invalides."}, status=400)
        if date_from > date_to:
            return Response({"detail":"date_from doit être ≤ date_to."}, status=400)

        group_by = (request.GET.get("group_by") or "day").lower()
        if group_by not in ("day","week","month"):
            group_by = "day"

        trunc, fmt = {
            "day":   (TruncDay("vente__created_at"),   "%Y-%m-%d"),
            "week":  (TruncWeek("vente__created_at"),  "%G-W%V"),
            "month": (TruncMonth("vente__created_at"), "%Y-%m"),
        }[group_by]

        # -------- 3) base: lignes du vendor --------
        lines = (VenteProduit.objects
                 .filter(vendor=target_vendor,
                         vente__created_at__date__gte=date_from,
                         vente__created_at__date__lte=date_to))

        # KPI globaux
        agg_revenue = lines.aggregate(rev=Sum("prix_ttc"))["rev"] or Decimal("0.00")
        agg_qty     = lines.aggregate(q=Sum("quantite"))["q"] or 0
        # nb ventes distinctes (commandes)
        orders_cnt  = (lines.values("vente_id").distinct().count()) or 0
        avg_ticket  = (agg_revenue / orders_cnt) if orders_cnt else Decimal("0.00")

        summary = {
            "vendor": {
                "id": target_vendor.id,
                "username": getattr(target_vendor.user, "username", None),
                "email": getattr(target_vendor.user, "email", None),
                "bijouterie": getattr(target_vendor.bijouterie, "nom", None),
            },
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "orders_count": orders_cnt,
            "quantity_sold": int(agg_qty),
            "revenue_total": str(agg_revenue.quantize(Decimal("0.01"))),
            "avg_ticket": str(avg_ticket.quantize(Decimal("0.01"))),
        }

        # Série temporelle
        series_qr = (lines
                     .annotate(bucket=trunc)
                     .values("bucket")
                     .annotate(
                         orders=Count("vente_id", distinct=True),
                         quantity=Sum("quantite"),
                         revenue=Sum("prix_ttc"),
                     )
                     .order_by("bucket"))

        series = []
        for row in series_qr:
            b = row["bucket"]
            label = b.strftime(fmt) if hasattr(b, "strftime") else str(b)
            series.append({
                "bucket": label,
                "orders": row["orders"] or 0,
                "quantity": int(row["quantity"] or 0),
                "revenue": str((row["revenue"] or Decimal("0.00")).quantize(Decimal("0.01"))),
            })

        # export ?
        if request.GET.get("export") == "excel":
            return self._export_excel(summary, series, f"vendor_stats_{target_vendor.id}.xlsx")

        return Response({"summary": summary, "series": series}, status=200)

    # ------ helper export ------
    def _export_excel(self, summary: dict, series: list[dict], filename: str):
        from io import BytesIO

        from openpyxl import Workbook

        wb = Workbook()
        ws1 = wb.active
        ws1.title = "Summary"
        ws1.append(["Clé", "Valeur"])
        for k, v in summary.items():
            if isinstance(v, dict):
                ws1.append([k, ""])
                for sk, sv in v.items():
                    ws1.append([f"  {sk}", sv if sv is not None else ""])
            else:
                ws1.append([k, v if v is not None else ""])

        ws2 = wb.create_sheet("Timeseries")
        ws2.append(["bucket","orders","quantity","revenue"])
        for r in series:
            ws2.append([r["bucket"], r["orders"], r["quantity"], float(r["revenue"])])

        out = BytesIO()
        wb.save(out)
        out.seek(0)
        resp = HttpResponse(
            out.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp




# Un vendeur authentifié peut appeler GET /api/vendor/produits/
# Il recevra la liste des produits associés à son stock
def _get_role(user):
    if getattr(user, "is_superuser", False):
        return "admin"
    return getattr(getattr(user, "user_role", None), "role", None)

class VendorProduitListView(APIView):
    """
    GET /api/vendor/produits/
    - Vendeur connecté : ses produits
    - Admin : ?vendor_id=<id> requis
    Retourne: nom, marque, modele, categorie, purete, poids, prix,
              quantite_allouee, quantite_disponible, quantite_stock(=allouee)
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Produits du stock vendeur (allouée + disponible)",
        manual_parameters=[
            openapi.Parameter(
                "vendor_id", openapi.IN_QUERY,
                description="ID du vendeur (requis pour admin)",
                type=openapi.TYPE_INTEGER, required=False
            )
        ],
        responses={200: openapi.Response("OK")},
        tags=["vendor"]
    )
    def get(self, request):
        user = request.user
        role = _get_role(user)

        # 1) Vendeur ciblé
        if role == "vendor":
            try:
                vendor = Vendor.objects.select_related("user", "bijouterie").get(user=user)
            except Vendor.DoesNotExist:
                return Response({"error": "Aucun vendeur associé à cet utilisateur."}, status=400)
        elif role == "admin":
            vendor_id = request.query_params.get("vendor_id")
            if not vendor_id:
                return Response({"error": "Paramètre 'vendor_id' requis pour admin."}, status=400)
            try:
                vendor = Vendor.objects.select_related("user", "bijouterie").get(pk=vendor_id)
            except Vendor.DoesNotExist:
                return Response({"error": f"Vendeur #{vendor_id} introuvable."}, status=404)
        else:
            return Response({"error": "Accès réservé aux vendeurs ou admins."}, status=403)

        if not getattr(vendor, "verifie", True):
            return Response({"error": "Ce vendeur est désactivé."}, status=403)

        # 2) Charger le stock vendeur et agréger par produit
        vstocks = (
            VendorStock.objects
            .filter(vendor=vendor)
            .select_related(
                "produit_line",
                "produit_line__produit",
                "produit_line__produit__marque",
                "produit_line__produit__modele",
                "produit_line__produit__categorie",
                "produit_line__produit__purete",
            )
        )

        # Agrégat Python : par produit → somme allouée & disponible
        by_prod = defaultdict(lambda: {"q_allouee": 0, "q_dispo": 0, "obj": None})
        for vs in vstocks:
            pl = getattr(vs, "produit_line", None)
            if not pl:
                continue
            prod = getattr(pl, "produit", None)
            if not prod:
                continue
            by_prod[prod.id]["q_allouee"] += int(getattr(vs, "quantite_allouee", 0) or 0)
            by_prod[prod.id]["q_dispo"]   += int(getattr(vs, "quantite_disponible", 0) or 0)
            by_prod[prod.id]["obj"] = prod

        # 3) Réponse plate
        rows = []
        for _, info in by_prod.items():
            p = info["obj"]
            if p is None:
                continue

            marque = getattr(getattr(p, "marque", None), "nom", "") or getattr(p, "marque_nom", "") or ""
            modele = getattr(getattr(p, "modele", None), "nom", "") or getattr(p, "modele_nom", "") or ""
            categorie = getattr(getattr(p, "categorie", None), "nom", "") or getattr(p, "categorie_nom", "") or ""
            purete = getattr(getattr(p, "purete", None), "nom", "") or getattr(p, "purete_nom", "") or ""

            poids = None
            for attr in ("poids", "poids_grammes", "poids_g"):
                if hasattr(p, attr):
                    poids = getattr(p, attr); break

            prix = None
            for attr in ("prix", "prix_vente", "prix_unitaire", "prix_par_gramme"):
                if hasattr(p, attr):
                    prix = getattr(p, attr); break

            rows.append({
                "produit_id": p.id,
                "nom": getattr(p, "nom", f"Produit #{p.id}"),
                "marque": marque,
                "modele": modele,
                "categorie": categorie,
                "purete": purete,
                "poids": poids,
                "prix": prix,
                "quantite_allouee": info["q_allouee"],
                "quantite_disponible": info["q_dispo"],
                # "quantite_stock": info["q_allouee"],  # alias (compat) quantite_stock = quantite_allouee
            })

        rows.sort(key=lambda r: (r["nom"] or "").lower())
        return Response(rows, status=200)

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
class VendorListView(generics.ListAPIView):
    """
    GET /api/vendors/
    Retourne la liste de tous les vendeurs (sans filtre).
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = VendorReadSerializer

    def get_queryset(self):
        return Vendor.objects.select_related("user", "bijouterie").order_by("-id")

    @swagger_auto_schema(
        operation_summary="Lister tous les vendeurs",
        responses={200: VendorReadSerializer(many=True)},
        tags=["vendor"]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

# ---------- DÉTAIL / LECTURE + MÀJ ----------
class VendorDetailView(APIView):
    """
    GET  /api/vendors/<int:id>/
    GET  /api/vendors/by-slug/<slug:slug>/
    PATCH/PUT idem (avec VendorUpdateSerializer)
    """
    permission_classes = [permissions.IsAuthenticated]

    def _get_obj(self, **kwargs):
        vendor_id = kwargs.get("id") or kwargs.get("pk")
        slug = kwargs.get("slug") or self.request.query_params.get("slug")

        if vendor_id:
            return get_object_or_404(
                Vendor.objects.select_related("user", "bijouterie"),
                pk=vendor_id
            )
        if slug:
            return get_object_or_404(
                Vendor.objects.select_related("user", "bijouterie"),
                user__slug=slug
            )
        # Fallback explicite
        return get_object_or_404(
            Vendor.objects.select_related("user", "bijouterie"),
            pk=self.request.query_params.get("id")
        )

    def _can_update(self, request, vendor: Vendor) -> bool:
        role = getattr(getattr(request.user, "user_role", None), "role", None)
        is_admin_or_manager = role in {"admin", "manager"}
        is_owner = vendor.user_id == request.user.id
        return bool(is_admin_or_manager or is_owner)

    # --- GET ---
    @swagger_auto_schema(
        responses={200: VendorReadSerializer},
        manual_parameters=[
            openapi.Parameter("slug", openapi.IN_QUERY, description="(optionnel si non fourni dans l'URL) user.slug", type=openapi.TYPE_STRING),
            openapi.Parameter("id", openapi.IN_QUERY, description="(optionnel si non fourni dans l'URL) vendor id", type=openapi.TYPE_INTEGER),
        ],
    )
    def get(self, request, *args, **kwargs):
        vendor = self._get_obj(**kwargs)
        return Response(VendorReadSerializer(vendor).data)

    # --- PATCH ---
    @swagger_auto_schema(
        request_body=VendorUpdateSerializer,
        responses={200: VendorReadSerializer, 403: "Access Denied"},
        tags=["vendor"],
    )
    def patch(self, request, *args, **kwargs):
        vendor = self._get_obj(**kwargs)
        if not self._can_update(request, vendor):
            return Response({"detail": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        s = VendorUpdateSerializer(vendor, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(VendorReadSerializer(vendor).data, status=200)

    # --- PUT (comportement identique, mais non-partial) ---
    @swagger_auto_schema(
        request_body=VendorUpdateSerializer,
        responses={200: VendorReadSerializer, 403: "Access Denied"},
        tags=["vendor"]
    )
    def put(self, request, *args, **kwargs):
        vendor = self._get_obj(**kwargs)
        if not self._can_update(request, vendor):
            return Response({"detail": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        s = VendorUpdateSerializer(vendor, data=request.data, partial=False)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(VendorReadSerializer(vendor).data, status=200)


class UpdateVendorStatusAPIView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]
    ALLOWED_ROLES = {"admin", "manager"}

    @swagger_auto_schema(
        operation_summary="Mise à jour du statut vendeur (verifie)",
        operation_description="Active/Désactive un vendeur via le champ booléen 'verifie'. "
                              "Autorisé: admin, manager.",
        request_body=VendorStatusInputSerializer,
        responses={200: "Statut mis à jour", 403: "Accès refusé", 404: "Vendeur introuvable"}
    )
    def patch(self, request, user_id: int):
        # 1) Rôle
        role = getattr(getattr(request.user, "user_role", None), "role", None)
        if role not in self.ALLOWED_ROLES:
            return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

        # 2) Vendeur
        vendor = Vendor.objects.select_related("user").filter(user_id=user_id).first()
        if not vendor:
            return Response({"detail": "Vendeur introuvable."}, status=status.HTTP_404_NOT_FOUND)

        # 3) (Optionnel) Si manager, vérifier même bijouterie
        # my_shop_id = getattr(getattr(request.user, "staff_manager_profile", None), "bijouterie_id", None)
        # if role == "manager" and my_shop_id and vendor.bijouterie_id != my_shop_id:
        #     return Response({"detail": "Vendeur d'une autre bijouterie."}, status=status.HTTP_403_FORBIDDEN)

        # 4) Validation du champ 'verifie'
        s = VendorStatusInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        old = bool(vendor.verifie)
        vendor.verifie = s.validated_data["verifie"]
        vendor.save(update_fields=["verifie"])

        return Response({
            "message": f"✅ Vendeur {'activé' if vendor.verifie else 'désactivé'}.",
            "vendor_id": vendor.id,
            "user_id": vendor.user_id,
            "verifie_avant": old,
            "verifie_apres": vendor.verifie,
            "email": getattr(vendor.user, "email", None),
        }, status=status.HTTP_200_OK)
    

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



class VendorProduitAssociationAPIView(APIView):
    """
    Affecte des produits d'une **bijouterie source** vers un **vendeur** :
      - Détermination automatique de la bijouterie via l'email du vendeur si `src_bijouterie_id` n'est pas fourni.
      - Décrément du stock *de la bijouterie source*.
      - Mise à jour du stock vendeur (VendorProduit).
      - Journalisation `VENDOR_ASSIGN` (traçabilité possible via lot_id).
      Explication:
      Voici ce que signifie le champ status renvoyé pour chaque ligne de produit :

    "créé"
        → C’est la première fois que ce vendeur reçoit ce produit.
    "mis à jour"
        → Le vendeur avait déjà ce produit dans son stock.
        L’API incrémente simplement la quantité existante (quantite = quantite + attribuée) sur la même ligne VendorProduit. 
        On ne crée pas de nouvelle ligne ; on met à jour la ligne existante.
    
    Quelques points à bien retenir :

        Le statut est par paire (vendeur, produit), pas par lot_id.
        Même si tu fournis un lot_id différent, si le vendeur possède déjà ce produit, ce sera "mis à jour" 
        (la traçabilité du lot est dans le mouvement InventoryMovement, pas dans VendorProduit).
    
    En résumé :
        "créé" = nouvelle ligne VendorProduit(vendor, produit) créée.
        "mis à jour" = ligne déjà existante, quantité augmentée (ou ajustée).
    
    Exemple de payload pour “réduction”
        {
        "email": "vendeur@exemple.com",
        "produits": [
            { "produit_id": 12, "set_stock_vendeur": 5 }
        ]
        }
    Explication du payload:
    S’il en avait 9, on fait –4 côté vendeur et +4 en bijouterie, 
    et on journalise un ADJUSTMENT (dst=BIJOUTERIE) pour la traçabilité retour.

    Remarque lot : le lot_id que tu envoies ici traçera cette opération (nouvelle affectation). 
    Ça ne remplace pas le lot_id d’un mouvement passé (on ne réécrit pas l’historique).
        
    """
    permission_classes = [IsAuthenticated]
    allowed_roles_admin_manager = {"admin", "manager"}

    @swagger_auto_schema(
        operation_summary="Affecter des produits à un vendeur (déduction bijouterie source automatique)",
        operation_description=(
            "- Si `src_bijouterie_id` est omis, on le déduit de `vendor.bijouterie_id` (via l'email).\n"
            "- Si `src_bijouterie_id` est fourni ET que le vendeur a une bijouterie, ils doivent correspondre.\n"
            "- `lot_id` est **optionnel** (traçabilité). On **ne décrémente pas** le lot d’achat ici.\n"
            "- Le stock décrémenté est celui de la **bijouterie source**, pas le réservé."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["email", "produits"],
            properties={
                "email": openapi.Schema(type=openapi.TYPE_STRING, description="Email du vendeur"),
                "src_bijouterie_id": openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description="Bijouterie source (optionnel si vend. rattaché)"
                ),
                "produits": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        required=["produit_id", "quantite"],
                        properties={
                            "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                            "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, description="> 0"),
                            "lot_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="Optionnel (traçabilité)"),
                        }
                    )
                )
            }
        ),
        responses={
            201: "Produits affectés",
            400: "Requête invalide",
            403: "Accès refusé",
            404: "Ressource introuvable",
            409: "Conflit de stock",
        },
        tags=["Vendeurs / Affectations"],
    )
    @transaction.atomic
    def post(self, request):
        # 1) Permissions
        role = getattr(getattr(request.user, "user_role", None), "role", None)
        if role not in self.allowed_roles_admin_manager:
            return Response({"message": "⛔ Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

        # 2) Entrées de base
        email = request.data.get("email")
        produits_data = request.data.get("produits", [])
        payload_src_bij = request.data.get("src_bijouterie_id")

        if not email:
            return Response({"error": "L'email du vendeur est requis."}, status=400)
        if not isinstance(produits_data, list) or not produits_data:
            return Response({"error": "La liste des produits est vide ou invalide."}, status=400)

        # 3) Vendeur + bijouterie source (déduction si nécessaire)
        try:
            vendor = Vendor.objects.select_related("user", "bijouterie").get(user__email=email)
        except Vendor.DoesNotExist:
            return Response({"error": "Vendeur introuvable."}, status=404)
        if not vendor.verifie:
            return Response({"error": "Ce vendeur est désactivé."}, status=403)

        vendor_bij = getattr(vendor, "bijouterie_id", None)
        if payload_src_bij is None and vendor_bij is None:
            return Response(
                {"error": "Impossible de déterminer la bijouterie source. "
                          "Renseigne 'src_bijouterie_id' ou rattache le vendeur à une bijouterie."},
                status=400
            )

        if payload_src_bij is not None:
            try:
                src_bijouterie_id = int(payload_src_bij)
            except Exception:
                return Response({"error": "'src_bijouterie_id' doit être un entier."}, status=400)

            if not Bijouterie.objects.filter(pk=src_bijouterie_id).exists():
                return Response({"error": f"Bijouterie #{src_bijouterie_id} introuvable."}, status=404)

            if vendor_bij and vendor_bij != src_bijouterie_id:
                return Response(
                    {"error": "Incohérence : la bijouterie fournie ne correspond pas à celle du vendeur."},
                    status=400
                )
        else:
            src_bijouterie_id = vendor_bij

        # 4) Validation/chargement des items (on ne regroupe pas pour préserver lot_id par ligne)
        cleaned_items, produit_ids, lot_ids = [], set(), set()
        for idx, raw in enumerate(produits_data, start=1):
            try:
                pid = int(raw.get("produit_id"))
                qty = int(raw.get("quantite"))
            except Exception:
                return Response(
                    {"error": f"Item {idx}: 'produit_id' et 'quantite' doivent être des entiers."}, status=400
                )
            if pid <= 0 or qty <= 0:
                return Response({"error": f"Item {idx}: 'produit_id' et 'quantite' doivent être > 0."}, status=400)

            lot_id = raw.get("lot_id")
            if lot_id is not None:
                try:
                    lot_id = int(lot_id)
                    if lot_id <= 0:
                        return Response({"error": f"Item {idx}: 'lot_id' doit être > 0."}, status=400)
                    lot_ids.add(lot_id)
                except Exception:
                    return Response({"error": f"Item {idx}: 'lot_id' doit être un entier."}, status=400)

            produit_ids.add(pid)
            cleaned_items.append({"produit_id": pid, "quantite": qty, "lot_id": lot_id})

        # 5) Existence produits
        produits = Produit.objects.filter(id__in=produit_ids)
        if produits.count() != len(produit_ids):
            ids_ok = set(produits.values_list("id", flat=True))
            manquants = [p for p in produit_ids if p not in ids_ok]
            return Response({"error": f"Produit(s) introuvable(s) : {manquants}"}, status=404)
        produits_by_id = {p.id: p for p in produits}

        # 6) Traitement items
        result = []
        now = timezone.now()

        for idx, item in enumerate(cleaned_items, start=1):
            pid = item["produit_id"]
            qty = item["quantite"]
            lot_id = item["lot_id"]
            produit = produits_by_id[pid]

            # 6.a Vérrouillage + décrément du stock de la bijouterie source
            stock = (Stock.objects
                     .select_for_update()
                     .filter(produit_id=pid, bijouterie_id=src_bijouterie_id)
                     .first())
            if not stock:
                return Response(
                    {"error": f"Aucun stock en bijouterie #{src_bijouterie_id} pour le produit {produit.nom}."}, status=400
                )
            if stock.quantite < qty:
                return Response(
                    {"error": f"Stock insuffisant en bijouterie #{src_bijouterie_id} pour {produit.nom}. "
                              f"Stock actuel : {stock.quantite}, demandé : {qty}"},
                    status=400
                )
            updated = (Stock.objects
                       .filter(pk=stock.pk, quantite__gte=qty)
                       .update(quantite=F("quantite") - qty))
            if not updated:
                return Response({"error": "Conflit de stock détecté. Réessayez."}, status=409)
            stock.refresh_from_db(fields=["quantite"])

            # 6.b Incrément du stock vendeur (VendorProduit)
            vs = (VendorStock.objects
                  .select_for_update()
                  .filter(vendor=vendor, produit_id=pid)
                  .first())
            if vs:
                VendorStock.objects.filter(pk=vs.pk).update(quantite=F("quantite") + qty)
                vs.refresh_from_db(fields=["quantite"])
                status_item = "mis à jour"
            else:
                vs = VendorStock.objects.create(vendor=vendor, produit_id=pid, quantite=qty)
                status_item = "créé"

            # 6.c Mouvement VENDOR_ASSIGN (traçabilité + origine bijouterie)
            InventoryMovement.objects.create(
                produit=produit,
                movement_type=MovementType.VENDOR_ASSIGN,
                qty=qty,
                unit_cost=None,              # pas de coût calculé ici
                lot_id=lot_id,               # traçabilité (optionnel)
                reason=f"Affectation au vendeur #{vendor.id} depuis bijouterie #{src_bijouterie_id}",
                src_bucket=Bucket.BIJOUTERIE,
                src_bijouterie_id=src_bijouterie_id,
                dst_bucket=None,
                dst_bijouterie=None,
                achat=None, achat_ligne=None,
                facture=None, vente=None, vente_ligne=None,
                vendor=vendor,
                occurred_at=now,
                created_by=request.user,
            )

            result.append({
                "produit_id": produit.id,
                "nom": produit.nom,
                "quantite_attribuee": qty,
                "lot_id": lot_id,
                "stock_vendeur": vs.quantite,
                "stock_restant_bijouterie": stock.quantite,
                "status": status_item,
            })

        # 7) OK
        return Response({
            "message": "✅ Produits affectés avec succès.",
            "source_bijouterie_id": src_bijouterie_id,
            "vendeur": {
                "id": vendor.id,
                "nom_complet": vendor.user.get_full_name() if vendor.user else "",
                "email": vendor.user.email if vendor.user else "",
            },
            "lignes": result
        }, status=201)
        


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
