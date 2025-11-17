from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.db.models import (Case, DecimalField, F, IntegerField, Q, Sum,
                              Value, When)
from django.db.models.functions import Coalesce, ExtractQuarter
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from openpyxl import Workbook
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from inventory.models import InventoryMovement, MovementType
from inventory.utils import ExportXlsxMixin
from store.models import Bijouterie, Produit
from vendor.models import Vendor

# ==========================================================
#                 HELPERS GÉNÉRAUX
# ==========================================================

def _b(v: Optional[str], default: bool = False) -> bool:
    """
    Convertit une valeur de query (?include_costs=1, true, yes, on) en booléen.
    """
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _dec(v: Optional[str]) -> Optional[Decimal]:
    """
    Convertit une string en Decimal, ou retourne None si vide / invalide.
    Exemple: _dec("12.34") -> Decimal("12.34")
    """
    if v in (None, "", "null"):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _dt(v: Optional[str]):
    """
    Parse une date au format 'YYYY-MM-DD' et renvoie un datetime à 00:00.
    Exemple: _dt("2025-01-15") -> datetime(2025, 1, 15, 0, 0)
    Retourne None si le format est invalide ou vide.
    """
    if not v:
        return None
    try:
        return datetime.strptime(v, "%Y-%m-%d")
    except Exception:
        return None


def _user_bijouterie_id(user) -> Optional[int]:
    """
    Retourne l'ID de la bijouterie liée à l'utilisateur si c'est
    un manager, un vendor ou un cashier.
    """
    # Manager
    mgr = getattr(user, "staff_manager_profile", None)
    if mgr and getattr(mgr, "bijouterie_id", None):
        return mgr.bijouterie_id

    # Vendor
    vend = getattr(user, "staff_vendor_profile", None)
    if vend and getattr(vend, "bijouterie_id", None):
        return vend.bijouterie_id

    # Cashier
    cash = getattr(user, "staff_cashier_profile", None)
    if cash and getattr(cash, "bijouterie_id", None):
        return cash.bijouterie_id

    return None


# ==========================================================
#      1) JOURNAL DÉTAILLÉ : InventoryMovementListView
# ==========================================================

class InventoryMovementListView(ExportXlsxMixin, APIView):
    """
    Journal détaillé des mouvements d’inventaire (InventoryMovement).

    - admin   : accès global, peut filtrer par ?bijouterie_id=...
    - manager : accès limité à SA bijouterie (src ou dst)

    Chaque ligne correspond à un mouvement individuel (achat, vente, transfert, annulation, etc.).

    Champs retournés (par ligne) :
        - id, occurred_at, movement_type
        - produit : produit_id, produit_nom, produit_sku
        - quantités : qty, signed_qty (CANCEL_PURCHASE en négatif)
        - coûts : unit_cost, total_cost (si include_costs=1)
        - source : src_bucket, src_bijouterie_id/nom
        - destination : dst_bucket, dst_bijouterie_id/nom
        - lot : lot_id
        - achat : achat_id
        - auteur / raison : created_by_id, reason
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Lister les mouvements d’inventaire (détail) + export Excel",
        operation_description=(
            "Journal détaillé des InventoryMovement avec filtres avancés.\n\n"
            "Filtrage par période, produit, lot, achat, bijouterie, type de mouvement, etc.\n"
            "Possibilité d’export Excel complet.\n"
            "⚠️ Pas de pagination : tous les résultats sont renvoyés dans un seul tableau JSON."
        ),
        manual_parameters=[
            openapi.Parameter("q", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Recherche produit.nom/sku, lot_code, reason"),
            openapi.Parameter("date_from", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="YYYY-MM-DD (début inclus)"),
            openapi.Parameter("date_to", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="YYYY-MM-DD (fin inclus)"),
            openapi.Parameter("movement_types", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="CSV: PURCHASE_IN,CANCEL_PURCHASE,ALLOCATE,TRANSFER,RETURN_IN,SALE_OUT,…"),
            openapi.Parameter("produit_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Filtrer produit"),
            openapi.Parameter("lot_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Filtrer lot_id"),
            openapi.Parameter("lot_code", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Filtrer lot_code"),
            openapi.Parameter("achat_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Filtrer achat"),
            openapi.Parameter("src_bucket", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Filtrer source bucket"),
            openapi.Parameter("dst_bucket", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Filtrer destination bucket"),
            openapi.Parameter("bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="(admin) Filtrer mouvements d’une bijouterie (src OU dst)"),
            openapi.Parameter("src_bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="Filtrer source bijouterie"),
            openapi.Parameter("dst_bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="Filtrer destination bijouterie"),
            openapi.Parameter("min_qty", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Quantité minimale"),
            openapi.Parameter("max_qty", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Quantité maximale"),
            openapi.Parameter("include_costs", openapi.IN_QUERY, type=openapi.TYPE_BOOLEAN,
                              description="Inclure total_cost (= signed_qty * unit_cost)"),
            openapi.Parameter("ordering", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Tri: -occurred_at (def), occurred_at, -qty, qty, produit_nom, -produit_nom"),
            openapi.Parameter("export", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="xlsx pour export Excel (désactive le JSON)"),
        ],
        tags=["Inventaire"],
        responses={200: "OK", 403: "Accès refusé"},
    )
    def get(self, request):
        getf = request.GET.get

        # -------- Rôle & accès --------
        role = getattr(getattr(request.user, "user_role", None), "role", "") or ""
        role = role.lower()
        if role not in {"admin", "manager"}:
            return Response({"detail": "Accès réservé aux admins et managers."}, status=403)

        qs = InventoryMovement.objects.select_related("produit", "lot").all()

        # -------- Scope bijouterie --------
        if role == "admin":
            bijouterie_id = getf("bijouterie_id")
        else:
            bijouterie_id = _user_bijouterie_id(request.user)
            if not bijouterie_id:
                return Response(
                    {"detail": "Ce manager n'est rattaché à aucune bijouterie."},
                    status=400,
                )

        if bijouterie_id:
            qs = qs.filter(
                Q(src_bijouterie_id=bijouterie_id) |
                Q(dst_bijouterie_id=bijouterie_id)
            )

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
        if getf("produit_id"):
            qs = qs.filter(produit_id=getf("produit_id"))
        if getf("lot_id"):
            qs = qs.filter(lot_id=getf("lot_id"))
        if getf("lot_code"):
            qs = qs.filter(lot__lot_code__iexact=getf("lot_code"))
        if getf("achat_id"):
            qs = qs.filter(achat_id=getf("achat_id"))
        if getf("src_bucket"):
            qs = qs.filter(src_bucket=getf("src_bucket"))
        if getf("dst_bucket"):
            qs = qs.filter(dst_bucket=getf("dst_bucket"))
        if getf("src_bijouterie_id"):
            qs = qs.filter(src_bijouterie_id=getf("src_bijouterie_id"))
        if getf("dst_bijouterie_id"):
            qs = qs.filter(dst_bijouterie_id=getf("dst_bijouterie_id"))

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
        if min_qty is not None:
            qs = qs.filter(qty__gte=min_qty)
        if max_qty is not None:
            qs = qs.filter(qty__lte=max_qty)

        # ---- Annotations: signed & cost ----
        include_costs = _b(getf("include_costs"), False)
        sign = Case(
            When(movement_type=MovementType.CANCEL_PURCHASE, then=Value(-1)),
            default=Value(1),
            output_field=DecimalField(max_digits=4, decimal_places=0),
        )
        qs = qs.annotate(
            signed_qty=F("qty") * sign
        )
        if include_costs:
            qs = qs.annotate(
                total_cost=Coalesce(F("unit_cost"), Value(Decimal("0.00"))) * F("signed_qty"),
            )

        # ---- Tri ----
        ordering = (getf("ordering") or "-occurred_at").strip()
        allowed = {"occurred_at", "-occurred_at", "qty", "-qty", "produit_nom", "-produit_nom"}
        if ordering not in allowed:
            ordering = "-occurred_at"
        if "produit_nom" in ordering:
            ordering = ordering.replace("produit_nom", "produit__nom")
        qs = qs.order_by(ordering)

        # ---- Hydratation des noms (bijouteries) ----
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
            if r.get("src_bijouterie_id"):
                bij_ids.add(r["src_bijouterie_id"])
            if r.get("dst_bijouterie_id"):
                bij_ids.add(r["dst_bijouterie_id"])
        bij_map = {b.id: b.nom for b in Bijouterie.objects.filter(id__in=bij_ids)} if bij_ids else {}

        for r in rows:
            r["produit_nom"] = r.pop("produit__nom", None)
            r["produit_sku"] = r.pop("produit__sku", None)
            r["src_bijouterie_nom"] = bij_map.get(r.get("src_bijouterie_id"))
            r["dst_bijouterie_nom"] = bij_map.get(r.get("dst_bijouterie_id"))

        # ---- Export Excel ? ----
        if (getf("export") or "").lower() == "xlsx":
            wb = Workbook()
            ws = wb.active
            ws.title = "Mouvements"
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

        # ---- JSON (sans pagination) ----
        return Response({
            "count": len(rows),
            "results": rows,
        })


# ==========================================================
#  2) TABLEAU INVENTAIRE PAR BIJOUTERIE + PRODUIT
# ==========================================================

class InventoryMovementTablePerBijouterieView(ExportXlsxMixin, APIView):
    """
    Tableau d’inventaire par PRODUIT ET BIJOUTERIE.

    - admin   : accès global, peut filtrer par ?bijouterie_id=...
    - manager : limité à SA bijouterie, sur une période max de 3 ans en arrière

    Pour chaque couple (bijouterie, produit), sur une période donnée :
      - opening_qty      : stock d’ouverture (avant date_from)
      - purchase_in      : achats (PURCHASE_IN) pendant la période
      - sale_out         : ventes (SALE_OUT) pendant la période
      - cancel_purchase  : annulations d’achats (CANCEL_PURCHASE)
      - net_period       : purchase_in - sale_out - cancel_purchase
      - closing_qty      : opening_qty + net_period
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Tableau d’inventaire par produit ET bijouterie",
        operation_description=(
            "Calcule l’inventaire par couple (bijouterie, produit) sur une période donnée : "
            "stock d’ouverture, achats, ventes, annulations, stock de clôture.\n\n"
            "admin : accès global, filtre optionnel bijouterie_id.\n"
            "manager : limité à sa propre bijouterie, période max 3 ans en arrière."
        ),
        manual_parameters=[
            openapi.Parameter("date_from", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="YYYY-MM-DD (début de période, inclusif)"),
            openapi.Parameter("date_to", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="YYYY-MM-DD (fin de période, inclusif)"),
            openapi.Parameter("bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="(admin) Restreindre à une bijouterie spécifique"),
            openapi.Parameter("produit_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="Filtrer un produit précis"),
            openapi.Parameter("lot_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="Filtrer par lot_id"),
            openapi.Parameter("lot_code", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Filtrer par lot_code"),
            openapi.Parameter("achat_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="Filtrer par achat"),
            openapi.Parameter("movement_types", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="CSV de types si tu veux restreindre (ex: PURCHASE_IN,SALE_OUT)"),
            openapi.Parameter("export", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="xlsx pour export Excel"),
        ],
        tags=["Inventaire"],
        responses={200: "OK", 403: "Accès refusé"},
    )
    def get(self, request):
        getf = request.GET.get
        now = timezone.now()

        # -------- Rôle --------
        role = getattr(getattr(request.user, "user_role", None), "role", "") or ""
        role = role.lower()
        if role not in {"admin", "manager"}:
            return Response({"detail": "Accès réservé aux admins et managers."}, status=403)

        # -------- Fenêtre de dates --------
        date_from = _dt(getf("date_from"))
        date_to = _dt(getf("date_to")) or now

        if role == "manager":
            three_years_ago = now - timedelta(days=3 * 365)
            if not date_from or date_from < three_years_ago:
                date_from = three_years_ago
        else:
            if not date_from:
                date_from = now.replace(
                    month=1, day=1, hour=0, minute=0, second=0, microsecond=0
                )
        date_to_plus = date_to + timedelta(days=1)

        # -------- Scope bijouterie --------
        if role == "admin":
            bijouterie_filter_id = getf("bijouterie_id")
        else:
            bijouterie_filter_id = _user_bijouterie_id(request.user)
            if not bijouterie_filter_id:
                return Response(
                    {"detail": "Ce manager n'est rattaché à aucune bijouterie."},
                    status=400,
                )

        # -------- Query de base --------
        qs = InventoryMovement.objects.select_related("produit").all()

        if bijouterie_filter_id:
            qs = qs.filter(
                Q(src_bijouterie_id=bijouterie_filter_id) |
                Q(dst_bijouterie_id=bijouterie_filter_id)
            )

        if getf("produit_id"):
            qs = qs.filter(produit_id=getf("produit_id"))
        if getf("lot_id"):
            qs = qs.filter(lot_id=getf("lot_id"))
        if getf("lot_code"):
            qs = qs.filter(lot__lot_code__iexact=getf("lot_code"))
        if getf("achat_id"):
            qs = qs.filter(achat_id=getf("achat_id"))

        types_csv = (getf("movement_types") or "").strip()
        if types_csv:
            types = [t.strip() for t in types_csv.split(",") if t.strip()]
            qs = qs.filter(movement_type__in=types)

        # -------- Annotation bijouterie_effective --------
        qs = qs.annotate(
            bijouterie_effective=Case(
                When(dst_bijouterie_id__isnull=False, then=F("dst_bijouterie_id")),
                When(src_bijouterie_id__isnull=False, then=F("src_bijouterie_id")),
                default=Value(None),
                output_field=IntegerField(),
            )
        ).filter(bijouterie_effective__isnull=False)

        # -------- Stock d'ouverture (avant date_from) --------
        opening_qs = qs.filter(occurred_at__lt=date_from)
        opening_agg = opening_qs.values("bijouterie_effective", "produit_id").annotate(
            opening_purchase_in=Sum("qty", filter=Q(movement_type=MovementType.PURCHASE_IN)),
            opening_sale_out=Sum("qty", filter=Q(movement_type=MovementType.SALE_OUT)),
            opening_cancel_purchase=Sum("qty", filter=Q(movement_type=MovementType.CANCEL_PURCHASE)),
        )

        opening_map = {}
        for r in opening_agg:
            bid = r["bijouterie_effective"]
            pid = r["produit_id"]
            opening_in = r["opening_purchase_in"] or 0
            opening_out = (r["opening_sale_out"] or 0) + (r["opening_cancel_purchase"] or 0)
            opening_map[(bid, pid)] = opening_in - opening_out

        # -------- Mouvements période --------
        period_qs = qs.filter(occurred_at__gte=date_from, occurred_at__lt=date_to_plus)
        period_agg = period_qs.values("bijouterie_effective", "produit_id").annotate(
            purchase_in=Sum("qty", filter=Q(movement_type=MovementType.PURCHASE_IN)),
            sale_out=Sum("qty", filter=Q(movement_type=MovementType.SALE_OUT)),
            cancel_purchase=Sum("qty", filter=Q(movement_type=MovementType.CANCEL_PURCHASE)),
        )

        bij_ids = set()
        produit_ids = set()
        for r in period_agg:
            bij_ids.add(r["bijouterie_effective"])
            produit_ids.add(r["produit_id"])
        for (bid, pid) in opening_map.keys():
            bij_ids.add(bid)
            produit_ids.add(pid)

        bijs = Bijouterie.objects.filter(id__in=bij_ids)
        bij_map = {b.id: b.nom for b in bijs}

        produits = Produit.objects.filter(id__in=produit_ids)
        prod_map = {p.id: p for p in produits}

        rows = []
        for r in period_agg:
            bid = r["bijouterie_effective"]
            pid = r["produit_id"]
            prod = prod_map.get(pid)

            opening_qty = opening_map.get((bid, pid), 0) or 0
            purchase_in = r["purchase_in"] or 0
            sale_out = r["sale_out"] or 0
            cancel_purchase = r["cancel_purchase"] or 0

            net_period = purchase_in - sale_out - cancel_purchase
            closing_qty = opening_qty + net_period

            rows.append({
                "bijouterie_id": bid,
                "bijouterie_nom": bij_map.get(bid),
                "produit_id": pid,
                "produit_nom": getattr(prod, "nom", None),
                "produit_sku": getattr(prod, "sku", None),
                "opening_qty": opening_qty,
                "purchase_in": purchase_in,
                "sale_out": sale_out,
                "cancel_purchase": cancel_purchase,
                "net_period": net_period,
                "closing_qty": closing_qty,
            })

        # -------- Export Excel ? --------
        if (getf("export") or "").lower() == "xlsx":
            wb = Workbook()
            ws = wb.active
            ws.title = "Inventaire par bijouterie"

            headers = [
                "bijouterie_id", "bijouterie_nom",
                "produit_id", "produit_nom", "produit_sku",
                "opening_qty",
                "purchase_in", "sale_out", "cancel_purchase",
                "net_period", "closing_qty",
            ]
            ws.append(headers)

            for r in rows:
                ws.append([
                    r["bijouterie_id"],
                    r["bijouterie_nom"],
                    r["produit_id"],
                    r["produit_nom"],
                    r["produit_sku"],
                    r["opening_qty"],
                    r["purchase_in"],
                    r["sale_out"],
                    r["cancel_purchase"],
                    r["net_period"],
                    r["closing_qty"],
                ])

            self._autosize(ws)
            filename = f"inventory_table_per_bijouterie_{date_from.date()}_{date_to.date()}.xlsx"
            return self._xlsx_response(wb, filename)

        # -------- JSON --------
        return Response({
            "scope": role,
            "bijouterie_filter_id": bijouterie_filter_id,
            "date_from": date_from.date().isoformat(),
            "date_to": date_to.date().isoformat(),
            "count": len(rows),
            "results": rows,
        })


# ==========================================================
#  3) INVENTAIRE COMBINÉ BIJOUTERIE + VENDOR
# ==========================================================

class InventoryBijouterieVendorTableView(ExportXlsxMixin, APIView):
    """
    V3 combinée : inventaire par BIJOUTERIE+PRODUIT et par VENDOR+PRODUIT
    dans une seule réponse.

    - admin   : accès global, peut filtrer par ?bijouterie_id=...
    - manager : limité à SA bijouterie, période max = 3 ans en arrière

    Pour chaque (bijouterie, produit) :
      - opening_qty, purchase_in, sale_out, cancel_purchase, net_period, closing_qty

    Pour chaque (vendor, produit) :
      - opening_qty, assigned_in (VENDOR_ASSIGN), sale_out, net_period, closing_qty
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Inventaire combiné bijouterie + vendor (par produit)",
        operation_description=(
            "Retourne dans une même réponse :\n"
            "- inventory_bijouterie : inventaire par (bijouterie, produit)\n"
            "- inventory_vendors   : inventaire par (vendor, produit)\n\n"
            "admin : accès global, peut filtrer par bijouterie_id.\n"
            "manager : limité à sa bijouterie, période max 3 ans."
        ),
        manual_parameters=[
            openapi.Parameter("date_from", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="YYYY-MM-DD (début de période, inclusif)"),
            openapi.Parameter("date_to", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="YYYY-MM-DD (fin de période, inclusif)"),
            openapi.Parameter("bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="(admin) Restreindre à une bijouterie spécifique"),
            openapi.Parameter("produit_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="Filtrer un produit précis"),
            openapi.Parameter("export", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="xlsx pour export Excel (2 onglets : Bijouteries & Vendors)"),
        ],
        tags=["Inventaire"],
        responses={200: "OK", 403: "Accès refusé"},
    )
    def get(self, request):
        getf = request.GET.get
        now = timezone.now()

        # -------- Rôle --------
        role = getattr(getattr(request.user, "user_role", None), "role", "") or ""
        role = role.lower()
        if role not in {"admin", "manager"}:
            return Response({"detail": "Accès réservé aux admins et managers."}, status=403)

        # -------- Fenêtre de dates --------
        date_from = _dt(getf("date_from"))
        date_to = _dt(getf("date_to")) or now

        if role == "manager":
            three_years_ago = now - timedelta(days=3 * 365)
            if not date_from or date_from < three_years_ago:
                date_from = three_years_ago
        else:
            if not date_from:
                date_from = now.replace(
                    month=1, day=1, hour=0, minute=0, second=0, microsecond=0
                )
        date_to_plus = date_to + timedelta(days=1)

        # -------- Scope bijouterie --------
        if role == "admin":
            bij_scope_id = getf("bijouterie_id")
        else:
            bij_scope_id = _user_bijouterie_id(request.user)
            if not bij_scope_id:
                return Response(
                    {"detail": "Ce manager n'est rattaché à aucune bijouterie."},
                    status=400,
                )

        # -------- Query de base --------
        qs = InventoryMovement.objects.select_related("produit").all()

        if bij_scope_id:
            qs = qs.filter(
                Q(src_bijouterie_id=bij_scope_id) |
                Q(dst_bijouterie_id=bij_scope_id)
            )

        if getf("produit_id"):
            qs = qs.filter(produit_id=getf("produit_id"))

        # =====================================================================
        # 1) INVENTAIRE PAR BIJOUTERIE + PRODUIT
        # =====================================================================
        qs_bij = qs.annotate(
            bijouterie_effective=Case(
                When(dst_bijouterie_id__isnull=False, then=F("dst_bijouterie_id")),
                When(src_bijouterie_id__isnull=False, then=F("src_bijouterie_id")),
                default=Value(None),
                output_field=IntegerField(),
            )
        ).filter(bijouterie_effective__isnull=False)

        opening_bij_qs = qs_bij.filter(occurred_at__lt=date_from)
        opening_bij_agg = opening_bij_qs.values("bijouterie_effective", "produit_id").annotate(
            opening_purchase_in=Sum("qty", filter=Q(movement_type=MovementType.PURCHASE_IN)),
            opening_sale_out=Sum("qty", filter=Q(movement_type=MovementType.SALE_OUT)),
            opening_cancel_purchase=Sum("qty", filter=Q(movement_type=MovementType.CANCEL_PURCHASE)),
        )

        opening_bij_map = {}
        for r in opening_bij_agg:
            bid = r["bijouterie_effective"]
            pid = r["produit_id"]
            o_in = r["opening_purchase_in"] or 0
            o_out = (r["opening_sale_out"] or 0) + (r["opening_cancel_purchase"] or 0)
            opening_bij_map[(bid, pid)] = o_in - o_out

        period_bij_qs = qs_bij.filter(occurred_at__gte=date_from, occurred_at__lt=date_to_plus)
        period_bij_agg = period_bij_qs.values("bijouterie_effective", "produit_id").annotate(
            purchase_in=Sum("qty", filter=Q(movement_type=MovementType.PURCHASE_IN)),
            sale_out=Sum("qty", filter=Q(movement_type=MovementType.SALE_OUT)),
            cancel_purchase=Sum("qty", filter=Q(movement_type=MovementType.CANCEL_PURCHASE)),
        )

        bij_ids = set()
        produit_ids = set()
        for r in period_bij_agg:
            bij_ids.add(r["bijouterie_effective"])
            produit_ids.add(r["produit_id"])
        for (bid, pid) in opening_bij_map.keys():
            bij_ids.add(bid)
            produit_ids.add(pid)

        bijs = Bijouterie.objects.filter(id__in=bij_ids)
        bij_map = {b.id: b.nom for b in bijs}

        produits = Produit.objects.filter(id__in=produit_ids)
        prod_map = {p.id: p for p in produits}

        inventory_bijouterie = []
        for r in period_bij_agg:
            bid = r["bijouterie_effective"]
            pid = r["produit_id"]
            prod = prod_map.get(pid)

            opening_qty = opening_bij_map.get((bid, pid), 0) or 0
            purchase_in = r["purchase_in"] or 0
            sale_out = r["sale_out"] or 0
            cancel_purchase = r["cancel_purchase"] or 0
            net_period = purchase_in - sale_out - cancel_purchase
            closing_qty = opening_qty + net_period

            inventory_bijouterie.append({
                "bijouterie_id": bid,
                "bijouterie_nom": bij_map.get(bid),
                "produit_id": pid,
                "produit_nom": getattr(prod, "nom", None),
                "produit_sku": getattr(prod, "sku", None),
                "opening_qty": opening_qty,
                "purchase_in": purchase_in,
                "sale_out": sale_out,
                "cancel_purchase": cancel_purchase,
                "net_period": net_period,
                "closing_qty": closing_qty,
            })

        # =====================================================================
        # 2) INVENTAIRE PAR VENDOR + PRODUIT
        # =====================================================================
        qs_vendor = qs.filter(vendor_id__isnull=False)

        opening_vendor_qs = qs_vendor.filter(occurred_at__lt=date_from)
        opening_vendor_agg = opening_vendor_qs.values("vendor_id", "produit_id").annotate(
            opening_in=Sum("qty", filter=Q(movement_type=MovementType.VENDOR_ASSIGN)),
            opening_out=Sum("qty", filter=Q(movement_type=MovementType.SALE_OUT)),
        )

        opening_vendor_map = {}
        for r in opening_vendor_agg:
            vid = r["vendor_id"]
            pid = r["produit_id"]
            o_in = r["opening_in"] or 0
            o_out = r["opening_out"] or 0
            opening_vendor_map[(vid, pid)] = o_in - o_out

        period_vendor_qs = qs_vendor.filter(occurred_at__gte=date_from, occurred_at__lt=date_to_plus)
        period_vendor_agg = period_vendor_qs.values("vendor_id", "produit_id").annotate(
            assigned_in=Sum("qty", filter=Q(movement_type=MovementType.VENDOR_ASSIGN)),
            sale_out=Sum("qty", filter=Q(movement_type=MovementType.SALE_OUT)),
        )

        vendor_ids = set()
        produit_ids_vendor = set()
        for r in period_vendor_agg:
            vendor_ids.add(r["vendor_id"])
            produit_ids_vendor.add(r["produit_id"])
        for (vid, pid) in opening_vendor_map.keys():
            vendor_ids.add(vid)
            produit_ids_vendor.add(pid)

        vendors = Vendor.objects.select_related("user").filter(id__in=vendor_ids)
        vend_map = {
            v.id: {
                "username": getattr(v.user, "username", None),
                "email": getattr(v.user, "email", None),
            }
            for v in vendors
        }

        produits_vendor = Produit.objects.filter(id__in=produit_ids_vendor)
        prod_vendor_map = {p.id: p for p in produits_vendor}

        inventory_vendors = []
        for r in period_vendor_agg:
            vid = r["vendor_id"]
            pid = r["produit_id"]

            opening_qty = opening_vendor_map.get((vid, pid), 0) or 0
            assigned_in = r["assigned_in"] or 0
            sale_out = r["sale_out"] or 0
            net_period = assigned_in - sale_out
            closing_qty = opening_qty + net_period

            vend_info = vend_map.get(vid, {})
            prod = prod_vendor_map.get(pid)

            inventory_vendors.append({
                "vendor_id": vid,
                "vendor_username": vend_info.get("username"),
                "vendor_email": vend_info.get("email"),
                "produit_id": pid,
                "produit_nom": getattr(prod, "nom", None),
                "produit_sku": getattr(prod, "sku", None),
                "opening_qty": opening_qty,
                "assigned_in": assigned_in,
                "sale_out": sale_out,
                "net_period": net_period,
                "closing_qty": closing_qty,
            })

        # =====================================================================
        # 3) Export Excel ?
        # =====================================================================
        if (getf("export") or "").lower() == "xlsx":
            wb = Workbook()

            # Onglet 1 : Bijouteries
            ws1 = wb.active
            ws1.title = "Bijouteries"
            headers_bij = [
                "bijouterie_id", "bijouterie_nom",
                "produit_id", "produit_nom", "produit_sku",
                "opening_qty",
                "purchase_in", "sale_out", "cancel_purchase",
                "net_period", "closing_qty",
            ]
            ws1.append(headers_bij)
            for r in inventory_bijouterie:
                ws1.append([
                    r["bijouterie_id"],
                    r["bijouterie_nom"],
                    r["produit_id"],
                    r["produit_nom"],
                    r["produit_sku"],
                    r["opening_qty"],
                    r["purchase_in"],
                    r["sale_out"],
                    r["cancel_purchase"],
                    r["net_period"],
                    r["closing_qty"],
                ])
            self._autosize(ws1)

            # Onglet 2 : Vendors
            ws2 = wb.create_sheet(title="Vendors")
            headers_vendor = [
                "vendor_id", "vendor_username", "vendor_email",
                "produit_id", "produit_nom", "produit_sku",
                "opening_qty",
                "assigned_in", "sale_out",
                "net_period", "closing_qty",
            ]
            ws2.append(headers_vendor)
            for r in inventory_vendors:
                ws2.append([
                    r["vendor_id"],
                    r["vendor_username"],
                    r["vendor_email"],
                    r["produit_id"],
                    r["produit_nom"],
                    r["produit_sku"],
                    r["opening_qty"],
                    r["assigned_in"],
                    r["sale_out"],
                    r["net_period"],
                    r["closing_qty"],
                ])
            self._autosize(ws2)

            filename = f"inventory_bijouterie_vendor_{date_from.date()}_{date_to.date()}.xlsx"
            return self._xlsx_response(wb, filename)

        # =====================================================================
        # 4) JSON
        # =====================================================================
        return Response({
            "scope": role,
            "bijouterie_scope_id": bij_scope_id,
            "date_from": date_from.date().isoformat(),
            "date_to": date_to.date().isoformat(),
            "inventory_bijouterie": inventory_bijouterie,
            "inventory_vendors": inventory_vendors,
        })


# ==========================================================
#  4) STATS ALLOCATIONS VENDOR / ANNÉE
# ==========================================================

class VendorAllocationStatsView(APIView):
    """
    Statistiques d’allocations de stock pour un vendeur sur une année donnée.

    Basé sur InventoryMovement avec movement_type = VENDOR_ASSIGN :

      - totaux par trimestre (T1..T4)
      - totaux par semestre (S1, S2)
      - total annuel

    Utile pour un dashboard vendeur ou pour l’admin/manager.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Statistiques d’allocations de stock pour un vendeur (annuel)",
        operation_description=(
            "Retourne les quantités assignées à un vendor (movement_type=VENDOR_ASSIGN) pour une année donnée, "
            "agrégées par trimestre (T1..T4), par semestre (S1,S2) et en total annuel."
        ),
        manual_parameters=[
            openapi.Parameter(
                "year",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                description="Année cible (par défaut: année courante)",
            ),
        ],
        tags=["Vendors", "Inventaire"],
        responses={200: "OK", 400: "Paramètre invalide", 404: "Vendor introuvable"},
    )
    def get(self, request, vendor_id: int):
        getf = request.GET.get

        try:
            year = int(getf("year") or timezone.now().year)
        except ValueError:
            return Response({"detail": "Paramètre 'year' invalide."}, status=400)

        # Vérifier que le vendor existe (optionnel mais propre)
        try:
            Vendor.objects.get(pk=vendor_id)
        except Vendor.DoesNotExist:
            return Response({"detail": "Vendor introuvable."}, status=404)

        qs = (
            InventoryMovement.objects
            .filter(
                movement_type=MovementType.VENDOR_ASSIGN,
                vendor_id=vendor_id,
                occurred_at__year=year,
            )
            .annotate(qtr=ExtractQuarter("occurred_at"))
        )

        agg = qs.aggregate(
            trimestre_1=Sum("qty", filter=Q(qtr=1)),
            trimestre_2=Sum("qty", filter=Q(qtr=2)),
            trimestre_3=Sum("qty", filter=Q(qtr=3)),
            trimestre_4=Sum("qty", filter=Q(qtr=4)),
            semestre_1=Sum("qty", filter=Q(occurred_at__month__lte=6)),
            semestre_2=Sum("qty", filter=Q(occurred_at__month__gte=7)),
            annuel=Sum("qty"),
        )

        data = {
            "vendor_id": vendor_id,
            "year": year,
            "trimestriels": {
                "T1": agg["trimestre_1"] or 0,
                "T2": agg["trimestre_2"] or 0,
                "T3": agg["trimestre_3"] or 0,
                "T4": agg["trimestre_4"] or 0,
            },
            "semestres": {
                "S1": agg["semestre_1"] or 0,
                "S2": agg["semestre_2"] or 0,
            },
            "annuel": agg["annuel"] or 0,
        }
        return Response(data)

