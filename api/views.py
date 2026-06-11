# dashboard/views.py  (ou api/views/dashboard.py)

from __future__ import annotations

from datetime import datetime
from datetime import time as dtime
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import (Case, Count, DecimalField, ExpressionWrapper, F,
                              IntegerField, Q, Sum, Value, When)
from django.db.models.functions import (Coalesce, TruncDay, TruncMonth,
                                        TruncWeek)
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.permissions import IsAdminOrManager
from backend.query_scopes import scope_bijouterie_q
from backend.roles import ROLE_ADMIN, ROLE_MANAGER, get_role_name
from sale.models import Facture, Paiement, PaiementLigne, Vente, VenteProduit
from stock.models import Stock, VendorStock
from store.models import Bijouterie, MarquePurete
from store.services.price_history_service import update_marque_purete_price
from userauths.permissions import (ROLE_ADMIN, ROLE_MANAGER, IsAdminOrManager,
                                   get_role_name)

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


def _parse_date(value):
    if not value:
        return None
    return parse_date(value)


def _aware_range(date_from, date_to, tz):
    start_dt = timezone.make_aware(
        timezone.datetime.combine(date_from, timezone.datetime.min.time()),
        tz,
    )
    end_dt = timezone.make_aware(
        timezone.datetime.combine(date_to + timedelta(days=1), timezone.datetime.min.time()),
        tz,
    )
    return start_dt, end_dt


def scope_bijouterie_q(user, field="bijouterie_id"):
    """
    Scope admin / manager.

    Admin:
        - voit tout

    Manager:
        - voit uniquement ses bijouteries ManyToMany
        - adapte ici si ton Manager a seulement une bijouterie simple.
    """

    role = get_role_name(user)

    if role == ROLE_ADMIN:
        return Q()

    if role == ROLE_MANAGER:
        manager_profile = getattr(user, "manager", None)

        if not manager_profile:
            return Q(pk__isnull=True)

        if hasattr(manager_profile, "bijouteries"):
            ids = list(manager_profile.bijouteries.values_list("id", flat=True))
            return Q(**{f"{field}__in": ids})

        if hasattr(manager_profile, "bijouterie") and manager_profile.bijouterie_id:
            return Q(**{field: manager_profile.bijouterie_id})

        return Q(pk__isnull=True)

    return Q(pk__isnull=True)


class ManagerDashboardAPIView(APIView):
    """
    Dashboard manager/admin:
    - ventes
    - paiements
    - stock
    - top produits
    - courbe temporelle
    """

    permission_classes = [IsAuthenticated, IsAdminOrManager]

    @swagger_auto_schema(
        operation_id="managerDashboard",
        operation_summary="Dashboard manager complet",
        operation_description=(
            "Retourne un dashboard complet pour admin ou manager.\n\n"
            "- Admin : toutes les bijouteries ou filtre par `bijouterie_id`\n"
            "- Manager : limité automatiquement à ses bijouteries\n\n"
            "Période par défaut : les 30 derniers jours."
        ),
        manual_parameters=[
            openapi.Parameter(
                "date_from",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                format="date",
                required=False,
                description="Date début YYYY-MM-DD",
            ),
            openapi.Parameter(
                "date_to",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                format="date",
                required=False,
                description="Date fin YYYY-MM-DD",
            ),
            openapi.Parameter(
                "group_by",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                enum=["day", "week", "month"],
                default="day",
                required=False,
                description="Agrégation: day, week ou month",
            ),
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="Admin seulement : filtrer une bijouterie précise",
            ),
            openapi.Parameter(
                "vendor_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="Filtrer par vendeur",
            ),
        ],
        responses={
            200: openapi.Response("Dashboard manager"),
            400: openapi.Response("Paramètres invalides"),
            403: openapi.Response("Accès refusé"),
        },
        tags=["Dashboard"],
    )
    def get(self, request):
        user = request.user
        role = get_role_name(user)
        tz = timezone.get_current_timezone()

        if role not in {ROLE_ADMIN, ROLE_MANAGER}:
            return Response(
                {"detail": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # =========================
        # 1. Période
        # =========================
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
                    {"detail": "date_from doit être inférieur ou égal à date_to."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        start_dt, end_dt = _aware_range(date_from, date_to, tz)

        group_by = (request.query_params.get("group_by") or "day").strip().lower()

        if group_by not in {"day", "week", "month"}:
            return Response(
                {"detail": "group_by invalide. Choisir day, week ou month."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =========================
        # 2. Scopes
        # =========================
        vente_scope_q = scope_bijouterie_q(user, field="bijouterie_id")
        facture_scope_q = scope_bijouterie_q(user, field="bijouterie_id")
        stock_scope_q = scope_bijouterie_q(user, field="bijouterie_id")
        vendor_stock_scope_q = scope_bijouterie_q(user, field="bijouterie_id")

        bijouterie_id = request.query_params.get("bijouterie_id")

        if bijouterie_id:
            try:
                bijouterie_id = int(bijouterie_id)
            except ValueError:
                return Response(
                    {"detail": "bijouterie_id doit être un entier."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if role != ROLE_ADMIN:
                return Response(
                    {"detail": "bijouterie_id est réservé à l’admin."},
                    status=status.HTTP_403_FORBIDDEN,
                )

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
                return Response(
                    {"detail": "vendor_id doit être un entier."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # =========================
        # 3. Querysets
        # =========================
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

        paiement_lignes_qs = (
            PaiementLigne.objects
            .select_related("paiement", "paiement__facture", "mode_paiement")
            .filter(paiement__in=paiements_qs)
        )

        lignes_qs = (
            VenteProduit.objects
            .select_related("vente", "vente__bijouterie", "produit", "vendor")
            .filter(vente__in=ventes_qs)
        )

        if vendor_id_int:
            ventes_qs = ventes_qs.filter(vendor_id=vendor_id_int)
            lignes_qs = lignes_qs.filter(vendor_id=vendor_id_int)
            factures_qs = factures_qs.filter(vente__vendor_id=vendor_id_int)
            paiements_qs = paiements_qs.filter(facture__vente__vendor_id=vendor_id_int)
            paiement_lignes_qs = paiement_lignes_qs.filter(
                paiement__facture__vente__vendor_id=vendor_id_int
            )

        # =========================
        # 4. KPI ventes / paiements
        # =========================
        ventes_count = ventes_qs.distinct().count()

        ventes_amount = (
            factures_qs
            .filter(status=Facture.STAT_PAYE)
            .aggregate(
                total=Coalesce(
                    Sum("montant_total"),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )
            .get("total") or Decimal("0.00")
        )

        cash_total = (
            paiement_lignes_qs
            .aggregate(
                total=Coalesce(
                    Sum("montant_paye"),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )
            .get("total") or Decimal("0.00")
        )

        unpaid_total = (
            Facture.objects
            .filter(facture_scope_q)
            .filter(
                status=Facture.STAT_NON_PAYE,
                date_creation__gte=start_dt,
                date_creation__lt=end_dt,
            )
            .aggregate(
                total=Coalesce(
                    Sum("montant_total"),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )
            .get("total") or Decimal("0.00")
        )

        avg_ticket = Decimal("0.00")
        if ventes_count > 0:
            avg_ticket = (ventes_amount / Decimal(ventes_count)).quantize(Decimal("0.01"))

        total_qty_sold = (
            lignes_qs
            .aggregate(total=Coalesce(Sum("quantite"), 0))
            .get("total") or 0
        )

        # =========================
        # 5. Paiements par mode
        # =========================
        payments_by_mode_qs = (
            paiement_lignes_qs
            .values("mode_paiement__id", "mode_paiement__nom", "mode_paiement__code")
            .annotate(
                total=Coalesce(
                    Sum("montant_paye"),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                ),
                count=Count("id"),
            )
            .order_by("mode_paiement__nom")
        )

        payments_by_mode = [
            {
                "mode_paiement_id": row["mode_paiement__id"],
                "mode_paiement": row["mode_paiement__nom"],
                "code": row["mode_paiement__code"],
                "count": int(row["count"] or 0),
                "total": float(row["total"] or 0),
            }
            for row in payments_by_mode_qs
        ]

        # =========================
        # 6. Courbe ventes
        # =========================
        trunc_map = {
            "day": TruncDay("date_creation"),
            "week": TruncWeek("date_creation"),
            "month": TruncMonth("date_creation"),
        }

        sales_over_time_qs = (
            factures_qs
            .filter(status=Facture.STAT_PAYE)
            .annotate(period=trunc_map[group_by])
            .values("period")
            .annotate(
                ventes_count=Count("id"),
                total=Coalesce(
                    Sum("montant_total"),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                ),
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

        # =========================
        # 7. Top produits
        # =========================
        top_products_qs = (
            lignes_qs
            .values(
                "produit_id",
                "produit__slug",
                "produit__sku",
                "produit__marque__nom",
                "produit__modele__nom",
                "produit__purete__nom",
            )
            .annotate(
                quantite=Coalesce(Sum("quantite"), 0),
                total_ttc=Coalesce(
                    Sum("montant_total"),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                ),
                ventes_distinctes=Count("vente_id", distinct=True),
            )
            .order_by("-total_ttc", "-quantite")[:10]
        )

        top_products = []

        for row in top_products_qs:
            produit_nom = " ".join(
                filter(
                    None,
                    [
                        row.get("produit__marque__nom"),
                        row.get("produit__modele__nom"),
                        row.get("produit__purete__nom"),
                    ],
                )
            )

            top_products.append(
                {
                    "produit_id": row["produit_id"],
                    "produit": produit_nom or row.get("produit__sku") or "Produit",
                    "slug": row.get("produit__slug"),
                    "sku": row.get("produit__sku"),
                    "quantite": int(row["quantite"] or 0),
                    "total_ttc": float(row["total_ttc"] or 0),
                    "ventes_distinctes": int(row["ventes_distinctes"] or 0),
                }
            )

        # =========================
        # 8. Stock boutique
        # =========================
        stock_qs = (
            Stock.objects
            .select_related("bijouterie", "produit_line", "produit_line__produit")
            .filter(stock_scope_q)
        )

        stock_summary = stock_qs.aggregate(
            total_alloue=Coalesce(Sum("quantite_allouee"), 0),
            total_disponible=Coalesce(Sum("quantite_disponible"), 0),
            lignes_stock=Count("id"),
        )

        reserve_qs = Stock.objects.filter(
            bijouterie__isnull=True
        )

        reserve_total = (
            reserve_qs
            .aggregate(total=Coalesce(Sum("quantite_disponible"), 0))
            .get("total") or 0
        )

        vendor_stock_qs = (
            VendorStock.objects
            .select_related("vendor", "produit_line", "produit_line__produit")
            .filter(vendor_stock_scope_q)
            .annotate(
                disponible=ExpressionWrapper(
                    Coalesce(F("quantite_allouee"), Value(0))
                    - Coalesce(F("quantite_vendue"), Value(0)),
                    output_field=IntegerField(),
                )
            )
        )

        vendor_available_total = (
            vendor_stock_qs
            .aggregate(total=Coalesce(Sum("disponible"), 0))
            .get("total") or 0
        )

        stock_by_product_qs = (
            stock_qs
            .values(
                "produit_line__produit_id",
                "produit_line__produit__slug",
                "produit_line__produit__sku",
                "produit_line__produit__marque__nom",
                "produit_line__produit__modele__nom",
                "produit_line__produit__purete__nom",
            )
            .annotate(
                total_alloue=Coalesce(Sum("quantite_allouee"), 0),
                total_disponible=Coalesce(Sum("quantite_disponible"), 0),
            )
            .order_by("-total_disponible")[:10]
        )

        stock_by_product = []

        for row in stock_by_product_qs:
            produit_nom = " ".join(
                filter(
                    None,
                    [
                        row.get("produit_line__produit__marque__nom"),
                        row.get("produit_line__produit__modele__nom"),
                        row.get("produit_line__produit__purete__nom"),
                    ],
                )
            )

            stock_by_product.append(
                {
                    "produit_id": row["produit_line__produit_id"],
                    "produit": produit_nom or row.get("produit_line__produit__sku") or "Produit",
                    "slug": row.get("produit_line__produit__slug"),
                    "sku": row.get("produit_line__produit__sku"),
                    "quantite_allouee": int(row["total_alloue"] or 0),
                    "quantite_disponible": int(row["total_disponible"] or 0),
                }
            )

        # =========================
        # 9. Réponse
        # =========================
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
                    "total_alloue": int(stock_summary.get("total_alloue") or 0),
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

### Règles métier
- Si `appliquer_tva = false`, alors `taux_tva` devient automatiquement `null`.
- Si `appliquer_tva = true`, alors `taux_tva` doit être fourni ou déjà existant.
- Le prix marque/pureté doit être supérieur à 0.
- Un manager ne peut modifier que les bijouteries qu’il gère.
        """,
        request_body=CommercialSettingsSerializer,
        responses={
            200: openapi.Response(description="Paramétrage commercial mis à jour avec succès."),
            400: openapi.Response(description="Erreur de validation ou couple marque/pureté introuvable."),
            403: openapi.Response(description="Accès refusé."),
            404: openapi.Response(description="Bijouterie introuvable."),
        },
        tags=["Paramétrage commercial"],
    )
    @transaction.atomic
    def patch(self, request, *args, **kwargs):
        serializer = CommercialSettingsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            bijouterie = Bijouterie.objects.select_for_update().get(pk=data["bijouterie_id"])
        except Bijouterie.DoesNotExist:
            return Response(
                {"detail": "Bijouterie introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        role = get_role_name(request.user)

        if role == "manager":
            manager = getattr(request.user, "staff_manager_profile", None)

            if not manager or not manager.bijouteries.filter(pk=bijouterie.pk).exists():
                return Response(
                    {"detail": "Vous ne pouvez pas modifier cette bijouterie."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        updated_prices = []

        old_appliquer_tva = bijouterie.appliquer_tva
        old_taux_tva = bijouterie.taux_tva

        # =========================
        # TVA
        # =========================
        tva_updated = False

        if "appliquer_tva" in data:
            bijouterie.appliquer_tva = data["appliquer_tva"]
            tva_updated = True

        if "taux_tva" in data:
            bijouterie.taux_tva = data["taux_tva"]
            tva_updated = True

        # Cohérence TVA
        if not bijouterie.appliquer_tva:
            bijouterie.taux_tva = None
        else:
            if bijouterie.taux_tva is None:
                return Response(
                    {"detail": "Le taux de TVA est obligatoire lorsque la TVA est activée."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if bijouterie.taux_tva < 0 or bijouterie.taux_tva > 100:
                return Response(
                    {"detail": "Le taux de TVA doit être compris entre 0 et 100."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if tva_updated:
            update_fields = ["appliquer_tva", "taux_tva"]

            if hasattr(bijouterie, "updated_at"):
                update_fields.append("updated_at")

            bijouterie.save(update_fields=update_fields)

            # Optionnel si tu as un modèle TVAHistory :
            # TVAHistory.objects.create(
            #     bijouterie=bijouterie,
            #     old_appliquer_tva=old_appliquer_tva,
            #     new_appliquer_tva=bijouterie.appliquer_tva,
            #     old_taux_tva=old_taux_tva,
            #     new_taux_tva=bijouterie.taux_tva,
            #     changed_by=request.user,
            #     source="api",
            # )

        # =========================
        # PRIX MARQUE / PURETE
        # =========================
        for item in data.get("prix_marque_purete", []):
            try:
                new_price = Decimal(str(item["prix"]))
            except (InvalidOperation, TypeError, KeyError):
                return Response(
                    {"detail": "Prix invalide."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if new_price <= 0:
                return Response(
                    {
                        "detail": (
                            f"Le prix doit être supérieur à 0 "
                            f"pour marque='{item.get('marque')}'."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

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
            
            # if self.appliquer_tva and (self.taux_tva is None or Decimal(str(self.taux_tva)) <= 0):
            #     raise ValidationError({
            #         "taux_tva": "Le taux de TVA est obligatoire lorsque la TVA est activée."
            #     })

            try:
                obj, history = update_marque_purete_price(
                    obj=obj,
                    new_price=new_price,
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

                "tva_updated": tva_updated,
                "prix_updated": len(updated_prices) > 0,

                "bijouterie": {
                    "id": bijouterie.id,
                    "nom": bijouterie.nom,
                    "appliquer_tva": bijouterie.appliquer_tva,
                    "taux_tva": (
                        str(bijouterie.taux_tva)
                        if bijouterie.taux_tva is not None
                        else None
                    ),
                },

                "prix_updates_count": len(updated_prices),
                "prix_updates": updated_prices,
            },
            status=status.HTTP_200_OK,
        )
        
        


