
from textwrap import dedent

from django.core.exceptions import ValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import Q
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.permissions import IsAdminOrManager
from backend.query_scopes import BijouterieScopedQuerysetMixin
from backend.roles import ROLE_MANAGER, get_role_name
from stock.models import Stock
from vendor.models import Vendor

from .serializers import (MagasinProduitDisponibleSerializer,
                          StockDisponiblePourVendeurSerializer,
                          StockToVendorAssignmentInSerializer,
                          StockToVendorAssignmentOutSerializer)
from .services.magasin_to_vendor_service import assign_stock_to_vendor


class MagasinProduitDisponibleListView(
    BijouterieScopedQuerysetMixin,
    ListAPIView,
):
    """
    Liste des ProduitLine encore disponibles dans les magasins.

    Accès :
    - ADMIN : toutes les bijouteries
    - MANAGER : uniquement les bijouteries qu'il gère

    Filtre :
    - ?bijouterie_id=<id>
    """

    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]

    serializer_class = MagasinProduitDisponibleSerializer
    pagination_class = None

    scope_field = "bijouterie_id"

    queryset = (
        Stock.objects
        .select_related(
            "bijouterie",
            "produit_line",
            "produit_line__lot",
            "produit_line__produit",
            "produit_line__produit__purete",
            "produit_line__produit__marque",
        )
        .filter(
            en_stock__gt=0,
        )
    )

    @swagger_auto_schema(
        operation_id="listMagasinProduitsDisponibles",
        operation_summary=(
            "Lister les produits disponibles en magasin"
        ),
        operation_description=(
            "Retourne les lignes de stock dont la quantité "
            "disponible en magasin est supérieure à zéro.\n\n"
            "Accès :\n"
            "- ADMIN : toutes les bijouteries.\n"
            "- MANAGER : uniquement les bijouteries gérées.\n\n"
            "Filtre facultatif : `bijouterie_id`.\n\n"
            "Les résultats ne sont pas paginés."
        ),
        manual_parameters=[
            openapi.Parameter(
                name="bijouterie_id",
                in_=openapi.IN_QUERY,
                description=(
                    "Identifiant de la bijouterie à filtrer."
                ),
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
        ],
        responses={
            200: openapi.Response(
                description=(
                    "Liste des produits disponibles en magasin."
                ),
                schema=MagasinProduitDisponibleSerializer(
                    many=True,
                ),
            ),
            400: openapi.Response(
                description="Identifiant de bijouterie invalide.",
            ),
            401: openapi.Response(
                description="Authentification requise.",
            ),
            403: openapi.Response(
                description="Accès interdit.",
            ),
        },
        tags=["Stock / Magasin"],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        """
        Le mixin applique les permissions selon la bijouterie.
        """

        queryset = super().get_queryset()

        bijouterie_id = self.request.query_params.get(
            "bijouterie_id"
        )

        if bijouterie_id not in (None, ""):
            try:
                bijouterie_id = int(bijouterie_id)
            except (TypeError, ValueError):
                raise ValidationError({
                    "bijouterie_id": (
                        "bijouterie_id doit être un entier valide."
                    )
                })

            if bijouterie_id <= 0:
                raise ValidationError({
                    "bijouterie_id": (
                        "bijouterie_id doit être supérieur à zéro."
                    )
                })

            queryset = queryset.filter(
                bijouterie_id=bijouterie_id,
            )

        return queryset.order_by(
            "bijouterie__nom",
            "produit_line__lot__numero_lot",
            "produit_line__produit__sku",
            "produit_line_id",
        )



class BijouterieToVendorAssignmentView(APIView):
    """
    Affecte du stock disponible dans une bijouterie
    à un vendeur.

    Le vendeur doit appartenir à cette bijouterie.

    Toute l'affectation est gérée par le service métier
    assign_stock_to_vendor.
    """

    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]

    http_method_names = ["post"]

    # ========================================================
    # FORMATAGE DES ERREURS
    # ========================================================

    @staticmethod
    def format_assignment_error(exc):
        """
        Transforme une DjangoValidationError en réponse
        JSON compréhensible par Swagger et Angular.

        Gère notamment le format historique :

        {
            "stocks": [
                "1",
                "bague local",
                "30",
                "20",
                "Stock magasin insuffisant."
            ]
        }
        """

        if hasattr(exc, "message_dict"):
            errors = exc.message_dict
        else:
            return {
                "message": (
                    "Impossible d'effectuer l'affectation."
                ),
                "errors": exc.messages,
            }

        stocks = errors.get("stocks")

        if isinstance(stocks, list):

            # Format historique :
            # [produit_line_id, nom, demandee, disponible, erreur]

            if (
                len(stocks) == 5
                and str(stocks[4]).strip()
                == "Stock magasin insuffisant."
            ):
                try:
                    produit_line_id = int(stocks[0])
                    produit_nom = str(stocks[1])

                    quantite_demandee = int(stocks[2])
                    quantite_disponible = int(stocks[3])

                except (TypeError, ValueError):
                    pass

                else:
                    quantite_manquante = max(
                        0,
                        quantite_demandee
                        - quantite_disponible,
                    )

                    message = (
                        f"Impossible d'affecter "
                        f"{quantite_demandee} unité(s) "
                        f"du produit « {produit_nom} » "
                        f"au vendeur. "
                        f"Seulement {quantite_disponible} "
                        f"unité(s) sont disponibles "
                        f"en magasin. "
                        f"Il manque "
                        f"{quantite_manquante} unité(s)."
                    )

                    return {
                        "message": (
                            "Stock insuffisant "
                            "pour l'affectation."
                        ),
                        "code": "STOCK_INSUFFISANT",
                        "stocks": [
                            {
                                "produit_line_id": (
                                    produit_line_id
                                ),
                                "produit_nom": produit_nom,
                                "quantite_demandee": (
                                    quantite_demandee
                                ),
                                "quantite_disponible": (
                                    quantite_disponible
                                ),
                                "quantite_manquante": (
                                    quantite_manquante
                                ),
                                "message": message,
                            }
                        ],
                    }

        # Autres erreurs de validation :
        # conserver les détails originaux.

        return {
            "message": (
                "Impossible d'effectuer l'affectation."
            ),
            "code": "VALIDATION_ERROR",
            "errors": errors,
        }

    # ========================================================
    # SWAGGER
    # ========================================================

    @swagger_auto_schema(
        operation_id="assignMagasinStockToVendor",
        operation_summary=(
            "Affecter du stock magasin à un vendeur"
        ),
        operation_description=dedent(
            """
            Affecte du stock disponible dans une
            bijouterie à un vendeur.

            Effets :
            - Décrémente Stock.en_stock
            - Incrémente VendorStock.quantite_allouee
            - Crée un InventoryMovement(VENDOR_ASSIGN)

            Sécurité :
            - ADMIN : accès selon les permissions du projet
            - MANAGER : uniquement ses bijouteries

            Toutes les lignes sont traitées dans
            une transaction unique par le service métier.

            Si une ligne échoue, l'affectation
            entière est annulée.
            """
        ),
        tags=["Stock"],
        request_body=StockToVendorAssignmentInSerializer,
        responses={
            200: openapi.Response(
                description="Stock affecté avec succès.",
                schema=StockToVendorAssignmentOutSerializer,
            ),
            400: openapi.Response(
                description=(
                    "Données invalides, vendeur introuvable "
                    "ou stock insuffisant."
                ),
            ),
            403: openapi.Response(
                description="Accès interdit.",
            ),
        },
    )
    def post(self, request):

        # ====================================================
        # 1. VALIDATION DE LA REQUÊTE
        # ====================================================

        input_serializer = (
            StockToVendorAssignmentInSerializer(
                data=request.data
            )
        )

        input_serializer.is_valid(
            raise_exception=True
        )

        data = input_serializer.validated_data

        vendor_email = data["vendor_email"]

        # ====================================================
        # 2. RÔLE DE L'UTILISATEUR
        # ====================================================

        role = get_role_name(request.user)

        # ====================================================
        # 3. RECHERCHE DU VENDEUR
        # ====================================================

        vendor = (
            Vendor.objects
            .select_related(
                "bijouterie",
                "user",
            )
            .filter(
                user__email__iexact=vendor_email,
                verifie=True,
            )
            .first()
        )

        if vendor is None:
            return Response(
                {
                    "message": (
                        "Aucun vendeur actif n'a été trouvé "
                        "avec cette adresse e-mail."
                    ),
                    "code": "VENDEUR_INTROUVABLE",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ====================================================
        # 4. VÉRIFICATION DE LA BIJOUTERIE
        # ====================================================

        if not vendor.bijouterie_id:
            return Response(
                {
                    "message": (
                        "Ce vendeur n'est rattaché "
                        "à aucune bijouterie."
                    ),
                    "code": "VENDEUR_SANS_BIJOUTERIE",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ====================================================
        # 5. CONTRÔLE D'ACCÈS MANAGER
        # ====================================================

        if role == ROLE_MANAGER:

            manager_profile = getattr(
                request.user,
                "staff_manager_profile",
                None,
            )

            if (
                manager_profile is None
                or not getattr(
                    manager_profile,
                    "verifie",
                    True,
                )
            ):
                return Response(
                    {
                        "message": (
                            "Votre profil manager est "
                            "invalide ou désactivé."
                        ),
                        "code": "MANAGER_INVALIDE",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            manager_has_access = (
                manager_profile.bijouteries
                .filter(
                    pk=vendor.bijouterie_id
                )
                .exists()
            )

            if not manager_has_access:
                return Response(
                    {
                        "message": (
                            "Vous ne pouvez pas affecter "
                            "du stock à un vendeur "
                            "appartenant à une bijouterie "
                            "que vous ne gérez pas."
                        ),
                        "code": "BIJOUTERIE_NON_AUTORISEE",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        # ====================================================
        # 6. AFFECTATION DU STOCK
        # ====================================================

        try:
            result = assign_stock_to_vendor(
                vendor_email=vendor_email,
                lignes=data["lignes"],
                note=data.get("note", ""),
                user=request.user,
            )

        # ====================================================
        # 7. ERREURS MÉTIER DJANGO
        # ====================================================

        except DjangoValidationError as exc:

            return Response(
                self.format_assignment_error(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ====================================================
        # 8. ERREURS DRF
        # ====================================================

        except DRFValidationError as exc:

            return Response(
                {
                    "message": (
                        "Les données de l'affectation "
                        "sont invalides."
                    ),
                    "code": "VALIDATION_ERROR",
                    "errors": exc.detail,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ====================================================
        # 9. ERREURS D'INTÉGRITÉ
        # ====================================================

        except IntegrityError:

            return Response(
                {
                    "message": (
                        "Une erreur d'intégrité est "
                        "survenue pendant l'affectation "
                        "du stock."
                    ),
                    "code": "INTEGRITY_ERROR",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ====================================================
        # 10. SERIALIZER DE SORTIE
        # ====================================================

        output_serializer = (
            StockToVendorAssignmentOutSerializer(
                result
            )
        )

        # ====================================================
        # 11. RÉPONSE
        # ====================================================

        return Response(
            output_serializer.data,
            status=status.HTTP_200_OK,
        )


