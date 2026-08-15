
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

    # Le modèle Stock possède directement bijouterie_id.
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

    def get_queryset(self):
        """
        Le super().get_queryset() applique automatiquement :

        - admin : accès global ;
        - manager : uniquement ses bijouteries ;
        - profil manager désactivé : aucun résultat.
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
            
        
class MagasinToVendorAssignmentView(APIView):
    """
    Affecte du stock disponible dans une bijouterie à un vendeur.

    Le vendeur doit obligatoirement appartenir à la bijouterie
    depuis laquelle le stock est affecté.
    """

    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]
    http_method_names = ["post"]

    @swagger_auto_schema(
        operation_id="assignMagasinStockToVendor",
        operation_summary=(
            "Affecter du stock magasin à un vendeur"
        ),
        operation_description=dedent(
            """
            Affecte du stock disponible dans une bijouterie à un vendeur.

            Effets :
            - Stock magasin :
              décrémente uniquement `Stock.en_stock`
            - Stock vendeur :
              incrémente `VendorStock.quantite_allouee`
            - Historique :
              crée un `InventoryMovement(VENDOR_ASSIGN)`

            `Stock.quantite_totale` reste inchangé, car il représente
            la quantité historiquement reçue dans la bijouterie.

            Sécurité :
            - ADMIN :
              peut affecter du stock à tous les vendeurs
            - MANAGER :
              peut affecter du stock uniquement aux vendeurs appartenant
              aux bijouteries qu'il gère

            Toutes les lignes sont traitées dans une transaction unique.
            Si une ligne échoue, toute l'affectation est annulée.
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
        input_serializer = StockToVendorAssignmentInSerializer(
            data=request.data
        )
        input_serializer.is_valid(raise_exception=True)

        data = input_serializer.validated_data
        vendor_email = data["vendor_email"]

        role = get_role_name(request.user)

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
                    "vendor_email": (
                        "Aucun vendeur n'a été trouvé avec cette adresse."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not vendor.bijouterie_id:
            return Response(
                {
                    "vendor_email": (
                        "Ce vendeur n'est rattaché à aucune bijouterie."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if role == ROLE_MANAGER:
            manager_profile = getattr(
                request.user,
                "staff_manager_profile",
                None,
            )

            if (
                manager_profile is None
                or not getattr(manager_profile, "verifie", True)
            ):
                return Response(
                    {
                        "detail": (
                            "Votre profil manager est invalide "
                            "ou désactivé."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            manager_has_access = (
                manager_profile.bijouteries
                .filter(pk=vendor.bijouterie_id)
                .exists()
            )

            if not manager_has_access:
                return Response(
                    {
                        "detail": (
                            "Vous ne pouvez pas affecter du stock "
                            "à un vendeur appartenant à une bijouterie "
                            "que vous ne gérez pas."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        try:
            result = assign_stock_to_vendor(
                vendor_email=vendor_email,
                lignes=data["lignes"],
                note=data.get("note", ""),
                user=request.user,
            )

        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                detail = exc.message_dict
            elif hasattr(exc, "messages"):
                detail = exc.messages
            else:
                detail = str(exc)

            return Response(
                detail,
                status=status.HTTP_400_BAD_REQUEST,
            )

        except DRFValidationError as exc:
            return Response(
                exc.detail,
                status=status.HTTP_400_BAD_REQUEST,
            )

        except IntegrityError:
            return Response(
                {
                    "detail": (
                        "Une erreur d'intégrité est survenue pendant "
                        "l'affectation du stock."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        output_serializer = StockToVendorAssignmentOutSerializer(
            result
        )

        return Response(
            output_serializer.data,
            status=status.HTTP_200_OK,
        )




class StockDisponiblePourVendeurView(
    BijouterieScopedQuerysetMixin,
    ListAPIView,
):
    permission_classes = [
        IsAuthenticated,
        IsAdminOrManager,
    ]

    serializer_class = StockDisponiblePourVendeurSerializer
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

    def get_queryset(self):
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
        )
        

