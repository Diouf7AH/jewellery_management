# vendor/views.py

from __future__ import annotations

import datetime
from collections import defaultdict
from datetime import date
from datetime import date as ddate
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO
from textwrap import dedent
from typing import Optional

from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.core.paginator import EmptyPage, Paginator
from django.db import IntegrityError, transaction
from django.db.models import (Avg, Count, DecimalField, ExpressionWrapper, F,
                              IntegerField, OuterRef, Q, Subquery, Sum, Value)
from django.db.models.functions import (Coalesce, TruncDay, TruncMonth,
                                        TruncWeek)
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.permissions import IsAdminOrManager
from backend.query_scopes import scope_bijouterie_q
from backend.renderers import UserRenderer
from backend.roles import ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, get_role_name
from inventory.models import Bucket, InventoryMovement, MovementType
from purchase.models import Lot, ProduitLine
from sale.models import Facture, VenteProduit
from staff.models import Manager
from stock.models import Stock, VendorStock
from stock.serializers import VendorStockSerializer
from store.models import Bijouterie, Marque, Produit
from store.serializers import ProduitSerializer
from userauths.models import Role

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
    Stock disponible du vendeur.

    Formule :
        quantite_disponible =
            quantite_allouee - quantite_vendue

    Filtres :
        - annee
        - page
        - page_size

    Par défaut :
        - annee = année courante
        - page = 1
        - page_size = 50

    Accès :
        - vendor : son propre stock
        - admin : vendor_email obligatoire
        - manager : vendor_email obligatoire,
          limité à ses bijouteries
    """

    permission_classes = [
        IsAuthenticated,
    ]

    http_method_names = [
        "get",
        "options",
    ]

    DEFAULT_PAGE_SIZE = 50
    MAX_PAGE_SIZE = 100

    @swagger_auto_schema(
        operation_summary="Stock disponible du vendeur",
        operation_description=(
            "Retourne le stock disponible du vendeur.\n\n"
            "Vendor connecté : aucun vendor_email requis.\n"
            "Admin/Manager : vendor_email obligatoire.\n\n"
            "Par défaut, le stock de l'année courante "
            "est retourné."
        ),
        manual_parameters=[
            openapi.Parameter(
                "vendor_email",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=False,
                description=(
                    "Email du vendeur. "
                    "Obligatoire pour admin/manager."
                ),
            ),
            openapi.Parameter(
                "annee",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description=(
                    "Année du stock. "
                    "Par défaut : année courante."
                ),
            ),
            openapi.Parameter(
                "page",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="Page. Par défaut : 1.",
            ),
            openapi.Parameter(
                "page_size",
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description=(
                    "Nombre de résultats par page. "
                    "Par défaut : 50. Maximum : 100."
                ),
            ),
        ],
        responses={
            200: VendorStockResponseSerializer(),
            400: openapi.Response(
                "Paramètres invalides"
            ),
            403: openapi.Response(
                "Accès refusé"
            ),
            404: openapi.Response(
                "Vendeur introuvable"
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
                            "annee doit être "
                            "un entier valide."
                        ),
                        "code": "INVALID_YEAR",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if (
                annee < 2000
                or annee > current_year
            ):
                return Response(
                    {
                        "detail": (
                            f"annee doit être comprise "
                            f"entre 2000 et "
                            f"{current_year}."
                        ),
                        "code": "INVALID_YEAR",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ============================================================
        # 3. PAGINATION
        # ============================================================

        try:
            page_number = int(
                request.query_params.get(
                    "page",
                    1,
                )
            )
        except (TypeError, ValueError):
            return Response(
                {
                    "detail":
                        "page doit être un entier valide.",
                    "code": "INVALID_PAGE",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if page_number <= 0:
            return Response(
                {
                    "detail":
                        "page doit être supérieur à zéro.",
                    "code": "INVALID_PAGE",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            page_size = int(
                request.query_params.get(
                    "page_size",
                    self.DEFAULT_PAGE_SIZE,
                )
            )
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

        if page_size <= 0:
            return Response(
                {
                    "detail": (
                        "page_size doit être "
                        "supérieur à zéro."
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
        # 4. RÉSOUDRE LE VENDEUR
        # ============================================================

        if role == ROLE_VENDOR:

            vendor = getattr(
                request.user,
                "staff_vendor_profile",
                None,
            )

            if not vendor:
                return Response(
                    {
                        "detail":
                            "Profil vendeur introuvable.",
                        "code":
                            "VENDOR_PROFILE_NOT_FOUND",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not getattr(
                vendor,
                "verifie",
                False,
            ):
                return Response(
                    {
                        "detail":
                            "Profil vendeur désactivé.",
                        "code":
                            "VENDOR_PROFILE_DISABLED",
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
                        "code":
                            "VENDOR_EMAIL_REQUIRED",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            vendor = get_object_or_404(
                Vendor.objects.select_related(
                    "user",
                    "bijouterie",
                ),
                user__email__iexact=vendor_email,
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
                            "detail":
                                "Profil manager introuvable.",
                            "code":
                                "MANAGER_PROFILE_NOT_FOUND",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                has_access = (
                    manager
                    .bijouteries
                    .filter(
                        id=vendor.bijouterie_id
                    )
                    .exists()
                )

                if not has_access:
                    return Response(
                        {
                            "detail": (
                                "Ce vendeur n'appartient "
                                "pas à votre périmètre."
                            ),
                            "code":
                                "VENDOR_OUT_OF_SCOPE",
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
        # 5. BIJOUTERIE
        # ============================================================

        if not vendor.bijouterie_id:
            return Response(
                {
                    "detail": (
                        "Le vendeur n'est rattaché "
                        "à aucune bijouterie."
                    ),
                    "code":
                        "VENDOR_WITHOUT_BIJOUTERIE",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ============================================================
        # 6. QUERYSET
        # ============================================================

        queryset = (
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

                # Filtre principal
                created_at__year=annee,
            )
            .order_by(
                "-created_at",
                "-id",
            )
        )

        # ============================================================
        # 7. CALCUL DES TOTAUX
        #
        # Les totaux sont calculés sur TOUTE l'année,
        # pas uniquement sur la page courante.
        # ============================================================

        total_allouee = 0
        total_vendue = 0
        total_disponible = 0

        total_poids_disponible = Decimal(
            "0.000"
        )

        stock_ids_disponibles = []

        for stock in queryset:

            quantite_allouee = int(
                stock.quantite_allouee
                or 0
            )

            quantite_vendue = int(
                stock.quantite_vendue
                or 0
            )

            quantite_disponible = int(
                stock.quantite_disponible
            )

            total_allouee += (
                quantite_allouee
            )

            total_vendue += (
                quantite_vendue
            )

            total_disponible += (
                quantite_disponible
            )

            # Ne pas afficher les lignes épuisées
            if quantite_disponible <= 0:
                continue

            stock_ids_disponibles.append(
                stock.id
            )

            produit = getattr(
                stock.produit_line,
                "produit",
                None,
            )

            if (
                produit
                and produit.poids is not None
            ):
                poids = Decimal(
                    str(produit.poids)
                )

                total_poids_disponible += (
                    poids
                    * Decimal(
                        str(
                            quantite_disponible
                        )
                    )
                )

        # ============================================================
        # 8. QUERYSET DISPONIBLE
        # ============================================================

        stock_disponible_queryset = (
            queryset
            .filter(
                id__in=stock_ids_disponibles
            )
        )

        # ============================================================
        # 9. PAGINATION
        # ============================================================

        paginator = Paginator(
            stock_disponible_queryset,
            page_size,
        )

        try:
            page_obj = paginator.page(
                page_number
            )

        except EmptyPage:
            return Response(
                {
                    "detail":
                        "Cette page n'existe pas.",
                    "code":
                        "PAGE_NOT_FOUND",
                },
                status=status.HTTP_404_NOT_FOUND,
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

        stock_data = (
            VendorStockSerializer(
                page_obj.object_list,
                many=True,
            ).data
        )

        # ============================================================
        # 12. RESPONSE
        # ============================================================

        response_data = {
            "vendor":
                vendor_data,

            "filtre": {
                "annee":
                    annee,
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
                    page_obj.number,

                "page_size":
                    page_size,

                "total_pages":
                    paginator.num_pages,

                "total_results":
                    paginator.count,

                "has_next":
                    page_obj.has_next(),

                "has_previous":
                    page_obj.has_previous(),
            },

            "count":
                len(stock_data),

            "results":
                stock_data,
        }

        # ============================================================
        # 13. VALIDATION RESPONSE
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
            response_serializer.data,
            status=status.HTTP_200_OK,
        )


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

            vendor = getattr(
                request.user,
                "staff_vendor_profile",
                None,
            )

            if not vendor:
                return Response(
                    {
                        "detail": "Profil vendeur introuvable.",
                        "code": "VENDOR_PROFILE_NOT_FOUND",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not getattr(
                vendor,
                "verifie",
                False,
            ):
                return Response(
                    {
                        "detail": "Profil vendeur désactivé.",
                        "code": "VENDOR_PROFILE_DISABLED",
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

        stock_data = (
            VendorStockSerializer(
                page_results,
                many=True,
            ).data
        )

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
