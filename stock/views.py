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

from backend.permissions import IsAdminOrManager, IsAdminOrManagerOrVendor
from backend.query_scopes import scope_bijouterie_q
from backend.roles import ROLE_ADMIN, ROLE_MANAGER, get_role_name
from stock.models import Stock
from stock.serializers import StockSerializer
from vendor.models import Vendor

from .serializers import (MagasinProduitDisponibleSerializer,
                          MagasinToVendorInSerializer,
                          MagasinToVendorOutSerializer)
from .services.magasin_to_vendor_service import transfer_magasin_to_vendor


class MagasinProduitDisponibleListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MagasinProduitDisponibleSerializer

    def get_queryset(self):
        user = self.request.user
        role = get_role_name(user)

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
                is_reserve=False,
                bijouterie__isnull=False,
                en_stock__gt=0,
            )
            .order_by("bijouterie__nom", "produit_line__lot__numero_lot", "produit_line__produit__sku")
        )

        bijouterie_id = self.request.query_params.get("bijouterie_id")

        if role == ROLE_ADMIN:
            if bijouterie_id:
                queryset = queryset.filter(bijouterie_id=bijouterie_id)
            return queryset

        if role == ROLE_MANAGER:
            manager = getattr(user, "staff_manager_profile", None)
            if not manager:
                return Stock.objects.none()

            manager_bijouteries = manager.bijouteries.all()

            queryset = queryset.filter(bijouterie__in=manager_bijouteries)

            if bijouterie_id:
                queryset = queryset.filter(bijouterie_id=bijouterie_id)

            return queryset

        return Stock.objects.none()


class MagasinToVendorTransferView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    http_method_names = ["post"]

    @swagger_auto_schema(
        operation_id="magasinToVendorTransfer",
        operation_summary="Transférer du stock Magasin vers un vendeur",
        operation_description=dedent("""
            Effectue un transfert Magasin/Bijouterie → Vendeur.

            Effets :
            - Magasin : décrémente Stock(en_stock) et quantite_disponible
            - Vendeur : incrémente VendorStock.quantite_allouee
            - Audit : crée InventoryMovement(VENDOR_ASSIGN)

            Sécurité :
            - admin : toutes bijouteries
            - manager : uniquement vendeurs appartenant à ses bijouteries
        """),
        tags=["Stock"],
        request_body=MagasinToVendorInSerializer,
        responses={
            200: MagasinToVendorOutSerializer,
            400: openapi.Response(description="ValidationError / stock insuffisant"),
            403: openapi.Response(description="Forbidden"),
        },
    )
    def post(self, request):
        serializer = MagasinToVendorInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        role = (get_role_name(request.user) or "").lower()

        vendor = (
            Vendor.objects
            .select_related("bijouterie", "user")
            .filter(user__email__iexact=data["vendor_email"])
            .first()
        )

        if not vendor:
            return Response(
                {"detail": "Vendeur introuvable."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not vendor.bijouterie_id:
            return Response(
                {"detail": "Ce vendeur n'est rattaché à aucune bijouterie."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if role == ROLE_MANAGER:
            manager_profile = getattr(request.user, "staff_manager_profile", None)

            if not manager_profile or (
                hasattr(manager_profile, "verifie") and not manager_profile.verifie
            ):
                return Response(
                    {"detail": "Profil manager invalide."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if not manager_profile.bijouteries.filter(id=vendor.bijouterie_id).exists():
                return Response(
                    {
                        "detail": (
                            "Vous ne pouvez pas affecter un vendeur "
                            "hors de vos bijouteries."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        try:
            result = transfer_magasin_to_vendor(
                vendor_email=data["vendor_email"],
                lignes=data["lignes"],
                note=data.get("note", ""),
                user=request.user,
            )

        except (DjangoValidationError, DRFValidationError) as e:
            detail = (
                getattr(e, "message_dict", None)
                or getattr(e, "detail", None)
                or getattr(e, "messages", None)
                or str(e)
            )

            return Response(
                {"detail": detail},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except IntegrityError as e:
            return Response(
                {"detail": f"Erreur base de données: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            return Response(
                {"detail": f"Erreur serveur: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(result, status=status.HTTP_200_OK)



class StockDisponiblePourVendeurView(APIView):
    """
    GET /api/stocks/available-for-vendor/

    Liste claire des ProduitLine disponibles en réserve pour affectation vendeur.
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]
    http_method_names = ["get"]

    @swagger_auto_schema(
        operation_summary="Lister les ProduitLine disponibles à affecter à un vendeur",
        manual_parameters=[
            openapi.Parameter("q", openapi.IN_QUERY, type=openapi.TYPE_STRING, required=False),
            openapi.Parameter("produit_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, required=False),
            openapi.Parameter("lot_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, required=False),
        ],
        tags=["Stock"],
        responses={200: openapi.Response("OK")},
    )
    def get(self, request):
        q = (request.GET.get("q") or "").strip()
        produit_id = request.GET.get("produit_id")
        lot_id = request.GET.get("lot_id")

        qs = (
            Stock.objects
            .select_related(
                "produit_line",
                "produit_line__produit",
                "produit_line__lot",
            )
            .filter(
                is_reserve=True,
                bijouterie__isnull=True,
                en_stock__gt=0,
            )
            .order_by(
                "produit_line__lot__received_at",
                "produit_line_id",
            )
        )

        if produit_id:
            qs = qs.filter(produit_line__produit_id=produit_id)

        if lot_id:
            qs = qs.filter(produit_line__lot_id=lot_id)

        if q:
            qs = qs.filter(
                Q(produit_line__produit__nom__icontains=q) |
                Q(produit_line__produit__sku__icontains=q) |
                Q(produit_line__lot__numero_lot__icontains=q) |
                Q(produit_line__lot__lot_code__icontains=q)
            )

        results = []

        for stock in qs:
            pl = stock.produit_line
            produit = getattr(pl, "produit", None)
            lot = getattr(pl, "lot", None)

            results.append({
                "produit_line_id": pl.id,
                "produit_id": produit.id if produit else None,
                "produit_nom": produit.nom if produit else None,
                "sku": getattr(produit, "sku", None) if produit else None,

                "lot_id": lot.id if lot else None,
                "lot": (
                    getattr(lot, "numero_lot", None)
                    or getattr(lot, "lot_code", None)
                ),

                "stock_disponible": int(stock.en_stock or 0),
                "stock_total": int(stock.quantite_disponible or 0),
            })

        return Response({
            "count": len(results),
            "results": results,
        })
        



