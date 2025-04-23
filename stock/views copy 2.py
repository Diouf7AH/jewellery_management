from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from store.models import Produit
from store.serializers import ProduitSerializer

from .models import (Fournisseur, LigneCommandeFournisseur, Produit, Stock,
                     StockCommande)
from .serializers import StockCommandeSerializer, StockSerializer


class StockCommandeAPIView(APIView):

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        """
        Create or update a stock order.
        This API will ensure that stock updates and order lines are atomically committed.
        """
        data = request.data

        # Create or update Product
        produit_data = data.get('produit')
        produit, created = Produit.objects.get_or_create(
            sku=produit_data['sku'],
            defaults=produit_data
        ) 
        # Créer stock
        stock = Stock.objects.create(produit=produit)
        
        # # Parse and create the StockOrder
        # fournisseur_data = data.get('fournisseur')
        # fournisseur = get_object_or_404(Fournisseur, id=fournisseur_data['id'])
        # stock_commande = StockCommande.objects.create(fournisseur=fournisseur)
        # Create or update Product
        fournisseur_data = data.get('fournisseur')
        fournisseur, created = fournisseur.objects.get_or_create(
            telephone=fournisseur_data['telephone'],
            defaults=fournisseur_data
        ) 
        # Créer stockCommande
        stock_commande = StockCommande.objects.create(fournisseur=fournisseur)

        # Process each order line
        commande_lignes_data = data.get('commande_lignes', [])
        for ligne_data in commande_lignes_data:
            produit_data = ligne_data.get('produit')
            produit = get_object_or_404(Produit, id=produit_data['id'])

            # Create SupplierOrderLine
            fournisseur_commande_ligne = LigneCommandeFournisseur.objects.create(
                stock_commande=stock_commande,
                produit=produit,
                quantite=ligne_data['quantite'],
                prix=ligne_data['prix']
            )

            # Update the stock (quantity)
            stock = Stock.objects.filter(produit=produit).first()
            # if stock:
            #     stock.quantite += ligne_data['quantite']
            #     stock.save()
            
            if stock and self.stock_commande.etat=='livré':
                stock.quantite += ligne_data['quantite']
                stock.save()

        # Return the serialized response
        stock_commande_serializer = StockCommandeSerializer(stock_commande)
        return Response(stock_commande_serializer.data, status=status.HTTP_201_CREATED)
    
    
class CommandeFournisseurView(APIView):
    
    def get(self, request, *args, **kwargs):
        """
        Get a single supplier order with all the details.
        """
        commande_id = kwargs.get('commande_id')
        try:
            commande = StockCommande.objects.get(id=commande_id)
            serializer = StockCommandeSerializer(commande)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except StockCommande.DoesNotExist:
            return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)