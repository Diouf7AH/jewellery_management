from rest_framework import serializers

from store.serializers import ProduitSerializer

from .models import Achat, AchatProduit, Fournisseur


class FournisseurSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fournisseur
        fields = '__all__' 


class AchatProduitSerializer(serializers.ModelSerializer):
    # produit = ProduitSerializer()
    class Meta:
        model = AchatProduit
        fields = ['id', 'produit', 'quantite', 'prix_achat_gramme', 'tax', 'sous_total_prix_achat']
        read_only_fields = ['sous_total_prix_achat'] 


class AchatSerializer(serializers.ModelSerializer):
    fournisseur = FournisseurSerializer()
    produits = AchatProduitSerializer(many=True)
    class Meta:
        model = Achat
        fields = ['id', 'created_at', 'produits', 'fournisseur',
                'montant_total_ht', 'montant_total_ttc']
        # fields = '__all__'
