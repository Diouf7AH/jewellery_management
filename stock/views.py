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
from django.db import transaction
from django.db.models import Sum
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import generics, permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from store.models import Bijouterie
from vendor.models import Vendor

from .models import Stock
from .serializers import (BijouterieToVendorInSerializer,
                          ReserveToBijouterieInSerializer, StockSerializer)
from .services import (transfer_bijouterie_to_vendor,
                       transfer_reserve_to_bijouterie_by_produit)
from .utils_role import get_manager_bijouterie_id, vendor_stock_filter

STATUS_CHOICES = ("reserved", "allocated", "in_stock", "all")
allowed_roles = ['admin', 'manager', 'vendeur']
# from backend.permissions import (ROLE_MANAGER, ROLE_VENDOR, IsAdminOrManager,
#                                  IsAdminOrManagerOrSelfVendor, get_role_name)

from backend.permissions import (ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR,
                                 IsAdminOrManagerOrSelfVendor, get_role_name)
from stock.utils_role import (get_manager_bijouterie_id,
                              get_vendor_bijouterie_id)

# class ReserveToBijouterieTransferView(APIView):
#     """
#         {
#             "bijouterie_id": 5,
#             "bijouterie_nom": "Sandaga",
#             "lignes": [
#                 {"produit_line_id": 123, "transfere": 3, "reserve_disponible": 12, "bijouterie_disponible": 3},
#                 {"produit_line_id": 124, "transfere": 2, "reserve_disponible": 8, "bijouterie_disponible": 5}
#             ],
#             "note": "Affectation vitrines"
#         }
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManagerOrSelfVendor]

#     @swagger_auto_schema(
#         operation_id="transferReserveToBijouterie",
#         operation_summary="Affecter du stock de la Réserve vers une Bijouterie",
#         request_body=ReserveToBijouterieInSerializer,
#         responses={200: "Résumé du transfert", 400: "Erreur de validation"},
#         tags=["Stock"],
#     )
#     def post(self, request):
#         s = ReserveToBijouterieInSerializer(data=request.data)
#         s.is_valid(raise_exception=True)
#         try:
#             res = transfer_reserve_to_bijouterie(
#                 bijouterie_id=s.validated_data["bijouterie_id"],
#                 mouvements=s.validated_data["lignes"],
#                 note=s.validated_data.get("note", "")
#             )
#         except ValueError as e:
#             return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
#         return Response(res, status=status.HTTP_200_OK)


# class ReserveToBijouterieTransferView(APIView):
#     """
#     POST /api/stocks/transfer/reserve-to-bijouterie/

#     Exemple payload:
#     {
#       "bijouterie_id": 1,
#       "lignes": [
#         {"produit_line_id": 123, "transfere": 3},
#         {"produit_line_id": 124, "transfere": 2}
#       ],
#       "note": "Affectation vitrines"
#     }

#     Réponse typique:
#     {
#       "bijouterie_id": 1,
#       "bijouterie_nom": "rio-gold",
#       "lignes": [
#         {"produit_line_id": 123, "transfere": 3, "reserve_disponible": 9, "bijouterie_allouee": 3, "bijouterie_disponible": 0},
#         {"produit_line_id": 124, "transfere": 2, "reserve_disponible": 6, "bijouterie_allouee": 2, "bijouterie_disponible": 0}
#       ],
#       "note": "Affectation vitrines"
#     }
#     """
#     permission_classes = [IsAuthenticated, IsAdminOrManagerOrSelfVendor]

#     @swagger_auto_schema(
#         operation_id="transferReserveToBijouterie",
#         operation_summary="Affecter du stock Réserve → Bijouterie (allocation ERP)",
#         operation_description=(
#             "ERP: Réserve.quantite_disponible -= qty ; "
#             "Bijouterie.quantite_allouee += qty (disponible inchangé). "
#             "Crée un InventoryMovement(ALLOCATE) par ligne. "
#             "⚠️ Pas de pagination."
#         ),
#         request_body=ReserveToBijouterieInSerializer,
#         responses={
#             200: openapi.Response("Résumé du transfert"),
#             400: openapi.Response("Erreur de validation"),
#             403: openapi.Response("Accès refusé"),
#         },
#         tags=["Stock"],
#     )
#     def post(self, request):
#         s = ReserveToBijouterieInSerializer(data=request.data)
#         s.is_valid(raise_exception=True)

#         try:
#             res = transfer_reserve_to_bijouterie(
#                 bijouterie_id=s.validated_data["bijouterie_id"],
#                 mouvements=s.validated_data["lignes"],
#                 note=s.validated_data.get("note", ""),
#                 user=request.user,
#             )
#         except ValueError as e:
#             return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

#         return Response(res, status=status.HTTP_200_OK)



class ReserveToBijouterieTransferView(APIView):
    """
    POST /api/stocks/transfer/reserve-to-bijouterie/

    Payload:
    {
      "bijouterie_id": 1,
      "lignes": [
        {"produit_id": 10, "transfere": 3},
        {"produit_id": 11, "transfere": 2}
      ],
      "note": "Affectation vitrines"
    }
    """
    permission_classes = [IsAuthenticated, IsAdminOrManagerOrSelfVendor]

    @swagger_auto_schema(
        operation_id="transferReserveToBijouterie",
        operation_summary="Affecter du stock Réserve → Bijouterie (FIFO par produit)",
        operation_description=(
            "ERP: Réserve.quantite_disponible -= qty ; "
            "Bijouterie.quantite_allouee += qty (disponible inchangé). "
            "Consommation FIFO sur les ProduitLine du produit. "
            "Crée un InventoryMovement(ALLOCATE) par sous-ligne consommée."
        ),
        request_body=ReserveToBijouterieInSerializer,
        responses={
            200: openapi.Response("Résumé du transfert"),
            400: openapi.Response("Erreur de validation"),
            403: openapi.Response("Accès refusé"),
        },
        tags=["Stock"],
    )
    def post(self, request):
        s = ReserveToBijouterieInSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        try:
            res = transfer_reserve_to_bijouterie_by_produit(
                bijouterie_id=s.validated_data["bijouterie_id"],
                lignes=s.validated_data["lignes"],
                note=s.validated_data.get("note", ""),
                user=request.user,
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(res, status=status.HTTP_200_OK)


# class BijouterieToVendorTransferView(APIView):
#     """
#         {
#             "vendor_email": vendeur@live.com,
#             "vendor_label": "Vendor john",
#             "bijouterie_id": 5,
#             "bijouterie_nom": "Sandaga",
#             "lignes": [
#                 { "produit_line_id": 123, "transfere": 2, "bijouterie_disponible": 10, "vendor_disponible": 2 },
#                 { "produit_line_id": 124, "transfere": 1, "bijouterie_disponible": 7,  "vendor_disponible": 1 }
#             ],
#             "note": "Dotation stand"
#         }
#     """
#     @swagger_auto_schema(
#         operation_summary="Affecter du stock d’une Bijouterie vers un Vendor",
#         request_body=BijouterieToVendorInSerializer,
#         tags=["Stock"],
#     )
#     def post(self, request):
#         s = BijouterieToVendorInSerializer(data=request.data)
#         s.is_valid(raise_exception=True)
#         res = transfer_bijouterie_to_vendor(
#             vendor_email=s.validated_data["vendor_email"],
#             mouvements=s.validated_data["lignes"],
#             note=s.validated_data.get("note", "")
#         )
#         return Response(res, status=200)

# class BijouterieToVendorTransferView(APIView):
#     permission_classes = [IsAuthenticated, IsAdminOrManager]

#     @swagger_auto_schema(
#         operation_summary="Transférer du stock d’une bijouterie vers un vendeur (via vendor_email)",
#         request_body=BijouterieToVendorInSerializer,
#         tags=["Stock"],
#     )
#     @transaction.atomic
#     def post(self, request):
#         ser = BijouterieToVendorInSerializer(data=request.data)
#         ser.is_valid(raise_exception=True)
#         data = ser.validated_data

#         email = data["vendor_email"]
#         lignes = data["lignes"]
#         note   = data.get("note", "")

#         # 1) Récupérer le vendeur via son user.email
#         vendor = Vendor.objects.select_related("user", "bijouterie").filter(
#             user__email__iexact=email
#         ).first()
#         if not vendor:
#             return Response(
#                 {"error": f"Aucun vendeur trouvé pour l’email {email}."},
#                 status=status.HTTP_404_NOT_FOUND,
#             )

#         if not getattr(vendor, "verifie", False):
#             return Response(
#                 {"error": "Ce vendeur est désactivé (verifie=False)."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         # 2) Appeler ton service de transfert
#         res = transfer_bijouterie_to_vendor(
#             vendor_id=vendor.id,
#             mouvements=lignes,
#             note=note,
#         )

#         # 3) Compléter la réponse avec quelques infos utiles
#         if not isinstance(res, dict):
#             res = {}

#         res.setdefault("vendor", {
#             "id": vendor.id,
#             "email": vendor.user.email if vendor.user else None,
#             "bijouterie_id": vendor.bijouterie_id,
#             "bijouterie_nom": getattr(vendor.bijouterie, "nom", None),
#         })

#         return Response(res, status=200)


# class BijouterieToVendorTransferView(APIView):
#     permission_classes = [permissions.IsAuthenticated, IsAdminOrManagerOrSelfVendor]

#     @swagger_auto_schema(
#         operation_summary="Transférer du stock d’une bijouterie vers un vendeur (par vendor_email)",
#         request_body=BijouterieToVendorInSerializer,
#         responses={
#             200: "Transfert réussi",
#             400: "Erreur de validation",
#             403: "Refusé",
#             404: "Introuvable",
#             409: "Conflit",
#         },
#         tags=["Stock"],
#     )
#     def post(self, request):
#         ser = BijouterieToVendorInSerializer(data=request.data)
#         ser.is_valid(raise_exception=True)
#         data = ser.validated_data

#         # 1) Récupérer le vendeur via vendor_email
#         email = data["vendor_email"].strip().lower()

#         try:
#             vendor = (
#                 Vendor.objects
#                 .select_related("user", "bijouterie")
#                 .get(user__email__iexact=email)
#             )
#         except Vendor.DoesNotExist:
#             return Response(
#                 {"error": f"Aucun vendeur associé à l'email {email}."},
#                 status=status.HTTP_404_NOT_FOUND,
#             )

#         if not getattr(vendor, "verifie", True):
#             return Response(
#                 {"error": "Ce vendeur est désactivé (verifie=False)."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         # 2) Appel du service métier (avec user pour InventoryMovement.created_by)
#         try:
#             res = transfer_bijouterie_to_vendor(
#                 vendor_id=vendor.id,
#                 mouvements=data["lignes"],
#                 note=data.get("note", ""),
#                 user=request.user,  # 👈 important pour journaliser qui a fait le transfert
#             )
#         except Bijouterie.DoesNotExist:
#             return Response(
#                 {"error": "Bijouterie introuvable."},
#                 status=status.HTTP_404_NOT_FOUND,
#             )
#         except ValidationError as e:
#             # erreurs levées par le service (ex: vendeur sans bijouterie, quantités invalides…)
#             payload = getattr(e, "message_dict", None) or {"detail": e.messages}
#             return Response(payload, status=status.HTTP_400_BAD_REQUEST)
#         except Exception as e:
#             return Response(
#                 {"detail": "Erreur inattendue", "error": str(e)},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         # 3) Compléter la réponse avec les infos du vendeur
#         if not isinstance(res, dict):
#             res = {}

#         res.setdefault(
#             "vendor",
#             {
#                 "id": vendor.id,
#                 "email": vendor.user.email if vendor.user else email,
#                 "full_name": (
#                     f"{(vendor.user.first_name or '').strip()} "
#                     f"{(vendor.user.last_name or '').strip()}"
#                     if vendor.user
#                     else ""
#                 ).strip(),
#                 "bijouterie_id": getattr(vendor.bijouterie, "id", None),
#                 "bijouterie_nom": getattr(vendor.bijouterie, "nom", None),
#             },
#         )

#         return Response(res, status=status.HTTP_200_OK)


class BijouterieToVendorTransferView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrManagerOrSelfVendor]

    @swagger_auto_schema(
        operation_summary="Transférer du stock d’une bijouterie vers un vendeur (par vendor_email)",
        request_body=BijouterieToVendorInSerializer,
        responses={200: "Transfert réussi", 400: "Erreur", 403: "Refusé", 404: "Introuvable", 409: "Conflit"},
        tags=["Stock"],
    )
    def post(self, request):
        ser = BijouterieToVendorInSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        email = data["vendor_email"].strip().lower()

        try:
            vendor = (
                Vendor.objects
                .select_related("user", "bijouterie")
                .get(user__email__iexact=email)
            )
        except Vendor.DoesNotExist:
            return Response({"error": f"Aucun vendeur associé à l'email {email}."}, status=404)

        if not getattr(vendor, "verifie", True):
            return Response({"error": "Ce vendeur est désactivé (verifie=False)."}, status=403)

        try:
            res = transfer_bijouterie_to_vendor(
                vendor_id=vendor.id,
                mouvements=data["lignes"],
                note=data.get("note", ""),
                user=request.user,
            )
        except ValidationError as e:
            payload = getattr(e, "message_dict", None) or {"detail": e.messages}
            return Response(payload, status=400)
        except Exception as e:
            return Response({"detail": "Erreur inattendue", "error": str(e)}, status=400)

        res.setdefault("vendor", {
            "id": vendor.id,
            "email": vendor.user.email if vendor.user else email,
            "full_name": (
                f"{(vendor.user.first_name or '').strip()} {(vendor.user.last_name or '').strip()}"
                if vendor.user else ""
            ).strip(),
            "bijouterie_id": getattr(vendor.bijouterie, "id", None),
            "bijouterie_nom": getattr(vendor.bijouterie, "nom", None),
        })
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


# # ---- Pagination par défaut ----
# class DefaultPagination(PageNumberPagination):
#     page_size = api_settings.PAGE_SIZE or 20
#     page_size_query_param = "page_size"
#     max_page_size = 100


# # ---- Vue principale ----
# class StockListView(APIView):
#     permission_classes = [permissions.IsAuthenticated, IsAdminOrManagerOrSelfVendor]
#     pagination_class = DefaultPagination

#     @swagger_auto_schema(
#         operation_summary="Lister les stocks (admin : tout | manager : sa bijouterie | vendor : son stock)",
#         operation_description=dedent("""
#             Retourne les lignes de stock.

#             **Règles d'accès**
#             - admin : accès à tout
#             - manager : accès **uniquement** aux stocks de **sa bijouterie**
#             - vendor : accès **uniquement** à **son stock** (par sa bijouterie)

#             **Filtre `status`**
#             - `reserved` : en réserve (bijouterie=NULL, disponible>0)
#             - `allocated` : alloués à une bijouterie (allouée>0)
#             - `in_stock` : tout ce qui a disponible>0 (réserve + alloués)
#             - `all` : sans filtre

#             Exemple de réponse (extrait) :
#             ```json
#             [
#                 {
#                     "id": 12,
#                     "produit_line": 5,
#                     "bijouterie": null,
#                     "bijouterie_nom": null,
#                     "quantite_allouee": 100,
#                     "quantite_disponible": 60,
#                     "status": "reserved",
#                     "created_at": "2025-10-22T10:00:00Z",
#                     "updated_at": "2025-10-22T10:10:00Z"
#                 },
#                 {
#                     "id": 13,
#                     "produit_line": 5,
#                     "bijouterie": 2,
#                     "bijouterie_nom": "Bijouterie Centre",
#                     "quantite_allouee": 40,
#                     "quantite_disponible": 30,
#                     "status": "allocated",
#                     "created_at": "2025-10-22T10:01:00Z",
#                     "updated_at": "2025-10-22T10:02:00Z"
#                 }
#             ]
#             ```
#         """),
#         manual_parameters=[
#             openapi.Parameter(
#                 name="status",
#                 in_=openapi.IN_QUERY,
#                 required=False,
#                 type=openapi.TYPE_STRING,
#                 enum=list(STATUS_CHOICES),
#                 default="in_stock",
#                 description="Filtre par statut",
#             ),
#             openapi.Parameter(
#                 name="page",
#                 in_=openapi.IN_QUERY,
#                 required=False,
#                 type=openapi.TYPE_INTEGER,
#                 description="Numéro de page (>=1)",
#             ),
#             openapi.Parameter(
#                 name="page_size",
#                 in_=openapi.IN_QUERY,
#                 required=False,
#                 type=openapi.TYPE_INTEGER,
#                 description="Taille de page (max 100)",
#             ),
#         ],
#         responses={
#             200: openapi.Response(
#                 "Liste des stocks",
#                 StockSerializer(many=True),
#                 examples={
#                     "application/json": [
#                         {
#                             "id": 12,
#                             "produit_line": 5,
#                             "bijouterie": None,
#                             "bijouterie_nom": None,
#                             "quantite_allouee": 100,
#                             "quantite_disponible": 60,
#                             "status": "reserved",
#                             "created_at": "2025-10-22T10:00:00Z",
#                             "updated_at": "2025-10-22T10:10:00Z",
#                         },
#                         {
#                             "id": 13,
#                             "produit_line": 5,
#                             "bijouterie": 2,
#                             "bijouterie_nom": "Bijouterie Centre",
#                             "quantite_allouee": 40,
#                             "quantite_disponible": 30,
#                             "status": "allocated",
#                             "created_at": "2025-10-22T10:01:00Z",
#                             "updated_at": "2025-10-22T10:02:00Z",
#                         },
#                     ]
#                 },
#             )
#         },
#         tags=["Stock"],
#     )
#     def get(self, request, *args, **kwargs):
#         # 1) Valider le paramètre
#         status_param = request.query_params.get("status", "in_stock")
#         if status_param not in STATUS_CHOICES:
#             raise ValidationError({"status": f"Valeur invalide. Choisir parmi {STATUS_CHOICES}."})

#         # 2) Base queryset
#         qs = Stock.objects.select_related("produit_line", "bijouterie").order_by("-id")

#         # 3) Périmètre par rôle
#         role = get_role_name(request.user)

#         # Manager → restreindre à SA bijouterie
#         if role == ROLE_MANAGER:
#             bj_id = get_manager_bijouterie_id(request.user)
#             qs = qs.filter(bijouterie_id=bj_id) if bj_id else qs.none()

#         # Vendor → restreindre à SON stock
#         if role == ROLE_VENDOR:
#             qs = qs.filter(vendor_stock_filter(request.user))

#         # 4) Filtre métier
#         if status_param == "reserved":
#             qs = qs.filter(bijouterie__isnull=True, quantite_disponible__gt=0)
#         elif status_param == "allocated":
#             qs = qs.filter(bijouterie__isnull=False, quantite_allouee__gt=0)
#         elif status_param == "in_stock":
#             qs = qs.filter(quantite_disponible__gt=0)
#         # "all" => pas de filtre supplémentaire

#         # 5) Pagination + réponse
#         paginator = self.pagination_class()
#         page = paginator.paginate_queryset(qs, request, view=self)
#         data = StockSerializer(page or qs, many=True).data
#         return paginator.get_paginated_response(data) if page is not None else Response(data)


# class StockListView(APIView):
#     permission_classes = [permissions.IsAuthenticated, IsAdminOrManagerOrSelfVendor]

#     @swagger_auto_schema(
#         operation_summary="Lister les stocks (admin : tout | manager : sa bijouterie | vendor : son stock)",
#         operation_description=dedent("""
#             Retourne les lignes de stock **sans pagination**.

#             **Règles d'accès**
#             - admin : accès à tout
#             - manager : accès **uniquement** aux stocks de **sa bijouterie**
#             - vendor : accès **uniquement** à **son stock** (par sa bijouterie)

#             **Filtre `status`**
#             - `reserved` : en réserve (bijouterie=NULL, disponible>0)
#             - `allocated` : alloués à une bijouterie (allouée>0)
#             - `in_stock` : tout ce qui a disponible>0 (réserve + alloués)
#             - `all` : sans filtre
#         """),
#         manual_parameters=[
#             openapi.Parameter(
#                 name="status",
#                 in_=openapi.IN_QUERY,
#                 required=False,
#                 type=openapi.TYPE_STRING,
#                 enum=list(STATUS_CHOICES),
#                 default="in_stock",
#                 description="Filtre par statut",
#             ),
#         ],
#         responses={
#             200: openapi.Response(
#                 "Liste des stocks",
#                 StockSerializer(many=True),
#                 examples={
#                     "application/json": [
#                         {
#                             "id": 12,
#                             "produit_line": 5,
#                             "bijouterie": None,
#                             "bijouterie_nom": None,
#                             "quantite_allouee": 100,
#                             "quantite_disponible": 60,
#                             "status": "reserved",
#                             "created_at": "2025-10-22T10:00:00Z",
#                             "updated_at": "2025-10-22T10:10:00Z",
#                         },
#                         {
#                             "id": 13,
#                             "produit_line": 5,
#                             "bijouterie": 2,
#                             "bijouterie_nom": "Bijouterie Centre",
#                             "quantite_allouee": 40,
#                             "quantite_disponible": 30,
#                             "status": "allocated",
#                             "created_at": "2025-10-22T10:01:00Z",
#                             "updated_at": "2025-10-22T10:02:00Z",
#                         },
#                     ]
#                 },
#             )
#         },
#         tags=["Stock"],
#     )
#     def get(self, request, *args, **kwargs):
#         # 1) Valider le paramètre
#         status_param = request.query_params.get("status", "in_stock")
#         if status_param not in STATUS_CHOICES:
#             raise ValidationError({"status": f"Valeur invalide. Choisir parmi {STATUS_CHOICES}."})

#         # 2) Base queryset
#         qs = Stock.objects.select_related("produit_line", "bijouterie").order_by("-id")

#         # 3) Périmètre par rôle
#         role = get_role_name(request.user)

#         # Manager → restreindre à SA bijouterie
#         if role == ROLE_MANAGER:
#             bj_id = get_manager_bijouterie_id(request.user)
#             qs = qs.filter(bijouterie_id=bj_id) if bj_id else qs.none()

#         # Vendor → restreindre à SON stock
#         if role == ROLE_VENDOR:
#             qs = qs.filter(vendor_stock_filter(request.user))

#         # 4) Filtre métier
#         if status_param == "reserved":
#             qs = qs.filter(bijouterie__isnull=True, quantite_disponible__gt=0)
#         elif status_param == "allocated":
#             qs = qs.filter(bijouterie__isnull=False, quantite_allouee__gt=0)
#         elif status_param == "in_stock":
#             qs = qs.filter(quantite_disponible__gt=0)
#         # "all" => pas de filtre supplémentaire

#         # 5) Réponse SANS pagination
#         serializer = StockSerializer(qs, many=True)
#         return Response(serializer.data)

class StockListView(APIView):
    """
    GET /api/stock/?status=in_stock|reserved|allocated|all

    - admin   : voit tout (réserve + bijouteries)
    - manager : voit uniquement sa bijouterie
    - vendor  : voit uniquement sa bijouterie
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminOrManagerOrSelfVendor]

    @swagger_auto_schema(
        operation_summary="Lister les stocks (admin : tout | manager/vendor : leur bijouterie)",
        operation_description=dedent("""
            Retourne les lignes de stock **sans pagination**.

            **Règles d'accès**
            - admin   : accès à tout
            - manager : accès uniquement aux stocks de sa bijouterie
            - vendor  : accès uniquement aux stocks de sa bijouterie
            
            * En une phrase :
            - reserved = stock central non affecté
            - in_stock = tout ce qui est réellement disponible, où qu’il soit
            
            **Filtre `status`**
            - `reserved`  : réserve (bijouterie=NULL, disponible>0, allouée=0) (admin only)
            - `allocated` : lignes affectées à une bijouterie (bijouterie!=NULL)
            - `in_stock`  : tout ce qui a disponible>0 (réserve + bijouteries)
            - `all`       : sans filtre
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
        ],
        responses={200: openapi.Response("Liste des stocks", StockSerializer(many=True))},
        tags=["Stock"],
    )
    def get(self, request, *args, **kwargs):
        # 1) Paramètre
        status_param = request.query_params.get("status", "in_stock")
        if status_param not in STATUS_CHOICES:
            raise ValidationError({"status": f"Valeur invalide. Choisir parmi {STATUS_CHOICES}."})

        # 2) Base queryset
        qs = Stock.objects.select_related("produit_line", "bijouterie").order_by("-id")

        # 3) Scope par rôle
        role = get_role_name(request.user)

        if role == ROLE_MANAGER:
            bj_id = get_manager_bijouterie_id(request.user)
            qs = qs.filter(bijouterie_id=bj_id) if bj_id else qs.none()

        elif role == ROLE_VENDOR:
            bj_id = get_vendor_bijouterie_id(request.user)
            qs = qs.filter(bijouterie_id=bj_id) if bj_id else qs.none()


        # ROLE_ADMIN => pas de filtre

        # 4) Filtre status
        if status_param == "reserved":
            # Réserve = globale => admin only (recommandé)
            if role != ROLE_ADMIN:
                return Response({"detail": "Accès refusé au stock réserve."}, status=403)
            qs = qs.filter(bijouterie__isnull=True, quantite_disponible__gt=0)

        elif status_param == "allocated":
            qs = qs.filter(bijouterie__isnull=False)

        elif status_param == "in_stock":
            qs = qs.filter(quantite_disponible__gt=0)

        # "all" => pas de filtre

        return Response(StockSerializer(qs, many=True).data)
    

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

# TOTAL_BY_CHOICES = ("disponible", "allouee")
# class StockSummaryView(APIView):
#     permission_classes = [permissions.IsAuthenticated, IsAdminOrManager]

#     @swagger_auto_schema(
#         operation_summary="Résumé des stocks (agrégats)",
#         operation_description=dedent("""
#             Renvoie des agrégats par catégorie : `reserved`, `allocated`, `in_stock`.

#             Par défaut (totaux = disponibles) :

#                 GET /api/stocks/summary
#                 Totaux basés sur allouée :
#                 GET /api/stocks/summary?total_by=allouee

#             **Accès**
#             - admin : toutes bijouteries
#             - manager : uniquement sa bijouterie

#             **Champs**
#             - `lignes` : nombre d’enregistrements Stock
#             - `allouee` : somme de `quantite_allouee`
#             - `disponible` : somme de `quantite_disponible`
#             - `produits_totaux` : somme de la colonne choisie par `total_by` (`disponible` par défaut)

#             Exemple :
#             ```json
#             {
#               "reserved":  {"lignes": 4, "allouee": 300, "disponible": 180, "produits_totaux": 180},
#               "allocated": {"lignes": 7, "allouee": 520, "disponible": 310, "produits_totaux": 310},
#               "in_stock":  {"lignes": 9, "allouee": 820, "disponible": 490, "produits_totaux": 490}
#             }
#             ```
#         """),
#         manual_parameters=[
#             openapi.Parameter(
#                 name="total_by",
#                 in_=openapi.IN_QUERY,
#                 required=False,
#                 type=openapi.TYPE_STRING,
#                 enum=list(TOTAL_BY_CHOICES),
#                 default="disponible",
#                 description="Colonne utilisée pour `produits_totaux`",
#             ),
#         ],
#         responses={200: openapi.Response("Résumé des stocks", StockSummarySerializer)},
#         tags=["Stock"],
#     )
#     def get(self, request):
#         # Périmètre
#         qs = Stock.objects.all()
#         if get_role_name(request.user) == ROLE_MANAGER:
#             bj_id = get_manager_bijouterie_id(request.user)
#             qs = qs.filter(bijouterie_id=bj_id) if bj_id else qs.none()

#         # Paramètre de total
#         total_by = request.query_params.get("total_by", "disponible")
#         if total_by not in TOTAL_BY_CHOICES:
#             total_by = "disponible"

#         def agg(qs_):
#             allouee = qs_.aggregate(Sum("quantite_allouee"))["quantite_allouee__sum"] or 0
#             dispo   = qs_.aggregate(Sum("quantite_disponible"))["quantite_disponible__sum"] or 0
#             produits_totaux = dispo if total_by == "disponible" else allouee
#             return {
#                 "lignes": qs_.count(),
#                 "allouee": allouee,
#                 "disponible": dispo,
#                 "produits_totaux": produits_totaux,
#             }

#         data = {
#             "reserved":  agg(qs.filter(bijouterie__isnull=True)),
#             "allocated": agg(qs.filter(bijouterie__isnull=False)),
#             "in_stock":  agg(qs.filter(quantite_disponible__gt=0)),
#         }
#         return Response(StockSummarySerializer(data).data)
