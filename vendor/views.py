# vendor/views.py

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from datetime import date as ddate
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.paginator import EmptyPage, Paginator
from django.db.models import (Avg, Count, DecimalField, ExpressionWrapper, F,
                              IntegerField, OuterRef, Q, Subquery, Sum, Value)
from django.db.models.functions import (Coalesce, TruncDate, TruncDay,
                                        TruncMonth, TruncWeek)
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import generics, permissions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.query_scopes import scope_bijouterie_q
from backend.roles import ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, get_role_name
from inventory.models import Bucket, InventoryMovement, MovementType
from purchase.models import Lot, ProduitLine
from purchase.services.etiquettes import build_code_etiquette
from sale.models import Facture, VenteProduit
from staff.models import Manager
from stock.models import Stock, VendorStock
from stock.serializers import VendorStockSerializer
from vendor.services.qr_scan_service import (decode_etiquette_qr,
                                             resolve_scan_vendor)
from vendor.services.vendor_service import get_connected_vendor

from .models import Vendor
from .serializer import (VendorStockResponseSerializer,
                         VendorStockVendorSerializer)

# ============================================================
# DJANGO
# ============================================================










# ============================================================
# DJANGO REST FRAMEWORK
# ============================================================







# ============================================================
# SWAGGER
# ============================================================



# ============================================================
# BACKEND
# ============================================================






# ============================================================
# INVENTORY
# ============================================================



# ============================================================
# PURCHASE
# ============================================================



# ============================================================
# SALE
# ============================================================



# ============================================================
# STAFF
# ============================================================



# ============================================================
# STOCK
# ============================================================




# ============================================================
# STORE
# ============================================================




# ============================================================
# USER AUTH
# ============================================================



# ============================================================
# VENDOR
# ============================================================




# ============================================================
# CONSTANTES
# ============================================================

ZERO = Decimal("0.00")


# ============================================================
# USER MODEL
# ============================================================

User = get_user_model()


# ============================================================
# ROLES
# ============================================================

allowed_all_roles = [
    "admin",
    "manager",
    "vendeur",
]

allowed_roles_admin_manager = [
    "admin",
    "manager",
]


class VendorStockView(APIView):
    """
    Liste du stock disponible d'un vendeur.

    Règles :
    - vendeur :
        voit uniquement son propre stock ;

    - admin :
        doit fournir vendor_email ;

    - manager :
        doit fournir vendor_email
        et ne peut consulter qu'un vendeur
        appartenant à son périmètre ;

    - annee :
        année courante par défaut ;

    - pagination :
        50 lignes par défaut,
        maximum 100.

    Important :
    - les totaux sont calculés sur toute l'année filtrée ;
    - results contient uniquement les lignes encore disponibles ;
    - les lignes épuisées ne sont pas retournées.
    """

    permission_classes = [IsAuthenticated]

    http_method_names = [
        "get",
        "options",
    ]

    DEFAULT_PAGE_SIZE = 50
    MAX_PAGE_SIZE = 100

    @swagger_auto_schema(
        operation_summary="Stock disponible d'un vendeur",
        operation_description=(
            "Retourne le stock disponible d'un vendeur.\n\n"
            "### Vendeur connecté\n"
            "Aucun vendor_email nécessaire.\n\n"
            "### Admin / Manager\n"
            "`vendor_email` est obligatoire.\n\n"
            "### Filtres\n"
            "- `annee` : année recherchée ; année courante par défaut.\n"
            "- `page` : page courante ; 1 par défaut.\n"
            "- `page_size` : nombre de lignes ; 50 par défaut, maximum 100."
        ),
        manual_parameters=[
            openapi.Parameter(
                "vendor_email",
                openapi.IN_QUERY,
                description=(
                    "Email du vendeur. "
                    "Obligatoire pour admin/manager."
                ),
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "annee",
                openapi.IN_QUERY,
                description=(
                    "Année du stock. "
                    "Année courante par défaut."
                ),
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "page",
                openapi.IN_QUERY,
                description="Numéro de page. Défaut : 1.",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "page_size",
                openapi.IN_QUERY,
                description=(
                    "Nombre de résultats par page. "
                    "Défaut : 50. Maximum : 100."
                ),
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
        ],
        responses={
            200: VendorStockResponseSerializer(),
            400: openapi.Response(
                description="Paramètres invalides.",
            ),
            403: openapi.Response(
                description="Accès refusé.",
            ),
            404: openapi.Response(
                description="Vendeur ou page introuvable.",
            ),
        },
        tags=["vendor"],
    )
    def get(self, request):

        # ============================================================
        # 1. RÔLE
        # ============================================================

        role = (
            get_role_name(request.user)
            or ""
        ).lower()

        vendor_email = (
            request.query_params.get(
                "vendor_email"
            )
            or ""
        ).strip().lower()

        # ============================================================
        # 2. ANNÉE
        # ============================================================

        current_year = timezone.localdate().year

        annee_param = request.query_params.get(
            "annee"
        )

        if annee_param in (None, ""):
            annee = current_year

        else:
            try:
                annee = int(annee_param)

            except (TypeError, ValueError):
                return Response(
                    {
                        "detail": (
                            "annee doit être un entier valide."
                        ),
                        "code": "INVALID_YEAR",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if annee < 2000 or annee > current_year:
                return Response(
                    {
                        "detail": (
                            f"annee doit être comprise "
                            f"entre 2000 et {current_year}."
                        ),
                        "code": "INVALID_YEAR",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ============================================================
        # 3. PAGINATION
        # ============================================================

        page_param = request.query_params.get(
            "page",
            "1",
        )

        page_size_param = request.query_params.get(
            "page_size",
            str(self.DEFAULT_PAGE_SIZE),
        )

        try:
            page_number = int(page_param)

        except (TypeError, ValueError):
            return Response(
                {
                    "detail": "page doit être un entier valide.",
                    "code": "INVALID_PAGE",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if page_number < 1:
            return Response(
                {
                    "detail": (
                        "page doit être supérieur "
                        "ou égal à 1."
                    ),
                    "code": "INVALID_PAGE",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            page_size = int(page_size_param)

        except (TypeError, ValueError):
            return Response(
                {
                    "detail": (
                        "page_size doit être "
                        "un entier valide."
                    ),
                    "code": "INVALID_PAGE_SIZE",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if page_size < 1:
            return Response(
                {
                    "detail": (
                        "page_size doit être supérieur "
                        "ou égal à 1."
                    ),
                    "code": "INVALID_PAGE_SIZE",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        page_size = min(
            page_size,
            self.MAX_PAGE_SIZE,
        )

        # ============================================================
        # 4. VENDEUR
        # ============================================================

        if role == ROLE_VENDOR:

            vendor = get_connected_vendor(request.user)

            if vendor is None:
                return Response(
                    {
                        "detail": (
                            "Profil vendeur introuvable ou désactivé."
                        ),
                        "code": "VENDOR_PROFILE_UNAVAILABLE",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        elif role in {
            ROLE_ADMIN,
            ROLE_MANAGER,
        }:

            if not vendor_email:
                return Response(
                    {
                        "detail": (
                            "vendor_email est obligatoire "
                            "pour admin/manager."
                        ),
                        "code": "VENDOR_EMAIL_REQUIRED",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            vendor = (
                Vendor.objects
                .select_related(
                    "user",
                    "bijouterie",
                )
                .filter(
                    user__email__iexact=vendor_email
                )
                .first()
            )

            if not vendor:
                return Response(
                    {
                        "detail": "Vendeur introuvable.",
                        "code": "VENDOR_NOT_FOUND",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            # ========================================================
            # MANAGER
            # ========================================================

            if role == ROLE_MANAGER:

                manager = getattr(
                    request.user,
                    "staff_manager_profile",
                    None,
                )

                if not manager:
                    return Response(
                        {
                            "detail": (
                                "Profil manager introuvable."
                            ),
                            "code": (
                                "MANAGER_PROFILE_NOT_FOUND"
                            ),
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Utilise le scope déjà présent dans ton projet.
                #
                # Si ton Manager possède directement une relation
                # bijouteries, adapte uniquement ce bloc.

                allowed = scope_bijouterie_q(
                    request.user,
                    prefix="bijouterie",
                )

                if not (
                    Vendor.objects
                    .filter(
                        pk=vendor.pk
                    )
                    .filter(
                        allowed
                    )
                    .exists()
                ):
                    return Response(
                        {
                            "detail": (
                                "Ce vendeur n'appartient pas "
                                "à votre périmètre."
                            ),
                            "code": "VENDOR_OUT_OF_SCOPE",
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

        else:
            return Response(
                {
                    "detail": "Accès refusé.",
                    "code": "ACCESS_DENIED",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # ============================================================
        # 5. BIJOUTERIE VENDEUR
        # ============================================================

        if not getattr(
            vendor,
            "bijouterie_id",
            None,
        ):
            return Response(
                {
                    "detail": (
                        "Le vendeur n'est rattaché "
                        "à aucune bijouterie."
                    ),
                    "code": "VENDOR_WITHOUT_BIJOUTERIE",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ============================================================
        # 6. QUERYSET ANNÉE
        # ============================================================

        stock_qs = (
            VendorStock.objects
            .select_related(
                "vendor",
                "vendor__user",
                "bijouterie",

                "produit_line",
                "produit_line__lot",

                "produit_line__produit",
                "produit_line__produit__categorie",
                "produit_line__produit__marque",
                "produit_line__produit__purete",
                "produit_line__produit__modele",
            )
            .filter(
                vendor=vendor,
                bijouterie_id=vendor.bijouterie_id,

                # Filtre année
                created_at__year=annee,
            )
            .order_by(
                "-created_at",
                "-id",
            )
        )

        # ============================================================
        # 7. TOTAUX + IDENTIFICATION DES LIGNES DISPONIBLES
        # ============================================================

        total_allouee = 0
        total_vendue = 0
        total_disponible = 0

        total_poids_disponible = Decimal(
            "0.000"
        )

        stock_ids_disponibles = []

        for stock in stock_qs:

            quantite_allouee = int(
                stock.quantite_allouee
                or 0
            )

            quantite_vendue = int(
                stock.quantite_vendue
                or 0
            )

            quantite_disponible = max(
                quantite_allouee
                - quantite_vendue,
                0,
            )

            # --------------------------------------------------------
            # TOTAUX ANNUELS
            # --------------------------------------------------------

            total_allouee += quantite_allouee

            total_vendue += quantite_vendue

            total_disponible += quantite_disponible

            # --------------------------------------------------------
            # LIGNE ÉPUISÉE
            # --------------------------------------------------------

            if quantite_disponible <= 0:
                continue

            stock_ids_disponibles.append(
                stock.id
            )

            # --------------------------------------------------------
            # POIDS DISPONIBLE
            # --------------------------------------------------------

            produit_line = getattr(
                stock,
                "produit_line",
                None,
            )

            produit = (
                getattr(
                    produit_line,
                    "produit",
                    None,
                )
                if produit_line
                else None
            )

            if (
                produit
                and produit.poids is not None
            ):
                poids_unitaire = Decimal(
                    str(produit.poids)
                )

                total_poids_disponible += (
                    poids_unitaire
                    * Decimal(
                        str(
                            quantite_disponible
                        )
                    )
                )

        # ============================================================
        # 8. STOCK RÉELLEMENT DISPONIBLE
        # ============================================================

        stock_disponible_qs = (
            stock_qs
            .filter(
                id__in=stock_ids_disponibles
            )
        )

        # ============================================================
        # 9. PAGINATION
        # ============================================================

        paginator = Paginator(
            stock_disponible_qs,
            page_size,
        )

        # Cas particulier :
        # aucune donnée => page 1 vide autorisée

        if paginator.count == 0:

            if page_number != 1:
                return Response(
                    {
                        "detail": "Cette page n'existe pas.",
                        "code": "PAGE_NOT_FOUND",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            page_results = []

            total_pages = 0

            has_next = False
            has_previous = False

        else:

            try:
                page_obj = paginator.page(
                    page_number
                )

            except EmptyPage:
                return Response(
                    {
                        "detail": "Cette page n'existe pas.",
                        "code": "PAGE_NOT_FOUND",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            page_results = (
                page_obj.object_list
            )

            total_pages = (
                paginator.num_pages
            )

            has_next = (
                page_obj.has_next()
            )

            has_previous = (
                page_obj.has_previous()
            )

        # ============================================================
        # 10. SERIALIZER VENDEUR
        # ============================================================

        vendor_data = (
            VendorStockVendorSerializer(
                vendor
            ).data
        )

        # ============================================================
        # 11. SERIALIZER STOCK
        # ============================================================

        stock_data = VendorStockSerializer(
            page_results,
            many=True,
            context={"request": request},
        ).data

        # ============================================================
        # 12. RESPONSE
        # ============================================================

        response_data = {
            "vendor": vendor_data,

            "filtre": {
                "annee": annee,
            },

            "totaux": {
                "quantite_allouee":
                    total_allouee,

                "quantite_vendue":
                    total_vendue,

                "quantite_disponible":
                    total_disponible,

                "poids_disponible":
                    total_poids_disponible,
            },

            "pagination": {
                "page":
                    page_number,

                "page_size":
                    page_size,

                "total_pages":
                    total_pages,

                "total_results":
                    paginator.count,

                "has_next":
                    has_next,

                "has_previous":
                    has_previous,
            },

            # Nombre de lignes dans la page actuelle
            "count":
                len(stock_data),

            "produits":
                stock_data,
        }

        # ============================================================
        # 13. VALIDATION DE LA RESPONSE
        # ============================================================

        response_serializer = (
            VendorStockResponseSerializer(
                data=response_data
            )
        )

        response_serializer.is_valid(
            raise_exception=True
        )

        return Response(
            response_serializer.validated_data,
            status=status.HTTP_200_OK,
        )


class VendorScanQRCodeAPIView(APIView):
    """
    Scan QR Code des bijoux Rio-Gold.

    Rôles :
        VENDOR  : son propre stock.
        MANAGER : stock d'un vendeur de ses bijouteries.
        ADMIN   : stock d'un vendeur de toute bijouterie.

    Format QR :
        PL:<uuid ProduitLine>

    Fonctionnement :
        - Maximum 100 QR Codes.
        - Regroupement des QR identiques.
        - Calcul de quantite_demandee.
        - Vérification de VendorStock.
        - Aucun mouvement de stock.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    MAX_QR_CODES = 100

    # ============================================================
    # SWAGGER
    # ============================================================

    @swagger_auto_schema(
        operation_summary="Scanner les QR Codes des bijoux",
        operation_description=(
            "Scanne un ou plusieurs QR Codes des étiquettes Rio-Gold.\n\n"
            "**Accès :**\n"
            "- Vendeur : son propre stock.\n"
            "- Manager : vendeur de l'une de ses bijouteries.\n"
            "- Admin : vendeur de n'importe quelle bijouterie.\n\n"
            "**Paramètres :**\n"
            "- `qr_codes` : liste obligatoire des QR Codes.\n"
            "- `vendor_email` : obligatoire pour manager et admin.\n\n"
            "**Règles :**\n"
            "- Format QR : `PL:<uuid>`.\n"
            "- Maximum 100 scans par requête.\n"
            "- Les QR identiques sont regroupés.\n"
            "- Chaque répétition augmente `quantite_demandee`.\n"
            "- La disponibilité est vérifiée dans `VendorStock`.\n"
            "- Aucun stock n'est réservé ou déduit.\n"
            "- Une réponse HTTP 200 peut contenir `success=false`."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["qr_codes"],
            properties={
                "vendor_email": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_EMAIL,
                    description=(
                        "Email du vendeur dont le stock est consulté. "
                        "Obligatoire pour manager et admin. "
                        "Facultatif pour le vendeur connecté."
                    ),
                    example="vendeur@riogold.com",
                ),
                "qr_codes": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    minItems=1,
                    maxItems=100,
                    description=(
                        "Liste des QR Codes. "
                        "Les doublons sont autorisés."
                    ),
                    items=openapi.Items(
                        type=openapi.TYPE_STRING,
                    ),
                    example=[
                        "PL:550e8400-e29b-41d4-a716-446655440000",
                        "PL:550e8400-e29b-41d4-a716-446655440000",
                        "PL:660e8400-e29b-41d4-a716-446655440001",
                    ],
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="Résultat des scans QR Codes.",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "success": openapi.Schema(
                            type=openapi.TYPE_BOOLEAN,
                        ),
                        "vendor": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "id": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                ),
                                "email": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                ),
                                "bijouterie_id": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                ),
                            },
                        ),
                        "nombre_scans": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                        ),
                        "nombre_produits": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                        ),
                        "nombre_erreurs": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                        ),
                        "nombre_produits_indisponibles": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                        ),
                        "produits": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "qr_code": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                    ),
                                    "code_etiquette": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                    ),
                                    "produit_line_id": openapi.Schema(
                                        type=openapi.TYPE_INTEGER,
                                    ),
                                    "produit_line_uuid": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                    ),
                                    "produit_id": openapi.Schema(
                                        type=openapi.TYPE_INTEGER,
                                    ),
                                    "sku": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        x_nullable=True,
                                    ),
                                    "nom": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                    ),
                                    "lot_id": openapi.Schema(
                                        type=openapi.TYPE_INTEGER,
                                    ),
                                    "vendor_stock_id": openapi.Schema(
                                        type=openapi.TYPE_INTEGER,
                                    ),
                                    "poids_unitaire_achat": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        x_nullable=True,
                                    ),
                                    "quantite_demandee": openapi.Schema(
                                        type=openapi.TYPE_INTEGER,
                                    ),
                                    "quantite_allouee": openapi.Schema(
                                        type=openapi.TYPE_INTEGER,
                                    ),
                                    "quantite_vendue": openapi.Schema(
                                        type=openapi.TYPE_INTEGER,
                                    ),
                                    "quantite_disponible": openapi.Schema(
                                        type=openapi.TYPE_INTEGER,
                                    ),
                                    "peut_vendre": openapi.Schema(
                                        type=openapi.TYPE_BOOLEAN,
                                    ),
                                },
                            ),
                        ),
                        "erreurs": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "qr_code": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                    ),
                                    "code": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                    ),
                                    "detail": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                    ),
                                },
                            ),
                        ),
                    },
                ),
            ),
            400: openapi.Response(
                description="Données ou QR Codes invalides.",
            ),
            401: openapi.Response(
                description="Authentification requise.",
            ),
            403: openapi.Response(
                description="Accès refusé.",
            ),
        },
        tags=["vendor"],
    )
    def post(self, request):

        # ========================================================
        # 1. RÉCUPÉRER LE VENDEUR AUTORISÉ
        # ========================================================

        vendor = resolve_scan_vendor(
            user=request.user,
            vendor_email=request.data.get("vendor_email"),
        )

        # La fonction vérifie :
        # - le rôle du compte connecté ;
        # - l'activation du vendeur ;
        # - les bijouteries du manager ;
        # - l'accès global de l'admin.

        # ========================================================
        # 2. VALIDATION DES QR CODES
        # ========================================================

        qr_codes = request.data.get("qr_codes")

        if not isinstance(qr_codes, list) or not qr_codes:
            return Response(
                {
                    "detail": "qr_codes doit être une liste non vide.",
                    "code": "INVALID_QR_CODES",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(qr_codes) > self.MAX_QR_CODES:
            return Response(
                {
                    "detail": (
                        f"Maximum {self.MAX_QR_CODES} "
                        "QR Codes par requête."
                    ),
                    "code": "QR_CODES_LIMIT_EXCEEDED",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ========================================================
        # 3. DÉCODAGE ET VALIDATION
        # ========================================================

        uuids = []
        erreurs_validation = []

        for index, qr_code in enumerate(qr_codes):

            if (
                not isinstance(qr_code, str)
                or not qr_code.strip()
            ):
                erreurs_validation.append(
                    {
                        "index": index,
                        "qr_code": qr_code,
                        "code": "INVALID_QR_CODE",
                        "detail": (
                            "Le QR Code doit être "
                            "une chaîne non vide."
                        ),
                    }
                )
                continue

            try:
                qr_uuid = decode_etiquette_qr(qr_code)
                uuids.append(str(qr_uuid))

            except ValueError as exc:
                erreurs_validation.append(
                    {
                        "index": index,
                        "qr_code": qr_code,
                        "code": "INVALID_QR_CODE",
                        "detail": str(exc),
                    }
                )

        if erreurs_validation:
            return Response(
                {
                    "detail": "Un ou plusieurs QR Codes sont invalides.",
                    "code": "QR_VALIDATION_FAILED",
                    "erreurs": erreurs_validation,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ========================================================
        # 4. REGROUPER LES QR IDENTIQUES
        # ========================================================

        compteurs = Counter(uuids)
        uuids_uniques = list(compteurs.keys())

        # ========================================================
        # 5. RECHERCHER LES PRODUITLINE
        # ========================================================

        produit_lines = (
            ProduitLine.objects
            .select_related(
                "lot",
                "produit",
                "produit__categorie",
                "produit__marque",
                "produit__purete",
                "produit__modele",
            )
            .filter(uuid__in=uuids_uniques)
        )

        produit_lines_map = {
            str(pl.uuid): pl
            for pl in produit_lines
        }

        # ========================================================
        # 6. RECHERCHER LE STOCK DU VENDEUR
        # ========================================================

        vendor_stocks = (
            VendorStock.objects
            .filter(
                vendor=vendor,
                bijouterie_id=vendor.bijouterie_id,
                produit_line__uuid__in=uuids_uniques,
            )
        )

        vendor_stocks_map = {
            stock.produit_line_id: stock
            for stock in vendor_stocks
        }

        # ========================================================
        # 7. PRÉPARER LES RÉSULTATS
        # ========================================================

        produits = []
        erreurs = []

        # ========================================================
        # 8. TRAITER CHAQUE PRODUITLINE
        # ========================================================

        for qr_uuid, quantite_demandee in compteurs.items():

            qr_code = f"PL:{qr_uuid}"

            produit_line = produit_lines_map.get(qr_uuid)

            if produit_line is None:
                erreurs.append(
                    {
                        "qr_code": qr_code,
                        "code": "PRODUIT_LINE_NOT_FOUND",
                        "detail": "Étiquette introuvable.",
                    }
                )
                continue

            vendor_stock = vendor_stocks_map.get(
                produit_line.id
            )

            if vendor_stock is None:
                erreurs.append(
                    {
                        "qr_code": qr_code,
                        "code": "STOCK_NOT_ASSIGNED",
                        "detail": (
                            "Produit non affecté au stock "
                            "du vendeur sélectionné."
                        ),
                    }
                )
                continue

            # ----------------------------------------------------
            # QUANTITÉS
            # ----------------------------------------------------

            quantite_allouee = int(
                vendor_stock.quantite_allouee
            )

            quantite_vendue = int(
                vendor_stock.quantite_vendue
            )

            quantite_disponible = max(
                0,
                quantite_allouee - quantite_vendue,
            )

            peut_vendre = (
                quantite_demandee <= quantite_disponible
            )

            # ----------------------------------------------------
            # INFORMATIONS PRODUIT
            # ----------------------------------------------------

            produit = produit_line.produit

            produits.append(
                {
                    "qr_code": qr_code,
                    "code_etiquette": build_code_etiquette(
                        produit_line
                    ),
                    "produit_line_id": produit_line.id,
                    "produit_line_uuid": str(produit_line.uuid),
                    "produit_id": produit.id,
                    "sku": produit.sku,
                    "nom": produit.nom,
                    "lot_id": produit_line.lot_id,
                    "vendor_stock_id": vendor_stock.id,
                    "poids_unitaire_achat": (
                        str(produit_line.poids_unitaire_achat)
                        if produit_line.poids_unitaire_achat is not None
                        else None
                    ),
                    "quantite_demandee": quantite_demandee,
                    "quantite_allouee": quantite_allouee,
                    "quantite_vendue": quantite_vendue,
                    "quantite_disponible": quantite_disponible,
                    "peut_vendre": peut_vendre,
                }
            )

        # ========================================================
        # 9. CALCULER LES TOTAUX
        # ========================================================

        nombre_erreurs = len(erreurs)

        nombre_indisponibles = sum(
            1
            for produit in produits
            if not produit["peut_vendre"]
        )

        success = (
            nombre_erreurs == 0
            and nombre_indisponibles == 0
        )

        # ========================================================
        # 10. RÉPONSE FINALE
        # ========================================================

        return Response(
            {
                "success": success,
                "vendor": {
                    "id": vendor.id,
                    "email": vendor.user.email,
                    "bijouterie_id": vendor.bijouterie_id,
                },
                "nombre_scans": len(qr_codes),
                "nombre_produits": len(produits),
                "nombre_erreurs": nombre_erreurs,
                "nombre_produits_indisponibles": nombre_indisponibles,
                "produits": produits,
                "erreurs": erreurs,
            },
            status=status.HTTP_200_OK,
        )
        
        



class VendorDashboardView(APIView):
    """
    Dashboard personnel du vendeur Rio-Gold.

    Filtres :
        annee   : 3 dernières années uniquement
        periode : jour, semaine, mois, annee
        mois    : 1 à 12, pour la période mois

    Par défaut :
        année courante
        période mois
        mois courant

    Sécurité :
        vendeur connecté et vérifié uniquement
        statistiques limitées à ses propres ventes
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Dashboard vendeur Rio-Gold",
        operation_description=(
            "Affiche les statistiques personnelles du vendeur. "
            "Les ventes sont limitées aux trois dernières années, "
            "année courante comprise. "
            "Par défaut, affiche le mois courant. "
            "Le stock représente le stock actuel du vendeur."
        ),
        manual_parameters=[
            openapi.Parameter(
                name="annee",
                in_=openapi.IN_QUERY,
                description=(
                    "Année à consulter. "
                    "Trois dernières années uniquement. "
                    "Par défaut : année courante."
                ),
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                name="periode",
                in_=openapi.IN_QUERY,
                description="Période des statistiques.",
                type=openapi.TYPE_STRING,
                enum=["jour", "semaine", "mois", "annee"],
                default="mois",
                required=False,
            ),
            openapi.Parameter(
                name="mois",
                in_=openapi.IN_QUERY,
                description=(
                    "Mois à consulter (1 à 12). "
                    "Utilisé avec periode=mois. "
                    "Par défaut : mois courant pour "
                    "l'année courante, décembre pour "
                    "une année précédente."
                ),
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
        ],
        responses={
            200: "Dashboard vendeur",
            400: "Paramètres invalides",
            403: "Accès refusé",
        },
    )
    def get(self, request):

        # ==========================================
        # 1. Vérification du vendeur
        # ==========================================

        if get_role_name(request.user) != ROLE_VENDOR:
            return Response(
                {
                    "detail": "Accès réservé aux vendeurs."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        vendor = (
            Vendor.objects
            .select_related("user", "bijouterie")
            .filter(
                user=request.user,
                verifie=True,
            )
            .first()
        )

        if vendor is None:
            return Response(
                {
                    "detail": (
                        "Profil vendeur introuvable "
                        "ou désactivé."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # ==========================================
        # 2. Années autorisées
        # ==========================================

        now = timezone.localtime()
        today = now.date()

        annee_courante = today.year

        annees_autorisees = list(
            range(
                annee_courante - 2,
                annee_courante + 1,
            )
        )

        annee_param = request.query_params.get(
            "annee",
            str(annee_courante),
        )

        try:
            annee = int(annee_param)
        except (TypeError, ValueError):
            return Response(
                {
                    "detail": "L'année doit être un entier.",
                    "annees_autorisees": annees_autorisees,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if annee not in annees_autorisees:
            return Response(
                {
                    "detail": (
                        "Consultation limitée aux "
                        "trois dernières années."
                    ),
                    "annees_autorisees": annees_autorisees,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ==========================================
        # 3. Période
        # ==========================================

        periode = request.query_params.get(
            "periode",
            "mois",
        ).strip().lower()

        periodes_autorisees = (
            "jour",
            "semaine",
            "mois",
            "annee",
        )

        if periode not in periodes_autorisees:
            return Response(
                {
                    "detail": "Période invalide.",
                    "periodes_autorisees": (
                        periodes_autorisees
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ==========================================
        # 4. Mois
        # ==========================================

        mois_defaut = (
            today.month
            if annee == annee_courante
            else 12
        )

        mois_param = request.query_params.get(
            "mois",
            str(mois_defaut),
        )

        try:
            mois = int(mois_param)
        except (TypeError, ValueError):
            return Response(
                {
                    "detail": "Le mois doit être un entier."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not 1 <= mois <= 12:
            return Response(
                {
                    "detail": (
                        "Le mois doit être compris "
                        "entre 1 et 12."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if (
            annee == annee_courante
            and mois > today.month
        ):
            return Response(
                {
                    "detail": (
                        "Impossible de consulter "
                        "un mois futur."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ==========================================
        # 5. Dates de la période
        # ==========================================

        if periode == "annee":

            start_date = date(annee, 1, 1)

            end_date = (
                today
                if annee == annee_courante
                else date(annee, 12, 31)
            )

        elif periode == "mois":

            start_date = date(annee, mois, 1)

            if annee == annee_courante and mois == today.month:
                end_date = today
            else:
                if mois == 12:
                    next_month = date(annee + 1, 1, 1)
                else:
                    next_month = date(annee, mois + 1, 1)

                end_date = next_month - timedelta(days=1)

        else:
            # Pour jour/semaine, on utilise
            # le dernier jour du mois sélectionné,
            # ou aujourd'hui si mois courant.

            if annee == annee_courante and mois == today.month:
                reference_date = today
            else:
                if mois == 12:
                    next_month = date(annee + 1, 1, 1)
                else:
                    next_month = date(annee, mois + 1, 1)

                reference_date = (
                    next_month - timedelta(days=1)
                )

            if periode == "jour":
                start_date = reference_date
                end_date = reference_date

            else:
                start_date = reference_date - timedelta(
                    days=reference_date.weekday()
                )

                end_date = reference_date

                # Empêcher la semaine de dépasser
                # le début de l'année sélectionnée.
                start_date = max(
                    start_date,
                    date(annee, 1, 1),
                )

        # ==========================================
        # 6. Bornes datetime
        # ==========================================

        start_datetime = timezone.make_aware(
            datetime.combine(
                start_date,
                time.min,
            ),
            timezone.get_current_timezone(),
        )

        end_datetime = timezone.make_aware(
            datetime.combine(
                end_date + timedelta(days=1),
                time.min,
            ),
            timezone.get_current_timezone(),
        )

        # ==========================================
        # 7. Ventes personnelles
        # ==========================================

        ventes = VenteProduit.objects.filter(
            vendor=vendor,
            vente__created_at__gte=start_datetime,
            vente__created_at__lt=end_datetime,
        )

        # À adapter au champ de statut de Vente :
        # exclure impérativement les ventes annulées
        # et appliquer les règles des retours.
        #
        # Le champ montant_total doit représenter
        # le montant réel de chaque ligne vendue.

        montant_field = DecimalField(
            max_digits=18,
            decimal_places=2,
        )

        stats_ventes = ventes.aggregate(
            nombre_ventes=Count(
                "vente_id",
                distinct=True,
            ),
            quantite_vendue=Coalesce(
                Sum("quantite"),
                0,
            ),
            chiffre_affaires=Coalesce(
                Sum("montant_total"),
                Decimal("0.00"),
                output_field=montant_field,
            ),
        )

        # ==========================================
        # 8. Stock actuel du vendeur
        # ==========================================

        stock_stats = (
            VendorStock.objects
            .filter(vendor=vendor)
            .aggregate(
                quantite_allouee=Coalesce(
                    Sum("quantite_allouee"),
                    0,
                ),
                quantite_vendue=Coalesce(
                    Sum("quantite_vendue"),
                    0,
                ),
            )
        )

        quantite_disponible = max(
            0,
            stock_stats["quantite_allouee"]
            - stock_stats["quantite_vendue"],
        )

        # ==========================================
        # 9. Évolution quotidienne des ventes
        # ==========================================

        evolution_queryset = (
            ventes
            .annotate(
                jour=TruncDate(
                    "vente__created_at"
                )
            )
            .values("jour")
            .annotate(
                nombre_ventes=Count(
                    "vente_id",
                    distinct=True,
                ),
                quantite_vendue=Coalesce(
                    Sum("quantite"),
                    0,
                ),
                montant=Coalesce(
                    Sum("montant_total"),
                    Decimal("0.00"),
                    output_field=montant_field,
                ),
            )
            .order_by("jour")
        )

        evolution_ventes = [
            {
                "date": item["jour"].isoformat(),
                "nombre_ventes": item["nombre_ventes"],
                "quantite_vendue": item["quantite_vendue"],
                "montant": str(item["montant"]),
            }
            for item in evolution_queryset
        ]

        # ==========================================
        # 10. Top 5 produits
        # ==========================================

        top_queryset = (
            ventes
            .values(
                "produit_line__produit_id",
                "produit_line__produit__nom",
            )
            .annotate(
                quantite_vendue=Coalesce(
                    Sum("quantite"),
                    0,
                ),
                chiffre_affaires=Coalesce(
                    Sum("montant_total"),
                    Decimal("0.00"),
                    output_field=montant_field,
                ),
            )
            .order_by(
                "-quantite_vendue",
                "produit_line__produit_id",
            )[:5]
        )

        top_produits = [
            {
                "produit_id": item[
                    "produit_line__produit_id"
                ],
                "produit_nom": item[
                    "produit_line__produit__nom"
                ],
                "quantite_vendue": item[
                    "quantite_vendue"
                ],
                "chiffre_affaires": str(
                    item["chiffre_affaires"]
                ),
            }
            for item in top_queryset
        ]

        # ==========================================
        # 11. Dernières ventes : 10 maximum
        # ==========================================

        dernieres_queryset = (
            ventes
            .values(
                "vente_id",
                "vente__numero_vente",
                "vente__created_at",
            )
            .annotate(
                montant=Coalesce(
                    Sum("montant_total"),
                    Decimal("0.00"),
                    output_field=montant_field,
                ),
                quantite=Coalesce(
                    Sum("quantite"),
                    0,
                ),
            )
            .order_by(
                "-vente__created_at",
                "-vente_id",
            )[:10]
        )

        dernieres_ventes = [
            {
                "vente_id": item["vente_id"],
                "numero_vente": item[
                    "vente__numero_vente"
                ],
                "date": (
                    timezone.localtime(
                        item["vente__created_at"]
                    ).isoformat()
                    if item["vente__created_at"]
                    else None
                ),
                "quantite": item["quantite"],
                "montant": str(item["montant"]),
            }
            for item in dernieres_queryset
        ]

        # ==========================================
        # 12. Réponse finale
        # ==========================================

        return Response(
            {
                "vendeur": {
                    "id": vendor.id,
                    "email": vendor.user.email,
                    "nom": vendor.user.get_full_name(),
                    "bijouterie_id": vendor.bijouterie_id,
                    "bijouterie_nom": vendor.bijouterie.nom,
                },
                "filtres": {
                    "annee": annee,
                    "annees_autorisees": annees_autorisees,
                    "periode": periode,
                    "mois": mois,
                    "date_debut": start_date.isoformat(),
                    "date_fin": end_date.isoformat(),
                },
                "ventes": {
                    "nombre": stats_ventes["nombre_ventes"],
                    "quantite_vendue": stats_ventes[
                        "quantite_vendue"
                    ],
                    "chiffre_affaires": str(
                        stats_ventes["chiffre_affaires"]
                    ),
                },
                "stock": {
                    "quantite_allouee": stock_stats[
                        "quantite_allouee"
                    ],
                    "quantite_vendue": stock_stats[
                        "quantite_vendue"
                    ],
                    "quantite_disponible": quantite_disponible,
                },
                "evolution_ventes": evolution_ventes,
                "top_produits": top_produits,
                "dernieres_ventes": dernieres_ventes,
            },
            status=status.HTTP_200_OK,
        )
        

