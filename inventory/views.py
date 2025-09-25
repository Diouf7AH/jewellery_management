# purchase/views/achat_year_inventory.py
from __future__ import annotations
from typing import List, Optional, Tuple, Dict
from decimal import Decimal

from django.utils import timezone
from django.db.models import (
    Sum, F, Value, DecimalField, ExpressionWrapper, Case, When
)
from django.db.models.functions import Coalesce, ExtractYear
from django.http import HttpResponse

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

# Modèles (adapte si besoin)
from inventory.models import InventoryMovement, MovementType
from store.models import Produit, Bijouterie

# ============== XLSX mixin réutilisable ==============
from io import BytesIO
from openpyxl import Workbook
from openpyxl.utils import get_column_letter

class ExportXlsxMixin:
    def _xlsx_response(self, wb: Workbook, filename: str) -> HttpResponse:
        bio = BytesIO()
        wb.save(bio)
        bio.seek(0)
        resp = HttpResponse(
            bio.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @staticmethod
    def _autosize(ws):
        for col in ws.columns:
            mx = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                v = "" if cell.value is None else str(cell.value)
                mx = max(mx, len(v))
            ws.column_dimensions[col_letter].width = min(mx + 2, 50)


# =================== Helpers ===================
def _parse_bool(v: Optional[str], default=False) -> bool:
    if v is None:
        return default
    return str(v).lower() in ("1", "true", "yes", "y", "on")

def _parse_group_by(param: Optional[str]) -> List[str]:
    allowed = {"product", "location", "lot", "achat"}
    if not param:
        return ["product", "location"]
    items = [p.strip().lower() for p in param.split(",") if p.strip()]
    return [x for x in items if x in allowed] or ["product", "location"]


# =======================================================
#   Vue: Inventaire des achats par ANNÉE + export Excel
# =======================================================
class AchatYearInventoryView(ExportXlsxMixin, APIView):
    """
    Liste l'inventaire **des achats** par **année** à partir des InventoryMovement :
      - `PURCHASE_IN` (+qty)
      - `CANCEL_PURCHASE` (−qty)

    Options :
      - `group_by`: product,location,lot,achat (combinaisons possibles)
      - `include_costs`: ajoute la valorisation (Σ qty * unit_cost)
      - `net_by_location`: si `location` est présent, soustrait le côté source
         des transferts internes (ALLOCATE/TRANSFER) pour un **net** par localisation
      - `export=xlsx`: export Excel

    Fenêtrage année :
      - Par défaut : les **N dernières années** (param `years`, défaut 3).
      - Ou `start_year` / `end_year` (inclus).
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Inventaire des achats par année (JSON/Excel)",
        operation_description=(
            "Agrège par année les mouvements d’achats.\n\n"
            "Fenêtre 2023 → 2025 (Excel), avec coûts, net par localisation\n"
            "Rappel\n"
            "net_by_location=1 est utile si tu inclus ALLOCATE et que tu veux\n"
            "un net par localisation (réservé vs bijouteries).\n"
            "Sans ALLOCATE, la vue mesure strictement ce qui a été acheté\n"
            "(PURCHASE_IN − CANCEL_PURCHASE).\n"
            "url\n"
            "GET /api/purchase-inventory/yearly/?start_year=2023&end_year=2025\n"
            "&group_by=product,location&include_costs=1&net_by_location=1\n"
            "&movement_types=PURCHASE_IN,CANCEL_PURCHASE,ALLOCATE&export=xlsx\n\n"
            "Paramètres:\n"
            "- `years` (int): nombre d'années en arrière (défaut 3) si `start_year/end_year` non fournis\n"
            "- `start_year`, `end_year` (YYYY): borne inclusive\n"
            "- `group_by` (CSV): parmi product,location,lot,achat (défaut: product,location)\n"
            "- `include_costs` (bool): inclure total_cost (Σ qty*unit_cost) — défaut false\n"
            "- `net_by_location` (bool): net par localisation (réservé/bijouterie) — défaut false\n"
            "- `movement_types` (CSV): override des types (défaut PURCHASE_IN,CANCEL_PURCHASE)\n"
            "- `export` = xlsx: export Excel\n"
        ),
        manual_parameters=[
            openapi.Parameter("years", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="N dernières années (défaut 3)"),
            openapi.Parameter("start_year", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="Année début (incluse)"),
            openapi.Parameter("end_year", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="Année fin (incluse)"),
            openapi.Parameter("group_by", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="CSV: product,location,lot,achat (défaut: product,location)"),
            openapi.Parameter("include_costs", openapi.IN_QUERY, type=openapi.TYPE_BOOLEAN,
                              description="Inclure Σ qty*unit_cost"),
            openapi.Parameter("net_by_location", openapi.IN_QUERY, type=openapi.TYPE_BOOLEAN,
                              description="Soustraire la source des transferts internes pour un net par localisation"),
            openapi.Parameter("movement_types", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="CSV de types, défaut: PURCHASE_IN,CANCEL_PURCHASE"),
            openapi.Parameter("export", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="xlsx pour export Excel"),
        ],
        tags=["Achats", "Inventaire"],
        responses={200: "OK"}
    )
    def get(self, request):
        # -------- Fenêtre: années --------
        today = timezone.localdate()
        start_year = request.GET.get("start_year")
        end_year = request.GET.get("end_year")
        years = int(request.GET.get("years") or 3)

        if start_year and end_year:
            y1, y2 = int(start_year), int(end_year)
        else:
            y2 = today.year
            y1 = y2 - years + 1  # inclusif

        # -------- Groupement & options --------
        group_by = _parse_group_by(request.GET.get("group_by"))
        include_costs = _parse_bool(request.GET.get("include_costs"), False)
        net_by_location = _parse_bool(request.GET.get("net_by_location"), False)

        # -------- Types de mouvements --------
        default_types = [MovementType.PURCHASE_IN, MovementType.CANCEL_PURCHASE]
        types_csv = request.GET.get("movement_types")
        if types_csv:
            chosen = [s.strip() for s in types_csv.split(",") if s.strip()]
            movement_types = chosen or default_types
        else:
            movement_types = default_types

        # -------- Base queryset --------
        qs = (
            InventoryMovement.objects
            .annotate(year=ExtractYear("occurred_at"))
            .filter(year__gte=y1, year__lte=y2, movement_type__in=movement_types)
        )

        # Signe: cancel à −1, le reste +1
        sign = Case(
            When(movement_type=MovementType.CANCEL_PURCHASE, then=Value(-1)),
            default=Value(1),
            output_field=DecimalField(max_digits=4, decimal_places=0),
        )
        signed_qty = ExpressionWrapper(F("qty") * sign, output_field=DecimalField(max_digits=18, decimal_places=2))
        cost_expr = ExpressionWrapper(
            Coalesce(F("unit_cost"), Value(Decimal("0.00"))) * signed_qty,
            output_field=DecimalField(max_digits=18, decimal_places=2),
        )

        # Champs de groupement (toujours l'année)
        values_fields: List[str] = ["year"]
        if "product" in group_by:
            values_fields.append("produit_id")
        if "location" in group_by:
            values_fields += ["dst_bucket", "dst_bijouterie_id"]
        if "lot" in group_by:
            values_fields.append("lot_id")
        if "achat" in group_by:
            values_fields.append("achat_id")

        agg = (
            qs.values(*values_fields)
              .annotate(
                  total_qty=Coalesce(Sum(signed_qty), Value(Decimal("0.00"))),
                  total_cost=Coalesce(Sum(cost_expr), Value(Decimal("0.00"))),
              )
              .order_by("year", *[f for f in values_fields if f != "year"])
        )

        rows = list(agg)

        # -------- Option: net par localisation (soustrait la source) --------
        if net_by_location and "location" in group_by:
            transfer_types = [MovementType.ALLOCATE, getattr(MovementType, "TRANSFER", "TRANSFER")]
            src_values = ["year"]
            if "product" in group_by:
                src_values.append("produit_id")
            if "lot" in group_by:
                src_values.append("lot_id")
            if "achat" in group_by:
                src_values.append("achat_id")

            src_qs = (
                InventoryMovement.objects
                .annotate(year=ExtractYear("occurred_at"))
                .filter(year__gte=y1, year__lte=y2, movement_type__in=transfer_types)
                .values(*src_values, "src_bucket", "src_bijouterie_id")
                .annotate(total_qty=Coalesce(Sum(signed_qty), Value(Decimal("0.00"))))
            )

            for r in src_qs:
                row = {k: r.get(k) for k in src_values}
                row["dst_bucket"] = r["src_bucket"]
                row["dst_bijouterie_id"] = r["src_bijouterie_id"]
                row["total_qty"] = -r["total_qty"]  # on soustrait la source
                row["total_cost"] = Decimal("0.00")  # pas de coût sur transferts internes
                rows.append(row)

        # -------- Hydratation (noms) --------
        prod_ids = {r.get("produit_id") for r in rows if "produit_id" in r}
        bij_ids = {r.get("dst_bijouterie_id") for r in rows if r.get("dst_bijouterie_id")}
        products = {p.id: p for p in Produit.objects.filter(id__in=prod_ids)} if prod_ids else {}
        bijs = {b.id: b for b in Bijouterie.objects.filter(id__in=bij_ids)} if bij_ids else {}

        data_rows: List[Dict] = []
        for r in rows:
            out = {
                "year": int(r["year"]),
                "total_qty": str(r["total_qty"]),
            }
            if include_costs:
                out["total_cost"] = str(r["total_cost"])

            if "produit_id" in r:
                pid = r["produit_id"]
                p = products.get(pid)
                out.update({
                    "produit_id": pid,
                    "produit_nom": getattr(p, "nom", None) if p else None,
                    "produit_sku": getattr(p, "sku", None) if p else None,
                })

            if "dst_bucket" in r:
                out["location_type"] = r["dst_bucket"]
            if "dst_bijouterie_id" in r:
                bid = r["dst_bijouterie_id"]
                out["bijouterie_id"] = bid
                out["bijouterie_nom"] = bijs[bid].nom if bid and bid in bijs else None

            if "lot_id" in r:
                out["lot_id"] = r["lot_id"]
            if "achat_id" in r:
                out["achat_id"] = r["achat_id"]

            data_rows.append(out)

        # -------- Export Excel ? --------
        if request.GET.get("export") == "xlsx":
            wb = Workbook()
            ws = wb.active
            ws.title = "Inventaire achats annuel"

            headers = [
                "year",
                "produit_id", "produit_nom", "produit_sku",
                "location_type", "bijouterie_id", "bijouterie_nom",
                "lot_id", "achat_id",
                "total_qty",
            ]
            if include_costs:
                headers.append("total_cost")
            ws.append(headers)

            for row in data_rows:
                ws.append([
                    row.get("year"),
                    row.get("produit_id"),
                    row.get("produit_nom"),
                    row.get("produit_sku"),
                    row.get("location_type"),
                    row.get("bijouterie_id"),
                    row.get("bijouterie_nom"),
                    row.get("lot_id"),
                    row.get("achat_id"),
                    row.get("total_qty"),
                    row.get("total_cost") if include_costs else None,
                ])

            self._autosize(ws)
            filename = f"achats_inventory_yearly_{timezone.now().strftime('%Y%m%d')}.xlsx"
            return self._xlsx_response(wb, filename)

        # -------- JSON --------
        payload = {
            "range": {"start_year": y1, "end_year": y2},
            "group_by": group_by,
            "include_costs": include_costs,
            "net_by_location": net_by_location,
            "rows": data_rows,
        }
        return Response(payload, status=status.HTTP_200_OK)