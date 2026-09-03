import datetime
from collections import defaultdict
from datetime import date
from datetime import date as ddate
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO
from textwrap import dedent
from typing import Optional

from dateutil.relativedelta import relativedelta
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

from backend.permissions import IsAdminOrManager  # ton permission
from backend.permissions import ROLE_VENDOR
from backend.query_scopes import scope_bijouterie_q
from backend.renderers import UserRenderer
from backend.roles import ROLE_ADMIN, ROLE_MANAGER, get_role_name
from inventory.models import Bucket, InventoryMovement, MovementType
# ⬇️ aligne le chemin du modèle de lot d’achat
from purchase.models import Lot, ProduitLine
from sale.models import VenteProduit  # 👈 lignes de vente (contient vendor)
from sale.models import Facture
from staff.models import Manager
from stock.models import VendorStock  # adapte app
from stock.models import Stock
from store.models import Bijouterie, Marque, Produit
from store.serializers import ProduitSerializer
from userauths.models import Role
from vendor.models import Vendor  # 👈 ton modèle Vendor (app vendor)
from vendor.serializer import VendorStockListSerializer  # adapte serializer

from .models import Vendor
from .serializer import (CreateVendorSerializer, VendorDashboardKpiSerializer,
                         VendorDashboardSeriesSerializer, VendorListSerializer,
                         VendorStockListSerializer,
                         VendorStockSummaryByProduitSerializer,
                         VendorStockSummaryByVendorProduitSerializer,
                         VendorStockSummaryByVendorSerializer,
                         VendorUpdateSerializer)

ZERO = Decimal("0.00")

# Create your views here.
User = get_user_model()
allowed_all_roles = ['admin', 'manager', 'vendeur']
allowed_roles_admin_manager = ['admin', 'manager',]


class VendorStockView(APIView):
    """
    Stock réel vendeur :
    stock_reel = quantite_allouee - quantite_vendue

    - vendor  : voit son propre stock
    - admin   : fournit vendor_email
    - manager : fournit vendor_email, limité à ses bijouteries
    """
    permission_classes = [IsAuthenticated]
    http_method_names = ["get"]

    @swagger_auto_schema(
        operation_summary="Stock réel vendeur",
        operation_description=(
            "Vendor connecté : aucun paramètre requis.\n"
            "Admin/Manager : fournir `vendor_email`.\n\n"
            "Formule : stock_reel = quantite_allouee - quantite_vendue."
        ),
        manual_parameters=[
            openapi.Parameter(
                "vendor_email",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
                description="Obligatoire pour admin/manager.",
            ),
        ],
        tags=["vendor"],
        responses={200: openapi.Response("Liste du stock réel vendeur")},
    )
    def get(self, request):
        role = (get_role_name(request.user) or "").lower()
        vendor_email = (request.query_params.get("vendor_email") or "").strip()

        # 1) Résoudre vendeur cible
        if role == ROLE_VENDOR:
            vendor = getattr(request.user, "staff_vendor_profile", None)
            if not vendor:
                return Response(
                    {"detail": "Profil vendeur introuvable."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        elif role in {ROLE_ADMIN, ROLE_MANAGER}:
            if not vendor_email:
                return Response(
                    {"detail": "vendor_email est obligatoire pour admin/manager."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            vendor = get_object_or_404(
                Vendor.objects.select_related("user", "bijouterie"),
                user__email__iexact=vendor_email,
            )

            # Manager M2M : ne peut voir que ses bijouteries
            if role == ROLE_MANAGER:
                manager_profile = getattr(request.user, "staff_manager_profile", None)

                if not manager_profile:
                    return Response(
                        {"detail": "Profil manager introuvable."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if not manager_profile.bijouteries.filter(id=vendor.bijouterie_id).exists():
                    return Response(
                        {"detail": "Ce vendeur n'appartient pas à votre périmètre."},
                        status=status.HTTP_403_FORBIDDEN,
                    )

        else:
            return Response(
                {"detail": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 2) Stock vendeur
        qs = (
            VendorStock.objects
            .select_related(
                "produit_line",
                "produit_line__produit",
                "produit_line__lot",
            )
            .filter(vendor=vendor)
        )

        results = []
        total_allouee = 0
        total_vendue = 0
        total_stock_reel = 0

        for stock in qs:
            produit_line = stock.produit_line
            produit = getattr(produit_line, "produit", None)
            lot = getattr(produit_line, "lot", None)

            quantite_allouee = int(stock.quantite_allouee or 0)
            quantite_vendue = int(stock.quantite_vendue or 0)
            stock_reel = quantite_allouee - quantite_vendue

            if stock_reel <= 0:
                continue

            total_allouee += quantite_allouee
            total_vendue += quantite_vendue
            total_stock_reel += stock_reel

            results.append({
                "vendor_stock_id": stock.id,
                "produit_line_id": produit_line.id if produit_line else None,

                "produit_id": produit.id if produit else None,
                "produit_nom": produit.nom if produit else None,
                "sku": getattr(produit, "sku", None) if produit else None,

                "lot_id": lot.id if lot else None,
                "lot": getattr(lot, "numero_lot", None) or getattr(lot, "lot_code", None),

                "quantite_allouee": quantite_allouee,
                "quantite_vendue": quantite_vendue,
                "stock_reel": stock_reel,
            })

        return Response(
            {
                "vendor": {
                    "id": vendor.id,
                    "email": getattr(getattr(vendor, "user", None), "email", None),
                    "bijouterie_id": vendor.bijouterie_id,
                    "bijouterie_nom": getattr(getattr(vendor, "bijouterie", None), "nom", None),
                },
                "totaux": {
                    "quantite_allouee": total_allouee,
                    "quantite_vendue": total_vendue,
                    "stock_reel": total_stock_reel,
                },
                "count": len(results),
                "results": results,
            },
            status=status.HTTP_200_OK,
        )


# class VendorDashboardView(APIView):
#     permission_classes = [IsAuthenticated]
#     http_method_names = ["get"]

#     @swagger_auto_schema(
#         operation_summary="Dashboard vendeur connecté",
#         operation_description=(
#             "Retourne le tableau de bord du vendeur connecté :\n"
#             "- ventes semaine\n"
#             "- ventes mois\n"
#             "- ventes année\n"
#             "- top produits\n"
#             "- stock restant\n"
#             "- graphique journalier sur 30 jours\n"
#         ),
#         tags=["vendor"],
#         responses={200: openapi.Response("OK")},
#     )
#     def get(self, request):
#         vendor = getattr(request.user, "staff_vendor_profile", None)
#         if not vendor:
#             return Response(
#                 {"detail": "Profil vendeur introuvable."},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         now = timezone.now()
#         start_week = now - timedelta(days=7)
#         start_month = now - timedelta(days=30)
#         start_year = now - timedelta(days=365)

#         # -----------------------------
#         # 1) ventes semaine
#         # -----------------------------
#         ventes_semaine_qs = (
#             VenteProduit.objects
#             .filter(vendor=vendor, vente__created_at__gte=start_week)
#             .aggregate(
#                 total_quantite=Sum("quantite"),
#                 total_ttc=Sum("montant_total")
#             )
#         )

#         ventes_semaine = {
#             "total_quantite": int(ventes_semaine_qs["total_quantite"] or 0),
#             "total_ttc": float(ventes_semaine_qs["total_ttc"] or 0),
#         }

#         # -----------------------------
#         # 2) ventes mois
#         # -----------------------------
#         ventes_mois_qs = (
#             VenteProduit.objects
#             .filter(vendor=vendor, vente__created_at__gte=start_month)
#             .aggregate(
#                 total_quantite=Sum("quantite"),
#                 total_ttc=Sum("montant_total")
#             )
#         )

#         ventes_mois = {
#             "total_quantite": int(ventes_mois_qs["total_quantite"] or 0),
#             "total_ttc": float(ventes_mois_qs["total_ttc"] or 0),
#         }

#         # -----------------------------
#         # 3) ventes année
#         # -----------------------------
#         ventes_annee_qs = (
#             VenteProduit.objects
#             .filter(vendor=vendor, vente__created_at__gte=start_year)
#             .aggregate(
#                 total_quantite=Sum("quantite"),
#                 total_ttc=Sum("montant_total")
#             )
#         )

#         ventes_annee = {
#             "total_quantite": int(ventes_annee_qs["total_quantite"] or 0),
#             "total_ttc": float(ventes_annee_qs["total_ttc"] or 0),
#         }

#         # -----------------------------
#         # 4) top produits
#         # -----------------------------
#         top_produits_qs = (
#             VenteProduit.objects
#             .filter(vendor=vendor)
#             .values("produit__id", "produit__nom", "produit__sku")
#             .annotate(
#                 total_quantite=Sum("quantite"),
#                 total_ttc=Sum("montant_total")
#             )
#             .order_by("-total_quantite")[:10]
#         )

#         top_produits = []
#         for item in top_produits_qs:
#             top_produits.append({
#                 "produit_id": item["produit__id"],
#                 "nom": item["produit__nom"],
#                 "sku": item["produit__sku"],
#                 "total_quantite": int(item["total_quantite"] or 0),
#                 "total_ttc": float(item["total_ttc"] or 0),
#             })

#         # -----------------------------
#         # 5) stock restant
#         # -----------------------------
#         stock_qs = (
#             VendorStock.objects
#             .select_related("produit_line", "produit_line__produit")
#             .filter(vendor=vendor)
#         )

#         stock_restant = []
#         for stock in stock_qs:
#             produit = getattr(stock.produit_line, "produit", None)
#             restant = int(stock.quantite_allouee or 0) - int(stock.quantite_vendue or 0)

#             stock_restant.append({
#                 "produit_id": produit.id if produit else None,
#                 "produit_nom": produit.nom if produit else None,
#                 "sku": getattr(produit, "sku", None) if produit else None,
#                 "quantite_allouee": int(stock.quantite_allouee or 0),
#                 "quantite_vendue": int(stock.quantite_vendue or 0),
#                 "restant": restant,
#             })

#         # -----------------------------
#         # 6) graphique par jour (30 jours)
#         # ⚠️ sans TruncDay pour éviter le bug MySQL timezone
#         # -----------------------------
#         graphique_rows = (
#             VenteProduit.objects
#             .filter(vendor=vendor, vente__created_at__gte=start_month)
#             .values("vente__created_at", "quantite", "montant_total")
#             .order_by("vente__created_at")
#         )

#         by_day = defaultdict(lambda: {
#             "total_quantite": 0,
#             "total_ttc": 0.0,
#         })

#         for row in graphique_rows:
#             dt = row["vente__created_at"]
#             if not dt:
#                 continue

#             local_day = timezone.localtime(dt).date().isoformat()
#             by_day[local_day]["total_quantite"] += int(row["quantite"] or 0)
#             by_day[local_day]["total_ttc"] += float(row["montant_total"] or 0)

#         graphique = []
#         for day in sorted(by_day.keys()):
#             graphique.append({
#                 "jour": day,
#                 "total_quantite": by_day[day]["total_quantite"],
#                 "total_ttc": by_day[day]["total_ttc"],
#             })

#         return Response(
#             {
#                 "vendor": {
#                     "id": vendor.id,
#                     "email": getattr(getattr(vendor, "user", None), "email", None),
#                     "bijouterie": getattr(getattr(vendor, "bijouterie", None), "nom", None),
#                 },
#                 "ventes_semaine": ventes_semaine,
#                 "ventes_mois": ventes_mois,
#                 "ventes_annee": ventes_annee,
#                 "top_produits": top_produits,
#                 "stock_restant": stock_restant,
#                 "graphique": graphique,
#             },
#             status=status.HTTP_200_OK
#         )


# class VendorDashboardView(APIView):
#     """
#     Dashboard du vendeur connecté.

#     Retourne :
#     - CA semaine courante
#     - CA mois courant
#     - CA année courante
#     - top produits vendus
#     - stock vendeur restant
#     - graphique des 30 derniers jours
#     - historique annuel
#     """

#     permission_classes = [IsAuthenticated]
#     http_method_names = ["get"]

#     @swagger_auto_schema(
#         operation_summary="Dashboard vendeur connecté",
#         operation_description=(
#             "Retourne le tableau de bord du vendeur connecté.\n\n"
#             "- ventes semaine courante\n"
#             "- ventes mois courant\n"
#             "- ventes année courante\n"
#             "- top produits réellement vendus\n"
#             "- stock vendeur restant\n"
#             "- graphique journalier des 30 derniers jours\n"
#             "- historique annuel automatique\n"
#         ),
#         tags=["vendor"],
#         responses={
#             200: openapi.Response("Dashboard vendeur"),
#             400: openapi.Response("Profil vendeur introuvable"),
#             403: openapi.Response("Profil vendeur désactivé"),
#         },
#     )
#     def get(self, request):

#         # ============================================================
#         # 1. Vendeur connecté
#         # ============================================================

#         vendor = getattr(
#             request.user,
#             "staff_vendor_profile",
#             None,
#         )

#         if not vendor:
#             return Response(
#                 {
#                     "detail": "Profil vendeur introuvable."
#                 },
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         if not getattr(vendor, "verifie", False):
#             return Response(
#                 {
#                     "detail": "Profil vendeur désactivé."
#                 },
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         # ============================================================
#         # 2. Dates
#         # ============================================================

#         now = timezone.now()
#         today = timezone.localdate()

#         # début semaine courante : lundi
#         start_week_date = (
#             today - timedelta(days=today.weekday())
#         )

#         # début mois courant
#         start_month_date = today.replace(
#             day=1
#         )

#         # début année courante
#         start_year_date = today.replace(
#             month=1,
#             day=1,
#         )

#         start_week = timezone.make_aware(
#             datetime.combine(
#                 start_week_date,
#                 datetime.min.time(),
#             )
#         )

#         start_month = timezone.make_aware(
#             datetime.combine(
#                 start_month_date,
#                 datetime.min.time(),
#             )
#         )

#         start_year = timezone.make_aware(
#             datetime.combine(
#                 start_year_date,
#                 datetime.min.time(),
#             )
#         )

#         # uniquement pour le graphique
#         start_30_days = now - timedelta(days=29)

#         # ============================================================
#         # QuerySet de base du vendeur
#         # ============================================================

#         ventes_vendor = (
#             VenteProduit.objects
#             .filter(
#                 vendor=vendor,
#             )
#         )

#         # ============================================================
#         # 3. Ventes semaine courante
#         # ============================================================

#         ventes_semaine_qs = (
#             ventes_vendor
#             .filter(
#                 vente__created_at__gte=start_week,
#             )
#             .aggregate(
#                 total_quantite=Sum("quantite"),
#                 total_ttc=Sum("total_ligne"),
#             )
#         )

#         ventes_semaine = {
#             "total_quantite": int(
#                 ventes_semaine_qs["total_quantite"] or 0
#             ),
#             "total_ttc": float(
#                 ventes_semaine_qs["total_ttc"] or Decimal("0.00")
#             ),
#         }

#         # ============================================================
#         # 4. Ventes mois courant
#         # ============================================================

#         ventes_mois_qs = (
#             ventes_vendor
#             .filter(
#                 vente__created_at__gte=start_month,
#             )
#             .aggregate(
#                 total_quantite=Sum("quantite"),
#                 total_ttc=Sum("total_ligne"),
#             )
#         )

#         ventes_mois = {
#             "total_quantite": int(
#                 ventes_mois_qs["total_quantite"] or 0
#             ),
#             "total_ttc": float(
#                 ventes_mois_qs["total_ttc"] or Decimal("0.00")
#             ),
#         }

#         # ============================================================
#         # 5. Ventes année courante
#         # ============================================================

#         ventes_annee_qs = (
#             ventes_vendor
#             .filter(
#                 vente__created_at__gte=start_year,
#             )
#             .aggregate(
#                 total_quantite=Sum("quantite"),
#                 total_ttc=Sum("total_ligne"),
#             )
#         )

#         ventes_annee = {
#             "total_quantite": int(
#                 ventes_annee_qs["total_quantite"] or 0
#             ),
#             "total_ttc": float(
#                 ventes_annee_qs["total_ttc"] or Decimal("0.00")
#             ),
#         }

#         # ============================================================
#         # 6. Top produits vendus
#         # ============================================================

#         top_produits_qs = (
#             ventes_vendor
#             .values(
#                 "produit__id",
#                 "produit__nom",
#                 "produit__sku",
#             )
#             .annotate(
#                 total_quantite=Sum("quantite"),
#                 total_ttc=Sum("total_ligne"),
#             )
#             .order_by(
#                 "-total_quantite"
#             )[:10]
#         )

#         top_produits = [
#             {
#                 "produit_id": item["produit__id"],
#                 "nom": item["produit__nom"],
#                 "sku": item["produit__sku"],
#                 "total_quantite": int(
#                     item["total_quantite"] or 0
#                 ),
#                 "total_ttc": float(
#                     item["total_ttc"] or Decimal("0.00")
#                 ),
#             }
#             for item in top_produits_qs
#         ]

#         # ============================================================
#         # 7. Stock restant vendeur
#         # ============================================================

#         stock_qs = (
#             VendorStock.objects
#             .select_related(
#                 "produit_line",
#                 "produit_line__produit",
#                 "produit_line__lot",
#             )
#             .filter(
#                 vendor=vendor,
#             )
#         )

#         stock_restant = []

#         total_alloue = 0
#         total_vendu = 0
#         total_restant = 0

#         for stock in stock_qs:

#             produit_line = stock.produit_line
#             produit = getattr(
#                 produit_line,
#                 "produit",
#                 None,
#             )

#             lot = getattr(
#                 produit_line,
#                 "lot",
#                 None,
#             )

#             quantite_allouee = int(
#                 stock.quantite_allouee or 0
#             )

#             quantite_vendue = int(
#                 stock.quantite_vendue or 0
#             )

#             restant = (
#                 quantite_allouee
#                 - quantite_vendue
#             )

#             # On ne retourne pas les stocks épuisés
#             if restant <= 0:
#                 continue

#             total_alloue += quantite_allouee
#             total_vendu += quantite_vendue
#             total_restant += restant

#             stock_restant.append(
#                 {
#                     "vendor_stock_id": stock.id,

#                     "produit_line_id": (
#                         produit_line.id
#                         if produit_line
#                         else None
#                     ),

#                     "produit_id": (
#                         produit.id
#                         if produit
#                         else None
#                     ),

#                     "produit_nom": (
#                         produit.nom
#                         if produit
#                         else None
#                     ),

#                     "sku": (
#                         getattr(
#                             produit,
#                             "sku",
#                             None,
#                         )
#                         if produit
#                         else None
#                     ),

#                     "lot_id": (
#                         lot.id
#                         if lot
#                         else None
#                     ),

#                     "numero_lot": (
#                         getattr(
#                             lot,
#                             "numero_lot",
#                             None,
#                         )
#                         if lot
#                         else None
#                     ),

#                     "quantite_allouee": (
#                         quantite_allouee
#                     ),

#                     "quantite_vendue": (
#                         quantite_vendue
#                     ),

#                     "restant": restant,
#                 }
#             )

#         stock_totaux = {
#             "quantite_allouee": total_alloue,
#             "quantite_vendue": total_vendu,
#             "quantite_restante": total_restant,
#         }

#         # ============================================================
#         # 8. Graphique 30 derniers jours
#         # ============================================================

#         graphique_rows = (
#             ventes_vendor
#             .filter(
#                 vente__created_at__gte=start_30_days,
#             )
#             .values(
#                 "vente__created_at",
#                 "quantite",
#                 "total_ligne",
#             )
#             .order_by(
#                 "vente__created_at"
#             )
#         )

#         by_day = defaultdict(
#             lambda: {
#                 "total_quantite": 0,
#                 "total_ttc": Decimal("0.00"),
#             }
#         )

#         for row in graphique_rows:

#             dt = row["vente__created_at"]

#             if not dt:
#                 continue

#             local_day = (
#                 timezone.localtime(dt)
#                 .date()
#                 .isoformat()
#             )

#             by_day[local_day]["total_quantite"] += int(
#                 row["quantite"] or 0
#             )

#             by_day[local_day]["total_ttc"] += (
#                 row["total_ligne"]
#                 or Decimal("0.00")
#             )

#         # ------------------------------------------------------------
#         # Générer aussi les jours sans vente
#         # ------------------------------------------------------------

#         graphique = []

#         start_graph_date = (
#             timezone.localdate()
#             - timedelta(days=29)
#         )

#         for offset in range(30):

#             current_date = (
#                 start_graph_date
#                 + timedelta(days=offset)
#             )

#             day_key = current_date.isoformat()

#             data = by_day.get(
#                 day_key,
#                 {
#                     "total_quantite": 0,
#                     "total_ttc": Decimal("0.00"),
#                 },
#             )

#             graphique.append(
#                 {
#                     "jour": day_key,
#                     "total_quantite": int(
#                         data["total_quantite"]
#                     ),
#                     "total_ttc": float(
#                         data["total_ttc"]
#                     ),
#                 }
#             )

#         # ============================================================
#         # 9. Historique annuel
#         # ============================================================

#         historique_qs = (
#             ventes_vendor
#             .values(
#                 "vente__created_at__year"
#             )
#             .annotate(
#                 total_quantite=Sum(
#                     "quantite"
#                 ),
#                 total_ttc=Sum(
#                     "total_ligne"
#                 ),
#             )
#             .order_by(
#                 "-vente__created_at__year"
#             )
#         )

#         historique = []

#         for item in historique_qs:

#             annee = item[
#                 "vente__created_at__year"
#             ]

#             if not annee:
#                 continue

#             historique.append(
#                 {
#                     "annee": annee,
#                     "total_quantite": int(
#                         item["total_quantite"] or 0
#                     ),
#                     "total_ttc": float(
#                         item["total_ttc"]
#                         or Decimal("0.00")
#                     ),
#                 }
#             )

#         # ============================================================
#         # 10. Response
#         # ============================================================

#         return Response(
#             {
#                 "vendor": {
#                     "id": vendor.id,

#                     "email": getattr(
#                         getattr(
#                             vendor,
#                             "user",
#                             None,
#                         ),
#                         "email",
#                         None,
#                     ),

#                     "bijouterie_id": (
#                         vendor.bijouterie_id
#                     ),

#                     "bijouterie": getattr(
#                         getattr(
#                             vendor,
#                             "bijouterie",
#                             None,
#                         ),
#                         "nom",
#                         None,
#                     ),
#                 },

#                 "ventes_semaine": ventes_semaine,

#                 "ventes_mois": ventes_mois,

#                 "ventes_annee": ventes_annee,

#                 "top_produits": top_produits,

#                 "stock": {
#                     "totaux": stock_totaux,
#                     "count": len(stock_restant),
#                     "results": stock_restant,
#                 },

#                 "graphique_30_jours": graphique,

#                 "historique": historique,
#             },
#             status=status.HTTP_200_OK,
#         )


class VendorDashboardView(APIView):
    """
    Dashboard du vendeur connecté.

    Règles :
    - vendeur connecté uniquement ;
    - profil vendeur vérifié obligatoire ;
    - seules les factures PAYÉES alimentent le chiffre d'affaires ;
    - dashboard principal = année en cours ;
    - graphique = 30 derniers jours ;
    - top produits = année en cours ;
    - stock = stock vendeur réellement disponible ;
    - historique = agrégation annuelle des ventes payées.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "options"]

    @swagger_auto_schema(
        operation_summary="Dashboard vendeur connecté",
        operation_description=(
            "Retourne le tableau de bord du vendeur connecté.\n\n"
            "### Données retournées\n"
            "- CA semaine courante\n"
            "- CA mois courant\n"
            "- CA année courante\n"
            "- nombre de ventes année courante\n"
            "- quantité d'articles vendus année courante\n"
            "- top produits réellement vendus\n"
            "- stock vendeur restant\n"
            "- graphique journalier des 30 derniers jours\n"
            "- historique annuel\n\n"
            "### Règles\n"
            "- Seules les factures avec `status=paye` sont comptabilisées.\n"
            "- Les proformas non payées ne sont pas incluses dans le CA.\n"
            "- Le dashboard principal concerne l'année en cours."
        ),
        tags=["vendor"],
        responses={
            200: openapi.Response(
                description="Dashboard vendeur",
                examples={
                    "application/json": {
                        "vendor": {
                            "id": 4,
                            "email": "vendeur@rio-gold.com",
                            "bijouterie_id": 1,
                            "bijouterie": "Rio Gold Dakar",
                        },
                        "resume": {
                            "ca_semaine": "1250000.00",
                            "ca_mois": "4850000.00",
                            "ca_annee": "42350000.00",
                            "nombre_ventes_annee": 68,
                            "quantite_vendue_annee": 91,
                        },
                        "ventes_semaine": {
                            "nombre_ventes": 8,
                            "total_quantite": 12,
                            "total_ttc": "1250000.00",
                        },
                        "ventes_mois": {
                            "nombre_ventes": 24,
                            "total_quantite": 32,
                            "total_ttc": "4850000.00",
                        },
                        "ventes_annee": {
                            "nombre_ventes": 68,
                            "total_quantite": 91,
                            "total_ttc": "42350000.00",
                        },
                        "top_produits": [],
                        "stock": {
                            "totaux": {
                                "quantite_allouee": 180,
                                "quantite_vendue": 54,
                                "quantite_restante": 126,
                            },
                            "count": 10,
                            "results": [],
                        },
                        "graphique_30_jours": [],
                        "historique": [],
                    }
                },
            ),
            400: openapi.Response(
                description="Profil vendeur introuvable."
            ),
            403: openapi.Response(
                description="Profil vendeur désactivé."
            ),
        },
    )
    def get(self, request):

        # ============================================================
        # 1. VENDEUR CONNECTÉ
        # ============================================================

        vendor = getattr(
            request.user,
            "staff_vendor_profile",
            None,
        )

        if not vendor:
            return Response(
                {
                    "detail": "Profil vendeur introuvable.",
                    "code": "VENDOR_PROFILE_NOT_FOUND",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not getattr(vendor, "verifie", False):
            return Response(
                {
                    "detail": "Profil vendeur désactivé.",
                    "code": "VENDOR_PROFILE_DISABLED",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if not getattr(vendor, "bijouterie_id", None):
            return Response(
                {
                    "detail": (
                        "Le vendeur n'est rattaché à aucune bijouterie."
                    ),
                    "code": "VENDOR_WITHOUT_BIJOUTERIE",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ============================================================
        # 2. DATES
        # ============================================================

        now = timezone.now()
        today = timezone.localdate()

        # Lundi de la semaine courante
        start_week_date = today - timedelta(
            days=today.weekday()
        )

        # Premier jour du mois courant
        start_month_date = today.replace(day=1)

        # Premier janvier année courante
        start_year_date = today.replace(
            month=1,
            day=1,
        )

        start_week = timezone.make_aware(
            datetime.combine(
                start_week_date,
                datetime.min.time(),
            )
        )

        start_month = timezone.make_aware(
            datetime.combine(
                start_month_date,
                datetime.min.time(),
            )
        )

        start_year = timezone.make_aware(
            datetime.combine(
                start_year_date,
                datetime.min.time(),
            )
        )

        start_30_days_date = today - timedelta(days=29)

        start_30_days = timezone.make_aware(
            datetime.combine(
                start_30_days_date,
                datetime.min.time(),
            )
        )

        # ============================================================
        # 3. QUERYSET DE BASE
        # ============================================================

        ventes_vendor = (
            VenteProduit.objects
            .select_related(
                "vente",
                "vente__facture_vente",
                "produit",
            )
            .filter(
                vendor=vendor,
                vente__is_cancelled=False,
                vente__facture_vente__status=Facture.STAT_PAYE,
            )
        )

        # Dashboard principal = année courante
        ventes_annee_base = ventes_vendor.filter(
            vente__created_at__gte=start_year,
        )

        # ============================================================
        # HELPER AGRÉGATION
        # ============================================================

        def aggregate_period(queryset):
            result = queryset.aggregate(
                total_quantite=Sum("quantite"),
                total_ttc=Sum("montant_total"),
                nombre_ventes=Count(
                    "vente_id",
                    distinct=True,
                ),
            )

            return {
                "nombre_ventes": int(
                    result["nombre_ventes"] or 0
                ),
                "total_quantite": int(
                    result["total_quantite"] or 0
                ),
                "total_ttc": str(
                    result["total_ttc"] or ZERO
                ),
            }

        # ============================================================
        # 4. SEMAINE COURANTE
        # ============================================================

        ventes_semaine = aggregate_period(
            ventes_annee_base.filter(
                vente__created_at__gte=start_week,
            )
        )

        # ============================================================
        # 5. MOIS COURANT
        # ============================================================

        ventes_mois = aggregate_period(
            ventes_annee_base.filter(
                vente__created_at__gte=start_month,
            )
        )

        # ============================================================
        # 6. ANNÉE COURANTE
        # ============================================================

        ventes_annee = aggregate_period(
            ventes_annee_base
        )

        # ============================================================
        # 7. RÉSUMÉ
        # ============================================================

        resume = {
            "ca_semaine": ventes_semaine["total_ttc"],
            "ca_mois": ventes_mois["total_ttc"],
            "ca_annee": ventes_annee["total_ttc"],

            "nombre_ventes_semaine":
                ventes_semaine["nombre_ventes"],

            "nombre_ventes_mois":
                ventes_mois["nombre_ventes"],

            "nombre_ventes_annee":
                ventes_annee["nombre_ventes"],

            "quantite_vendue_annee":
                ventes_annee["total_quantite"],
        }

        # ============================================================
        # 8. TOP PRODUITS — ANNÉE COURANTE
        # ============================================================

        top_produits_qs = (
            ventes_annee_base
            .values(
                "produit_id",
                "produit__nom",
                "produit__sku",
                "produit__etat",
                "produit__poids",
            )
            .annotate(
                total_quantite=Sum("quantite"),
                total_ttc=Sum("montant_total"),
                nombre_ventes=Count(
                    "vente_id",
                    distinct=True,
                ),
            )
            .order_by(
                "-total_quantite",
                "-total_ttc",
            )[:10]
        )

        top_produits = [
            {
                "produit_id": item["produit_id"],
                "nom": item["produit__nom"],
                "sku": item["produit__sku"],
                "etat": item["produit__etat"],

                "poids": (
                    str(item["produit__poids"])
                    if item["produit__poids"] is not None
                    else None
                ),

                "nombre_ventes": int(
                    item["nombre_ventes"] or 0
                ),

                "total_quantite": int(
                    item["total_quantite"] or 0
                ),

                "total_ttc": str(
                    item["total_ttc"] or ZERO
                ),
            }
            for item in top_produits_qs
        ]

        # ============================================================
        # 9. STOCK VENDEUR
        # ============================================================

        stock_qs = (
            VendorStock.objects
            .select_related(
                "produit_line",
                "produit_line__produit",
                "produit_line__produit__categorie",
                "produit_line__produit__marque",
                "produit_line__produit__purete",
                "produit_line__produit__modele",
                "produit_line__lot",
            )
            .filter(
                vendor=vendor,
                bijouterie_id=vendor.bijouterie_id,
            )
            .order_by("-id")
        )

        stock_restant = []

        total_alloue = 0
        total_vendu = 0
        total_restant = 0
        references_disponibles = 0

        for stock in stock_qs:

            produit_line = stock.produit_line

            produit = (
                getattr(
                    produit_line,
                    "produit",
                    None,
                )
                if produit_line
                else None
            )

            lot = (
                getattr(
                    produit_line,
                    "lot",
                    None,
                )
                if produit_line
                else None
            )

            quantite_allouee = int(
                stock.quantite_allouee or 0
            )

            quantite_vendue = int(
                stock.quantite_vendue or 0
            )

            restant = max(
                quantite_allouee - quantite_vendue,
                0,
            )

            # Totaux incluent même les lignes épuisées
            total_alloue += quantite_allouee
            total_vendu += quantite_vendue
            total_restant += restant

            # On n'affiche pas les lignes épuisées
            if restant <= 0:
                continue

            references_disponibles += 1

            stock_restant.append(
                {
                    "vendor_stock_id": stock.id,

                    "produit_line_id": (
                        produit_line.id
                        if produit_line
                        else None
                    ),

                    "produit_id": (
                        produit.id
                        if produit
                        else None
                    ),

                    "produit_nom": (
                        produit.nom
                        if produit
                        else None
                    ),

                    "sku": (
                        produit.sku
                        if produit
                        else None
                    ),

                    "etat": (
                        produit.etat
                        if produit
                        else None
                    ),

                    "poids": (
                        str(produit.poids)
                        if (
                            produit
                            and produit.poids is not None
                        )
                        else None
                    ),

                    "categorie": (
                        produit.categorie.nom
                        if (
                            produit
                            and produit.categorie
                        )
                        else None
                    ),

                    "marque": (
                        produit.marque.marque
                        if (
                            produit
                            and produit.marque
                        )
                        else None
                    ),

                    "purete": (
                        produit.purete.purete
                        if (
                            produit
                            and produit.purete
                        )
                        else None
                    ),

                    "modele": (
                        produit.modele.modele
                        if (
                            produit
                            and produit.modele
                        )
                        else None
                    ),

                    "lot_id": (
                        lot.id
                        if lot
                        else None
                    ),

                    "numero_lot": (
                        getattr(
                            lot,
                            "numero_lot",
                            None,
                        )
                        if lot
                        else None
                    ),

                    "quantite_allouee":
                        quantite_allouee,

                    "quantite_vendue":
                        quantite_vendue,

                    "quantite_restante":
                        restant,
                }
            )

        stock_totaux = {
            "quantite_allouee": total_alloue,
            "quantite_vendue": total_vendu,
            "quantite_restante": total_restant,
            "references_disponibles":
                references_disponibles,
        }

        # ============================================================
        # 10. GRAPHIQUE — 30 DERNIERS JOURS
        # ============================================================

        graphique_rows = (
            ventes_vendor
            .filter(
                vente__created_at__gte=start_30_days,
            )
            .values(
                "vente__created_at",
                "vente_id",
                "quantite",
                "montant_total",
            )
            .order_by(
                "vente__created_at"
            )
        )

        by_day = defaultdict(
            lambda: {
                "total_quantite": 0,
                "total_ttc": ZERO,
                "vente_ids": set(),
            }
        )

        for row in graphique_rows:

            dt = row["vente__created_at"]

            if not dt:
                continue

            local_day = (
                timezone.localtime(dt)
                .date()
                .isoformat()
            )

            by_day[local_day][
                "total_quantite"
            ] += int(
                row["quantite"] or 0
            )

            by_day[local_day][
                "total_ttc"
            ] += (
                row["montant_total"]
                or ZERO
            )

            if row["vente_id"]:
                by_day[local_day][
                    "vente_ids"
                ].add(
                    row["vente_id"]
                )

        graphique_30_jours = []

        for offset in range(30):

            current_date = (
                start_30_days_date
                + timedelta(days=offset)
            )

            day_key = current_date.isoformat()

            data = by_day.get(
                day_key,
                {
                    "total_quantite": 0,
                    "total_ttc": ZERO,
                    "vente_ids": set(),
                },
            )

            graphique_30_jours.append(
                {
                    "jour": day_key,

                    "nombre_ventes": len(
                        data["vente_ids"]
                    ),

                    "total_quantite": int(
                        data["total_quantite"]
                    ),

                    "total_ttc": str(
                        data["total_ttc"]
                    ),
                }
            )

        # ============================================================
        # 11. DERNIÈRES VENTES PAYÉES
        # ============================================================

        dernieres_ventes_qs = (
            ventes_annee_base
            .values(
                "vente_id",
                "vente__numero_vente",
                "vente__created_at",
                "vente__client__nom",
                "vente__client__prenom",
                "vente__client__telephone",
            )
            .annotate(
                total_quantite=Sum("quantite"),
                total_ttc=Sum("montant_total"),
            )
            .order_by(
                "-vente__created_at",
                "-vente_id",
            )[:10]
        )

        dernieres_ventes = []

        for item in dernieres_ventes_qs:

            created_at = item[
                "vente__created_at"
            ]

            dernieres_ventes.append(
                {
                    "vente_id":
                        item["vente_id"],

                    "numero_vente":
                        item["vente__numero_vente"],

                    "date": (
                        timezone.localtime(
                            created_at
                        ).isoformat()
                        if created_at
                        else None
                    ),

                    "client": {
                        "nom":
                            item[
                                "vente__client__nom"
                            ],

                        "prenom":
                            item[
                                "vente__client__prenom"
                            ],

                        "telephone":
                            item[
                                "vente__client__telephone"
                            ],
                    },

                    "total_quantite": int(
                        item["total_quantite"]
                        or 0
                    ),

                    "total_ttc": str(
                        item["total_ttc"]
                        or ZERO
                    ),

                    "status": Facture.STAT_PAYE,
                }
            )

        # ============================================================
        # 12. HISTORIQUE ANNUEL
        # ============================================================

        historique_qs = (
            ventes_vendor
            .values(
                "vente__created_at__year"
            )
            .annotate(
                nombre_ventes=Count(
                    "vente_id",
                    distinct=True,
                ),
                total_quantite=Sum(
                    "quantite"
                ),
                total_ttc=Sum(
                    "montant_total"
                ),
            )
            .order_by(
                "-vente__created_at__year"
            )
        )

        historique = []

        for item in historique_qs:

            annee = item[
                "vente__created_at__year"
            ]

            if not annee:
                continue

            historique.append(
                {
                    "annee": int(annee),

                    "nombre_ventes": int(
                        item["nombre_ventes"]
                        or 0
                    ),

                    "total_quantite": int(
                        item["total_quantite"]
                        or 0
                    ),

                    "total_ttc": str(
                        item["total_ttc"]
                        or ZERO
                    ),
                }
            )

        # ============================================================
        # 13. RESPONSE
        # ============================================================

        return Response(
            {
                "vendor": {
                    "id": vendor.id,

                    "email": getattr(
                        getattr(
                            vendor,
                            "user",
                            None,
                        ),
                        "email",
                        None,
                    ),

                    "bijouterie_id":
                        vendor.bijouterie_id,

                    "bijouterie": getattr(
                        getattr(
                            vendor,
                            "bijouterie",
                            None,
                        ),
                        "nom",
                        None,
                    ),
                },

                "periode": {
                    "annee": today.year,

                    "date_debut":
                        start_year_date.isoformat(),

                    "date_fin":
                        today.isoformat(),
                },

                "resume": resume,

                "ventes_semaine":
                    ventes_semaine,

                "ventes_mois":
                    ventes_mois,

                "ventes_annee":
                    ventes_annee,

                "top_produits":
                    top_produits,

                "stock": {
                    "totaux":
                        stock_totaux,

                    "count":
                        len(stock_restant),

                    "results":
                        stock_restant,
                },

                "graphique_30_jours":
                    graphique_30_jours,

                "dernieres_ventes":
                    dernieres_ventes,

                "historique":
                    historique,
            },
            status=status.HTTP_200_OK,
        )
        
        

