# from django.db import transaction
# from django.shortcuts import get_object_or_404
# from rest_framework import status
# from rest_framework.response import Response
# from rest_framework.views import APIView

# from store.models import Produit
# from store.serializers import ProduitSerializer

# from .models import (CommandeStock, Fournisseur, LigneCommandeStock, Produit,
#                      Stock)
# from .serializers import (CommandeStockSerializer, FournisseurSerializer,
#                           LigneCommandeStockSerializer, StockSerializer)

# class AddCommandeFournisseurAPIView(APIView):

#     @transaction.atomic
#     def post(self, request, *args, **kwargs):
#         """
#         Create or update a sfournisseur, manage stock, and create an ocommande atomically.
#         """
#         try:
#             # Handle creating or updating the sfournisseur
#             fournisseur_data = request.data.get('fournisseur')
#             fournisseur = self.create_or_update_fournisseur(fournisseur_data)

#             # Handle creating an ocommande and its ocommande lines
#             commande_stock_data = request.data.get('commande_stock')
#             commande_stock_serializer = CommandeStockSerializer(data=commande_stock_data)

#             if commande_stock_serializer.is_valid():
#                 commande_stock = commande_stock_serializer.save(fournisseur=fournisseur)

#                 # Handle each ocommande line
#                 ligne_commande_data = request.data.get('ligne_commande')
#                 for ligne_data in ligne_commande_data:
#                     self.create_ligne_commande(commande_stock, ligne_data)

#                 return Response(commande_stock_serializer.data, status=status.HTTP_201_CREATED)
#             else:
#                 return Response(commande_stock_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
#         except Exception as e:
#             # If any exception occurs, rollback the transaction
#             return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

#     def create_or_update_fournisseur(self, fournisseur_data):
#         """
#         Creates or updates a sfournisseur based on the provided data.
#         """
#         fournisseur, created = Fournisseur.objects.update_or_create(
#             id=fournisseur_data.get('id', None),
#             # phone=fournisseur_data.get('phone', None),
#             defaults=fournisseur_data
#             # defaults={
#             #     'name': fournisseur_data.get('name'),
#             # }
#         )
#         return fournisseur

#     def create_ligne_commande(self, commande_stock, line_data):
#         """
#         Creates an commande line and adjusts stock levels.
#         """
#         produit = Produit.objects.get(id=line_data['produit_id'])
#         stock = Stock.objects.get(produit=produit, fournisseur=commande_stock.fournisseur)

#         # if stock.quantite >= line_data['quantite']:
#         #     stock.quantite -= line_data['quantite']
#         #     stock.save()
            
#         if line_data['quantite'] > 0:
#             stock.quantite += line_data['quantite']
#             stock.save()

#             LigneCommandeStock.objects.create(
#                 commande_stock=commande_stock,
#                 produit=produit,
#                 quantite=line_data['quantite'],
#                 price=line_data['prix_par_unite']
#                 # price=produit.price
#             )
#         else:
#             raise ValueError(f"Not enough stock for produit {produit.nom}.")


# class CommandeFournisseurView(APIView):
    
#     def get(self, request, *args, **kwargs):
#         """
#         Get a single sfournisseur ocommande with all the details.
#         """
#         commande_stock_id = kwargs.get('commande_stock_id')
#         try:
#             commande_stock = CommandeStock.objects.get(id=commande_stock_id)
#             serializer = CommandeStockSerializer(commande_stock)
#             return Response(serializer.data, status=status.HTTP_200_OK)
#         except CommandeStock.DoesNotExist:
#             return Response({"detail": "Commande not found."}, status=status.HTTP_404_NOT_FOUND)



# class CommandeFournisseurView(APIView):
    
#     def get(self, request, *args, **kwargs):
#         """
#         Get a single supplier order with all the details.
#         """
#         commande_id = kwargs.get('commande_id')
#         try:
#             commande = LigneCommandeStock.objects.get(id=commande_id)
#             serializer = LigneCommandeStockSerializer(commande)
#             return Response(serializer.data, status=status.HTTP_200_OK)
#         except CommandeStock.DoesNotExist:
#             return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

from textwrap import dedent

from django.core.exceptions import ValidationError
from django.db.models import Sum
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import generics, permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from .models import Stock
from .serializers import (BijouterieToVendorInSerializer,
                          ReserveToBijouterieInSerializer, StockSerializer,
                          StockSummarySerializer)
from .services import (transfer_bijouterie_to_vendor,
                       transfer_reserve_to_bijouterie)
from .utils_role import get_manager_bijouterie_id, vendor_stock_filter

STATUS_CHOICES = ("reserved", "allocated", "in_stock", "all")
allowed_roles = ['admin', 'manager', 'vendeur']
from backend.permissions import (ROLE_MANAGER, ROLE_VENDOR, IsAdminOrManager,
                                 IsAdminOrManagerOrSelfVendor, get_role_name)


class ReserveToBijouterieTransferView(APIView):
    """
        {
            "bijouterie_id": 5,
            "bijouterie_nom": "Sandaga",
            "lignes": [
                {"produit_line_id": 123, "transfere": 3, "reserve_disponible": 12, "bijouterie_disponible": 3},
                {"produit_line_id": 124, "transfere": 2, "reserve_disponible": 8, "bijouterie_disponible": 5}
            ],
            "note": "Affectation vitrines"
        }
    """
    permission_classes = [IsAuthenticated, IsAdminOrManager]

    @swagger_auto_schema(
        operation_id="transferReserveToBijouterie",
        operation_summary="Affecter du stock de la Réserve vers une Bijouterie",
        request_body=ReserveToBijouterieInSerializer,
        responses={200: "Résumé du transfert", 400: "Erreur de validation"},
        tags=["Stocks"],
    )
    def post(self, request):
        s = ReserveToBijouterieInSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            res = transfer_reserve_to_bijouterie(
                bijouterie_id=s.validated_data["bijouterie_id"],
                mouvements=s.validated_data["lignes"],
                note=s.validated_data.get("note", "")
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(res, status=status.HTTP_200_OK)


class BijouterieToVendorTransferView(APIView):
    """
        {
            "vendor_id": 42,
            "vendor_label": "Vendor john",
            "bijouterie_id": 5,
            "bijouterie_nom": "Sandaga",
            "lignes": [
                { "produit_line_id": 123, "transfere": 2, "bijouterie_disponible": 10, "vendor_disponible": 2 },
                { "produit_line_id": 124, "transfere": 1, "bijouterie_disponible": 7,  "vendor_disponible": 1 }
            ],
            "note": "Dotation stand"
        }
    """
    @swagger_auto_schema(
        operation_summary="Affecter du stock d’une Bijouterie vers un Vendor",
        request_body=BijouterieToVendorInSerializer,
        tags=["Stocks"],
    )
    def post(self, request):
        s = BijouterieToVendorInSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        res = transfer_bijouterie_to_vendor(
            vendor_id=s.validated_data["vendor_id"],
            mouvements=s.validated_data["lignes"],
            note=s.validated_data.get("note", "")
        )
        return Response(res, status=200)
    

# class StockListView(generics.ListAPIView):
#     permission_classes = [permissions.IsAuthenticated]
#     serializer_class = StockSerializer

#     @swagger_auto_schema(
#         operation_summary="Lister les stocks",
#         operation_description=dedent("""
#             Retourne les lignes de stock. Filtre optionnel par `status` :
#             - `reserved` : en réserve (bijouterie=NULL, disponible>0)
#             - `allocated` : alloués à une bijouterie (allouée>0)
#             - `in_stock` : tout ce qui a disponible>0 (réserve + alloués)
#             - `all` : sans filtre

#             Exemple de réponse (extrait) :
#             ```json
#             [
#               {
#                 "id": 12,
#                 "produit_line": 5,
#                 "bijouterie": null,
#                 "bijouterie_nom": null,
#                 "quantite_allouee": 100,
#                 "quantite_disponible": 60,
#                 "status": "reserved",
#                 "created_at": "2025-10-22T10:00:00Z",
#                 "updated_at": "2025-10-22T10:10:00Z"
#               },
#               {
#                 "id": 13,
#                 "produit_line": 5,
#                 "bijouterie": 2,
#                 "bijouterie_nom": "Bijouterie Centre",
#                 "quantite_allouee": 40,
#                 "quantite_disponible": 30,
#                 "status": "allocated",
#                 "created_at": "2025-10-22T10:01:00Z",
#                 "updated_at": "2025-10-22T10:02:00Z"
#               }
#             ]
#             ```
#         """),
#         manual_parameters=[
#             openapi.Parameter(
#                 name="status",
#                 in_=openapi.IN_QUERY,
#                 required=False,
#                 schema=openapi.Schema(
#                     type=openapi.TYPE_STRING,
#                     enum=list(STATUS_CHOICES),
#                     default="in_stock",
#                     description="Filtre par statut"
#                 ),
#             ),
#         ],
#         responses={200: openapi.Response("Liste des stocks", StockSerializer(many=True))},
#         tags=["Stock"],
#     )
#     def get(self, request, *args, **kwargs):
#         # validation explicite du paramètre pour retourner 400 si invalide
#         status_param = request.query_params.get("status", "in_stock")
#         if status_param not in STATUS_CHOICES:
#             raise ValidationError({"status": f"Valeur invalide. Choisir parmi {STATUS_CHOICES}."})
#         return super().get(request, *args, **kwargs)

#     def get_queryset(self):
#         status_param = self.request.query_params.get("status", "in_stock")
#         qs = Stock.objects.select_related("produit_line", "bijouterie").order_by("-id")
#         if status_param == "reserved":
#             return qs.filter(bijouterie__isnull=True, quantite_disponible__gt=0)
#         if status_param == "allocated":
#             return qs.filter(bijouterie__isnull=False, quantite_allouee__gt=0)
#         if status_param == "in_stock":
#             return qs.filter(quantite_disponible__gt=0)
#         return qs  # "all"


# ---- Pagination par défaut ----
class DefaultPagination(PageNumberPagination):
    page_size = api_settings.PAGE_SIZE or 20
    page_size_query_param = "page_size"
    max_page_size = 100


# ---- Vue principale ----
class StockListView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrManagerOrSelfVendor]
    pagination_class = DefaultPagination

    @swagger_auto_schema(
        operation_summary="Lister les stocks (admin : tout | manager : sa bijouterie | vendor : son stock)",
        operation_description=dedent("""
            Retourne les lignes de stock.

            **Règles d'accès**
            - admin : accès à tout
            - manager : accès **uniquement** aux stocks de **sa bijouterie**
            - vendor : accès **uniquement** à **son stock** (par sa bijouterie)

            **Filtre `status`**
            - `reserved` : en réserve (bijouterie=NULL, disponible>0)
            - `allocated` : alloués à une bijouterie (allouée>0)
            - `in_stock` : tout ce qui a disponible>0 (réserve + alloués)
            - `all` : sans filtre
            
            Exemple de réponse (extrait) :
            ```json
            [
                {
                    "id": 12,
                    "produit_line": 5,
                    "bijouterie": null,
                    "bijouterie_nom": null,
                    "quantite_allouee": 100,
                    "quantite_disponible": 60,
                    "status": "reserved",
                    "created_at": "2025-10-22T10:00:00Z",
                    "updated_at": "2025-10-22T10:10:00Z"
                },
                {
                    "id": 13,
                    "produit_line": 5,
                    "bijouterie": 2,
                    "bijouterie_nom": "Bijouterie Centre",
                    "quantite_allouee": 40,
                    "quantite_disponible": 30,
                    "status": "allocated",
                    "created_at": "2025-10-22T10:01:00Z",
                    "updated_at": "2025-10-22T10:02:00Z"
                }
            ]
            ```
        """),
        manual_parameters=[
            openapi.Parameter(
                name="status",
                in_=openapi.IN_QUERY,
                required=False,
                type=openapi.TYPE_STRING,
                enum=list(STATUS_CHOICES),
                default="in_stock",
                description="Filtre par statut",
            ),
            openapi.Parameter(
                name="page",
                in_=openapi.IN_QUERY,
                required=False,
                type=openapi.TYPE_INTEGER,
                description="Numéro de page (>=1)",
            ),
            openapi.Parameter(
                name="page_size",
                in_=openapi.IN_QUERY,
                required=False,
                type=openapi.TYPE_INTEGER,
                description="Taille de page (max 100)",
            ),
        ],
        responses={
            200: openapi.Response(
                "Liste des stocks",
                StockSerializer(many=True),
                examples={
                    "application/json": [
                        {
                            "id": 12,
                            "produit_line": 5,
                            "bijouterie": None,
                            "bijouterie_nom": None,
                            "quantite_allouee": 100,
                            "quantite_disponible": 60,
                            "status": "reserved",
                            "created_at": "2025-10-22T10:00:00Z",
                            "updated_at": "2025-10-22T10:10:00Z",
                        },
                        {
                            "id": 13,
                            "produit_line": 5,
                            "bijouterie": 2,
                            "bijouterie_nom": "Bijouterie Centre",
                            "quantite_allouee": 40,
                            "quantite_disponible": 30,
                            "status": "allocated",
                            "created_at": "2025-10-22T10:01:00Z",
                            "updated_at": "2025-10-22T10:02:00Z",
                        },
                    ]
                },
            )
        },
        tags=["Stock"],
    )
    def get(self, request, *args, **kwargs):
        # 1) Valider le paramètre
        status_param = request.query_params.get("status", "in_stock")
        if status_param not in STATUS_CHOICES:
            raise ValidationError({"status": f"Valeur invalide. Choisir parmi {STATUS_CHOICES}."})

        # 2) Base queryset
        qs = Stock.objects.select_related("produit_line", "bijouterie").order_by("-id")

        # 3) Périmètre par rôle
        role = get_role_name(request.user)

        # Manager → restreindre à SA bijouterie
        if role == ROLE_MANAGER:
            bj_id = get_manager_bijouterie_id(request.user)
            qs = qs.filter(bijouterie_id=bj_id) if bj_id else qs.none()

        # Vendor → restreindre à SON stock
        if role == ROLE_VENDOR:
            qs = qs.filter(vendor_stock_filter(request.user))

        # 4) Filtre métier
        if status_param == "reserved":
            qs = qs.filter(bijouterie__isnull=True, quantite_disponible__gt=0)
        elif status_param == "allocated":
            qs = qs.filter(bijouterie__isnull=False, quantite_allouee__gt=0)
        elif status_param == "in_stock":
            qs = qs.filter(quantite_disponible__gt=0)
        # "all" => pas de filtre supplémentaire

        # 5) Pagination + réponse
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        data = StockSerializer(page or qs, many=True).data
        return paginator.get_paginated_response(data) if page is not None else Response(data)


# class StockSummaryView(APIView):
#     permission_classes = [permissions.IsAuthenticated]

#     @swagger_auto_schema(
#         operation_summary="Résumé des stocks (agrégats)",
#         operation_description=dedent("""
#             Renvoie des agrégats par catégorie : `reserved`, `allocated`, `in_stock`.
#             - `lignes` : nombre d’enregistrements Stock
#             - `allouee` : somme de `quantite_allouee`
#             - `disponible` : somme de `quantite_disponible`

#             Exemple de réponse :
#             ```json
#             {
#                 "reserved":  {"lignes": 4, "allouee": 300, "disponible": 180},
#                 "allocated": {"lignes": 7, "allouee": 520, "disponible": 310},
#                 "in_stock":  {"lignes": 9, "allouee": 820, "disponible": 490}
#             }
#             ```
#         """),
#         responses={200: openapi.Response("Résumé des stocks", StockSummarySerializer)},
#     )
#     def get(self, request):
#         base = Stock.objects.all()

#         def agg(qs):
#             return {
#                 "lignes": qs.count(),
#                 "allouee": qs.aggregate(Sum("quantite_allouee"))["quantite_allouee__sum"] or 0,
#                 "disponible": qs.aggregate(Sum("quantite_disponible"))["quantite_disponible__sum"] or 0,
#             }

#         data = {
#             "reserved":  agg(base.filter(bijouterie__isnull=True)),
#             "allocated": agg(base.filter(bijouterie__isnull=False)),
#             "in_stock":  agg(base.filter(quantite_disponible__gt=0)),
#         }
#         return Response(StockSummarySerializer(data).data)

TOTAL_BY_CHOICES = ("disponible", "allouee")
class StockSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrManager]

    @swagger_auto_schema(
        operation_summary="Résumé des stocks (agrégats)",
        operation_description=dedent("""
            Renvoie des agrégats par catégorie : `reserved`, `allocated`, `in_stock`.
            
            Par défaut (totaux = disponibles) :
                
                GET /api/stocks/summary
                Totaux basés sur allouée :
                GET /api/stocks/summary?total_by=allouee

            **Accès**
            - admin : toutes bijouteries
            - manager : uniquement sa bijouterie

            **Champs**
            - `lignes` : nombre d’enregistrements Stock
            - `allouee` : somme de `quantite_allouee`
            - `disponible` : somme de `quantite_disponible`
            - `produits_totaux` : somme de la colonne choisie par `total_by` (`disponible` par défaut)

            Exemple :
            ```json
            {
              "reserved":  {"lignes": 4, "allouee": 300, "disponible": 180, "produits_totaux": 180},
              "allocated": {"lignes": 7, "allouee": 520, "disponible": 310, "produits_totaux": 310},
              "in_stock":  {"lignes": 9, "allouee": 820, "disponible": 490, "produits_totaux": 490}
            }
            ```
        """),
        manual_parameters=[
            openapi.Parameter(
                name="total_by",
                in_=openapi.IN_QUERY,
                required=False,
                type=openapi.TYPE_STRING,
                enum=list(TOTAL_BY_CHOICES),
                default="disponible",
                description="Colonne utilisée pour `produits_totaux`",
            ),
        ],
        responses={200: openapi.Response("Résumé des stocks", StockSummarySerializer)},
        tags=["Stock"],
    )
    def get(self, request):
        # Périmètre
        qs = Stock.objects.all()
        if get_role_name(request.user) == ROLE_MANAGER:
            bj_id = get_manager_bijouterie_id(request.user)
            qs = qs.filter(bijouterie_id=bj_id) if bj_id else qs.none()

        # Paramètre de total
        total_by = request.query_params.get("total_by", "disponible")
        if total_by not in TOTAL_BY_CHOICES:
            total_by = "disponible"

        def agg(qs_):
            allouee = qs_.aggregate(Sum("quantite_allouee"))["quantite_allouee__sum"] or 0
            dispo   = qs_.aggregate(Sum("quantite_disponible"))["quantite_disponible__sum"] or 0
            produits_totaux = dispo if total_by == "disponible" else allouee
            return {
                "lignes": qs_.count(),
                "allouee": allouee,
                "disponible": dispo,
                "produits_totaux": produits_totaux,
            }

        data = {
            "reserved":  agg(qs.filter(bijouterie__isnull=True)),
            "allocated": agg(qs.filter(bijouterie__isnull=False)),
            "in_stock":  agg(qs.filter(quantite_disponible__gt=0)),
        }
        return Response(StockSummarySerializer(data).data)
    