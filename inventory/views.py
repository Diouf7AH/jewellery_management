from __future__ import annotations
from typing import Optional, List
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from inventory.models import InventoryMovement, MovementType
from django.db.models import (
    Q, F, Value, DecimalField, ExpressionWrapper, Case, When
)
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.db.models import Sum, Q
from django.db.models.functions import ExtractQuarter
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from inventory.models import InventoryMovement, MovementType
from store.models import Produit, Bijouterie
from purchase.models import AchatProduitLot  # pour lot_code si présent

# ---------- Permission admin/manager ----------
class IsAdminOrManager(IsAuthenticated):
    def has_permission(self, request, view):
        ok = super().has_permission(request, view)
        if not ok:
            return False
        role = getattr(getattr(request.user, "user_role", None), "role", "")
        return role in {"admin", "manager"}

# ---------- Export Excel ----------
from io import BytesIO
from openpyxl import Workbook
from openpyxl.utils import get_column_letter

class ExportXlsxMixin:
    def _xlsx_response(self, wb: Workbook, filename: str) -> HttpResponse:
        bio = BytesIO(); wb.save(bio); bio.seek(0)
        resp = HttpResponse(
            bio.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @staticmethod
    def _autosize(ws):
        for col in ws.columns:
            width = max((len(str(c.value)) if c.value is not None else 0) for c in col) + 2
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(width, 50)

# ---------- Pagination ----------
class MovementPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500

# ---------- Helpers ----------
def _b(v: Optional[str], default=False) -> bool:
    if v is None: return default
    return str(v).lower() in ("1", "true", "yes", "y", "on")

def _dec(v: Optional[str]) -> Optional[Decimal]:
    if not v: return None
    try: return Decimal(str(v))
    except (InvalidOperation, TypeError): return None

def _dt(v: Optional[str]):
    # accepte "YYYY-MM-DD" (00:00 inclusif) ; pour la borne haute on fera +1 jour
    if not v: return None
    try: return datetime.strptime(v, "%Y-%m-%d")
    except Exception: return None

# ==========================================================
#      LISTE DES MOUVEMENTS D’INVENTAIRE (détail)
# ==========================================================
class InventoryMovementListView(ExportXlsxMixin, APIView):
    """
    Liste les **InventoryMovement** (détail), avec filtres + export Excel.

    Champs retournés (par ligne) :
      - horodatage : occurred_at
      - type : movement_type
      - produit : produit_id, produit_nom, produit_sku
      - quantités : qty, signed_qty (CANCEL_PURCHASE en négatif), unit_cost, total_cost (optionnel)
      - source : src_bucket, src_bijouterie_id/nom
      - destination : dst_bucket, dst_bijouterie_id/nom
      - lot : lot_id, lot_code (si relié)
      - achat : achat_id
      - auteur / raison : created_by_id, reason

    Filtres (query params) :
      - q : recherche (produit.nom/sku, lot_code, reason)
      - date_from, date_to : "YYYY-MM-DD" (occurred_at, inclusif)
      - movement_types : CSV (ex: PURCHASE_IN,CANCEL_PURCHASE,ALLOCATE,TRANSFER,RETURN_IN)
      - produit_id, lot_id, lot_code, achat_id
      - src_bucket, dst_bucket (EXTERNAL/RESERVED/BIJOUTERIE/… selon vos enums)
      - src_bijouterie_id, dst_bijouterie_id
      - min_qty, max_qty (sur qty brute)
      - include_costs=1 : inclure total_cost (Σ signed_qty * unit_cost)
      - ordering : -occurred_at (défaut), occurred_at, -qty, qty, produit_nom, -produit_nom
      - export=xlsx : export Excel (désactive pagination)
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]

    @swagger_auto_schema(
        operation_summary="Lister les mouvements d’inventaire (détail) + export Excel",
        manual_parameters=[
            openapi.Parameter("q", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Recherche produit.nom/sku, lot_code, reason"),
            openapi.Parameter("date_from", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="YYYY-MM-DD (inclus)"),
            openapi.Parameter("date_to", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="YYYY-MM-DD (inclus)"),
            openapi.Parameter("movement_types", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="CSV: PURCHASE_IN,CANCEL_PURCHASE,ALLOCATE,TRANSFER,RETURN_IN,SALE_OUT,…"),
            openapi.Parameter("produit_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Filtrer produit"),
            openapi.Parameter("lot_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Filtrer lot_id"),
            openapi.Parameter("lot_code", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Filtrer lot_code"),
            openapi.Parameter("achat_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Filtrer achat"),
            openapi.Parameter("src_bucket", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Filtrer source bucket"),
            openapi.Parameter("dst_bucket", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Filtrer destination bucket"),
            openapi.Parameter("src_bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Filtrer source bijouterie"),
            openapi.Parameter("dst_bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Filtrer destination bijouterie"),
            openapi.Parameter("min_qty", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Quantité minimale"),
            openapi.Parameter("max_qty", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Quantité maximale"),
            openapi.Parameter("include_costs", openapi.IN_QUERY, type=openapi.TYPE_BOOLEAN,
                              description="Inclure total_cost (= signed_qty * unit_cost)"),
            openapi.Parameter("ordering", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Tri: -occurred_at (def), occurred_at, -qty, qty, produit_nom, -produit_nom"),
            openapi.Parameter("page", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Numéro de page"),
            openapi.Parameter("page_size", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Taille de page"),
            openapi.Parameter("export", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="xlsx pour export Excel"),
        ],
        tags=["Inventaire"],
        responses={200: "OK", 403: "Accès refusé (admin/manager)"},
    )
    def get(self, request):
        getf = request.GET.get

        qs = (InventoryMovement.objects
              .select_related("produit", "lot")
              .all())

        # ---- Recherche plein texte ----
        q = (getf("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(produit__nom__icontains=q) |
                Q(produit__sku__icontains=q) |
                Q(lot__lot_code__icontains=q) |
                Q(reason__icontains=q)
            )

        # ---- Filtres simples ----
        if getf("produit_id"):       qs = qs.filter(produit_id=getf("produit_id"))
        if getf("lot_id"):           qs = qs.filter(lot_id=getf("lot_id"))
        if getf("lot_code"):         qs = qs.filter(lot__lot_code__iexact=getf("lot_code"))
        if getf("achat_id"):         qs = qs.filter(achat_id=getf("achat_id"))
        if getf("src_bucket"):       qs = qs.filter(src_bucket=getf("src_bucket"))
        if getf("dst_bucket"):       qs = qs.filter(dst_bucket=getf("dst_bucket"))
        if getf("src_bijouterie_id"):qs = qs.filter(src_bijouterie_id=getf("src_bijouterie_id"))
        if getf("dst_bijouterie_id"):qs = qs.filter(dst_bijouterie_id=getf("dst_bijouterie_id"))

        # Mouvement types
        types_csv = (getf("movement_types") or "").strip()
        if types_csv:
            types = [t.strip() for t in types_csv.split(",") if t.strip()]
            qs = qs.filter(movement_type__in=types)

        # Date window (inclusif)
        df = _dt(getf("date_from"))
        dt = _dt(getf("date_to"))
        if df:
            qs = qs.filter(occurred_at__gte=df)
        if dt:
            qs = qs.filter(occurred_at__lt=dt + timedelta(days=1))

        # Qty range
        min_qty = _dec(getf("min_qty"))
        max_qty = _dec(getf("max_qty"))
        if min_qty is not None: qs = qs.filter(qty__gte=min_qty)
        if max_qty is not None: qs = qs.filter(qty__lte=max_qty)

        # ---- Annotations: signed & cost ----
        include_costs = _b(getf("include_costs"), False)
        sign = Case(
            When(movement_type=MovementType.CANCEL_PURCHASE, then=Value(-1)),
            default=Value(1),
            output_field=DecimalField(max_digits=4, decimal_places=0),
        )
        qs = qs.annotate(
            signed_qty=ExpressionWrapper(F("qty") * sign, output_field=DecimalField(max_digits=18, decimal_places=2)),
        )
        if include_costs:
            qs = qs.annotate(
                total_cost=ExpressionWrapper(
                    Coalesce(F("unit_cost"), Value(Decimal("0.00"))) * F("signed_qty"),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )

        # ---- Tri ----
        ordering = (getf("ordering") or "-occurred_at").strip()
        allowed = {"occurred_at", "-occurred_at", "qty", "-qty", "produit_nom", "-produit_nom"}
        if ordering not in allowed:
            ordering = "-occurred_at"
        if "produit_nom" in ordering:
            # on remplace par champ DB équivalent
            ordering = ordering.replace("produit_nom", "produit__nom")
        qs = qs.order_by(ordering)

        # ---- Hydratation des noms (bijouteries) ----
        # (On va matérialiser plus tard pour Excel/JSON)
        rows = list(qs.values(
            "id", "occurred_at", "movement_type", "qty", "signed_qty",
            "unit_cost", "total_cost",
            "produit_id", "produit__nom", "produit__sku",
            "src_bucket", "src_bijouterie_id",
            "dst_bucket", "dst_bijouterie_id",
            "lot_id", "achat_id", "created_by_id", "reason",
        ))

        bij_ids = set()
        for r in rows:
            if r.get("src_bijouterie_id"): bij_ids.add(r["src_bijouterie_id"])
            if r.get("dst_bijouterie_id"): bij_ids.add(r["dst_bijouterie_id"])
        bij_map = {b.id: b.nom for b in Bijouterie.objects.filter(id__in=bij_ids)} if bij_ids else {}

        # enrichir lignes
        for r in rows:
            r["produit_nom"] = r.pop("produit__nom", None)
            r["produit_sku"] = r.pop("produit__sku", None)
            r["src_bijouterie_nom"] = bij_map.get(r.get("src_bijouterie_id"))
            r["dst_bijouterie_nom"] = bij_map.get(r.get("dst_bijouterie_id"))

        # ---- Export Excel ? ----
        if (getf("export") or "").lower() == "xlsx":
            wb = Workbook(); ws = wb.active; ws.title = "Mouvements"
            headers = [
                "id", "occurred_at", "movement_type",
                "produit_id", "produit_nom", "produit_sku",
                "qty", "signed_qty",
                "unit_cost",
                "total_cost" if include_costs else None,
                "src_bucket", "src_bijouterie_id", "src_bijouterie_nom",
                "dst_bucket", "dst_bijouterie_id", "dst_bijouterie_nom",
                "lot_id", "achat_id", "created_by_id",
                "reason",
            ]
            ws.append([h for h in headers if h is not None])

            for r in rows:
                line = [
                    r.get("id"),
                    r.get("occurred_at"),
                    r.get("movement_type"),
                    r.get("produit_id"),
                    r.get("produit_nom"),
                    r.get("produit_sku"),
                    r.get("qty"),
                    r.get("signed_qty"),
                    r.get("unit_cost"),
                ]
                if include_costs:
                    line.append(r.get("total_cost"))
                line += [
                    r.get("src_bucket"), r.get("src_bijouterie_id"), r.get("src_bijouterie_nom"),
                    r.get("dst_bucket"), r.get("dst_bijouterie_id"), r.get("dst_bijouterie_nom"),
                    r.get("lot_id"), r.get("achat_id"), r.get("created_by_id"),
                    r.get("reason"),
                ]
                ws.append(line)

            self._autosize(ws)
            return self._xlsx_response(wb, "inventory_movements.xlsx")

        # ---- Pagination + JSON ----
        paginator = MovementPagination()
        page = paginator.paginate_queryset(rows, request)
        return paginator.get_paginated_response(page)
    

# API qui retourne les totaux la quantité alloue au vendeur  
#trimestriels, semestres et annuel pour un vendeur donné et une année
class VendorAllocationStatsView(APIView):
    permission_classes = [IsAuthenticated]

    # GET /api/vendors/{vendor_id}/allocations/stats?year=2025
    def get(self, request, vendor_id: int):
        try:
            year = int(request.query_params.get("year", timezone.now().year))
        except ValueError:
            return Response({"detail": "Paramètre 'year' invalide."}, status=400)

        qs = (InventoryMovement.objects
            .filter(
                movement_type=MovementType.VENDOR_ASSIGN,
                vendor_id=vendor_id,
                occurred_at__year=year
            )
            .annotate(qtr=ExtractQuarter("occurred_at")))

        agg = qs.aggregate(
            trimestre_1=Sum("qty", filter=Q(qtr=1)) or 0,
            trimestre_2=Sum("qty", filter=Q(qtr=2)) or 0,
            trimestre_3=Sum("qty", filter=Q(qtr=3)) or 0,
            trimestre_4=Sum("qty", filter=Q(qtr=4)) or 0,
            semestre_1=Sum("qty", filter=Q(occurred_at__month__lte=6)) or 0,
            semestre_2=Sum("qty", filter=Q(occurred_at__month__gte=7)) or 0,
            annuel=Sum("qty") or 0,
        )

        return Response({
            "vendor_id": vendor_id,
            "year": year,
            "allocations": agg
        })