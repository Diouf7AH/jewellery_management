from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
# ---------- (facultatif) mixin réutilisé pour Excel ----------
from io import BytesIO
from textwrap import dedent
from typing import Dict, Optional, Tuple

from dateutil.relativedelta import relativedelta
from django.core.exceptions import MultipleObjectsReturned, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q, Sum, UniqueConstraint
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
# import phonenumbers
# from phonenumbers import PhoneNumber
from django.template.loader import get_template
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from xhtml2pdf import pisa

from backend.permissions import IsAdminOrManager
from backend.renderers import UserRenderer
# --- Inventaire
from inventory.models import Bucket, InventoryMovement, MovementType
from inventory.services import log_move  # ta fonction utilitaire
# ⚙️ services que tu as (ou à mettre) dans purchase/services.py
# from purchase.services import create_purchase, rebase_purchase
from purchase.utils import \
    _auto_decrement_any_bucket_with_trace as \
    _dec_auto  # <- helpers stock (exact/auto)
from purchase.utils import _decrement_bucket as _dec_exact
from stock.models import Stock
from store.models import Bijouterie, Produit

# from .your_mixin_and_pagination_module import ExportXlsxMixin, AchatPagination
from .models import Achat, Fournisseur, Lot
from .serializers import (AchatCancelSerializer, AchatCreateResponseSerializer,
                          AchatCreateSerializer, AchatListSerializer,
                          AchatSerializer, AchatUpdateSerializer,
                          FournisseurSerializer,
                          StockReserveAffectationSerializer)
from .utils import _auto_decrement_any_bucket_with_trace, _decrement_bucket

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


# # =============== LIST VIEW ===============
# class AchatListView(ExportXlsxMixin, APIView):
#     """
#     Liste paginée des achats (+ export Excel).

#     Filtres disponibles (query params) :
#       - q : recherche plein texte (numero_achat, fournisseur.nom/prenom/téléphone)
#       - fournisseur_id : ID fournisseur
#       - produit_id : ID produit contenu dans au moins une ligne de l’achat
#       - bijouterie_id : (si tu rattaches l’achat à une bijouterie, sinon ignoré)
#       - date_from, date_to : AAAA-MM-JJ sur created_at (inclus)
#       - min_total, max_total : borne sur montant_total_ttc
#       - status : si ton modèle contient un champ `status` (sinon ignoré)
#       - ordering : -created_at (défaut), created_at, -montant_total_ttc, montant_total_ttc, numero_achat, -numero_achat
#       - export=xlsx : renvoie un fichier Excel (désactive la pagination)
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]

#     @swagger_auto_schema(
#         operation_summary="Lister les achats (paginé) + export Excel",
#         manual_parameters=[
#             openapi.Parameter("q", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                               description="Recherche (numero_achat, fournisseur nom/prénom/téléphone)"),
#             openapi.Parameter("fournisseur_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
#                               description="Filtrer par fournisseur"),
#             openapi.Parameter("produit_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
#                               description="Filtrer par produit présent dans l'achat"),
#             openapi.Parameter("bijouterie_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
#                               description="(Optionnel) Filtrer par bijouterie si applicable"),
#             openapi.Parameter("date_from", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                               description="AAAA-MM-JJ (inclus)"),
#             openapi.Parameter("date_to", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                               description="AAAA-MM-JJ (inclus)"),
#             openapi.Parameter("min_total", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                               description="Montant TTC minimum"),
#             openapi.Parameter("max_total", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                               description="Montant TTC maximum"),
#             openapi.Parameter("status", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                               description="Statut (si champ présent sur Achat)"),
#             openapi.Parameter("ordering", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                               description="Tri: -created_at (défaut), created_at, +/-montant_total_ttc, +/-numero_achat"),
#             openapi.Parameter("page", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Numéro de page"),
#             openapi.Parameter("page_size", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Taille de page"),
#             openapi.Parameter("export", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="xlsx pour export Excel"),
#         ],
#         tags=["Achats"],
#         responses={
#             200: "OK",
#             403: openapi.Response(description="Accès refusé – réservé aux rôles admin/manager")
#         }
#     )
#     def get(self, request):
#         qs = (
#             Achat.objects
#             .select_related("fournisseur")
#             .prefetch_related("produits__produit")  # lignes + produit
#             .all()
#         )

#         getf = request.GET.get

#         # ---- Recherche plein texte ----
#         q = getf("q")
#         if q:
#             q = q.strip()
#             # sécuriser: numero_achat peut ne pas exister partout
#             fields = {f.name for f in Achat._meta.get_fields()}
#             has_numero = "numero_achat" in fields
#             filt = (
#                 Q(fournisseur__nom__icontains=q) |
#                 Q(fournisseur__prenom__icontains=q) |
#                 Q(fournisseur__telephone__icontains=q)
#             )
#             if has_numero:
#                 filt |= Q(numero_achat__icontains=q)
#             qs = qs.filter(filt)

#         # ---- Filtres simples ----
#         if getf("fournisseur_id"):
#             qs = qs.filter(fournisseur_id=getf("fournisseur_id"))

#         if getf("produit_id"):
#             qs = qs.filter(produits__produit_id=getf("produit_id")).distinct()

#         if getf("bijouterie_id"):
#             # à activer si ton modèle Achat a un lien direct vers une bijouterie
#             qs = qs.filter(bijouterie_id=getf("bijouterie_id"))

#         # Dates
#         def _parse_date(s: str):
#             try:
#                 return datetime.strptime(s, "%Y-%m-%d")
#             except Exception:
#                 return None

#         df = _parse_date(getf("date_from") or "")
#         dt = _parse_date(getf("date_to") or "")
#         if df:
#             qs = qs.filter(created_at__date__gte=df.date())
#         if dt:
#             qs = qs.filter(created_at__date__lte=dt.date())

#         # Totaux TTC
#         def _dec(s: str | None) -> Decimal | None:
#             if not s:
#                 return None
#             try:
#                 return Decimal(str(s))
#             except (InvalidOperation, TypeError):
#                 return None

#         min_total = _dec(getf("min_total"))
#         max_total = _dec(getf("max_total"))
#         if min_total is not None:
#             qs = qs.filter(montant_total_ttc__gte=min_total)
#         if max_total is not None:
#             qs = qs.filter(montant_total_ttc__lte=max_total)

#         # Statut (si présent)
#         if getf("status") and "status" in {f.name for f in Achat._meta.get_fields()}:
#             qs = qs.filter(status=getf("status"))

#         # ---- Tri ----
#         ordering = getf("ordering") or "-created_at"
#         allowed = {"created_at", "-created_at",
#                    "montant_total_ttc", "-montant_total_ttc",
#                    "numero_achat", "-numero_achat"}
#         if ordering not in allowed:
#             ordering = "-created_at"
#         # si numero_achat n'existe pas dans le modèle, on retombe sur created_at
#         if "numero_achat" in ordering and "numero_achat" not in {f.name for f in Achat._meta.get_fields()}:
#             ordering = "-created_at"
#         qs = qs.order_by(ordering)

#         # ---- Export Excel ? ----
#         if (getf("export") or "").lower() == "xlsx":
#             # Une ligne par achat
#             qs_export = (
#                 qs.annotate(nb_lignes=Count("produits"))
#             )
#             wb = Workbook()
#             ws = wb.active
#             ws.title = "Achats"

#             headers = [
#                 "id", "created_at", "numero_achat",
#                 "fournisseur_id", "fournisseur_nom", "fournisseur_prenom", "fournisseur_telephone",
#                 "montant_total_ht", "montant_total_tax", "montant_total_ttc",
#                 "nb_lignes",
#             ]
#             ws.append(headers)

#             for a in qs_export:
#                 f = a.fournisseur
#                 ws.append([
#                     a.id,
#                     getattr(a, "created_at", None),
#                     getattr(a, "numero_achat", None),
#                     getattr(f, "id", None) if f else None,
#                     getattr(f, "nom", None) if f else None,
#                     getattr(f, "prenom", None) if f else None,
#                     getattr(f, "telephone", None) if f else None,
#                     getattr(a, "montant_total_ht", None),
#                     getattr(a, "montant_total_tax", None),
#                     getattr(a, "montant_total_ttc", None),
#                     getattr(a, "nb_lignes", None),
#                 ])

#             self._autosize(ws)
#             return self._xlsx_response(wb, "achats.xlsx")

#         # ---- Pagination + JSON ----
#         paginator = AchatPagination()
#         page = paginator.paginate_queryset(qs, request)
#         data = AchatSerializer(page, many=True).data
#         return paginator.get_paginated_response(data)

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



# # (Optionnel) log des mouvements ; no-op si le module n'existe pas
# try:
#     from inventory.services import log_move
# except Exception:
#     def log_move(**kwargs):
#         return None


# # ---------- Helpers ----------
# def _role_ok(user) -> bool:
#     return bool(getattr(user, "user_role", None) and user.user_role.role in ["admin", "manager"])


# def _stock_increment(
#     *,
#     produit_id: int,
#     bijouterie_id: Optional[int],
#     delta_qty: int,
#     lot_id: Optional[int] = None,
# ):
#     """
#     Incrémente un bucket de stock :
#       - bijouterie_id=None  -> stock réservé (bijouterie=NULL) + reservation_key='RES-<produit_id>-<lot|NOLOT>'
#       - sinon               -> stock attribué à la bijouterie.
#     Compatible MySQL via reservation_key.
#     Si Stock.lot existe, on le renseigne pour la traçabilité.
#     """
#     if delta_qty <= 0:
#         return None

#     # détecter dynamiquement la présence du champ 'lot'
#     has_lot_fk = any(getattr(f, "name", "") == "lot" for f in Stock._meta.get_fields())

#     if bijouterie_id is None:
#         reservation_key = f"RES-{produit_id}-{lot_id or 'NOLOT'}"
#         get_or_create_kwargs = dict(
#             produit_id=produit_id,
#             bijouterie=None,
#             reservation_key=reservation_key,
#             defaults={"quantite": 0, "is_reserved": True},
#         )
#         if has_lot_fk:
#             get_or_create_kwargs["lot_id"] = lot_id
#         stock, _ = (
#             Stock.objects.select_for_update()
#             .get_or_create(**get_or_create_kwargs)
#         )
#     else:
#         # valider la bijouterie
#         get_object_or_404(Bijouterie, pk=int(bijouterie_id))
#         get_or_create_kwargs = dict(
#             produit_id=produit_id,
#             bijouterie_id=int(bijouterie_id),
#             defaults={"quantite": 0, "is_reserved": False},
#         )
#         if has_lot_fk:
#             get_or_create_kwargs["lot_id"] = lot_id
#         stock, _ = (
#             Stock.objects.select_for_update()
#             .get_or_create(**get_or_create_kwargs)
#         )

#     Stock.objects.filter(pk=stock.pk).update(quantite=F("quantite") + int(delta_qty))
#     stock.refresh_from_db(fields=["quantite"])
#     return stock
# # ------------------------------




# # (Optionnel) log des mouvements ; no-op si le module n'existe pas
# try:
#     from inventory.services import log_move
# except Exception:
#     def log_move(**kwargs):
#         return None

# # ----------------- Helpers locaux -----------------
# def _role_ok(user) -> bool:
#     return bool(getattr(user, "user_role", None) and user.user_role.role in ["admin", "manager"])


# def _stock_increment(*, produit_id: int, bijouterie_id: int | None, delta_qty: int, lot_id: int | None = None) -> Stock:
#     """
#     Incrémente le stock en PIÈCES (jamais 0 à la création).
#     Réserve si bijouterie_id=None, sinon boutique.
#     """
#     if delta_qty is None or int(delta_qty) <= 0:
#         return None  # on ignore les 0 ou négatifs

#     if bijouterie_id is not None:
#         get_object_or_404(Bijouterie, pk=int(bijouterie_id))

#     lookup = {
#         "produit_id": int(produit_id),
#         "bijouterie_id": int(bijouterie_id) if bijouterie_id is not None else None,
#         "lot_id": int(lot_id) if lot_id is not None else None,
#     }

#     with transaction.atomic():
#         st = Stock.objects.select_for_update().filter(**lookup).first()
#         if st is None:
#             try:
#                 # ✅ création déjà VALIDE (quantite > 0)
#                 st = Stock.objects.create(**lookup, quantite=int(delta_qty))
#             except IntegrityError:
#                 # collision rare -> reprendre puis increment
#                 st = Stock.objects.select_for_update().get(**lookup)
#                 Stock.objects.filter(pk=st.pk).update(quantite=F("quantite") + int(delta_qty))
#                 st.refresh_from_db(fields=["quantite"])
#         else:
#             Stock.objects.filter(pk=st.pk).update(quantite=F("quantite") + int(delta_qty))
#             st.refresh_from_db(fields=["quantite"])
#         return st


# # =========================
# #       CREATE VIEW
# # =========================
# class AchatCreateView(APIView):
#     """
#     Crée un achat + lots (optionnels) et met à jour les stocks :
#       - Affectation par **lot** : ventilation vers des bijouteries, le reste va en **RÉSERVE**.
#       - Affectation **directe** (sans lot) : ventilation au niveau de la ligne, le reste va en **RÉSERVE**.
#       - **Tout réservé** : aucune affectation fournie -> tout va en **RÉSERVE**.

#     Règles (pièces uniquement) :
#       - Somme(lots.quantite) == quantite de la ligne (si lots).
#       - Somme(affectations.quantite) ≤ quantite (ligne/lot).
#       - Stock crédité :
#           • Bijouterie : (produit, bijouterie, lot) ; is_reserved=False
#           • Réserve    : (produit, bijouterie=NULL, lot) ; is_reserved=True
#       - Mouvement : MovementType.PURCHASE_IN (src=EXTERNAL → dst=BIJOUTERIE/RESERVED).
#     """
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Créer un achat (lots, affectation directe, réservé)",
#         operation_description=dedent("""
#         Crée un achat fournisseur, des lots (optionnels) et met à jour les stocks (bijouteries / réserve).

#         ## Affectation par lot
#         ```json
#         {
#           "fournisseur": {"nom":"Diop","prenom":"Abdou","telephone":"770000000","address":"Dakar"},
#           "produits":[
#             {
#               "produit": 12,
#               "quantite": 50,
#               "prix_achat_gramme": "4500.00",
#               "lots": [
#                 {
#                   "lot_code": "LOT-A1",
#                   "quantite": 30,
#                   "affectations": [
#                     {"bijouterie_id": 2, "quantite": 12},
#                     {"bijouterie_id": 5, "quantite": 10}
#                   ]
#                 },
#                 {
#                   "lot_code": null,
#                   "quantite": 20,
#                   "affectations": [
#                     {"bijouterie_id": 2, "quantite": 15}
#                   ]
#                 }
#               ]
#             }
#           ],
#           "frais_transport": "0.00",
#           "frais_douane": "0.00"
#         }
#         ```

#         ## Affectation directe (sans lots)
#         ```json
#         {
#           "fournisseur": {"nom":"Kane","prenom":"Moussa","telephone":"780000000"},
#           "produits":[
#             {
#               "produit": 34,
#               "quantite": 8,
#               "prix_achat_gramme": "5200.00",
#               "affectations": [
#                 {"bijouterie_id": 3, "quantite": 5},
#                 {"bijouterie_id": 7, "quantite": 1}
#               ]
#             }
#           ]
#         }
#         ```
#         """),
#         request_body=AchatCreateSerializer,
#         responses={201: openapi.Response("Création réussie", schema=AchatSerializer)},
#         tags=["Achats"],
#     )
#     @transaction.atomic
#     def post(self, request):
#         # 0) ACL
#         if not _role_ok(request.user):
#             return Response({"detail": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

#         # 1) Valider payload
#         ser = AchatCreateSerializer(data=request.data)
#         ser.is_valid(raise_exception=True)
#         data = ser.validated_data

#         # 2) Upsert fournisseur (par téléphone)
#         f = data["fournisseur"]
#         fournisseur, _ = Fournisseur.objects.get_or_create(
#             telephone=f["telephone"],
#             defaults={"nom": f.get("nom", ""), "prenom": f.get("prenom", ""), "address": f.get("address", "")},
#         )

#         # 3) Créer l'achat
#         achat = Achat.objects.create(
#             fournisseur=fournisseur,
#             description=f.get("address", ""),
#             frais_transport=data.get("frais_transport", Decimal("0.00")),
#             frais_douane=data.get("frais_douane", Decimal("0.00")),
#         )

#         # 4) Traiter chaque ligne produit
#         now = timezone.now()
#         for line in data["produits"]:
#             produit_id = int(line["produit"])
#             produit = get_object_or_404(Produit, pk=produit_id)

#             q_line = int(line["quantite"])
#             prix_gramme = line["prix_achat_gramme"]  # Decimal
#             lots = line.get("lots") or []
#             affs = line.get("affectations") or []

#             # ---- MODE A : avec lots
#             if lots:
#                 for l in lots:
#                     lot_code_input = (l.get("lot_code") or "").strip().upper() or None
#                     lot_qty = int(l["quantite"])

#                     # (Option valorisation) poids = lot_qty * produit.poids (si dispo)
#                     try:
#                         poids_unitaire = getattr(produit, "poids", None)
#                         if poids_unitaire is None:
#                             poids_total = Decimal("0.000")
#                         else:
#                             poids_total = (Decimal(lot_qty) * Decimal(poids_unitaire)).quantize(Decimal("0.000"))
#                     except Exception:
#                         poids_total = Decimal("0.000")

#                     lot = Lot(
#                         achat=achat,
#                         produit=produit,
#                         lot_code=lot_code_input,
#                         poids_total=poids_total,
#                         poids_restant=poids_total,
#                         prix_achat_gramme=prix_gramme,
#                         commentaire="Créé via AchatCreateView",
#                     )
#                     try:
#                         lot.save()
#                     except IntegrityError:
#                         lot.lot_code = None
#                         lot.save()

#                     # Ventilation vers bijouteries
#                     somme_aff = 0
#                     for a in (l.get("affectations") or []):
#                         bid = int(a["bijouterie_id"])
#                         q = int(a["quantite"])
#                         if q <= 0:
#                             continue
#                         somme_aff += q

#                         _stock_increment(produit_id=produit_id, bijouterie_id=bid, delta_qty=q, lot_id=lot.id)
#                         log_move(
#                             produit=produit,
#                             qty=q,
#                             movement_type=MovementType.PURCHASE_IN,
#                             src_bucket=Bucket.EXTERNAL,
#                             dst_bucket=Bucket.BIJOUTERIE,
#                             dst_bijouterie_id=bid,
#                             unit_cost=prix_gramme,
#                             achat=achat,
#                             lot=lot,
#                             user=request.user,
#                             reason=f"Arrivée achat (lot {lot.lot_code or lot.id} → bijouterie)",
#                             # occurred_at=now,
#                         )

#                     # Reste du lot -> RÉSERVE
#                     reste = lot_qty - somme_aff
#                     if reste > 0:
#                         _stock_increment(produit_id=produit_id, bijouterie_id=None, delta_qty=reste, lot_id=lot.id)
#                         log_move(
#                             produit=produit,
#                             qty=reste,
#                             movement_type=MovementType.PURCHASE_IN,
#                             src_bucket=Bucket.EXTERNAL,
#                             dst_bucket=Bucket.RESERVED,
#                             unit_cost=prix_gramme,
#                             achat=achat,
#                             lot=lot,
#                             user=request.user,
#                             reason=f"Arrivée achat (reste lot {lot.lot_code or lot.id} en réservé)",
#                             # occurred_at=now,
#                         )

#             # ---- MODE B : sans lots (affectations directes ou tout réservé)
#             else:
#                 somme_aff = 0
#                 for a in affs:
#                     bid = int(a["bijouterie_id"])
#                     q = int(a["quantite"])
#                     if q <= 0:
#                         continue
#                     somme_aff += q

#                     _stock_increment(produit_id=produit_id, bijouterie_id=bid, delta_qty=q, lot_id=None)
#                     log_move(
#                         produit=produit,
#                         qty=q,
#                         movement_type=MovementType.PURCHASE_IN,
#                         src_bucket=Bucket.EXTERNAL,
#                         dst_bucket=Bucket.BIJOUTERIE,
#                         dst_bijouterie_id=bid,
#                         unit_cost=prix_gramme,
#                         achat=achat,
#                         lot=None,
#                         user=request.user,
#                         reason="Arrivée achat (affectation directe)",
#                         # occurred_at=now,
#                     )

#                 # Reste -> RÉSERVE
#                 reste = q_line - somme_aff
#                 if reste > 0:
#                     _stock_increment(produit_id=produit_id, bijouterie_id=None, delta_qty=reste, lot_id=None)
#                     log_move(
#                         produit=produit,
#                         qty=reste,
#                         movement_type=MovementType.PURCHASE_IN,
#                         src_bucket=Bucket.EXTERNAL,
#                         dst_bucket=Bucket.RESERVED,
#                         unit_cost=prix_gramme,
#                         achat=achat,
#                         lot=None,
#                         user=request.user,
#                         reason="Arrivée achat (reste en réservé)",
#                         occurred_at=now,
#                     )

#         # 5) Totaux achat (silencieux si non implémenté)
#         try:
#             achat.update_total(save=True)
#         except Exception:
#             pass

#         # 6) Réponse
#         return Response(AchatSerializer(achat).data, status=status.HTTP_201_CREATED)


# (Optionnel) log des mouvements ; no-op si le module n'existe pas
try:
    from inventory.services import log_move
except Exception:
    def log_move(**kwargs):
        return None

# ----------------- Helpers locaux -----------------
def _role_ok(user) -> bool:
    return bool(getattr(user, "user_role", None) and user.user_role.role in ["admin", "manager"])


def _stock_increment(*, produit_id: int, bijouterie_id: int | None, delta_qty: int, lot_id: int | None = None) -> Stock | None:
    """
    Incrémente le stock en PIÈCES (jamais 0 à la création).
    Réserve si bijouterie_id=None, sinon boutique.
    """
    if delta_qty is None or int(delta_qty) <= 0:
        return None  # on ignore les 0/négatifs

    if bijouterie_id is not None:
        get_object_or_404(Bijouterie, pk=int(bijouterie_id))

    lookup = {
        "produit_id": int(produit_id),
        "bijouterie_id": int(bijouterie_id) if bijouterie_id is not None else None,
        "lot_id": int(lot_id) if lot_id is not None else None,
    }

    with transaction.atomic():
        st = Stock.objects.select_for_update().filter(**lookup).first()
        if st is None:
            try:
                # ✅ création déjà VALIDE (quantite > 0)
                st = Stock.objects.create(**lookup, quantite=int(delta_qty))
            except IntegrityError:
                # collision rare -> reprendre puis increment
                st = Stock.objects.select_for_update().get(**lookup)
                Stock.objects.filter(pk=st.pk).update(quantite=F("quantite") + int(delta_qty))
                st.refresh_from_db(fields=["quantite"])
        else:
            Stock.objects.filter(pk=st.pk).update(quantite=F("quantite") + int(delta_qty))
            st.refresh_from_db(fields=["quantite"])
        return st


# =========================
#       CREATE VIEW
# =========================
class AchatCreateView(APIView):
    """
    Crée un achat + lots (optionnels) et met à jour les stocks :
      - Affectation par **lot** : ventilation vers des bijouteries, le reste va en **RÉSERVE**.
      - Affectation **directe** (sans lot) : ventilation au niveau de la ligne, le reste va en **RÉSERVE**.
      - **Tout réservé** : aucune affectation fournie -> tout va en **RÉSERVE**.

    Règles (pièces uniquement) :
      - Somme(lots.quantite) == quantite de la ligne (si lots).
      - Somme(affectations.quantite) ≤ quantite (ligne/lot).
      - Stock crédité :
          • Bijouterie : (produit, bijouterie, lot) ; is_reserved=False
          • Réserve    : (produit, bijouterie=NULL, lot) ; is_reserved=True
      - Mouvement : MovementType.PURCHASE_IN (src=EXTERNAL → dst=BIJOUTERIE/RESERVED).
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Créer un achat (lots, affectation directe, réservé)",
        operation_description=dedent("""
        Crée un achat fournisseur, des lots (optionnels) et met à jour les stocks (bijouteries / réserve).

        ## Affectation par lot
        ```json
        {
          "fournisseur": {"nom":"Diop","prenom":"Abdou","telephone":"770000000","address":"Dakar"},
          "produits":[
            {
              "produit": 12,
              "quantite": 50,
              "prix_achat_gramme": "4500.00",
              "lots": [
                {
                  "lot_code": "LOT-A1",
                  "quantite": 30,
                  "affectations": [
                    {"bijouterie_id": 2, "quantite": 12},
                    {"bijouterie_id": 5, "quantite": 10}
                  ]
                },
                {
                  "lot_code": null,
                  "quantite": 20,
                  "affectations": [
                    {"bijouterie_id": 2, "quantite": 15}
                  ]
                }
              ]
            }
          ],
          "frais_transport": "0.00",
          "frais_douane": "0.00"
        }
        ```

        ## Affectation directe (sans lots)
        ```json
        {
          "fournisseur": {"nom":"Kane","prenom":"Moussa","telephone":"780000000"},
          "produits":[
            {
              "produit": 34,
              "quantite": 8,
              "prix_achat_gramme": "5200.00",
              "affectations": [
                {"bijouterie_id": 3, "quantite": 5},
                {"bijouterie_id": 7, "quantite": 1}
              ]
            }
          ]
        }
        ```
        """),
        request_body=AchatCreateSerializer,
        responses={201: openapi.Response("Création réussie", schema=AchatSerializer)},
        tags=["Achats"],
    )
    @transaction.atomic
    def post(self, request):
        # 0) ACL
        if not _role_ok(request.user):
            return Response({"detail": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        # 1) Valider payload
        ser = AchatCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        # 2) Upsert fournisseur (par téléphone)
        f = data["fournisseur"]
        fournisseur, _ = Fournisseur.objects.get_or_create(
            telephone=f["telephone"],
            defaults={"nom": f.get("nom", ""), "prenom": f.get("prenom", ""), "address": f.get("address", "")},
        )

        # 3) Créer l'achat
        achat = Achat.objects.create(
            fournisseur=fournisseur,
            description=f.get("address", ""),
            frais_transport=data.get("frais_transport", Decimal("0.00")),
            frais_douane=data.get("frais_douane", Decimal("0.00")),
        )

        # 4) Traiter chaque ligne produit
        now = timezone.now()

        # -- Conteneur de réponse enrichie
        details: list[dict] = []

        for line in data["produits"]:
            produit_id = int(line["produit"])
            produit = get_object_or_404(Produit, pk=produit_id)

            q_line = int(line["quantite"])
            prix_gramme = line["prix_achat_gramme"]  # Decimal
            lots = line.get("lots") or []
            affs = line.get("affectations") or []

            # ---- MODE A : avec lots
            if lots:
                line_result = {
                    "produit_id": produit_id,
                    "mode": "LOTS",
                    "quantite_ligne": q_line,
                    "lots": [],
                }

                for l in lots:
                    lot_code_input = (l.get("lot_code") or "").strip().upper() or None
                    lot_qty = int(l["quantite"])

                    # (Option valorisation) poids = lot_qty * produit.poids (si dispo)
                    try:
                        poids_unitaire = getattr(produit, "poids", None)
                        if poids_unitaire is None:
                            poids_total = Decimal("0.000")
                        else:
                            poids_total = (Decimal(lot_qty) * Decimal(poids_unitaire)).quantize(Decimal("0.000"))
                    except Exception:
                        poids_total = Decimal("0.000")

                    lot = Lot(
                        achat=achat,
                        produit=produit,
                        lot_code=lot_code_input,
                        poids_total=poids_total,
                        poids_restant=poids_total,
                        prix_achat_gramme=prix_gramme,
                        commentaire="Créé via AchatCreateView",
                    )
                    try:
                        lot.save()
                    except IntegrityError:
                        lot.lot_code = None
                        lot.save()

                    # Ventilation vers bijouteries
                    somme_aff = 0
                    lot_result = {
                        "lot_id": lot.id,
                        "lot_code": lot.lot_code,
                        "quantite": lot_qty,
                        "affectations": [],
                    }

                    for a in (l.get("affectations") or []):
                        bid = int(a["bijouterie_id"])
                        q = int(a["quantite"])
                        if q <= 0:
                            continue
                        somme_aff += q

                        st = _stock_increment(produit_id=produit_id, bijouterie_id=bid, delta_qty=q, lot_id=lot.id)
                        log_move(
                            produit=produit,
                            qty=q,
                            movement_type=MovementType.PURCHASE_IN,
                            src_bucket=Bucket.EXTERNAL,
                            dst_bucket=Bucket.BIJOUTERIE,
                            dst_bijouterie_id=bid,
                            unit_cost=prix_gramme,
                            achat=achat,
                            lot=lot,
                            user=request.user,
                            reason=f"Arrivée achat (lot {lot.lot_code or lot.id} → bijouterie)",
                        )

                        lot_result["affectations"].append({
                            "bijouterie_id": bid,
                            "quantite": q,
                            "stock": {
                                "id": st.id, "produit_id": st.produit_id,
                                "bijouterie_id": st.bijouterie_id, "lot_id": st.lot_id,
                                "quantite": st.quantite, "is_reserved": st.is_reserved,
                            },
                        })

                    # Reste du lot -> RÉSERVE
                    reste = lot_qty - somme_aff
                    if reste > 0:
                        st = _stock_increment(produit_id=produit_id, bijouterie_id=None, delta_qty=reste, lot_id=lot.id)
                        log_move(
                            produit=produit,
                            qty=reste,
                            movement_type=MovementType.PURCHASE_IN,
                            src_bucket=Bucket.EXTERNAL,
                            dst_bucket=Bucket.RESERVED,
                            unit_cost=prix_gramme,
                            achat=achat,
                            lot=lot,
                            user=request.user,
                            reason=f"Arrivée achat (reste lot {lot.lot_code or lot.id} en réservé)",
                        )
                        lot_result["reserve"] = {
                            "id": st.id, "produit_id": st.produit_id,
                            "bijouterie_id": st.bijouterie_id, "lot_id": st.lot_id,
                            "quantite": st.quantite, "is_reserved": st.is_reserved,
                        }

                    line_result["lots"].append(lot_result)

                details.append(line_result)

            # ---- MODE B : sans lots (affectations directes ou tout réservé)
            else:
                line_result = {
                    "produit_id": produit_id,
                    "mode": "DIRECT",
                    "quantite_ligne": q_line,
                    "affectations": [],
                }
                somme_aff = 0

                for a in affs:
                    bid = int(a["bijouterie_id"])
                    q = int(a["quantite"])
                    if q <= 0:
                        continue
                    somme_aff += q

                    st = _stock_increment(produit_id=produit_id, bijouterie_id=bid, delta_qty=q, lot_id=None)
                    log_move(
                        produit=produit,
                        qty=q,
                        movement_type=MovementType.PURCHASE_IN,
                        src_bucket=Bucket.EXTERNAL,
                        dst_bucket=Bucket.BIJOUTERIE,
                        dst_bijouterie_id=bid,
                        unit_cost=prix_gramme,
                        achat=achat,
                        lot=None,
                        user=request.user,
                        reason="Arrivée achat (affectation directe)",
                    )

                    line_result["affectations"].append({
                        "bijouterie_id": bid,
                        "quantite": q,
                        "stock": {
                            "id": st.id, "produit_id": st.produit_id,
                            "bijouterie_id": st.bijouterie_id, "lot_id": st.lot_id,
                            "quantite": st.quantite, "is_reserved": st.is_reserved,
                        },
                    })

                # Reste -> RÉSERVE
                reste = q_line - somme_aff
                if reste > 0:
                    st = _stock_increment(produit_id=produit_id, bijouterie_id=None, delta_qty=reste, lot_id=None)
                    log_move(
                        produit=produit,
                        qty=reste,
                        movement_type=MovementType.PURCHASE_IN,
                        src_bucket=Bucket.EXTERNAL,
                        dst_bucket=Bucket.RESERVED,
                        unit_cost=prix_gramme,
                        achat=achat,
                        lot=None,
                        user=request.user,
                        reason="Arrivée achat (reste en réservé)",
                    )
                    line_result["reserve"] = {
                        "id": st.id, "produit_id": st.produit_id,
                        "bijouterie_id": st.bijouterie_id, "lot_id": st.lot_id,
                        "quantite": st.quantite, "is_reserved": st.is_reserved,
                    }

                details.append(line_result)

        # 5) Totaux achat (silencieux si non implémenté)
        try:
            achat.update_total(save=True)
        except Exception:
            pass

        # 6) Réponse enrichie
        payload = {
            "achat": AchatSerializer(achat).data,
            "details": details,
        }
        return Response(payload, status=status.HTTP_201_CREATED)


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

def _stock_get_strict(produit_id: int, bijouterie_id: Optional[int], lot_id: Optional[int]):
    row = _stock_row_qs(produit_id, bijouterie_id, lot_id).first()
    if not row:
        where = "réservé" if bijouterie_id is None else f"bijouterie_id={bijouterie_id}"
        raise ValidationError(f"Ligne de stock introuvable pour produit={produit_id}, {where}, lot_id={lot_id}.")
    return row

def _stock_increment_strict(*, produit_id: int, bijouterie_id: Optional[int], delta_qty: int, lot_id: Optional[int]):
    if delta_qty <= 0:
        return
    row = _stock_get_strict(produit_id, bijouterie_id, lot_id)
    Stock.objects.filter(pk=row.pk).update(quantite=F("quantite") + int(delta_qty))

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

def _apply_repartition_strict(
    *,
    produit,
    achat,
    achat_ligne,
    lot: Optional[Lot],
    unit_cost: Decimal,
    current_res: int,
    current_bij: Dict[int, int],
    target_res: int,
    target_bij: Dict[int, int],
    user,
):
    """
    Applique les deltas pour un (produit, lot) en STRICT update :
    - Ne crée jamais de lignes de stock.
    - Échoue si stock insuffisant.
    """
    lot_id = lot.pk if lot else None
    produit_id = produit.pk

    # 1) Ajuster le 'réservé'
    delta_res = target_res - current_res
    if delta_res > 0:
        _stock_increment_strict(produit_id=produit_id, bijouterie_id=None, delta_qty=delta_res, lot_id=lot_id)
        log_move(
            produit=produit, qty=delta_res,
            movement_type=MovementType.PURCHASE_IN,
            src_bucket=Bucket.EXTERNAL, dst_bucket=Bucket.RESERVED,
            unit_cost=unit_cost, achat=achat, achat_ligne=achat_ligne, lot=lot, user=user,
            reason=f"Maj achat (strict): +{delta_res} réservé" + (f" (lot {lot.lot_code})" if lot else ""),
        )
    elif delta_res < 0:
        delta = -delta_res
        _stock_decrement_strict(produit_id=produit_id, bijouterie_id=None, delta_qty=delta, lot_id=lot_id)
        log_move(
            produit=produit, qty=delta,
            movement_type=MovementType.CANCEL_PURCHASE,
            src_bucket=Bucket.RESERVED, dst_bucket=Bucket.EXTERNAL,
            unit_cost=unit_cost, achat=achat, achat_ligne=achat_ligne, lot=lot, user=user,
            reason=f"Maj achat (strict): -{delta} réservé" + (f" (lot {lot.lot_code})" if lot else ""),
        )

    # 2) Ajuster les bijouteries
    for bid in set(current_bij) | set(target_bij):
        cur = current_bij.get(bid, 0)
        tgt = target_bij.get(bid, 0)
        diff = tgt - cur
        if diff > 0:
            _stock_decrement_strict(produit_id=produit_id, bijouterie_id=None, delta_qty=diff, lot_id=lot_id)
            _stock_increment_strict(produit_id=produit_id, bijouterie_id=bid, delta_qty=diff, lot_id=lot_id)
            log_move(
                produit=produit, qty=diff,
                movement_type=MovementType.ALLOCATE,
                src_bucket=Bucket.RESERVED, dst_bucket=Bucket.BIJOUTERIE, dst_bijouterie_id=bid,
                unit_cost=unit_cost, achat=achat, achat_ligne=achat_ligne, lot=lot, user=user,
                reason="Maj achat (strict): réservé → bijouterie",
            )
        elif diff < 0:
            take = -diff
            _stock_decrement_strict(produit_id=produit_id, bijouterie_id=bid, delta_qty=take, lot_id=lot_id)
            _stock_increment_strict(produit_id=produit_id, bijouterie_id=None, delta_qty=take, lot_id=lot_id)
            log_move(
                produit=produit, qty=take,
                movement_type=MovementType.ADJUSTMENT,
                src_bucket=Bucket.BIJOUTERIE, src_bijouterie_id=bid,
                unit_cost=unit_cost, achat=achat, achat_ligne=achat_ligne, lot=lot, user=user,
                reason="Maj achat (strict): bijouterie → réservé (out)",
            )
            log_move(
                produit=produit, qty=take,
                movement_type=MovementType.ADJUSTMENT,
                dst_bucket=Bucket.RESERVED,
                unit_cost=unit_cost, achat=achat, achat_ligne=achat_ligne, lot=lot, user=user,
                reason="Maj achat (strict): bijouterie → réservé (in)",
            )


# ====================== VIEW (STRICT UPDATE + SWAGGER + SERIALIZERS) ======================
class AchatUpdateView(APIView):
    """
    Update uniquement :
      - Aucune création de lignes d'achat, de lots ou de lignes de stock.
      - Ajuste la répartition réservé/bijouteries (par lot si présent).
      - Échoue si références manquantes ou stock insuffisant.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        tags=["Achats"],
        operation_summary="Mettre à jour un achat (STRICT, pas de création)",
        operation_description=(
            "Utilise `AchatUpdateSerializer` en entrée et `AchatSerializer` en sortie.\n"
            "Ajuste les répartitions (réservé/bijouteries) par lot si fourni.\n"
            "Échoue si une ligne/lot/stock est manquant ou si le stock est insuffisant."
        ),
        manual_parameters=[
            openapi.Parameter(
                name="achat_id",
                in_=openapi.IN_PATH,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="ID de l'achat à modifier",
            ),
        ],
        request_body=AchatUpdateSerializer,
        responses={
            200: AchatSerializer,
            400: "Requête invalide",
            403: "Accès refusé",
            404: "Ressource introuvable",
            409: "Conflit (stock insuffisant / lignes manquantes)",
        },
    )
    @transaction.atomic
    def put(self, request, achat_id: int):
        user = request.user
        if not _role_ok(user):
            return Response({"detail": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        achat = get_object_or_404(Achat, pk=achat_id)
        if getattr(achat, "status", None) == "cancelled":
            return Response({"detail": "Achat annulé : modification interdite."}, status=status.HTTP_400_BAD_REQUEST)

        ser = AchatUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        # Fournisseur (STRICT : doit exister)
        f_data = data.get("fournisseur")
        if f_data:
            try:
                fournisseur = Fournisseur.objects.get(telephone=f_data["telephone"])
            except Fournisseur.DoesNotExist:
                return Response({"detail": "Fournisseur inconnu (update-only)."}, status=status.HTTP_404_NOT_FOUND)
            if achat.fournisseur_id != fournisseur.id:
                achat.fournisseur = fournisseur
                achat.save(update_fields=["fournisseur"])
        # (si tu préfères l'upsert: remplace le bloc ci-dessus par un get_or_create)

        # Lignes existantes (update-only)
        existing_lines = {ap.produit_id: ap for ap in achat.produits.select_related("produit").all()}

        for item in data.get("produits", []):
            produit_id = int(item["produit"])
            ap = existing_lines.get(produit_id)
            if not ap:
                return Response(
                    {"detail": f"Ligne d'achat inconnue pour produit_id={produit_id} (update-only)."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            produit = ap.produit
            unit_cost = Decimal(item["prix_achat_gramme"])
            qty_total_payload = int(item["quantite"])

            # MAJ de la ligne (sans création)
            ap.prix_achat_gramme = unit_cost
            ap.quantite = qty_total_payload
            ap.save(update_fields=["prix_achat_gramme", "quantite"])

            lots_payload = item.get("lots") or []
            affectations = item.get("affectations") or []

            # ---- MODE A : par lots ----
            if lots_payload:
                existing_lots = {l.lot_code: l for l in ap.lots.all()}

                # Tous les lots envoyés doivent exister
                for lot_item in lots_payload:
                    lot_code = (lot_item.get("lot_code") or "").strip().upper()
                    if lot_code not in existing_lots:
                        return Response(
                            {"detail": f"Lot inconnu '{lot_code}' pour cette ligne (update-only)."},
                            status=status.HTTP_404_NOT_FOUND,
                        )

                somme_lots_payload = 0
                for lot_item in lots_payload:
                    lot_code = (lot_item.get("lot_code") or "").strip().upper()
                    lot_qty_new = int(lot_item.get("quantite") or 0)
                    if lot_qty_new <= 0:
                        return Response({"detail": f"Quantité du lot {lot_code} doit être > 0."}, status=status.HTTP_400_BAD_REQUEST)
                    somme_lots_payload += lot_qty_new

                    lot = existing_lots[lot_code]
                    cur_res, cur_bij = _snapshot_stock(produit_id=produit.id, lot_id=lot.pk)

                    # cible (réservé + bijouteries)
                    target_bij: Dict[int, int] = {}
                    somme_aff = 0
                    for aff in (lot_item.get("affectations") or []):
                        bid = int(aff["bijouterie_id"])
                        q = int(aff["quantite"])
                        if q <= 0:
                            continue
                        somme_aff += q
                        target_bij[bid] = target_bij.get(bid, 0) + q
                    if somme_aff > lot_qty_new:
                        return Response({"detail": f"Affectations > quantité du lot {lot_code}."}, status=status.HTTP_400_BAD_REQUEST)
                    target_res = lot_qty_new - somme_aff

                    try:
                        _apply_repartition_strict(
                            produit=produit, achat=achat, achat_ligne=ap, lot=lot,
                            unit_cost=unit_cost,
                            current_res=cur_res, current_bij=cur_bij,
                            target_res=target_res, target_bij=target_bij,
                            user=user,
                        )
                    except ValidationError as e:
                        return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)

                    # Recalage lot (on-hand = réservé + bijouteries)
                    new_res, new_bij = _snapshot_stock(produit_id=produit.id, lot_id=lot.pk)
                    on_hand = int(new_res + sum(new_bij.values()))
                    lot.quantite_total = lot_qty_new
                    lot.quantite_restante = on_hand
                    lot.prix_achat_gramme = unit_cost
                    lot.save(update_fields=["quantite_total", "quantite_restante", "prix_achat_gramme"])

                # (facultatif mais conseillé)
                if somme_lots_payload != qty_total_payload:
                    return Response(
                        {"detail": f"Incohérence: somme des lots={somme_lots_payload} ≠ quantité de ligne={qty_total_payload}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # ---- MODE B : sans lots ----
            else:
                if ap.lots.exists():
                    return Response(
                        {"detail": "Cette ligne a des lots existants. Utilisez le mode 'lots' pour la mettre à jour."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                cur_res, cur_bij = _snapshot_stock(produit_id=produit.id, lot_id=None)
                target_bij: Dict[int, int] = {}
                somme_aff = 0
                for aff in affectations:
                    bid = int(aff["bijouterie_id"])
                    q = int(aff["quantite"])
                    if q <= 0:
                        continue
                    somme_aff += q
                    target_bij[bid] = target_bij.get(bid, 0) + q
                if somme_aff > qty_total_payload:
                    return Response({"detail": "Affectations > quantité de la ligne."}, status=status.HTTP_400_BAD_REQUEST)
                target_res = qty_total_payload - somme_aff

                try:
                    _apply_repartition_strict(
                        produit=produit, achat=achat, achat_ligne=ap, lot=None,
                        unit_cost=unit_cost,
                        current_res=cur_res, current_bij=cur_bij,
                        target_res=target_res, target_bij=target_bij,
                        user=user,
                    )
                except ValidationError as e:
                    return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)

        # Totaux (sauvegardés)
        achat.update_total(save=True)

        return Response(
            {"message": "Achat mis à jour avec succès", "achat": AchatSerializer(achat).data},
            status=status.HTTP_200_OK
        )


# -------------------------End A Update view

# class AchatUpdateView(APIView):
#     """
#     PUT: rebase complet d’un achat :
#       - retire l’ancien stock (et loggue des mouvements CANCEL_PURCHASE + extourne compta),
#       - recrée les lignes avec nouveau payload (PURCHASE_IN + nouvelle écriture comptable).
#     """
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         tags=["Achats"],
#         operation_summary="Mettre à jour un achat (rebase : stocks + inventaire + compta)",
#         operation_description=(
#             "Body attendu : { reverse_allocations?: [...], payload: <AchatCreateSerializer> }.\n"
#             "- reverse_allocations (optionnel) permet de préciser d’où retirer l’ancien stock "
#             "(réservé / bijouteries). Sinon, retrait automatique: réservé puis bijouteries."
#         ),
#         manual_parameters=[
#             openapi.Parameter("achat_id", openapi.IN_PATH, required=True, type=openapi.TYPE_INTEGER),
#         ],
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             properties={
#                 "reverse_allocations": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     description="Contrôle fin du retrait (ancien achat).",
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["produit_id", "allocations"],
#                         properties={
#                             "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "allocations": openapi.Schema(
#                                 type=openapi.TYPE_ARRAY,
#                                 items=openapi.Schema(
#                                     type=openapi.TYPE_OBJECT,
#                                     required=["quantite"],
#                                     properties={
#                                         "bijouterie_id": openapi.Schema(type=openapi.TYPE_INTEGER, nullable=True),
#                                         "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, minimum=1),
#                                     },
#                                 ),
#                             ),
#                         },
#                     ),
#                 ),
#                 "payload": AchatCreateSerializer.schema,  # même forme que POST
#             },
#             example={
#                 "reverse_allocations": [
#                     {"produit_id": 10, "allocations": [{"bijouterie_id": None, "quantite": 2}, {"bijouterie_id": 3, "quantite": 1}]}
#                 ],
#                 "payload": {
#                     "fournisseur": {"nom": "Diallo", "prenom": "Aïcha", "telephone": "77112233"},
#                     "produits": [
#                         {
#                             "produit": {"id": 12},
#                             "quantite": 5,
#                             "prix_achat_gramme": "25000.00",
#                             "tax": "0.00",
#                             "affectations": [{"bijouterie_id": 1, "quantite": 3}],
#                         }
#                     ]
#                 }
#             }
#         ),
#         responses={200: AchatSerializer, 403: "Accès refusé", 404: "Introuvable", 409: "Conflit stock"},
#     )
#     @transaction.atomic
#     def put(self, request, achat_id: int):
#         user = request.user
#         if not _role_ok(user):
#             return Response({"detail": "Access Denied"}, status=403)

#         achat = get_object_or_404(Achat, pk=achat_id)

#         reverse_alloc = (request.data or {}).get("reverse_allocations")
#         payload_in = (request.data or {}).get("payload") or {}

#         ser = AchatCreateSerializer(data=payload_in)
#         ser.is_valid(raise_exception=True)

#         achat = rebase_purchase(achat, ser.validated_data, reverse_alloc, user)  # ✅ auto inventaire + compta
#         return Response(
#             {"message": "Achat mis à jour (rebase)", "achat": AchatSerializer(achat).data},
#             status=200
#         )


# class AchatUpdateView(APIView):
#     """
#     Met à jour un achat **en rebase** :
#     - retire des stocks les quantités de l'achat existant (mouvements d’inventaire CANCEL_PURCHASE),
#     - extourne l’écriture comptable associée,
#     - recrée les lignes et ré-affecte les stocks (mouvements PURCHASE_IN),
#     - reposte l’écriture comptable (Dr Stock / Dr TVA / Cr Fournisseur) via vos services.

#     Toute la logique inventaire + compta est déléguée à `purchase.services.rebase_purchase(...)`.
#     """
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         tags=["Achats"],
#         operation_summary="Mettre à jour un achat (rebase : inventaire + comptabilité automatiques)",
#         operation_description=(
#             "Met à jour un achat en retirant d'abord l'ancien stock (avec mouvements `CANCEL_PURCHASE`), "
#             "en extournant la compta, puis en recréant les lignes/affectations (mouvements `PURCHASE_IN`) "
#             "et en republiant l'écriture (Dr Stock / Dr TVA / Cr Fournisseur)."
#         ),
#         manual_parameters=[
#             openapi.Parameter(
#                 name="achat_id",
#                 in_=openapi.IN_PATH,
#                 description="ID de l'achat à mettre à jour",
#                 type=openapi.TYPE_INTEGER,
#                 required=True,
#             ),
#         ],
#         request_body=AchatUpdateRequestSerializer,
#         responses={200: AchatSerializer, 403: "Accès refusé", 404: "Introuvable", 409: "Conflit stock"},
#     )
#     def put(self, request, achat_id: int):
#         user = request.user
#         if not _role_ok(user):
#             return Response({"detail": "Access Denied"}, status=403)

#         achat = get_object_or_404(Achat, pk=achat_id)

#         # Valider la structure du body (reverse_allocations + payload)
#         body_ser = AchatUpdateRequestSerializer(data=request.data)
#         body_ser.is_valid(raise_exception=True)
#         reverse_alloc = body_ser.validated_data.get("reverse_allocations")
#         payload = body_ser.validated_data["payload"]

#         try:
#             # Le service applique la transaction, l’inventaire et la compta
#             updated_achat = rebase_purchase(achat=achat, payload=payload, reverse_alloc=reverse_alloc, user=user)
#         except ValueError as e:
#             # typiquement : stock insuffisant / incohérences d’allocations
#             return Response({"detail": str(e)}, status=409)
#         except Exception as e:
#             return Response({"detail": str(e)}, status=500)

#         return Response(
#             {
#                 "message": "Achat mis à jour (rebase) avec succès",
#                 "achat": AchatSerializer(updated_achat).data,
#             },
#             status=200,
#         )


# class AchatListView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
       
#         operation_description="Liste tous les achats avec leurs produits. Filtrable par fournisseur et date.",#
# #        manual_parameters=[
# #            openapi.Parameter('start_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Date de début (format YYYY-MM-DD)"),
# #            openapi.Parameter('end_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Date de fin (format YYYY-MM-DD)"),
# #            openapi.Parameter('fournisseur_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="ID du fournisseur")
# #        ],

#         responses={200: AchatSerializer(many=True)}
#     )
#     def get(self, request, *args, **kwargs):
#         user_role = getattr(request.user.user_role, 'role', None)
#         if user_role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             achats = Achat.objects.all().prefetch_related('produits__produit', 'fournisseur')

#             serializer = AchatSerializer(achats, many=True)
#             return Response(serializer.data, status=200)

#         except Exception as e:
#             return Response({'error': str(e)}, status=400)
        

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


# class AchatProduitUpdateAPIView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Modifier un AchatProduit et les données associées de l'achat.",
#         manual_parameters=[
#             openapi.Parameter('achatproduit_id', openapi.IN_PATH, type=openapi.TYPE_INTEGER, required=True),
#             openapi.Parameter('achat_id', openapi.IN_PATH, type=openapi.TYPE_INTEGER, required=True)
#         ],
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=['quantite', 'prix_achat_gramme', 'tax', 'produit_id', 'fournisseur_id'],
#             properties={
#                 'quantite': openapi.Schema(type=openapi.TYPE_INTEGER),
#                 'prix_achat_gramme': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal'),
#                 'tax': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal'),
#                 'produit_id': openapi.Schema(type=openapi.TYPE_INTEGER),
#                 'fournisseur_id': openapi.Schema(type=openapi.TYPE_INTEGER)
#             }
#         ),
#         responses={200: AchatProduitSerializer}
#     )
#     @transaction.atomic
#     def put(self, request, achat_id, achatproduit_id):
#         role = getattr(request.user.user_role, 'role', None)
#         if role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             achat = Achat.objects.get(id=achat_id)
#             achat_produit = AchatProduit.objects.get(id=achatproduit_id, achat=achat)

#             # Récupérer les nouvelles données
#             quantite = int(request.data.get('quantite'))
#             prix_achat_gramme = Decimal(request.data.get('prix_achat_gramme'))
#             tax = Decimal(request.data.get('tax'))
#             produit = Produit.objects.get(id=request.data.get('produit_id'))
#             fournisseur = Fournisseur.objects.get(id=request.data.get('fournisseur_id'))

#             # Calcul sous total
#             sous_total = quantite * prix_achat_gramme * (produit.poids or 1)

#             # Mise à jour AchatProduit
#             achat_produit.quantite = quantite
#             achat_produit.prix_achat_gramme = prix_achat_gramme
#             achat_produit.tax = tax
#             achat_produit.produit = produit
#             achat_produit.fournisseur = fournisseur
#             achat_produit.sous_total_prix_achat = sous_total
#             achat_produit.save()

#             # Mise à jour Achat
#             achat.fournisseur = fournisseur
#             achat.update_total()  # déjà calcule montant_total_ht et montant_total_ttc
#             achat.save()

#             return Response({
#                 "achat_produit_id": achat_produit.id,
#                 "produit_id": produit.id,
#                 "fournisseur_id": fournisseur.id,
#                 "quantite": quantite,
#                 "prix_achat_gramme": str(prix_achat_gramme),
#                 "tax": str(tax),
#                 "sous_total_prix_achat": str(sous_total),
#                 "achat": {
#                     "id": achat.id,
#                     "created_at": achat.created_at,
#                     "numero_achat": achat.numero_achat,
#                     "fournisseur_id": achat.fournisseur.id if achat.fournisseur else None,
#                     "montant_total": str(achat.montant_total),
#                     "montant_total_tax_inclue": str(achat.montant_total_tax_inclue)
#                 }
#             }, status=200)

#         except Achat.DoesNotExist:
#             return Response({"detail": "Achat non trouvé."}, status=404)
#         except AchatProduit.DoesNotExist:
#             return Response({"detail": "AchatProduit non trouvé."}, status=404)
#         except Produit.DoesNotExist:
#             return Response({"detail": "Produit non trouvé."}, status=404)
#         except Fournisseur.DoesNotExist:
#             return Response({"detail": "Fournisseur non trouvé."}, status=404)
#         except Exception as e:
#             return Response({"detail": str(e)}, status=500)



# class StockReserveAffectationView(APIView):
#     permission_classes = [IsAuthenticated]

#     def post(self, request):
#         user = request.user
#         if not _role_ok(user):  # admin/manager
#             return Response({"detail": "Access Denied"}, status=403)

#         try:
#             produit_id = int(request.data["produit_id"])
#             bijouterie_id = int(request.data["bijouterie_id"])
#             quantite = int(request.data["quantite"])
#         except (KeyError, ValueError):
#             return Response({"detail": "Requis: produit_id, bijouterie_id, quantite (int)."}, status=400)

#         try:
#             res = move_reserved_to_bijouterie(produit_id, bijouterie_id, quantite)
#             return Response({"message": "Affectation effectuée", "result": res}, status=200)
#         except Exception as e:
#             return Response({"detail": str(e)}, status=400)


# class StockReserveAffectationView(APIView):
#     """
#     Affecte des quantités depuis le **stock réservé** d’un produit vers une **bijouterie** donnée,
#     en consignant un mouvement d’inventaire ALLOCATE (RESERVED -> BIJOUTERIE) pour chaque affectation.
#     """
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         tags=["Stocks"],
#         operation_summary="Affecter du stock RÉSERVÉ vers une bijouterie (avec log inventaire)",
#         operation_description=(
#             "Déplace des quantités depuis le **stock réservé** (`bijouterie=NULL`, `reservation_key='RES-<produit_id>'`) "
#             "vers une **bijouterie** cible.\n\n"
#             "**Règles :**\n"
#             "- 409 si stock réservé insuffisant.\n"
#             "- Opération atomique (transaction) et sûre en concurrence (`select_for_update`).\n"
#             "- Rôles autorisés : `admin`, `manager`.\n"
#             "- Un mouvement d’inventaire `ALLOCATE` est créé pour chaque ligne."
#         ),
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["moves"],
#             properties={
#                 "moves": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     description="Liste de mouvements à effectuer",
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["produit_id", "bijouterie_id", "quantite"],
#                         properties={
#                             "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "bijouterie_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, minimum=1),
#                             # Optionnel : commentaire libre pour le log d’inventaire
#                             "reason": openapi.Schema(type=openapi.TYPE_STRING),
#                         },
#                     ),
#                 ),
#             },
#             example={
#                 "moves": [
#                     {"produit_id": 10, "bijouterie_id": 2, "quantite": 5, "reason": "Affectation ouverture magasin"},
#                     {"produit_id": 10, "bijouterie_id": 3, "quantite": 2},
#                     {"produit_id": 7,  "bijouterie_id": 2, "quantite": 1},
#                 ]
#             },
#         ),
#         responses={
#             200: openapi.Response(
#                 description="Affectations effectuées",
#                 schema=openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     properties={
#                         "message": openapi.Schema(type=openapi.TYPE_STRING),
#                         "movements": openapi.Schema(
#                             type=openapi.TYPE_ARRAY,
#                             items=openapi.Schema(
#                                 type=openapi.TYPE_OBJECT,
#                                 properties={
#                                     "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                                     "bijouterie_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                                     "moved": openapi.Schema(type=openapi.TYPE_INTEGER),
#                                     "reserved_qte_apres": openapi.Schema(type=openapi.TYPE_INTEGER),
#                                     "bijouterie_qte_apres": openapi.Schema(type=openapi.TYPE_INTEGER),
#                                     "inventory_movement_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                                 },
#                             ),
#                         ),
#                     },
#                 ),
#             ),
#             400: openapi.Response(description="Requête invalide"),
#             403: openapi.Response(description="Accès refusé"),
#             404: openapi.Response(description="Produit/Bijouterie introuvable"),
#             409: openapi.Response(description="Stock réservé insuffisant"),
#         },
#     )
#     @transaction.atomic
#     def post(self, request):
#         user = request.user
#         if not _role_ok(user):
#             return Response({"detail": "Access Denied"}, status=403)

#         body = request.data or {}
#         moves = body.get("moves") or []
#         if not isinstance(moves, list) or not moves:
#             return Response({"detail": "Le champ 'moves' (liste) est requis et non vide."}, status=400)

#         results = []

#         try:
#             for mv in moves:
#                 try:
#                     produit_id = int(mv["produit_id"])
#                     bijouterie_id = int(mv["bijouterie_id"])
#                     qty = int(mv["quantite"])
#                 except (KeyError, ValueError, TypeError):
#                     return Response(
#                         {"detail": "Chaque mouvement doit contenir produit_id, bijouterie_id, quantite (entiers)."},
#                         status=400
#                     )
#                 if qty <= 0:
#                     return Response({"detail": "quantite doit être > 0."}, status=400)

#                 reason = (mv.get("reason") or "").strip() or "Affectation réservé → bijouterie"

#                 # Valide et charge les instances
#                 produit = get_object_or_404(Produit, pk=produit_id)
#                 get_object_or_404(Bijouterie, pk=bijouterie_id)

#                 # 1) Stock réservé source
#                 reservation_key = f"RES-{produit_id}"
#                 reserved = (
#                     Stock.objects.select_for_update()
#                     .filter(
#                         produit_id=produit_id,
#                         bijouterie__isnull=True,
#                         reservation_key=reservation_key,
#                     )
#                     .first()
#                 )
#                 if not reserved or reserved.quantite < qty:
#                     dispo = getattr(reserved, "quantite", 0)
#                     return Response(
#                         {"detail": f"Stock RÉSERVÉ insuffisant pour produit={produit_id}. requis={qty}, dispo={dispo}"},
#                         status=409,
#                     )

#                 # 2) décrémente le réservé
#                 Stock.objects.filter(pk=reserved.pk).update(quantite=F("quantite") - qty)

#                 # 3) incrémente le bucket bijouterie cible
#                 target, _ = (
#                     Stock.objects.select_for_update()
#                     .get_or_create(
#                         produit_id=produit_id,
#                         bijouterie_id=bijouterie_id,
#                         defaults={"quantite": 0, "is_reserved": False},
#                     )
#                 )
#                 Stock.objects.filter(pk=target.pk).update(quantite=F("quantite") + qty, is_reserved=False)

#                 # 4) log inventaire : ALLOCATE (RESERVED -> BIJOUTERIE)
#                 mv_rec = log_move(
#                     produit=produit,
#                     qty=qty,
#                     movement_type=MovementType.ALLOCATE,
#                     src_bucket=Bucket.RESERVED,
#                     dst_bucket=Bucket.BIJOUTERIE,
#                     dst_bijouterie_id=bijouterie_id,
#                     # on ne renseigne pas unit_cost ici (None) car c’est une réaffectation interne
#                     unit_cost=None,
#                     achat=None, achat_ligne=None,
#                     user=user,
#                     reason=reason,
#                 )

#                 # 5) rafraîchir pour le récap
#                 reserved.refresh_from_db(fields=["quantite"])
#                 target.refresh_from_db(fields=["quantite"])

#                 results.append({
#                     "produit_id": produit_id,
#                     "bijouterie_id": bijouterie_id,
#                     "moved": qty,
#                     "reserved_qte_apres": reserved.quantite,
#                     "bijouterie_qte_apres": target.quantite,
#                     "inventory_movement_id": mv_rec.id,
#                 })

#             return Response({"message": "Affectations effectuées", "movements": results}, status=200)

#         except Exception as e:
#             # en transaction : toute erreur annule le batch
#             return Response({"detail": str(e)}, status=500)


# -----------Affectation

# # Mouvement d'inventaire (no-op si le module n'existe pas)
# try:
#     from inventory.services import log_move
# except Exception:
#     def log_move(**kwargs):
#         return None

# def _role_ok(user) -> bool:
#     return bool(getattr(user, "user_role", None) and user.user_role.role in ["admin", "manager"])

# def _reservation_key(produit_id: int) -> str:
#     return f"RES-{int(produit_id)}"


# class StockReserveAffectationView(APIView):
#     """
#     Déplace des quantités depuis le stock réservé (bijouterie=NULL) vers une ou plusieurs bijouteries.
#     - Tout est atomique (transaction) ;
#     - Vérifie le stock réservé suffisant ;
#     - Journalise InventoryMovement (ALLOCATE).
#     """
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         tags=["Stocks"],
#         operation_summary="Affecter du stock RÉSERVÉ → bijouteries",
#         operation_description=(
#             "Pour chaque mouvement, la somme des `affectations[].quantite` doit être **égale** à `quantite`.\n"
#             "Les champs `prix_achat_gramme` / `tax` sont acceptés (hérités du serializer) mais **ignorés** ici."
#         ),
#         request_body=StockReserveAffectationPayloadSerializer,
#         responses={
#             200: openapi.Response(
#                 description="Affectations réalisées",
#                 schema=openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     properties={
#                         "message": openapi.Schema(type=openapi.TYPE_STRING),
#                         "results": openapi.Schema(
#                             type=openapi.TYPE_ARRAY,
#                             items=openapi.Schema(
#                                 type=openapi.TYPE_OBJECT,
#                                 properties={
#                                     "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                                     "reserved_before": openapi.Schema(type=openapi.TYPE_INTEGER),
#                                     "reserved_after": openapi.Schema(type=openapi.TYPE_INTEGER),
#                                     "allocations": openapi.Schema(
#                                         type=openapi.TYPE_ARRAY,
#                                         items=openapi.Schema(
#                                             type=openapi.TYPE_OBJECT,
#                                             properties={
#                                                 "bijouterie_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                                                 "delta": openapi.Schema(type=openapi.TYPE_INTEGER),
#                                                 "stock_qte_apres": openapi.Schema(type=openapi.TYPE_INTEGER),
#                                             },
#                                         ),
#                                     ),
#                                 },
#                             ),
#                         ),
#                     },
#                 ),
#             ),
#             403: openapi.Response(description="Accès refusé"),
#             409: openapi.Response(description="Conflit (stock réservé insuffisant)"),
#         },
#         examples={
#             "application/json": {
#                 "mouvements": [
#                     {
#                         "produit": 1,
#                         "quantite": 7,
#                         "prix_achat_gramme": "0.00",  # ignoré
#                         "tax": "0.00",                # ignoré
#                         "affectations": [
#                             {"bijouterie_id": 3, "quantite": 5},
#                             {"bijouterie_id": 4, "quantite": 2}
#                         ]
#                     }
#                 ]
#             }
#         }
#     )
#     @transaction.atomic
#     def post(self, request):
#         user = request.user
#         if not _role_ok(user):
#             return Response({"detail": "Access Denied"}, status=403)

#         ser = StockReserveAffectationPayloadSerializer(data=request.data)
#         ser.is_valid(raise_exception=True)
#         mouvements = ser.validated_data["mouvements"]

#         # ---- 1) Vérifier et verrouiller la dispo du stock réservé par produit ----
#         for m in mouvements:
#             produit_id = int(m["produit"])
#             need = int(m["quantite"])  # == somme des affectations (imposé par le wrapper)
#             reserved = (Stock.objects.select_for_update()
#                         .filter(
#                             produit_id=produit_id,
#                             bijouterie__isnull=True,
#                             reservation_key=_reservation_key(produit_id),
#                         ).first())
#             if not reserved or reserved.quantite < need:
#                 return Response(
#                     {"detail": f"Stock réservé insuffisant pour produit={produit_id}. "
#                                f"Requis={need}, disponible={getattr(reserved, 'quantite', 0)}"},
#                     status=409
#                 )

#         results = []

#         # ---- 2) Appliquer les affectations ----
#         for m in mouvements:
#             produit_id = int(m["produit"])
#             produit = get_object_or_404(Produit, pk=produit_id)
#             need = int(m["quantite"])
#             allocs = m["affectations"]

#             reserved = (Stock.objects.select_for_update()
#                         .filter(
#                             produit_id=produit_id,
#                             bijouterie__isnull=True,
#                             reservation_key=_reservation_key(produit_id),
#                         ).first())

#             before = reserved.quantite

#             # décrémente d’un coup le stock réservé
#             Stock.objects.filter(pk=reserved.pk).update(quantite=F("quantite") - need)
#             reserved.refresh_from_db(fields=["quantite"])

#             line_results = []
#             for a in allocs:
#                 bid = int(a["bijouterie_id"])
#                 q = int(a["quantite"])

#                 # upsert stock bijouterie
#                 dest, _ = (Stock.objects.select_for_update()
#                            .get_or_create(
#                                produit_id=produit_id,
#                                bijouterie_id=bid,
#                                defaults={"quantite": 0, "is_reserved": False},
#                            ))
#                 Stock.objects.filter(pk=dest.pk).update(quantite=F("quantite") + q)
#                 dest.refresh_from_db(fields=["quantite"])

#                 # Journal inventaire: RESERVED -> BIJOUTERIE
#                 log_move(
#                     produit=produit,
#                     qty=q,
#                     movement_type=MovementType.ALLOCATE,
#                     src_bucket=Bucket.RESERVED,
#                     dst_bucket=Bucket.BIJOUTERIE,
#                     dst_bijouterie_id=bid,
#                     unit_cost=None,
#                     achat=None, achat_ligne=None,
#                     user=user,
#                     reason="Affectation du stock réservé",
#                 )

#                 line_results.append({
#                     "bijouterie_id": bid,
#                     "delta": q,
#                     "stock_qte_apres": dest.quantite,
#                 })

#             results.append({
#                 "produit_id": produit_id,
#                 "reserved_before": before,
#                 "reserved_after": reserved.quantite,
#                 "allocations": line_results,
#             })

#         return Response({"message": "Affectations effectuées", "results": results}, status=200)


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
        raise ValidationError("Stock réservé insuffisant ou ligne introuvable.")

def _stock_increment_strict(*, produit_id: int, bijouterie_id: Optional[int], delta_qty: int, lot_id: Optional[int]):
    if delta_qty <= 0:
        return
    qs = _stock_row_qs(produit_id, bijouterie_id, lot_id)
    row = qs.first()
    if not row:
        raise ValidationError("Ligne de stock destination introuvable (strict update).")
    Stock.objects.filter(pk=row.pk).update(quantite=F("quantite") + int(delta_qty))

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
class StockReserveAffectationView(APIView):
    """
    Affecte du stock **réservé** vers 1..N bijouteries, optionnellement **par lot**.
    Strict update : aucune création de ligne de stock. Échoue si la destination n'existe pas.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        tags=["Stock"],
        operation_summary="Affecter le stock réservé vers des bijouteries (avec lots optionnels)",
        operation_description=(
            "Décrémente le **réservé** et incrémente les **bijouteries** (STRICT: pas de création de lignes).\n\n"
            "### Exemples de payload\n"
            "```json\n"
            "{\n"
            "  \"items\": [\n"
            "    {\"produit\": 123, \"affectations\": [{\"bijouterie_id\": 1, \"quantite\": 5}, {\"bijouterie_id\": 2, \"quantite\": 3}]},\n"
            "    {\"produit\": 456, \"lot_code\": \"LOT-2025-0007-A\", \"affectations\": [{\"bijouterie_id\": 1, \"quantite\": 2}]}\n"
            "  ]\n"
            "}\n"
            "```\n"
            "**Remarques** :\n"
            "- Si `lot_id` ou `lot_code` est fourni, l'affectation est faite **sur ce lot** uniquement.\n"
            "- En mode strict, la ligne `Stock` destination (bijouterie, produit, [lot]) doit exister."
        ),
        request_body=StockReserveAffectationSerializer,
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "message": openapi.Schema(type=openapi.TYPE_STRING),
                    "results": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "produit": openapi.Schema(type=openapi.TYPE_INTEGER),
                                "lot_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                                "reserved_before": openapi.Schema(type=openapi.TYPE_INTEGER),
                                "reserved_after": openapi.Schema(type=openapi.TYPE_INTEGER),
                                "by_shop": openapi.Schema(
                                    type=openapi.TYPE_ARRAY,
                                    items=openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            "bijouterie_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                                            "delta": openapi.Schema(type=openapi.TYPE_INTEGER),
                                        }
                                    )
                                ),
                            }
                        )
                    ),
                },
            ),
            400: "Requête invalide",
            403: "Accès refusé",
            404: "Ressource introuvable",
            409: "Conflit (stock insuffisant)",
        },
    )
    @transaction.atomic
    def post(self, request):
        user = request.user
        if not _role_ok(user):
            return Response({"detail": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

        ser = StockReserveAffectationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        payload = ser.validated_data

        results = []

        for it in payload["items"]:
            produit_id = int(it["produit"])
            produit = get_object_or_404(Produit, pk=produit_id)

            # Résolution lot (optionnelle)
            lot_id = it.get("lot_id")
            lot_obj = None
            if lot_id:
                lot_obj = get_object_or_404(Lot, pk=int(lot_id))
                if lot_obj.achat_ligne.produit_id != produit_id:
                    return Response(
                        {"detail": f"Le lot #{lot_id} n'appartient pas au produit {produit_id}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            elif it.get("lot_code"):
                code = it["lot_code"]
                try:
                    lot_obj = Lot.objects.get(
                        lot_code=code, achat_ligne__produit_id=produit_id
                    )
                except Lot.DoesNotExist:
                    return Response(
                        {"detail": f"Lot '{code}' introuvable pour le produit {produit_id}."},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                except MultipleObjectsReturned:
                    return Response(
                        {"detail": f"Lot '{code}' non unique pour ce produit : utilisez lot_id."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # Snapshot avant
            res_before, by_shop_before = _snapshot_stock(produit_id=produit_id, lot_id=lot_obj.pk if lot_obj else None)

            # Somme à affecter
            affectations = it["affectations"]
            total_out = sum(int(a["quantite"]) for a in affectations)

            # 1) Décrément réservé (strict)
            try:
                _stock_decrement_strict(
                    produit_id=produit_id, bijouterie_id=None, delta_qty=total_out,
                    lot_id=lot_obj.pk if lot_obj else None
                )
            except ValidationError as e:
                return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)

            # 2) Incrément bijouteries (strict)
            per_shop_res = []
            for a in affectations:
                bid = int(a["bijouterie_id"])
                qty = int(a["quantite"])

                # Valider l'existence de la bijouterie
                get_object_or_404(Bijouterie, pk=bid)

                try:
                    _stock_increment_strict(
                        produit_id=produit_id, bijouterie_id=bid, delta_qty=qty,
                        lot_id=lot_obj.pk if lot_obj else None
                    )
                except ValidationError as e:
                    # rollback logique : on remet le réservé (pour ce qui a déjà été décrémenté)
                    _stock_increment_strict(
                        produit_id=produit_id, bijouterie_id=None, delta_qty=qty,
                        lot_id=lot_obj.pk if lot_obj else None
                    )
                    return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)

                # log mouvement
                log_move(
                    produit=produit,
                    qty=qty,
                    movement_type=MovementType.ALLOCATE,
                    src_bucket=Bucket.RESERVED,
                    dst_bucket=Bucket.BIJOUTERIE,
                    dst_bijouterie_id=bid,
                    unit_cost=None,  # tu peux passer un coût si utile (ex: dernier coût lot)
                    lot=lot_obj,
                    user=user,
                    reason="Affectation stock réservé → bijouterie",
                )
                per_shop_res.append({"bijouterie_id": bid, "delta": qty})

            # Snapshot après
            res_after, _ = _snapshot_stock(produit_id=produit_id, lot_id=lot_obj.pk if lot_obj else None)

            # (Optionnel) recaler quantite_restante du lot = on-hand (réservé + bijouteries)
            if lot_obj:
                _, new_bij = _snapshot_stock(produit_id=produit_id, lot_id=lot_obj.pk)
                on_hand = int(res_after + sum(new_bij.values()))
                if on_hand != lot_obj.quantite_restante:
                    lot_obj.quantite_restante = on_hand
                    lot_obj.save(update_fields=["quantite_restante"])

            results.append({
                "produit": produit_id,
                "lot_id": lot_obj.pk if lot_obj else None,
                "reserved_before": res_before,
                "reserved_after": res_after,
                "by_shop": per_shop_res,
            })

        return Response(
            {"message": "Affectations réalisées avec succès.", "results": results},
            status=status.HTTP_200_OK
        )
        
# -----------END Affectation


# def _auto_decrement_any_bucket_with_trace(produit_id: int, qty: int):
#     """
#     Wrapper: utilise _dec_auto() et renvoie une trace exploitable
#     pour logger un mouvement CANCEL_PURCHASE par fragment retiré.
#     """
#     allocations = _dec_auto(produit_id, qty)  # [(bucket, bijouterie_id, q), ...]
#     return [
#         {"src_bucket": bucket, "src_bijouterie_id": bij_id, "qty": q}
#         for (bucket, bij_id, q) in allocations
#     ]


# class AchatCancelView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         tags=["Achats"],
#         operation_summary="Annuler un achat (stock + inventaire + comptabilité)",
#         operation_description=(
#             "Annule l'achat et retire les quantités des stocks.\n"
#             "- Mode **contrôlé** : fournir `reverse_allocations` (par produit/bucket) pour viser exactement réservé/bijouterie.\n"
#             "- Mode **auto** : retire d'abord du **réservé**, puis des **bijouteries**.\n"
#             "Chaque retrait génère un `InventoryMovement` de type `CANCEL_PURCHASE` (src → EXTERNAL).\n"
#             "Enfin, la pièce d'achat est **extournée** via `reverse_purchase_entry()`."
#         ),
#         manual_parameters=[
#             openapi.Parameter(
#                 name="achat_id", in_=openapi.IN_PATH, type=openapi.TYPE_INTEGER,
#                 description="ID de l'achat à annuler", required=True
#             ),
#         ],
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             properties={
#                 "reason": openapi.Schema(type=openapi.TYPE_STRING),
#                 "reverse_allocations": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["produit_id", "allocations"],
#                         properties={
#                             "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "allocations": openapi.Schema(
#                                 type=openapi.TYPE_ARRAY,
#                                 items=openapi.Schema(
#                                     type=openapi.TYPE_OBJECT,
#                                     required=["quantite"],
#                                     properties={
#                                         "bijouterie_id": openapi.Schema(type=openapi.TYPE_INTEGER, nullable=True),
#                                         "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, minimum=1),
#                                     },
#                                 ),
#                             ),
#                         },
#                     ),
#                 ),
#             },
#             example={
#                 "reason": "Erreur de saisie fournisseur",
#                 "reverse_allocations": [
#                     {
#                         "produit_id": 1,
#                         "allocations": [
#                             {"bijouterie_id": None, "quantite": 3},  # réservé
#                             {"bijouterie_id": 2, "quantite": 2},     # bijouterie 2
#                         ],
#                     }
#                 ],
#             },
#         ),
#     )
#     @transaction.atomic
#     def post(self, request, achat_id: int):
#         user = request.user
#         # contrôle d’accès (admin/manager)
#         if not (getattr(user, "user_role", None) and user.user_role.role in ["admin", "manager"]):
#             return Response({"detail": "Access Denied"}, status=403)

#         achat = get_object_or_404(Achat.objects.select_for_update(), pk=achat_id)

#         # idempotence simple
#         if getattr(achat, "status", None) == "cancelled":
#             return Response({"message": "Achat déjà annulé", "achat_id": achat.id}, status=200)

#         # quantités par produit
#         lignes = (
#             AchatProduit.objects.filter(achat=achat)
#             .values("produit_id")
#             .annotate(total=Sum("quantite"))
#         )
#         if not lignes:
#             return Response({"detail": "Aucun produit dans cet achat."}, status=400)

#         qty_by_prod = {row["produit_id"]: int(row["total"] or 0) for row in lignes}

#         payload = request.data or {}
#         reason = (payload.get("reason") or "").strip() or "Annulation achat"
#         reverse_allocations = payload.get("reverse_allocations")

#         inventory_movements = []
#         mode = "auto"

#         try:
#             if reverse_allocations:
#                 # ----- MODE CONTRÔLÉ : décrément EXACT + log par fragment -----
#                 mode = "controlled"
#                 for item in reverse_allocations:
#                     produit_id = int(item["produit_id"])
#                     allocs = item.get("allocations") or []
#                     if produit_id not in qty_by_prod:
#                         return Response(
#                             {"detail": f"produit_id={produit_id} n'appartient pas à cet achat."},
#                             status=400
#                         )
#                     if sum(int(a.get("quantite", 0)) for a in allocs) != qty_by_prod[produit_id]:
#                         return Response(
#                             {"detail": f"Les allocations pour produit_id={produit_id} doivent totaliser {qty_by_prod[produit_id]}."},
#                             status=400
#                         )

#                     produit = get_object_or_404(Produit, pk=produit_id)
#                     for a in allocs:
#                         raw_bid = a.get("bijouterie_id", None)
#                         q = int(a.get("quantite", 0))
#                         if q <= 0:
#                             continue
#                         bij_id = None if (raw_bid in (None, "", 0)) else int(raw_bid)

#                         # 1) décrémente exactement le bucket ciblé
#                         _dec_exact(produit_id, bij_id, q)

#                         # 2) log inventaire src -> EXTERNAL
#                         mv = log_move(
#                             produit=produit,
#                             qty=q,
#                             movement_type=MovementType.CANCEL_PURCHASE,
#                             src_bucket=(Bucket.RESERVED if bij_id is None else Bucket.BIJOUTERIE),
#                             src_bijouterie_id=(None if bij_id is None else bij_id),
#                             dst_bucket=Bucket.EXTERNAL,
#                             unit_cost=None,
#                             achat=achat,
#                             achat_ligne=None,
#                             user=user,
#                             reason=reason,
#                         )
#                         inventory_movements.append(mv.id)
#             else:
#                 # ----- MODE AUTO : réservé d’abord, puis bijouteries + log par fragments -----
#                 for produit_id, total_qty in qty_by_prod.items():
#                     produit = get_object_or_404(Produit, pk=produit_id)
#                     trace = _dec_auto(produit_id, total_qty)
#                     # trace = _auto_decrement_any_bucket_with_trace(produit_id, total_qty)
#                     for frag in trace:
#                         mv = log_move(
#                             produit=produit,
#                             qty=frag["qty"],
#                             movement_type=MovementType.CANCEL_PURCHASE,
#                             src_bucket=frag["src_bucket"],
#                             src_bijouterie_id=frag["src_bijouterie_id"],
#                             dst_bucket=Bucket.EXTERNAL,
#                             unit_cost=None,
#                             achat=achat,
#                             achat_ligne=None,
#                             user=user,
#                             reason=reason,
#                         )
#                         inventory_movements.append(mv.id)

#             # ----- COMPTABILITÉ : extourne la pièce du purchase -----
#             reverse_purchase_entry(achat, user=user)

#             # ----- Marque l’achat annulé (si champs présents) -----
#             updated_fields = []
#             if hasattr(achat, "status"):
#                 achat.status = "cancelled"; updated_fields.append("status")
#             if hasattr(achat, "cancelled_at"):
#                 achat.cancelled_at = timezone.now(); updated_fields.append("cancelled_at")
#             if hasattr(achat, "cancelled_by"):
#                 achat.cancelled_by = user; updated_fields.append("cancelled_by")
#             if hasattr(achat, "cancel_reason"):
#                 achat.cancel_reason = reason; updated_fields.append("cancel_reason")
#             if updated_fields:
#                 achat.save(update_fields=updated_fields)

#             return Response(
#                 {
#                     "message": "Achat annulé avec succès",
#                     "achat_id": achat.id,
#                     "mode": mode,
#                     "inventory_movements": inventory_movements,
#                     "accounting_reversed": True,
#                 },
#                 status=200,
#             )

#         except ValueError as e:
#             return Response({"detail": str(e)}, status=409)
#         except Exception as e:
#             return Response({"detail": str(e)}, status=500)


# ------------------Cencel

# # ---------- log mouvement (direct sur InventoryMovement) ----------
# def _log_move(*, produit, qty: int, src_bucket, dst_bucket, src_bijouterie_id=None,
#               achat=None, achat_ligne=None, user=None, reason: str = ""):
#     mv = InventoryMovement.objects.create(
#         produit=produit,
#         movement_type=MovementType.CANCEL_PURCHASE,
#         qty=qty,
#         unit_cost=None,  # pas d’évaluation ici
#         src_bucket=src_bucket,
#         src_bijouterie_id=src_bijouterie_id,
#         dst_bucket=dst_bucket,
#         dst_bijouterie_id=None,
#         achat=achat,
#         achat_ligne=achat_ligne,
#         created_by=user,
#         reason=reason or "Annulation achat",
#         occurred_at=timezone.now(),
#         is_locked=True,
#     )
#     return mv.id

# # ---------- helpers accès ----------
# def _role_ok(user) -> bool:
#     return bool(getattr(user, "user_role", None) and user.user_role.role in ["admin", "manager"])

# def _reservation_key(pid: int) -> str:
#     return f"RES-{pid}"

# # ---------- décrément “exact” d’un bucket ----------
# def _dec_exact(produit_id: int, bijouterie_id: int | None, qty: int):
#     if qty <= 0:
#         return
#     if bijouterie_id is None:
#         st = (Stock.objects
#               .select_for_update()
#               .filter(produit_id=produit_id, bijouterie__isnull=True, reservation_key=_reservation_key(produit_id))
#               .first())
#     else:
#         st = (Stock.objects
#               .select_for_update()
#               .filter(produit_id=produit_id, bijouterie_id=bijouterie_id)
#               .first())
#     if not st or st.quantite < qty:
#         cible = "réservé" if bijouterie_id is None else f"bijouterie={bijouterie_id}"
#         raise ValueError(f"Stock insuffisant pour produit={produit_id} ({cible}). Requis={qty}, dispo={getattr(st, 'quantite', 0)}")
#     Stock.objects.filter(pk=st.pk).update(quantite=F("quantite") - qty)

# # ---------- décrément automatique avec “trace” pour audit ----------
# def _dec_auto_with_trace(produit_id: int, total_qty: int):
#     """
#     Retire 'total_qty' en privilégiant:
#     1) stock réservé, puis
#     2) stocks attribués (bijouteries, ordre par id).
#     Retourne une liste de fragments: [{"src_bucket": ..., "src_bijouterie_id": ..., "qty": ...}]
#     """
#     if total_qty <= 0:
#         return []
#     trace = []

#     # 1) réservé
#     reserved = (Stock.objects
#                 .select_for_update()
#                 .filter(produit_id=produit_id, bijouterie__isnull=True, reservation_key=_reservation_key(produit_id))
#                 .first())
#     if reserved and total_qty > 0:
#         take = min(reserved.quantite, total_qty)
#         if take > 0:
#             Stock.objects.filter(pk=reserved.pk).update(quantite=F("quantite") - take)
#             trace.append({"src_bucket": Bucket.RESERVED, "src_bijouterie_id": None, "qty": take})
#             total_qty -= take

#     # 2) attribué par bijouterie
#     if total_qty > 0:
#         buckets = (Stock.objects
#                    .select_for_update()
#                    .filter(produit_id=produit_id, bijouterie__isnull=False, quantite__gt=0)
#                    .order_by("bijouterie_id"))
#         for b in buckets:
#             if total_qty <= 0:
#                 break
#             take = min(b.quantite, total_qty)
#             if take > 0:
#                 Stock.objects.filter(pk=b.pk).update(quantite=F("quantite") - take)
#                 trace.append({"src_bucket": Bucket.BIJOUTERIE, "src_bijouterie_id": b.bijouterie_id, "qty": take})
#                 total_qty -= take

#     if total_qty > 0:
#         raise ValueError(f"Stock global insuffisant pour produit={produit_id}. Reste à retirer={total_qty}")

#     return trace


# class AchatCancelView(APIView):
#     """
#     Annule un achat et retire les quantités des stocks **avec journal d’inventaire (audit)**.
#     - Mode contrôlé: `reverse_allocations` indique exactement d’où retirer (réservé / bijouterie).
#     - Mode auto: retire d’abord du réservé, puis des bijouteries.
#     """
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         tags=["Achats"],
#         operation_summary="Annuler un achat (inventaire automatique + journal d’audit)",
#         operation_description=(
#             "Annule l'achat et décrémente les stocks.\n\n"
#             "• **Contrôlé**: fournir `reverse_allocations` pour cibler précisément réservé/bijouteries.\n"
#             "• **Auto**: par défaut, retire d’abord du **réservé**, puis des **bijouteries**.\n\n"
#             "Chaque retrait crée un `InventoryMovement` de type `CANCEL_PURCHASE` (src → EXTERNAL). "
#             "Aucune écriture comptable n’est générée ici (vue dédiée inventaire/audit).\n\n"
#             "**Rôles**: admin, manager."
#         ),
#         manual_parameters=[
#             openapi.Parameter(
#                 name="achat_id", in_=openapi.IN_PATH, type=openapi.TYPE_INTEGER,
#                 required=True, description="ID de l'achat à annuler",
#             )
#         ],
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             properties={
#                 "reason": openapi.Schema(type=openapi.TYPE_STRING, description="Motif de l’annulation (journal d’audit)"),
#                 "reverse_allocations": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     description="Mode contrôlé: répartition exacte des retraits par produit et bucket.",
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["produit_id", "allocations"],
#                         properties={
#                             "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "allocations": openapi.Schema(
#                                 type=openapi.TYPE_ARRAY,
#                                 items=openapi.Schema(
#                                     type=openapi.TYPE_OBJECT,
#                                     required=["quantite"],
#                                     properties={
#                                         "bijouterie_id": openapi.Schema(
#                                             type=openapi.TYPE_INTEGER, nullable=True,
#                                             description="null/0 ⇒ réservé ; sinon ID de la bijouterie"
#                                         ),
#                                         "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, minimum=1),
#                                     }
#                                 )
#                             ),
#                         }
#                     )
#                 )
#             },
#             example={
#                 "reason": "Erreur de saisie fournisseur",
#                 "reverse_allocations": [
#                     {"produit_id": 1, "allocations": [
#                         {"bijouterie_id": None, "quantite": 3},
#                         {"bijouterie_id": 2, "quantite": 2}
#                     ]}
#                 ]
#             }
#         ),
#         responses={
#             200: openapi.Response(
#                 "Achat annulé (inventaire)",
#                 openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     properties={
#                         "message": openapi.Schema(type=openapi.TYPE_STRING),
#                         "achat_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                         "mode": openapi.Schema(type=openapi.TYPE_STRING, enum=["controlled", "auto"]),
#                         "movements": openapi.Schema(
#                             type=openapi.TYPE_ARRAY,
#                             items=openapi.Schema(
#                                 type=openapi.TYPE_OBJECT,
#                                 properties={
#                                     "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                                     "fragments": openapi.Schema(
#                                         type=openapi.TYPE_ARRAY,
#                                         items=openapi.Schema(
#                                             type=openapi.TYPE_OBJECT,
#                                             properties={
#                                                 "src_bucket": openapi.Schema(type=openapi.TYPE_STRING),
#                                                 "src_bijouterie_id": openapi.Schema(type=openapi.TYPE_INTEGER, nullable=True),
#                                                 "qty": openapi.Schema(type=openapi.TYPE_INTEGER),
#                                                 "movement_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                                             }
#                                         )
#                                     )
#                                 }
#                             )
#                         )
#                     }
#                 )
#             ),
#             403: "Accès refusé",
#             404: "Achat introuvable",
#             409: "Conflit: stock insuffisant",
#             500: "Erreur serveur"
#         }
#     )
#     @transaction.atomic
#     def post(self, request, achat_id: int):
#         user = request.user
#         if not _role_ok(user):
#             return Response({"detail": "Access Denied"}, status=403)

#         achat = get_object_or_404(Achat.objects.select_for_update(), pk=achat_id)

#         # Idempotence douce
#         if getattr(achat, "status", None) == "cancelled":
#             return Response({"message": "Achat déjà annulé", "achat_id": achat.id}, status=200)

#         # Total par produit (quantités à retirer)
#         lignes = (AchatProduit.objects
#                   .filter(achat=achat)
#                   .values("produit_id")
#                   .annotate(total=Sum("quantite")))
#         if not lignes:
#             return Response({"detail": "Aucun produit dans cet achat."}, status=400)

#         qty_by_prod = {row["produit_id"]: int(row["total"] or 0) for row in lignes}

#         payload = request.data or {}
#         reason = (payload.get("reason") or "").strip() or "Annulation achat"
#         reverse_allocations = payload.get("reverse_allocations")

#         results = []
#         mode = "auto"

#         try:
#             if reverse_allocations:
#                 mode = "controlled"
#                 for item in reverse_allocations:
#                     produit_id = int(item["produit_id"])
#                     if produit_id not in qty_by_prod:
#                         return Response({"detail": f"produit_id={produit_id} n'appartient pas à cet achat."}, status=400)

#                     allocs = item.get("allocations") or []
#                     if sum(int(a.get("quantite", 0)) for a in allocs) != qty_by_prod[produit_id]:
#                         return Response(
#                             {"detail": f"Les allocations pour produit_id={produit_id} doivent totaliser {qty_by_prod[produit_id]}."},
#                             status=400
#                         )

#                     produit = get_object_or_404(Produit, pk=produit_id)
#                     frags = []

#                     for a in allocs:
#                         raw_bid = a.get("bijouterie_id", None)
#                         q = int(a.get("quantite", 0))
#                         if q <= 0:
#                             continue
#                         bij_id = None if (raw_bid in (None, "", 0)) else int(raw_bid)

#                         # 1) décrément exact
#                         _dec_exact(produit_id, bij_id, q)

#                         # 2) log inventaire (src → EXTERNAL)
#                         mv_id = _log_move(
#                             produit=produit, qty=q,
#                             src_bucket=(Bucket.RESERVED if bij_id is None else Bucket.BIJOUTERIE),
#                             src_bijouterie_id=(None if bij_id is None else bij_id),
#                             dst_bucket=Bucket.EXTERNAL,
#                             achat=achat, achat_ligne=None, user=user, reason=reason,
#                         )
#                         frags.append({
#                             "src_bucket": Bucket.RESERVED if bij_id is None else Bucket.BIJOUTERIE,
#                             "src_bijouterie_id": bij_id,
#                             "qty": q,
#                             "movement_id": mv_id,
#                         })

#                     results.append({"produit_id": produit_id, "fragments": frags})

#             else:
#                 # AUTO: réservé d’abord, puis bijouteries
#                 for produit_id, total_qty in qty_by_prod.items():
#                     produit = get_object_or_404(Produit, pk=produit_id)
#                     trace = _dec_auto_with_trace(produit_id, total_qty)
#                     frags = []
#                     for frag in trace:
#                         mv_id = _log_move(
#                             produit=produit,
#                             qty=frag["qty"],
#                             src_bucket=frag["src_bucket"],
#                             src_bijouterie_id=frag["src_bijouterie_id"],
#                             dst_bucket=Bucket.EXTERNAL,
#                             achat=achat, achat_ligne=None, user=user, reason=reason,
#                         )
#                         frags.append({
#                             "src_bucket": frag["src_bucket"],
#                             "src_bijouterie_id": frag["src_bijouterie_id"],
#                             "qty": frag["qty"],
#                             "movement_id": mv_id,
#                         })
#                     results.append({"produit_id": produit_id, "fragments": frags})

#             # Marquage achat annulé (si champs présents dans ton modèle)
#             updated = []
#             if hasattr(achat, "status"): achat.status = "cancelled"; updated.append("status")
#             if hasattr(achat, "cancelled_at"): achat.cancelled_at = timezone.now(); updated.append("cancelled_at")
#             if hasattr(achat, "cancelled_by"): achat.cancelled_by = user; updated.append("cancelled_by")
#             if hasattr(achat, "cancel_reason"): achat.cancel_reason = reason; updated.append("cancel_reason")
#             if updated:
#                 achat.save(update_fields=updated)

#             return Response({
#                 "message": "Achat annulé (inventaire journalisé)",
#                 "achat_id": achat.id,
#                 "mode": mode,
#                 "movements": results
#             }, status=200)

#         except ValueError as e:
#             return Response({"detail": str(e)}, status=409)
#         except Exception as e:
#             return Response({"detail": str(e)}, status=500)


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

# # ---------- Helpers ----------
# def _role_ok(user) -> bool:
#     """Autorise uniquement admin / manager"""
#     return bool(getattr(user, "user_role", None) and user.user_role.role in ["admin", "manager"])


# def _decrement_bucket(produit_id: int, bijouterie_id: int | None, qty: int):
#     """
#     Retire 'qty' unités d'un 'bucket' de stock :
#     - bijouterie_id=None -> stock réservé (reservation_key='RES-<produit_id>')
#     - bijouterie_id=int  -> stock attribué à cette bijouterie
#     Lève ValueError si stock insuffisant.
#     """
#     if qty <= 0:
#         return

#     if bijouterie_id is None:
#         reservation_key = f"RES-{produit_id}"
#         stock = (
#             Stock.objects.select_for_update()
#             .filter(
#                 produit_id=produit_id,
#                 bijouterie__isnull=True,
#                 reservation_key=reservation_key,
#             )
#             .first()
#         )
#     else:
#         stock = (
#             Stock.objects.select_for_update()
#             .filter(
#                 produit_id=produit_id,
#                 bijouterie_id=bijouterie_id,
#             )
#             .first()
#         )

#     if not stock or stock.quantite < qty:
#         cible = "réservé" if bijouterie_id is None else f"bijouterie={bijouterie_id}"
#         raise ValueError(
#             f"Stock insuffisant pour produit={produit_id} ({cible}). "
#             f"Requis={qty}, dispo={getattr(stock, 'quantite', 0)}"
#         )

#     Stock.objects.filter(pk=stock.pk).update(quantite=F("quantite") - qty)


# def _auto_decrement_any_bucket(produit_id: int, qty: int):
#     """
#     Retire automatiquement 'qty' en priorisant :
#     1) le stock réservé
#     2) puis les stocks attribués (toutes bijouteries, ordre arbitraire)
#     Lève ValueError si insuffisant.
#     """
#     if qty <= 0:
#         return

#     # 1) réservé
#     reservation_key = f"RES-{produit_id}"
#     reserved = (
#         Stock.objects.select_for_update()
#         .filter(
#             produit_id=produit_id,
#             bijouterie__isnull=True,
#             reservation_key=reservation_key,
#         )
#         .first()
#     )
#     if reserved:
#         take = min(reserved.quantite, qty)
#         if take > 0:
#             Stock.objects.filter(pk=reserved.pk).update(quantite=F("quantite") - take)
#             qty -= take

#     if qty <= 0:
#         return

#     # 2) attribué (toutes bijouteries ayant du stock)
#     buckets = (
#         Stock.objects.select_for_update()
#         .filter(produit_id=produit_id, bijouterie__isnull=False, quantite__gt=0)
#         .order_by("bijouterie_id")
#     )
#     for b in buckets:
#         if qty <= 0:
#             break
#         take = min(b.quantite, qty)
#         if take > 0:
#             Stock.objects.filter(pk=b.pk).update(quantite=F("quantite") - take)
#             qty -= take

#     if qty > 0:
#         raise ValueError(f"Stock global insuffisant pour produit={produit_id}. Reste à retirer={qty}")


# # ---------- Vue ----------
# class AchatCancelView(APIView):
#     """
#     Annule un achat et retire les quantités du stock.

#     - Si `reverse_allocations` est fourni, on suit précisément d'où retirer :
#       [
#         {"produit_id": 1, "allocations": [
#             {"bijouterie_id": null, "quantite": 3},        # réservé
#             {"bijouterie_id": 2, "quantite": 2}            # bijouterie 2
#         ]},
#         {"produit_id": 5, "allocations": [
#             {"bijouterie_id": 4, "quantite": 1}
#         ]}
#       ]

#     - Sinon : on retire automatiquement d'abord du stock RÉSERVÉ, puis des bijouteries.
#     """
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         tags=["Achats"],
#         operation_summary="Annuler un achat et décrémenter les stocks",
#         operation_description=(
#             "Annule l'achat spécifié et retire des stocks les quantités des produits concernés.\n\n"
#             "**Deux modes :**\n"
#             "1) **Contrôlé** (avec `reverse_allocations`) : précise exactement d’où retirer (réservé / bijouterie).\n"
#             "2) **Automatique** (sans `reverse_allocations`) : retire d’abord du **stock réservé**, puis des **bijouteries** si besoin.\n\n"
#             "**Remarques :**\n"
#             "- `bijouterie_id` peut être `null`/`0` pour viser le stock **réservé**.\n"
#             "- Idempotent : si l’achat est déjà annulé, renvoie 200 avec un message adapté.\n"
#             "- S’il manque du stock lors d’un retrait, renvoie **409 (Conflict)**."
#         ),
#         manual_parameters=[
#             openapi.Parameter(
#                 name="achat_id",
#                 in_=openapi.IN_PATH,
#                 description="ID de l'achat à annuler",
#                 type=openapi.TYPE_INTEGER,
#                 required=True,
#             ),
#         ],
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             properties={
#                 "reason": openapi.Schema(
#                     type=openapi.TYPE_STRING,
#                     description="Raison de l'annulation (optionnelle). Sera enregistrée si `Achat` a un champ `cancel_reason`.",
#                 ),
#                 "reverse_allocations": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     description=(
#                         "Répartition **précise** des retraits par produit et par bucket. "
#                         "Pour chaque `produit_id`, la somme des `quantite` doit égaler la quantité totale de ce produit dans l'achat."
#                     ),
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["produit_id", "allocations"],
#                         properties={
#                             "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "allocations": openapi.Schema(
#                                 type=openapi.TYPE_ARRAY,
#                                 items=openapi.Schema(
#                                     type=openapi.TYPE_OBJECT,
#                                     required=["quantite"],
#                                     properties={
#                                         "bijouterie_id": openapi.Schema(
#                                             type=openapi.TYPE_INTEGER,
#                                             nullable=True,
#                                             description="`null`/`0` ⇒ stock réservé ; sinon ID de la bijouterie.",
#                                         ),
#                                         "quantite": openapi.Schema(
#                                             type=openapi.TYPE_INTEGER,
#                                             minimum=1,
#                                             description="Quantité à retirer de ce bucket.",
#                                         ),
#                                     },
#                                 ),
#                             ),
#                         },
#                     ),
#                 ),
#             },
#             example={
#                 "reason": "Erreur de saisie fournisseur",
#                 "reverse_allocations": [
#                     {
#                         "produit_id": 1,
#                         "allocations": [
#                             {"bijouterie_id": None, "quantite": 3},  # réservé
#                             {"bijouterie_id": 2, "quantite": 2},     # bijouterie 2
#                         ],
#                     },
#                     {
#                         "produit_id": 5,
#                         "allocations": [
#                             {"bijouterie_id": 4, "quantite": 1}
#                         ],
#                     },
#                 ],
#             },
#         ),
#         responses={
#             200: openapi.Response(
#                 description="Achat annulé",
#                 schema=openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     properties={
#                         "message": openapi.Schema(type=openapi.TYPE_STRING),
#                         "achat_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                         "mode": openapi.Schema(
#                             type=openapi.TYPE_STRING,
#                             enum=["controlled", "auto"],
#                             description="`controlled` si `reverse_allocations` fourni, sinon `auto`."
#                         ),
#                     },
#                 ),
#             ),
#             403: openapi.Response(description="Accès refusé"),
#             404: openapi.Response(description="Achat introuvable"),
#             409: openapi.Response(description="Conflit : stock insuffisant (réservé/bijouterie)"),
#             500: openapi.Response(description="Erreur serveur"),
#         },
#     )
#     @transaction.atomic
#     def post(self, request, achat_id: int):
#         user = request.user
#         if not _role_ok(user):
#             return Response({"detail": "Access Denied"}, status=403)

#         achat = get_object_or_404(Achat.objects.select_for_update(), pk=achat_id)

#         # Idempotence simple : si déjà annulé, OK
#         if getattr(achat, "status", None) == "cancelled":
#             return Response({"message": "Achat déjà annulé", "achat_id": achat.id}, status=200)

#         # Total des quantités par produit dans l'achat
#         lignes = (
#             AchatProduit.objects
#             .filter(achat=achat)
#             .values("produit_id")
#             .annotate(total=Sum("quantite"))
#         )
#         if not lignes:
#             return Response({"detail": "Aucun produit dans cet achat."}, status=400)

#         qty_by_prod = {row["produit_id"]: int(row["total"] or 0) for row in lignes}

#         payload = request.data or {}
#         reason = payload.get("reason", "")
#         reverse_allocations = payload.get("reverse_allocations")

#         try:
#             if reverse_allocations:
#                 # Mode contrôlé : on respecte les allocations fournies
#                 for item in reverse_allocations:
#                     produit_id = int(item["produit_id"])
#                     allocs = item.get("allocations") or []
#                     if produit_id not in qty_by_prod:
#                         return Response(
#                             {"detail": f"produit_id={produit_id} n'appartient pas à cet achat."},
#                             status=400
#                         )

#                     sum_alloc = sum(int(a.get("quantite", 0)) for a in allocs)
#                     if sum_alloc != qty_by_prod[produit_id]:
#                         return Response(
#                             {"detail": f"Les allocations pour produit_id={produit_id} doivent totaliser {qty_by_prod[produit_id]}."},
#                             status=400
#                         )

#                     for a in allocs:
#                         bid = a.get("bijouterie_id", None)
#                         q = int(a.get("quantite", 0))
#                         if q <= 0:
#                             continue
#                         bij_id = None if (bid in (None, "", 0)) else int(bid)
#                         _decrement_bucket(produit_id, bij_id, q)

#             else:
#                 # Mode automatique : retirer la quantité totale de chaque produit
#                 for produit_id, total_qty in qty_by_prod.items():
#                     _auto_decrement_any_bucket(produit_id, total_qty)

#             # Marque l'achat comme annulé si les champs existent
#             updated_fields = []
#             if hasattr(achat, "status"):
#                 achat.status = "cancelled"
#                 updated_fields.append("status")
#             if hasattr(achat, "cancelled_at"):
#                 achat.cancelled_at = timezone.now()
#                 updated_fields.append("cancelled_at")
#             if hasattr(achat, "cancelled_by"):
#                 achat.cancelled_by = user
#                 updated_fields.append("cancelled_by")
#             if hasattr(achat, "cancel_reason"):
#                 achat.cancel_reason = reason
#                 updated_fields.append("cancel_reason")

#             if updated_fields:
#                 achat.save(update_fields=updated_fields)

#             return Response(
#                 {
#                     "message": "Achat annulé avec succès",
#                     "achat_id": achat.id,
#                     "mode": "controlled" if reverse_allocations else "auto",
#                 },
#                 status=200,
#             )

#         except ValueError as e:
#             # Manque de stock dans un bucket -> 409
#             return Response({"detail": str(e)}, status=409)
#         except Exception as e:
#             return Response({"detail": str(e)}, status=500)


# ------------------  AchatCancelView
# ... tes helpers _role_ok, _decrement_bucket, et la NOUVELLE _auto_decrement_any_bucket_with_trace ...

# class AchatCancelView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         tags=["Achats"],
#         operation_summary="Annuler un achat et décrémenter les stocks (avec log inventaire)",
#         operation_description=(
#             "Annule l'achat et retire les quantités des stocks.\n"
#             "- Mode contrôlé : utiliser `reverse_allocations` pour préciser d'où retirer par produit/bucket.\n"
#             "- Mode automatique : retrait d'abord du **réservé**, puis des **bijouteries**.\n"
#             "Chaque retrait génère un `InventoryMovement` de type `CANCEL_PURCHASE` (src → EXTERNAL)."
#         ),
#         # ... (garde ta même spec swagger déjà en place) ...
#     )
#     @transaction.atomic
#     def post(self, request, achat_id: int):
#         user = request.user
#         if not _role_ok(user):
#             return Response({"detail": "Access Denied"}, status=403)

#         achat = get_object_or_404(Achat.objects.select_for_update(), pk=achat_id)

#         if getattr(achat, "status", None) == "cancelled":
#             return Response({"message": "Achat déjà annulé", "achat_id": achat.id}, status=200)

#         # quantités par produit
#         lignes = (
#             AchatProduit.objects.filter(achat=achat)
#             .values("produit_id")
#             .annotate(total=Sum("quantite"))
#         )
#         if not lignes:
#             return Response({"detail": "Aucun produit dans cet achat."}, status=400)

#         qty_by_prod = {row["produit_id"]: int(row["total"] or 0) for row in lignes}

#         payload = request.data or {}
#         reason  = (payload.get("reason") or "").strip() or "Annulation achat"
#         reverse_allocations = payload.get("reverse_allocations")

#         inventory_movements = []  # pour répondre avec les IDs loggés

#         try:
#             if reverse_allocations:
#                 # ---- MODE CONTROLE ----
#                 for item in reverse_allocations:
#                     produit_id = int(item["produit_id"])
#                     allocs = item.get("allocations") or []
#                     if produit_id not in qty_by_prod:
#                         return Response(
#                             {"detail": f"produit_id={produit_id} n'appartient pas à cet achat."},
#                             status=400
#                         )
#                     sum_alloc = sum(int(a.get("quantite", 0)) for a in allocs)
#                     if sum_alloc != qty_by_prod[produit_id]:
#                         return Response(
#                             {"detail": f"Les allocations pour produit_id={produit_id} doivent totaliser {qty_by_prod[produit_id]}."},
#                             status=400
#                         )

#                     # Exécute retraits + log inventaire par allocation
#                     for a in allocs:
#                         raw_bid = a.get("bijouterie_id", None)
#                         q = int(a.get("quantite", 0))
#                         if q <= 0:
#                             continue
#                         bij_id = None if (raw_bid in (None, "", 0)) else int(raw_bid)

#                         # 1) décrément bucket ciblé
#                         _decrement_bucket(produit_id, bij_id, q)

#                         # 2) log inventaire src -> EXTERNAL
#                         mv = log_move(
#                             produit_id=produit_id,
#                             qty=q,
#                             movement_type=MovementType.CANCEL_PURCHASE,
#                             src_bucket=(Bucket.RESERVED if bij_id is None else Bucket.BIJOUTERIE),
#                             src_bijouterie_id=(None if bij_id is None else bij_id),
#                             dst_bucket=Bucket.EXTERNAL,
#                             dst_bijouterie_id=None,
#                             unit_cost=None,
#                             achat=achat,
#                             achat_ligne=None,
#                             user=user,
#                             reason=reason,
#                         )
#                         inventory_movements.append(mv.id)

#                 mode = "controlled"

#             else:
#                 # ---- MODE AUTO ----
#                 for produit_id, total_qty in qty_by_prod.items():
#                     trace = _auto_decrement_any_bucket_with_trace(produit_id, total_qty)
#                     # log un mouvement par fragment retiré
#                     for frag in trace:
#                         mv = log_move(
#                             produit_id=produit_id,
#                             qty=frag["qty"],
#                             movement_type=MovementType.CANCEL_PURCHASE,
#                             src_bucket=frag["src_bucket"],
#                             src_bijouterie_id=frag["src_bijouterie_id"],
#                             dst_bucket=Bucket.EXTERNAL,
#                             dst_bijouterie_id=None,
#                             unit_cost=None,
#                             achat=achat,
#                             achat_ligne=None,
#                             user=user,
#                             reason=reason,
#                         )
#                         inventory_movements.append(mv.id)

#                 mode = "auto"

#             # marque l’achat annulé (si ces champs existent)
#             updated_fields = []
#             if hasattr(achat, "status"):
#                 achat.status = "cancelled"
#                 updated_fields.append("status")
#             if hasattr(achat, "cancelled_at"):
#                 achat.cancelled_at = timezone.now()
#                 updated_fields.append("cancelled_at")
#             if hasattr(achat, "cancelled_by"):
#                 achat.cancelled_by = user
#                 updated_fields.append("cancelled_by")
#             if hasattr(achat, "cancel_reason"):
#                 achat.cancel_reason = reason
#                 updated_fields.append("cancel_reason")
#             if updated_fields:
#                 achat.save(update_fields=updated_fields)

#             return Response(
#                 {
#                     "message": "Achat annulé avec succès",
#                     "achat_id": achat.id,
#                     "mode": mode,
#                     "inventory_movements": inventory_movements,  # IDs des mouvements créés
#                 },
#                 status=200,
#             )

#         except ValueError as e:
#             return Response({"detail": str(e)}, status=409)
#         except Exception as e:
#             return Response({"detail": str(e)}, status=500)



# class AchatProduitUpdateAPIView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Modifier un produit spécifique d’un achat, y compris le fournisseur et les données produit.",
#         manual_parameters=[
#             openapi.Parameter('achat_id', openapi.IN_PATH, type=openapi.TYPE_INTEGER, required=True, description="ID de l'achat"),
#             openapi.Parameter('achatproduit_id', openapi.IN_PATH, type=openapi.TYPE_INTEGER, required=True, description="ID du produit d'achat à modifier")
#         ],
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=['quantite', 'prix_achat_gramme', 'tax'],
#             properties={
#                 'quantite': openapi.Schema(type=openapi.TYPE_INTEGER),
#                 'prix_achat_gramme': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal'),
#                 'tax': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal'),
#                 'produit': openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     properties={
#                         'id': openapi.Schema(type=openapi.TYPE_INTEGER),
#                         'nom': openapi.Schema(type=openapi.TYPE_STRING),
#                         'poids': openapi.Schema(type=openapi.TYPE_NUMBER),
#                         # Ajoute d'autres champs modifiables si nécessaire
#                     }
#                 ),
#                 'fournisseur': openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     properties={
#                         'nom': openapi.Schema(type=openapi.TYPE_STRING),
#                         'prenom': openapi.Schema(type=openapi.TYPE_STRING),
#                         'address': openapi.Schema(type=openapi.TYPE_STRING),
#                         'telephone': openapi.Schema(type=openapi.TYPE_STRING),
#                     }
#                 )
#             }
#         ),
#         responses={
#             200: openapi.Response("Produit mis à jour avec succès", AchatProduitSerializer),
#             400: "Erreur de validation",
#             403: "Accès refusé",
#             404: "Non trouvé"
#         }
#     )
#     @transaction.atomic
#     def put(self, request, achat_id, achatproduit_id):
#         role = getattr(request.user.user_role, 'role', None)
#         if role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             achat = Achat.objects.get(id=achat_id)
#             achat_produit = AchatProduit.objects.select_related('produit', 'fournisseur').get(id=achatproduit_id, achat=achat)

#             ancienne_quantite = achat_produit.quantite
#             produit = achat_produit.produit
#             fournisseur = achat_produit.fournisseur
#             stock, _ = Stock.objects.get_or_create(produit=produit)

#             # 1. Fournisseur (si fourni)
#             fournisseur_data = request.data.get('fournisseur')
#             if fournisseur_data and fournisseur:
#                 fournisseur.nom = fournisseur_data.get('nom', fournisseur.nom)
#                 fournisseur.prenom = fournisseur_data.get('prenom', fournisseur.prenom)
#                 fournisseur.address = fournisseur_data.get('address', fournisseur.address)
#                 fournisseur.telephone = fournisseur_data.get('telephone', fournisseur.telephone)
#                 fournisseur.save()

#             # 2. Produit (si fourni et existant)
#             produit_data = request.data.get('produit')
#             if produit_data:
#                 new_produit_id = produit_data.get('id')
#                 if new_produit_id and new_produit_id != produit.id:
#                     try:
#                         new_produit = Produit.objects.get(id=new_produit_id)
#                         produit = new_produit
#                         stock, _ = Stock.objects.get_or_create(produit=produit)  # nouveau stock
#                     except Produit.DoesNotExist:
#                         return Response({"detail": "Produit fourni introuvable."}, status=404)
#                 else:
#                     produit.nom = produit_data.get('nom', produit.nom)
#                     produit.poids = produit_data.get('poids', produit.poids)
#                     produit.save()

#             # 3. Mise à jour principale
#             quantite_nouvelle = int(request.data.get('quantite'))
#             prix_achat_gramme = Decimal(request.data.get('prix_achat_gramme'))
#             tax = Decimal(request.data.get('tax'))

#             if quantite_nouvelle <= 0:
#                 return Response({'detail': "Quantité invalide."}, status=400)

#             poids = produit.poids or 1
#             sous_total = prix_achat_gramme * quantite_nouvelle * poids

#             # Mise à jour de AchatProduit
#             achat_produit.produit = produit
#             achat_produit.quantite = quantite_nouvelle
#             achat_produit.prix_achat_gramme = prix_achat_gramme
#             achat_produit.tax = tax
#             achat_produit.sous_total_prix_achat = sous_total
#             achat_produit.save()

#             # Stock update
#             difference = quantite_nouvelle - ancienne_quantite
#             stock.quantite = (stock.quantite or 0) + difference
#             stock.save()

#             # Update total achat
#             achat.update_total()

#             return Response(AchatProduitSerializer(achat_produit).data, status=200)

#         except Achat.DoesNotExist:
#             return Response({"detail": "Achat non trouvé."}, status=404)
#         except AchatProduit.DoesNotExist:
#             return Response({"detail": "AchatProduit non trouvé."}, status=404)
#         except Exception as e:
#             return Response({"detail": str(e)}, status=500)


# class AchatProduitUpdateAPIView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Modifier un produit spécifique d’un achat.",
#         manual_parameters=[
#             openapi.Parameter('achat_id', openapi.IN_PATH, type=openapi.TYPE_INTEGER, required=True, description="ID de l'achat"),
#             openapi.Parameter('achatproduit_id', openapi.IN_PATH, type=openapi.TYPE_INTEGER, required=True, description="ID de l'achat produit à modifier")
#         ],
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=['quantite', 'prix_achat_gramme', 'tax'],
#             properties={
#                 'quantite': openapi.Schema(type=openapi.TYPE_INTEGER),
#                 'prix_achat_gramme': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal'),
#                 'tax': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal'),
#             }
#         ),
#         responses={
#             200: openapi.Response("Produit mis à jour avec succès", AchatProduitSerializer),
#             400: "Erreur de validation",
#             403: "Accès refusé",
#             404: "Non trouvé"
#         }
#     )
#     @transaction.atomic
#     def put(self, request, achat_id, achatproduit_id):
#         role = getattr(request.user.user_role, 'role', None)
#         if role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             achat = Achat.objects.get(id=achat_id)
#             achat_produit = AchatProduit.objects.select_related('produit').get(id=achatproduit_id, achat=achat)

#             # Stock avant mise à jour
#             ancienne_quantite = achat_produit.quantite
#             produit = achat_produit.produit
#             stock, _ = Stock.objects.get_or_create(produit=produit)

#             # Données entrantes
#             quantite_nouvelle = int(request.data.get('quantite'))
#             prix_achat_gramme = Decimal(request.data.get('prix_achat_gramme'))
#             tax = Decimal(request.data.get('tax'))

#             if quantite_nouvelle <= 0:
#                 return Response({'detail': "Quantité invalide."}, status=400)

#             poids = produit.poids or 1
#             sous_total = prix_achat_gramme * quantite_nouvelle * poids
#             total_ttc = sous_total + tax

#             # Mise à jour de l'objet AchatProduit
#             achat_produit.quantite = quantite_nouvelle
#             achat_produit.prix_achat_gramme = prix_achat_gramme
#             achat_produit.tax = tax
#             achat_produit.sous_total_prix_achat = sous_total
#             achat_produit.save()

#             # Mise à jour du stock (différence)
#             difference = quantite_nouvelle - ancienne_quantite
#             stock.quantite = (stock.quantite or 0) + difference
#             stock.save()

#             # Mise à jour de l'achat global
#             achat.update_total()

#             return Response(AchatProduitSerializer(achat_produit).data, status=200)

#         except Achat.DoesNotExist:
#             return Response({"detail": "Achat non trouvé."}, status=404)
#         except AchatProduit.DoesNotExist:
#             return Response({"detail": "AchatProduit non trouvé."}, status=404)
#         except Exception as e:
#             return Response({"detail": str(e)}, status=500)


# class AchatUpdateAchatProduitAPIView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]
    
#     @swagger_auto_schema(
#         operation_description="Met à jour un achat existant avec ses produits et le fournisseur.",
#         manual_parameters=[
#             openapi.Parameter('achat_id', openapi.IN_PATH, description="ID de l'achat à modifier", type=openapi.TYPE_INTEGER),
#         ],
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             properties={
#                 'fournisseur': openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     properties={
#                         'nom': openapi.Schema(type=openapi.TYPE_STRING),
#                         'prenom': openapi.Schema(type=openapi.TYPE_STRING),
#                         'address': openapi.Schema(type=openapi.TYPE_STRING),
#                         'telephone': openapi.Schema(type=openapi.TYPE_STRING),
#                     }
#                 ),
#                 'produits': openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         properties={
#                             'produit': openapi.Schema(type=openapi.TYPE_OBJECT, properties={
#                                 'id': openapi.Schema(type=openapi.TYPE_INTEGER)
#                             }),
#                             'quantite': openapi.Schema(type=openapi.TYPE_INTEGER),
#                             'prix_achat_gramme': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal'),
#                             'tax': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal'),
#                         }
#                     )
#                 )
#             }
#         ),
#         responses={
#             200: openapi.Response("Mise à jour réussie", AchatSerializer),
#             400: "Requête invalide",
#             403: "Accès refusé",
#             404: "Achat non trouvé"
#         }
#     )

#     @transaction.atomic
#     def put(self, request, achat_id):
#         user_role = getattr(request.user.user_role, 'role', None)
#         if user_role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             achat = Achat.objects.get(id=achat_id)
#             fournisseur_id = achat.fournisseur_id
#             fournisseur_data = request.data.get('fournisseur')

#             # Mise à jour du fournisseur
#             if fournisseur_data:
#                 fournisseur = Fournisseur.objects.get(id=fournisseur_id)
#                 fournisseur.nom = fournisseur_data.get('nom', fournisseur.nom)
#                 fournisseur.prenom = fournisseur_data.get('prenom', fournisseur.prenom)
#                 fournisseur.address = fournisseur_data.get('address', fournisseur.address)
#                 fournisseur.telephone = fournisseur_data.get('telephone', fournisseur.telephone)
#                 fournisseur.save()
#                 achat.fournisseur = fournisseur

#             montant_total = Decimal(0)

#             for produit_data in request.data.get('produits', []):
#                 produit_id = produit_data.get('produit', {}).get('id')
#                 quantite_nouvelle = int(produit_data.get('quantite', 0))
#                 prix_achat_gramme = Decimal(produit_data.get('prix_achat_gramme', 0))
#                 tax = Decimal(produit_data.get('tax', 0))

#                 try:
#                     produit = Produit.objects.get(id=produit_id)
#                 except Produit.DoesNotExist:
#                     return Response({"error": f"Produit ID {produit_id} introuvable"}, status=400)

#                 # Ancienne quantité
#                 achat_produit_obj = AchatProduit.objects.get(achat=achat, produit=produit)
#                 quantite_ancienne = achat_produit_obj.quantite

#                 # Mise à jour ou création
#                 poids = produit.poids or 0
#                 sous_total = prix_achat_gramme * quantite_nouvelle * poids

#                 achat_produit, _ = AchatProduit.objects.update_or_create(
#                     achat=achat,
#                     produit=produit,
#                     fournisseur=achat.fournisseur,
#                     defaults={
#                         'quantite': quantite_nouvelle,
#                         'prix_achat_gramme': prix_achat_gramme,
#                         'tax': tax,
#                         'sous_total_prix_achat': sous_total,
#                     }
#                 )

#                 # Mise à jour du stock (différence)
#                 stock, _ = Stock.objects.get_or_create(produit=produit)
#                 difference = quantite_nouvelle - quantite_ancienne
#                 stock.quantite = (stock.quantite or 0) + difference
#                 stock.save()

#                 montant_total += sous_total + tax

#             achat.montant_total = montant_total
#             achat.montant_total_tax_inclue = montant_total
#             achat.save()

#             updated_achat = Achat.objects.prefetch_related('produits').get(id=achat.id)
#             return Response(AchatSerializer(updated_achat).data, status=200)

#         except Achat.DoesNotExist:
#             return Response({"error": "Achat introuvable"}, status=404)


# # --- helpers (mêmes signatures que dans ta vue de création) ------------------

# def _as_decimal(val, default="0.00") -> Decimal:
#     if val is None or val == "":
#         return Decimal(default)
#     return Decimal(str(val))

# def _role_ok(user) -> bool:
#     return bool(getattr(user, "user_role", None) and user.user_role.role in ["admin", "manager"])

# def upsert_stock_increment(produit_id: int, bijouterie_id: int | None, delta_qty: int):
#     """
#     Incrémente le stock correspondant.
#     - bijouterie_id is None => stock réservé (bijouterie=NULL) via reservation_key='RES-<produit_id>'
#     - sinon stock attribué à la bijouterie.
#     """
#     if delta_qty <= 0:
#         return None

#     if bijouterie_id is None:
#         reservation_key = f"RES-{produit_id}"
#         stock, _ = (
#             Stock.objects.select_for_update()
#             .get_or_create(
#                 produit_id=produit_id,
#                 bijouterie=None,
#                 reservation_key=reservation_key,
#                 defaults={"quantite": 0}
#             )
#         )
#     else:
#         get_object_or_404(Bijouterie, pk=bijouterie_id)
#         stock, _ = (
#             Stock.objects.select_for_update()
#             .get_or_create(
#                 produit_id=produit_id,
#                 bijouterie_id=bijouterie_id,
#                 defaults={"quantite": 0}
#             )
#         )

#     Stock.objects.filter(pk=stock.pk).update(quantite=F("quantite") + int(delta_qty))
#     stock.refresh_from_db(fields=["quantite"])
#     return stock


# # --- Vue d’update ------------------------------------------------------------

# class AchatUpdateCreateView(APIView):
#     """
#     Met à jour un achat existant :
#         - fournisseur (facultatif)
#         - lignes :
#           * si 'achat_produit_id' (ou 'ligne_id') est fourni -> update de la ligne
#                 - si la nouvelle quantité > ancienne => on ajoute le delta au stock
#                 - si la nouvelle quantité < ancienne => REFUS (utiliser endpoint de retrait/transfert)
#           * si pas d'id -> création d'une nouvelle ligne + affectation au stock

#     Affectation du stock (mêmes règles que la création) :
#         - par ligne, vous pouvez passer:
#           * affectations=[{bijouterie_id, quantite}, ...] (ventilation fine)
#           * sinon bijouterie_id (ligne) ; sinon bijouterie_id (global payload)
#       - le reste non affecté part en **stock réservé** (bijouterie NULL)
#     """,
#     """Cette vue refuse la baisse de quantité sur une ligne existante : sans journal de mouvements ni 
#     traçabilité par lots, on ne peut pas déterminer proprement quelles unités retirer (réservées vs 
#     attribuées). Utilisez vos endpoints de retrait/transfert (ex. StockReserveAffectationView, StockTransferView, etc.)."""
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Mettre à jour un achat existant (ajout/modif de lignes, affectations du delta)",
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["achat_id"],
#             properties={
#                 "achat_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                 "bijouterie_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="Bijouterie par défaut (optionnel)"),
#                 "fournisseur": openapi.Schema(
#                     type=openapi.TYPE_OBJECT,
#                     description="Si fourni, upsert sur le téléphone",
#                     required=["nom", "prenom", "telephone"],
#                     properties={
#                         "nom": openapi.Schema(type=openapi.TYPE_STRING),
#                         "prenom": openapi.Schema(type=openapi.TYPE_STRING),
#                         "telephone": openapi.Schema(type=openapi.TYPE_STRING),
#                         "address": openapi.Schema(type=openapi.TYPE_STRING),
#                     }
#                 ),
#                 "produits": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["produit", "quantite", "prix_achat_gramme"],
#                         properties={
#                             # identifier la ligne existante à mettre à jour (optionnel)
#                             "achat_produit_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "ligne_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="alias de achat_produit_id"),
#                             "produit": openapi.Schema(
#                                 type=openapi.TYPE_OBJECT,
#                                 properties={"id": openapi.Schema(type=openapi.TYPE_INTEGER)}
#                             ),
#                             "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, minimum=1),
#                             "prix_achat_gramme": openapi.Schema(type=openapi.TYPE_STRING),
#                             "tax": openapi.Schema(type=openapi.TYPE_STRING, default="0.00"),
#                             "bijouterie_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="Affectation simple pour toute la ligne (delta)"),
#                             "affectations": openapi.Schema(
#                                 type=openapi.TYPE_ARRAY,
#                                 description="Ventilation (delta) par bijouterie",
#                                 items=openapi.Schema(
#                                     type=openapi.TYPE_OBJECT,
#                                     required=["bijouterie_id", "quantite"],
#                                     properties={
#                                         "bijouterie_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                                         "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, minimum=1),
#                                     }
#                                 )
#                             ),
#                         }
#                     )
#                 ),
#             }
#         ),
#         responses={200: openapi.Response("OK", AchatSerializer), 400: "Bad Request", 403: "Forbidden", 404: "Not Found"}
#     )
#     @transaction.atomic
#     def post(self, request):
#         user = request.user
#         if not _role_ok(user):
#             return Response({"detail": "Access Denied"}, status=403)

#         data = request.data or {}
#         achat_id = data.get("achat_id")
#         if not achat_id:
#             return Response({"detail": "achat_id requis."}, status=400)

#         achat = get_object_or_404(Achat, pk=achat_id)

#         # --- Upsert fournisseur (facultatif)
#         fournisseur_data = data.get("fournisseur")
#         if fournisseur_data:
#             for k in ("nom", "prenom", "telephone"):
#                 if k not in fournisseur_data:
#                     return Response({"detail": f"Champ fournisseur manquant: {k}"}, status=400)
#             fournisseur, _ = Fournisseur.objects.get_or_create(
#                 telephone=fournisseur_data["telephone"],
#                 defaults={
#                     "nom": fournisseur_data["nom"],
#                     "prenom": fournisseur_data["prenom"],
#                     "address": fournisseur_data.get("address", ""),
#                 },
#             )
#             achat.fournisseur = fournisseur
#             achat.save(update_fields=["fournisseur"])

#         default_bijouterie_id = data.get("bijouterie_id")
#         stocks_result = []

#         items = data.get("produits") or []
#         if not items:
#             # Rien à changer côté lignes → on renvoie l'achat tel quel
#             return Response({"achat": AchatSerializer(achat).data, "stocks": []}, status=200)

#         try:
#             for item in items:
#                 produit_id = int(item["produit"]["id"])
#                 quantite_new = int(item["quantite"])
#                 if quantite_new <= 0:
#                     return Response({"detail": "La quantité doit être > 0."}, status=400)

#                 prix_achat_gramme = _as_decimal(item.get("prix_achat_gramme"), "0.00")
#                 tax = _as_decimal(item.get("tax"), "0.00")
#                 produit = get_object_or_404(Produit, pk=produit_id)

#                 # Cherche une ligne existante si id fourni
#                 ligne_id = item.get("achat_produit_id") or item.get("ligne_id")
#                 if ligne_id:
#                     ap = get_object_or_404(AchatProduit, pk=int(ligne_id), achat_id=achat.id)
#                     old_qty = int(ap.quantite)

#                     # Maj du prix/tax (le sous-total sera recalculé dans save())
#                     ap.produit = produit
#                     ap.prix_achat_gramme = prix_achat_gramme
#                     ap.tax = tax

#                     if quantite_new < old_qty:
#                         # On refuse la baisse ici (utiliser un endpoint de retrait/transfer)
#                         return Response(
#                             {"detail": f"Diminution non autorisée sur la ligne #{ap.id}. "
#                                        f"Utilisez un endpoint de retrait/transfert de stock."},
#                             status=400
#                         )

#                     ap.quantite = quantite_new
#                     ap.save()  # recalcule sous_total + update_total de l'achat

#                     delta = quantite_new - old_qty
#                     if delta > 0:
#                         # Affectation du delta comme à la création
#                         affectations = item.get("affectations")
#                         if affectations:
#                             somme_aff = sum(int(a.get("quantite", 0)) for a in affectations)
#                             if somme_aff > delta:
#                                 return Response(
#                                     {"detail": f"La somme des affectations ({somme_aff}) dépasse le delta ({delta})."},
#                                     status=400,
#                                 )
#                             for aff in affectations:
#                                 bid = int(aff["bijouterie_id"])
#                                 q = int(aff["quantite"])
#                                 if q <= 0:
#                                     continue
#                                 st = upsert_stock_increment(produit_id, bid, q)
#                                 stocks_result.append({
#                                     "action": "increment",
#                                     "achat_produit_id": ap.id,
#                                     "produit_id": produit_id,
#                                     "bijouterie_id": bid,
#                                     "reserved": False,
#                                     "delta": q,
#                                     "stock_qte_apres": st.quantite,
#                                 })
#                             reste = delta - somme_aff
#                             if reste > 0:
#                                 st = upsert_stock_increment(produit_id, None, reste)
#                                 stocks_result.append({
#                                     "action": "increment",
#                                     "achat_produit_id": ap.id,
#                                     "produit_id": produit_id,
#                                     "bijouterie_id": None,
#                                     "reserved": True,
#                                     "delta": reste,
#                                     "stock_qte_apres": st.quantite,
#                                 })
#                         else:
#                             line_bijouterie_id = item.get("bijouterie_id", default_bijouterie_id)
#                             if line_bijouterie_id in (None, "", 0):
#                                 st = upsert_stock_increment(produit_id, None, delta)
#                                 stocks_result.append({
#                                     "action": "increment",
#                                     "achat_produit_id": ap.id,
#                                     "produit_id": produit_id,
#                                     "bijouterie_id": None,
#                                     "reserved": True,
#                                     "delta": delta,
#                                     "stock_qte_apres": st.quantite,
#                                 })
#                             else:
#                                 bid = int(line_bijouterie_id)
#                                 st = upsert_stock_increment(produit_id, bid, delta)
#                                 stocks_result.append({
#                                     "action": "increment",
#                                     "achat_produit_id": ap.id,
#                                     "produit_id": produit_id,
#                                     "bijouterie_id": bid,
#                                     "reserved": False,
#                                     "delta": delta,
#                                     "stock_qte_apres": st.quantite,
#                                 })

#                 else:
#                     # Nouvelle ligne
#                     ap = AchatProduit.objects.create(
#                         achat=achat,
#                         produit=produit,
#                         quantite=quantite_new,
#                         prix_achat_gramme=prix_achat_gramme,
#                         tax=tax,
#                         fournisseur=achat.fournisseur,
#                     )

#                     affectations = item.get("affectations")
#                     if affectations:
#                         somme_aff = sum(int(a.get("quantite", 0)) for a in affectations)
#                         if somme_aff > quantite_new:
#                             return Response(
#                                 {"detail": "La somme des affectations dépasse la quantité de la ligne."},
#                                 status=400,
#                             )
#                         for aff in affectations:
#                             bid = int(aff["bijouterie_id"])
#                             q = int(aff["quantite"])
#                             if q <= 0:
#                                 continue
#                             st = upsert_stock_increment(produit_id, bid, q)
#                             stocks_result.append({
#                                 "action": "increment",
#                                 "achat_produit_id": ap.id,
#                                 "produit_id": produit_id,
#                                 "bijouterie_id": bid,
#                                 "reserved": False,
#                                 "delta": q,
#                                 "stock_qte_apres": st.quantite,
#                             })
#                         reste = quantite_new - somme_aff
#                         if reste > 0:
#                             st = upsert_stock_increment(produit_id, None, reste)
#                             stocks_result.append({
#                                 "action": "increment",
#                                 "achat_produit_id": ap.id,
#                                 "produit_id": produit_id,
#                                 "bijouterie_id": None,
#                                 "reserved": True,
#                                 "delta": reste,
#                                 "stock_qte_apres": st.quantite,
#                             })
#                     else:
#                         line_bijouterie_id = item.get("bijouterie_id", default_bijouterie_id)
#                         if line_bijouterie_id in (None, "", 0):
#                             st = upsert_stock_increment(produit_id, None, quantite_new)
#                             stocks_result.append({
#                                 "action": "increment",
#                                 "achat_produit_id": ap.id,
#                                 "produit_id": produit_id,
#                                 "bijouterie_id": None,
#                                 "reserved": True,
#                                 "delta": quantite_new,
#                                 "stock_qte_apres": st.quantite,
#                             })
#                         else:
#                             bid = int(line_bijouterie_id)
#                             st = upsert_stock_increment(produit_id, bid, quantite_new)
#                             stocks_result.append({
#                                 "action": "increment",
#                                 "achat_produit_id": ap.id,
#                                 "produit_id": produit_id,
#                                 "bijouterie_id": bid,
#                                 "reserved": False,
#                                 "delta": quantite_new,
#                                 "stock_qte_apres": st.quantite,
#                             })

#             # Recalcule HT/TTC final
#             achat.update_total(save=True)

#             return Response({
#                 "message": "Achat mis à jour",
#                 "achat": AchatSerializer(achat).data,
#                 "stocks": stocks_result,
#             }, status=200)

#         except KeyError:
#             return Response({"detail": "Structure de ligne invalide."}, status=400)
#         except Produit.DoesNotExist:
#             return Response({"detail": "Produit introuvable."}, status=400)
#         except Bijouterie.DoesNotExist:
#             return Response({"detail": "Bijouterie introuvable."}, status=400)
#         except Exception as e:
#             return Response({"detail": str(e)}, status=500)
        


# # --------- Helpers ---------

# def _role_ok(user) -> bool:
#     return bool(getattr(user, "user_role", None) and user.user_role.role in ["admin", "manager"])

# def _decrement_bucket(produit_id: int, bijouterie_id: int | None, qty: int):
#     """
#     Retire 'qty' unités d'un 'bucket' de stock :
#     - bijouterie_id=None  -> stock réservé (reservation_key=RES-<produit_id>)
#     - bijouterie_id=int   -> stock attribué à cette bijouterie
#     Lève ValueError si stock insuffisant.
#     """
#     if qty <= 0:
#         return

#     if bijouterie_id is None:
#         reservation_key = f"RES-{produit_id}"
#         stock = (Stock.objects
#                  .select_for_update()
#                  .filter(produit_id=produit_id, bijouterie__isnull=True, reservation_key=reservation_key)
#                  .first())
#     else:
#         stock = (Stock.objects
#                  .select_for_update()
#                  .filter(produit_id=produit_id, bijouterie_id=bijouterie_id)
#                  .first())

#     if not stock or stock.quantite < qty:
#         cible = "réservé" if bijouterie_id is None else f"bijouterie={bijouterie_id}"
#         raise ValueError(f"Stock insuffisant pour produit={produit_id} ({cible}). Requis={qty}, dispo={getattr(stock,'quantite',0)}")

#     Stock.objects.filter(pk=stock.pk).update(quantite=F("quantite") - qty)

# def _auto_decrement_any_bucket(produit_id: int, qty: int):
#     """
#     Retire automatiquement 'qty' en priorisant :
#     1) le stock réservé
#     2) puis les stocks attribués (toutes bijouteries, ordre arbitraire)
#     Lève ValueError si insuffisant.
#     """
#     if qty <= 0:
#         return

#     # 1) réservé
#     reservation_key = f"RES-{produit_id}"
#     reserved = (Stock.objects
#                 .select_for_update()
#                 .filter(produit_id=produit_id, bijouterie__isnull=True, reservation_key=reservation_key)
#                 .first())
#     if reserved:
#         take = min(reserved.quantite, qty)
#         if take > 0:
#             Stock.objects.filter(pk=reserved.pk).update(quantite=F("quantite") - take)
#             qty -= take

#     if qty <= 0:
#         return

#     # 2) attribué (toutes bijouteries ayant du stock)
#     buckets = (Stock.objects
#                .select_for_update()
#                .filter(produit_id=produit_id, bijouterie__isnull=False, quantite__gt=0)
#                .order_by("bijouterie_id"))
#     for b in buckets:
#         if qty <= 0:
#             break
#         take = min(b.quantite, qty)
#         if take > 0:
#             Stock.objects.filter(pk=b.pk).update(quantite=F("quantite") - take)
#             qty -= take

#     if qty > 0:
#         raise ValueError(f"Stock global insuffisant pour produit={produit_id}. Reste à retirer={qty}")

# # --------- Vue ---------

# class AchatCancelView(APIView):
#     """
#     Annule un achat et retire les quantités du stock.

#     - Si `reverse_allocations` est fourni, on suit précisément d'où retirer :
#       [
#         {"produit_id": 1, "allocations": [
#             {"bijouterie_id": null, "quantite": 3},        # réservé
#             {"bijouterie_id": 2, "quantite": 2}            # bijouterie 2
#         ]},
#         {"produit_id": 5, "allocations": [
#             {"bijouterie_id": 4, "quantite": 1}
#         ]}
#       ]

#     - Sinon (pas de reverse_allocations) : on retire automatiquement
#       d'abord du stock réservé, puis des bijouteries si nécessaire.
#     """
#     permission_classes = [IsAuthenticated]

#     @transaction.atomic
#     def post(self, request, achat_id: int):
#         user = request.user
#         if not _role_ok(user):
#             return Response({"detail": "Access Denied"}, status=403)

#         achat = get_object_or_404(Achat.objects.select_for_update(), pk=achat_id)

#         # Idempotence simple : si déjà annulé, on répond OK
#         if getattr(achat, "status", None) == "cancelled":
#             return Response({"message": "Achat déjà annulé", "achat_id": achat.id}, status=200)

#         # Total des quantités par produit dans cet achat
#         lignes = (AchatProduit.objects
#                   .filter(achat=achat)
#                   .values("produit_id")
#                   .annotate(total=Sum("quantite")))
#         if not lignes:
#             return Response({"detail": "Aucun produit dans cet achat."}, status=400)

#         qty_by_prod = {row["produit_id"]: int(row["total"] or 0) for row in lignes}

#         # Payload optionnel : reverse_allocations
#         payload = request.data or {}
#         reason = payload.get("reason", "")
#         reverse_allocations = payload.get("reverse_allocations")

#         try:
#             if reverse_allocations:
#                 # Contrôlé : on respecte les allocations fournies
#                 for item in reverse_allocations:
#                     produit_id = int(item["produit_id"])
#                     allocs = item.get("allocations") or []
#                     if produit_id not in qty_by_prod:
#                         return Response({"detail": f"produit_id={produit_id} n'appartient pas à cet achat."}, status=400)

#                     sum_alloc = sum(int(a.get("quantite", 0)) for a in allocs)
#                     if sum_alloc != qty_by_prod[produit_id]:
#                         return Response(
#                             {"detail": f"Les allocations pour produit_id={produit_id} doivent totaliser {qty_by_prod[produit_id]}."},
#                             status=400
#                         )

#                     for a in allocs:
#                         bid = a.get("bijouterie_id", None)
#                         q = int(a.get("quantite", 0))
#                         if q <= 0:
#                             continue
#                         # None/""/0 => réservé
#                         bij_id = None if (bid in (None, "", 0)) else int(bid)
#                         _decrement_bucket(produit_id, bij_id, q)

#             else:
#                 # Automatique : on retire la quantité totale de chaque produit
#                 for produit_id, total_qty in qty_by_prod.items():
#                     _auto_decrement_any_bucket(produit_id, total_qty)

#             # Marquage de l'achat comme annulé (si champs présents)
#             updated_fields = []
#             if hasattr(achat, "status"):
#                 achat.status = "cancelled"
#                 updated_fields.append("status")
#             if hasattr(achat, "cancelled_at"):
#                 achat.cancelled_at = timezone.now()
#                 updated_fields.append("cancelled_at")
#             if hasattr(achat, "cancelled_by"):
#                 achat.cancelled_by = user
#                 updated_fields.append("cancelled_by")
#             if hasattr(achat, "cancel_reason"):
#                 achat.cancel_reason = reason
#                 updated_fields.append("cancel_reason")

#             if updated_fields:
#                 achat.save(update_fields=updated_fields)

#             return Response({
#                 "message": "Achat annulé avec succès",
#                 "achat_id": achat.id,
#                 "mode": "controlled" if reverse_allocations else "auto",
#             }, status=200)

#         except ValueError as e:
#             # Manque de stock quelque part -> 409
#             return Response({"detail": str(e)}, status=409)
#         except Exception as e:
#             return Response({"detail": str(e)}, status=500)


# # ---- helpers ----

# def _role_ok(user) -> bool:
#     return bool(getattr(user, "user_role", None) and user.user_role.role in ["admin", "manager"])

# def _res_key(produit_id: int) -> str:
#     return f"RES-{produit_id}"

# def _get_reserved_locked(produit_id: int) -> Stock | None:
#     try:
#         return (Stock.objects
#                 .select_for_update()
#                 .get(produit_id=produit_id, bijouterie=None, reservation_key=_res_key(produit_id)))
#     except Stock.DoesNotExist:
#         return None

# def _get_alloc_locked(produit_id: int, bijouterie_id: int) -> Stock | None:
#     try:
#         return (Stock.objects
#                 .select_for_update()
#                 .get(produit_id=produit_id, bijouterie_id=bijouterie_id))
#     except Stock.DoesNotExist:
#         return None

# def _safe_decrement(stock: Stock, qty: int):
#     """Décrémente de façon atomique avec garde-fou."""
#     if qty <= 0:
#         return
#     # vérif dispo
#     stock.refresh_from_db(fields=["quantite"])
#     if stock.quantite < qty:
#         raise ValueError(f"Stock insuffisant (disponible={stock.quantite}, demandé={qty}).")
#     # décrément atomique
#     updated = (Stock.objects
#                .filter(pk=stock.pk, quantite__gte=qty)
#                .update(quantite=F("quantite") - qty))
#     if updated == 0:
#         # autre concurrent / plus assez de stock
#         raise ValueError("Conflit de mise à jour du stock (réessayez).")

# def _decrement_bucket(produit_id: int, bijouterie_id: int | None, qty: int):
#     if qty <= 0:
#         return
#     if bijouterie_id is None:
#         stock = _get_reserved_locked(produit_id)
#         if not stock:
#             raise ValueError("Aucun stock réservé pour ce produit.")
#         _safe_decrement(stock, qty)
#     else:
#         stock = _get_alloc_locked(produit_id, bijouterie_id)
#         if not stock:
#             raise ValueError(f"Aucun stock attribué pour cette bijouterie (id={bijouterie_id}).")
#         _safe_decrement(stock, qty)

# def _auto_decrement_any_bucket(produit_id: int, qty: int):
#     """Retire d'abord du réservé, puis des bijouteries jusqu'à couvrir qty."""
#     if qty <= 0:
#         return
#     # 1) réservé
#     rest = qty
#     reserved = _get_reserved_locked(produit_id)
#     if reserved and reserved.quantite > 0:
#         take = min(reserved.quantite, rest)
#         _safe_decrement(reserved, take)
#         rest -= take

#     if rest <= 0:
#         return

#     # 2) boucles sur les stocks attribués (ordre simple par id)
#     allocs = (Stock.objects
#               .select_for_update()
#               .filter(produit_id=produit_id, bijouterie__isnull=False)
#               .order_by("id"))
#     for st in allocs:
#         if rest <= 0:
#             break
#         st.refresh_from_db(fields=["quantite"])
#         if st.quantite <= 0:
#             continue
#         take = min(st.quantite, rest)
#         _safe_decrement(st, take)
#         rest -= take

#     if rest > 0:
#         raise ValueError(f"Stock total insuffisant pour le produit {produit_id} (reste {rest}).")

# # ---- Vue ----

# class AchatCancelView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         tags=["Achats"],
#         operation_summary="Annuler un achat et retirer les quantités du stock",
#         operation_description=(
#             "Annule l'achat et décrémente les stocks.\n"
#             "• **Contrôlé**: fournir `reverse_allocations` pour dire d'où retirer (réservé / bijouterie).\n"
#             "• **Auto**: sans `reverse_allocations`, retire d'abord du **réservé**, puis des **bijouteries**.\n"
#             "Idempotent si `Achat.status == 'cancelled'`."
#         ),
#         manual_parameters=[
#             openapi.Parameter("achat_id", openapi.IN_PATH, "ID de l'achat", type=openapi.TYPE_INTEGER, required=True),
#         ],
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             properties={
#                 "reason": openapi.Schema(type=openapi.TYPE_STRING, description="Raison (optionnelle)."),
#                 "reverse_allocations": openapi.Schema(
#                     type=openapi.TYPE_ARRAY,
#                     description="Répartition précise des retraits par produit/bijouterie (bijouterie_id null => réservé).",
#                     items=openapi.Schema(
#                         type=openapi.TYPE_OBJECT,
#                         required=["produit_id", "allocations"],
#                         properties={
#                             "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#                             "allocations": openapi.Schema(
#                                 type=openapi.TYPE_ARRAY,
#                                 items=openapi.Schema(
#                                     type=openapi.TYPE_OBJECT,
#                                     required=["quantite"],
#                                     properties={
#                                         "bijouterie_id": openapi.Schema(type=openapi.TYPE_INTEGER, nullable=True),
#                                         "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, minimum=1),
#                                     },
#                                 ),
#                             ),
#                         },
#                     ),
#                 ),
#             },
#         ),
#         responses={
#             200: openapi.Response("Achat annulé"),
#             403: openapi.Response("Accès refusé"),
#             404: openapi.Response("Achat introuvable"),
#             409: openapi.Response("Stock insuffisant / conflit"),
#             500: openapi.Response("Erreur serveur"),
#         },
#     )
#     @transaction.atomic
#     def post(self, request, achat_id: int):
#         user = request.user
#         if not _role_ok(user):
#             return Response({"detail": "Access Denied"}, status=403)

#         achat = get_object_or_404(Achat.objects.select_for_update(), pk=achat_id)

#         # Idempotence simple
#         if getattr(achat, "status", None) == "cancelled":
#             return Response({"message": "Achat déjà annulé", "achat_id": achat.id}, status=200)

#         # Quantités par produit dans cet achat
#         lignes = (AchatProduit.objects
#                   .filter(achat=achat)
#                   .values("produit_id")
#                   .annotate(total=Sum("quantite")))
#         if not lignes:
#             return Response({"detail": "Aucun produit dans cet achat."}, status=400)

#         qty_by_prod = {row["produit_id"]: int(row["total"] or 0) for row in lignes}

#         payload = request.data or {}
#         reason = payload.get("reason", "")
#         reverse_allocations = payload.get("reverse_allocations")

#         try:
#             if reverse_allocations:
#                 # retrait contrôlé
#                 for item in reverse_allocations:
#                     produit_id = int(item["produit_id"])
#                     allocs = item.get("allocations") or []
#                     if produit_id not in qty_by_prod:
#                         return Response({"detail": f"produit_id={produit_id} n'appartient pas à cet achat."}, status=400)

#                     sum_alloc = sum(int(a.get("quantite", 0)) for a in allocs)
#                     if sum_alloc != qty_by_prod[produit_id]:
#                         return Response(
#                             {"detail": f"Les allocations pour produit_id={produit_id} doivent totaliser {qty_by_prod[produit_id]}."},
#                             status=400
#                         )

#                     for a in allocs:
#                         bid = a.get("bijouterie_id", None)
#                         q = int(a.get("quantite", 0))
#                         if q <= 0:
#                             continue
#                         bij_id = None if (bid in (None, "", 0)) else int(bid)
#                         _decrement_bucket(produit_id, bij_id, q)
#             else:
#                 # retrait automatique
#                 for produit_id, total_qty in qty_by_prod.items():
#                     _auto_decrement_any_bucket(produit_id, total_qty)

#             # Marque l'achat annulé si les champs existent
#             updated = []
#             if hasattr(achat, "status"):
#                 achat.status = "cancelled"; updated.append("status")
#             if hasattr(achat, "cancelled_at"):
#                 achat.cancelled_at = timezone.now(); updated.append("cancelled_at")
#             if hasattr(achat, "cancelled_by"):
#                 achat.cancelled_by = user; updated.append("cancelled_by")
#             if hasattr(achat, "cancel_reason"):
#                 achat.cancel_reason = reason; updated.append("cancel_reason")
#             if updated:
#                 achat.save(update_fields=updated)

#             return Response({"message": "Achat annulé avec succès", "achat_id": achat.id,
#                             "mode": "controlled" if reverse_allocations else "auto"}, status=200)

#         except ValueError as e:
#             return Response({"detail": str(e)}, status=409)
#         except Exception as e:
#             return Response({"detail": str(e)}, status=500)

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
