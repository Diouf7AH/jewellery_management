from __future__ import annotations

import csv
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
# ---------- (facultatif) mixin réutilisé pour Excel ----------
from textwrap import dedent
from typing import Dict, Optional, Tuple

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import (Case, Count, DecimalField, ExpressionWrapper, F,
                              IntegerField, Q, Sum, Value, When)
from django.db.models.functions import Coalesce
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import get_template
from django.utils import timezone
from django.utils.dateparse import parse_date
from django_filters.rest_framework import DjangoFilterBackend
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from rest_framework import status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from xhtml2pdf import pisa

from backend.permissions import IsAdminOrManager
from backend.renderers import UserRenderer
# --- Inventaire
from inventory.models import Bucket, InventoryMovement, MovementType
from inventory.services import log_move
from purchase.services import _get_or_upsert_fournisseur, _recalc_totaux_achat
from stock.models import Stock
from store.models import Produit

# from .your_mixin_and_pagination_module import ExportXlsxMixin, AchatPagination
from .models import Achat, Fournisseur, Lot, ProduitLine
from .serializers import (AchatCancelSerializer, AchatCreateResponseSerializer,
                          AchatListSerializer, AchatSerializer,
                          ArrivageAdjustmentsInSerializer,
                          ArrivageCreateInSerializer,
                          ArrivageMetaUpdateInSerializer,
                          FournisseurSerializer, LotDisplaySerializer,
                          LotListSerializer)

logger = logging.getLogger(__name__)

# Create your views here.

# helpers fournis précédemment
# from services.stocks import allocate_arrival

allowed_roles = ['admin', 'manager', 'vendeur']

ZERO = Decimal("0.00")
TWOPLACES = Decimal('0.01')

class FournisseurGetView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Récupère les informations d'un fournisseur par son ID.",
        responses={
            200: FournisseurSerializer(),
            403: openapi.Response(description="Accès refusé"),
            404: openapi.Response(description="Fournisseur introuvable"),
        }
    )
    def get(self, request, pk, format=None):
        user_role = getattr(request.user.user_role, 'role', None)
        if user_role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        try:
            fournisseur = Fournisseur.objects.get(pk=pk)
        except Fournisseur.DoesNotExist:
            return Response({"detail": "Fournisseur not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = FournisseurSerializer(fournisseur)
        return Response(serializer.data, status=200)

# PUT: mise à jour complète (tous les champs doivent être fournis)
# PATCH: mise à jour partielle (champs optionnels)
# Swagger : la doc est affichée proprement pour chaque méthode
# Contrôle des rôles (admin, manager)
class FournisseurUpdateView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Met à jour complètement un fournisseur (remplace tous les champs).",
        request_body=FournisseurSerializer,
        responses={
            200: FournisseurSerializer(),
            400: "Requête invalide",
            403: "Accès refusé",
            404: "Fournisseur introuvable",
        }
    )
    def put(self, request, pk, format=None):
        return self.update_fournisseur(request, pk, partial=False)

    @swagger_auto_schema(
        operation_description="Met à jour partiellement un fournisseur (seuls les champs fournis sont modifiés).",
        request_body=FournisseurSerializer,
        responses={
            200: FournisseurSerializer(),
            400: "Requête invalide",
            403: "Accès refusé",
            404: "Fournisseur introuvable",
        }
    )
    def patch(self, request, pk, format=None):
        return self.update_fournisseur(request, pk, partial=True)

    def update_fournisseur(self, request, pk, partial):
        user_role = getattr(request.user.user_role, 'role', None)
        if user_role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        try:
            fournisseur = Fournisseur.objects.get(pk=pk)
        except Fournisseur.DoesNotExist:
            return Response({"detail": "Fournisseur not found"}, status=404)

        serializer = FournisseurSerializer(fournisseur, data=request.data, partial=partial)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=400)



class FournisseurListView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Liste tous les fournisseurs, avec option de recherche par nom ou téléphone via le paramètre `search`.",
        manual_parameters=[
            openapi.Parameter(
                'search', openapi.IN_QUERY,
                description="Nom ou téléphone à rechercher",
                type=openapi.TYPE_STRING
            )
        ],
        responses={200: FournisseurSerializer(many=True)}
    )
    def get(self, request):
        user_role = getattr(request.user.user_role, 'role', None)
        if user_role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        search = request.query_params.get('search', '')
        fournisseurs = Fournisseur.objects.all()
        if search:
            fournisseurs = fournisseurs.filter(
                Q(nom__icontains=search) | Q(prenom__icontains=search) | Q(telephone__icontains=search)
            )

        serializer = FournisseurSerializer(fournisseurs, many=True)
        return Response(serializer.data, status=200)



class FournisseurDeleteView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Supprime un fournisseur à partir de son ID.",
        responses={
            204: "Fournisseur supprimé avec succès",
            403: "Accès refusé",
            404: "Fournisseur introuvable",
        }
    )
    def delete(self, request, pk, format=None):
        role = getattr(request.user.user_role, 'role', None)
        if role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        try:
            fournisseur = Fournisseur.objects.get(pk=pk)
        except Fournisseur.DoesNotExist:
            return Response({"detail": "Fournisseur not found"}, status=404)

        fournisseur.delete()
        return Response({"message": "Fournisseur supprimé avec succès."}, status=204)



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
            width = max((len(str(c.value)) if c.value is not None else 0) for c in col) + 2
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(width, 50)


# ---------- Pagination ----------
class AchatPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200



class AchatListView(ExportXlsxMixin, APIView):
    """
    Liste paginée des achats (+ export Excel).
    Inclut : n° de lot, status, description, cancelled_by/at/reason.
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]

    @swagger_auto_schema(
        operation_summary="Lister les achats (paginé) + export Excel",
        manual_parameters=[
            openapi.Parameter("q", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Recherche (numero_achat, fournisseur nom/prénom/téléphone, lot_code)"),
            openapi.Parameter("fournisseur_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="Filtrer par fournisseur"),
            openapi.Parameter("produit_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="Filtrer par produit présent dans l'achat"),
            openapi.Parameter("bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                              description="(Optionnel) Filtrer par bijouterie si applicable"),
            openapi.Parameter("date_from", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="AAAA-MM-JJ (inclus)"),
            openapi.Parameter("date_to", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="AAAA-MM-JJ (inclus)"),
            openapi.Parameter("min_total", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Montant TTC minimum"),
            openapi.Parameter("max_total", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Montant TTC maximum"),
            openapi.Parameter("status", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Statut (si champ présent sur Achat)"),
            openapi.Parameter("ordering", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="Tri: -created_at (défaut), created_at, +/-montant_total_ttc, +/-numero_achat"),
            openapi.Parameter("page", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Numéro de page"),
            openapi.Parameter("page_size", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Taille de page"),
            openapi.Parameter("export", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="xlsx pour export Excel"),
        ],
        tags=["Achats"],
        responses={200: "OK", 403: "Accès refusé – admin/manager uniquement"}
    )
    def get(self, request):
        fields = {f.name for f in Achat._meta.get_fields()}

        qs = (
            Achat.objects
            .select_related("fournisseur", "cancelled_by")
            .prefetch_related("produits__produit", "produits__lots")  # ← lots
        )

        getf = request.GET.get

        # --- Recherche plein texte (inclut lot_code) ---
        q = (getf("q") or "").strip()
        if q:
            filt = (
                Q(fournisseur__nom__icontains=q) |
                Q(fournisseur__prenom__icontains=q) |
                Q(fournisseur__telephone__icontains=q) |
                Q(produits__lots__lot_code__icontains=q)
            )
            if "numero_achat" in fields:
                filt |= Q(numero_achat__icontains=q)
            qs = qs.filter(filt).distinct()

        # --- Filtres ---
        if getf("fournisseur_id"):
            qs = qs.filter(fournisseur_id=getf("fournisseur_id"))
        if getf("produit_id"):
            qs = qs.filter(produits__produit_id=getf("produit_id")).distinct()
        if getf("bijouterie_id") and "bijouterie" in fields:
            qs = qs.filter(bijouterie_id=getf("bijouterie_id"))

        # Dates
        def _d(s):
            try: return datetime.strptime(s, "%Y-%m-%d").date()
            except Exception: return None
        df = _d(getf("date_from") or "")
        dt = _d(getf("date_to") or "")
        if df: qs = qs.filter(created_at__date__gte=df)
        if dt: qs = qs.filter(created_at__date__lte=dt)

        # Totaux TTC
        def _dec(s):
            if not s: return None
            try: return Decimal(str(s))
            except (InvalidOperation, TypeError): return None
        min_total = _dec(getf("min_total"))
        max_total = _dec(getf("max_total"))
        if min_total is not None: qs = qs.filter(montant_total_ttc__gte=min_total)
        if max_total is not None: qs = qs.filter(montant_total_ttc__lte=max_total)

        # Statut
        if getf("status") and "status" in fields:
            qs = qs.filter(status=getf("status"))

        # --- Tri ---
        ordering = getf("ordering") or "-created_at"
        allowed = {"created_at","-created_at","montant_total_ttc","-montant_total_ttc","numero_achat","-numero_achat"}
        if ordering not in allowed or ("numero_achat" in ordering and "numero_achat" not in fields):
            ordering = "-created_at"
        qs = qs.order_by(ordering)

        # --- Export Excel ? ---
        if (getf("export") or "").lower() == "xlsx":
            qs_export = qs.annotate(nb_lignes=Count("produits"))

            # achat_id -> "LOT-..., LOT-..."
            lot_codes_by_achat = {}
            for a in qs_export:
                codes = set()
                for lp in a.produits.all():
                    for lot in lp.lots.all():
                        if lot.lot_code:
                            codes.add(lot.lot_code)
                lot_codes_by_achat[a.id] = ", ".join(sorted(codes))

            from openpyxl import Workbook
            wb = Workbook()
            ws = wb.active
            ws.title = "Achats"

            headers = [
                "id", "created_at", "numero_achat",
                "status", "description",
                "cancelled_by", "cancelled_at", "cancel_reason",
                "fournisseur_id", "fournisseur_nom", "fournisseur_prenom", "fournisseur_telephone",
                "montant_total_ht", "montant_total_tax", "montant_total_ttc",
                "nb_lignes",
                "lot_codes",
            ]
            ws.append(headers)

            for a in qs_export:
                f = a.fournisseur
                cancelled_by_display = None
                if getattr(a, "cancelled_by", None):
                    u = a.cancelled_by
                    cancelled_by_display = (u.get_full_name() or u.username)

                ws.append([
                    a.id,
                    getattr(a, "created_at", None),
                    getattr(a, "numero_achat", None) if "numero_achat" in fields else None,
                    getattr(a, "status", None) if "status" in fields else None,
                    getattr(a, "description", None) if "description" in fields else None,
                    cancelled_by_display if "cancelled_by" in fields else None,
                    getattr(a, "cancelled_at", None) if "cancelled_at" in fields else None,
                    getattr(a, "cancel_reason", None) if "cancel_reason" in fields else None,
                    getattr(f, "id", None) if f else None,
                    getattr(f, "nom", None) if f else None,
                    getattr(f, "prenom", None) if f else None,
                    getattr(f, "telephone", None) if f else None,
                    getattr(a, "montant_total_ht", None),
                    getattr(a, "montant_total_tax", None),
                    getattr(a, "montant_total_ttc", None),
                    getattr(a, "nb_lignes", None),
                    lot_codes_by_achat.get(a.id),
                ])

            self._autosize(ws)
            return self._xlsx_response(wb, "achats.xlsx")

        # --- Pagination + JSON (avec lots & champs d’annulation) ---
        paginator = AchatPagination()
        page = paginator.paginate_queryset(qs, request)
        data = AchatListSerializer(page, many=True).data
        return paginator.get_paginated_response(data)



class AchatDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Dashboard des achats filtré par période dynamique (en mois)",
        manual_parameters=[
            openapi.Parameter(
                'mois',
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                enum=[1, 3, 6, 12],
                default=3,
                description="Nombre de mois à remonter"
            )
        ],
        responses={200: openapi.Response(description="Statistiques + achats récents")}
    )
    def get(self, request):
        user_role = getattr(request.user.user_role, 'role', None)
        if user_role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        # Lire le paramètre "mois" dans l'URL, défaut = 3
        try:
            nb_mois = int(request.GET.get('mois', 3))
            nb_mois = max(1, min(nb_mois, 12))  # sécurise entre 1 et 12
        except ValueError:
            nb_mois = 3

        depuis = timezone.now() - relativedelta(months=nb_mois)

        achats = Achat.objects.filter(created_at__gte=depuis)

        stats = achats.aggregate(
            total_achats=Count('id'),
            montant_total_ht=Sum('montant_total_ht'),
            montant_total_ttc=Sum('montant_total_ttc')
        )

        achats_recents = achats.order_by('-created_at')[:10]
        achats_serializer = AchatSerializer(achats_recents, many=True)

        return Response({
            "periode": {
                "mois": nb_mois,
                "depuis": depuis.date().isoformat(),
                "jusqu_a": timezone.now().date().isoformat()
            },
            "statistiques": stats,
            "achats_recents": achats_serializer.data
        })




# --------------------------------------EXCEL AND CSV -----------------------------------------------
# ---------- helpers communs ----------
def _filter_and_annotate_lots(request):
    qs = (Lot.objects
          .select_related("achat", "achat__fournisseur")
          .prefetch_related("lignes__produit"))

    # Filtres
    date_min = request.GET.get("date_min")
    date_max = request.GET.get("date_max")
    fournisseur = request.GET.get("fournisseur")
    search = request.GET.get("search")
    ordering = request.GET.get("ordering") or "-received_at"

    if date_min:
        qs = qs.filter(received_at__date__gte=date_min)
    if date_max:
        qs = qs.filter(received_at__date__lte=date_max)
    if fournisseur:
        qs = qs.filter(achat__fournisseur__id=fournisseur)
    if search:
        qs = qs.filter(
            Q(numero_lot__icontains=search) |
            Q(description__icontains=search) |
            Q(achat__numero_achat__icontains=search) |
            Q(achat__fournisseur__nom__icontains=search)
        )

    poids_total_expr = ExpressionWrapper(
        F("lignes__quantite_total") * F("lignes__produit__poids"),
        output_field=DecimalField(max_digits=18, decimal_places=3)
    )
    poids_restant_expr = ExpressionWrapper(
        F("lignes__quantite_restante") * F("lignes__produit__poids"),
        output_field=DecimalField(max_digits=18, decimal_places=3)
    )

    qs = (qs
          .annotate(
              nb_lignes=Count("lignes", distinct=True),
              quantite_total=Sum("lignes__quantite_total", output_field=IntegerField()),
              quantite_restante=Sum("lignes__quantite_restante", output_field=IntegerField()),
              poids_total=Sum(poids_total_expr),
              poids_restant=Sum(poids_restant_expr),
          )
          .order_by(ordering))

    return qs



# ---------- CSV ----------
class LotExportCSVView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrManager]

    @swagger_auto_schema(
        operation_id="exportLotsCSV",
        operation_summary="Exporter la liste des lots en CSV (non paginé)",
        manual_parameters=[
            openapi.Parameter("date_min", openapi.IN_QUERY, type=openapi.TYPE_STRING, format="date"),
            openapi.Parameter("date_max", openapi.IN_QUERY, type=openapi.TYPE_STRING, format="date"),
            openapi.Parameter("fournisseur", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter("search", openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter("ordering", openapi.IN_QUERY, type=openapi.TYPE_STRING,
                              description="received_at, -received_at, numero_lot, nb_lignes, quantite_total, poids_total"),
        ],
        tags=["Achats / Arrivages"],
        responses={200: "CSV file"},
    )
    def get(self, request):
        qs = _filter_and_annotate_lots(request)

        # En-têtes CSV
        headers = [
            "numero_lot", "received_at", "numero_achat", "fournisseur",
            "nb_lignes", "quantite_total", "quantite_restante",
            "poids_total", "poids_restant",
            "frais_transport", "frais_douane", "description",
        ]

        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)

        for lot in qs:
            writer.writerow([
                lot.numero_lot,
                lot.received_at.isoformat(),
                getattr(lot.achat, "numero_achat", ""),
                getattr(lot.achat.fournisseur, "nom", "") if lot.achat and lot.achat.fournisseur else "",
                lot.nb_lignes or 0,
                lot.quantite_total or 0,
                lot.quantite_restante or 0,
                f"{(lot.poids_total or Decimal('0')).quantize(Decimal('0.001'))}",
                f"{(lot.poids_restant or Decimal('0')).quantize(Decimal('0.001'))}",
                f"{getattr(lot.achat, 'frais_transport', 0)}",
                f"{getattr(lot.achat, 'frais_douane', 0)}",
                lot.description or "",
            ])

        resp = StreamingHttpResponse(iter([buf.getvalue()]), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="lots_{timezone.localdate().isoformat()}.csv"'
        return resp



# ---------- EXCEL (.xlsx) ----------
class LotExportExcelView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrManager]

    @swagger_auto_schema(
        operation_id="exportLotsXLSX",
        operation_summary="Exporter la liste des lots en Excel (non paginé)",
        manual_parameters=[
            openapi.Parameter("date_min", openapi.IN_QUERY, type=openapi.TYPE_STRING, format="date"),
            openapi.Parameter("date_max", openapi.IN_QUERY, type=openapi.TYPE_STRING, format="date"),
            openapi.Parameter("fournisseur", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter("search", openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter("ordering", openapi.IN_QUERY, type=openapi.TYPE_STRING),
        ],
        tags=["Achats / Arrivages"],
        responses={200: "XLSX file"},
    )
    def get(self, request):
        # openpyxl doit être installé:  pip install openpyxl
        from openpyxl import Workbook
        from openpyxl.utils import get_column_letter

        qs = _filter_and_annotate_lots(request)

        wb = Workbook()
        ws = wb.active
        ws.title = "Lots"

        headers = [
            "numero_lot", "received_at", "numero_achat", "fournisseur",
            "nb_lignes", "quantite_total", "quantite_restante",
            "poids_total", "poids_restant",
            "frais_transport", "frais_douane", "description",
        ]
        ws.append(headers)

        for lot in qs:
            ws.append([
                lot.numero_lot,
                lot.received_at.isoformat(),
                getattr(lot.achat, "numero_achat", ""),
                getattr(lot.achat.fournisseur, "nom", "") if lot.achat and lot.achat.fournisseur else "",
                lot.nb_lignes or 0,
                lot.quantite_total or 0,
                lot.quantite_restante or 0,
                float(lot.poids_total or 0),
                float(lot.poids_restant or 0),
                float(getattr(lot.achat, "frais_transport", 0) or 0),
                float(getattr(lot.achat, "frais_douane", 0) or 0),
                lot.description or "",
            ])

        # Auto-width simple
        for col_idx, header in enumerate(headers, start=1):
            max_len = max(len(str(header)), *[len(str(c.value)) for c in ws.iter_cols(min_col=col_idx, max_col=col_idx, min_row=1, values_only=False)])
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 2, 60)

        out = BytesIO()
        wb.save(out)
        out.seek(0)

        resp = HttpResponse(
            out.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="lots_{timezone.localdate().isoformat()}.xlsx"'
        return resp
# -------------------------------------END EXCEL CSV ------------------------------------------------



class LotListView(ListAPIView):
    """
    GET /api/lots/?search=LOT-2025&date_min=2025-10-01&date_max=2025-10-31&fournisseur=12&ordering=-received_at
    """
    serializer_class = LotListSerializer
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]

    # Filtres simples via django-filter
    filterset_fields = {
        "achat__fournisseur__id": ["exact"],  # alias ci-dessous: ?fournisseur=ID
    }
    search_fields = ["numero_lot", "description", "achat__numero_achat", "achat__fournisseur__nom"]
    ordering_fields = ["received_at", "numero_lot", "nb_lignes", "quantite_total", "poids_total"]
    ordering = ["-received_at"]

    @swagger_auto_schema(
        operation_id="listLots",
        operation_summary="Lister les lots (avec totaux quantité/poids)",
        operation_description=dedent("""
            Filtres:
            - `search` : texte (numéro de lot, description, numéro d’achat, fournisseur)
            - `date_min` : YYYY-MM-DD (inclus)
            - `date_max` : YYYY-MM-DD (inclus)
            - `fournisseur` : ID du fournisseur (alias de `achat__fournisseur__id`)
            - `ordering` : `received_at`, `-received_at`, `numero_lot`, `nb_lignes`, `quantite_total`, `poids_total`
            - `page`, `page_size`

            Le poids cumulé est calculé par ligne ainsi :
            - si `lignes.poids_total` est renseigné → on l’utilise
            - sinon `lignes.quantite_total × lignes.produit.poids`
        """),
        manual_parameters=[
            openapi.Parameter(
                name="search", in_=openapi.IN_QUERY, required=False,
                type=openapi.TYPE_STRING, description="Recherche texte"
            ),
            openapi.Parameter(
                name="date_min", in_=openapi.IN_QUERY, required=False,
                type=openapi.TYPE_STRING, description="Date min (YYYY-MM-DD, inclus)"
            ),
            openapi.Parameter(
                name="date_max", in_=openapi.IN_QUERY, required=False,
                type=openapi.TYPE_STRING, description="Date max (YYYY-MM-DD, inclus)"
            ),
            openapi.Parameter(
                name="fournisseur", in_=openapi.IN_QUERY, required=False,
                type=openapi.TYPE_INTEGER, description="ID du fournisseur (alias)"
            ),
            openapi.Parameter(
                name="ordering", in_=openapi.IN_QUERY, required=False,
                type=openapi.TYPE_STRING,
                description="received_at, -received_at, numero_lot, nb_lignes, quantite_total, poids_total"
            ),
            openapi.Parameter(
                name="page", in_=openapi.IN_QUERY, required=False,
                type=openapi.TYPE_INTEGER, description="Numéro de page (>=1)"
            ),
            openapi.Parameter(
                name="page_size", in_=openapi.IN_QUERY, required=False,
                type=openapi.TYPE_INTEGER, description="Taille de page"
            ),
        ],
        tags=["Achats / Arrivages"],
    )
    def get(self, request, *args, **kwargs):
        # validation des dates (format ISO)
        date_min_s = request.query_params.get("date_min")
        date_max_s = request.query_params.get("date_max")
        for label, val in (("date_min", date_min_s), ("date_max", date_max_s)):
            if val and parse_date(val) is None:
                raise ValidationError({label: "Format invalide. Utiliser YYYY-MM-DD."})
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        qs = (Lot.objects
              .select_related("achat", "achat__fournisseur")
              .prefetch_related("lignes__produit"))

        # Filtres custom (date + alias fournisseur)
        date_min_s = self.request.query_params.get("date_min")
        date_max_s = self.request.query_params.get("date_max")
        fournisseur = self.request.query_params.get("fournisseur")

        if date_min_s:
            qs = qs.filter(received_at__date__gte=date_min_s)
        if date_max_s:
            qs = qs.filter(received_at__date__lte=date_max_s)
        if fournisseur:
            qs = qs.filter(achat__fournisseur__id=fournisseur)

        # Poids par ligne :
        # - utilise poids_total si présent
        # - sinon quantite_total * produit.poids (0 si l'un est NULL)
        poids_par_ligne = Case(
            When(lignes__poids_total__isnull=False, then=F("lignes__poids_total")),
            default=ExpressionWrapper(
                Coalesce(F("lignes__quantite_total"), Value(0)) *
                Coalesce(F("lignes__produit__poids"), Value(0.0)),
                output_field=DecimalField(max_digits=18, decimal_places=3)
            ),
            output_field=DecimalField(max_digits=18, decimal_places=3),
        )
        poids_restant_par_ligne = Case(
            When(lignes__poids_restant__isnull=False, then=F("lignes__poids_restant")),
            default=ExpressionWrapper(
                Coalesce(F("lignes__quantite_restante"), Value(0)) *
                Coalesce(F("lignes__produit__poids"), Value(0.0)),
                output_field=DecimalField(max_digits=18, decimal_places=3)
            ),
            output_field=DecimalField(max_digits=18, decimal_places=3),
        )

        qs = qs.annotate(
            nb_lignes=Count("lignes", distinct=True),
            quantite_total=Coalesce(Sum("lignes__quantite_total", output_field=IntegerField()), Value(0)),
            quantite_restante=Coalesce(Sum("lignes__quantite_restante", output_field=IntegerField()), Value(0)),
            poids_total=Coalesce(Sum(poids_par_ligne), Value(0.0)),
            poids_restant=Coalesce(Sum(poids_restant_par_ligne), Value(0.0)),
        )

        return qs
# -----------------------------End list------------------------------------------



# ------------------------------------Lots display-------------------------------
class LotDetailView(RetrieveAPIView):
    queryset = Lot.objects.select_related("achat", "achat__fournisseur").prefetch_related("lignes__produit")
    serializer_class = LotDisplaySerializer
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    lookup_field = "pk"

    @swagger_auto_schema(
        operation_id="getLotDisplay",
        operation_summary="Détail d’un lot (format affichage personnalisé)",
        tags=["Achats / Arrivages"],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
# -------------------------------End lot display---------------------------------

def generate_numero_lot() -> str:
    """Génère LOT-YYYYMMDD-XXXX ; XXXX repart à 0001 chaque jour."""
    today = timezone.localdate().strftime("%Y%m%d")
    prefix = f"LOT-{today}-"
    last = (Lot.objects
            .filter(numero_lot__startswith=prefix)
            .order_by("-numero_lot")
            .values_list("numero_lot", flat=True)
            .first())
    if last:
        try:
            seq = int(last.rsplit("-", 1)[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


class ArrivageCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    http_method_names = ["post"]

    @swagger_auto_schema(
        operation_id="createArrivage",
        operation_summary="Créer un arrivage (lot auto-numéroté) et initialiser l'inventaire",
        operation_description=(
            "Crée un Achat, un Lot avec un numéro auto (LOT-YYYYMMDD-XXXX), les lignes produits (quantités), "
            "pousse 100% du stock en Réserve, et valorise l'achat au gramme si fourni."
        ),
        request_body=ArrivageCreateInSerializer,
        responses={201: AchatCreateResponseSerializer, 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden"},
        tags=["Achats / Arrivages"],
    )
    @transaction.atomic
    def post(self, request):
        s = ArrivageCreateInSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        # Validations métier (produits, poids)
        lots_in = v["lots"]
        pids = {row["produit_id"] for row in lots_in}
        exists = set(Produit.objects.filter(id__in=pids).values_list("id", flat=True))
        missing = pids - exists
        if missing:
            return Response({"lots": f"Produit(s) introuvable(s): {sorted(list(missing))}."}, status=400)

        missing_weight = list(Produit.objects.filter(id__in=pids, poids__isnull=True).values_list("id", flat=True))
        if missing_weight:
            return Response({"lots": f"Produit(s) sans poids: {missing_weight}."}, status=400)

        # Fournisseur
        f = v["fournisseur"]
        fournisseur, _ = Fournisseur.objects.get_or_create(
            telephone=(f.get("telephone") or "").strip() or None,
            defaults={"nom": f["nom"], "prenom": f.get("prenom", "")},
        )

        # Achat
        numero_achat = f"ACH-{timezone.localdate().strftime('%Y%m%d')}-{timezone.now().strftime('%H%M%S')}"
        achat = Achat.objects.create(
            fournisseur=fournisseur,
            description=v.get("description", ""),
            frais_transport=v.get("frais_transport", Decimal("0")),
            frais_douane=v.get("frais_douane", Decimal("0")),
            numero_achat=numero_achat,
            status="confirmed",
        )

        # Lot (header) — génération auto + retry en cas de collision concurrente
        for _ in range(5):
            numero_lot = generate_numero_lot()
            try:
                lot = Lot.objects.create(
                    achat=achat,
                    numero_lot=numero_lot,
                    description=v.get("description", ""),
                    received_at=timezone.now(),
                )
                break
            except IntegrityError:
                # une autre requête a pris le même numéro juste avant ; on retente
                continue
        else:
            return Response({"detail": "Impossible de générer un numéro de lot unique."}, status=400)

        # Lignes + stock Réserve + valorisation
        total_ht = Decimal("0.00")
        produits_by_id = {p.id: p for p in Produit.objects.filter(id__in=pids).only("id", "poids", "nom")}

        for row in lots_in:
            produit = produits_by_id[row["produit_id"]]
            qte = int(row["quantite"])

            pl = ProduitLine.objects.create(
                lot=lot,
                produit=produit,
                prix_gramme_achat=row.get("prix_achat_gramme"),
                quantite_total=qte,
                quantite_restante=qte,
            )

            # Stock initial en Réserve
            Stock.objects.create(
                produit_line=pl, bijouterie=None,
                quantite_allouee=qte, quantite_disponible=qte,
            )

            # Valorisation HT au gramme
            if pl.prix_gramme_achat:
                poids_total_calc = Decimal(produit.poids) * Decimal(qte)
                total_ht += poids_total_calc * pl.prix_gramme_achat

        # Totaux Achat (ne PAS inclure 'montant_total_tax' si @property)
        achat.montant_total_ht = total_ht
        achat.montant_total_ttc = total_ht + Decimal(achat.frais_transport or 0) + Decimal(achat.frais_douane or 0)
        achat.save(update_fields=["montant_total_ht", "montant_total_ttc"])

        out = AchatCreateResponseSerializer(lot).data
        return Response(out, status=status.HTTP_201_CREATED)
    


# ========= VIEW ArrivageMetaUpdateView and ArrivageAdjustmentsView ======================
# ========== 1) META-ONLY ==========
class ArrivageMetaUpdateView(APIView):
    """
    PATCH /api/purchase/arrivage/<lot_id>/meta/
    
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    http_method_names = ["patch"]

    @swagger_auto_schema(
        operation_id="updateArrivageMeta",
        operation_summary="MAJ META d’un arrivage (Achat/Lot) — sans toucher quantités/prix",
        # operation_description=(
        #     "Met à jour les métadonnées : achat (fournisseur, description, frais) "
        #     "et lot (description, received_at). **Aucune** modification de quantités/prix/stock."
        # ),
        operation_description=dedent("""
                                    Met à jour les métadonnées : achat (fournisseur, description, frais)
                                    et lot (description, received_at). **Aucune** modification de quantités/prix/stock.
                                    
                                    Payloads d’exemple
                                    META-ONLY (PATCH)
                                    
                                    ```json
                                    {
                                        "achat": {
                                            "description": "MAJ description & frais",
                                            "frais_transport": 100.00,
                                            "frais_douane": 50.00,
                                            "fournisseur": { "id": 12 }
                                        },
                                        "lot": {
                                            "description": "Arrivage DXB révisé",
                                            "received_at": "2025-10-28T10:00:00Z"
                                        }
                                    }
                                    ```
                                    """),
        request_body=ArrivageMetaUpdateInSerializer,
        responses={200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found"},
        tags=["Achats / Arrivages"],
    )
    @transaction.atomic
    def patch(self, request, lot_id: int):
        lot = get_object_or_404(Lot.objects.select_related("achat", "achat__fournisseur"), pk=lot_id)
        achat = lot.achat

        s = ArrivageMetaUpdateInSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        # Achat
        if "achat" in v:
            a = v["achat"]
            if "fournisseur" in a:
                achat.fournisseur = _get_or_upsert_fournisseur(a["fournisseur"])
            if "description" in a:
                achat.description = a["description"]
            if "frais_transport" in a:
                achat.frais_transport = a["frais_transport"]
            if "frais_douane" in a:
                achat.frais_douane = a["frais_douane"]
            achat.save(update_fields=["fournisseur", "description", "frais_transport", "frais_douane"])

        # Lot
        if "lot" in v:
            lp = v["lot"]
            if "description" in lp:
                lot.description = lp["description"]
            if "received_at" in lp:
                lot.received_at = lp["received_at"]
            lot.save(update_fields=["description", "received_at"])

        # Recalc totaux (si frais modifiés)
        _recalc_totaux_achat(achat)

        return Response({"detail": "Meta mis à jour.", "lot_id": lot.id, "achat_id": achat.id}, status=200)


# ========== 2) ADJUSTMENTS ==========
class ArrivageAdjustmentsView(APIView):
    """
    POST /api/purchase/arrivage/<lot_id>/adjustments/
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    http_method_names = ["post"]

    @swagger_auto_schema(
        operation_id="arrivageAdjustments",
        operation_summary="Ajustements d’arrivage (mouvements d’inventaire normalisés)",
        # operation_description=(
        #     "**Ajouts**: PURCHASE_IN (nouvelle ligne) → EXTERNAL → RESERVED\n"
        #     "**Retraits**: CANCEL_PURCHASE (réduction ligne existante) → RESERVED → EXTERNAL\n"
        #     "Règles: réduction limitée au disponible en Réserve; aucune suppression si allocations bijouterie existent."
        # ),
        operation_description=dedent("""
                                    **Ajouts**: PURCHASE_IN (nouvelle ligne) → EXTERNAL → RESERVED\n
                                    **Retraits**: CANCEL_PURCHASE (réduction ligne existante) → RESERVED → EXTERNAL\n
                                    Règles: réduction limitée au disponible en Réserve; aucune suppression si allocations bijouterie existent.
                                    
                                    ADJUSTMENTS (POST)
                                    
                                    ```json
                                    {
                                    "actions": [
                                            {
                                            "type": "PURCHASE_IN",
                                            "produit_id": 55,
                                            "quantite": 30,
                                            "prix_achat_gramme": 42000.00,
                                            "reason": "Complément de réception"
                                            },
                                            {
                                            "type": "CANCEL_PURCHASE",
                                            "produit_line_id": 101,
                                            "quantite": 12,
                                            "reason": "Retour fournisseur (qualité)"
                                            }
                                        ]
                                    }
                                    ```
                                    """),
        request_body=ArrivageAdjustmentsInSerializer,
        responses={200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found"},
        tags=["Achats / Arrivages"],
    )
    @transaction.atomic
    def post(self, request, lot_id: int):
        lot = get_object_or_404(Lot.objects.select_related("achat"), pk=lot_id)
        achat = lot.achat

        s = ArrivageAdjustmentsInSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        actions = s.validated_data["actions"]

        for i, act in enumerate(actions):
            t = act.get("type")

            # ----- PURCHASE_IN (ajout ligne) -----
            if t == "PURCHASE_IN":
                pid = int(act["produit_id"])
                q   = int(act["quantite"])
                ppo = act.get("prix_achat_gramme")  # peut être None
                produit = get_object_or_404(Produit.objects.only("id", "poids"), pk=pid)

                # créer ligne
                pl = ProduitLine.objects.create(
                    lot=lot,
                    produit=produit,
                    prix_gramme_achat=ppo,
                    quantite_total=q,
                    quantite_restante=q,
                )
                # stock réserve
                Stock.objects.create(
                    produit_line=pl, bijouterie=None,
                    quantite_allouee=q, quantite_disponible=q,
                )
                # mouvement inventaire
                InventoryMovement.objects.create(
                    produit=produit,
                    movement_type=MovementType.PURCHASE_IN,
                    qty=q,
                    unit_cost=None,  # option: Decimal(produit.poids)*ppo si tu veux un coût unitaire pièce
                    lot=lot,
                    reason=act.get("reason") or "Ajout ligne (amendement)",
                    src_bucket=Bucket.EXTERNAL,
                    dst_bucket=Bucket.RESERVED,
                    achat=achat,
                    occurred_at=timezone.now(),
                    created_by=request.user,
                )

            # ----- CANCEL_PURCHASE (retrait partiel) -----
            elif t == "CANCEL_PURCHASE":
                pl_id = int(act["produit_line_id"])
                q     = int(act["quantite"])
                pl = get_object_or_404(ProduitLine.objects.select_related("produit", "lot"), pk=pl_id)

                if pl.lot_id != lot.id:
                    return Response(
                        {f"actions[{i}]": f"ProduitLine {pl_id} n'appartient pas au lot {lot.id}."}, status=400
                    )

                # refuse si allocations bijouterie existent
                if Stock.objects.filter(produit_line=pl, bijouterie__isnull=False, quantite_allouee__gt=0).exists():
                    return Response(
                        {f"actions[{i}]": f"Ligne {pl_id}: des allocations bijouterie existent (retrait interdit)."},
                        status=400
                    )

                reserve = Stock.objects.filter(produit_line=pl, bijouterie__isnull=True).first()
                disp = int(reserve.quantite_disponible or 0) if reserve else 0
                if q > disp:
                    return Response(
                        {f"actions[{i}]": f"Réduction {q} > disponible réserve ({disp}) pour ligne {pl_id}."},
                        status=400
                    )

                # appliquer la réduction
                pl.quantite_total = max(0, int((pl.quantite_total or 0) - q))
                pl.quantite_restante = max(0, int((pl.quantite_restante or 0) - q))
                pl.save(update_fields=["quantite_total", "quantite_restante"])

                if reserve:
                    reserve.quantite_allouee = max(0, int((reserve.quantite_allouee or 0) - q))
                    reserve.quantite_disponible = max(0, int((reserve.quantite_disponible or 0) - q))
                    reserve.save(update_fields=["quantite_allouee", "quantite_disponible"])

                # mouvement inventaire
                InventoryMovement.objects.create(
                    produit=pl.produit,
                    movement_type=MovementType.CANCEL_PURCHASE,
                    qty=q,
                    unit_cost=None,
                    lot=lot,
                    reason=act.get("reason") or "Retrait partiel (annulation achat)",
                    src_bucket=Bucket.RESERVED,
                    dst_bucket=Bucket.EXTERNAL,
                    achat=achat,
                    occurred_at=timezone.now(),
                    created_by=request.user,
                )

            else:
                return Response({f"actions[{i}]": f"Type inconnu: {t}"}, status=400)

        # Recalc totaux achat
        _recalc_totaux_achat(achat)
        return Response({"detail": "Ajustements appliqués.", "lot_id": lot.id, "achat_id": achat.id}, status=200)
# ========= AND VIEW ArrivageMetaUpdateView and ArrivageAdjustmentsView ======================



class AchatProduitGetOneView(APIView):  # renommé pour cohérence
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Récupère un achat spécifique avec ses produits associés.",
        responses={
            200: openapi.Response('Achat trouvé', AchatSerializer),
            404: "Achat non trouvé",
            403: "Accès refusé"
        }
    )
    @transaction.atomic
    def get(self, request, pk):
        user_role = getattr(request.user.user_role, 'role', None)
        if user_role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        try:
            achat = Achat.objects.select_related('fournisseur').prefetch_related('produits__produit').get(pk=pk)
            serializer = AchatSerializer(achat)
            return Response(serializer.data, status=200)

        except Achat.DoesNotExist:
            return Response({"detail": "Achat not found."}, status=404)

        except Exception as e:
            return Response({"detail": f"Erreur interne : {str(e)}"}, status=500)



# (Optionnel) log des mouvements ; no-op si le module n'existe pas
try:
    from inventory.services import log_move
except Exception:
    def log_move(**kwargs):
        return None


# ---------- Helpers rôles ----------
def _role_ok(user) -> bool:
    return bool(getattr(user, "user_role", None) and user.user_role.role in ["admin", "manager"])


# ---------- Helpers Stock (STRICT: jamais de création) ----------
def _has_lot_fk() -> bool:
    return any(getattr(f, "name", "") == "lot" for f in Stock._meta.get_fields())

def _reservation_key(produit_id: int, lot_id: Optional[int]) -> str:
    return f"RES-{produit_id}-{lot_id or 'NOLOT'}"

def _stock_row_qs(produit_id: int, bijouterie_id: Optional[int], lot_id: Optional[int]):
    qs = Stock.objects.select_for_update().filter(produit_id=produit_id)
    if bijouterie_id is None:
        qs = qs.filter(bijouterie__isnull=True, reservation_key=_reservation_key(produit_id, lot_id))
    else:
        qs = qs.filter(bijouterie_id=int(bijouterie_id))
    if _has_lot_fk():
        qs = qs.filter(lot_id=lot_id) if lot_id else qs.filter(lot__isnull=True)
    return qs

def _stock_decrement_strict(*, produit_id: int, bijouterie_id: Optional[int], delta_qty: int, lot_id: Optional[int]):
    if delta_qty <= 0:
        return
    qs = _stock_row_qs(produit_id, bijouterie_id, lot_id)
    updated = qs.filter(quantite__gte=delta_qty).update(quantite=F("quantite") - int(delta_qty))
    if not updated:
        raise ValidationError("Stock insuffisant ou ligne de stock introuvable.")

def _snapshot_stock(*, produit_id: int, lot_id: Optional[int]) -> Tuple[int, Dict[int, int]]:
    # Réservé
    r_qs = Stock.objects.filter(
        produit_id=produit_id,
        bijouterie__isnull=True,
        reservation_key=_reservation_key(produit_id, lot_id),
    )
    if _has_lot_fk():
        r_qs = r_qs.filter(lot_id=lot_id) if lot_id else r_qs.filter(lot__isnull=True)
    reserved = int(r_qs.aggregate(s=Sum("quantite"))["s"] or 0)

    # Bijouteries
    b_qs = Stock.objects.filter(produit_id=produit_id, bijouterie__isnull=False)
    if _has_lot_fk():
        b_qs = b_qs.filter(lot_id=lot_id) if lot_id else b_qs.filter(lot__isnull=True)
    pairs = list(
        b_qs.values_list("bijouterie_id").annotate(s=Sum("quantite")).values_list("bijouterie_id", "s")
    ) if b_qs.exists() else []
    return reserved, {int(k): int(v or 0) for k, v in pairs}


# ====================== VIEW ======================
class AchatCancelView(APIView):
    """
    Annule *intégralement* un achat :
      - déverse le stock (réservé + bijouteries) vers EXTERNAL,
      - journalise en CANCEL_PURCHASE,
      - interdit l'annulation si des quantités ont déjà été consommées (vente, ajustement…).
    Strict update : aucune création de ligne Stock.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        tags=["Achats"],
        operation_summary="Annuler un achat (mouvements inverse vers EXTERNAL)",
        operation_description=(
            "Annulation intégrale si *toutes* les quantités de l'achat sont encore disponibles "
            "dans le système (réservé et/ou bijouteries). Sinon → 409 avec détail.\n\n"
            "Entrée: `AchatCancelSerializer` (reason obligatoire, cancelled_at optionnel). "
            "Sortie: `AchatSerializer`."
        ),
        manual_parameters=[
            openapi.Parameter(
                name="achat_id",
                in_=openapi.IN_PATH,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="ID de l'achat à annuler",
            ),
        ],
        request_body=AchatCancelSerializer,
        responses={
            200: AchatSerializer,
            400: "Requête invalide",
            403: "Accès refusé",
            404: "Ressource introuvable",
            409: "Conflit (quantités manquantes empêchant l'annulation)",
        },
    )
    @transaction.atomic
    def post(self, request, achat_id: int):
        user = request.user
        if not _role_ok(user):
            return Response({"detail": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        achat = get_object_or_404(Achat, pk=achat_id)

        # déjà annulé ?
        if getattr(achat, "status", None) in ("cancelled", getattr(Achat, "STATUS_CANCELLED", "cancelled")):
            return Response({"detail": "Achat déjà annulé."}, status=status.HTTP_400_BAD_REQUEST)

        # valider payload
        ser = AchatCancelSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        reason = ser.validated_data["reason"]
        cancelled_at = ser.validated_data.get("cancelled_at") or timezone.now()

        # 1) Contrôle d'annulabilité : rien ne doit manquer
        # - sans lot : on exige on_hand == ap.quantite
        # - avec lots : on exige lot.quantite_restante == lot.quantite_total (pour chaque lot)
        errors = []
        lignes = list(achat.produits.select_related("produit").prefetch_related("lots"))

        for ap in lignes:
            produit_id = ap.produit_id
            if ap.lots.exists():
                for lot in ap.lots.all():
                    res, by_shop = _snapshot_stock(produit_id=produit_id, lot_id=lot.pk)
                    on_hand = res + sum(by_shop.values())
                    if on_hand != int(lot.quantite_total):
                        errors.append({
                            "produit_id": produit_id,
                            "lot_id": lot.pk,
                            "expected": int(lot.quantite_total),
                            "on_hand": int(on_hand),
                            "detail": "Quantités manquantes (lot).",
                        })
            else:
                res, by_shop = _snapshot_stock(produit_id=produit_id, lot_id=None)
                on_hand = res + sum(by_shop.values())
                if on_hand != int(ap.quantite):
                    errors.append({
                        "produit_id": produit_id,
                        "expected": int(ap.quantite),
                        "on_hand": int(on_hand),
                        "detail": "Quantités manquantes (ligne sans lot).",
                    })

        if errors:
            return Response(
                {"detail": "Annulation impossible: certaines quantités ont déjà été consommées.", "missing": errors},
                status=status.HTTP_409_CONFLICT,
            )

        # 2) Exécution : déverser tout vers EXTERNAL + log
        cancelled_lines = []

        for ap in lignes:
            produit = ap.produit

            if ap.lots.exists():
                for lot in ap.lots.all():
                    lot_id = lot.pk
                    res, by_shop = _snapshot_stock(produit_id=produit.pk, lot_id=lot_id)

                    # réservé -> EXTERNAL
                    if res > 0:
                        _stock_decrement_strict(produit_id=produit.pk, bijouterie_id=None, delta_qty=res, lot_id=lot_id)
                        log_move(
                            produit=produit, qty=int(res),
                            movement_type=MovementType.CANCEL_PURCHASE,
                            src_bucket=Bucket.RESERVED, dst_bucket=Bucket.EXTERNAL,
                            unit_cost=ap.prix_achat_gramme, achat=achat, achat_ligne=ap, lot=lot, user=user,
                            reason=f"Annulation achat: retour réservé (lot {lot.lot_code})",
                        )

                    # bijouteries -> EXTERNAL
                    for bid, q in by_shop.items():
                        if q <= 0:
                            continue
                        _stock_decrement_strict(produit_id=produit.pk, bijouterie_id=bid, delta_qty=int(q), lot_id=lot_id)
                        log_move(
                            produit=produit, qty=int(q),
                            movement_type=MovementType.CANCEL_PURCHASE,
                            src_bucket=Bucket.BIJOUTERIE, src_bijouterie_id=int(bid),
                            dst_bucket=Bucket.EXTERNAL,
                            unit_cost=ap.prix_achat_gramme, achat=achat, achat_ligne=ap, lot=lot, user=user,
                            reason=f"Annulation achat: retour bijouterie → externe (lot {lot.lot_code})",
                        )

                    # recaler le lot (on_hand = 0)
                    if lot.quantite_restante != 0:
                        lot.quantite_restante = 0
                        lot.save(update_fields=["quantite_restante"])

                    cancelled_lines.append({
                        "produit_id": produit.pk,
                        "lot_id": lot_id,
                        "returned": int(res + sum(by_shop.values())),
                    })
            else:
                res, by_shop = _snapshot_stock(produit_id=produit.pk, lot_id=None)

                if res > 0:
                    _stock_decrement_strict(produit_id=produit.pk, bijouterie_id=None, delta_qty=int(res), lot_id=None)
                    log_move(
                        produit=produit, qty=int(res),
                        movement_type=MovementType.CANCEL_PURCHASE,
                        src_bucket=Bucket.RESERVED, dst_bucket=Bucket.EXTERNAL,
                        unit_cost=ap.prix_achat_gramme, achat=achat, achat_ligne=ap, user=user,
                        reason="Annulation achat: retour réservé",
                    )

                for bid, q in by_shop.items():
                    if q <= 0:
                        continue
                    _stock_decrement_strict(produit_id=produit.pk, bijouterie_id=int(bid), delta_qty=int(q), lot_id=None)
                    log_move(
                        produit=produit, qty=int(q),
                        movement_type=MovementType.CANCEL_PURCHASE,
                        src_bucket=Bucket.BIJOUTERIE, src_bijouterie_id=int(bid),
                        dst_bucket=Bucket.EXTERNAL,
                        unit_cost=ap.prix_achat_gramme, achat=achat, achat_ligne=ap, user=user,
                        reason="Annulation achat: retour bijouterie → externe",
                    )

                cancelled_lines.append({
                    "produit_id": produit.pk,
                    "lot_id": None,
                    "returned": int(res + sum(by_shop.values())),
                })

        # 3) Statut d'achat
        achat.status = getattr(Achat, "STATUS_CANCELLED", "cancelled")
        achat.cancel_reason = reason
        achat.cancelled_at = cancelled_at
        achat.cancelled_by = user
        achat.save(update_fields=["status", "cancel_reason", "cancelled_at", "cancelled_by"])

        # (facultatif) si tu veux recalculer les totaux après (les lignes n'ont pas changé)
        # achat.update_total(save=True)

        return Response(
            {
                "message": "Achat annulé avec succès.",
                "achat": AchatSerializer(achat).data,
                "cancelled": cancelled_lines,
            },
            status=status.HTTP_200_OK
        )
        
# -----------------End cencel


class AchatProduitPDFView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Télécharge le PDF du détail d’un produit acheté.",
        manual_parameters=[
            openapi.Parameter('pk', openapi.IN_PATH, description="ID de l'achat-produit", type=openapi.TYPE_INTEGER)
        ],
        responses={
            200: openapi.Response(description="PDF généré avec succès"),
            404: "Produit d'achat non trouvé",
            403: "Accès refusé"
        }
    )
    def get(self, request, pk):
        role = getattr(request.user.user_role, 'role', None)
        if role not in ['admin', 'manager']:
            return Response({"message": "Access Denied"}, status=403)

        try:
            achat_produit = Lot.objects.select_related('achat', 'produit', 'fournisseur').get(pk=pk)
        except Lot.DoesNotExist:
            return Response({"detail": "AchatProduit non trouvé."}, status=404)

        context = {
            "p": achat_produit,
            "achat": achat_produit.achat,
            "fournisseur": achat_produit.fournisseur or achat_produit.achat.fournisseur
        }

        template = get_template("pdf/achat_produit_detail.html")
        html = template.render(context)

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename=AchatProduit_{achat_produit.id}.pdf'

        pisa_status = pisa.CreatePDF(html, dest=response)
        if pisa_status.err:
            return Response({"detail": "Erreur lors de la génération du PDF"}, status=500)

        return response


# class AchatPDFView(APIView):
#     permission_classes = [IsAuthenticated]
    
#     @swagger_auto_schema(
#         operation_description="Télécharge le PDF du détail d’un achat.",
#         manual_parameters=[
#             openapi.Parameter('pk', openapi.IN_PATH, description="ID de l'achat", type=openapi.TYPE_INTEGER)
#         ],
#         responses={
#             200: openapi.Response(description="PDF généré"),
#             404: "Achat non trouvé",
#             403: "Accès refusé"
#         }
#     )
#     def get(self, request, pk):
#         role = getattr(request.user.user_role, 'role', None)
#         if role not in ['admin', 'manager', 'vendeur']:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             # achat = Achat.objects.select_related('fournisseur').prefetch_related('produits__produit').get(pk=pk)
#             achat = AchatProduit.objects.select_related('fournisseur').prefetch_related('produits__produit').get(pk=pk)
#         except Achat.DoesNotExist:
#             return Response({"detail": "Achat non trouvé."}, status=404)

#         template_path = 'pdf/achat_detail.html'
#         context = {'achat': achat}
#         template = get_template(template_path)
#         html = template.render(context)

#         response = HttpResponse(content_type='application/pdf')
#         response['Content-Disposition'] = f'attachment; filename=Achat_{achat.numero_achat}.pdf'

#         pisa_status = pisa.CreatePDF(html, dest=response)

#         if pisa_status.err:
#             return Response({"detail": "Erreur lors de la génération du PDF"}, status=500)
#         return response


# class AchatUpdateAPIView(APIView):
#     @transaction.atomic
#     def put(self, request, achat_id):
#         # Récupérer l'achat et ses informations
#         try:
#             achat = Achat.objects.get(id=achat_id)
#             fournisseur_data = request.data.get('fournisseur')
#             produits_data = request.data.get('produits')  # Liste de produits à mettre à jour
#             achatproduit_data = request.data.get('achatproduit')
#             # Mettre à jour l'achat
#             achat.montant_total = request.data.get('montant_total', achat.montant_total)

#             # #recupere le id du achatproduit pour setter le stock precendant
#             # achat_produit_obj = AchatProduit.objects.get(achat_id=achat.id)
#             # print(achat_produit_obj.quantite)
#             # quantite_achat_update = achat_produit_obj.quantite

#             achat.save()

#             # Mettre à jour le fournisseur
#             if fournisseur_data:
#                 fournisseur = Fournisseur.objects.get(id=fournisseur_data['id'])
#                 fournisseur.nom = fournisseur_data.get('nom', fournisseur.nom)
#                 fournisseur.prenom = fournisseur_data.get('prenom', fournisseur.prenom)
#                 fournisseur.address = fournisseur_data.get('address', fournisseur.address)
#                 fournisseur.telephone = fournisseur_data.get('telephone', fournisseur.telephone)
#                 fournisseur.save()
#                 achat.fournisseur = fournisseur  # Associer à l'achat
#                 achat.save()


#             # Mettre à jour les produits et le stock
#             for produit_data in produits_data:
#                 produit = Produit.objects.get(id=produit_data['id'])

#                 #recupere le id du achatproduit pour setter le stock precendant
#                 achat_produit_obj = AchatProduit.objects.get(achat_id=achat, produit_id=produit)
#                 print(achat_produit_obj.produit_id)
#                 print(achat_produit_obj.quantite)
#                 quantite_achat_update = achat_produit_obj.quantite

#                 quantite_achat = produit_data['quantite']
#                 #Ceux-ci  la quantité enregistré et il faut le odifier pour mettre a jour le stock
#                 # prix_achat = produit_data['prix_achat']
#                 prix_achat_gramme = produit_data['prix_achat_gramme']
#                 tax = produit_data['tax']

#                 prix_achat = Decimal(prix_achat_gramme)*Decimal(produit.poids)
#                 sous_total_prix_achat = Decimal(prix_achat)*Decimal(quantite_achat)

#                 prix_achat = Decimal(prix_achat_gramme)*Decimal(produit.poids)
#                 sous_total_prix_achat = Decimal(prix_achat)*Decimal(quantite_achat)

#                 # Mettre à jour la table AchatProduit
#                 # achatProduit = AchatProduit.objects.get(id=achatproduit_data['id'])
#                 # achatProduit.produit=produit
#                 # achatProduit.quantite = quantite_achat
#                 # achatProduit.prix_achat_gramme = prix_achat_gramme
#                 # achatProduit.tax=tax
#                 # achatProduit.sous_total_prix_achat=sous_total_prix_achat
#                 # achatProduit.save()
#                 achat_produit, created = AchatProduit.objects.update_or_create(
#                     achat=achat,
#                     produit=produit,
#                     defaults={
#                         'fournisseur': fournisseur,
#                         'quantite': quantite_achat,
#                         'prix_achat_gramme': prix_achat_gramme,
#                         'prix_achat': prix_achat,
#                         'tax':tax,
#                         'sous_total_prix_achat': sous_total_prix_achat
#                         }
#                 )
#                 # Mettre à jour le stock
#                 stock, created = Stock.objects.get_or_create(produit=produit)
#                 #Appliquon la quantité pour que la mis a jour soit normal sans la table stock
#                 quantite_achat_normal = quantite_achat - quantite_achat_update
#                 #si cette diference est egale a 0 il n'aura pas de changement de stock
#                 if quantite_achat_normal > 0:
#                     quantite_achat_normal = quantite_achat_normal
#                     stock.quantite += quantite_achat_normal  # Ajouter la quantité achetée
#                     stock.save()
#                 # elif quantite_achat_normal == 0:
#                 #     stock.quantite = quantite_achat_update
#                 #     stock.save()
#                 else:
#                     quantite_achat_normal = quantite_achat_normal*(-1)
#                     stock.quantite -= quantite_achat_normal  # Ajouter la quantité achetée
#                     stock.save()
#                 # stock.quantite += quantite_achat  # Ajouter la quantité achetée
#                 # stock.save()

#                 achatproduit_serializer = AchatSerializer(achat)
#             return Response(achatproduit_serializer.data, status=status.HTTP_200_OK)

#         except Exception as e:
#             # Si une erreur se produit, toute la transaction est annulée.
#             return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

# django apiview put produit, pachat, suplier, produitsuplier and stock @transaction-atomic json out update pachat suplier all produit in achate



# class AchatUpdateAchatProduitAPIView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]
    
#     @transaction.atomic
#     def put(self, request, achat_id):
#         if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager' and request.user.user_role.role != 'vendeur':
#             return Response({"message": "Access Denied"})
#         try:
#             # Retrieve the Achat object to update
#             achat = Achat.objects.get(id=achat_id)
#             fournisseur_data = request.data.get('fournisseur')
#             # fournisseur_id = Achat.objects.get(fournisseur_id=achat.fournisseur_id)
#             # print(fournisseur_id)
#             # print(achat)
#             fournisseur_id=achat.fournisseur_id

#             achat.save()

#             if fournisseur_data:
#                 fournisseur = Fournisseur.objects.get(id=fournisseur_id)
#                 fournisseur.nom = fournisseur_data.get('nom', fournisseur.nom)
#                 fournisseur.prenom = fournisseur_data.get('prenom', fournisseur.prenom)
#                 fournisseur.address = fournisseur_data.get('address', fournisseur.address)
#                 fournisseur.telephone = fournisseur_data.get('telephone', fournisseur.telephone)
#                 fournisseur.save()
#                 achat.fournisseur = fournisseur  # Associer à l'achat
#                 achat.save()
#             # except Achat.DoesNotExist:
#             #     return Response({"error": "Achat not found"}, status=status.HTTP_404_NOT_FOUND)

#             # Deserialize the incoming data
#             # serializer = AchatSerializer(achat, data=request.data)
#             # if serializer.is_valid():
#             #     # Update Achat fields
#             #     serializer.save()


#             # # Mettre à jour le fournisseur
#             # if fournisseur_data:
#             #     fournisseur = Fournisseur.objects.get(id=fournisseur_data['id'])
#             #     fournisseur.nom = fournisseur_data.get('nom', fournisseur.nom)
#             #     fournisseur.prenom = fournisseur_data.get('prenom', fournisseur.prenom)
#             #     fournisseur.address = fournisseur_data.get('address', fournisseur.address)
#             #     fournisseur.telephone = fournisseur_data.get('telephone', fournisseur.telephone)
#             #     fournisseur.save()
#             #     achat.fournisseur = fournisseur  # Associer à l'achat
#             #     achat.save()

#             # Loop through the products in the 'produits' field
#             montant_total = 0
#             for produit_data in request.data.get('produits', []):
#                 produit_id = produit_data.get('produit', {}).get('id')
#                 quantite = produit_data.get('quantite')
#                 prix_achat_gramme = produit_data.get('prix_achat_gramme')
#                 tax = produit_data.get('tax')
                
                
#                 # print(produit_data)
#                 if produit_id and quantite is not None:
#                     # Check if the produit exists
#                     try:
#                         produit = Produit.objects.get(id=produit_id)

#                     except Produit.DoesNotExist:
#                         return Response({"error": f"Produit with id {produit_id} not found"}, status=status.HTTP_400_BAD_REQUEST)


#                     #recupere le id du achatproduit pour setter le stock precendant
#                     achat_produit_obj = AchatProduit.objects.get(achat_id=achat, produit_id=produit)
#                     # print(achat_produit_obj.produit_id)
#                     # print(achat_produit_obj.quantite)
#                     quantite_achat_update = achat_produit_obj.quantite

#                     quantite_achat = produit_data['quantite']
#                     #Ceux-ci  la quantité enregistré et il faut le odifier pour mettre a jour le stock
#                     # prix_achat = produit_data['prix_achat']
#                     # prix_achat_gramme = produit_data['prix_achat_gramme']
#                     # tax = produit_data['tax']

#                     # prix_achat = Decimal(prix_achat_gramme)*Decimal(produit.poids)
#                     # sous_total_prix_achat = Decimal(prix_achat)*Decimal(quantite_achat)

#                     # prix_achat = Decimal(prix_achat_gramme)*Decimal(produit.poids)
#                     # sous_total_prix_achat = Decimal(prix_achat)*Decimal(quantite_achat)


#                     # # Update the stock for the produit
#                     # stock, created = Stock.objects.get_or_create(produit=produit)
#                     # stock.quantite += quantite  # Assuming a reduction in stock
#                     # stock.save()

#                     # Add or update the AchatProduit entry
#                     achat_produit, created = AchatProduit.objects.update_or_create(
#                         achat=achat,
#                         produit=produit,
#                         fournisseur=fournisseur,
#                         defaults={
#                             'quantite': quantite_achat,
#                             'prix_achat_gramme': prix_achat_gramme,
#                             # 'prix_achat': prix_achat,
#                             'tax':tax,
#                         }
#                     )
#                     poids = produit.poids
#                     achat_produit.sous_total_prix_achat = Decimal(prix_achat_gramme)*Decimal(quantite_achat)*Decimal(poids)
#                     montant_total += achat_produit.sous_total_prix_achat + achat_produit.tax
#                     achat_produit.save()
#                     achat.montant_total = montant_total
#                     achat.save()
#                     # montant_total = 0
#                     # Mettre à jour le stock
#                     stock, created = Stock.objects.get_or_create(produit=produit)
#                     #Appliquon la quantité pour que la mis a jour soit normal sans la table stock
#                     quantite_achat_normal = quantite_achat - quantite_achat_update
#                     #si cette diference est egale a 0 il n'aura pas de changement de stock
#                     if quantite_achat_normal > 0:
#                         quantite_achat_normal = quantite_achat_normal
#                         stock.quantite += quantite_achat_normal  # Ajouter la quantité achetée
#                         stock.save()
#                     # elif quantite_achat_normal == 0:
#                     #     stock.quantite = quantite_achat_update
#                     #     stock.save()
#                     else:
#                         quantite_achat_normal = quantite_achat_normal*(-1)
#                         stock.quantite -= quantite_achat_normal  # Ajouter la quantité achetée
#                         stock.save()
#                     # stock.quantite += quantite_achat  # Ajouter la quantité achetée
#                     # stock.save()

#             # Return the updated achat with the produits
#             updated_achat = Achat.objects.prefetch_related('produits').get(id=achat.id)
#             updated_achat_serializer = AchatSerializer(updated_achat)
#             return Response(updated_achat_serializer.data, status=status.HTTP_200_OK)

#         except Achat.DoesNotExist:
#             return Response({"error": "Achat not found"}, status=status.HTTP_404_NOT_FOUND)
#             # return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
