# from __future__ import annotations

# import csv
# import logging
# from datetime import date, datetime
# from decimal import Decimal, InvalidOperation
# from io import BytesIO, StringIO
# # ---------- (facultatif) mixin réutilisé pour Excel ----------
# from textwrap import dedent
# from typing import Dict, Optional, Tuple

# from dateutil.relativedelta import relativedelta
# from django.core.exceptions import ValidationError
# from django.db import IntegrityError, transaction
# from django.db.models import (Case, Count, DecimalField, ExpressionWrapper, F,
#                               IntegerField, Prefetch, Q, Sum, Value, When)
# from django.db.models.functions import Cast, Coalesce
# from django.http import HttpResponse, StreamingHttpResponse
# from django.shortcuts import get_object_or_404
# from django.template.loader import get_template
# from django.utils import timezone
# from django.utils.dateparse import parse_date
# from django_filters.rest_framework import DjangoFilterBackend
# from drf_yasg import openapi
# from drf_yasg.utils import swagger_auto_schema
# from openpyxl import Workbook
# from openpyxl.utils import get_column_letter
# from rest_framework import status
# from rest_framework.filters import OrderingFilter, SearchFilter
# from rest_framework.generics import ListAPIView, RetrieveAPIView
# from rest_framework.pagination import PageNumberPagination
# from rest_framework.permissions import IsAuthenticated
# from rest_framework.response import Response
# from rest_framework.views import APIView
# from xhtml2pdf import pisa

# from backend.permissions import IsAdminManagerVendor, IsAdminOrManager
# from backend.renderers import UserRenderer
# # --- Inventaire
# from inventory.models import Bucket, InventoryMovement, MovementType
# from inventory.services import log_move
# from purchase.services import _get_or_upsert_fournisseur, _recalc_totaux_achat
# from stock.models import Stock
# from store.models import Produit

# # from .your_mixin_and_pagination_module import ExportXlsxMixin, AchatPagination
# from .models import Achat, Fournisseur, Lot, ProduitLine
# from .serializers import (AchatCancelSerializer, AchatCreateResponseSerializer,
#                           AchatDashboardResponseSerializer,
#                           AchatListSerializer, AchatSerializer,
#                           ArrivageAdjustmentsInSerializer,
#                           ArrivageCreateInSerializer,
#                           ArrivageMetaUpdateInSerializer,
#                           FournisseurSerializer, LotDisplaySerializer,
#                           LotListSerializer)

# logger = logging.getLogger(__name__)

# # Create your views here.

# # helpers fournis précédemment
# # from services.stocks import allocate_arrival

# allowed_roles = ['admin', 'manager', 'vendeur']

# ZERO = Decimal("0.00")
# TWOPLACES = Decimal('0.01')

# # class FournisseurGetView(APIView):
# #     renderer_classes = [UserRenderer]
# #     permission_classes = [IsAuthenticated]

# #     @swagger_auto_schema(
# #         operation_description="Récupère les informations d'un fournisseur par son ID.",
# #         responses={
# #             200: FournisseurSerializer(),
# #             403: openapi.Response(description="Accès refusé"),
# #             404: openapi.Response(description="Fournisseur introuvable"),
# #         }
# #     )
# #     def get(self, request, pk, format=None):
# #         user_role = getattr(request.user.user_role, 'role', None)
# #         if user_role not in ['admin', 'manager']:
# #             return Response({"message": "Access Denied"}, status=403)

# #         try:
# #             fournisseur = Fournisseur.objects.get(pk=pk)
# #         except Fournisseur.DoesNotExist:
# #             return Response({"detail": "Fournisseur not found"}, status=status.HTTP_404_NOT_FOUND)

# #         serializer = FournisseurSerializer(fournisseur)
# #         return Response(serializer.data, status=200)

# # PUT: mise à jour complète (tous les champs doivent être fournis)
# # PATCH: mise à jour partielle (champs optionnels)
# # Swagger : la doc est affichée proprement pour chaque méthode
# # Contrôle des rôles (admin, manager)
# class FournisseurUpdateView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Met à jour complètement un fournisseur (remplace tous les champs).",
#         request_body=FournisseurSerializer,
#         responses={
#             200: FournisseurSerializer(),
#             400: "Requête invalide",
#             403: "Accès refusé",
#             404: "Fournisseur introuvable",
#         }
#     )
#     def put(self, request, pk, format=None):
#         return self.update_fournisseur(request, pk, partial=False)

#     @swagger_auto_schema(
#         operation_description="Met à jour partiellement un fournisseur (seuls les champs fournis sont modifiés).",
#         request_body=FournisseurSerializer,
#         responses={
#             200: FournisseurSerializer(),
#             400: "Requête invalide",
#             403: "Accès refusé",
#             404: "Fournisseur introuvable",
#         }
#     )
#     def patch(self, request, pk, format=None):
#         return self.update_fournisseur(request, pk, partial=True)

#     def update_fournisseur(self, request, pk, partial):
#         user_role = getattr(request.user.user_role, 'role', None)
#         if user_role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             fournisseur = Fournisseur.objects.get(pk=pk)
#         except Fournisseur.DoesNotExist:
#             return Response({"detail": "Fournisseur not found"}, status=404)

#         serializer = FournisseurSerializer(fournisseur, data=request.data, partial=partial)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data, status=200)
#         return Response(serializer.errors, status=400)



# class FournisseurListView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Liste tous les fournisseurs, avec option de recherche par nom ou téléphone via le paramètre `search`.",
#         manual_parameters=[
#             openapi.Parameter(
#                 'search', openapi.IN_QUERY,
#                 description="Nom ou téléphone à rechercher",
#                 type=openapi.TYPE_STRING
#             )
#         ],
#         responses={200: FournisseurSerializer(many=True)}
#     )
#     def get(self, request):
#         user_role = getattr(request.user.user_role, 'role', None)
#         if user_role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)

#         search = request.query_params.get('search', '')
#         fournisseurs = Fournisseur.objects.all()
#         if search:
#             fournisseurs = fournisseurs.filter(
#                 Q(nom__icontains=search) | Q(prenom__icontains=search) | Q(telephone__icontains=search)
#             )

#         serializer = FournisseurSerializer(fournisseurs, many=True)
#         return Response(serializer.data, status=200)



# class FournisseurDeleteView(APIView):
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Supprime un fournisseur à partir de son ID.",
#         responses={
#             204: "Fournisseur supprimé avec succès",
#             403: "Accès refusé",
#             404: "Fournisseur introuvable",
#         }
#     )
#     def delete(self, request, pk, format=None):
#         role = getattr(request.user.user_role, 'role', None)
#         if role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             fournisseur = Fournisseur.objects.get(pk=pk)
#         except Fournisseur.DoesNotExist:
#             return Response({"detail": "Fournisseur not found"}, status=404)

#         fournisseur.delete()
#         return Response({"message": "Fournisseur supprimé avec succès."}, status=204)



# class ExportXlsxMixin:
#     def _xlsx_response(self, wb: Workbook, filename: str) -> HttpResponse:
#         bio = BytesIO()
#         wb.save(bio)
#         bio.seek(0)
#         resp = HttpResponse(
#             bio.getvalue(),
#             content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
#         )
#         resp["Content-Disposition"] = f'attachment; filename="{filename}"'
#         return resp

#     @staticmethod
#     def _autosize(ws):
#         for col in ws.columns:
#             width = max((len(str(c.value)) if c.value is not None else 0) for c in col) + 2
#             ws.column_dimensions[get_column_letter(col[0].column)].width = min(width, 50)




# # -----------------------------Liste des achats---------------------------------
# class AchatListView(ListAPIView):
#     """
#     Liste des achats :
#     - par défaut : année courante
#     - si date_from & date_to sont fournis : intervalle [date_from, date_to] (inclus)
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]
#     serializer_class = AchatSerializer
#     # pagination_class = None  # pas de pagination

#     @swagger_auto_schema(
#         operation_summary="Lister les achats (année courante par défaut, sinon entre deux dates)",
#         operation_description=(
#             "• Si `date_from` **et** `date_to` sont fournis → filtre inclusif.\n"
#             "• Sinon → achats de l’**année courante**.\n"
#             "Formats : `YYYY-MM-DD`."
#         ),
#         manual_parameters=[
#             openapi.Parameter("date_from", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                               description="Borne min incluse (YYYY-MM-DD). Avec date_to."),
#             openapi.Parameter("date_to", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                               description="Borne max incluse (YYYY-MM-DD). Avec date_from."),
#             openapi.Parameter("ordering", openapi.IN_QUERY, type=openapi.TYPE_STRING,
#                               description="Tri: -created_at (défaut), created_at, numero_achat, -numero_achat"),
#         ],
#         responses={200: AchatSerializer(many=True)},
#         tags=["Achats"],
#     )
#     def get(self, request, *args, **kwargs):
#         def _check_date(label, val):
#             if not val:
#                 return
#             try:
#                 datetime.strptime(val, "%Y-%m-%d").date()
#             except Exception:
#                 raise ValidationError({label: "Format invalide. Utiliser YYYY-MM-DD."})
#         _check_date("date_from", request.query_params.get("date_from"))
#         _check_date("date_to", request.query_params.get("date_to"))
#         return super().get(request, *args, **kwargs)

#     def get_queryset(self):
#         params = self.request.query_params
#         getf = params.get

#         ordering = getf("ordering") or "-created_at"
#         allowed = {"created_at", "-created_at", "numero_achat", "-numero_achat"}
#         if ordering not in allowed:
#             ordering = "-created_at"

#         qs = (
#             Achat.objects
#             .select_related("fournisseur", "cancelled_by")
#             .only(
#                 "id", "created_at", "description",
#                 "frais_transport", "frais_douane", "note",
#                 "numero_achat", "montant_total_ht", "montant_total_ttc",
#                 "status", "cancel_reason", "cancelled_at", "cancelled_by_id",
#                 "fournisseur_id",
#             )
#         )

#         date_from_s = getf("date_from")
#         date_to_s   = getf("date_to")

#         if date_from_s and date_to_s:
#             df = datetime.strptime(date_from_s, "%Y-%m-%d").date()
#             dt = datetime.strptime(date_to_s, "%Y-%m-%d").date()
#             if df > dt:
#                 raise ValidationError({"detail": "date_from doit être ≤ date_to."})
#             qs = qs.filter(created_at__date__gte=df, created_at__date__lte=dt)
#         else:
#             # ✅ beaucoup plus robuste pour “année courante”
#             y = timezone.localdate().year
#             qs = qs.filter(created_at__year=y)

#         return qs.order_by(ordering)


# # class AchatDashboardView(APIView):
# #     permission_classes = [IsAuthenticated, IsAdminManagerVendor]

# #     @swagger_auto_schema(
# #         operation_description="Dashboard des achats filtré par période dynamique (en mois)",
# #         manual_parameters=[
# #             openapi.Parameter(
# #                 'mois',
# #                 openapi.IN_QUERY,
# #                 type=openapi.TYPE_INTEGER,
# #                 enum=[1, 3, 6, 12],
# #                 default=3,
# #                 description="Nombre de mois à remonter"
# #             )
# #         ],
# #         responses={200: openapi.Response(description="Statistiques + achats récents")}
# #     )
# #     def get(self, request):
# #         user_role = getattr(request.user.user_role, 'role', None)
# #         if user_role not in ['admin', 'manager']:
# #             return Response({"message": "Access Denied"}, status=403)

# #         # Lire le paramètre "mois" dans l'URL, défaut = 3
# #         try:
# #             nb_mois = int(request.GET.get('mois', 3))
# #             nb_mois = max(1, min(nb_mois, 12))  # sécurise entre 1 et 12
# #         except ValueError:
# #             nb_mois = 3

# #         depuis = timezone.now() - relativedelta(months=nb_mois)

# #         achats = Achat.objects.filter(created_at__gte=depuis)

# #         stats = achats.aggregate(
# #             total_achats=Count('id'),
# #             montant_total_ht=Sum('montant_total_ht'),
# #             montant_total_ttc=Sum('montant_total_ttc')
# #         )

# #         achats_recents = achats.order_by('-created_at')[:10]
# #         achats_serializer = AchatSerializer(achats_recents, many=True)

# #         return Response({
# #             "periode": {
# #                 "mois": nb_mois,
# #                 "depuis": depuis.date().isoformat(),
# #                 "jusqu_a": timezone.now().date().isoformat()
# #             },
# #             "statistiques": stats,
# #             "achats_recents": achats_serializer.data
# #         })


# class AchatDashboardView(APIView):
#     permission_classes = [IsAuthenticated, IsAdminOrManager]

#     @swagger_auto_schema(
#         operation_summary="Dashboard des achats (période dynamique en mois)",
#         operation_description=(
#             "Retourne des statistiques globales (nombre d'achats, montants HT/TTC) et "
#             "les 10 achats les plus récents sur la période.\n\n"
#             "- Paramètre `mois` dans la query : 1, 3, 6 ou 12 (par défaut 3).\n"
#             "- Accès réservé aux rôles `admin` et `manager`."
#         ),
#         manual_parameters=[
#             openapi.Parameter(
#                 'mois',
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_INTEGER,
#                 enum=[1, 3, 6, 12],
#                 default=3,
#                 description="Nombre de mois à remonter (1, 3, 6, 12)."
#             )
#         ],
#         responses={200: AchatDashboardResponseSerializer},
#         tags=["Achats / Dashboard"],
#     )
#     def get(self, request):
#         user_role = getattr(request.user.user_role, 'role', None)
#         if user_role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)

#         # Paramètre mois sécurisé entre 1 et 12
#         try:
#             nb_mois = int(request.GET.get('mois', 3))
#             nb_mois = max(1, min(nb_mois, 12))
#         except (TypeError, ValueError):
#             nb_mois = 3

#         depuis = timezone.now() - relativedelta(months=nb_mois)

#         achats = Achat.objects.filter(created_at__gte=depuis)

#         stats = achats.aggregate(
#             total_achats=Count('id'),
#             montant_total_ht=Sum('montant_total_ht'),
#             montant_total_ttc=Sum('montant_total_ttc'),
#         )

#         achats_recents = achats.order_by('-created_at')[:10]
#         achats_serializer = AchatSerializer(achats_recents, many=True)

#         data = {
#             "periode": {
#                 "mois": nb_mois,
#                 "depuis": depuis.date(),
#                 "jusqu_a": timezone.localdate(),
#             },
#             "statistiques": {
#                 "total_achats": stats["total_achats"] or 0,
#                 "montant_total_ht": stats["montant_total_ht"] or Decimal("0.00"),
#                 "montant_total_ttc": stats["montant_total_ttc"] or Decimal("0.00"),
#             },
#             "achats_recents": achats_serializer.data,
#         }
#         return Response(data)

# # -----------------------------End list------------------------------------------

# # class LotListView(ListAPIView):
# #     """
# #     Liste des lots :
# #     - par défaut : année courante (received_at)
# #     - si date_from & date_to sont fournis : intervalle [date_from, date_to] (inclus)
# #     """
# #     permission_classes = [IsAuthenticated, IsAdminOrManager]
# #     serializer_class = LotListSerializer
# #     pagination_class = None  # pas de pagination

# #     @swagger_auto_schema(
# #         operation_summary="Lister les lots (année courante par défaut, sinon entre deux dates)",
# #         operation_description=(
# #             "• Si `date_from` **et** `date_to` sont fournis → filtre **inclusif**.\n"
# #             "• Sinon → lots de l’**année courante** (champ `received_at`).\n"
# #             "Formats attendus : `YYYY-MM-DD`."
# #         ),
# #         manual_parameters=[
# #             openapi.Parameter("date_from", openapi.IN_QUERY, type=openapi.TYPE_STRING,
# #                               description="Borne min incluse (YYYY-MM-DD). À utiliser avec date_to."),
# #             openapi.Parameter("date_to", openapi.IN_QUERY, type=openapi.TYPE_STRING,
# #                               description="Borne max incluse (YYYY-MM-DD). À utiliser avec date_from."),
# #             openapi.Parameter("ordering", openapi.IN_QUERY, type=openapi.TYPE_STRING,
# #                               description=("Tri: -received_at (défaut), received_at, "
# #                                            "numero_lot, -numero_lot, "
# #                                            "nb_lignes, -nb_lignes, "
# #                                            "quantite, -quantite, "
# #                                            "poids_total, -poids_total")),
# #         ],
# #         responses={200: LotListSerializer(many=True)},
# #         tags=["Achats / Arrivages"],
# #     )
# #     def get(self, request, *args, **kwargs):
# #         # Validation légère des dates (retourne 400 propre si invalide)
# #         def _check_date(label, val):
# #             if not val:
# #                 return
# #             try:
# #                 datetime.strptime(val, "%Y-%m-%d").date()
# #             except Exception:
# #                 raise ValidationError({label: "Format invalide. Utiliser YYYY-MM-DD."})

# #         _check_date("date_from", request.query_params.get("date_from"))
# #         _check_date("date_to", request.query_params.get("date_to"))
# #         return super().get(request, *args, **kwargs)

# #     def get_queryset(self):
# #         params = self.request.query_params
# #         getf = params.get

# #         # Tri autorisé
# #         ordering = getf("ordering") or "-received_at"
# #         allowed = {
# #             "received_at", "-received_at",
# #             "numero_lot", "-numero_lot",
# #             "nb_lignes", "-nb_lignes",
# #             "quantite", "-quantite",
# #             "poids_total", "-poids_total",
# #         }
# #         if ordering not in allowed:
# #             ordering = "-received_at"

# #         # Base queryset (+ préchargements)
# #         qs = (
# #             Lot.objects
# #             .select_related("achat", "achat__fournisseur")
# #             .prefetch_related(
# #                 Prefetch("lignes", queryset=ProduitLine.objects.select_related("produit"))
# #             )
# #         )

# #         # Filtres dates (année courante OU intervalle inclusif)
# #         date_from_s = getf("date_from")
# #         date_to_s   = getf("date_to")
# #         if date_from_s and date_to_s:
# #             df = datetime.strptime(date_from_s, "%Y-%m-%d").date()
# #             dt = datetime.strptime(date_to_s, "%Y-%m-%d").date()
# #             if df > dt:
# #                 raise ValidationError({"detail": "date_from doit être ≤ date_to."})
# #             qs = qs.filter(received_at__date__gte=df, received_at__date__lte=dt)
# #         else:
# #             y = timezone.localdate().year
# #             qs = qs.filter(received_at__year=y)

# #         # Agrégats
# #         I0 = Value(0)
# #         D0 = Value(Decimal("0.000"), output_field=DecimalField(max_digits=18, decimal_places=3))
# #         poids_produit = Cast(
# #             F("lignes__produit__poids"),
# #             output_field=DecimalField(max_digits=18, decimal_places=3),
# #         )
# #         poids_par_ligne = ExpressionWrapper(
# #             Coalesce(F("lignes__quantite"), I0) * Coalesce(poids_produit, D0),
# #             output_field=DecimalField(max_digits=18, decimal_places=3),
# #         )

# #         qs = qs.annotate(
# #             nb_lignes=Count("lignes", distinct=True),
# #             quantite=Coalesce(Sum("lignes__quantite", output_field=IntegerField()), I0),
# #             poids_total=Coalesce(Sum(poids_par_ligne), D0),
# #         )

# #         return qs.order_by(ordering)


# class LotListView(ListAPIView):
#     """
#     Liste des lots :
#     - par défaut : année courante (received_at)
#     - si date_from & date_to sont fournis : intervalle [date_from, date_to] (inclus)
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]
#     serializer_class = LotListSerializer
#     pagination_class = None  # pas de pagination

#     @swagger_auto_schema(
#         operation_summary="Lister les lots (année courante par défaut, sinon entre deux dates)",
#         operation_description=(
#             "• Si `date_from` **et** `date_to` sont fournis → filtre **inclusif**.\n"
#             "• Sinon → lots de l’**année courante** (champ `received_at`).\n"
#             "Formats attendus : `YYYY-MM-DD`."
#         ),
#         manual_parameters=[
#             openapi.Parameter(
#                 "date_from",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Borne min incluse (YYYY-MM-DD). À utiliser avec date_to.",
#             ),
#             openapi.Parameter(
#                 "date_to",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Borne max incluse (YYYY-MM-DD). À utiliser avec date_from.",
#             ),
#             openapi.Parameter(
#                 "ordering",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description=(
#                     "Tri: -received_at (défaut), received_at, "
#                     "numero_lot, -numero_lot, "
#                     "nb_lignes, -nb_lignes, "
#                     "quantite, -quantite, "
#                     "poids_total, -poids_total"
#                 ),
#             ),
#         ],
#         responses={200: LotListSerializer(many=True)},
#         tags=["Achats / Arrivages"],
#     )
#     def get(self, request, *args, **kwargs):
#         # Validation légère des dates (retourne 400 propre si invalide)
#         def _check_date(label, val):
#             if not val:
#                 return
#             try:
#                 datetime.strptime(val, "%Y-%m-%d").date()
#             except Exception:
#                 raise ValidationError({label: "Format invalide. Utiliser YYYY-MM-DD."})

#         _check_date("date_from", request.query_params.get("date_from"))
#         _check_date("date_to", request.query_params.get("date_to"))
#         return super().get(request, *args, **kwargs)

#     def get_queryset(self):
#         params = self.request.query_params
#         getf = params.get

#         # Tri autorisé
#         ordering = getf("ordering") or "-received_at"
#         allowed = {
#             "received_at", "-received_at",
#             "numero_lot", "-numero_lot",
#             "nb_lignes", "-nb_lignes",
#             "quantite", "-quantite",
#             "poids_total", "-poids_total",
#         }
#         if ordering not in allowed:
#             ordering = "-received_at"

#         # Base queryset (+ préchargements)
#         qs = (
#             Lot.objects
#             .select_related("achat", "achat__fournisseur")
#             .prefetch_related(
#                 Prefetch(
#                     "lignes",
#                     queryset=ProduitLine.objects.select_related("produit")
#                 )
#             )
#         )

#         # Filtres dates (année courante OU intervalle inclusif)
#         date_from_s = getf("date_from")
#         date_to_s   = getf("date_to")
#         if date_from_s and date_to_s:
#             df = datetime.strptime(date_from_s, "%Y-%m-%d").date()
#             dt = datetime.strptime(date_to_s, "%Y-%m-%d").date()
#             if df > dt:
#                 raise ValidationError({"detail": "date_from doit être ≤ date_to."})
#             qs = qs.filter(received_at__date__gte=df, received_at__date__lte=dt)
#         else:
#             y = timezone.localdate().year
#             qs = qs.filter(received_at__year=y)

#         # Agrégats
#         I0 = Value(0, output_field=IntegerField())
#         D0 = Value(Decimal("0.000"), output_field=DecimalField(max_digits=18, decimal_places=3))

#         poids_produit = Cast(
#             F("lignes__produit__poids"),
#             output_field=DecimalField(max_digits=18, decimal_places=3),
#         )
#         poids_par_ligne = ExpressionWrapper(
#             Coalesce(F("lignes__quantite"), I0) * Coalesce(poids_produit, D0),
#             output_field=DecimalField(max_digits=18, decimal_places=3),
#         )

#         qs = qs.annotate(
#             nb_lignes=Count("lignes", distinct=True),
#             quantite=Coalesce(
#                 Sum("lignes__quantite", output_field=IntegerField()),
#                 I0,
#             ),
#             poids_total=Coalesce(Sum(poids_par_ligne), D0),
#         )

#         return qs.order_by(ordering)
    
    
# # ------------------------------------Lots display-------------------------------
# # class LotDetailView(RetrieveAPIView):
# #     queryset = Lot.objects.select_related("achat", "achat__fournisseur").prefetch_related("lignes__produit")
# #     serializer_class = LotDisplaySerializer
# #     permission_classes = [IsAuthenticated, IsAdminOrManager]
# #     lookup_field = "pk"

# #     @swagger_auto_schema(
# #         operation_id="getLotDisplay",
# #         operation_summary="Détail d’un lot (format affichage personnalisé)",
# #         tags=["Achats / Arrivages"],
# #     )
# #     def get(self, request, *args, **kwargs):
# #         return super().get(request, *args, **kwargs)


# class LotDetailView(RetrieveAPIView):
#     """
#     Détail d’un lot dans un format “affichage” :
#     - fournisseur
#     - frais
#     - numéro de lot
#     - lignes produits (produit_id, quantite, prix_achat_gramme)
#     """
#     queryset = (
#         Lot.objects
#         .select_related("achat", "achat__fournisseur")
#         .prefetch_related("lignes__produit")
#     )
#     serializer_class = LotDisplaySerializer
#     permission_classes = [IsAuthenticated, IsAdminOrManager]
#     lookup_field = "pk"  # facultatif, c’est le défaut

#     @swagger_auto_schema(
#         operation_id="getLotDisplay",
#         operation_summary="Détail d’un lot (format affichage personnalisé)",
#         tags=["Achats / Arrivages"],
#     )
#     def get(self, request, *args, **kwargs):
#         return super().get(request, *args, **kwargs)


# # -------------------------------End lot display---------------------------------

# # def generate_numero_lot() -> str:
# #     """Génère LOT-YYYYMMDD-XXXX ; XXXX repart à 0001 chaque jour."""
# #     today = timezone.localdate().strftime("%Y%m%d")
# #     prefix = f"LOT-{today}-"
# #     last = (Lot.objects
# #             .filter(numero_lot__startswith=prefix)
# #             .order_by("-numero_lot")
# #             .values_list("numero_lot", flat=True)
# #             .first())
# #     if last:
# #         try:
# #             seq = int(last.rsplit("-", 1)[-1]) + 1
# #         except ValueError:
# #             seq = 1
# #     else:
# #         seq = 1
# #     return f"{prefix}{seq:04d}"


# # class ArrivageCreateView(APIView):
# #     permission_classes = [IsAuthenticated, IsAdminOrManager]
# #     http_method_names = ["post"]

# #     @swagger_auto_schema(
# #         operation_id="createArrivage",
# #         operation_summary="Créer un arrivage (lot auto-numéroté) et initialiser l'inventaire",
# #         operation_description=(
# #             "Crée un Achat, un Lot avec un numéro auto (LOT-YYYYMMDD-XXXX), les lignes produits (quantités), "
# #             "pousse 100% du stock en Réserve, et valorise l'achat au gramme si fourni."
# #         ),
# #         request_body=ArrivageCreateInSerializer,
# #         responses={201: AchatCreateResponseSerializer, 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden"},
# #         tags=["Achats / Arrivages"],
# #     )
# #     @transaction.atomic
# #     def post(self, request):
# #         s = ArrivageCreateInSerializer(data=request.data)
# #         s.is_valid(raise_exception=True)
# #         v = s.validated_data

# #         # Validations métier (produits, poids)
# #         lots_in = v["lots"]
# #         pids = {row["produit_id"] for row in lots_in}
# #         exists = set(Produit.objects.filter(id__in=pids).values_list("id", flat=True))
# #         missing = pids - exists
# #         if missing:
# #             return Response({"lots": f"Produit(s) introuvable(s): {sorted(list(missing))}."}, status=400)

# #         missing_weight = list(Produit.objects.filter(id__in=pids, poids__isnull=True).values_list("id", flat=True))
# #         if missing_weight:
# #             return Response({"lots": f"Produit(s) sans poids: {missing_weight}."}, status=400)

# #         # Fournisseur
# #         f = v["fournisseur"]
# #         fournisseur, _ = Fournisseur.objects.get_or_create(
# #             telephone=(f.get("telephone") or "").strip() or None,
# #             defaults={"nom": f["nom"], "prenom": f.get("prenom", "")},
# #         )

# #         # Achat
# #         numero_achat = f"ACH-{timezone.localdate().strftime('%Y%m%d')}-{timezone.now().strftime('%H%M%S')}"
# #         achat = Achat.objects.create(
# #             fournisseur=fournisseur,
# #             description=v.get("description", ""),
# #             frais_transport=v.get("frais_transport", Decimal("0")),
# #             frais_douane=v.get("frais_douane", Decimal("0")),
# #             numero_achat=numero_achat,
# #             status="confirmed",
# #         )

# #         # Lot (header) — génération auto + retry en cas de collision concurrente
# #         for _ in range(5):
# #             numero_lot = generate_numero_lot()
# #             try:
# #                 lot = Lot.objects.create(
# #                     achat=achat,
# #                     numero_lot=numero_lot,
# #                     description=v.get("description", ""),
# #                     received_at=timezone.now(),
# #                 )
# #                 break
# #             except IntegrityError:
# #                 # une autre requête a pris le même numéro juste avant ; on retente
# #                 continue
# #         else:
# #             return Response({"detail": "Impossible de générer un numéro de lot unique."}, status=400)

# #         # Lignes + stock Réserve + valorisation
# #         total_ht = Decimal("0.00")
# #         produits_by_id = {p.id: p for p in Produit.objects.filter(id__in=pids).only("id", "poids", "nom")}

# #         for row in lots_in:
# #             produit = produits_by_id[row["produit_id"]]
# #             qte = int(row["quantite"])

# #             pl = ProduitLine.objects.create(
# #                 lot=lot,
# #                 produit=produit,
# #                 prix_gramme_achat=row.get("prix_achat_gramme"),
# #                 quantite_total=qte,
# #                 quantite_restante=qte,
# #             )

# #             # Stock initial en Réserve
# #             Stock.objects.create(
# #                 produit_line=pl, bijouterie=None,
# #                 quantite_allouee=qte, quantite_disponible=qte,
# #             )

# #             # Valorisation HT au gramme
# #             if pl.prix_gramme_achat:
# #                 poids_total_calc = Decimal(produit.poids) * Decimal(qte)
# #                 total_ht += poids_total_calc * pl.prix_gramme_achat

# #         # Totaux Achat (ne PAS inclure 'montant_total_tax' si @property)
# #         achat.montant_total_ht = total_ht
# #         achat.montant_total_ttc = total_ht + Decimal(achat.frais_transport or 0) + Decimal(achat.frais_douane or 0)
# #         achat.save(update_fields=["montant_total_ht", "montant_total_ttc"])

# #         out = AchatCreateResponseSerializer(lot).data
# #         return Response(out, status=status.HTTP_201_CREATED)
    



# def generate_numero_lot() -> str:
#     """Génère LOT-YYYYMMDD-XXXX ; XXXX repart à 0001 chaque jour."""
#     today = timezone.localdate().strftime("%Y%m%d")
#     prefix = f"LOT-{today}-"
#     last = (
#         Lot.objects
#         .filter(numero_lot__startswith=prefix)
#         .order_by("-numero_lot")
#         .values_list("numero_lot", flat=True)
#         .first()
#     )
#     if last:
#         try:
#             seq = int(last.rsplit("-", 1)[-1]) + 1
#         except ValueError:
#             seq = 1
#     else:
#         seq = 1
#     return f"{prefix}{seq:04d}"


# class ArrivageCreateView(APIView):
#     """
#     Création d’un arrivage simple :

#     - Crée un Achat (fournisseur + frais)
#     - Crée 1 Lot rattaché à cet achat, avec numero_lot auto (LOT-YYYYMMDD-XXXX)
#     - Crée les ProduitLine (quantité achetée, prix_achat_gramme)
#     - Pousse 100% de la quantité en stock "Réserve"
#     - Recalcule les totaux de l’achat via Achat.update_total()
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]
#     http_method_names = ["post"]

#     @swagger_auto_schema(
#         operation_id="createArrivage",
#         operation_summary="Créer un arrivage (lot auto-numéroté) et initialiser l'inventaire",
#         operation_description=(
#             "Crée un Achat, un Lot avec un numéro auto (LOT-YYYYMMDD-XXXX), les lignes produits (quantités), "
#             "pousse 100% du stock en Réserve, et valorise l'achat au gramme si fourni."
#         ),
#         request_body=ArrivageCreateInSerializer,
#         responses={
#             201: AchatCreateResponseSerializer,
#             400: "Bad Request",
#             401: "Unauthorized",
#             403: "Forbidden",
#         },
#         tags=["Achats / Arrivages"],
#     )
#     @transaction.atomic
#     def post(self, request):
#         s = ArrivageCreateInSerializer(data=request.data)
#         s.is_valid(raise_exception=True)
#         v = s.validated_data

#         lots_in = v["lots"]

#         # --------- Validation produits ---------
#         pids = {row["produit_id"] for row in lots_in}
#         exists = set(
#             Produit.objects.filter(id__in=pids).values_list("id", flat=True)
#         )
#         missing = pids - exists
#         if missing:
#             return Response(
#                 {"lots": f"Produit(s) introuvable(s): {sorted(list(missing))}."},
#                 status=400,
#             )

#         missing_weight = list(
#             Produit.objects
#             .filter(id__in=pids, poids__isnull=True)
#             .values_list("id", flat=True)
#         )
#         if missing_weight:
#             return Response(
#                 {"lots": f"Produit(s) sans poids: {missing_weight}."},
#                 status=400,
#             )

#         # --------- Fournisseur ---------
#         f = v["fournisseur"]
#         fournisseur, _ = Fournisseur.objects.get_or_create(
#             telephone=(f.get("telephone") or "").strip() or None,
#             defaults={
#                 "nom": f["nom"],
#                 "prenom": f.get("prenom", ""),
#             },
#         )

#         # --------- Achat ---------
#         # numero_achat sera généré automatiquement par Achat.save()
#         achat = Achat.objects.create(
#             fournisseur=fournisseur,
#             description=v.get("description", ""),
#             frais_transport=v.get("frais_transport", Decimal("0")),
#             frais_douane=v.get("frais_douane", Decimal("0")),
#             # status par défaut = STATUS_CONFIRMED dans le modèle
#         )

#         # --------- Lot (header) ---------
#         for _ in range(5):
#             numero_lot = generate_numero_lot()
#             try:
#                 lot = Lot.objects.create(
#                     achat=achat,
#                     numero_lot=numero_lot,
#                     description=v.get("description", ""),
#                     received_at=timezone.now(),
#                 )
#                 break
#             except IntegrityError:
#                 # une autre requête a pris le même numéro juste avant ; on retente
#                 continue
#         else:
#             return Response(
#                 {"detail": "Impossible de générer un numéro de lot unique."},
#                 status=400,
#             )

#         # --------- Lignes produit + Stock Réserve ---------
#         produits_by_id = {
#             p.id: p
#             for p in Produit.objects.filter(id__in=pids).only("id", "poids", "nom")
#         }

#         for row in lots_in:
#             produit = produits_by_id[row["produit_id"]]
#             qte = int(row["quantite"])

#             pl = ProduitLine.objects.create(
#                 lot=lot,
#                 produit=produit,
#                 prix_achat_gramme=row.get("prix_achat_gramme"),
#                 quantite=qte,
#             )

#             # Stock initial en Réserve (à adapter à ton modèle Stock réel)
#             Stock.objects.create(
#                 produit_line=pl,
#                 bijouterie=None,
#                 quantite_allouee=qte,
#                 quantite_disponible=qte,
#             )

#         # --------- Totaux Achat via logique centrale ---------
#         achat.update_total(save=True)

#         # Réponse : à toi de voir si tu renvoies l'achat ou le lot
#         out = AchatCreateResponseSerializer(lot).data
#         return Response(out, status=status.HTTP_201_CREATED)



# # ========= VIEW ArrivageMetaUpdateView and ArrivageAdjustmentsView ======================
# # ========== 1) META-ONLY ==========
# class ArrivageMetaUpdateView(APIView):
#     """
#     PATCH /api/purchase/arrivage/<lot_id>/meta/
    
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]
#     http_method_names = ["patch"]

#     @swagger_auto_schema(
#         operation_id="updateArrivageMeta",
#         operation_summary="MAJ META d’un arrivage (Achat/Lot) — sans toucher quantités/prix",
#         # operation_description=(
#         #     "Met à jour les métadonnées : achat (fournisseur, description, frais) "
#         #     "et lot (description, received_at). **Aucune** modification de quantités/prix/stock."
#         # ),
#         operation_description=dedent("""
#                                     Met à jour les métadonnées : achat (fournisseur, description, frais)
#                                     et lot (description, received_at). **Aucune** modification de quantités/prix/stock.
                                    
#                                     Payloads d’exemple
#                                     META-ONLY (PATCH)
                                    
#                                     ```json
#                                     {
#                                         "achat": {
#                                             "description": "MAJ description & frais",
#                                             "frais_transport": 100.00,
#                                             "frais_douane": 50.00,
#                                             "fournisseur": { "id": 12 }
#                                         },
#                                         "lot": {
#                                             "description": "Arrivage DXB révisé",
#                                             "received_at": "2025-10-28T10:00:00Z"
#                                         }
#                                     }
#                                     ```
#                                     """),
#         request_body=ArrivageMetaUpdateInSerializer,
#         responses={200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found"},
#         tags=["Achats / Arrivages"],
#     )
#     @transaction.atomic
#     def patch(self, request, lot_id: int):
#         lot = get_object_or_404(Lot.objects.select_related("achat", "achat__fournisseur"), pk=lot_id)
#         achat = lot.achat

#         s = ArrivageMetaUpdateInSerializer(data=request.data)
#         s.is_valid(raise_exception=True)
#         v = s.validated_data

#         # Achat
#         if "achat" in v:
#             a = v["achat"]
#             if "fournisseur" in a:
#                 achat.fournisseur = _get_or_upsert_fournisseur(a["fournisseur"])
#             if "description" in a:
#                 achat.description = a["description"]
#             if "frais_transport" in a:
#                 achat.frais_transport = a["frais_transport"]
#             if "frais_douane" in a:
#                 achat.frais_douane = a["frais_douane"]
#             achat.save(update_fields=["fournisseur", "description", "frais_transport", "frais_douane"])

#         # Lot
#         if "lot" in v:
#             lp = v["lot"]
#             if "description" in lp:
#                 lot.description = lp["description"]
#             if "received_at" in lp:
#                 lot.received_at = lp["received_at"]
#             lot.save(update_fields=["description", "received_at"])

#         # Recalc totaux (si frais modifiés)
#         _recalc_totaux_achat(achat)

#         return Response({"detail": "Meta mis à jour.", "lot_id": lot.id, "achat_id": achat.id}, status=200)


# # ========== 2) ADJUSTMENTS ==========

# # ---------- Schémas Swagger ----------
# purchase_in_schema = openapi.Schema(
#     type=openapi.TYPE_OBJECT,
#     required=["type", "produit_id", "quantite"],
#     properties={
#         "type": openapi.Schema(type=openapi.TYPE_STRING, enum=["PURCHASE_IN"]),
#         "produit_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#         "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, minimum=1),
#         "prix_achat_gramme": openapi.Schema(type=openapi.TYPE_NUMBER, format="double"),
#         "reason": openapi.Schema(type=openapi.TYPE_STRING),
#     },
# )

# cancel_purchase_schema = openapi.Schema(
#     type=openapi.TYPE_OBJECT,
#     required=["type", "produit_line_id", "quantite"],
#     properties={
#         "type": openapi.Schema(type=openapi.TYPE_STRING, enum=["CANCEL_PURCHASE"]),
#         "produit_line_id": openapi.Schema(type=openapi.TYPE_INTEGER),
#         "quantite": openapi.Schema(type=openapi.TYPE_INTEGER, minimum=1),
#         "reason": openapi.Schema(type=openapi.TYPE_STRING),
#     },
# )

# # 👉 version simplifiée sans oneOf
# actions_schema = openapi.Schema(
#     type=openapi.TYPE_ARRAY,
#     items=openapi.Schema(
#         type=openapi.TYPE_OBJECT,
#         properties={
#             # commun
#             "type": openapi.Schema(
#                 type=openapi.TYPE_STRING,
#                 enum=["PURCHASE_IN", "CANCEL_PURCHASE"],
#                 description="Type d’action : PURCHASE_IN ou CANCEL_PURCHASE",
#             ),
#             # champs pour PURCHASE_IN
#             "produit_id": openapi.Schema(
#                 type=openapi.TYPE_INTEGER,
#                 description="Obligatoire si type=PURCHASE_IN",
#             ),
#             "prix_achat_gramme": openapi.Schema(
#                 type=openapi.TYPE_NUMBER,
#                 format="double",
#                 description="Optionnel, seulement pour PURCHASE_IN",
#             ),
#             # champs pour CANCEL_PURCHASE
#             "produit_line_id": openapi.Schema(
#                 type=openapi.TYPE_INTEGER,
#                 description="Obligatoire si type=CANCEL_PURCHASE",
#             ),
#             # commun
#             "quantite": openapi.Schema(
#                 type=openapi.TYPE_INTEGER,
#                 minimum=1,
#             ),
#             "reason": openapi.Schema(
#                 type=openapi.TYPE_STRING,
#             ),
#         },
#         required=["type", "quantite"],
#         description=(
#             "Selon `type` :\n"
#             "- PURCHASE_IN → utiliser `produit_id`, `quantite`, `prix_achat_gramme` (optionnel)\n"
#             "- CANCEL_PURCHASE → utiliser `produit_line_id`, `quantite`"
#         ),
#     ),
# )

# arrivage_adjustments_example = {
#     "actions": [
#         {
#             "type": "PURCHASE_IN",
#             "produit_id": 55,
#             "quantite": 30,
#             "prix_achat_gramme": 42000.00,
#             "reason": "Complément de réception"
#         },
#         {
#             "type": "CANCEL_PURCHASE",
#             "produit_line_id": 101,
#             "quantite": 12,
#             "reason": "Retour fournisseur (qualité)"
#         }
#     ]
# }

# arrivage_adjustments_request_schema = openapi.Schema(
#     type=openapi.TYPE_OBJECT,
#     required=["actions"],
#     properties={"actions": actions_schema},
#     example=arrivage_adjustments_example,
# )


# class ArrivageAdjustmentsView(APIView):
#     """
#     POST /api/achat/arrivage/{lot_id}/adjustments/
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]
#     http_method_names = ["post"]

#     @swagger_auto_schema(
#         operation_id="arrivageAdjustments",
#         operation_summary="Ajustements d’arrivage (mouvements d’inventaire normalisés)",
#         operation_description=(
#             "Ajouts: PURCHASE_IN (nouvelle ligne) → EXTERNAL → RESERVED\n"
#             "PURCHASE_IN → ajouter une nouvelle ligne (quantité supplémentaire) dans ce lot\n\n"
#             "Retraits: CANCEL_PURCHASE (réduction ligne existante) → RESERVED → EXTERNAL\n"
#             "CANCEL_PURCHASE → retirer une partie d’une ligne existante de ce lot\n\n"
#             "Règles: réduction limitée au disponible en Réserve; aucune suppression si allocations bijouterie existent."
#         ),
#         request_body=arrivage_adjustments_request_schema,
#         responses={
#             200: openapi.Response(
#                 description="OK",
#                 examples={
#                     "application/json": {
#                         "detail": "Ajustements appliqués.",
#                         "lot_id": 1,
#                         "achat_id": 1
#                     }
#                 },
#             ),
#             400: "Bad Request",
#             403: "Forbidden",
#             404: "Not Found",
#         },
#         tags=["Achats / Arrivages"],
#     )
#     @transaction.atomic
#     def post(self, request, lot_id: int):
#         lot = get_object_or_404(Lot.objects.select_related("achat"), pk=lot_id)
#         achat = lot.achat

#         s = ArrivageAdjustmentsInSerializer(data=request.data)
#         s.is_valid(raise_exception=True)
#         actions = s.validated_data["actions"]

#         for i, act in enumerate(actions):
#             t = act.get("type")

#             # ----- PURCHASE_IN (ajout d’une nouvelle ligne) -----
#             if t == "PURCHASE_IN":
#                 pid = int(act["produit_id"])
#                 q   = int(act["quantite"])
#                 ppo = act.get("prix_achat_gramme")  # peut être None

#                 produit = get_object_or_404(Produit.objects.only("id", "poids"), pk=pid)

#                 pl = ProduitLine.objects.create(
#                     lot=lot,
#                     produit=produit,
#                     prix_achat_gramme=ppo,
#                     quantite=q,
#                 )

#                 # stock réserve initial pour cette ligne
#                 Stock.objects.create(
#                     produit_line=pl, bijouterie=None,
#                     quantite_allouee=q, quantite_disponible=q,
#                 )

#                 # mouvement inventaire
#                 InventoryMovement.objects.create(
#                     produit=produit,
#                     movement_type=MovementType.PURCHASE_IN,
#                     qty=q,
#                     unit_cost=None,  # (option) Decimal(produit.poids) * ppo si tu veux valoriser à la pièce
#                     lot=lot,
#                     reason=act.get("reason") or "Ajout ligne (amendement)",
#                     src_bucket=Bucket.EXTERNAL,
#                     dst_bucket=Bucket.RESERVED,
#                     achat=achat,
#                     occurred_at=timezone.now(),
#                     created_by=request.user,
#                 )

#             # ----- CANCEL_PURCHASE (retrait partiel d’une ligne existante) -----
#             elif t == "CANCEL_PURCHASE":
#                 pl_id = int(act["produit_line_id"])
#                 q     = int(act["quantite"])

#                 pl = get_object_or_404(
#                     ProduitLine.objects.select_related("produit", "lot"),
#                     pk=pl_id
#                 )
#                 if pl.lot_id != lot.id:
#                     return Response(
#                         {f"actions[{i}]": f"ProduitLine {pl_id} n'appartient pas au lot {lot.id}."},
#                         status=status.HTTP_400_BAD_REQUEST
#                     )

#                 # interdit si allocations bijouterie existent
#                 has_alloc = Stock.objects.filter(
#                     produit_line=pl, bijouterie__isnull=False, quantite_allouee__gt=0
#                 ).exists()
#                 if has_alloc:
#                     return Response(
#                         {f"actions[{i}]": f"Ligne {pl_id}: des allocations bijouterie existent (retrait interdit)."},
#                         status=status.HTTP_400_BAD_REQUEST
#                     )

#                 # vérifier la réserve
#                 reserve = Stock.objects.filter(produit_line=pl, bijouterie__isnull=True).first()
#                 disp = int(reserve.quantite_disponible or 0) if reserve else 0
#                 if q > disp:
#                     return Response(
#                         {f"actions[{i}]": f"Réduction {q} > disponible réserve ({disp}) pour ligne {pl_id}."},
#                         status=status.HTTP_400_BAD_REQUEST
#                     )

#                 # appliquer la réduction sur la ligne et la réserve
#                 pl.quantite = max(0, int((pl.quantite or 0) - q))
#                 pl.save(update_fields=["quantite"])

#                 if reserve:
#                     reserve.quantite_allouee = max(0, int((reserve.quantite_allouee or 0) - q))
#                     reserve.quantite_disponible = max(0, int((reserve.quantite_disponible or 0) - q))
#                     reserve.save(update_fields=["quantite_allouee", "quantite_disponible"])

#                 # mouvement inventaire
#                 InventoryMovement.objects.create(
#                     produit=pl.produit,
#                     movement_type=MovementType.CANCEL_PURCHASE,
#                     qty=q,
#                     unit_cost=None,
#                     lot=lot,
#                     reason=act.get("reason") or "Retrait partiel (annulation achat)",
#                     src_bucket=Bucket.RESERVED,
#                     dst_bucket=Bucket.EXTERNAL,
#                     achat=achat,
#                     occurred_at=timezone.now(),
#                     created_by=request.user,
#                 )

#             else:
#                 return Response(
#                     {f"actions[{i}]": f"Type inconnu: {t}"},
#                     status=status.HTTP_400_BAD_REQUEST
#                 )

#         # (option) Recalcul des totaux de l’achat si tu as une fonction utilitaire
#         # _recalc_totaux_achat(achat)

#         return Response(
#             {"detail": "Ajustements appliqués.", "lot_id": lot.id, "achat_id": achat.id},
#             status=status.HTTP_200_OK
#         )
# # ========= AND VIEW ArrivageMetaUpdateView and ArrivageAdjustmentsView ======================



# class AchatProduitGetOneView(APIView):  # renommé pour cohérence
#     renderer_classes = [UserRenderer]
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Récupère un achat spécifique avec ses produits associés.",
#         responses={
#             200: openapi.Response('Achat trouvé', AchatSerializer),
#             404: "Achat non trouvé",
#             403: "Accès refusé"
#         }
#     )
#     @transaction.atomic
#     def get(self, request, pk):
#         user_role = getattr(request.user.user_role, 'role', None)
#         if user_role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             achat = Achat.objects.select_related('fournisseur').prefetch_related('produits__produit').get(pk=pk)
#             serializer = AchatSerializer(achat)
#             return Response(serializer.data, status=200)

#         except Achat.DoesNotExist:
#             return Response({"detail": "Achat not found."}, status=404)

#         except Exception as e:
#             return Response({"detail": f"Erreur interne : {str(e)}"}, status=500)



# # (Optionnel) log des mouvements ; no-op si le module n'existe pas
# try:
#     from inventory.services import log_move
# except Exception:
#     def log_move(**kwargs):
#         return None


# # ---------- Helpers rôles ----------
# def _role_ok(user) -> bool:
#     """
#     Autorise seulement admin / manager (en fonction de ton user_role).
#     Adapte si ton système de rôles est différent.
#     """
#     role_obj = getattr(user, "user_role", None)
#     return bool(role_obj and role_obj.role in ["admin", "manager"])

# # ---------- Helpers Stock (STRICT: jamais de création) ----------
# # Snapshot du stock pour une ligne de produit
# def _snapshot_stock_for_line(pl: ProduitLine) -> Tuple[int, Dict[int, int]]:
#     """
#     Retourne :
#       - reserved : quantité totale en réserve (bijouterie NULL)
#       - by_shop  : dict {bijouterie_id: quantite_disponible} pour chaque bijouterie

#     On s'appuie sur le même modèle que dans ArrivageAdjustmentsView :
#       Stock(produit_line, bijouterie, quantite_allouee, quantite_disponible)
#     """
#     qs = Stock.objects.filter(produit_line=pl)

#     # Réserve (bijouterie NULL)
#     reserved = qs.filter(bijouterie__isnull=True).aggregate(
#         s=Coalesce(Sum("quantite_disponible"), 0)
#     )["s"] or 0

#     # Bijouteries
#     shops = (
#         qs.filter(bijouterie__isnull=False)
#         .values("bijouterie_id")
#         .annotate(s=Coalesce(Sum("quantite_disponible"), 0))
#     )

#     by_shop = {row["bijouterie_id"]: int(row["s"] or 0) for row in shops}

#     return int(reserved), by_shop

# # Décrément strict d’une ligne Stock
# def _deplete_stock_row(stock_row: Stock, delta: int):
#     """
#     Décrémente quantite_allouee et quantite_disponible d'une ligne de Stock
#     sans jamais passer en négatif.
#     """
#     if delta <= 0:
#         return

#     qa = int(stock_row.quantite_allouee or 0)
#     qd = int(stock_row.quantite_disponible or 0)

#     if delta > qd:
#         raise ValidationError("Stock insuffisant pour décrémenter.")

#     stock_row.quantite_allouee = max(0, qa - delta)
#     stock_row.quantite_disponible = max(0, qd - delta)
#     stock_row.save(update_fields=["quantite_allouee", "quantite_disponible"])

# # ====================== VIEW ======================
# class AchatCancelView(APIView):
#     """
#     Annule *intégralement* un achat :
#       - vérifie que toutes les quantités de chaque ProduitLine sont encore présentes
#         (réserve + bijouteries),
#       - déverse le stock vers EXTERNAL,
#       - crée des mouvements CANCEL_PURCHASE,
#       - marque l'achat comme annulé.
#     """
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         tags=["Achats"],
#         operation_summary="Annuler un achat (mouvements inverses vers EXTERNAL)",
#         operation_description=(
#             "Annulation intégrale si *toutes* les quantités des ProduitLine de l'achat "
#             "sont encore présentes dans le système (réserve et/ou bijouteries). "
#             "Sinon → 409 avec détail.\n\n"
#             "Entrée: `AchatCancelSerializer` (reason obligatoire, cancelled_at optionnel). "
#             "Sortie: `AchatSerializer` + détails des lignes annulées."
#         ),
#         manual_parameters=[
#             openapi.Parameter(
#                 name="achat_id",
#                 in_=openapi.IN_PATH,
#                 type=openapi.TYPE_INTEGER,
#                 required=True,
#                 description="ID de l'achat à annuler",
#             ),
#         ],
#         request_body=AchatCancelSerializer,
#         responses={
#             200: AchatSerializer,
#             400: "Requête invalide",
#             403: "Accès refusé",
#             404: "Ressource introuvable",
#             409: "Conflit (quantités manquantes empêchant l'annulation)",
#         },
#     )
#     @transaction.atomic
#     def post(self, request, achat_id: int):
#         user = request.user
#         if not _role_ok(user):
#             return Response({"detail": "Access Denied"}, status=status.HTTP_403_FORBIDDEN)

#         achat = get_object_or_404(
#             Achat.objects.select_related("fournisseur"),
#             pk=achat_id,
#         )

#         # déjà annulé ?
#         if achat.status == getattr(Achat, "STATUS_CANCELLED", "cancelled"):
#             return Response({"detail": "Achat déjà annulé."}, status=status.HTTP_400_BAD_REQUEST)

#         # valider payload
#         ser = AchatCancelSerializer(data=request.data)
#         ser.is_valid(raise_exception=True)
#         reason = ser.validated_data["reason"]
#         cancelled_at = ser.validated_data.get("cancelled_at") or timezone.now()

#         # 1) Contrôle d'annulabilité
#         # On parcourt toutes les ProduitLine des lots de l'achat
#         lignes = (
#             ProduitLine.objects
#             .filter(lot__achat=achat)
#             .select_related("produit", "lot")
#         )

#         errors = []

#         for pl in lignes:
#             reserved, by_shop = _snapshot_stock_for_line(pl)
#             on_hand = reserved + sum(by_shop.values())
#             expected = int(pl.quantite or 0)

#             if on_hand != expected:
#                 errors.append({
#                     "produit_line_id": pl.id,
#                     "produit_id": pl.produit_id,
#                     "lot_id": pl.lot_id,
#                     "expected": expected,
#                     "on_hand": int(on_hand),
#                     "detail": "Quantités manquantes (vente ou ajustement déjà passés).",
#                 })

#         if errors:
#             return Response(
#                 {
#                     "detail": "Annulation impossible: certaines quantités ont déjà été consommées.",
#                     "missing": errors,
#                 },
#                 status=status.HTTP_409_CONFLICT,
#             )

#         # 2) Exécution : déverser tout vers EXTERNAL + mouvements
#         cancelled_lines = []

#         for pl in lignes:
#             produit = pl.produit
#             lot = pl.lot

#             reserved, by_shop = _snapshot_stock_for_line(pl)

#             # -------- Réserve -> EXTERNAL --------
#             if reserved > 0:
#                 reserve_row = (
#                     Stock.objects
#                     .filter(produit_line=pl, bijouterie__isnull=True)
#                     .first()
#                 )
#                 if reserve_row:
#                     _deplete_stock_row(reserve_row, reserved)

#                     InventoryMovement.objects.create(
#                         produit=produit,
#                         movement_type=MovementType.CANCEL_PURCHASE,
#                         qty=int(reserved),
#                         unit_cost=pl.prix_achat_gramme,
#                         lot=lot,
#                         reason=f"Annulation achat #{achat.id}: retour réserve → externe",
#                         src_bucket=Bucket.RESERVED,
#                         dst_bucket=Bucket.EXTERNAL,
#                         achat=achat,
#                         occurred_at=timezone.now(),
#                         created_by=user,
#                     )

#             # -------- Bijouteries -> EXTERNAL --------
#             shop_rows = Stock.objects.filter(produit_line=pl, bijouterie__isnull=False)
#             for s in shop_rows:
#                 qd = int(s.quantite_disponible or 0)
#                 if qd <= 0:
#                     continue

#                 bid = s.bijouterie_id
#                 _deplete_stock_row(s, qd)

#                 InventoryMovement.objects.create(
#                     produit=produit,
#                     movement_type=MovementType.CANCEL_PURCHASE,
#                     qty=qd,
#                     unit_cost=pl.prix_achat_gramme,
#                     lot=lot,
#                     reason=f"Annulation achat #{achat.id}: retour bijouterie → externe",
#                     src_bucket=Bucket.BIJOUTERIE,
#                     src_bijouterie_id=bid,
#                     dst_bucket=Bucket.EXTERNAL,
#                     achat=achat,
#                     occurred_at=timezone.now(),
#                     created_by=user,
#                 )

#             cancelled_lines.append({
#                 "produit_line_id": pl.id,
#                 "produit_id": produit.id,
#                 "lot_id": lot.id if lot else None,
#                 "returned": int(reserved + sum(by_shop.values())),
#             })

#         # 3) Statut d'achat
#         achat.status = getattr(Achat, "STATUS_CANCELLED", "cancelled")
#         achat.cancel_reason = reason
#         achat.cancelled_at = cancelled_at
#         achat.cancelled_by = user
#         achat.save(update_fields=["status", "cancel_reason", "cancelled_at", "cancelled_by"])

#         # (facultatif) si tu veux recalculer les totaux après (les lignes n'ont pas changé)
#         # achat.update_total(save=True)

#         return Response(
#             {
#                 "message": "Achat annulé avec succès.",
#                 "achat": AchatSerializer(achat).data,
#                 "cancelled": cancelled_lines,
#             },
#             status=status.HTTP_200_OK,
#         )
# # -----------------End cencel


# class AchatProduitPDFView(APIView):
#     permission_classes = [IsAuthenticated]

#     @swagger_auto_schema(
#         operation_description="Télécharge le PDF du détail d’un produit acheté.",
#         manual_parameters=[
#             openapi.Parameter('pk', openapi.IN_PATH, description="ID de l'achat-produit", type=openapi.TYPE_INTEGER)
#         ],
#         responses={
#             200: openapi.Response(description="PDF généré avec succès"),
#             404: "Produit d'achat non trouvé",
#             403: "Accès refusé"
#         }
#     )
#     def get(self, request, pk):
#         role = getattr(request.user.user_role, 'role', None)
#         if role not in ['admin', 'manager']:
#             return Response({"message": "Access Denied"}, status=403)

#         try:
#             achat_produit = Lot.objects.select_related('achat', 'produit', 'fournisseur').get(pk=pk)
#         except Lot.DoesNotExist:
#             return Response({"detail": "AchatProduit non trouvé."}, status=404)

#         context = {
#             "p": achat_produit,
#             "achat": achat_produit.achat,
#             "fournisseur": achat_produit.fournisseur or achat_produit.achat.fournisseur
#         }

#         template = get_template("pdf/achat_produit_detail.html")
#         html = template.render(context)

#         response = HttpResponse(content_type='application/pdf')
#         response['Content-Disposition'] = f'attachment; filename=AchatProduit_{achat_produit.id}.pdf'

#         pisa_status = pisa.CreatePDF(html, dest=response)
#         if pisa_status.err:
#             return Response({"detail": "Erreur lors de la génération du PDF"}, status=500)

#         return response


# # class AchatPDFView(APIView):
# #     permission_classes = [IsAuthenticated]
    
# #     @swagger_auto_schema(
# #         operation_description="Télécharge le PDF du détail d’un achat.",
# #         manual_parameters=[
# #             openapi.Parameter('pk', openapi.IN_PATH, description="ID de l'achat", type=openapi.TYPE_INTEGER)
# #         ],
# #         responses={
# #             200: openapi.Response(description="PDF généré"),
# #             404: "Achat non trouvé",
# #             403: "Accès refusé"
# #         }
# #     )
# #     def get(self, request, pk):
# #         role = getattr(request.user.user_role, 'role', None)
# #         if role not in ['admin', 'manager', 'vendeur']:
# #             return Response({"message": "Access Denied"}, status=403)

# #         try:
# #             # achat = Achat.objects.select_related('fournisseur').prefetch_related('produits__produit').get(pk=pk)
# #             achat = AchatProduit.objects.select_related('fournisseur').prefetch_related('produits__produit').get(pk=pk)
# #         except Achat.DoesNotExist:
# #             return Response({"detail": "Achat non trouvé."}, status=404)

# #         template_path = 'pdf/achat_detail.html'
# #         context = {'achat': achat}
# #         template = get_template(template_path)
# #         html = template.render(context)

# #         response = HttpResponse(content_type='application/pdf')
# #         response['Content-Disposition'] = f'attachment; filename=Achat_{achat.numero_achat}.pdf'

# #         pisa_status = pisa.CreatePDF(html, dest=response)

# #         if pisa_status.err:
# #             return Response({"detail": "Erreur lors de la génération du PDF"}, status=500)
# #         return response


# # class AchatUpdateAPIView(APIView):
# #     @transaction.atomic
# #     def put(self, request, achat_id):
# #         # Récupérer l'achat et ses informations
# #         try:
# #             achat = Achat.objects.get(id=achat_id)
# #             fournisseur_data = request.data.get('fournisseur')
# #             produits_data = request.data.get('produits')  # Liste de produits à mettre à jour
# #             achatproduit_data = request.data.get('achatproduit')
# #             # Mettre à jour l'achat
# #             achat.montant_total = request.data.get('montant_total', achat.montant_total)

# #             # #recupere le id du achatproduit pour setter le stock precendant
# #             # achat_produit_obj = AchatProduit.objects.get(achat_id=achat.id)
# #             # print(achat_produit_obj.quantite)
# #             # quantite_achat_update = achat_produit_obj.quantite

# #             achat.save()

# #             # Mettre à jour le fournisseur
# #             if fournisseur_data:
# #                 fournisseur = Fournisseur.objects.get(id=fournisseur_data['id'])
# #                 fournisseur.nom = fournisseur_data.get('nom', fournisseur.nom)
# #                 fournisseur.prenom = fournisseur_data.get('prenom', fournisseur.prenom)
# #                 fournisseur.address = fournisseur_data.get('address', fournisseur.address)
# #                 fournisseur.telephone = fournisseur_data.get('telephone', fournisseur.telephone)
# #                 fournisseur.save()
# #                 achat.fournisseur = fournisseur  # Associer à l'achat
# #                 achat.save()


# #             # Mettre à jour les produits et le stock
# #             for produit_data in produits_data:
# #                 produit = Produit.objects.get(id=produit_data['id'])

# #                 #recupere le id du achatproduit pour setter le stock precendant
# #                 achat_produit_obj = AchatProduit.objects.get(achat_id=achat, produit_id=produit)
# #                 print(achat_produit_obj.produit_id)
# #                 print(achat_produit_obj.quantite)
# #                 quantite_achat_update = achat_produit_obj.quantite

# #                 quantite_achat = produit_data['quantite']
# #                 #Ceux-ci  la quantité enregistré et il faut le odifier pour mettre a jour le stock
# #                 # prix_achat = produit_data['prix_achat']
# #                 prix_achat_gramme = produit_data['prix_achat_gramme']
# #                 tax = produit_data['tax']

# #                 prix_achat = Decimal(prix_achat_gramme)*Decimal(produit.poids)
# #                 sous_total_prix_achat = Decimal(prix_achat)*Decimal(quantite_achat)

# #                 prix_achat = Decimal(prix_achat_gramme)*Decimal(produit.poids)
# #                 sous_total_prix_achat = Decimal(prix_achat)*Decimal(quantite_achat)

# #                 # Mettre à jour la table AchatProduit
# #                 # achatProduit = AchatProduit.objects.get(id=achatproduit_data['id'])
# #                 # achatProduit.produit=produit
# #                 # achatProduit.quantite = quantite_achat
# #                 # achatProduit.prix_achat_gramme = prix_achat_gramme
# #                 # achatProduit.tax=tax
# #                 # achatProduit.sous_total_prix_achat=sous_total_prix_achat
# #                 # achatProduit.save()
# #                 achat_produit, created = AchatProduit.objects.update_or_create(
# #                     achat=achat,
# #                     produit=produit,
# #                     defaults={
# #                         'fournisseur': fournisseur,
# #                         'quantite': quantite_achat,
# #                         'prix_achat_gramme': prix_achat_gramme,
# #                         'prix_achat': prix_achat,
# #                         'tax':tax,
# #                         'sous_total_prix_achat': sous_total_prix_achat
# #                         }
# #                 )
# #                 # Mettre à jour le stock
# #                 stock, created = Stock.objects.get_or_create(produit=produit)
# #                 #Appliquon la quantité pour que la mis a jour soit normal sans la table stock
# #                 quantite_achat_normal = quantite_achat - quantite_achat_update
# #                 #si cette diference est egale a 0 il n'aura pas de changement de stock
# #                 if quantite_achat_normal > 0:
# #                     quantite_achat_normal = quantite_achat_normal
# #                     stock.quantite += quantite_achat_normal  # Ajouter la quantité achetée
# #                     stock.save()
# #                 # elif quantite_achat_normal == 0:
# #                 #     stock.quantite = quantite_achat_update
# #                 #     stock.save()
# #                 else:
# #                     quantite_achat_normal = quantite_achat_normal*(-1)
# #                     stock.quantite -= quantite_achat_normal  # Ajouter la quantité achetée
# #                     stock.save()
# #                 # stock.quantite += quantite_achat  # Ajouter la quantité achetée
# #                 # stock.save()

# #                 achatproduit_serializer = AchatSerializer(achat)
# #             return Response(achatproduit_serializer.data, status=status.HTTP_200_OK)

# #         except Exception as e:
# #             # Si une erreur se produit, toute la transaction est annulée.
# #             return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

# # django apiview put produit, pachat, suplier, produitsuplier and stock @transaction-atomic json out update pachat suplier all produit in achate



# # class AchatUpdateAchatProduitAPIView(APIView):
# #     renderer_classes = [UserRenderer]
# #     permission_classes = [IsAuthenticated]
    
# #     @transaction.atomic
# #     def put(self, request, achat_id):
# #         if request.user.user_role is not None and request.user.user_role.role != 'admin' and request.user.user_role.role != 'manager' and request.user.user_role.role != 'vendeur':
# #             return Response({"message": "Access Denied"})
# #         try:
# #             # Retrieve the Achat object to update
# #             achat = Achat.objects.get(id=achat_id)
# #             fournisseur_data = request.data.get('fournisseur')
# #             # fournisseur_id = Achat.objects.get(fournisseur_id=achat.fournisseur_id)
# #             # print(fournisseur_id)
# #             # print(achat)
# #             fournisseur_id=achat.fournisseur_id

# #             achat.save()

# #             if fournisseur_data:
# #                 fournisseur = Fournisseur.objects.get(id=fournisseur_id)
# #                 fournisseur.nom = fournisseur_data.get('nom', fournisseur.nom)
# #                 fournisseur.prenom = fournisseur_data.get('prenom', fournisseur.prenom)
# #                 fournisseur.address = fournisseur_data.get('address', fournisseur.address)
# #                 fournisseur.telephone = fournisseur_data.get('telephone', fournisseur.telephone)
# #                 fournisseur.save()
# #                 achat.fournisseur = fournisseur  # Associer à l'achat
# #                 achat.save()
# #             # except Achat.DoesNotExist:
# #             #     return Response({"error": "Achat not found"}, status=status.HTTP_404_NOT_FOUND)

# #             # Deserialize the incoming data
# #             # serializer = AchatSerializer(achat, data=request.data)
# #             # if serializer.is_valid():
# #             #     # Update Achat fields
# #             #     serializer.save()


# #             # # Mettre à jour le fournisseur
# #             # if fournisseur_data:
# #             #     fournisseur = Fournisseur.objects.get(id=fournisseur_data['id'])
# #             #     fournisseur.nom = fournisseur_data.get('nom', fournisseur.nom)
# #             #     fournisseur.prenom = fournisseur_data.get('prenom', fournisseur.prenom)
# #             #     fournisseur.address = fournisseur_data.get('address', fournisseur.address)
# #             #     fournisseur.telephone = fournisseur_data.get('telephone', fournisseur.telephone)
# #             #     fournisseur.save()
# #             #     achat.fournisseur = fournisseur  # Associer à l'achat
# #             #     achat.save()

# #             # Loop through the products in the 'produits' field
# #             montant_total = 0
# #             for produit_data in request.data.get('produits', []):
# #                 produit_id = produit_data.get('produit', {}).get('id')
# #                 quantite = produit_data.get('quantite')
# #                 prix_achat_gramme = produit_data.get('prix_achat_gramme')
# #                 tax = produit_data.get('tax')
                
                
# #                 # print(produit_data)
# #                 if produit_id and quantite is not None:
# #                     # Check if the produit exists
# #                     try:
# #                         produit = Produit.objects.get(id=produit_id)

# #                     except Produit.DoesNotExist:
# #                         return Response({"error": f"Produit with id {produit_id} not found"}, status=status.HTTP_400_BAD_REQUEST)


# #                     #recupere le id du achatproduit pour setter le stock precendant
# #                     achat_produit_obj = AchatProduit.objects.get(achat_id=achat, produit_id=produit)
# #                     # print(achat_produit_obj.produit_id)
# #                     # print(achat_produit_obj.quantite)
# #                     quantite_achat_update = achat_produit_obj.quantite

# #                     quantite_achat = produit_data['quantite']
# #                     #Ceux-ci  la quantité enregistré et il faut le odifier pour mettre a jour le stock
# #                     # prix_achat = produit_data['prix_achat']
# #                     # prix_achat_gramme = produit_data['prix_achat_gramme']
# #                     # tax = produit_data['tax']

# #                     # prix_achat = Decimal(prix_achat_gramme)*Decimal(produit.poids)
# #                     # sous_total_prix_achat = Decimal(prix_achat)*Decimal(quantite_achat)

# #                     # prix_achat = Decimal(prix_achat_gramme)*Decimal(produit.poids)
# #                     # sous_total_prix_achat = Decimal(prix_achat)*Decimal(quantite_achat)


# #                     # # Update the stock for the produit
# #                     # stock, created = Stock.objects.get_or_create(produit=produit)
# #                     # stock.quantite += quantite  # Assuming a reduction in stock
# #                     # stock.save()

# #                     # Add or update the AchatProduit entry
# #                     achat_produit, created = AchatProduit.objects.update_or_create(
# #                         achat=achat,
# #                         produit=produit,
# #                         fournisseur=fournisseur,
# #                         defaults={
# #                             'quantite': quantite_achat,
# #                             'prix_achat_gramme': prix_achat_gramme,
# #                             # 'prix_achat': prix_achat,
# #                             'tax':tax,
# #                         }
# #                     )
# #                     poids = produit.poids
# #                     achat_produit.sous_total_prix_achat = Decimal(prix_achat_gramme)*Decimal(quantite_achat)*Decimal(poids)
# #                     montant_total += achat_produit.sous_total_prix_achat + achat_produit.tax
# #                     achat_produit.save()
# #                     achat.montant_total = montant_total
# #                     achat.save()
# #                     # montant_total = 0
# #                     # Mettre à jour le stock
# #                     stock, created = Stock.objects.get_or_create(produit=produit)
# #                     #Appliquon la quantité pour que la mis a jour soit normal sans la table stock
# #                     quantite_achat_normal = quantite_achat - quantite_achat_update
# #                     #si cette diference est egale a 0 il n'aura pas de changement de stock
# #                     if quantite_achat_normal > 0:
# #                         quantite_achat_normal = quantite_achat_normal
# #                         stock.quantite += quantite_achat_normal  # Ajouter la quantité achetée
# #                         stock.save()
# #                     # elif quantite_achat_normal == 0:
# #                     #     stock.quantite = quantite_achat_update
# #                     #     stock.save()
# #                     else:
# #                         quantite_achat_normal = quantite_achat_normal*(-1)
# #                         stock.quantite -= quantite_achat_normal  # Ajouter la quantité achetée
# #                         stock.save()
# #                     # stock.quantite += quantite_achat  # Ajouter la quantité achetée
# #                     # stock.save()

# #             # Return the updated achat with the produits
# #             updated_achat = Achat.objects.prefetch_related('produits').get(id=achat.id)
# #             updated_achat_serializer = AchatSerializer(updated_achat)
# #             return Response(updated_achat_serializer.data, status=status.HTTP_200_OK)

# #         except Achat.DoesNotExist:
# #             return Response({"error": "Achat not found"}, status=status.HTTP_404_NOT_FOUND)
# #             # return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)





# # ------------------------- ------------------------------------------------/
# #/                        Adjustement                                      #/
# #---------------------------------------------------------------------------/

# try:
#     from inventory.services import log_move
# except Exception:
#     def log_move(**kwargs):
#         return None


# def _safe_unit_cost(produit, prix_achat_gramme):
#     """
#     Calcule un unit_cost (prix par pièce) à partir du prix_achat_gramme et du poids produit.
#     Retourne None si impossible ou données invalides.
#     """
#     if not prix_achat_gramme or produit.poids is None:
#         return None
#     try:
#         return (Decimal(str(prix_achat_gramme)) * Decimal(str(produit.poids))).quantize(TWOPLACES)
#     except (InvalidOperation, TypeError, ValueError):
#         return None


# def _log_arrivage_move(
#     *,
#     action_type: str,
#     produit,
#     lot,
#     achat,
#     qty: int,
#     user,
#     prix_achat_gramme=None,
#     reason: str | None = None,
# ):
#     """
#     Centralise la création du mouvement d'inventaire pour un ajustement d'arrivage.
#     - action_type="PURCHASE_IN"  => EXTERNAL -> RESERVED
#     - action_type="CANCEL_PURCHASE" => RESERVED -> EXTERNAL
#     """
#     if action_type == "PURCHASE_IN":
#         movement_type = MovementType.PURCHASE_IN
#         src_bucket = Bucket.EXTERNAL
#         dst_bucket = Bucket.RESERVED
#         default_reason = "Ajout ligne (amendement)"
#     elif action_type == "CANCEL_PURCHASE":
#         movement_type = MovementType.CANCEL_PURCHASE
#         src_bucket = Bucket.RESERVED
#         dst_bucket = Bucket.EXTERNAL
#         default_reason = "Retrait partiel (annulation achat)"
#     else:
#         raise ValueError(f"Type d'action inconnu pour mouvement: {action_type}")

#     unit_cost = _safe_unit_cost(produit, prix_achat_gramme)
#     final_reason = reason or default_reason

#     return log_move(
#         produit=produit,
#         qty=int(qty),
#         movement_type=movement_type,
#         src_bucket=src_bucket,
#         dst_bucket=dst_bucket,
#         unit_cost=unit_cost,
#         lot=lot,
#         achat=achat,
#         user=user,
#         reason=final_reason,
#     )

# class ArrivageAdjustmentsView(APIView):
#     """
#     POST /api/achat/arrivage/{lot_id}/adjustments/

#     Permet :
#     - d’ajouter des lignes au lot (type=PURCHASE_IN)
#     - de retirer partiellement une ligne existante (type=CANCEL_PURCHASE)
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManager]
#     http_method_names = ["post"]

#     @swagger_auto_schema(
#         operation_id="arrivageAdjustments",
#         operation_summary="Ajustements d’arrivage (mouvements d’inventaire normalisés)",
#         operation_description=dedent("""
#             Applique une série d’actions sur un **lot** existant :

#             • **PURCHASE_IN** : ajout d’une nouvelle ligne produit dans ce lot  
#               - Stock : EXTERNAL → RESERVED  
#               - Champs utilisés : `produit_id`, `quantite`, `prix_achat_gramme` (optionnel), `reason` (optionnel)

#             • **CANCEL_PURCHASE** : retrait partiel d’une ligne existante du lot  
#               - Stock : RESERVED → EXTERNAL  
#               - Champs utilisés : `produit_line_id`, `quantite`, `reason` (optionnel)

#             Exemple de payload :

#             ```json
#             {
#               "actions": [
#                 {
#                   "type": "PURCHASE_IN",
#                   "produit_id": 55,
#                   "quantite": 30,
#                   "prix_achat_gramme": 42000.00,
#                   "reason": "Complément de réception"
#                 },
#                 {
#                   "type": "CANCEL_PURCHASE",
#                   "produit_line_id": 101,
#                   "quantite": 12,
#                   "reason": "Retour fournisseur (qualité)"
#                 }
#               ]
#             }
#             ```
#         """),
#         request_body=ArrivageAdjustmentsInSerializer,
#         responses={
#             200: ArrivageAdjustmentsOutSerializer,
#             400: "Bad Request",
#             403: "Forbidden",
#             404: "Not Found",
#         },
#         tags=["Achats / Arrivages"],
#     )
#     @transaction.atomic
#     def post(self, request, lot_id: int):
#         lot = get_object_or_404(Lot.objects.select_related("achat"), pk=lot_id)
#         achat = lot.achat

#         s = ArrivageAdjustmentsInSerializer(data=request.data)
#         s.is_valid(raise_exception=True)
#         actions = s.validated_data["actions"]

#         for i, act in enumerate(actions):
#             t = act["type"]

#             # ----- PURCHASE_IN (ajout d’une nouvelle ligne) -----
#             if t == "PURCHASE_IN":
#                 pid = int(act["produit_id"])
#                 q   = int(act["quantite"])
#                 ppo = act.get("prix_achat_gramme")  # peut être None

#                 produit = get_object_or_404(Produit.objects.only("id", "poids"), pk=pid)

#                 pl = ProduitLine.objects.create(
#                     lot=lot,
#                     produit=produit,
#                     prix_achat_gramme=ppo,
#                     quantite=q,
#                 )

#                 # stock réserve initial pour cette ligne
#                 Stock.objects.create(
#                     produit_line=pl, bijouterie=None,
#                     quantite_allouee=q, quantite_disponible=q,
#                 )

#                 # Mouvement inventaire automatique
#                 _log_arrivage_move(
#                     action_type="PURCHASE_IN",
#                     produit=produit,
#                     lot=lot,
#                     achat=achat,
#                     qty=q,
#                     user=request.user,
#                     prix_achat_gramme=ppo,
#                     reason=act.get("reason"),
#                 )

#             # ----- CANCEL_PURCHASE (retrait partiel d’une ligne existante) -----
#             elif t == "CANCEL_PURCHASE":
#                 pl_id = int(act["produit_line_id"])
#                 q     = int(act["quantite"])

#                 pl = get_object_or_404(
#                     ProduitLine.objects.select_related("produit", "lot"),
#                     pk=pl_id
#                 )
#                 if pl.lot_id != lot.id:
#                     return Response(
#                         {f"actions[{i}]": f"ProduitLine {pl_id} n'appartient pas au lot {lot.id}."},
#                         status=status.HTTP_400_BAD_REQUEST
#                     )

#                 # interdit si allocations bijouterie existent
#                 has_alloc = Stock.objects.filter(
#                     produit_line=pl, bijouterie__isnull=False, quantite_allouee__gt=0
#                 ).exists()
#                 if has_alloc:
#                     return Response(
#                         {f"actions[{i}]": f"Ligne {pl_id}: des allocations bijouterie existent (retrait interdit)."},
#                         status=status.HTTP_400_BAD_REQUEST
#                     )

#                 # vérifier la réserve
#                 reserve = Stock.objects.filter(produit_line=pl, bijouterie__isnull=True).first()
#                 disp = int(reserve.quantite_disponible or 0) if reserve else 0
#                 if q > disp:
#                     return Response(
#                         {f"actions[{i}]": f"Réduction {q} > disponible réserve ({disp}) pour ligne {pl_id}."},
#                         status=status.HTTP_400_BAD_REQUEST
#                     )

#                 # appliquer la réduction sur la ligne et la réserve
#                 pl.quantite = max(0, int((pl.quantite or 0) - q))
#                 pl.save(update_fields=["quantite"])

#                 if reserve:
#                     reserve.quantite_allouee = max(0, int((reserve.quantite_allouee or 0) - q))
#                     reserve.quantite_disponible = max(0, int((reserve.quantite_disponible or 0) - q))
#                     reserve.save(update_fields=["quantite_allouee", "quantite_disponible"])

#                 # Mouvement inventaire automatique
#                 _log_arrivage_move(
#                     action_type="CANCEL_PURCHASE",
#                     produit=pl.produit,
#                     lot=lot,
#                     achat=achat,
#                     qty=q,
#                     user=request.user,
#                     prix_achat_gramme=pl.prix_achat_gramme,
#                     reason=act.get("reason"),
#                 )

#             else:
#                 return Response(
#                 {f"actions[{i}]": f"Type inconnu: {t}"},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         return Response(
#             {"detail": "Ajustements appliqués.", "lot_id": lot.id, "achat_id": achat.id},
#             status=status.HTTP_200_OK
#         )



