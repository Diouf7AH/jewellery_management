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
