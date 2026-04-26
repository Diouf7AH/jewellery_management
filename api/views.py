# dashboard/views.py  (ou api/views/dashboard.py)

from __future__ import annotations

from datetime import datetime
from datetime import time as dtime
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import (Case, Count, DecimalField, ExpressionWrapper, F,
                              IntegerField, Q, Sum, Value, When)
from django.db.models.functions import (Coalesce, TruncDay, TruncMonth,
                                        TruncWeek)
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.permissions import IsAdminOrManager
from backend.query_scopes import scope_bijouterie_q
from backend.roles import ROLE_ADMIN, ROLE_MANAGER, get_role_name
from sale.models import Facture, Paiement, Vente, VenteProduit
from stock.models import Stock, VendorStock
from store.models import Bijouterie, MarquePurete
from store.services.price_history_service import update_marque_purete_price

from .serializers import CommercialSettingsSerializer


def _parse_date(v: str | None):
    if not v:
        return None
    try:
        return datetime.strptime(v, "%Y-%m-%d").date()
    except Exception:
        return None


def _aware_range(date_from, date_to, tz):
    start_dt = timezone.make_aware(datetime.combine(date_from, dtime.min), tz)
    end_dt = timezone.make_aware(datetime.combine(date_to + timedelta(days=1), dtime.min), tz)
    return start_dt, end_dt


class ManagerDashboardAPIView(APIView):
    """
    Dashboard manager/admin:
    - ventes
    - paiements / cash
    - stock
    - top produits
    - série temporelle
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]

    @swagger_auto_schema(
        operation_id="managerDashboard",
        operation_summary="Dashboard manager complet (ventes + stock + top produits + cash)",
        operation_description=(
            "Retourne un dashboard global pour **admin** ou **manager**.\n\n"
            "### Scopes\n"
            "- **admin** : toutes les bijouteries, ou une bijouterie précise via `bijouterie_id`\n"
            "- **manager** : limité automatiquement à ses bijouteries (**ManyToMany**)\n\n"
            "### Période\n"
            "- par défaut : les 30 derniers jours\n"
            "- sinon : `date_from=YYYY-MM-DD&date_to=YYYY-MM-DD`\n\n"
            "### group_by\n"
            "- `day` (défaut)\n"
            "- `week`\n"
            "- `month`\n"
        ),
        manual_parameters=[
            openapi.Parameter(
                "date_from", openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                format="date",
                required=False,
                description="Date début (YYYY-MM-DD). Défaut = 30 jours avant aujourd’hui.",
            ),
            openapi.Parameter(
                "date_to", openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                format="date",
                required=False,
                description="Date fin (YYYY-MM-DD). Défaut = aujourd’hui.",
            ),
            openapi.Parameter(
                "group_by", openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
                enum=["day", "week", "month"],
                default="day",
                description="Agrégation de la courbe d’évolution.",
            ),
            openapi.Parameter(
                "bijouterie_id", openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="Admin seulement: filtrer une bijouterie précise.",
            ),
            openapi.Parameter(
                "vendor_id", openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="Optionnel: filtrer sur un vendeur précis.",
            ),
        ],
        responses={
            200: openapi.Response(
                description="Dashboard manager",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "period": openapi.Schema(type=openapi.TYPE_OBJECT),
                        "scope": openapi.Schema(type=openapi.TYPE_OBJECT),
                        "kpis": openapi.Schema(type=openapi.TYPE_OBJECT),
                        "payments_by_mode": openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Items(type=openapi.TYPE_OBJECT)),
                        "sales_over_time": openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Items(type=openapi.TYPE_OBJECT)),
                        "top_products": openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Items(type=openapi.TYPE_OBJECT)),
                        "stock_summary": openapi.Schema(type=openapi.TYPE_OBJECT),
                        "stock_by_product": openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Items(type=openapi.TYPE_OBJECT)),
                    },
                ),
            ),
            400: openapi.Response(description="Paramètres invalides"),
            403: openapi.Response(description="Accès refusé"),
        },
        tags=["Dashboard"],
    )
    def get(self, request):
        user = request.user
        role = get_role_name(user)
        tz = timezone.get_current_timezone()

        if role not in {ROLE_ADMIN, ROLE_MANAGER}:
            return Response({"detail": "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        # ---------------------------------------------------
        # 1) Période
        # ---------------------------------------------------
        date_from_raw = (request.query_params.get("date_from") or "").strip()
        date_to_raw = (request.query_params.get("date_to") or "").strip()

        if not date_from_raw and not date_to_raw:
            date_to = timezone.localdate()
            date_from = date_to - timedelta(days=29)
        else:
            date_from = _parse_date(date_from_raw) if date_from_raw else None
            date_to = _parse_date(date_to_raw) if date_to_raw else None

            if date_from and not date_to:
                date_to = date_from
            if date_to and not date_from:
                date_from = date_to

            if not date_from or not date_to:
                return Response(
                    {"detail": "Format date invalide. Utilise YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if date_from > date_to:
                return Response(
                    {"detail": "date_from doit être <= date_to."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        start_dt, end_dt = _aware_range(date_from, date_to, tz)

        group_by = (request.query_params.get("group_by") or "day").strip().lower()
        if group_by not in {"day", "week", "month"}:
            return Response(
                {"detail": "group_by invalide. Choisir parmi day, week, month."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---------------------------------------------------
        # 2) Scope bijouterie
        # ---------------------------------------------------
        vente_scope_q = scope_bijouterie_q(user, field="bijouterie_id")
        facture_scope_q = scope_bijouterie_q(user, field="bijouterie_id")
        stock_scope_q = scope_bijouterie_q(user, field="bijouterie_id")
        vendor_stock_scope_q = scope_bijouterie_q(user, field="bijouterie_id")

        # admin peut filtrer une bijouterie précise
        bijouterie_id = request.query_params.get("bijouterie_id")
        if bijouterie_id:
            try:
                bijouterie_id = int(bijouterie_id)
            except ValueError:
                return Response({"detail": "bijouterie_id doit être un entier."}, status=status.HTTP_400_BAD_REQUEST)

            if role != ROLE_ADMIN:
                return Response({"detail": "bijouterie_id est réservé à l’admin."}, status=status.HTTP_403_FORBIDDEN)

            vente_scope_q &= Q(bijouterie_id=bijouterie_id)
            facture_scope_q &= Q(bijouterie_id=bijouterie_id)
            stock_scope_q &= Q(bijouterie_id=bijouterie_id)
            vendor_stock_scope_q &= Q(bijouterie_id=bijouterie_id)

        vendor_id = request.query_params.get("vendor_id")
        vendor_id_int = None
        if vendor_id:
            try:
                vendor_id_int = int(vendor_id)
            except ValueError:
                return Response({"detail": "vendor_id doit être un entier."}, status=status.HTTP_400_BAD_REQUEST)

        # ---------------------------------------------------
        # 3) Querysets de base
        # ---------------------------------------------------
        ventes_qs = (
            Vente.objects
            .select_related("bijouterie", "client", "vendor")
            .filter(vente_scope_q)
            .filter(created_at__gte=start_dt, created_at__lt=end_dt)
        )

        factures_qs = (
            Facture.objects
            .select_related("bijouterie", "vente")
            .filter(facture_scope_q)
            .filter(date_creation__gte=start_dt, date_creation__lt=end_dt)
        )

        paiements_qs = (
            Paiement.objects
            .select_related("facture", "facture__bijouterie", "cashier", "created_by")
            .filter(facture__bijouterie_id__in=factures_qs.values("bijouterie_id"))
            .filter(date_paiement__gte=start_dt, date_paiement__lt=end_dt)
        )

        lignes_qs = (
            VenteProduit.objects
            .select_related("vente", "vente__bijouterie", "produit", "vendor")
            .filter(vente__bijouterie_id__in=ventes_qs.values("bijouterie_id"))
            .filter(vente__created_at__gte=start_dt, vente__created_at__lt=end_dt)
        )

        if vendor_id_int:
            ventes_qs = ventes_qs.filter(vendor_id=vendor_id_int)
            lignes_qs = lignes_qs.filter(vendor_id=vendor_id_int)
            factures_qs = factures_qs.filter(vente__produits__vendor_id=vendor_id_int).distinct()
            paiements_qs = paiements_qs.filter(facture__vente__produits__vendor_id=vendor_id_int).distinct()

        # ---------------------------------------------------
        # 4) KPIs ventes / cash
        # ---------------------------------------------------
        ventes_count = ventes_qs.distinct().count()

        ventes_amount = (
            factures_qs.filter(status=Facture.STAT_PAYE)
            .aggregate(total=Coalesce(Sum("montant_total"), Decimal("0.00")))
            .get("total") or Decimal("0.00")
        )

        cash_total = (
            paiements_qs.aggregate(total=Coalesce(Sum("montant_paye"), Decimal("0.00"))).get("total")
            or Decimal("0.00")
        )

        unpaid_total = (
            Facture.objects
            .filter(facture_scope_q)
            .filter(status=Facture.STAT_NON_PAYE)
            .aggregate(total=Coalesce(Sum("montant_total"), Decimal("0.00")))
            .get("total") or Decimal("0.00")
        )

        avg_ticket = Decimal("0.00")
        if ventes_count > 0:
            avg_ticket = (ventes_amount / Decimal(ventes_count)).quantize(Decimal("0.01"))

        total_qty_sold = (
            lignes_qs.aggregate(total=Coalesce(Sum("quantite"), 0)).get("total") or 0
        )

        # ---------------------------------------------------
        # 5) Paiements par mode
        # ---------------------------------------------------
        payments_by_mode = list(
            paiements_qs.values("mode_paiement")
            .annotate(
                total=Coalesce(Sum("montant_paye"), Decimal("0.00")),
                count=Count("id"),
            )
            .order_by("mode_paiement")
        )

        payments_by_mode = [
            {
                "mode_paiement": row["mode_paiement"],
                "count": int(row["count"] or 0),
                "total": float(row["total"] or 0),
            }
            for row in payments_by_mode
        ]

        # ---------------------------------------------------
        # 6) Courbe d’évolution ventes
        # ---------------------------------------------------
        trunc_map = {
            "day": TruncDay("date_creation"),
            "week": TruncWeek("date_creation"),
            "month": TruncMonth("date_creation"),
        }

        sales_over_time_qs = (
            factures_qs.filter(status=Facture.STAT_PAYE)
            .annotate(period=trunc_map[group_by])
            .values("period")
            .annotate(
                ventes_count=Count("id"),
                total=Coalesce(Sum("montant_total"), Decimal("0.00")),
            )
            .order_by("period")
        )

        sales_over_time = [
            {
                "period": row["period"].date().isoformat() if row["period"] else None,
                "ventes_count": int(row["ventes_count"] or 0),
                "total": float(row["total"] or 0),
            }
            for row in sales_over_time_qs
        ]

        # ---------------------------------------------------
        # 7) Top produits
        # ---------------------------------------------------
        top_products_qs = (
            lignes_qs.values("produit_id", "produit__nom", "produit__slug")
            .annotate(
                quantite=Coalesce(Sum("quantite"), 0),
                total_ht=Coalesce(Sum("sous_total_prix_vente_ht"), Decimal("0.00")),
                total_ttc=Coalesce(Sum("prix_ttc"), Decimal("0.00")),
                ventes_distinctes=Count("vente_id", distinct=True),
            )
            .order_by("-total_ttc", "-quantite")[:10]
        )

        top_products = [
            {
                "produit_id": row["produit_id"],
                "produit": row["produit__nom"] or "Produit supprimé",
                "slug": row["produit__slug"],
                "quantite": int(row["quantite"] or 0),
                "total_ht": float(row["total_ht"] or 0),
                "total_ttc": float(row["total_ttc"] or 0),
                "ventes_distinctes": int(row["ventes_distinctes"] or 0),
            }
            for row in top_products_qs
        ]

        # ---------------------------------------------------
        # 8) Résumé stock boutique
        # ---------------------------------------------------
        stock_qs = (
            Stock.objects
            .select_related("bijouterie", "produit_line", "produit_line__produit")
            .filter(stock_scope_q)
        )

        stock_summary = stock_qs.aggregate(
            total_en_stock=Coalesce(Sum("en_stock"), 0),
            total_disponible=Coalesce(Sum("quantite_disponible"), 0),
            lignes_stock=Count("id"),
        )

        reserve_qs = Stock.objects.filter(is_reserve=True, bijouterie__isnull=True)
        reserve_total = reserve_qs.aggregate(total=Coalesce(Sum("en_stock"), 0)).get("total") or 0

        vendor_stock_qs = (
            VendorStock.objects
            .select_related("vendor", "vendor__user", "produit_line", "produit_line__produit")
            .filter(vendor_stock_scope_q)
            .annotate(
                disponible=ExpressionWrapper(
                    Coalesce(F("quantite_allouee"), Value(0)) - Coalesce(F("quantite_vendue"), Value(0)),
                    output_field=IntegerField(),
                )
            )
        )

        vendor_available_total = (
            vendor_stock_qs.aggregate(total=Coalesce(Sum("disponible"), 0)).get("total") or 0
        )

        stock_by_product_qs = (
            stock_qs.values("produit_line__produit_id", "produit_line__produit__nom")
            .annotate(
                total_en_stock=Coalesce(Sum("en_stock"), 0),
                total_disponible=Coalesce(Sum("quantite_disponible"), 0),
            )
            .order_by("-total_en_stock", "produit_line__produit__nom")[:10]
        )

        stock_by_product = [
            {
                "produit_id": row["produit_line__produit_id"],
                "produit": row["produit_line__produit__nom"],
                "en_stock": int(row["total_en_stock"] or 0),
                "quantite_disponible": int(row["total_disponible"] or 0),
            }
            for row in stock_by_product_qs
        ]

        # ---------------------------------------------------
        # 9) Réponse finale
        # ---------------------------------------------------
        return Response(
            {
                "period": {
                    "date_from": date_from.isoformat(),
                    "date_to": date_to.isoformat(),
                    "group_by": group_by,
                },
                "scope": {
                    "role": role,
                    "bijouterie_id": bijouterie_id,
                    "vendor_id": vendor_id_int,
                },
                "kpis": {
                    "ventes_count": int(ventes_count),
                    "ventes_amount": float(ventes_amount),
                    "cash_total": float(cash_total),
                    "unpaid_total": float(unpaid_total),
                    "average_ticket": float(avg_ticket),
                    "total_qty_sold": int(total_qty_sold or 0),
                },
                "payments_by_mode": payments_by_mode,
                "sales_over_time": sales_over_time,
                "top_products": top_products,
                "stock_summary": {
                    "lignes_stock": int(stock_summary.get("lignes_stock") or 0),
                    "total_en_stock": int(stock_summary.get("total_en_stock") or 0),
                    "total_disponible": int(stock_summary.get("total_disponible") or 0),
                    "reserve_total": int(reserve_total or 0),
                    "vendor_available_total": int(vendor_available_total or 0),
                },
                "stock_by_product": stock_by_product,
            },
            status=status.HTTP_200_OK,
        )
        



class CommercialSettingsUpdateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrManager]

    @swagger_auto_schema(
        operation_id="updateCommercialSettings",
        operation_summary="Mettre à jour la TVA et les prix par marque/pureté",
        operation_description="""
Permet à l’admin ou au manager de :

- activer ou désactiver la TVA d’une bijouterie
- modifier le taux de TVA
- mettre à jour le prix journalier d’un ou plusieurs couples marque/pureté
- créer automatiquement un historique des changements de prix
        """,
        request_body=CommercialSettingsSerializer,
        responses={
            200: openapi.Response(
                description="Paramétrage commercial mis à jour avec succès."
            ),
            400: openapi.Response(
                description="Erreur de validation ou couple marque/pureté introuvable."
            ),
            403: openapi.Response(description="Accès refusé."),
            404: openapi.Response(description="Bijouterie introuvable."),
        },
        tags=["Paramétrage commercial"],
    )
    @transaction.atomic
    def patch(self, request, *args, **kwargs):
        serializer = CommercialSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            bijouterie = Bijouterie.objects.select_for_update().get(pk=data["bijouterie_id"])
        except Bijouterie.DoesNotExist:
            return Response(
                {"detail": "Bijouterie introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # manager -> seulement ses bijouteries
        role = get_role_name(request.user)
        if role == "manager":
            manager = getattr(request.user, "staff_manager_profile", None)
            if not manager or not manager.bijouteries.filter(pk=bijouterie.pk).exists():
                return Response(
                    {"detail": "Vous ne pouvez pas modifier cette bijouterie."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        updated_prices = []

        # -------------------------
        # TVA
        # -------------------------
        if "appliquer_tva" in data:
            bijouterie.appliquer_tva = data["appliquer_tva"]

        if "taux_tva" in data and data["taux_tva"] is not None:
            bijouterie.taux_tva = data["taux_tva"]

        if "appliquer_tva" in data or "taux_tva" in data:
            update_fields = []
            if "appliquer_tva" in data:
                update_fields.append("appliquer_tva")
            if "taux_tva" in data and data["taux_tva"] is not None:
                update_fields.append("taux_tva")
            if hasattr(bijouterie, "updated_at"):
                update_fields.append("updated_at")

            bijouterie.save(update_fields=update_fields)

        # -------------------------
        # PRIX MARQUE / PURETE
        # -------------------------
        for item in data.get("prix_marque_purete", []):
            obj = (
                MarquePurete.objects
                .select_for_update()
                .select_related("marque", "purete")
                .filter(
                    marque__marque__iexact=item["marque"].strip(),
                    purete__purete__iexact=str(item["purete"]).strip(),
                )
                .first()
            )

            if not obj:
                return Response(
                    {
                        "detail": (
                            f"Aucune correspondance trouvée pour "
                            f"marque='{item['marque']}' et purete='{item['purete']}'."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            old_price = Decimal(str(obj.prix or "0.00"))

            try:
                obj, history = update_marque_purete_price(
                    obj=obj,
                    new_price=item["prix"],
                    user=request.user,
                    bijouterie=bijouterie,
                    source="api",
                    note="Mise à jour via paramétrage commercial",
                )
            except ValueError as e:
                return Response(
                    {"detail": str(e)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            updated_prices.append({
                "id": obj.id,
                "marque": getattr(obj.marque, "marque", None),
                "purete": getattr(obj.purete, "purete", None),
                "ancien_prix": str(old_price),
                "nouveau_prix": str(obj.prix),
                "history_id": history.id if history else None,
                "changed": history is not None,
            })

        return Response(
            {
                "message": "Paramétrage commercial mis à jour avec succès.",
                "bijouterie": {
                    "id": bijouterie.id,
                    "nom": bijouterie.nom,
                    "appliquer_tva": bijouterie.appliquer_tva,
                    "taux_tva": str(bijouterie.taux_tva),
                },
                "prix_updates_count": len(updated_prices),
                "prix_updates": updated_prices,
            },
            status=status.HTTP_200_OK,
        )
        



