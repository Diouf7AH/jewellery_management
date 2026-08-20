import zipfile
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from io import BytesIO

from django.db import IntegrityError, transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce, ExtractYear
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from openpyxl import Workbook
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.mixins import ExportXlsxMixin
from backend.permissions import ROLE_ADMIN, ROLE_MANAGER, IsAdminOrManager
from backend.query_scopes import scope_queryset_by_bijouterie
from backend.renderers import UserRenderer
from backend.roles import ROLE_ADMIN, ROLE_MANAGER, get_role_name
from inventory.models import Bucket, InventoryMovement, MovementType
from inventory.services import log_move
from purchase.models import Achat, Fournisseur, Lot, ProduitLine
from purchase.services.arrivage import (create_arrivage,
                                        resolve_arrivage_bijouterie)
from purchase.services.etiquettes import build_etiquette_bague_png
from purchase.utils import generate_numero_lot
from stock.models import Stock
from store.models import Bijouterie, Produit

from .models import Achat, Fournisseur, Lot, ProduitLine
from .serializers import (AchatDetailSerializer, AchatOutSerializer,
                          ArrivageCreateInSerializer,
                          ArrivageCreateResponseSerializer,
                          ArrivageMetaUpdateInSerializer,
                          FournisseurSerializer, LotListSerializer,
                          ProduitLineMiniSerializer)


class AchatDashboardView(APIView):
    """
    Dashboard des achats et arrivages.

    Périodes disponibles :
    - current_year : année en cours uniquement ;
    - 3_years      : trois dernières années,
                     année en cours incluse.

    Règles temporelles :
    - Achat.created_at pour les statistiques d'achats ;
    - Lot.received_at pour les statistiques d'arrivages.

    Périmètre :
    - admin : toutes les bijouteries ;
    - manager : uniquement ses bijouteries affectées.
    """

    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]

    @swagger_auto_schema(
        operation_summary=(
            "Dashboard des achats et arrivages"
        ),
        operation_description=(
            "Retourne les statistiques des achats et arrivages.\n\n"
            "Périodes disponibles :\n"
            "- `current_year` : année en cours uniquement ;\n"
            "- `3_years` : trois dernières années, "
            "année en cours incluse.\n\n"
            "Par défaut : `current_year`.\n\n"
            "Périmètre :\n"
            "- admin : toutes les bijouteries ;\n"
            "- manager : uniquement ses bijouteries affectées.\n\n"
            "Règles temporelles :\n"
            "- achats : `Achat.created_at` ;\n"
            "- lots et produits reçus : `Lot.received_at`."
        ),
        manual_parameters=[
            openapi.Parameter(
                "periode",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                enum=[
                    "current_year",
                    "3_years",
                ],
                description=(
                    "Période du dashboard. "
                    "`current_year` = année en cours ; "
                    "`3_years` = trois dernières années. "
                    "Défaut : current_year."
                ),
            ),
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                description=(
                    "Filtrer les statistiques par bijouterie."
                ),
            ),
        ],
        tags=["Achats - Dashboard"],
        responses={
            200: openapi.Response(
                description=(
                    "Dashboard des achats récupéré avec succès."
                ),
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "periode": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                        ),
                        "bijouterie_id": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            nullable=True,
                        ),
                        "total_achats": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                        ),
                        "montant_total": openapi.Schema(
                            type=openapi.TYPE_STRING,
                        ),
                        "total_lots": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                        ),
                        "total_quantite": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                        ),
                        "total_poids": openapi.Schema(
                            type=openapi.TYPE_STRING,
                        ),
                        "achats_par_annee": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(
                                type=openapi.TYPE_OBJECT,
                            ),
                        ),
                        "top_fournisseurs": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(
                                type=openapi.TYPE_OBJECT,
                            ),
                        ),
                        "repartition_produits": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(
                                type=openapi.TYPE_OBJECT,
                            ),
                        ),
                    },
                ),
            ),
            400: openapi.Response(
                description="Paramètres invalides.",
            ),
            403: openapi.Response(
                description="Accès refusé.",
            ),
        },
    )
    def get(self, request):
        role = get_role_name(request.user)

        # =====================================================
        # 1. Période
        # =====================================================

        current_year = timezone.localdate().year

        periode = (
            request.query_params.get("periode")
            or "current_year"
        ).strip().lower()

        allowed_periodes = {
            "current_year",
            "3_years",
        }

        if periode not in allowed_periodes:
            raise ValidationError({
                "periode": (
                    "Valeur invalide. "
                    "Utiliser 'current_year' ou '3_years'."
                )
            })

        if periode == "current_year":
            start_year = current_year
        else:
            start_year = current_year - 2

        start_date = timezone.make_aware(
            datetime(
                start_year,
                1,
                1,
            ),
            timezone.get_current_timezone(),
        )

        # =====================================================
        # 2. Périmètre des bijouteries
        # =====================================================

        accessible_bijouterie_ids = None

        if role == ROLE_MANAGER:
            manager = getattr(
                request.user,
                "staff_manager_profile",
                None,
            )

            if (
                not manager
                or not getattr(
                    manager,
                    "verifie",
                    False,
                )
            ):
                accessible_bijouterie_ids = []

            else:
                bijouteries = getattr(
                    manager,
                    "bijouteries",
                    None,
                )

                accessible_bijouterie_ids = (
                    list(
                        bijouteries.values_list(
                            "id",
                            flat=True,
                        )
                    )
                    if bijouteries is not None
                    else []
                )

        # =====================================================
        # 3. Validation bijouterie_id
        # =====================================================

        raw_bijouterie_id = (
            request.query_params.get(
                "bijouterie_id"
            )
        )

        bijouterie_id = None

        if raw_bijouterie_id not in (
            None,
            "",
        ):
            try:
                bijouterie_id = int(
                    raw_bijouterie_id
                )

            except (
                TypeError,
                ValueError,
            ):
                raise ValidationError({
                    "bijouterie_id": (
                        "Ce paramètre doit être un entier."
                    )
                })

            if bijouterie_id <= 0:
                raise ValidationError({
                    "bijouterie_id": (
                        "Ce paramètre doit être "
                        "supérieur à zéro."
                    )
                })

            if not Bijouterie.objects.filter(
                pk=bijouterie_id
            ).exists():
                raise ValidationError({
                    "bijouterie_id": (
                        "Bijouterie introuvable."
                    )
                })

            if (
                accessible_bijouterie_ids
                is not None
                and bijouterie_id
                not in accessible_bijouterie_ids
            ):
                raise ValidationError({
                    "bijouterie_id": (
                        "Vous n'avez pas accès "
                        "à cette bijouterie."
                    )
                })

        # =====================================================
        # 4. Querysets de base
        # =====================================================

        # Achats :
        # période basée sur Achat.created_at.
        achats = Achat.objects.filter(
            created_at__gte=start_date,
            status=Achat.STATUS_CONFIRMED,
        )

        # Lots :
        # période basée sur Lot.received_at.
        lots = Lot.objects.filter(
            received_at__gte=start_date,
            achat__status=Achat.STATUS_CONFIRMED,
        )

        # ProduitLine :
        # période basée sur Lot.received_at.
        lignes = (
            ProduitLine.objects
            .filter(
                lot__received_at__gte=start_date,
                lot__achat__status=(
                    Achat.STATUS_CONFIRMED
                ),
            )
            .annotate(
                poids_ligne=ExpressionWrapper(
                    F("quantite")
                    * Coalesce(
                        F("produit__poids"),
                        Decimal("0.000"),
                    ),
                    output_field=DecimalField(
                        max_digits=18,
                        decimal_places=3,
                    ),
                )
            )
        )

        # =====================================================
        # 5. Périmètre manager
        # =====================================================

        if accessible_bijouterie_ids is not None:
            achats = achats.filter(
                bijouterie_id__in=(
                    accessible_bijouterie_ids
                )
            )

            lots = lots.filter(
                achat__bijouterie_id__in=(
                    accessible_bijouterie_ids
                )
            )

            lignes = lignes.filter(
                lot__achat__bijouterie_id__in=(
                    accessible_bijouterie_ids
                )
            )

        # =====================================================
        # 6. Filtre bijouterie
        # =====================================================

        if bijouterie_id is not None:
            achats = achats.filter(
                bijouterie_id=bijouterie_id
            )

            lots = lots.filter(
                achat__bijouterie_id=bijouterie_id
            )

            lignes = lignes.filter(
                lot__achat__bijouterie_id=(
                    bijouterie_id
                )
            )

        # =====================================================
        # 7. Statistiques globales
        # =====================================================

        total_achats = achats.count()

        montant_total = achats.aggregate(
            total=Coalesce(
                Sum("montant_total_ht"),
                Decimal("0.00"),
                output_field=DecimalField(
                    max_digits=18,
                    decimal_places=2,
                ),
            )
        )["total"]

        total_lots = lots.count()

        total_quantite = lignes.aggregate(
            total=Coalesce(
                Sum("quantite"),
                0,
            )
        )["total"]

        total_poids = lignes.aggregate(
            total=Coalesce(
                Sum("poids_ligne"),
                Decimal("0.000"),
                output_field=DecimalField(
                    max_digits=18,
                    decimal_places=3,
                ),
            )
        )["total"]

        # =====================================================
        # 8. Achats par année
        # =====================================================

        achats_par_annee_qs = (
            achats
            .annotate(
                annee=ExtractYear(
                    "created_at"
                )
            )
            .values(
                "annee"
            )
            .annotate(
                total_achats=Count(
                    "id"
                ),
                montant_total=Coalesce(
                    Sum(
                        "montant_total_ht"
                    ),
                    Decimal("0.00"),
                    output_field=DecimalField(
                        max_digits=18,
                        decimal_places=2,
                    ),
                ),
            )
            .order_by(
                "annee"
            )
        )

        # =====================================================
        # 9. Quantités reçues par année
        # =====================================================

        quantites_par_annee_qs = (
            lignes
            .annotate(
                annee=ExtractYear(
                    "lot__received_at"
                )
            )
            .values(
                "annee"
            )
            .annotate(
                total_quantite=Coalesce(
                    Sum("quantite"),
                    0,
                ),
                total_poids=Coalesce(
                    Sum("poids_ligne"),
                    Decimal("0.000"),
                    output_field=DecimalField(
                        max_digits=18,
                        decimal_places=3,
                    ),
                ),
            )
            .order_by(
                "annee"
            )
        )

        quantites_by_year = {
            row["annee"]: row
            for row in quantites_par_annee_qs
        }

        achats_par_annee = []

        for row in achats_par_annee_qs:
            annee = row["annee"]

            quantite_row = (
                quantites_by_year.get(
                    annee,
                    {},
                )
            )

            achats_par_annee.append({
                "annee": annee,
                "total_achats": (
                    row["total_achats"]
                ),
                "montant_total": (
                    row["montant_total"]
                ),
                "total_quantite": (
                    quantite_row.get(
                        "total_quantite",
                        0,
                    )
                ),
                "total_poids": (
                    quantite_row.get(
                        "total_poids",
                        Decimal("0.000"),
                    )
                ),
            })

        # =====================================================
        # 10. Top fournisseurs
        # =====================================================

        top_fournisseurs_qs = (
            achats
            .values(
                "fournisseur_id",
                "fournisseur__nom",
                "fournisseur__prenom",
                "fournisseur__telephone",
            )
            .annotate(
                total_achats=Count(
                    "id"
                ),
                montant_total=Coalesce(
                    Sum(
                        "montant_total_ht"
                    ),
                    Decimal("0.00"),
                    output_field=DecimalField(
                        max_digits=18,
                        decimal_places=2,
                    ),
                ),
            )
            .order_by(
                "-montant_total",
                "-total_achats",
            )[:5]
        )

        top_fournisseurs = []

        for row in top_fournisseurs_qs:
            fournisseur_nom = " ".join(
                part
                for part in [
                    row[
                        "fournisseur__prenom"
                    ],
                    row[
                        "fournisseur__nom"
                    ],
                ]
                if part
            )

            if not fournisseur_nom:
                fournisseur_nom = (
                    row[
                        "fournisseur__telephone"
                    ]
                    or "N/A"
                )

            top_fournisseurs.append({
                "fournisseur_id": (
                    row["fournisseur_id"]
                ),
                "fournisseur": (
                    fournisseur_nom
                ),
                "telephone": (
                    row[
                        "fournisseur__telephone"
                    ]
                ),
                "total_achats": (
                    row["total_achats"]
                ),
                "montant_total": (
                    row["montant_total"]
                ),
            })

        # =====================================================
        # 11. Produits reçus
        # =====================================================

        produits_qs = (
            lignes
            .values(
                "produit_id",
                "produit__nom",
                "produit__sku",
            )
            .annotate(
                quantite=Coalesce(
                    Sum("quantite"),
                    0,
                ),
                poids_total=Coalesce(
                    Sum("poids_ligne"),
                    Decimal("0.000"),
                    output_field=DecimalField(
                        max_digits=18,
                        decimal_places=3,
                    ),
                ),
            )
            .order_by(
                "-quantite",
                "-poids_total",
            )[:5]
        )

        repartition_produits = [
            {
                "produit_id": (
                    row["produit_id"]
                ),
                "produit": (
                    row["produit__nom"]
                    or "N/A"
                ),
                "sku": (
                    row["produit__sku"]
                ),
                "quantite": (
                    row["quantite"]
                ),
                "poids_total": (
                    row["poids_total"]
                ),
            }
            for row in produits_qs
        ]

        # =====================================================
        # 12. Réponse
        # =====================================================

        return Response(
            {
                "periode": {
                    "type": periode,
                    "start_year": start_year,
                    "end_year": current_year,
                    "label": (
                        str(current_year)
                        if periode == "current_year"
                        else (
                            f"{start_year}-"
                            f"{current_year}"
                        )
                    ),
                },

                "bijouterie_id": (
                    bijouterie_id
                ),

                "total_achats": (
                    total_achats
                ),

                "montant_total": (
                    montant_total
                ),

                "total_lots": (
                    total_lots
                ),

                "total_quantite": (
                    total_quantite
                ),

                "total_poids": (
                    total_poids
                ),

                "achats_par_annee": (
                    achats_par_annee
                ),

                "top_fournisseurs": (
                    top_fournisseurs
                ),

                "repartition_produits": (
                    repartition_produits
                ),
            },
            status=status.HTTP_200_OK,
        )
        

class FournisseurGetView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]

    @swagger_auto_schema(
        operation_summary="Récupérer un fournisseur",
        operation_description=(
            "Récupère les informations d'un fournisseur par son ID. "
            "Accès réservé aux administrateurs et managers."
        ),
        responses={
            200: FournisseurSerializer(),
            403: openapi.Response(
                description="Accès refusé."
            ),
            404: openapi.Response(
                description="Fournisseur introuvable."
            ),
        },
        tags=["Fournisseurs"],
    )
    def get(self, request, pk, format=None):
        fournisseur = get_object_or_404(
            Fournisseur,
            pk=pk,
        )

        serializer = FournisseurSerializer(
            fournisseur
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )


class FournisseurUpdateView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]

    @swagger_auto_schema(
        operation_summary="Mettre à jour complètement un fournisseur",
        operation_description=(
            "Met à jour complètement un fournisseur. "
            "Tous les champs requis doivent être fournis."
        ),
        request_body=FournisseurSerializer,
        responses={
            200: FournisseurSerializer(),
            400: openapi.Response(
                description="Requête invalide."
            ),
            403: openapi.Response(
                description="Accès refusé."
            ),
            404: openapi.Response(
                description="Fournisseur introuvable."
            ),
        },
        tags=["Fournisseurs"],
    )
    def put(self, request, pk, format=None):
        return self._update_fournisseur(
            request=request,
            pk=pk,
            partial=False,
        )

    @swagger_auto_schema(
        operation_summary="Mettre à jour partiellement un fournisseur",
        operation_description=(
            "Met à jour uniquement les champs fournis."
        ),
        request_body=FournisseurSerializer,
        responses={
            200: FournisseurSerializer(),
            400: openapi.Response(
                description="Requête invalide."
            ),
            403: openapi.Response(
                description="Accès refusé."
            ),
            404: openapi.Response(
                description="Fournisseur introuvable."
            ),
        },
        tags=["Fournisseurs"],
    )
    def patch(self, request, pk, format=None):
        return self._update_fournisseur(
            request=request,
            pk=pk,
            partial=True,
        )

    def _update_fournisseur(
        self,
        *,
        request,
        pk,
        partial,
    ):
        fournisseur = get_object_or_404(
            Fournisseur,
            pk=pk,
        )

        serializer = FournisseurSerializer(
            fournisseur,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
        

class FournisseurListView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]

    @swagger_auto_schema(
        operation_summary="Lister les fournisseurs",
        operation_description=(
            "Liste les fournisseurs. "
            "Le paramètre `search` permet une recherche par nom, "
            "prénom ou téléphone."
        ),
        manual_parameters=[
            openapi.Parameter(
                "search",
                openapi.IN_QUERY,
                description=(
                    "Recherche par nom, prénom ou téléphone."
                ),
                type=openapi.TYPE_STRING,
            ),
        ],
        responses={
            200: FournisseurSerializer(many=True),
            403: openapi.Response(
                description="Accès refusé."
            ),
        },
        tags=["Fournisseurs"],
    )
    def get(self, request):
        search = (
            request.query_params.get("search") or ""
        ).strip()

        fournisseurs = Fournisseur.objects.all()

        if search:
            fournisseurs = fournisseurs.filter(
                Q(nom__icontains=search)
                | Q(prenom__icontains=search)
                | Q(telephone__icontains=search)
            )

        fournisseurs = fournisseurs.order_by(
            "nom",
            "prenom",
            "id",
        )

        serializer = FournisseurSerializer(
            fournisseurs,
            many=True,
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
        

class AchatProduitGetOneView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]

    @swagger_auto_schema(
        operation_summary="Récupérer un achat",
        operation_description=(
            "Récupère un achat spécifique avec son fournisseur, "
            "sa bijouterie, ses lots et ses lignes produits.\n\n"
            "Périmètre :\n"
            "- admin : tous les achats ;\n"
            "- manager : uniquement les achats de ses bijouteries."
        ),
        responses={
            200: openapi.Response(
                description="Achat trouvé.",
                schema=AchatDetailSerializer,
            ),
            403: openapi.Response(
                description="Accès refusé."
            ),
            404: openapi.Response(
                description="Achat introuvable."
            ),
        },
        tags=["Achats / Arrivages"],
    )
    def get(self, request, pk):
        role = get_role_name(request.user)

        queryset = (
            Achat.objects
            .select_related(
                "fournisseur",
                "bijouterie",
            )
            .prefetch_related(
                "lots",
                "lots__lignes",
                "lots__lignes__produit",
                "lots__lignes__produit__categorie",
                "lots__lignes__produit__marque",
                "lots__lignes__produit__purete",
            )
        )

        # =====================================================
        # Périmètre manager
        # =====================================================

        if role == ROLE_MANAGER:
            manager = getattr(
                request.user,
                "staff_manager_profile",
                None,
            )

            if (
                not manager
                or not getattr(manager, "verifie", True)
            ):
                queryset = queryset.none()
            else:
                bijouteries = getattr(
                    manager,
                    "bijouteries",
                    None,
                )

                if bijouteries is None:
                    queryset = queryset.none()
                else:
                    queryset = queryset.filter(
                        bijouterie_id__in=bijouteries.values(
                            "id"
                        )
                    )

        achat = get_object_or_404(
            queryset,
            pk=pk,
        )

        serializer = AchatDetailSerializer(
            achat
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

class LotDetailView(RetrieveAPIView):
    """
    Détail d’un lot :

    - achat ;
    - fournisseur ;
    - bijouterie ;
    - frais ;
    - numéro du lot ;
    - lignes produits ;
    - quantité ;
    - prix d'achat par gramme.

    Périmètre :
    - admin : tous les lots ;
    - manager : uniquement les lots de ses bijouteries.
    """

    serializer_class = LotListSerializer
    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]
    lookup_field = "pk"

    @swagger_auto_schema(
        operation_id="detailLot",
        operation_summary="Afficher le détail d’un lot",
        operation_description=(
            "Retourne le détail d’un lot avec son achat, "
            "son fournisseur, sa bijouterie et ses lignes produits.\n\n"
            "L’administrateur peut consulter tous les lots. "
            "Le manager peut uniquement consulter les lots "
            "de ses bijouteries affectées."
        ),
        responses={
            200: LotListSerializer(),
            403: openapi.Response(
                description="Accès refusé."
            ),
            404: openapi.Response(
                description="Lot introuvable."
            ),
        },
        tags=["Achats / Arrivages"],
    )
    def get(self, request, *args, **kwargs):
        return super().get(
            request,
            *args,
            **kwargs,
        )

    def get_queryset(self):
        role = get_role_name(self.request.user)

        queryset = (
            Lot.objects
            .select_related(
                "achat",
                "achat__fournisseur",
                "achat__bijouterie",
            )
            .prefetch_related(
                "lignes",
                "lignes__produit",
                "lignes__produit__categorie",
                "lignes__produit__marque",
                "lignes__produit__purete",
                "lignes__produit__modele",
            )
        )

        if role == ROLE_ADMIN:
            return queryset

        if role == ROLE_MANAGER:
            manager = getattr(
                self.request.user,
                "staff_manager_profile",
                None,
            )

            if (
                not manager
                or not getattr(manager, "verifie", True)
            ):
                return queryset.none()

            bijouteries = getattr(
                manager,
                "bijouteries",
                None,
            )

            if bijouteries is None:
                return queryset.none()

            return queryset.filter(
                achat__bijouterie_id__in=(
                    bijouteries.values_list(
                        "id",
                        flat=True,
                    )
                )
            )

        return queryset.none()
    

# class ArrivageCreateView(APIView):
#     """
#     Crée un arrivage fournisseur.

#     Cycle :

#         Fournisseur
#             ↓
#         Achat
#             ↓
#         Lot
#             ↓
#         ProduitLine
#             ↓
#         Stock magasin
#             ↓
#         PURCHASE_IN : EXTERNAL → BIJOUTERIE

#     Cette vue ne crée jamais :
#     - de stock réserve ;
#     - de VendorStock ;
#     - de VENDOR_ASSIGN ;
#     - de SALE_OUT.

#     Périmètre :
#     - admin : toutes les bijouteries ;
#     - manager : uniquement ses bijouteries affectées.
#     """

#     permission_classes = [
#         IsAuthenticated,
#         IsAdminOrManager,
#     ]

#     http_method_names = [
#         "post",
#         "options",
#     ]

#     @swagger_auto_schema(
#         operation_id="createArrivage",
#         operation_summary=(
#             "Créer un arrivage fournisseur et initialiser "
#             "le stock de la bijouterie"
#         ),
#         operation_description=(
#             "Crée un achat fournisseur avec un ou plusieurs lots.\n\n"
#             "Pour chaque ProduitLine créée :\n"
#             "- un Stock magasin est initialisé ;\n"
#             "- un mouvement PURCHASE_IN est enregistré ;\n"
#             "- le mouvement va de EXTERNAL vers BIJOUTERIE.\n\n"
#             "Aucun VendorStock ni stock réserve n'est créé."
#         ),
#         request_body=ArrivageCreateInSerializer,
#         responses={
#             201: openapi.Response(
#                 description="Arrivage créé avec succès.",
#                 schema=ArrivageCreateResponseSerializer,
#             ),
#             400: openapi.Response(
#                 description="Données invalides.",
#             ),
#             401: openapi.Response(
#                 description="Authentification requise.",
#             ),
#             403: openapi.Response(
#                 description=(
#                     "Accès refusé ou bijouterie non autorisée."
#                 ),
#             ),
#         },
#         tags=["Achats / Arrivages"],
#     )
#     @transaction.atomic
#     def post(self, request):
#         serializer = ArrivageCreateInSerializer(
#             data=request.data
#         )
#         serializer.is_valid(raise_exception=True)

#         data = serializer.validated_data
#         lots_in = data.get("lots") or []

#         # =====================================================
#         # 1. Bijouterie
#         # =====================================================

#         bijouterie_id = data["bijouterie_id"]

#         try:
#             bijouterie = Bijouterie.objects.get(
#                 pk=bijouterie_id
#             )
#         except Bijouterie.DoesNotExist:
#             raise ValidationError({
#                 "bijouterie_id": "Bijouterie introuvable."
#             })

#         # =====================================================
#         # 2. Périmètre utilisateur
#         # =====================================================

#         role = get_role_name(request.user)

#         if role == ROLE_MANAGER:
#             manager = getattr(
#                 request.user,
#                 "staff_manager_profile",
#                 None,
#             )

#             if (
#                 not manager
#                 or not getattr(manager, "verifie", False)
#             ):
#                 raise PermissionDenied(
#                     "Profil manager introuvable ou désactivé."
#                 )

#             bijouteries_manager = getattr(
#                 manager,
#                 "bijouteries",
#                 None,
#             )

#             if (
#                 bijouteries_manager is None
#                 or not bijouteries_manager.filter(
#                     pk=bijouterie.pk
#                 ).exists()
#             ):
#                 raise PermissionDenied(
#                     "Vous ne pouvez pas créer un arrivage "
#                     "dans cette bijouterie."
#                 )

#         elif role != ROLE_ADMIN:
#             raise PermissionDenied(
#                 "Seuls les administrateurs et les managers "
#                 "peuvent créer un arrivage."
#             )

#         # =====================================================
#         # 3. Validation des lots
#         # =====================================================

#         if not lots_in:
#             raise ValidationError({
#                 "lots": "Au moins un lot est requis."
#             })

#         produit_ids = set()
#         lots_normalises = []

#         for lot_index, lot_in in enumerate(lots_in):
#             lignes_in = lot_in.get("lignes") or []

#             if not lignes_in:
#                 raise ValidationError({
#                     f"lots[{lot_index}].lignes": (
#                         "Chaque lot doit contenir "
#                         "au moins une ligne."
#                     )
#                 })

#             produits_du_lot = set()
#             lignes_normalisees = []

#             for ligne_index, ligne_in in enumerate(
#                 lignes_in
#             ):
#                 prefixe = (
#                     f"lots[{lot_index}]."
#                     f"lignes[{ligne_index}]"
#                 )

#                 produit_id = ligne_in.get("produit_id")

#                 if not produit_id:
#                     raise ValidationError({
#                         f"{prefixe}.produit_id": (
#                             "produit_id est obligatoire."
#                         )
#                     })

#                 if produit_id in produits_du_lot:
#                     raise ValidationError({
#                         f"{prefixe}.produit_id": (
#                             "Un produit ne peut apparaître "
#                             "qu'une seule fois dans un même lot."
#                         )
#                     })

#                 produits_du_lot.add(produit_id)
#                 produit_ids.add(produit_id)

#                 try:
#                     quantite = int(
#                         ligne_in.get("quantite")
#                     )
#                 except (TypeError, ValueError):
#                     raise ValidationError({
#                         f"{prefixe}.quantite": (
#                             "Quantité invalide."
#                         )
#                     })

#                 if quantite < 1:
#                     raise ValidationError({
#                         f"{prefixe}.quantite": (
#                             "La quantité doit être supérieure "
#                             "ou égale à 1."
#                         )
#                     })

#                 prix_brut = ligne_in.get(
#                     "prix_achat_gramme"
#                 )

#                 if prix_brut is None:
#                     raise ValidationError({
#                         f"{prefixe}.prix_achat_gramme": (
#                             "Le prix d'achat par gramme "
#                             "est obligatoire."
#                         )
#                     })

#                 try:
#                     prix_achat_gramme = Decimal(
#                         str(prix_brut)
#                     ).quantize(
#                         Decimal("0.01"),
#                         rounding=ROUND_HALF_UP,
#                     )
#                 except (
#                     InvalidOperation,
#                     TypeError,
#                     ValueError,
#                 ):
#                     raise ValidationError({
#                         f"{prefixe}.prix_achat_gramme": (
#                             "Prix d'achat par gramme invalide."
#                         )
#                     })

#                 if prix_achat_gramme < Decimal("0.00"):
#                     raise ValidationError({
#                         f"{prefixe}.prix_achat_gramme": (
#                             "Le prix d'achat par gramme "
#                             "ne peut pas être négatif."
#                         )
#                     })

#                 lignes_normalisees.append({
#                     "produit_id": produit_id,
#                     "quantite": quantite,
#                     "prix_achat_gramme": (
#                         prix_achat_gramme
#                     ),
#                 })

#             lots_normalises.append({
#                 "description": (
#                     lot_in.get("description")
#                     or data.get("description")
#                     or ""
#                 ),
#                 "received_at": lot_in.get(
#                     "received_at"
#                 ),
#                 "lignes": lignes_normalisees,
#             })

#         # =====================================================
#         # 4. Validation des produits
#         # =====================================================

#         produits = (
#             Produit.objects
#             .filter(pk__in=produit_ids)
#             .only(
#                 "id",
#                 "poids",
#             )
#         )

#         produits_by_id = {
#             produit.id: produit
#             for produit in produits
#         }

#         produits_manquants = (
#             produit_ids - set(produits_by_id)
#         )

#         if produits_manquants:
#             raise ValidationError({
#                 "lots": (
#                     "Produit(s) introuvable(s) : "
#                     f"{sorted(produits_manquants)}."
#                 )
#             })

#         produits_sans_poids = [
#             produit.id
#             for produit in produits_by_id.values()
#             if produit.poids is None
#         ]

#         if produits_sans_poids:
#             raise ValidationError({
#                 "lots": (
#                     "Produit(s) sans poids renseigné : "
#                     f"{sorted(produits_sans_poids)}."
#                 )
#             })

#         # =====================================================
#         # 5. Fournisseur
#         # =====================================================

#         fournisseur_data = data["fournisseur"]

#         telephone = (
#             fournisseur_data["telephone"]
#             or ""
#         ).strip()

#         if not telephone:
#             raise ValidationError({
#                 "fournisseur": {
#                     "telephone": (
#                         "Le téléphone du fournisseur "
#                         "est obligatoire."
#                     )
#                 }
#             })

#         fournisseur, _ = (
#             Fournisseur.objects.update_or_create(
#                 telephone=telephone,
#                 defaults={
#                     "nom": (
#                         fournisseur_data.get("nom")
#                         or ""
#                     ),
#                     "prenom": (
#                         fournisseur_data.get("prenom")
#                         or ""
#                     ),
#                     "address": (
#                         fournisseur_data.get("address")
#                         or ""
#                     ),
#                 },
#             )
#         )

#         # =====================================================
#         # 6. Création de l'achat
#         # =====================================================

#         achat = Achat.objects.create(
#             fournisseur=fournisseur,
#             bijouterie=bijouterie,
#             reference_commande=(
#                 data.get("reference_commande")
#                 or ""
#             ),
#             description=(
#                 data.get("description")
#                 or ""
#             ),
#             frais_transport=(
#                 data.get("frais_transport")
#                 or Decimal("0.00")
#             ),
#             frais_douane=(
#                 data.get("frais_douane")
#                 or Decimal("0.00")
#             ),
#             status=Achat.STATUS_CONFIRMED,
#         )

#         lots_created = []

#         # =====================================================
#         # 7. Lots, ProduitLine, Stock et PURCHASE_IN
#         # =====================================================

#         for lot_data in lots_normalises:
#             lot = None

#             for _ in range(5):
#                 try:
#                     lot = Lot.objects.create(
#                         achat=achat,
#                         numero_lot=(
#                             generate_numero_lot()
#                         ),
#                         description=(
#                             lot_data["description"]
#                         ),
#                         received_at=(
#                             lot_data["received_at"]
#                             or timezone.now()
#                         ),
#                     )
#                     break

#                 except IntegrityError:
#                     lot = None

#             if lot is None:
#                 raise ValidationError({
#                     "numero_lot": (
#                         "Impossible de générer un "
#                         "numéro de lot unique."
#                     )
#                 })

#             lots_created.append(lot)

#             for ligne in lot_data["lignes"]:
#                 produit = produits_by_id[
#                     ligne["produit_id"]
#                 ]

#                 quantite = ligne["quantite"]
#                 prix_achat_gramme = ligne[
#                     "prix_achat_gramme"
#                 ]

#                 produit_line = (
#                     ProduitLine.objects.create(
#                         lot=lot,
#                         produit=produit,
#                         quantite=quantite,
#                         prix_achat_gramme=(
#                             prix_achat_gramme
#                         ),
#                     )
#                 )

#                 Stock.objects.create(
#                     produit_line=produit_line,
#                     bijouterie=bijouterie,
#                     quantite_totale=quantite,
#                     en_stock=quantite,
#                 )

#                 log_move(
#                     produit=produit,
#                     qty=quantite,
#                     movement_type=(
#                         MovementType.PURCHASE_IN
#                     ),
#                     src_bucket=Bucket.EXTERNAL,
#                     dst_bucket=Bucket.BIJOUTERIE,
#                     dst_bijouterie_id=bijouterie.id,
#                     unit_cost=prix_achat_gramme,
#                     achat=achat,
#                     produit_line=produit_line,
#                     lot=lot,
#                     user=request.user,
#                     reason=(
#                         "Entrée fournisseur vers bijouterie"
#                     ),
#                 )

#         # =====================================================
#         # 8. Totaux définitifs
#         # =====================================================

#         achat.update_total(save=True)

#         achat.refresh_from_db(
#             fields=[
#                 "montant_total_ht",
#                 "montant_total_ttc",
#             ]
#         )

#         # =====================================================
#         # 9. Réponse
#         # =====================================================

#         payload = {
#             "achat": achat,
#             "lots": lots_created,
#         }

#         output = ArrivageCreateResponseSerializer(
#             payload
#         ).data

#         return Response(
#             output,
#             status=status.HTTP_201_CREATED,
#         )
        



class ArrivageCreateView(APIView):
    """
    Création d'un arrivage fournisseur.

    Cycle :

        Achat
        ↓
        Lot
        ↓
        ProduitLine
        ↓
        Stock bijouterie
        ↓
        PURCHASE_IN : EXTERNAL → BIJOUTERIE
    """

    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]

    http_method_names = [
        "post",
        "options",
    ]

    @swagger_auto_schema(
        operation_id="createArrivage",
        operation_summary=(
            "Créer un arrivage fournisseur"
        ),
        operation_description=(
            "Crée un achat fournisseur avec un ou plusieurs lots.\n\n"
            "Règles de bijouterie :\n"
            "- une seule bijouterie accessible : sélection automatique ;\n"
            "- plusieurs bijouteries : `bijouterie_id` obligatoire.\n\n"
            "Pour chaque ProduitLine :\n"
            "- création du Stock magasin ;\n"
            "- création d'un mouvement PURCHASE_IN ;\n"
            "- flux EXTERNAL → BIJOUTERIE.\n\n"
            "Aucun VendorStock ni système de réserve n'est créé."
        ),
        request_body=ArrivageCreateInSerializer,
        responses={
            201: openapi.Response(
                description=(
                    "Arrivage créé avec succès."
                ),
                schema=(
                    ArrivageCreateResponseSerializer
                ),
            ),
            400: openapi.Response(
                description="Données invalides.",
            ),
            401: openapi.Response(
                description=(
                    "Authentification requise."
                ),
            ),
            403: openapi.Response(
                description="Accès refusé.",
            ),
        },
        tags=[
            "Achats / Arrivages"
        ],
    )
    def post(self, request):
        serializer = (
            ArrivageCreateInSerializer(
                data=request.data
            )
        )

        serializer.is_valid(
            raise_exception=True
        )

        result = create_arrivage(
            user=request.user,
            validated_data=(
                serializer.validated_data
            ),
        )

        output = (
            ArrivageCreateResponseSerializer(
                result
            )
        )

        return Response(
            output.data,
            status=status.HTTP_201_CREATED,
        )


class LotListView(ListAPIView):
    """
    Liste des lots.

    Périmètre :
    - admin : tous les lots ;
    - manager : uniquement les lots de ses bijouteries.

    Filtrage des dates :
    - si date_from et date_to sont fournis :
      intervalle inclusif sur received_at ;
    - sinon :
      filtre par year ou année courante.

    Filtres :
    - year ;
    - date_from ;
    - date_to ;
    - reference_commande ;
    - numero_lot ;
    - numero_achat ;
    - fournisseur_id ;
    - ordering.
    """

    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]
    serializer_class = LotListSerializer
    pagination_class = None

    @swagger_auto_schema(
        operation_id="listLots",
        operation_summary="Lister les lots avec filtres",
        operation_description=(
            "Liste les lots selon le périmètre de l'utilisateur.\n\n"
            "Périmètre :\n"
            "- admin : tous les lots ;\n"
            "- manager : lots de ses bijouteries uniquement.\n\n"
            "Priorité du filtre de période :\n"
            "- si `date_from` et `date_to` sont fournis, "
            "l'intervalle est appliqué sur `received_at` ;\n"
            "- sinon, `year` est utilisé ;\n"
            "- si `year` est absent, l'année courante est utilisée.\n\n"
            "Formats :\n"
            "- dates : `YYYY-MM-DD` ;\n"
            "- année : `YYYY`.\n\n"
            "Exemples :\n"
            "- `/api/lots/?year=2026`\n"
            "- `/api/lots/?date_from=2026-01-01&date_to=2026-01-31`\n"
            "- `/api/lots/?reference_commande=CMD-2026`"
        ),
        manual_parameters=[
            openapi.Parameter(
                "year",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                description=(
                    "Année de réception, par exemple 2026. "
                    "Ignorée si date_from et date_to sont fournis."
                ),
            ),
            openapi.Parameter(
                "reference_commande",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description=(
                    "Recherche partielle sur la référence de commande."
                ),
            ),
            openapi.Parameter(
                "date_from",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description=(
                    "Date minimale incluse au format YYYY-MM-DD. "
                    "Doit être utilisée avec date_to."
                ),
            ),
            openapi.Parameter(
                "date_to",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description=(
                    "Date maximale incluse au format YYYY-MM-DD. "
                    "Doit être utilisée avec date_from."
                ),
            ),
            openapi.Parameter(
                "numero_lot",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description=(
                    "Recherche partielle sur le numéro du lot."
                ),
            ),
            openapi.Parameter(
                "numero_achat",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description=(
                    "Filtre exact sur le numéro de l'achat."
                ),
            ),
            openapi.Parameter(
                "fournisseur_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                description="Filtre par fournisseur.",
            ),
            openapi.Parameter(
                "ordering",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description=(
                    "Tri autorisé : -received_at, received_at, "
                    "numero_lot, -numero_lot."
                ),
            ),
        ],
        responses={
            200: LotListSerializer(many=True),
            400: openapi.Response(
                description="Paramètres de filtrage invalides."
            ),
            403: openapi.Response(
                description="Accès refusé."
            ),
        },
        tags=["Achats / Arrivages"],
    )
    def get(self, request, *args, **kwargs):
        self._validate_query_params()
        return super().get(request, *args, **kwargs)

    def _parse_date(self, field_name, value):
        if not value:
            return None

        try:
            return datetime.strptime(
                value,
                "%Y-%m-%d",
            ).date()

        except (TypeError, ValueError):
            raise ValidationError({
                field_name: (
                    "Format invalide. Utiliser YYYY-MM-DD."
                )
            })

    def _parse_positive_integer(
        self,
        *,
        field_name,
        value,
        required=False,
    ):
        if value in (None, ""):
            if required:
                raise ValidationError({
                    field_name: "Ce paramètre est obligatoire."
                })

            return None

        try:
            parsed_value = int(value)

        except (TypeError, ValueError):
            raise ValidationError({
                field_name: "Une valeur entière est attendue."
            })

        if parsed_value < 1:
            raise ValidationError({
                field_name: (
                    "La valeur doit être supérieure ou égale à 1."
                )
            })

        return parsed_value

    def _validate_query_params(self):
        query_params = self.request.query_params

        date_from_value = query_params.get("date_from")
        date_to_value = query_params.get("date_to")

        date_from = self._parse_date(
            "date_from",
            date_from_value,
        )
        date_to = self._parse_date(
            "date_to",
            date_to_value,
        )

        if bool(date_from) != bool(date_to):
            raise ValidationError({
                "detail": (
                    "Fournir date_from et date_to ensemble."
                )
            })

        if (
            date_from
            and date_to
            and date_from > date_to
        ):
            raise ValidationError({
                "detail": (
                    "date_from doit être inférieure "
                    "ou égale à date_to."
                )
            })

        year_value = query_params.get("year")

        if year_value:
            year = self._parse_positive_integer(
                field_name="year",
                value=year_value,
            )

            if year < 1900 or year > 9999:
                raise ValidationError({
                    "year": "Année invalide."
                })

        fournisseur_id = query_params.get(
            "fournisseur_id"
        )

        if fournisseur_id:
            self._parse_positive_integer(
                field_name="fournisseur_id",
                value=fournisseur_id,
            )

    def get_queryset(self):
        query_params = self.request.query_params

        ordering = (
            query_params.get("ordering")
            or "-received_at"
        ).strip()

        allowed_ordering = {
            "received_at",
            "-received_at",
            "numero_lot",
            "-numero_lot",
        }

        if ordering not in allowed_ordering:
            ordering = "-received_at"

        queryset = (
            Lot.objects
            .select_related(
                "achat",
                "achat__fournisseur",
                "achat__bijouterie",
            )
            .prefetch_related(
                "lignes",
                "lignes__produit",
                "lignes__produit__categorie",
                "lignes__produit__marque",
                "lignes__produit__modele",
                "lignes__produit__purete",
            )
            .annotate(
                nb_lignes=Coalesce(
                    Count(
                        "lignes",
                        distinct=True,
                    ),
                    0,
                ),
                quantite_totale=Coalesce(
                    Sum("lignes__quantite"),
                    0,
                ),
            )
        )

        # =====================================================
        # Périmètre utilisateur
        # Admin : tout
        # Manager : uniquement ses bijouteries
        # =====================================================

        queryset = scope_queryset_by_bijouterie(
            queryset,
            user=self.request.user,
            field="achat__bijouterie_id",
        )

        # =====================================================
        # Filtre dates ou année
        # =====================================================

        date_from_value = query_params.get("date_from")
        date_to_value = query_params.get("date_to")

        if date_from_value and date_to_value:
            date_from = self._parse_date(
                "date_from",
                date_from_value,
            )
            date_to = self._parse_date(
                "date_to",
                date_to_value,
            )

            queryset = queryset.filter(
                received_at__date__range=(
                    date_from,
                    date_to,
                )
            )

        else:
            year_value = query_params.get("year")

            if year_value:
                year = int(year_value)
            else:
                year = timezone.localdate().year

            queryset = queryset.filter(
                received_at__year=year
            )

        # =====================================================
        # Autres filtres
        # =====================================================

        reference_commande = (
            query_params.get("reference_commande")
            or ""
        ).strip()

        if reference_commande:
            queryset = queryset.filter(
                achat__reference_commande__icontains=(
                    reference_commande
                )
            )

        numero_lot = (
            query_params.get("numero_lot")
            or ""
        ).strip()

        if numero_lot:
            queryset = queryset.filter(
                numero_lot__icontains=numero_lot
            )

        numero_achat = (
            query_params.get("numero_achat")
            or ""
        ).strip()

        if numero_achat:
            queryset = queryset.filter(
                achat__numero_achat=numero_achat
            )

        fournisseur_id = query_params.get(
            "fournisseur_id"
        )

        if fournisseur_id:
            queryset = queryset.filter(
                achat__fournisseur_id=int(
                    fournisseur_id
                )
            )

        return queryset.order_by(ordering)



class AchatListView(ListAPIView):
    """
    Liste des achats.

    Périmètre :
    - admin : tous les achats ;
    - manager : uniquement les achats de ses bijouteries.

    Filtrage des dates :
    - si date_from et date_to sont fournis :
      intervalle inclusif sur created_at ;
    - sinon :
      filtre par year ou année courante.

    Filtres :
    - year ;
    - date_from ;
    - date_to ;
    - reference_commande ;
    - numero_achat ;
    - fournisseur_id ;
    - status ;
    - ordering.
    """

    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]
    serializer_class = AchatOutSerializer
    pagination_class = None

    @swagger_auto_schema(
        operation_id="listAchats",
        operation_summary=(
            "Lister les achats par année ou entre deux dates"
        ),
        operation_description=(
            "Liste les achats selon le périmètre de l'utilisateur.\n\n"
            "Périmètre :\n"
            "- admin : tous les achats ;\n"
            "- manager : achats de ses bijouteries uniquement.\n\n"
            "Priorité du filtre de période :\n"
            "- si `date_from` et `date_to` sont fournis, "
            "l'intervalle est appliqué sur `created_at` ;\n"
            "- sinon, `year` est utilisé ;\n"
            "- si `year` est absent, l'année courante est utilisée.\n\n"
            "Formats :\n"
            "- dates : `YYYY-MM-DD` ;\n"
            "- année : `YYYY`."
        ),
        manual_parameters=[
            openapi.Parameter(
                "year",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                description=(
                    "Année de création, par exemple 2026. "
                    "Ignorée si date_from et date_to sont fournis."
                ),
            ),
            openapi.Parameter(
                "reference_commande",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description=(
                    "Recherche partielle sur la référence de commande."
                ),
            ),
            openapi.Parameter(
                "numero_achat",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description=(
                    "Filtre exact sur le numéro de l'achat."
                ),
            ),
            openapi.Parameter(
                "fournisseur_id",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                description="Filtre par fournisseur.",
            ),
            openapi.Parameter(
                "status",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description=(
                    "Statut de l'achat, par exemple "
                    "`confirmed` ou `cancelled`."
                ),
            ),
            openapi.Parameter(
                "date_from",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description=(
                    "Date minimale incluse au format YYYY-MM-DD. "
                    "Doit être utilisée avec date_to."
                ),
            ),
            openapi.Parameter(
                "date_to",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description=(
                    "Date maximale incluse au format YYYY-MM-DD. "
                    "Doit être utilisée avec date_from."
                ),
            ),
            openapi.Parameter(
                "ordering",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description=(
                    "Tri autorisé : -created_at, created_at, "
                    "numero_achat, -numero_achat."
                ),
            ),
        ],
        responses={
            200: AchatOutSerializer(many=True),
            400: openapi.Response(
                description="Paramètres de filtrage invalides."
            ),
            403: openapi.Response(
                description="Accès refusé."
            ),
        },
        tags=["Achats / Arrivages"],
    )
    def get(self, request, *args, **kwargs):
        self._validate_query_params()
        return super().get(request, *args, **kwargs)

    def _parse_date(self, field_name, value):
        if not value:
            return None

        try:
            return datetime.strptime(
                value,
                "%Y-%m-%d",
            ).date()

        except (TypeError, ValueError):
            raise ValidationError({
                field_name: (
                    "Format invalide. Utiliser YYYY-MM-DD."
                )
            })

    def _parse_positive_integer(
        self,
        *,
        field_name,
        value,
    ):
        if value in (None, ""):
            return None

        try:
            parsed_value = int(value)

        except (TypeError, ValueError):
            raise ValidationError({
                field_name: "Une valeur entière est attendue."
            })

        if parsed_value < 1:
            raise ValidationError({
                field_name: (
                    "La valeur doit être supérieure ou égale à 1."
                )
            })

        return parsed_value

    def _allowed_statuses(self):
        """
        Récupère les statuts directement depuis le modèle si possible.

        Compatible avec :
        - Achat.STATUS_CONFIRMED ;
        - Achat.STATUS_CANCELLED ;
        - Achat.STATUS_CHOICES ;
        - un champ utilisant TextChoices.
        """

        model_field = Achat._meta.get_field("status")

        if model_field.choices:
            return {
                str(value)
                for value, _label in model_field.choices
            }

        allowed = set()

        confirmed = getattr(
            Achat,
            "STATUS_CONFIRMED",
            None,
        )
        cancelled = getattr(
            Achat,
            "STATUS_CANCELLED",
            None,
        )

        if confirmed:
            allowed.add(str(confirmed))

        if cancelled:
            allowed.add(str(cancelled))

        return allowed

    def _validate_query_params(self):
        query_params = self.request.query_params

        date_from_value = query_params.get("date_from")
        date_to_value = query_params.get("date_to")

        date_from = self._parse_date(
            "date_from",
            date_from_value,
        )
        date_to = self._parse_date(
            "date_to",
            date_to_value,
        )

        if bool(date_from) != bool(date_to):
            raise ValidationError({
                "detail": (
                    "Fournir date_from et date_to ensemble."
                )
            })

        if (
            date_from
            and date_to
            and date_from > date_to
        ):
            raise ValidationError({
                "detail": (
                    "date_from doit être inférieure "
                    "ou égale à date_to."
                )
            })

        year_value = query_params.get("year")

        if year_value:
            year = self._parse_positive_integer(
                field_name="year",
                value=year_value,
            )

            if year < 1900 or year > 9999:
                raise ValidationError({
                    "year": "Année invalide."
                })

        fournisseur_id = query_params.get(
            "fournisseur_id"
        )

        if fournisseur_id:
            self._parse_positive_integer(
                field_name="fournisseur_id",
                value=fournisseur_id,
            )

        status_value = (
            query_params.get("status")
            or ""
        ).strip()

        if status_value:
            allowed_statuses = self._allowed_statuses()

            if (
                allowed_statuses
                and status_value not in allowed_statuses
            ):
                raise ValidationError({
                    "status": (
                        "Statut invalide. Valeurs autorisées : "
                        f"{sorted(allowed_statuses)}."
                    )
                })

    def get_queryset(self):
        query_params = self.request.query_params

        # =====================================================
        # Tri
        # =====================================================

        ordering = (
            query_params.get("ordering")
            or "-created_at"
        ).strip()

        allowed_ordering = {
            "created_at",
            "-created_at",
            "numero_achat",
            "-numero_achat",
        }

        if ordering not in allowed_ordering:
            ordering = "-created_at"

        # =====================================================
        # Base queryset
        # =====================================================

        queryset = (
            Achat.objects
            .select_related(
                "fournisseur",
                "bijouterie",
            )
            .prefetch_related(
                "lots",
                "lots__lignes",
                "lots__lignes__produit",
                "lots__lignes__produit__categorie",
                "lots__lignes__produit__marque",
                "lots__lignes__produit__modele",
                "lots__lignes__produit__purete",
            )
        )

        # =====================================================
        # Périmètre utilisateur
        # Admin : tout
        # Manager : uniquement ses bijouteries
        # =====================================================

        queryset = scope_queryset_by_bijouterie(
            queryset,
            user=self.request.user,
            field="bijouterie_id",
        )

        # =====================================================
        # Filtre dates ou année
        # =====================================================

        date_from_value = query_params.get("date_from")
        date_to_value = query_params.get("date_to")

        if date_from_value and date_to_value:
            date_from = self._parse_date(
                "date_from",
                date_from_value,
            )
            date_to = self._parse_date(
                "date_to",
                date_to_value,
            )

            queryset = queryset.filter(
                created_at__date__range=(
                    date_from,
                    date_to,
                )
            )

        else:
            year_value = query_params.get("year")

            if year_value:
                year = int(year_value)
            else:
                year = timezone.localdate().year

            queryset = queryset.filter(
                created_at__year=year
            )

        # =====================================================
        # Filtres optionnels
        # =====================================================

        reference_commande = (
            query_params.get("reference_commande")
            or ""
        ).strip()

        if reference_commande:
            queryset = queryset.filter(
                reference_commande__icontains=(
                    reference_commande
                )
            )

        numero_achat = (
            query_params.get("numero_achat")
            or ""
        ).strip()

        if numero_achat:
            queryset = queryset.filter(
                numero_achat=numero_achat
            )

        fournisseur_id = query_params.get(
            "fournisseur_id"
        )

        if fournisseur_id:
            queryset = queryset.filter(
                fournisseur_id=int(
                    fournisseur_id
                )
            )

        status_value = (
            query_params.get("status")
            or ""
        ).strip()

        if status_value:
            queryset = queryset.filter(
                status=status_value
            )

        return queryset.order_by(ordering)
    


class ArrivageMetaUpdateView(APIView):
    """
    Met à jour uniquement les informations documentaires
    d'un arrivage.

    Achat :
    - description ;
    - frais_transport ;
    - frais_douane ;
    - fournisseur.

    Lot :
    - description ;
    - received_at.

    Cette vue ne modifie jamais :
    - Stock ;
    - VendorStock ;
    - InventoryMovement ;
    - les quantités des ProduitLine.
    """

    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]
    http_method_names = [
        "patch",
        "options",
    ]

    @swagger_auto_schema(
        operation_id="arrivageMetaUpdate",
        operation_summary=(
            "Mettre à jour les métadonnées d'un arrivage"
        ),
        operation_description=(
            "Permet de corriger ou compléter les informations "
            "documentaires d'un arrivage.\n\n"
            "Champs modifiables côté achat :\n"
            "- `description` ;\n"
            "- `frais_transport` ;\n"
            "- `frais_douane` ;\n"
            "- `fournisseur` par identifiant ou téléphone.\n\n"
            "Champs modifiables côté lot :\n"
            "- `description` ;\n"
            "- `received_at`.\n\n"
            "Cette opération ne modifie ni le stock ni les "
            "mouvements d'inventaire."
        ),
        request_body=ArrivageMetaUpdateInSerializer,
        responses={
            200: ArrivageCreateResponseSerializer,
            400: openapi.Response(
                description="Données invalides."
            ),
            401: openapi.Response(
                description="Authentification requise."
            ),
            403: openapi.Response(
                description="Accès refusé."
            ),
            404: openapi.Response(
                description="Lot ou fournisseur introuvable."
            ),
        },
        tags=["Achats / Arrivages"],
        manual_parameters=[
            openapi.Parameter(
                "lot_id",
                in_=openapi.IN_PATH,
                type=openapi.TYPE_INTEGER,
                description="Identifiant du lot concerné.",
                required=True,
            ),
        ],
    )
    @transaction.atomic
    def patch(self, request, lot_id: int, *args, **kwargs):
        # =====================================================
        # Périmètre utilisateur
        # Admin : tous les lots
        # Manager : lots de ses bijouteries uniquement
        # =====================================================

        queryset = (
            Lot.objects
            .select_related(
                "achat",
                "achat__fournisseur",
                "achat__bijouterie",
            )
            .prefetch_related(
                "lignes",
                "lignes__produit",
            )
        )

        queryset = scope_queryset_by_bijouterie(
            queryset,
            user=request.user,
            field="achat__bijouterie_id",
        )

        lot = get_object_or_404(
            queryset,
            pk=lot_id,
        )

        achat: Achat = lot.achat

        # =====================================================
        # Validation
        # =====================================================

        serializer = ArrivageMetaUpdateInSerializer(
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data

        achat_data = validated_data.get("achat")
        lot_data = validated_data.get("lot")

        # =====================================================
        # Mise à jour Achat
        # =====================================================

        update_achat_fields = []

        if achat_data is not None:
            if "description" in achat_data:
                achat.description = (
                    achat_data.get("description") or ""
                )
                update_achat_fields.append("description")

            if "frais_transport" in achat_data:
                achat.frais_transport = achat_data[
                    "frais_transport"
                ]
                update_achat_fields.append("frais_transport")

            if "frais_douane" in achat_data:
                achat.frais_douane = achat_data[
                    "frais_douane"
                ]
                update_achat_fields.append("frais_douane")

            if "fournisseur" in achat_data:
                fournisseur_data = (
                    achat_data.get("fournisseur")
                )

                if fournisseur_data:
                    fournisseur = self._resolve_fournisseur(
                        fournisseur_data
                    )

                    if achat.fournisseur_id != fournisseur.id:
                        achat.fournisseur = fournisseur
                        update_achat_fields.append(
                            "fournisseur"
                        )

            if update_achat_fields:
                achat.full_clean()

                achat.save(
                    update_fields=list(
                        dict.fromkeys(update_achat_fields)
                    )
                )

        # =====================================================
        # Mise à jour Lot
        # =====================================================

        update_lot_fields = []

        if lot_data is not None:
            if "description" in lot_data:
                lot.description = (
                    lot_data.get("description") or ""
                )
                update_lot_fields.append("description")

            if "received_at" in lot_data:
                lot.received_at = lot_data["received_at"]
                update_lot_fields.append("received_at")

            if update_lot_fields:
                lot.full_clean()

                lot.save(
                    update_fields=list(
                        dict.fromkeys(update_lot_fields)
                    )
                )

        # =====================================================
        # Recalcul financier
        # Seulement si les frais de l'achat ont changé
        # =====================================================

        financial_fields = {
            "frais_transport",
            "frais_douane",
        }

        if financial_fields.intersection(
            update_achat_fields
        ):
            achat.update_total(save=True)

        # =====================================================
        # Réponse actualisée
        # =====================================================

        lot.refresh_from_db()
        achat.refresh_from_db()

        payload = {
            "achat": achat,
            "lots": [lot],
        }

        output = ArrivageCreateResponseSerializer(
            payload
        )

        return Response(
            output.data,
            status=status.HTTP_200_OK,
        )

    def _resolve_fournisseur(
            self,
            fournisseur_data,
        ) -> Fournisseur:
            """
            Résout le fournisseur selon les règles suivantes :

            - si `id` est fourni : récupère le fournisseur existant ;
            - sinon : le téléphone est obligatoire ;
            - le téléphone sert de clé métier ;
            - si le téléphone existe déjà, le fournisseur est mis à jour ;
            - sinon, un nouveau fournisseur est créé.
            """

            fournisseur_id = fournisseur_data.get("id")

            if fournisseur_id:
                return get_object_or_404(
                    Fournisseur,
                    pk=fournisseur_id,
                )

            telephone = (
                fournisseur_data.get("telephone")
                or ""
            ).strip()

            if not telephone:
                raise ValidationError({
                    "fournisseur": {
                        "telephone": (
                            "Le téléphone du fournisseur est obligatoire."
                        )
                    }
                })

            nom = (
                fournisseur_data.get("nom")
                or ""
            ).strip()

            if not nom:
                raise ValidationError({
                    "fournisseur": {
                        "nom": (
                            "Le nom du fournisseur est obligatoire."
                        )
                    }
                })

            defaults = {
                "nom": nom,
                "prenom": (
                    fournisseur_data.get("prenom")
                    or ""
                ).strip(),
                "address": (
                    fournisseur_data.get("address")
                    or ""
                ).strip(),
            }

            fournisseur, _created = (
                Fournisseur.objects.update_or_create(
                    telephone=telephone,
                    defaults=defaults,
                )
            )

            return fournisseur


# ------------------------- InventoryPhotoView -------------------------
# class InventoryPhotoView(ExportXlsxMixin, ListAPIView):
#     """
#     Photo instantanée du stock présent dans les bijouteries.

#     Cette vue affiche, pour chaque ProduitLine :

#     - l'achat fournisseur ;
#     - le lot ;
#     - le produit ;
#     - la bijouterie de réception ;
#     - la quantité initialement reçue ;
#     - la quantité totale rattachée au stock magasin ;
#     - la quantité actuellement disponible en magasin.

#     Nouveau cycle respecté :

#         PURCHASE_IN
#         EXTERNAL → BIJOUTERIE

#     Cette vue ne gère jamais :

#     - de stock réserve ;
#     - de Stock avec bijouterie=None ;
#     - de VendorStock ;
#     - les quantités actuellement chez les vendeurs.
#     """

#     permission_classes = [
#         IsAuthenticated,
#         IsAdminOrManager,
#     ]

#     serializer_class = ProduitLineMiniSerializer
#     pagination_class = None

#     @swagger_auto_schema(
#         operation_id="listProduitLinesInventoryPhoto",
#         operation_summary=(
#             "Afficher la photo instantanée du stock des bijouteries"
#         ),
#         operation_description=(
#             "Retourne les ProduitLine avec leur achat, leur lot, "
#             "leur produit et les quantités actuellement présentes "
#             "dans les stocks des bijouteries.\n\n"
#             "Cette vue respecte le cycle :\n"
#             "`PURCHASE_IN : EXTERNAL → BIJOUTERIE`.\n\n"
#             "Elle ne contient aucune logique de réserve.\n\n"
#             "Filtres disponibles :\n"
#             "- `year`\n"
#             "- `bijouterie_id`\n"
#             "- `reference_commande`\n"
#             "- `lot_id`\n"
#             "- `produit_id`\n"
#             "- `numero_lot`\n"
#             "- `numero_achat`\n"
#             "- `fournisseur_id`\n"
#             "- `en_stock_only`\n"
#             "- `ordering`\n\n"
#             "Export Excel : `?export=xlsx`."
#         ),
#         manual_parameters=[
#             openapi.Parameter(
#                 "year",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_INTEGER,
#                 description=(
#                     "Année de réception du lot. "
#                     "Par défaut : année courante."
#                 ),
#             ),
#             openapi.Parameter(
#                 "bijouterie_id",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_INTEGER,
#                 description=(
#                     "Filtre le stock d'une bijouterie précise."
#                 ),
#             ),
#             openapi.Parameter(
#                 "reference_commande",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description=(
#                     "Recherche partielle sur la référence "
#                     "de commande."
#                 ),
#             ),
#             openapi.Parameter(
#                 "lot_id",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_INTEGER,
#                 description="Filtre exact sur le lot.",
#             ),
#             openapi.Parameter(
#                 "produit_id",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_INTEGER,
#                 description="Filtre exact sur le produit.",
#             ),
#             openapi.Parameter(
#                 "numero_lot",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description=(
#                     "Recherche partielle sur le numéro du lot."
#                 ),
#             ),
#             openapi.Parameter(
#                 "numero_achat",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description=(
#                     "Filtre exact sur le numéro d'achat."
#                 ),
#             ),
#             openapi.Parameter(
#                 "fournisseur_id",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_INTEGER,
#                 description="Filtre exact sur le fournisseur.",
#             ),
#             openapi.Parameter(
#                 "en_stock_only",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_INTEGER,
#                 description=(
#                     "1 = afficher uniquement les lignes ayant "
#                     "encore du stock disponible en magasin."
#                 ),
#             ),
#             openapi.Parameter(
#                 "ordering",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description=(
#                     "Tri autorisé : received_at, -received_at, "
#                     "id, -id, en_stock, -en_stock."
#                 ),
#             ),
#             openapi.Parameter(
#                 "export",
#                 openapi.IN_QUERY,
#                 type=openapi.TYPE_STRING,
#                 description="Utiliser xlsx pour exporter.",
#             ),
#         ],
#         responses={
#             200: ProduitLineMiniSerializer(many=True),
#             400: openapi.Response(
#                 description="Paramètres invalides."
#             ),
#             401: openapi.Response(
#                 description="Non authentifié."
#             ),
#             403: openapi.Response(
#                 description="Accès refusé."
#             ),
#         },
#         tags=["Inventaire"],
#     )
#     def get(self, request, *args, **kwargs):
#         self._validate_query_params(request)

#         return super().get(
#             request,
#             *args,
#             **kwargs,
#         )

#     # ============================================================
#     # Validation
#     # ============================================================

#     def _parse_positive_integer(
#         self,
#         *,
#         value,
#         field_name,
#     ):
#         if value in (None, ""):
#             return None

#         try:
#             parsed_value = int(value)

#         except (TypeError, ValueError):
#             raise ValidationError({
#                 field_name: (
#                     "Ce paramètre doit être un entier."
#                 )
#             })

#         if parsed_value <= 0:
#             raise ValidationError({
#                 field_name: (
#                     "Ce paramètre doit être supérieur à zéro."
#                 )
#             })

#         return parsed_value

#     def _parse_year(self, value):
#         if value in (None, ""):
#             return timezone.localdate().year

#         try:
#             year = int(value)

#         except (TypeError, ValueError):
#             raise ValidationError({
#                 "year": "Année invalide. Exemple : 2026."
#             })

#         if year < 2000 or year > 2100:
#             raise ValidationError({
#                 "year": (
#                     "L'année doit être comprise entre "
#                     "2000 et 2100."
#                 )
#             })

#         return year

#     def _validate_query_params(self, request):
#         query_params = request.query_params

#         self._parse_year(
#             query_params.get("year")
#         )

#         integer_fields = (
#             "bijouterie_id",
#             "lot_id",
#             "produit_id",
#             "fournisseur_id",
#         )

#         for field_name in integer_fields:
#             self._parse_positive_integer(
#                 value=query_params.get(field_name),
#                 field_name=field_name,
#             )

#         en_stock_only = query_params.get(
#             "en_stock_only"
#         )

#         if en_stock_only not in (
#             None,
#             "",
#             "0",
#             "1",
#         ):
#             raise ValidationError({
#                 "en_stock_only": (
#                     "Utiliser 1 pour oui ou 0 pour non."
#                 )
#             })

#         ordering = (
#             query_params.get("ordering")
#             or "-received_at"
#         ).strip()

#         allowed_ordering = {
#             "received_at",
#             "-received_at",
#             "id",
#             "-id",
#             "en_stock",
#             "-en_stock",
#         }

#         if ordering not in allowed_ordering:
#             raise ValidationError({
#                 "ordering": (
#                     "Tri invalide. Valeurs autorisées : "
#                     "received_at, -received_at, id, -id, "
#                     "en_stock, -en_stock."
#                 )
#             })

#         export_format = (
#             query_params.get("export")
#             or ""
#         ).strip().lower()

#         if export_format not in ("", "xlsx"):
#             raise ValidationError({
#                 "export": (
#                     "Format invalide. Utiliser xlsx."
#                 )
#             })

#     # ============================================================
#     # Périmètre accessible
#     # ============================================================

#     def _get_accessible_bijouteries(self):
#         """
#         Retourne le queryset des bijouteries accessibles :

#         - admin : toutes les bijouteries ;
#         - manager : uniquement ses bijouteries ;
#         - autre rôle : queryset vide.
#         """

#         queryset = Bijouterie.objects.all()

#         queryset = scope_queryset_by_bijouterie(
#             queryset,
#             user=self.request.user,
#             field="lot__achat__bijouterie_id",
#         )

#     def _resolve_bijouterie_id(self):
#         """
#         Vérifie que la bijouterie demandée existe
#         et appartient au périmètre de l'utilisateur.
#         """

#         bijouterie_id = self._parse_positive_integer(
#             value=self.request.query_params.get(
#                 "bijouterie_id"
#             ),
#             field_name="bijouterie_id",
#         )

#         if bijouterie_id is None:
#             return None

#         accessible_bijouteries = (
#             self._get_accessible_bijouteries()
#         )

#         if not accessible_bijouteries.filter(
#             pk=bijouterie_id
#         ).exists():
#             raise ValidationError({
#                 "bijouterie_id": (
#                     "Bijouterie introuvable ou non accessible."
#                 )
#             })

#         return bijouterie_id

#     # ============================================================
#     # Queryset
#     # ============================================================

#     def get_queryset(self):
#         query_params = self.request.query_params
#         get_param = query_params.get

#         year = self._parse_year(
#             get_param("year")
#         )

#         bijouterie_id = self._resolve_bijouterie_id()

#         # ========================================================
#         # Queryset principal
#         # ========================================================

#         queryset = (
#             ProduitLine.objects
#             .select_related(
#                 "lot",
#                 "lot__achat",
#                 "lot__achat__bijouterie",
#                 "lot__achat__fournisseur",
#                 "produit",
#                 "produit__categorie",
#                 "produit__marque",
#                 "produit__modele",
#                 "produit__purete",
#             )
#             .filter(
#                 lot__received_at__year=year,
#                 lot__achat__status=Achat.STATUS_CONFIRMED,
#             )
#         )

#         # ========================================================
#         # Périmètre utilisateur
#         #
#         # Admin :
#         #     toutes les ProduitLine.
#         #
#         # Manager :
#         #     uniquement les ProduitLine reçues dans
#         #     ses bijouteries.
#         # ========================================================

#         queryset = scope_queryset_by_bijouterie(
#             queryset,
#             self.request.user,
#             field="lot__achat__bijouterie_id",
#         )

#         # ========================================================
#         # Filtre explicite de bijouterie
#         # ========================================================

#         if bijouterie_id is not None:
#             queryset = queryset.filter(
#                 lot__achat__bijouterie_id=bijouterie_id
#             )

#         # ========================================================
#         # Filtres documentaires
#         # ========================================================

#         reference_commande = (
#             get_param("reference_commande")
#             or ""
#         ).strip()

#         if reference_commande:
#             queryset = queryset.filter(
#                 lot__achat__reference_commande__icontains=(
#                     reference_commande
#                 )
#             )

#         numero_lot = (
#             get_param("numero_lot")
#             or ""
#         ).strip()

#         if numero_lot:
#             queryset = queryset.filter(
#                 lot__numero_lot__icontains=numero_lot
#             )

#         numero_achat = (
#             get_param("numero_achat")
#             or ""
#         ).strip()

#         if numero_achat:
#             queryset = queryset.filter(
#                 lot__achat__numero_achat=numero_achat
#             )

#         lot_id = self._parse_positive_integer(
#             value=get_param("lot_id"),
#             field_name="lot_id",
#         )

#         if lot_id is not None:
#             queryset = queryset.filter(
#                 lot_id=lot_id
#             )

#         produit_id = self._parse_positive_integer(
#             value=get_param("produit_id"),
#             field_name="produit_id",
#         )

#         if produit_id is not None:
#             queryset = queryset.filter(
#                 produit_id=produit_id
#             )

#         fournisseur_id = self._parse_positive_integer(
#             value=get_param("fournisseur_id"),
#             field_name="fournisseur_id",
#         )

#         if fournisseur_id is not None:
#             queryset = queryset.filter(
#                 lot__achat__fournisseur_id=(
#                     fournisseur_id
#                 )
#             )

#         # ========================================================
#         # Périmètre des agrégats Stock
#         # ========================================================

#         accessible_bijouterie_ids = (
#             self._get_accessible_bijouteries()
#             .values_list(
#                 "id",
#                 flat=True,
#             )
#         )

#         stock_filter = Q(
#             stocks__bijouterie_id__in=(
#                 accessible_bijouterie_ids
#             )
#         )

#         if bijouterie_id is not None:
#             stock_filter &= Q(
#                 stocks__bijouterie_id=bijouterie_id
#             )

#         # ========================================================
#         # Agrégats du stock magasin
#         # ========================================================

#         queryset = queryset.annotate(
#             quantite_totale_total=Coalesce(
#                 Sum(
#                     "stocks__quantite_totale",
#                     filter=stock_filter,
#                 ),
#                 0,
#             ),
#             en_stock_total=Coalesce(
#                 Sum(
#                     "stocks__en_stock",
#                     filter=stock_filter,
#                 ),
#                 0,
#             ),
#         )

#         # ========================================================
#         # Uniquement les lignes disponibles en magasin
#         # ========================================================

#         if get_param("en_stock_only") == "1":
#             queryset = queryset.filter(
#                 en_stock_total__gt=0
#             )

#         # ========================================================
#         # Tri
#         # ========================================================

#         ordering = (
#             get_param("ordering")
#             or "-received_at"
#         ).strip()

#         ordering_map = {
#             "received_at": "lot__received_at",
#             "-received_at": "-lot__received_at",
#             "id": "id",
#             "-id": "-id",
#             "en_stock": "en_stock_total",
#             "-en_stock": "-en_stock_total",
#         }

#         ordering_field = ordering_map[ordering]

#         return queryset.order_by(
#             ordering_field,
#             "lot__numero_lot",
#             "id",
#         )

#     # ============================================================
#     # JSON ou export Excel
#     # ============================================================

#     def list(self, request, *args, **kwargs):
#         export_format = (
#             request.query_params.get("export")
#             or ""
#         ).strip().lower()

#         if export_format != "xlsx":
#             return super().list(
#                 request,
#                 *args,
#                 **kwargs,
#             )

#         queryset = self.filter_queryset(
#             self.get_queryset()
#         )

#         workbook = Workbook()
#         worksheet = workbook.active
#         worksheet.title = "Inventaire bijouteries"

#         headers = [
#             "produit_line_id",
#             "bijouterie_id",
#             "bijouterie",
#             "lot_id",
#             "numero_lot",
#             "date_reception",
#             "achat_id",
#             "numero_achat",
#             "reference_commande",
#             "fournisseur",
#             "produit_id",
#             "produit",
#             "categorie",
#             "marque",
#             "modele",
#             "purete",
#             "poids_unitaire",
#             "prix_achat_gramme",
#             "quantite_recue",
#             "quantite_totale_magasin",
#             "en_stock_magasin",
#         ]

#         worksheet.append(headers)

#         for produit_line in queryset.iterator():
#             lot = produit_line.lot
#             achat = lot.achat
#             fournisseur = achat.fournisseur
#             bijouterie = achat.bijouterie
#             produit = produit_line.produit

#             fournisseur_nom = None

#             if fournisseur:
#                 fournisseur_nom = " ".join(
#                     part
#                     for part in (
#                         fournisseur.prenom,
#                         fournisseur.nom,
#                     )
#                     if part
#                 ) or str(fournisseur)

#             categorie = getattr(
#                 produit,
#                 "categorie",
#                 None,
#             )
#             marque = getattr(
#                 produit,
#                 "marque",
#                 None,
#             )
#             modele = getattr(
#                 produit,
#                 "modele",
#                 None,
#             )
#             purete = getattr(
#                 produit,
#                 "purete",
#                 None,
#             )

#             worksheet.append([
#                 produit_line.id,

#                 (
#                     bijouterie.id
#                     if bijouterie
#                     else None
#                 ),
#                 (
#                     bijouterie.nom
#                     if bijouterie
#                     else None
#                 ),

#                 lot.id,
#                 lot.numero_lot,
#                 (
#                     lot.received_at.isoformat()
#                     if lot.received_at
#                     else None
#                 ),

#                 achat.id,
#                 achat.numero_achat,
#                 achat.reference_commande,

#                 fournisseur_nom,

#                 produit.id,
#                 produit.nom,

#                 (
#                     getattr(categorie, "nom", None)
#                     or getattr(categorie, "title", None)
#                 ),
#                 (
#                     getattr(marque, "nom", None)
#                     or getattr(marque, "title", None)
#                 ),
#                 (
#                     getattr(modele, "nom", None)
#                     or getattr(modele, "title", None)
#                 ),
#                 str(purete or ""),

#                 (
#                     str(produit.poids)
#                     if produit.poids is not None
#                     else None
#                 ),
#                 (
#                     str(
#                         produit_line.prix_achat_gramme
#                     )
#                     if (
#                         produit_line.prix_achat_gramme
#                         is not None
#                     )
#                     else None
#                 ),

#                 int(
#                     produit_line.quantite
#                     or 0
#                 ),
#                 int(
#                     getattr(
#                         produit_line,
#                         "quantite_totale_total",
#                         0,
#                     )
#                     or 0
#                 ),
#                 int(
#                     getattr(
#                         produit_line,
#                         "en_stock_total",
#                         0,
#                     )
#                     or 0
#                 ),
#             ])

#         self._autosize(worksheet)

#         return self._xlsx_response(
#             workbook,
#             "inventaire_bijouteries.xlsx",
#         )
# ----------------------- End InventoryPhotoView -----------------------    



class ProduitLineEtiquettesZIPView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Télécharger les étiquettes PNG",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["produit_line_ids"],
            properties={
                "produit_line_ids": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Items(type=openapi.TYPE_INTEGER),
                    example=[1, 2, 3],
                ),
            },
        ),
        tags=["Étiquettes"],
    )
    def post(self, request):
        role = get_role_name(request.user)

        if role not in [ROLE_ADMIN, ROLE_MANAGER]:
            return Response({"detail": "Accès refusé."}, status=403)

        produit_line_ids = request.data.get("produit_line_ids") or []

        if not produit_line_ids:
            return Response(
                {"detail": "produit_line_ids est requis."},
                status=400,
            )

        produit_lines = (
            ProduitLine.objects
            .select_related(
                "produit",
                "produit__purete",
                "produit__marque",
                "produit__categorie",
                "produit__modele",
            )
            .filter(id__in=produit_line_ids)
        )

        found_ids = set(produit_lines.values_list("id", flat=True))
        requested_ids = set(produit_line_ids)
        missing_ids = requested_ids - found_ids

        if missing_ids:
            return Response(
                {
                    "detail": "Certaines lignes produit sont introuvables.",
                    "missing_ids": list(missing_ids),
                },
                status=404,
            )

        zip_buffer = BytesIO()

        with zipfile.ZipFile(
            zip_buffer,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as zip_file:
            for line in produit_lines:
                produit = line.produit
                safe_name = f"produit_{produit.id}"

                for i in range(1, int(line.quantite) + 1):
                    image_buffer = build_etiquette_bague_png(produit)
                    filename = f"{safe_name}_{i}.png"

                    zip_file.writestr(
                        filename,
                        image_buffer.getvalue(),
                    )

        zip_buffer.seek(0)

        response = HttpResponse(
            zip_buffer.getvalue(),
            content_type="application/zip",
        )
        response["Content-Disposition"] = (
            'attachment; filename="etiquettes_produits.zip"'
        )

        return response
    

