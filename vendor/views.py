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
from inventory.models import Bucket, InventoryMovement, MovementType
# ⬇️ aligne le chemin du modèle de lot d’achat
from purchase.models import Lot, ProduitLine
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
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

from backend.permissions import IsAdminOrManager  # ton permission
from backend.permissions import ROLE_VENDOR
from backend.query_scopes import scope_bijouterie_q
from backend.renderers import UserRenderer
from backend.roles import ROLE_ADMIN, ROLE_MANAGER, get_role_name

from .models import Vendor
from .serializer import (CreateVendorSerializer, VendorDashboardKpiSerializer,
                         VendorDashboardSeriesSerializer, VendorListSerializer,
                         VendorStockListSerializer,
                         VendorStockSummaryByProduitSerializer,
                         VendorStockSummaryByVendorProduitSerializer,
                         VendorStockSummaryByVendorSerializer,
                         VendorUpdateSerializer)

# Create your views here.
User = get_user_model()
allowed_all_roles = ['admin', 'manager', 'vendeur']
allowed_roles_admin_manager = ['admin', 'manager',]


# class VendorStockView(APIView):
#     """
#     Stock réel du vendeur connecté
#     = quantite_allouee - quantite_vendue
#     """
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Stock réel du vendeur connecté",
#         operation_description=(
#             "Retourne le stock réel du vendeur connecté.\n\n"
#             "Formule : stock_reel = quantite_allouee - quantite_vendue\n\n"
#             "- Ignore les produits avec stock = 0\n"
#             "- Inclut produit, SKU, lot\n"
#         ),
#         tags=["vendor"],
#         responses={200: openapi.Response("Liste du stock vendeur")},
#     )
#     def get(self, request):
#         vendor = getattr(request.user, "staff_vendor_profile", None)
#         if not vendor:
#             return Response(
#                 {"detail": "Profil vendeur introuvable."},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         qs = (
#             VendorStock.objects
#             .select_related(
#                 "produit_line",
#                 "produit_line__produit",
#                 "produit_line__lot",
#             )
#             .filter(vendor=vendor)
#         )

#         results = []

#         for stock in qs:
#             produit = getattr(stock.produit_line, "produit", None)

#             quantite_allouee = int(stock.quantite_allouee or 0)
#             quantite_vendue = int(stock.quantite_vendue or 0)

#             stock_reel = quantite_allouee - quantite_vendue

#             # ignorer stock vide
#             if stock_reel <= 0:
#                 continue

#             results.append({
#                 "produit_id": produit.id if produit else None,
#                 "produit_nom": produit.nom if produit else None,
#                 "sku": getattr(produit, "sku", None) if produit else None,
#                 "lot": getattr(stock.produit_line.lot, "numero_lot", None),
#                 "quantite_allouee": quantite_allouee,
#                 "quantite_vendue": quantite_vendue,
#                 "stock_reel": stock_reel,
#             })

#         return Response({
#             "vendor_id": vendor.id,
#             "count": len(results),
#             "results": results
#         }, status=status.HTTP_200_OK)
    


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


class VendorDashboardView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get"]

    @swagger_auto_schema(
        operation_summary="Dashboard vendeur connecté",
        operation_description=(
            "Retourne le tableau de bord du vendeur connecté :\n"
            "- ventes semaine\n"
            "- ventes mois\n"
            "- ventes année\n"
            "- top produits\n"
            "- stock restant\n"
            "- graphique journalier sur 30 jours\n"
        ),
        tags=["vendor"],
        responses={200: openapi.Response("OK")},
    )
    def get(self, request):
        vendor = getattr(request.user, "staff_vendor_profile", None)
        if not vendor:
            return Response(
                {"detail": "Profil vendeur introuvable."},
                status=status.HTTP_400_BAD_REQUEST
            )

        now = timezone.now()
        start_week = now - timedelta(days=7)
        start_month = now - timedelta(days=30)
        start_year = now - timedelta(days=365)

        # -----------------------------
        # 1) ventes semaine
        # -----------------------------
        ventes_semaine_qs = (
            VenteProduit.objects
            .filter(vendor=vendor, vente__created_at__gte=start_week)
            .aggregate(
                total_quantite=Sum("quantite"),
                total_ttc=Sum("montant_total")
            )
        )

        ventes_semaine = {
            "total_quantite": int(ventes_semaine_qs["total_quantite"] or 0),
            "total_ttc": float(ventes_semaine_qs["total_ttc"] or 0),
        }

        # -----------------------------
        # 2) ventes mois
        # -----------------------------
        ventes_mois_qs = (
            VenteProduit.objects
            .filter(vendor=vendor, vente__created_at__gte=start_month)
            .aggregate(
                total_quantite=Sum("quantite"),
                total_ttc=Sum("montant_total")
            )
        )

        ventes_mois = {
            "total_quantite": int(ventes_mois_qs["total_quantite"] or 0),
            "total_ttc": float(ventes_mois_qs["total_ttc"] or 0),
        }

        # -----------------------------
        # 3) ventes année
        # -----------------------------
        ventes_annee_qs = (
            VenteProduit.objects
            .filter(vendor=vendor, vente__created_at__gte=start_year)
            .aggregate(
                total_quantite=Sum("quantite"),
                total_ttc=Sum("montant_total")
            )
        )

        ventes_annee = {
            "total_quantite": int(ventes_annee_qs["total_quantite"] or 0),
            "total_ttc": float(ventes_annee_qs["total_ttc"] or 0),
        }

        # -----------------------------
        # 4) top produits
        # -----------------------------
        top_produits_qs = (
            VenteProduit.objects
            .filter(vendor=vendor)
            .values("produit__id", "produit__nom", "produit__sku")
            .annotate(
                total_quantite=Sum("quantite"),
                total_ttc=Sum("montant_total")
            )
            .order_by("-total_quantite")[:10]
        )

        top_produits = []
        for item in top_produits_qs:
            top_produits.append({
                "produit_id": item["produit__id"],
                "nom": item["produit__nom"],
                "sku": item["produit__sku"],
                "total_quantite": int(item["total_quantite"] or 0),
                "total_ttc": float(item["total_ttc"] or 0),
            })

        # -----------------------------
        # 5) stock restant
        # -----------------------------
        stock_qs = (
            VendorStock.objects
            .select_related("produit_line", "produit_line__produit")
            .filter(vendor=vendor)
        )

        stock_restant = []
        for stock in stock_qs:
            produit = getattr(stock.produit_line, "produit", None)
            restant = int(stock.quantite_allouee or 0) - int(stock.quantite_vendue or 0)

            stock_restant.append({
                "produit_id": produit.id if produit else None,
                "produit_nom": produit.nom if produit else None,
                "sku": getattr(produit, "sku", None) if produit else None,
                "quantite_allouee": int(stock.quantite_allouee or 0),
                "quantite_vendue": int(stock.quantite_vendue or 0),
                "restant": restant,
            })

        # -----------------------------
        # 6) graphique par jour (30 jours)
        # ⚠️ sans TruncDay pour éviter le bug MySQL timezone
        # -----------------------------
        graphique_rows = (
            VenteProduit.objects
            .filter(vendor=vendor, vente__created_at__gte=start_month)
            .values("vente__created_at", "quantite", "montant_total")
            .order_by("vente__created_at")
        )

        by_day = defaultdict(lambda: {
            "total_quantite": 0,
            "total_ttc": 0.0,
        })

        for row in graphique_rows:
            dt = row["vente__created_at"]
            if not dt:
                continue

            local_day = timezone.localtime(dt).date().isoformat()
            by_day[local_day]["total_quantite"] += int(row["quantite"] or 0)
            by_day[local_day]["total_ttc"] += float(row["montant_total"] or 0)

        graphique = []
        for day in sorted(by_day.keys()):
            graphique.append({
                "jour": day,
                "total_quantite": by_day[day]["total_quantite"],
                "total_ttc": by_day[day]["total_ttc"],
            })

        return Response(
            {
                "vendor": {
                    "id": vendor.id,
                    "email": getattr(getattr(vendor, "user", None), "email", None),
                    "bijouterie": getattr(getattr(vendor, "bijouterie", None), "nom", None),
                },
                "ventes_semaine": ventes_semaine,
                "ventes_mois": ventes_mois,
                "ventes_annee": ventes_annee,
                "top_produits": top_produits,
                "stock_restant": stock_restant,
                "graphique": graphique,
            },
            status=status.HTTP_200_OK
        )


