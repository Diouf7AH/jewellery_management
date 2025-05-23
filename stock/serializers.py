from rest_framework import serializers

from stock.models import Stock
from store.models import Produit
from store.serializers import ProduitSerializer

# class FournisseurSerializer(serializers.ModelSerializer):
    
#     class Meta:
#         model = Fournisseur
#         fields = ['id', 'nom', 'prenom', 'address', 'telephone']


class StockSerializer(serializers.ModelSerializer):
    # produit = ProduitSerializer()
    # fournisseur = FournisseurSerializer()
    class Meta:
        model = Stock
        fields = '__all__'


# class LigneCommandeStockSerializer(serializers.ModelSerializer):
#     produit = ProduitSerializer()

#     class Meta:
#         model = LigneCommandeStock
#         fields = '__all__'


# class CommandeStockSerializer(serializers.ModelSerializer):
#     fournisseur = FournisseurSerializer()
#     lignes_commande = LigneCommandeStockSerializer(many=True)

#     class Meta:
#         model = CommandeStock
#         # fields = '__all__'
#         fields = ['id', 'fournisseur', 'lignes_commande', 'etat']