# inventory/views.py
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Set

from django.core.exceptions import ValidationError
from django.db.models import (Case, Count, DecimalField, ExpressionWrapper, F,
                              Prefetch, Q, Sum, Value, When)
from django.db.models.functions import Coalesce
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from openpyxl import Workbook
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.mixins import (GROUP_BY_CHOICES, ExportXlsxMixin,
                            aware_range_month, parse_month_or_default,
                            resolve_tz)
from backend.permissions import IsAdminOrManager
from backend.roles import ROLE_ADMIN, ROLE_MANAGER, get_role_name
from inventory.models import InventoryMovement, MovementType
from purchase.models import ProduitLine
from stock.models import VendorStock
from store.models import Bijouterie
from vendor.models import Vendor

from .serializers import (InventoryBijouterieSerializer,
                          InventoryVendorSerializer,
                          ProduitLineWithInventorySerializer)
from .utils import _b
from .utils import parse_date as _date
from .utils import parse_int as _int

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

# ---------------------------------------------------------------------
# InventoryMovementListView
# ---------------------------------------------------------------------
class InventoryMovementListView(ExportXlsxMixin, APIView):
    """
    Journal détaillé des mouvements d’inventaire (Admin/Manager).

    - Admin   : voit tout + peut filtrer sur n'importe quelle bijouterie via ?bijouterie_id=
    - Manager : limité aux bijouteries de son profil manager (ManyToMany)
    - Export Excel : ?export=xlsx
    - Pagination simple : ?limit=200&offset=0
    """
    permission_classes = [IsAuthenticated]
    http_method_names = ["get"]

    @swagger_auto_schema(
        operation_id="inventoryMovementList",
        operation_summary="Lister les mouvements d’inventaire (Admin/Manager) + export Excel",
        operation_description=(
            "Journal détaillé des mouvements d’inventaire.\n\n"
            "### Scopes\n"
            "- **admin** : voit tout (et peut filtrer une bijouterie via `bijouterie_id`)\n"
            "- **manager** : voit uniquement les mouvements où `src_bijouterie` ou `dst_bijouterie` "
            "appartient à **ses bijouteries (ManyToMany)**\n\n"
            "### Filtres\n"
            "- `q` : recherche (produit.nom, produit.sku, reason, lot.numero_lot)\n"
            "- `date_from`, `date_to` : YYYY-MM-DD (inclusifs)\n"
            "- `movement_types` : CSV ex `PURCHASE_IN,ALLOCATE,SALE_OUT`\n"
            "- `produit_id`, `lot_id`, `lot_code`, `achat_id`\n"
            "- `vendor_id`, `vente_id`, `facture_id`\n"
            "- `src_bucket`, `dst_bucket`\n"
            "- `bijouterie_id` : **admin seulement** (scope)\n"
            "- `src_bijouterie_id`, `dst_bijouterie_id`\n"
            "- `min_qty`, `max_qty`\n\n"
            "### Options\n"
            "- `include_costs=1` : calcule `total_cost = signed_qty * unit_cost`\n"
            "- `ordering` : `-occurred_at` (def), `occurred_at`, `qty`, `-qty`, "
            "`produit_nom`, `-produit_nom`, `movement_type`, `-movement_type`\n"
            "- `export=xlsx` : export Excel\n"
            "- `limit`, `offset` : pagination simple\n"
        ),
        manual_parameters=[
            openapi.Parameter("q", openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter("date_from", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="YYYY-MM-DD"),
            openapi.Parameter("date_to", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="YYYY-MM-DD"),
            openapi.Parameter("movement_types", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="CSV"),
            openapi.Parameter("produit_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter("lot_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter("lot_code", openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter("achat_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter("vendor_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter("vente_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter("facture_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter("src_bucket", openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter("dst_bucket", openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter("bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Admin seulement"),
            openapi.Parameter("src_bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter("dst_bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter("min_qty", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter("max_qty", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter("include_costs", openapi.IN_QUERY, type=openapi.TYPE_BOOLEAN),
            openapi.Parameter("ordering", openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter("export", openapi.IN_QUERY, type=openapi.TYPE_STRING, enum=["xlsx"]),
            openapi.Parameter("limit", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="def 200, max 2000"),
            openapi.Parameter("offset", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="def 0"),
        ],
        tags=["Inventaire"],
        responses={
            200: openapi.Response(description="OK"),
            400: openapi.Response(description="Bad Request"),
            403: openapi.Response(description="Forbidden"),
        },
    )
    def get(self, request):
        getf = request.GET.get
        role = get_role_name(request.user)

        if role not in {ROLE_ADMIN, ROLE_MANAGER}:
            return Response({"detail": "Accès réservé aux admins et managers."}, status=403)

        qs = (
            InventoryMovement.objects
            .select_related(
                "produit",
                "lot",
                "src_bijouterie",
                "dst_bijouterie",
                "created_by",
                "vendor",
                "vendor__user",
                "vente",
                "facture",
            )
            .all()
        )

        # ---------------------------
        # Scope bijouterie
        # ---------------------------
        if role == ROLE_ADMIN:
            bj_id = _int(getf("bijouterie_id"))
            if bj_id:
                qs = qs.filter(Q(src_bijouterie_id=bj_id) | Q(dst_bijouterie_id=bj_id))
        else:
            mp = getattr(request.user, "staff_manager_profile", None)
            if not mp or (hasattr(mp, "verifie") and not mp.verifie):
                return Response({"detail": "Profil manager invalide."}, status=403)

            ids = list(mp.bijouteries.values_list("id", flat=True))
            if not ids:
                return Response({"detail": "Ce manager n'a aucune bijouterie assignée."}, status=400)

            qs = qs.filter(Q(src_bijouterie_id__in=ids) | Q(dst_bijouterie_id__in=ids))

        # ---------------------------
        # Recherche
        # ---------------------------
        q = (getf("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(produit__nom__icontains=q) |
                Q(produit__sku__icontains=q) |
                Q(reason__icontains=q) |
                Q(lot__numero_lot__icontains=q)
            )

        # ---------------------------
        # Filtres simples
        # ---------------------------
        produit_id = _int(getf("produit_id"))
        if produit_id:
            qs = qs.filter(produit_id=produit_id)

        lot_id = _int(getf("lot_id"))
        if lot_id:
            qs = qs.filter(lot_id=lot_id)

        lot_code = (getf("lot_code") or "").strip()
        if lot_code:
            qs = qs.filter(lot__numero_lot__iexact=lot_code)

        achat_id = _int(getf("achat_id"))
        if achat_id:
            qs = qs.filter(achat_id=achat_id)

        vendor_id = _int(getf("vendor_id"))
        if vendor_id:
            qs = qs.filter(vendor_id=vendor_id)

        vente_id = _int(getf("vente_id"))
        if vente_id:
            qs = qs.filter(vente_id=vente_id)

        facture_id = _int(getf("facture_id"))
        if facture_id:
            qs = qs.filter(facture_id=facture_id)

        src_bucket = (getf("src_bucket") or "").strip()
        if src_bucket:
            qs = qs.filter(src_bucket=src_bucket)

        dst_bucket = (getf("dst_bucket") or "").strip()
        if dst_bucket:
            qs = qs.filter(dst_bucket=dst_bucket)

        src_bij = _int(getf("src_bijouterie_id"))
        if src_bij:
            qs = qs.filter(src_bijouterie_id=src_bij)

        dst_bij = _int(getf("dst_bijouterie_id"))
        if dst_bij:
            qs = qs.filter(dst_bijouterie_id=dst_bij)

        # ---------------------------
        # Movement types
        # ---------------------------
        types_csv = (getf("movement_types") or "").strip()
        if types_csv:
            types = [t.strip().upper() for t in types_csv.split(",") if t.strip()]
            allowed_types = {c[0] for c in MovementType.choices}
            bad = [t for t in types if t not in allowed_types]
            if bad:
                return Response(
                    {"detail": f"movement_types invalide(s): {bad}. Allowed: {sorted(allowed_types)}"},
                    status=400,
                )
            qs = qs.filter(movement_type__in=types)

        # ---------------------------
        # Dates
        # ---------------------------
        df_raw = getf("date_from")
        dt_raw = getf("date_to")
        df = _date(df_raw)
        dt = _date(dt_raw)

        if df_raw and not df:
            return Response({"date_from": "Format invalide. Utiliser YYYY-MM-DD."}, status=400)
        if dt_raw and not dt:
            return Response({"date_to": "Format invalide. Utiliser YYYY-MM-DD."}, status=400)
        if df and dt and df > dt:
            return Response({"detail": "date_from doit être ≤ date_to."}, status=400)

        if df:
            qs = qs.filter(occurred_at__date__gte=df)
        if dt:
            qs = qs.filter(occurred_at__date__lte=dt)

        # ---------------------------
        # Qty range
        # ---------------------------
        min_qty = _int(getf("min_qty"))
        max_qty = _int(getf("max_qty"))
        if min_qty is not None:
            qs = qs.filter(qty__gte=min_qty)
        if max_qty is not None:
            qs = qs.filter(qty__lte=max_qty)

        # ---------------------------
        # Annotations
        # ---------------------------
        include_costs = _b(getf("include_costs"), False)

        sign = Case(
            When(movement_type__in=[MovementType.SALE_OUT, MovementType.CANCEL_PURCHASE], then=Value(-1)),
            default=Value(1),
            output_field=DecimalField(max_digits=4, decimal_places=0),
        )

        qs = qs.annotate(
            signed_qty=ExpressionWrapper(
                F("qty") * sign,
                output_field=DecimalField(max_digits=18, decimal_places=2),
            )
        )

        if include_costs:
            qs = qs.annotate(
                total_cost=ExpressionWrapper(
                    F("signed_qty") * Coalesce(F("unit_cost"), Value(Decimal("0.00"))),
                    output_field=DecimalField(max_digits=20, decimal_places=2),
                )
            )

        # ---------------------------
        # Ordering
        # ---------------------------
        ordering = (getf("ordering") or "-occurred_at").strip()
        allowed_ordering = {
            "occurred_at", "-occurred_at",
            "qty", "-qty",
            "movement_type", "-movement_type",
            "produit_nom", "-produit_nom",
        }
        if ordering not in allowed_ordering:
            ordering = "-occurred_at"
        if "produit_nom" in ordering:
            ordering = ordering.replace("produit_nom", "produit__nom")
        qs = qs.order_by(ordering)

        # ---------------------------
        # Export Excel
        # ---------------------------
        if (getf("export") or "").lower() == "xlsx":
            values_fields = [
                "id", "occurred_at", "movement_type",
                "produit_id", "produit__nom", "produit__sku",
                "lot_id", "lot__numero_lot",
                "qty", "signed_qty",
                "unit_cost",
                "achat_id",
                "vendor_id", "vendor__user__email",
                "vente_id", "vente__numero_vente",
                "facture_id", "facture__numero_facture",
                "src_bucket", "src_bijouterie_id",
                "dst_bucket", "dst_bijouterie_id",
                "created_by_id",
                "reason",
            ]
            if include_costs:
                values_fields.insert(values_fields.index("unit_cost") + 1, "total_cost")

            rows = list(qs.values(*values_fields))

            bij_ids: Set[int] = set()
            for r in rows:
                if r.get("src_bijouterie_id"):
                    bij_ids.add(r["src_bijouterie_id"])
                if r.get("dst_bijouterie_id"):
                    bij_ids.add(r["dst_bijouterie_id"])
            bij_map = {b.id: b.nom for b in Bijouterie.objects.filter(id__in=bij_ids)} if bij_ids else {}

            wb = Workbook()
            ws = wb.active
            ws.title = "Mouvements"

            headers = [
                "id", "occurred_at", "movement_type",
                "produit_id", "produit_nom", "produit_sku",
                "lot_id", "lot_code",
                "qty", "signed_qty",
                "unit_cost",
                "total_cost" if include_costs else None,
                "achat_id",
                "vendor_id", "vendor_email",
                "vente_id", "numero_vente",
                "facture_id", "numero_facture",
                "src_bucket", "src_bijouterie_id", "src_bijouterie_nom",
                "dst_bucket", "dst_bijouterie_id", "dst_bijouterie_nom",
                "created_by_id",
                "reason",
            ]
            headers = [h for h in headers if h is not None]
            ws.append(headers)

            for r in rows:
                line = {
                    "id": r.get("id"),
                    "occurred_at": r.get("occurred_at"),
                    "movement_type": r.get("movement_type"),
                    "produit_id": r.get("produit_id"),
                    "produit_nom": r.get("produit__nom"),
                    "produit_sku": r.get("produit__sku"),
                    "lot_id": r.get("lot_id"),
                    "lot_code": r.get("lot__numero_lot"),
                    "qty": r.get("qty"),
                    "signed_qty": r.get("signed_qty"),
                    "unit_cost": r.get("unit_cost"),
                    "total_cost": r.get("total_cost") if include_costs else None,
                    "achat_id": r.get("achat_id"),
                    "vendor_id": r.get("vendor_id"),
                    "vendor_email": r.get("vendor__user__email"),
                    "vente_id": r.get("vente_id"),
                    "numero_vente": r.get("vente__numero_vente"),
                    "facture_id": r.get("facture_id"),
                    "numero_facture": r.get("facture__numero_facture"),
                    "src_bucket": r.get("src_bucket"),
                    "src_bijouterie_id": r.get("src_bijouterie_id"),
                    "src_bijouterie_nom": bij_map.get(r.get("src_bijouterie_id")),
                    "dst_bucket": r.get("dst_bucket"),
                    "dst_bijouterie_id": r.get("dst_bijouterie_id"),
                    "dst_bijouterie_nom": bij_map.get(r.get("dst_bijouterie_id")),
                    "created_by_id": r.get("created_by_id"),
                    "reason": r.get("reason"),
                }
                ws.append([line.get(h) for h in headers])

            self._autosize(ws)
            return self._xlsx_response(wb, "inventory_movements.xlsx")

        # ---------------------------
        # Pagination simple
        # ---------------------------
        limit = _int(getf("limit")) or 200
        offset = _int(getf("offset")) or 0

        if limit < 1:
            limit = 200
        if limit > 2000:
            limit = 2000
        if offset < 0:
            offset = 0

        total = qs.count()
        page_qs = qs[offset: offset + limit]

        values_fields = [
            "id", "occurred_at", "movement_type",
            "qty", "signed_qty",
            "unit_cost",
            "produit_id", "produit__nom", "produit__sku",
            "lot_id", "lot__numero_lot",
            "achat_id",
            "vendor_id", "vendor__user__email",
            "vente_id", "vente__numero_vente",
            "facture_id", "facture__numero_facture",
            "src_bucket", "src_bijouterie_id",
            "dst_bucket", "dst_bijouterie_id",
            "created_by_id",
            "reason",
        ]
        if include_costs:
            values_fields.insert(values_fields.index("unit_cost") + 1, "total_cost")

        rows = list(page_qs.values(*values_fields))

        bij_ids: Set[int] = set()
        for r in rows:
            if r.get("src_bijouterie_id"):
                bij_ids.add(r["src_bijouterie_id"])
            if r.get("dst_bijouterie_id"):
                bij_ids.add(r["dst_bijouterie_id"])
        bij_map = {b.id: b.nom for b in Bijouterie.objects.filter(id__in=bij_ids)} if bij_ids else {}

        out = []
        for r in rows:
            out.append({
                "id": r.get("id"),
                "occurred_at": r.get("occurred_at"),
                "movement_type": r.get("movement_type"),
                "produit_id": r.get("produit_id"),
                "produit_nom": r.get("produit__nom"),
                "produit_sku": r.get("produit__sku"),
                "lot_id": r.get("lot_id"),
                "lot_code": r.get("lot__numero_lot"),
                "achat_id": r.get("achat_id"),
                "qty": r.get("qty"),
                "signed_qty": r.get("signed_qty"),
                "unit_cost": r.get("unit_cost"),
                "total_cost": r.get("total_cost") if include_costs else None,
                "vendor_id": r.get("vendor_id"),
                "vendor_email": r.get("vendor__user__email"),
                "vente_id": r.get("vente_id"),
                "numero_vente": r.get("vente__numero_vente"),
                "facture_id": r.get("facture_id"),
                "numero_facture": r.get("facture__numero_facture"),
                "src_bucket": r.get("src_bucket"),
                "src_bijouterie_id": r.get("src_bijouterie_id"),
                "src_bijouterie_nom": bij_map.get(r.get("src_bijouterie_id")),
                "dst_bucket": r.get("dst_bucket"),
                "dst_bijouterie_id": r.get("dst_bijouterie_id"),
                "dst_bijouterie_nom": bij_map.get(r.get("dst_bijouterie_id")),
                "created_by_id": r.get("created_by_id"),
                "reason": r.get("reason"),
            })

        next_offset = offset + limit
        return Response({
            "count": total,
            "limit": limit,
            "offset": offset,
            "next_offset": next_offset if next_offset < total else None,
            "results": out,
        }, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------
# ProduitLineWithInventoryListView
# ---------------------------------------------------------------------
class ProduitLineWithInventoryListView(ListAPIView):
    """
    GET /api/inventory/produit-lines/

    Liste des ProduitLine (par lot + produit) avec :
    - infos lot/achat/produit
    - agrégats stock (quantite_allouee, quantite_disponible_total)
    - mouvements d'inventaire liés à chaque ProduitLine
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    serializer_class = ProduitLineWithInventorySerializer
    pagination_class = None

    @swagger_auto_schema(
        operation_id="listProduitLinesWithInventory",
        operation_summary="Lister les ProduitLine avec stock + mouvements (par ligne)",
        operation_description=(
            "Retourne les **ProduitLine** (par lot) avec :\n"
            "- **agrégats stock** : `quantite_allouee`, `quantite_disponible_total`\n"
            "- **mouvements** : préchargés via `prefetched_movements`\n\n"
            "### Accès\n"
            "- **admin / manager** uniquement\n\n"
            "### Filtres\n"
            "- `year` : année des lots (`received_at__year`), défaut = année courante\n"
            "- `lot_id`, `produit_id`, `numero_lot`\n"
        ),
        tags=["Inventaire"],
        manual_parameters=[
            openapi.Parameter(
                "year",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="Année (ex: 2026). Défaut: année courante.",
            ),
            openapi.Parameter(
                "lot_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="Filtrer par ID du lot.",
            ),
            openapi.Parameter(
                "produit_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="Filtrer par ID du produit.",
            ),
            openapi.Parameter(
                "numero_lot",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
                description="Recherche partielle sur le numéro de lot.",
            ),
        ],
        responses={
            200: openapi.Response(
                description="Liste des ProduitLine avec inventaire",
                schema=ProduitLineWithInventorySerializer(many=True),
            ),
            400: openapi.Response(description="Paramètres invalides"),
            403: openapi.Response(description="Accès refusé"),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def _int_or_none(self, v, field_name: str):
        if v in (None, "", "null"):
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            raise ValidationError({field_name: "Doit être un entier."})

    def get_queryset(self):
        getf = self.request.query_params.get

        year_raw = getf("year")
        if year_raw in (None, "", "null"):
            year = timezone.localdate().year
        else:
            year = self._int_or_none(year_raw, "year")
            if not year:
                year = timezone.localdate().year
            if year < 2000 or year > 2100:
                raise ValidationError({"year": "Année invalide (2000-2100)."})

        pl_moves_qs = (
            InventoryMovement.objects
            .select_related("src_bijouterie", "dst_bijouterie", "vendor", "facture", "vente")
            .order_by("-occurred_at", "-id")
        )

        qs = (
            ProduitLine.objects
            .select_related(
                "lot",
                "lot__achat",
                "lot__achat__fournisseur",
                "produit",
                "produit__categorie",
                "produit__marque",
                "produit__purete",
            )
            .prefetch_related(
                Prefetch(
                    "inventory_movements",
                    queryset=pl_moves_qs,
                    to_attr="prefetched_movements",
                )
            )
            .annotate(
                quantite_allouee=Coalesce(Sum("stocks__quantite_allouee"), 0),
                quantite_disponible_total=Coalesce(Sum("stocks__quantite_disponible"), 0),
            )
            .filter(lot__received_at__year=year)
        )

        lot_id = self._int_or_none(getf("lot_id"), "lot_id")
        if lot_id:
            qs = qs.filter(lot_id=lot_id)

        produit_id = self._int_or_none(getf("produit_id"), "produit_id")
        if produit_id:
            qs = qs.filter(produit_id=produit_id)

        numero_lot = (getf("numero_lot") or "").strip()
        if numero_lot:
            qs = qs.filter(lot__numero_lot__icontains=numero_lot)

        return qs.order_by("-lot__received_at", "lot__numero_lot", "id")








class InventoryBijouterieView(ExportXlsxMixin, APIView):
    """
    Résumé des entrées / sorties de stock par bijouterie.
    """
    permission_classes = [IsAuthenticated]
    http_method_names = ["get"]

    @swagger_auto_schema(
        operation_id="inventoryBijouterie",
        operation_summary="Résumé des entrées et sorties de stock par bijouterie",
        operation_description=(
            "Retourne un **résumé global des mouvements de stock par bijouterie**.\n\n"
            "Cette vue permet de connaître, pour chaque bijouterie :\n"
            "- les **entrées d'achat** (`purchase_in`)\n"
            "- les **annulations d'achat** (`cancel_purchase_out`)\n"
            "- les **affectations reçues depuis la réserve** (`allocate_in`)\n"
            "- les **transferts entrants** (`transfer_in`)\n"
            "- les **transferts sortants** (`transfer_out`)\n"
            "- les **sorties de vente** (`sale_out`)\n"
            "- les **retours clients** (`return_in`)\n"
            "- les **ajustements positifs** (`adjustment_in`)\n"
            "- les **ajustements négatifs** (`adjustment_out`)\n"
            "- le **solde net des mouvements** (`stock_net`)\n\n"
            "### Règles d'accès\n"
            "- **Admin** : peut voir toutes les bijouteries\n"
            "- **Manager** : ne voit que les bijouteries qui lui sont assignées\n\n"
            "### Filtres disponibles\n"
            "- `bijouterie_id` : limiter le résumé à une seule bijouterie\n"
            "- `produit_id` : limiter le résumé à un produit précis\n"
            "- `date_from` : date de début incluse (`YYYY-MM-DD`)\n"
            "- `date_to` : date de fin incluse (`YYYY-MM-DD`)\n"
            "- `export=xlsx` : exporter le résumé au format Excel\n\n"
            "### Notes métier\n"
            "- `stock_net` est un **solde de mouvements**, pas une photo instantanée du stock physique.\n"
            "- Pour voir l'état actuel du stock par lot/produit, utilise la vue d'**inventaire photo**.\n"
        ),
        manual_parameters=[
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="ID d'une bijouterie pour limiter le résumé à cette bijouterie uniquement.",
            ),
            openapi.Parameter(
                "produit_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="ID d'un produit pour limiter le résumé à ce produit.",
            ),
            openapi.Parameter(
                "date_from",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
                required=False,
                description="Date de début incluse au format YYYY-MM-DD.",
            ),
            openapi.Parameter(
                "date_to",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
                required=False,
                description="Date de fin incluse au format YYYY-MM-DD.",
            ),
            openapi.Parameter(
                "export",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
                enum=["xlsx"],
                description="Mettre `xlsx` pour exporter le résumé en fichier Excel.",
            ),
        ],
        responses={
            200: openapi.Response(
                description="Résumé des mouvements de stock par bijouterie.",
                schema=InventoryBijouterieSerializer(many=True),
                examples={
                    "application/json": [
                        {
                            "bijouterie_id": 1,
                            "bijouterie_nom": "Rio Gold Dakar",
                            "purchase_in": "120.00",
                            "cancel_purchase_out": "5.00",
                            "allocate_in": "20.00",
                            "transfer_in": "8.00",
                            "transfer_out": "3.00",
                            "sale_out": "42.00",
                            "return_in": "2.00",
                            "adjustment_in": "1.00",
                            "adjustment_out": "0.00",
                            "stock_net": "101.00",
                        }
                    ]
                },
            ),
            400: openapi.Response(
                description="Paramètres invalides.",
                examples={
                    "application/json": {
                        "date_from": "Format invalide. Utiliser YYYY-MM-DD."
                    }
                },
            ),
            403: openapi.Response(
                description="Accès refusé.",
                examples={
                    "application/json": {
                        "detail": "Accès refusé."
                    }
                },
            ),
        },
        tags=["Inventaire / Résumés"],
    )
    def get(self, request):
        role = get_role_name(request.user)
        if role not in {ROLE_ADMIN, ROLE_MANAGER}:
            return Response({"detail": "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        getf = request.GET.get
        bijouterie_id = _int(getf("bijouterie_id"))
        produit_id = _int(getf("produit_id"))
        date_from = _date(getf("date_from"))
        date_to = _date(getf("date_to"))

        if getf("date_from") and not date_from:
            return Response(
                {"date_from": "Format invalide. Utiliser YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if getf("date_to") and not date_to:
            return Response(
                {"date_to": "Format invalide. Utiliser YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if date_from and date_to and date_from > date_to:
            return Response(
                {"detail": "date_from doit être <= date_to."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qs = InventoryMovement.objects.select_related(
            "src_bijouterie",
            "dst_bijouterie",
            "produit",
        )

        allowed_ids = None
        if role == ROLE_MANAGER:
            mp = getattr(request.user, "staff_manager_profile", None)
            if not mp or (hasattr(mp, "verifie") and not mp.verifie):
                return Response(
                    {"detail": "Profil manager invalide."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            allowed_ids = list(mp.bijouteries.values_list("id", flat=True))
            if not allowed_ids:
                return Response(
                    {"detail": "Ce manager n'a aucune bijouterie assignée."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            qs = qs.filter(
                Q(src_bijouterie_id__in=allowed_ids) |
                Q(dst_bijouterie_id__in=allowed_ids)
            )

        if bijouterie_id:
            qs = qs.filter(
                Q(src_bijouterie_id=bijouterie_id) |
                Q(dst_bijouterie_id=bijouterie_id)
            )

        if produit_id:
            qs = qs.filter(produit_id=produit_id)

        if date_from:
            qs = qs.filter(occurred_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(occurred_at__date__lte=date_to)

        bijouteries = Bijouterie.objects.all()
        if role == ROLE_MANAGER and allowed_ids is not None:
            bijouteries = bijouteries.filter(id__in=allowed_ids)
        if bijouterie_id:
            bijouteries = bijouteries.filter(id=bijouterie_id)

        rows = []
        for bj in bijouteries.order_by("nom"):
            in_qs = qs.filter(dst_bijouterie_id=bj.id)
            out_qs = qs.filter(src_bijouterie_id=bj.id)

            purchase_in = in_qs.filter(
                movement_type=MovementType.PURCHASE_IN
            ).aggregate(
                v=Coalesce(
                    Sum("qty"),
                    Value(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )["v"]

            cancel_purchase_out = out_qs.filter(
                movement_type=MovementType.CANCEL_PURCHASE
            ).aggregate(
                v=Coalesce(
                    Sum("qty"),
                    Value(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )["v"]

            allocate_in = in_qs.filter(
                movement_type=MovementType.ALLOCATE
            ).aggregate(
                v=Coalesce(
                    Sum("qty"),
                    Value(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )["v"]

            transfer_in = in_qs.filter(
                movement_type=MovementType.TRANSFER
            ).aggregate(
                v=Coalesce(
                    Sum("qty"),
                    Value(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )["v"]

            transfer_out = out_qs.filter(
                movement_type=MovementType.TRANSFER
            ).aggregate(
                v=Coalesce(
                    Sum("qty"),
                    Value(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )["v"]

            sale_out = out_qs.filter(
                movement_type=MovementType.SALE_OUT
            ).aggregate(
                v=Coalesce(
                    Sum("qty"),
                    Value(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )["v"]

            return_in = in_qs.filter(
                movement_type=MovementType.RETURN_IN
            ).aggregate(
                v=Coalesce(
                    Sum("qty"),
                    Value(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )["v"]

            adjustment_in = in_qs.filter(
                movement_type=MovementType.ADJUSTMENT
            ).aggregate(
                v=Coalesce(
                    Sum("qty"),
                    Value(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )["v"]

            adjustment_out = out_qs.filter(
                movement_type=MovementType.ADJUSTMENT
            ).aggregate(
                v=Coalesce(
                    Sum("qty"),
                    Value(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )["v"]

            stock_net = (
                purchase_in
                + allocate_in
                + transfer_in
                + return_in
                + adjustment_in
                - cancel_purchase_out
                - transfer_out
                - sale_out
                - adjustment_out
            )

            rows.append({
                "bijouterie_id": bj.id,
                "bijouterie_nom": bj.nom,
                "purchase_in": purchase_in,
                "cancel_purchase_out": cancel_purchase_out,
                "allocate_in": allocate_in,
                "transfer_in": transfer_in,
                "transfer_out": transfer_out,
                "sale_out": sale_out,
                "return_in": return_in,
                "adjustment_in": adjustment_in,
                "adjustment_out": adjustment_out,
                "stock_net": stock_net,
            })

        if (getf("export") or "").lower() == "xlsx":
            wb = Workbook()
            ws = wb.active
            ws.title = "Résumé bijouteries"

            headers = [
                "bijouterie_id",
                "bijouterie_nom",
                "purchase_in",
                "cancel_purchase_out",
                "allocate_in",
                "transfer_in",
                "transfer_out",
                "sale_out",
                "return_in",
                "adjustment_in",
                "adjustment_out",
                "stock_net",
            ]
            ws.append(headers)

            for row in rows:
                ws.append([row.get(h) for h in headers])

            self._autosize(ws)
            return self._xlsx_response(wb, "inventory_bijouterie.xlsx")

        serializer = InventoryBijouterieSerializer(rows, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class InventoryVendorView(ExportXlsxMixin, APIView):
    """
    Résumé du stock et des mouvements par vendeur.
    """
    permission_classes = [IsAuthenticated]
    http_method_names = ["get"]

    @swagger_auto_schema(
        operation_id="inventoryVendor",
        operation_summary="Résumé du stock par vendeur",
        operation_description=(
            "Retourne un **résumé du stock et des mouvements par vendeur**.\n\n"
            "Cette vue permet de connaître, pour chaque vendeur :\n"
            "- le **stock affecté reçu** (`vendor_assign_in`)\n"
            "- les **sorties de vente du vendeur** (`sale_out_vendor`)\n"
            "- les **retours/restaurations éventuels** (`return_in_vendor`)\n"
            "- le **stock restant vendeur** (`stock_restant`)\n\n"
            "### Règles d'accès\n"
            "- **Admin** : peut voir tous les vendeurs\n"
            "- **Manager** : ne voit que les vendeurs de ses bijouteries\n\n"
            "### Filtres disponibles\n"
            "- `vendor_id` : limiter à un vendeur précis\n"
            "- `bijouterie_id` : limiter aux vendeurs d'une bijouterie\n"
            "- `produit_id` : limiter à un produit précis\n"
            "- `date_from` : date de début incluse (`YYYY-MM-DD`)\n"
            "- `date_to` : date de fin incluse (`YYYY-MM-DD`)\n"
            "- `export=xlsx` : exporter le résumé en Excel\n\n"
            "### Notes métier\n"
            "- `vendor_assign_in` correspond aux mouvements `VENDOR_ASSIGN` liés au vendeur.\n"
            "- `sale_out_vendor` correspond aux mouvements `SALE_OUT` liés au vendeur.\n"
            "- `stock_restant` est calculé depuis `VendorStock` : `quantite_allouee - quantite_vendue`.\n"
        ),
        manual_parameters=[
            openapi.Parameter(
                "vendor_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="ID d'un vendeur pour limiter le résumé à ce vendeur uniquement.",
            ),
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="ID d'une bijouterie pour limiter aux vendeurs de cette bijouterie.",
            ),
            openapi.Parameter(
                "produit_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="ID d'un produit pour limiter le résumé à ce produit.",
            ),
            openapi.Parameter(
                "date_from",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
                required=False,
                description="Date de début incluse au format YYYY-MM-DD.",
            ),
            openapi.Parameter(
                "date_to",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
                required=False,
                description="Date de fin incluse au format YYYY-MM-DD.",
            ),
            openapi.Parameter(
                "export",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
                enum=["xlsx"],
                description="Mettre `xlsx` pour exporter le résumé vendeur en fichier Excel.",
            ),
        ],
        responses={
            200: openapi.Response(
                description="Résumé du stock par vendeur.",
                schema=InventoryVendorSerializer(many=True),
                examples={
                    "application/json": [
                        {
                            "vendor_id": 3,
                            "vendor_nom": "Amadou Diop",
                            "vendor_email": "amadou@riogold.sn",
                            "bijouterie_id": 1,
                            "bijouterie_nom": "Rio Gold Dakar",
                            "vendor_assign_in": "80.00",
                            "sale_out_vendor": "25.00",
                            "return_in_vendor": "2.00",
                            "stock_restant": "57.00",
                        }
                    ]
                },
            ),
            400: openapi.Response(
                description="Paramètres invalides.",
                examples={
                    "application/json": {
                        "vendor_id": "Doit être un entier."
                    }
                },
            ),
            403: openapi.Response(
                description="Accès refusé.",
                examples={
                    "application/json": {
                        "detail": "Accès refusé."
                    }
                },
            ),
        },
        tags=["Inventaire / Résumés"],
    )
    def get(self, request):
        role = get_role_name(request.user)
        if role not in {ROLE_ADMIN, ROLE_MANAGER}:
            return Response({"detail": "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        getf = request.GET.get
        vendor_id = _int(getf("vendor_id"))
        bijouterie_id = _int(getf("bijouterie_id"))
        produit_id = _int(getf("produit_id"))
        date_from = _date(getf("date_from"))
        date_to = _date(getf("date_to"))

        if getf("date_from") and not date_from:
            return Response(
                {"date_from": "Format invalide. Utiliser YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if getf("date_to") and not date_to:
            return Response(
                {"date_to": "Format invalide. Utiliser YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if date_from and date_to and date_from > date_to:
            return Response(
                {"detail": "date_from doit être <= date_to."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vendors = Vendor.objects.select_related("user", "bijouterie").all()

        allowed_ids = None
        if role == ROLE_MANAGER:
            mp = getattr(request.user, "staff_manager_profile", None)
            if not mp or (hasattr(mp, "verifie") and not mp.verifie):
                return Response(
                    {"detail": "Profil manager invalide."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            allowed_ids = list(mp.bijouteries.values_list("id", flat=True))
            if not allowed_ids:
                return Response(
                    {"detail": "Ce manager n'a aucune bijouterie assignée."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            vendors = vendors.filter(bijouterie_id__in=allowed_ids)

        if vendor_id:
            vendors = vendors.filter(id=vendor_id)

        if bijouterie_id:
            vendors = vendors.filter(bijouterie_id=bijouterie_id)

        move_qs = InventoryMovement.objects.select_related(
            "vendor",
            "vendor__user",
            "vendor__bijouterie",
            "produit",
        )
        stock_qs = VendorStock.objects.select_related(
            "vendor",
            "vendor__user",
            "vendor__bijouterie",
            "produit_line",
            "produit_line__produit",
        )

        if role == ROLE_MANAGER and allowed_ids is not None:
            move_qs = move_qs.filter(vendor__bijouterie_id__in=allowed_ids)
            stock_qs = stock_qs.filter(vendor__bijouterie_id__in=allowed_ids)

        if vendor_id:
            move_qs = move_qs.filter(vendor_id=vendor_id)
            stock_qs = stock_qs.filter(vendor_id=vendor_id)

        if bijouterie_id:
            move_qs = move_qs.filter(vendor__bijouterie_id=bijouterie_id)
            stock_qs = stock_qs.filter(vendor__bijouterie_id=bijouterie_id)

        if produit_id:
            move_qs = move_qs.filter(produit_id=produit_id)
            stock_qs = stock_qs.filter(produit_line__produit_id=produit_id)

        if date_from:
            move_qs = move_qs.filter(occurred_at__date__gte=date_from)
        if date_to:
            move_qs = move_qs.filter(occurred_at__date__lte=date_to)

        rows = []
        for v in vendors.order_by("id"):
            vendor_assign_in = move_qs.filter(
                vendor_id=v.id,
                movement_type=MovementType.VENDOR_ASSIGN,
            ).aggregate(
                s=Coalesce(
                    Sum("qty"),
                    Value(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )["s"]

            sale_out_vendor = move_qs.filter(
                vendor_id=v.id,
                movement_type=MovementType.SALE_OUT,
            ).aggregate(
                s=Coalesce(
                    Sum("qty"),
                    Value(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )["s"]

            return_in_vendor = move_qs.filter(
                vendor_id=v.id,
                movement_type=MovementType.RETURN_IN,
            ).aggregate(
                s=Coalesce(
                    Sum("qty"),
                    Value(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )["s"]

            stock_restant = stock_qs.filter(
                vendor_id=v.id
            ).aggregate(
                s=Coalesce(
                    Sum(
                        ExpressionWrapper(
                            F("quantite_allouee") - F("quantite_vendue"),
                            output_field=DecimalField(max_digits=18, decimal_places=2),
                        )
                    ),
                    Value(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )["s"]

            full_name = ""
            if getattr(v, "user", None):
                full_name = f"{(v.user.first_name or '').strip()} {(v.user.last_name or '').strip()}".strip()

            rows.append({
                "vendor_id": v.id,
                "vendor_nom": full_name or getattr(v, "nom", "") or "",
                "vendor_email": getattr(getattr(v, "user", None), "email", None),
                "bijouterie_id": getattr(v, "bijouterie_id", None),
                "bijouterie_nom": getattr(getattr(v, "bijouterie", None), "nom", None),
                "vendor_assign_in": vendor_assign_in,
                "sale_out_vendor": sale_out_vendor,
                "return_in_vendor": return_in_vendor,
                "stock_restant": stock_restant,
            })

        if (getf("export") or "").lower() == "xlsx":
            wb = Workbook()
            ws = wb.active
            ws.title = "Résumé vendeurs"

            headers = [
                "vendor_id",
                "vendor_nom",
                "vendor_email",
                "bijouterie_id",
                "bijouterie_nom",
                "vendor_assign_in",
                "sale_out_vendor",
                "return_in_vendor",
                "stock_restant",
            ]
            ws.append(headers)

            for row in rows:
                ws.append([row.get(h) for h in headers])

            self._autosize(ws)
            return self._xlsx_response(wb, "inventory_vendor.xlsx")

        serializer = InventoryVendorSerializer(rows, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    





