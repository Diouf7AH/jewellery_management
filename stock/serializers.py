from rest_framework import serializers

from stock.models import Fournisseur, Stock
from store.models import Produit
from store.serializers import ProduitSerializer


class FournisseurSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Fournisseur
        fields = ['id', 'nom', 'prenom', 'address', 'telephone']

class StockSerializer(serializers.ModelSerializer):
    # produit = serializers.PrimaryKeyRelatedField(queryset=Produit.objects.all())
    # fournisseur = serializers.PrimaryKeyRelatedField(queryset=Fournisseur.objects.all())

    # produit = ProduitSerializer()
    # fournisseur = FournisseurSerializer()
    # quantite = serializers.IntegerField(default=0)
    # produit_id = serializers.IntegerField()
    # fournisseur_id = serializers.IntegerField()
    # quantite = serializers.IntegerField()
    # poids = serializers.DecimalField(max_digits=12, decimal_places=2)
    # prix_achat_gramm = serializers.DecimalField(max_digits=12, decimal_places=2)
    # total_prix_achat = serializers.DecimalField(max_digits=12, decimal_places=2)
    # date_ajout = serializers.DateTimeField()
    # tax_pourcentage = serializers.DecimalField(max_digits=12, decimal_places=2)
    class Meta:
        model = Stock
        #fields = ['id', 'produit_id', 'fournisseur_id','quantite', 'prix_achat_gramme', 'total_poids_achat', 'total_prix_achat', 'date_ajout', ]
        fields = ['id', 'produit', 'fournisseur', 'quantite', 'prix_achat_gramme', 'date_ajout',]
    
        