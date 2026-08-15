from __future__ import annotations

from datetime import datetime

from django.db.models import F, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils.dateparse import parse_date, parse_datetime
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.roles import (ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER, ROLE_VENDOR,
                           get_role_name)
from inventory.models import Bucket, InventoryMovement, MovementType
from inventory.serializers import (InventoryBijouterieSerializer,
                                   InventoryMovementSerializer,
                                   InventoryVendorSerializer,
                                   ProduitLineWithInventorySerializer)
from purchase.models import ProduitLine
from stock.models import Stock, VendorStock
from store.models import Bijouterie
from vendor.models import Vendor


class InventoryMovementListView(ListAPIView):
    """
    Journal central des mouvements d'inventaire.

    Accès :
    - admin : tous les mouvements ;
    - manager : mouvements de ses bijouteries ;
    - vendor : mouvements qui lui sont directement liés ;
    - cashier : mouvements de sa bijouterie.

    Filtres :
    - q
    - movement_type
    - movement_types
    - produit_id
    - produit_line_id
    - lot_id
    - numero_lot
    - achat_id
    - facture_id
    - vente_id
    - vente_ligne_id
    - vendor_id
    - bijouterie_id
    - src_bucket
    - dst_bucket
    - date_from
    - date_to
    - min_qty
    - max_qty
    - is_locked
    - stock_consumed
    - ordering
    """

    permission_classes = [IsAuthenticated]
    serializer_class = InventoryMovementSerializer
    pagination_class = None

    ALLOWED_ORDERING = {
        "id",
        "-id",
        "occurred_at",
        "-occurred_at",
        "created_at",
        "-created_at",
        "qty",
        "-qty",
        "movement_type",
        "-movement_type",
    }

    @swagger_auto_schema(
        operation_id="listInventoryMovements",
        operation_summary="Lister les mouvements d'inventaire",
        operation_description=(
            "Retourne le journal central des mouvements d'inventaire.\n\n"
            "Types disponibles :\n"
            "- PURCHASE_IN\n"
            "- VENDOR_ASSIGN\n"
            "- SALE_OUT\n"
            "- RETURN_IN\n"
            "- CANCEL_PURCHASE\n"
            "- ADJUSTMENT\n\n"
            "Le résultat est automatiquement limité selon le rôle connecté."
        ),
        manual_parameters=[
            openapi.Parameter(
                "q",
                openapi.IN_QUERY,
                description=(
                    "Recherche dans le produit, SKU, lot, achat, "
                    "facture, vente, motif et vendeur."
                ),
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "movement_type",
                openapi.IN_QUERY,
                description="Type unique de mouvement.",
                type=openapi.TYPE_STRING,
                enum=[choice[0] for choice in MovementType.choices],
            ),
            openapi.Parameter(
                "movement_types",
                openapi.IN_QUERY,
                description=(
                    "Plusieurs types séparés par des virgules. "
                    "Exemple : PURCHASE_IN,ADJUSTMENT"
                ),
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "produit_id",
                openapi.IN_QUERY,
                description="Identifiant du produit.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "produit_line_id",
                openapi.IN_QUERY,
                description="Identifiant de la ProduitLine.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "lot_id",
                openapi.IN_QUERY,
                description="Identifiant du lot.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "numero_lot",
                openapi.IN_QUERY,
                description="Recherche par numéro de lot.",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "achat_id",
                openapi.IN_QUERY,
                description="Identifiant de l'achat.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "facture_id",
                openapi.IN_QUERY,
                description="Identifiant de la facture.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "vente_id",
                openapi.IN_QUERY,
                description="Identifiant de la vente.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "vente_ligne_id",
                openapi.IN_QUERY,
                description="Identifiant de la ligne de vente.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "vendor_id",
                openapi.IN_QUERY,
                description="Identifiant du vendeur.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                description=(
                    "Mouvements dont la bijouterie est source "
                    "ou destination."
                ),
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "src_bucket",
                openapi.IN_QUERY,
                description="Emplacement source.",
                type=openapi.TYPE_STRING,
                enum=[choice[0] for choice in Bucket.choices],
            ),
            openapi.Parameter(
                "dst_bucket",
                openapi.IN_QUERY,
                description="Emplacement destination.",
                type=openapi.TYPE_STRING,
                enum=[choice[0] for choice in Bucket.choices],
            ),
            openapi.Parameter(
                "date_from",
                openapi.IN_QUERY,
                description="Date minimale, format YYYY-MM-DD.",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
            ),
            openapi.Parameter(
                "date_to",
                openapi.IN_QUERY,
                description="Date maximale, format YYYY-MM-DD.",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
            ),
            openapi.Parameter(
                "min_qty",
                openapi.IN_QUERY,
                description="Quantité minimale.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "max_qty",
                openapi.IN_QUERY,
                description="Quantité maximale.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "is_locked",
                openapi.IN_QUERY,
                description="Filtrer les mouvements verrouillés.",
                type=openapi.TYPE_BOOLEAN,
            ),
            openapi.Parameter(
                "stock_consumed",
                openapi.IN_QUERY,
                description="Filtrer selon la consommation du stock.",
                type=openapi.TYPE_BOOLEAN,
            ),
            openapi.Parameter(
                "ordering",
                openapi.IN_QUERY,
                description=(
                    "Tri : -occurred_at, occurred_at, -qty, qty, "
                    "-id, id, movement_type."
                ),
                type=openapi.TYPE_STRING,
            ),
        ],
        responses={
            200: InventoryMovementSerializer(many=True),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    # ========================================================
    # Helpers
    # ========================================================

    @staticmethod
    def _parse_positive_int(value, field_name):
        if value in (None, ""):
            return None

        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise ValidationError({
                field_name: "Une valeur entière est requise."
            })

        if parsed <= 0:
            raise ValidationError({
                field_name: "La valeur doit être supérieure à zéro."
            })

        return parsed

    @staticmethod
    def _parse_non_negative_int(value, field_name):
        if value in (None, ""):
            return None

        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise ValidationError({
                field_name: "Une valeur entière est requise."
            })

        if parsed < 0:
            raise ValidationError({
                field_name: (
                    "La valeur doit être supérieure ou égale à zéro."
                )
            })

        return parsed

    @staticmethod
    def _parse_boolean(value, field_name):
        if value in (None, ""):
            return None

        normalized = str(value).strip().lower()

        if normalized in {"1", "true", "yes", "oui"}:
            return True

        if normalized in {"0", "false", "no", "non"}:
            return False

        raise ValidationError({
            field_name: (
                "Valeur booléenne invalide. "
                "Utilisez true, false, 1 ou 0."
            )
        })

    @staticmethod
    def _parse_date(value, field_name):
        if not value:
            return None

        parsed = parse_date(value)

        if parsed is None:
            parsed_datetime = parse_datetime(value)

            if parsed_datetime is not None:
                parsed = parsed_datetime.date()

        if parsed is None:
            raise ValidationError({
                field_name: "Format invalide. Utilisez YYYY-MM-DD."
            })

        return parsed

    @staticmethod
    def _verified_profile(user, attribute):
        profile = getattr(user, attribute, None)

        if not profile:
            return None

        if not getattr(profile, "verifie", True):
            return None

        return profile

    # ========================================================
    # Scope selon le rôle
    # ========================================================

    def _apply_role_scope(self, queryset):
        user = self.request.user
        role = get_role_name(user)

        if role == ROLE_ADMIN:
            return queryset

        if role == ROLE_MANAGER:
            manager = self._verified_profile(
                user,
                "staff_manager_profile",
            )

            if not manager:
                return queryset.none()

            bijouterie_ids = manager.bijouteries.values_list(
                "id",
                flat=True,
            )

            return queryset.filter(
                Q(src_bijouterie_id__in=bijouterie_ids)
                | Q(dst_bijouterie_id__in=bijouterie_ids)
            )

        if role == ROLE_VENDOR:
            vendor = (
                self._verified_profile(user, "vendor_profile")
                or self._verified_profile(
                    user,
                    "staff_vendor_profile",
                )
            )

            if not vendor:
                return queryset.none()

            return queryset.filter(
                vendor_id=vendor.id,
            )

        if role == ROLE_CASHIER:
            cashier = self._verified_profile(
                user,
                "staff_cashier_profile",
            )

            if not cashier or not cashier.bijouterie_id:
                return queryset.none()

            return queryset.filter(
                Q(src_bijouterie_id=cashier.bijouterie_id)
                | Q(dst_bijouterie_id=cashier.bijouterie_id)
            )

        return queryset.none()

    # ========================================================
    # Queryset
    # ========================================================

    def get_queryset(self):
        queryset = (
            InventoryMovement.objects
            .select_related(
                "produit",
                "produit__categorie",
                "produit__modele",
                "produit__marque",
                "produit__purete",
                "produit_line",
                "produit_line__lot",
                "produit_line__lot__achat",
                "lot",
                "lot__achat",
                "achat",
                "achat__fournisseur",
                "facture",
                "vente",
                "vente_ligne",
                "vendor",
                "vendor__user",
                "vendor__bijouterie",
                "src_bijouterie",
                "dst_bijouterie",
                "created_by",
            )
        )

        queryset = self._apply_role_scope(queryset)

        params = self.request.query_params

        # ====================================================
        # Recherche globale
        # ====================================================

        q = (params.get("q") or "").strip()

        if q:
            queryset = queryset.filter(
                Q(produit__nom__icontains=q)
                | Q(produit__sku__icontains=q)
                | Q(lot__numero_lot__icontains=q)
                | Q(achat__numero_achat__icontains=q)
                | Q(facture__numero_facture__icontains=q)
                | Q(vente__numero_vente__icontains=q)
                | Q(reason__icontains=q)
                | Q(vendor__user__email__icontains=q)
                | Q(vendor__user__first_name__icontains=q)
                | Q(vendor__user__last_name__icontains=q)
            )

        # ====================================================
        # Type de mouvement
        # ====================================================

        movement_type = (
            params.get("movement_type") or ""
        ).strip()

        if movement_type:
            valid_types = {
                choice[0]
                for choice in MovementType.choices
            }

            if movement_type not in valid_types:
                raise ValidationError({
                    "movement_type": (
                        "Type invalide. Valeurs autorisées : "
                        + ", ".join(sorted(valid_types))
                    )
                })

            queryset = queryset.filter(
                movement_type=movement_type,
            )

        movement_types_raw = (
            params.get("movement_types") or ""
        ).strip()

        if movement_types_raw:
            movement_types = [
                value.strip()
                for value in movement_types_raw.split(",")
                if value.strip()
            ]

            valid_types = {
                choice[0]
                for choice in MovementType.choices
            }

            invalid_types = [
                value
                for value in movement_types
                if value not in valid_types
            ]

            if invalid_types:
                raise ValidationError({
                    "movement_types": (
                        "Types invalides : "
                        + ", ".join(invalid_types)
                    )
                })

            queryset = queryset.filter(
                movement_type__in=movement_types,
            )

        # ====================================================
        # Identifiants
        # ====================================================

        id_filters = {
            "produit_id": "produit_id",
            "produit_line_id": "produit_line_id",
            "lot_id": "lot_id",
            "achat_id": "achat_id",
            "facture_id": "facture_id",
            "vente_id": "vente_id",
            "vente_ligne_id": "vente_ligne_id",
            "vendor_id": "vendor_id",
        }

        for parameter_name, model_field in id_filters.items():
            value = self._parse_positive_int(
                params.get(parameter_name),
                parameter_name,
            )

            if value is not None:
                queryset = queryset.filter(
                    **{model_field: value}
                )

        numero_lot = (
            params.get("numero_lot") or ""
        ).strip()

        if numero_lot:
            queryset = queryset.filter(
                lot__numero_lot__icontains=numero_lot,
            )

        # ====================================================
        # Bijouterie
        # ====================================================

        bijouterie_id = self._parse_positive_int(
            params.get("bijouterie_id"),
            "bijouterie_id",
        )

        if bijouterie_id is not None:
            queryset = queryset.filter(
                Q(src_bijouterie_id=bijouterie_id)
                | Q(dst_bijouterie_id=bijouterie_id)
            )

        # ====================================================
        # Buckets
        # ====================================================

        valid_buckets = {
            choice[0]
            for choice in Bucket.choices
        }

        src_bucket = (
            params.get("src_bucket") or ""
        ).strip()

        if src_bucket:
            if src_bucket not in valid_buckets:
                raise ValidationError({
                    "src_bucket": (
                        "Bucket source invalide. Valeurs autorisées : "
                        + ", ".join(sorted(valid_buckets))
                    )
                })

            queryset = queryset.filter(
                src_bucket=src_bucket,
            )

        dst_bucket = (
            params.get("dst_bucket") or ""
        ).strip()

        if dst_bucket:
            if dst_bucket not in valid_buckets:
                raise ValidationError({
                    "dst_bucket": (
                        "Bucket destination invalide. "
                        "Valeurs autorisées : "
                        + ", ".join(sorted(valid_buckets))
                    )
                })

            queryset = queryset.filter(
                dst_bucket=dst_bucket,
            )

        # ====================================================
        # Dates
        # ====================================================

        date_from = self._parse_date(
            params.get("date_from"),
            "date_from",
        )

        date_to = self._parse_date(
            params.get("date_to"),
            "date_to",
        )

        if date_from and date_to and date_from > date_to:
            raise ValidationError({
                "date_to": (
                    "date_to doit être supérieure ou égale à date_from."
                )
            })

        if date_from:
            queryset = queryset.filter(
                occurred_at__date__gte=date_from,
            )

        if date_to:
            queryset = queryset.filter(
                occurred_at__date__lte=date_to,
            )

        # ====================================================
        # Quantités
        # ====================================================

        min_qty = self._parse_non_negative_int(
            params.get("min_qty"),
            "min_qty",
        )

        max_qty = self._parse_non_negative_int(
            params.get("max_qty"),
            "max_qty",
        )

        if (
            min_qty is not None
            and max_qty is not None
            and min_qty > max_qty
        ):
            raise ValidationError({
                "max_qty": (
                    "max_qty doit être supérieur ou égal à min_qty."
                )
            })

        if min_qty is not None:
            queryset = queryset.filter(
                qty__gte=min_qty,
            )

        if max_qty is not None:
            queryset = queryset.filter(
                qty__lte=max_qty,
            )

        # ====================================================
        # États
        # ====================================================

        is_locked = self._parse_boolean(
            params.get("is_locked"),
            "is_locked",
        )

        if is_locked is not None:
            queryset = queryset.filter(
                is_locked=is_locked,
            )

        stock_consumed = self._parse_boolean(
            params.get("stock_consumed"),
            "stock_consumed",
        )

        if stock_consumed is not None:
            queryset = queryset.filter(
                stock_consumed=stock_consumed,
            )

        # ====================================================
        # Tri
        # ====================================================

        ordering = (
            params.get("ordering")
            or "-occurred_at"
        ).strip()

        if ordering not in self.ALLOWED_ORDERING:
            raise ValidationError({
                "ordering": (
                    "Tri invalide. Valeurs autorisées : "
                    + ", ".join(sorted(self.ALLOWED_ORDERING))
                )
            })

        return queryset.order_by(ordering, "-id")
    


class ProduitLineWithInventoryListView(ListAPIView):
    """
    Liste détaillée des ProduitLine avec :

    - achat ;
    - fournisseur ;
    - lot ;
    - produit ;
    - stock magasin ;
    - stock vendeur ;
    - quantité vendue ;
    - quantité retournée ;
    - mouvements d'inventaire.

    Accès :
    - admin : toutes les ProduitLine ;
    - manager : ProduitLine de ses bijouteries ;
    - cashier : ProduitLine de sa bijouterie ;
    - vendor : ProduitLine présentes dans son stock vendeur.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ProduitLineWithInventorySerializer
    pagination_class = None

    ALLOWED_ORDERING = {
        "id",
        "-id",
        "lot__received_at",
        "-lot__received_at",
        "lot__numero_lot",
        "-lot__numero_lot",
        "produit__nom",
        "-produit__nom",
        "quantite",
        "-quantite",
        "stock_magasin",
        "-stock_magasin",
        "stock_vendeur",
        "-stock_vendeur",
        "stock_global",
        "-stock_global",
    }

    @swagger_auto_schema(
        operation_id="listProduitLinesWithInventory",
        operation_summary=(
            "Lister les ProduitLine avec stocks et mouvements"
        ),
        operation_description=(
            "Retourne une vue détaillée par ligne d'achat ProduitLine.\n\n"
            "Chaque ligne contient notamment :\n"
            "- l'achat et le fournisseur ;\n"
            "- le lot ;\n"
            "- le produit ;\n"
            "- le stock magasin ;\n"
            "- le stock affecté aux vendeurs ;\n"
            "- les quantités vendues ;\n"
            "- les mouvements d'inventaire associés.\n\n"
            "Le résultat est automatiquement limité selon le rôle "
            "de l'utilisateur connecté."
        ),
        manual_parameters=[
            openapi.Parameter(
                "q",
                openapi.IN_QUERY,
                description=(
                    "Recherche par produit, SKU, lot, achat, "
                    "fournisseur ou description."
                ),
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "year",
                openapi.IN_QUERY,
                description="Année de réception du lot.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "achat_id",
                openapi.IN_QUERY,
                description="Identifiant de l'achat.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "lot_id",
                openapi.IN_QUERY,
                description="Identifiant du lot.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "numero_lot",
                openapi.IN_QUERY,
                description="Recherche par numéro de lot.",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "produit_id",
                openapi.IN_QUERY,
                description="Identifiant du produit.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "produit_line_id",
                openapi.IN_QUERY,
                description="Identifiant de la ProduitLine.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "fournisseur_id",
                openapi.IN_QUERY,
                description="Identifiant du fournisseur.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                description="Identifiant de la bijouterie.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "vendor_id",
                openapi.IN_QUERY,
                description="Identifiant du vendeur.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "has_stock",
                openapi.IN_QUERY,
                description=(
                    "true : uniquement les lignes avec stock global positif."
                ),
                type=openapi.TYPE_BOOLEAN,
            ),
            openapi.Parameter(
                "movement_type",
                openapi.IN_QUERY,
                description=(
                    "ProduitLine ayant au moins un mouvement de ce type."
                ),
                type=openapi.TYPE_STRING,
                enum=[
                    choice[0]
                    for choice in MovementType.choices
                ],
            ),
            openapi.Parameter(
                "ordering",
                openapi.IN_QUERY,
                description=(
                    "Tri par défaut : -lot__received_at. "
                    "Exemples : produit__nom, -stock_global, "
                    "lot__numero_lot."
                ),
                type=openapi.TYPE_STRING,
            ),
        ],
        responses={
            200: ProduitLineWithInventorySerializer(many=True),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    # ========================================================
    # Helpers
    # ========================================================

    @staticmethod
    def _parse_positive_int(value, field_name):
        if value in (None, ""):
            return None

        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise ValidationError({
                field_name: "Une valeur entière est requise."
            })

        if parsed <= 0:
            raise ValidationError({
                field_name: (
                    "La valeur doit être supérieure à zéro."
                )
            })

        return parsed

    @staticmethod
    def _parse_year(value):
        if value in (None, ""):
            return None

        try:
            year = int(value)
        except (TypeError, ValueError):
            raise ValidationError({
                "year": "Une année valide est requise."
            })

        if year < 2000 or year > 2100:
            raise ValidationError({
                "year": (
                    "L'année doit être comprise entre 2000 et 2100."
                )
            })

        return year

    @staticmethod
    def _parse_boolean(value, field_name):
        if value in (None, ""):
            return None

        normalized = str(value).strip().lower()

        if normalized in {
            "1",
            "true",
            "yes",
            "oui",
        }:
            return True

        if normalized in {
            "0",
            "false",
            "no",
            "non",
        }:
            return False

        raise ValidationError({
            field_name: (
                "Valeur booléenne invalide. "
                "Utilisez true, false, 1 ou 0."
            )
        })

    @staticmethod
    def _verified_profile(user, attribute):
        profile = getattr(user, attribute, None)

        if not profile:
            return None

        if not getattr(profile, "verifie", True):
            return None

        return profile

    # ========================================================
    # Scope selon le rôle
    # ========================================================

    def _apply_role_scope(self, queryset):
        user = self.request.user
        role = get_role_name(user)

        if role == ROLE_ADMIN:
            return queryset

        if role == ROLE_MANAGER:
            manager = self._verified_profile(
                user,
                "staff_manager_profile",
            )

            if not manager:
                return queryset.none()

            bijouterie_ids = manager.bijouteries.values_list(
                "id",
                flat=True,
            )

            return queryset.filter(
                Q(stocks__bijouterie_id__in=bijouterie_ids)
                | Q(
                    vendor_stocks__bijouterie_id__in=
                    bijouterie_ids
                )
                | Q(
                    inventory_movements__src_bijouterie_id__in=
                    bijouterie_ids
                )
                | Q(
                    inventory_movements__dst_bijouterie_id__in=
                    bijouterie_ids
                )
            ).distinct()

        if role == ROLE_CASHIER:
            cashier = self._verified_profile(
                user,
                "staff_cashier_profile",
            )

            if not cashier or not cashier.bijouterie_id:
                return queryset.none()

            bijouterie_id = cashier.bijouterie_id

            return queryset.filter(
                Q(stocks__bijouterie_id=bijouterie_id)
                | Q(vendor_stocks__bijouterie_id=bijouterie_id)
                | Q(
                    inventory_movements__src_bijouterie_id=
                    bijouterie_id
                )
                | Q(
                    inventory_movements__dst_bijouterie_id=
                    bijouterie_id
                )
            ).distinct()

        if role == ROLE_VENDOR:
            vendor = (
                self._verified_profile(
                    user,
                    "vendor_profile",
                )
                or self._verified_profile(
                    user,
                    "staff_vendor_profile",
                )
            )

            if not vendor:
                return queryset.none()

            return queryset.filter(
                vendor_stocks__vendor_id=vendor.id,
            ).distinct()

        return queryset.none()

    # ========================================================
    # Queryset
    # ========================================================

    def get_queryset(self):
        params = self.request.query_params

        bijouterie_id = self._parse_positive_int(
            params.get("bijouterie_id"),
            "bijouterie_id",
        )

        vendor_id = self._parse_positive_int(
            params.get("vendor_id"),
            "vendor_id",
        )

        # ----------------------------------------------------
        # Sous-requête stock magasin
        # ----------------------------------------------------

        stock_magasin_queryset = (
            Stock.objects
            .filter(
                produit_line_id=OuterRef("pk"),
            )
        )

        if bijouterie_id is not None:
            stock_magasin_queryset = (
                stock_magasin_queryset.filter(
                    bijouterie_id=bijouterie_id,
                )
            )

        stock_magasin_subquery = (
            stock_magasin_queryset
            .values("produit_line_id")
            .annotate(total=Sum("en_stock"))
            .values("total")[:1]
        )

        # ----------------------------------------------------
        # Sous-requête entrées cumulées magasin
        # ----------------------------------------------------

        quantite_totale_queryset = (
            Stock.objects
            .filter(
                produit_line_id=OuterRef("pk"),
            )
        )

        if bijouterie_id is not None:
            quantite_totale_queryset = (
                quantite_totale_queryset.filter(
                    bijouterie_id=bijouterie_id,
                )
            )

        quantite_totale_subquery = (
            quantite_totale_queryset
            .values("produit_line_id")
            .annotate(total=Sum("quantite_totale"))
            .values("total")[:1]
        )

        # ----------------------------------------------------
        # Sous-requêtes stock vendeur
        # ----------------------------------------------------

        vendor_stock_queryset = (
            VendorStock.objects
            .filter(
                produit_line_id=OuterRef("pk"),
            )
        )

        if bijouterie_id is not None:
            vendor_stock_queryset = (
                vendor_stock_queryset.filter(
                    bijouterie_id=bijouterie_id,
                )
            )

        if vendor_id is not None:
            vendor_stock_queryset = (
                vendor_stock_queryset.filter(
                    vendor_id=vendor_id,
                )
            )

        quantite_allouee_subquery = (
            vendor_stock_queryset
            .values("produit_line_id")
            .annotate(total=Sum("quantite_allouee"))
            .values("total")[:1]
        )

        quantite_vendue_subquery = (
            vendor_stock_queryset
            .values("produit_line_id")
            .annotate(total=Sum("quantite_vendue"))
            .values("total")[:1]
        )

        # ----------------------------------------------------
        # Quantité retournée
        # ----------------------------------------------------

        returned_queryset = (
            InventoryMovement.objects
            .filter(
                produit_line_id=OuterRef("pk"),
                movement_type=MovementType.RETURN_IN,
            )
        )

        if bijouterie_id is not None:
            returned_queryset = returned_queryset.filter(
                dst_bijouterie_id=bijouterie_id,
            )

        returned_subquery = (
            returned_queryset
            .values("produit_line_id")
            .annotate(total=Sum("qty"))
            .values("total")[:1]
        )

        # ----------------------------------------------------
        # Queryset principal
        # ----------------------------------------------------

        queryset = (
            ProduitLine.objects
            .select_related(
                "produit",
                "produit__categorie",
                "produit__modele",
                "produit__marque",
                "produit__purete",
                "lot",
                "lot__achat",
                "lot__achat__fournisseur",
                "lot__achat__bijouterie",
            )
            .prefetch_related(
                "stocks",
                "stocks__bijouterie",
                "vendor_stocks",
                "vendor_stocks__vendor",
                "vendor_stocks__vendor__user",
                "vendor_stocks__bijouterie",
                "inventory_movements",
                "inventory_movements__src_bijouterie",
                "inventory_movements__dst_bijouterie",
                "inventory_movements__vendor",
                "inventory_movements__created_by",
            )
            .annotate(
                stock_magasin=Coalesce(
                    Subquery(
                        stock_magasin_subquery,
                        output_field=IntegerField(),
                    ),
                    Value(0),
                ),
                quantite_entree_cumulee=Coalesce(
                    Subquery(
                        quantite_totale_subquery,
                        output_field=IntegerField(),
                    ),
                    Value(0),
                ),
                quantite_allouee_vendeur=Coalesce(
                    Subquery(
                        quantite_allouee_subquery,
                        output_field=IntegerField(),
                    ),
                    Value(0),
                ),
                quantite_vendue=Coalesce(
                    Subquery(
                        quantite_vendue_subquery,
                        output_field=IntegerField(),
                    ),
                    Value(0),
                ),
                quantite_retournee=Coalesce(
                    Subquery(
                        returned_subquery,
                        output_field=IntegerField(),
                    ),
                    Value(0),
                ),
            )
            .annotate(
                stock_vendeur=(
                    F("quantite_allouee_vendeur")
                    - F("quantite_vendue")
                ),
                stock_global=(
                    F("stock_magasin")
                    + F("quantite_allouee_vendeur")
                    - F("quantite_vendue")
                ),
            )
        )

        queryset = self._apply_role_scope(queryset)

        # ====================================================
        # Filtres simples
        # ====================================================

        q = (params.get("q") or "").strip()

        if q:
            queryset = queryset.filter(
                Q(produit__nom__icontains=q)
                | Q(produit__sku__icontains=q)
                | Q(lot__numero_lot__icontains=q)
                | Q(lot__description__icontains=q)
                | Q(
                    lot__achat__numero_achat__icontains=q
                )
                | Q(
                    lot__achat__description__icontains=q
                )
                | Q(
                    lot__achat__fournisseur__nom__icontains=q
                )
                | Q(
                    lot__achat__fournisseur__prenom__icontains=q
                )
                | Q(
                    lot__achat__fournisseur__telephone__icontains=q
                )
            )

        year = self._parse_year(
            params.get("year"),
        )

        if year is not None:
            queryset = queryset.filter(
                lot__received_at__year=year,
            )

        id_filters = {
            "achat_id": "lot__achat_id",
            "lot_id": "lot_id",
            "produit_id": "produit_id",
            "produit_line_id": "id",
            "fournisseur_id": (
                "lot__achat__fournisseur_id"
            ),
        }

        for parameter_name, model_field in id_filters.items():
            value = self._parse_positive_int(
                params.get(parameter_name),
                parameter_name,
            )

            if value is not None:
                queryset = queryset.filter(
                    **{model_field: value}
                )

        numero_lot = (
            params.get("numero_lot") or ""
        ).strip()

        if numero_lot:
            queryset = queryset.filter(
                lot__numero_lot__icontains=numero_lot,
            )

        if bijouterie_id is not None:
            queryset = queryset.filter(
                Q(stocks__bijouterie_id=bijouterie_id)
                | Q(
                    vendor_stocks__bijouterie_id=
                    bijouterie_id
                )
                | Q(
                    inventory_movements__src_bijouterie_id=
                    bijouterie_id
                )
                | Q(
                    inventory_movements__dst_bijouterie_id=
                    bijouterie_id
                )
            )

        if vendor_id is not None:
            queryset = queryset.filter(
                vendor_stocks__vendor_id=vendor_id,
            )

        movement_type = (
            params.get("movement_type") or ""
        ).strip()

        if movement_type:
            valid_types = {
                choice[0]
                for choice in MovementType.choices
            }

            if movement_type not in valid_types:
                raise ValidationError({
                    "movement_type": (
                        "Type invalide. Valeurs autorisées : "
                        + ", ".join(sorted(valid_types))
                    )
                })

            queryset = queryset.filter(
                inventory_movements__movement_type=
                movement_type,
            )

        has_stock = self._parse_boolean(
            params.get("has_stock"),
            "has_stock",
        )

        if has_stock is True:
            queryset = queryset.filter(
                stock_global__gt=0,
            )

        elif has_stock is False:
            queryset = queryset.filter(
                stock_global=0,
            )

        # ====================================================
        # Tri
        # ====================================================

        ordering = (
            params.get("ordering")
            or "-lot__received_at"
        ).strip()

        if ordering not in self.ALLOWED_ORDERING:
            raise ValidationError({
                "ordering": (
                    "Tri invalide. Valeurs autorisées : "
                    + ", ".join(
                        sorted(self.ALLOWED_ORDERING)
                    )
                )
            })

        return queryset.distinct().order_by(
            ordering,
            "-id",
        )
        

class InventoryBijouterieView(APIView):
    """
    Résumé global de l'inventaire par bijouterie.

    Définitions :

    stock_magasin_net :
        Stock physiquement disponible dans la bijouterie.

        PURCHASE_IN
        + RETURN_IN
        + ADJUSTMENT entrée
        - VENDOR_ASSIGN
        - CANCEL_PURCHASE
        - ADJUSTMENT sortie

    stock_global_net :
        Stock encore détenu par la bijouterie,
        magasin + vendeurs.

        PURCHASE_IN
        + RETURN_IN
        + ADJUSTMENT entrée
        - SALE_OUT
        - CANCEL_PURCHASE
        - ADJUSTMENT sortie

    VENDOR_ASSIGN ne diminue donc pas le stock global :
    il déplace seulement le stock du magasin vers un vendeur.
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_id="inventoryByBijouterie",
        operation_summary="Résumé de l'inventaire par bijouterie",
        operation_description=(
            "Retourne les entrées, sorties et stocks nets "
            "pour chaque bijouterie accessible à l'utilisateur.\n\n"
            "Règles d'accès :\n"
            "- admin : toutes les bijouteries ;\n"
            "- manager : ses bijouteries ;\n"
            "- cashier : sa bijouterie ;\n"
            "- vendor : sa bijouterie.\n\n"
            "Filtres :\n"
            "- bijouterie_id ;\n"
            "- date_from ;\n"
            "- date_to ;\n"
            "- produit_id ;\n"
            "- lot_id ;\n"
            "- produit_line_id."
        ),
        manual_parameters=[
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                description="Identifiant de la bijouterie.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "date_from",
                openapi.IN_QUERY,
                description="Date minimale au format YYYY-MM-DD.",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
            ),
            openapi.Parameter(
                "date_to",
                openapi.IN_QUERY,
                description="Date maximale au format YYYY-MM-DD.",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
            ),
            openapi.Parameter(
                "produit_id",
                openapi.IN_QUERY,
                description="Identifiant du produit.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "lot_id",
                openapi.IN_QUERY,
                description="Identifiant du lot.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "produit_line_id",
                openapi.IN_QUERY,
                description="Identifiant de la ProduitLine.",
                type=openapi.TYPE_INTEGER,
            ),
        ],
        responses={
            200: InventoryBijouterieSerializer(many=True),
        },
    )
    def get(self, request, *args, **kwargs):
        params = request.query_params

        bijouterie_id = self._parse_positive_int(
            params.get("bijouterie_id"),
            "bijouterie_id",
        )

        produit_id = self._parse_positive_int(
            params.get("produit_id"),
            "produit_id",
        )

        lot_id = self._parse_positive_int(
            params.get("lot_id"),
            "lot_id",
        )

        produit_line_id = self._parse_positive_int(
            params.get("produit_line_id"),
            "produit_line_id",
        )

        date_from = self._parse_date(
            params.get("date_from"),
            "date_from",
        )

        date_to = self._parse_date(
            params.get("date_to"),
            "date_to",
        )

        if date_from and date_to and date_from > date_to:
            raise ValidationError({
                "date_to": (
                    "date_to doit être supérieure ou égale à date_from."
                )
            })

        bijouteries = self._get_accessible_bijouteries()

        if bijouterie_id is not None:
            bijouteries = bijouteries.filter(
                id=bijouterie_id,
            )

        movements = InventoryMovement.objects.all()

        if date_from:
            movements = movements.filter(
                occurred_at__date__gte=date_from,
            )

        if date_to:
            movements = movements.filter(
                occurred_at__date__lte=date_to,
            )

        if produit_id is not None:
            movements = movements.filter(
                produit_id=produit_id,
            )

        if lot_id is not None:
            movements = movements.filter(
                lot_id=lot_id,
            )

        if produit_line_id is not None:
            movements = movements.filter(
                produit_line_id=produit_line_id,
            )

        results = []

        for bijouterie in bijouteries.order_by("nom", "id"):
            summary = self._build_summary(
                bijouterie=bijouterie,
                movements=movements,
            )

            results.append(summary)

        serializer = InventoryBijouterieSerializer(
            results,
            many=True,
        )

        return Response(serializer.data)

    # ========================================================
    # Helpers de validation
    # ========================================================

    @staticmethod
    def _parse_positive_int(value, field_name):
        if value in (None, ""):
            return None

        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise ValidationError({
                field_name: "Une valeur entière est requise."
            })

        if parsed <= 0:
            raise ValidationError({
                field_name: (
                    "La valeur doit être supérieure à zéro."
                )
            })

        return parsed

    @staticmethod
    def _parse_date(value, field_name):
        if not value:
            return None

        from django.utils.dateparse import parse_date

        parsed = parse_date(value)

        if parsed is None:
            raise ValidationError({
                field_name: (
                    "Format de date invalide. Utilisez YYYY-MM-DD."
                )
            })

        return parsed

    @staticmethod
    def _verified_profile(user, attribute):
        profile = getattr(user, attribute, None)

        if not profile:
            return None

        if not getattr(profile, "verifie", True):
            return None

        return profile

    # ========================================================
    # Bijouteries accessibles selon le rôle
    # ========================================================

    def _get_accessible_bijouteries(self):
        user = self.request.user
        role = get_role_name(user)

        queryset = Bijouterie.objects.all()

        if role == ROLE_ADMIN:
            return queryset

        if role == ROLE_MANAGER:
            manager = self._verified_profile(
                user,
                "staff_manager_profile",
            )

            if not manager:
                return queryset.none()

            return queryset.filter(
                id__in=manager.bijouteries.values_list(
                    "id",
                    flat=True,
                )
            )

        if role == ROLE_CASHIER:
            cashier = self._verified_profile(
                user,
                "staff_cashier_profile",
            )

            if not cashier or not cashier.bijouterie_id:
                return queryset.none()

            return queryset.filter(
                id=cashier.bijouterie_id,
            )

        if role == ROLE_VENDOR:
            vendor = (
                self._verified_profile(
                    user,
                    "vendor_profile",
                )
                or self._verified_profile(
                    user,
                    "staff_vendor_profile",
                )
            )

            if not vendor or not vendor.bijouterie_id:
                return queryset.none()

            return queryset.filter(
                id=vendor.bijouterie_id,
            )

        raise PermissionDenied(
            "Vous n'êtes pas autorisé à consulter l'inventaire."
        )

    # ========================================================
    # Calcul des quantités
    # ========================================================

    @staticmethod
    def _sum_qty(queryset):
        return (
            queryset.aggregate(
                total=Coalesce(
                    Sum("qty"),
                    0,
                )
            )["total"]
            or 0
        )

    def _build_summary(self, *, bijouterie, movements):
        bijouterie_id = bijouterie.id

        # ----------------------------------------------------
        # Entrée fournisseur dans la bijouterie
        # ----------------------------------------------------

        purchase_in = self._sum_qty(
            movements.filter(
                movement_type=MovementType.PURCHASE_IN,
                src_bucket=Bucket.EXTERNAL,
                dst_bucket=Bucket.BIJOUTERIE,
                dst_bijouterie_id=bijouterie_id,
            )
        )

        # ----------------------------------------------------
        # Annulation d'achat : sortie de la bijouterie
        # ----------------------------------------------------

        cancel_purchase_out = self._sum_qty(
            movements.filter(
                movement_type=MovementType.CANCEL_PURCHASE,
                src_bucket=Bucket.BIJOUTERIE,
                dst_bucket=Bucket.EXTERNAL,
                src_bijouterie_id=bijouterie_id,
            )
        )

        # ----------------------------------------------------
        # Affectation au vendeur
        # ----------------------------------------------------

        vendor_assign_out = self._sum_qty(
            movements.filter(
                movement_type=MovementType.VENDOR_ASSIGN,
                src_bucket=Bucket.BIJOUTERIE,
                dst_bucket=Bucket.VENDOR,
                src_bijouterie_id=bijouterie_id,
            )
        )

        # ----------------------------------------------------
        # Vente depuis un vendeur de cette bijouterie
        # ----------------------------------------------------

        sale_out = self._sum_qty(
            movements.filter(
                movement_type=MovementType.SALE_OUT,
                src_bucket=Bucket.VENDOR,
                dst_bucket=Bucket.EXTERNAL,
                vendor__bijouterie_id=bijouterie_id,
            )
        )

        # ----------------------------------------------------
        # Retour client dans la bijouterie
        # ----------------------------------------------------

        return_in = self._sum_qty(
            movements.filter(
                movement_type=MovementType.RETURN_IN,
                src_bucket=Bucket.EXTERNAL,
                dst_bucket=Bucket.BIJOUTERIE,
                dst_bijouterie_id=bijouterie_id,
            )
        )

        # ----------------------------------------------------
        # Ajustement positif
        # ----------------------------------------------------

        adjustment_in = self._sum_qty(
            movements.filter(
                movement_type=MovementType.ADJUSTMENT,
                src_bucket=Bucket.EXTERNAL,
                dst_bucket=Bucket.BIJOUTERIE,
                dst_bijouterie_id=bijouterie_id,
            )
        )

        # ----------------------------------------------------
        # Ajustement négatif
        # ----------------------------------------------------

        adjustment_out = self._sum_qty(
            movements.filter(
                movement_type=MovementType.ADJUSTMENT,
                src_bucket=Bucket.BIJOUTERIE,
                dst_bucket=Bucket.EXTERNAL,
                src_bijouterie_id=bijouterie_id,
            )
        )

        # ----------------------------------------------------
        # Stock physiquement présent en magasin
        # ----------------------------------------------------

        stock_magasin_net = (
            purchase_in
            + return_in
            + adjustment_in
            - vendor_assign_out
            - cancel_purchase_out
            - adjustment_out
        )

        # ----------------------------------------------------
        # Stock global détenu par la bijouterie
        #
        # Une affectation vendeur ne diminue pas le stock global.
        # Une vente vendeur le diminue.
        # ----------------------------------------------------

        stock_global_net = (
            purchase_in
            + return_in
            + adjustment_in
            - sale_out
            - cancel_purchase_out
            - adjustment_out
        )

        return {
            "bijouterie_id": bijouterie_id,
            "bijouterie_nom": bijouterie.nom,

            "purchase_in": purchase_in,
            "cancel_purchase_out": cancel_purchase_out,

            "vendor_assign_out": vendor_assign_out,
            "sale_out": sale_out,

            "return_in": return_in,

            "adjustment_in": adjustment_in,
            "adjustment_out": adjustment_out,

            "stock_magasin_net": stock_magasin_net,
            "stock_global_net": stock_global_net,
        }
        


class InventoryVendorView(APIView):
    """
    Résumé d'inventaire par vendeur.

    Cycle pris en charge :

        BIJOUTERIE
            ↓ VENDOR_ASSIGN
        VENDOR
            ↓ SALE_OUT
        EXTERNAL

    Définitions :

    vendor_assign_in :
        quantité totale affectée au vendeur selon InventoryMovement.

    sale_out_vendor :
        quantité totale vendue par le vendeur selon InventoryMovement.

    quantite_allouee :
        somme de VendorStock.quantite_allouee.

    quantite_vendue :
        somme de VendorStock.quantite_vendue.

    stock_restant :
        quantite_allouee - quantite_vendue.

    RETURN_IN ne retourne pas dans le stock du vendeur.
    Le retour client retourne directement dans la bijouterie.
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_id="inventoryByVendor",
        operation_summary="Résumé de l'inventaire par vendeur",
        operation_description=(
            "Retourne le stock et les mouvements d'inventaire "
            "agrégés par vendeur.\n\n"
            "Règles d'accès :\n"
            "- admin : tous les vendeurs ;\n"
            "- manager : vendeurs de ses bijouteries ;\n"
            "- cashier : vendeurs de sa bijouterie ;\n"
            "- vendor : uniquement son propre inventaire.\n\n"
            "Filtres disponibles :\n"
            "- vendor_id ;\n"
            "- bijouterie_id ;\n"
            "- produit_id ;\n"
            "- produit_line_id ;\n"
            "- lot_id ;\n"
            "- date_from ;\n"
            "- date_to ;\n"
            "- has_stock."
        ),
        manual_parameters=[
            openapi.Parameter(
                "vendor_id",
                openapi.IN_QUERY,
                description="Identifiant du vendeur.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "bijouterie_id",
                openapi.IN_QUERY,
                description="Identifiant de la bijouterie.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "produit_id",
                openapi.IN_QUERY,
                description="Identifiant du produit.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "produit_line_id",
                openapi.IN_QUERY,
                description="Identifiant de la ProduitLine.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "lot_id",
                openapi.IN_QUERY,
                description="Identifiant du lot.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "date_from",
                openapi.IN_QUERY,
                description="Date minimale au format YYYY-MM-DD.",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
            ),
            openapi.Parameter(
                "date_to",
                openapi.IN_QUERY,
                description="Date maximale au format YYYY-MM-DD.",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_DATE,
            ),
            openapi.Parameter(
                "has_stock",
                openapi.IN_QUERY,
                description=(
                    "true : uniquement les vendeurs ayant "
                    "un stock restant positif."
                ),
                type=openapi.TYPE_BOOLEAN,
            ),
        ],
        responses={
            200: InventoryVendorSerializer(many=True),
        },
    )
    def get(self, request, *args, **kwargs):
        params = request.query_params

        vendor_id = self._parse_positive_int(
            params.get("vendor_id"),
            "vendor_id",
        )

        bijouterie_id = self._parse_positive_int(
            params.get("bijouterie_id"),
            "bijouterie_id",
        )

        produit_id = self._parse_positive_int(
            params.get("produit_id"),
            "produit_id",
        )

        produit_line_id = self._parse_positive_int(
            params.get("produit_line_id"),
            "produit_line_id",
        )

        lot_id = self._parse_positive_int(
            params.get("lot_id"),
            "lot_id",
        )

        date_from = self._parse_date(
            params.get("date_from"),
            "date_from",
        )

        date_to = self._parse_date(
            params.get("date_to"),
            "date_to",
        )

        has_stock = self._parse_boolean(
            params.get("has_stock"),
            "has_stock",
        )

        if date_from and date_to and date_from > date_to:
            raise ValidationError({
                "date_to": (
                    "date_to doit être supérieure ou égale à date_from."
                )
            })

        vendors = self._get_accessible_vendors()

        if vendor_id is not None:
            vendors = vendors.filter(id=vendor_id)

        if bijouterie_id is not None:
            vendors = vendors.filter(
                bijouterie_id=bijouterie_id,
            )

        movements = InventoryMovement.objects.all()

        vendor_stocks = VendorStock.objects.all()

        if produit_id is not None:
            movements = movements.filter(
                produit_id=produit_id,
            )

            vendor_stocks = vendor_stocks.filter(
                produit_line__produit_id=produit_id,
            )

        if produit_line_id is not None:
            movements = movements.filter(
                produit_line_id=produit_line_id,
            )

            vendor_stocks = vendor_stocks.filter(
                produit_line_id=produit_line_id,
            )

        if lot_id is not None:
            movements = movements.filter(
                lot_id=lot_id,
            )

            vendor_stocks = vendor_stocks.filter(
                produit_line__lot_id=lot_id,
            )

        if date_from:
            movements = movements.filter(
                occurred_at__date__gte=date_from,
            )

        if date_to:
            movements = movements.filter(
                occurred_at__date__lte=date_to,
            )

        results = []

        for vendor in vendors.select_related(
            "user",
            "bijouterie",
        ).order_by(
            "bijouterie__nom",
            "user__first_name",
            "user__last_name",
            "id",
        ):
            summary = self._build_summary(
                vendor=vendor,
                movements=movements,
                vendor_stocks=vendor_stocks,
            )

            if has_stock is True and summary["stock_restant"] <= 0:
                continue

            if has_stock is False and summary["stock_restant"] > 0:
                continue

            results.append(summary)

        serializer = InventoryVendorSerializer(
            results,
            many=True,
        )

        return Response(serializer.data)

    # ========================================================
    # Validation des paramètres
    # ========================================================

    @staticmethod
    def _parse_positive_int(value, field_name):
        if value in (None, ""):
            return None

        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise ValidationError({
                field_name: "Une valeur entière est requise."
            })

        if parsed <= 0:
            raise ValidationError({
                field_name: (
                    "La valeur doit être supérieure à zéro."
                )
            })

        return parsed

    @staticmethod
    def _parse_date(value, field_name):
        if not value:
            return None

        from django.utils.dateparse import parse_date

        parsed = parse_date(value)

        if parsed is None:
            raise ValidationError({
                field_name: (
                    "Format de date invalide. Utilisez YYYY-MM-DD."
                )
            })

        return parsed

    @staticmethod
    def _parse_boolean(value, field_name):
        if value in (None, ""):
            return None

        normalized = str(value).strip().lower()

        if normalized in {
            "1",
            "true",
            "yes",
            "oui",
        }:
            return True

        if normalized in {
            "0",
            "false",
            "no",
            "non",
        }:
            return False

        raise ValidationError({
            field_name: (
                "Valeur booléenne invalide. "
                "Utilisez true, false, 1 ou 0."
            )
        })

    @staticmethod
    def _verified_profile(user, attribute):
        profile = getattr(user, attribute, None)

        if not profile:
            return None

        if not getattr(profile, "verifie", True):
            return None

        return profile

    # ========================================================
    # Scope selon le rôle
    # ========================================================

    def _get_accessible_vendors(self):
        user = self.request.user
        role = get_role_name(user)

        queryset = Vendor.objects.all()

        if role == ROLE_ADMIN:
            return queryset

        if role == ROLE_MANAGER:
            manager = self._verified_profile(
                user,
                "staff_manager_profile",
            )

            if not manager:
                return queryset.none()

            bijouterie_ids = manager.bijouteries.values_list(
                "id",
                flat=True,
            )

            return queryset.filter(
                bijouterie_id__in=bijouterie_ids,
            )

        if role == ROLE_CASHIER:
            cashier = self._verified_profile(
                user,
                "staff_cashier_profile",
            )

            if not cashier or not cashier.bijouterie_id:
                return queryset.none()

            return queryset.filter(
                bijouterie_id=cashier.bijouterie_id,
            )

        if role == ROLE_VENDOR:
            vendor = (
                self._verified_profile(
                    user,
                    "vendor_profile",
                )
                or self._verified_profile(
                    user,
                    "staff_vendor_profile",
                )
            )

            if not vendor:
                return queryset.none()

            return queryset.filter(
                id=vendor.id,
            )

        raise PermissionDenied(
            "Vous n'êtes pas autorisé à consulter "
            "l'inventaire des vendeurs."
        )

    # ========================================================
    # Agrégation
    # ========================================================

    @staticmethod
    def _sum_qty(queryset):
        return (
            queryset.aggregate(
                total=Coalesce(
                    Sum("qty"),
                    0,
                )
            )["total"]
            or 0
        )

    @staticmethod
    def _sum_vendor_stock(queryset, field):
        return (
            queryset.aggregate(
                total=Coalesce(
                    Sum(field),
                    0,
                )
            )["total"]
            or 0
        )

    def _build_summary(
        self,
        *,
        vendor,
        movements,
        vendor_stocks,
    ):
        # ----------------------------------------------------
        # Quantité affectée au vendeur selon le journal
        # ----------------------------------------------------

        vendor_assign_in = self._sum_qty(
            movements.filter(
                movement_type=MovementType.VENDOR_ASSIGN,
                src_bucket=Bucket.BIJOUTERIE,
                dst_bucket=Bucket.VENDOR,
                vendor_id=vendor.id,
            )
        )

        # ----------------------------------------------------
        # Quantité vendue selon le journal
        # ----------------------------------------------------

        sale_out_vendor = self._sum_qty(
            movements.filter(
                movement_type=MovementType.SALE_OUT,
                src_bucket=Bucket.VENDOR,
                dst_bucket=Bucket.EXTERNAL,
                vendor_id=vendor.id,
            )
        )

        # ----------------------------------------------------
        # État courant du VendorStock
        # ----------------------------------------------------

        current_vendor_stocks = vendor_stocks.filter(
            vendor_id=vendor.id,
        )

        quantite_allouee = self._sum_vendor_stock(
            current_vendor_stocks,
            "quantite_allouee",
        )

        quantite_vendue = self._sum_vendor_stock(
            current_vendor_stocks,
            "quantite_vendue",
        )

        stock_restant = max(
            0,
            int(quantite_allouee)
            - int(quantite_vendue),
        )

        user = getattr(vendor, "user", None)

        vendor_nom = ""

        vendor_email = None

        if user:
            vendor_nom = (
                user.get_full_name().strip()
                or user.email
                or f"Vendeur #{vendor.id}"
            )

            vendor_email = user.email

        else:
            vendor_nom = f"Vendeur #{vendor.id}"

        bijouterie = getattr(
            vendor,
            "bijouterie",
            None,
        )

        return {
            "vendor_id": vendor.id,
            "vendor_nom": vendor_nom,
            "vendor_email": vendor_email,

            "bijouterie_id": (
                bijouterie.id
                if bijouterie
                else None
            ),
            "bijouterie_nom": (
                bijouterie.nom
                if bijouterie
                else None
            ),

            "vendor_assign_in": vendor_assign_in,
            "sale_out_vendor": sale_out_vendor,

            "quantite_allouee": quantite_allouee,
            "quantite_vendue": quantite_vendue,

            "stock_restant": stock_restant,
        }
    