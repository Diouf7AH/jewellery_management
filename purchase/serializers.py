from rest_framework import serializers

from store.serializers import ProduitSerializer

from .models import Achat, AchatProduit, Fournisseur


class FournisseurSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fournisseur
        fields = '__all__' 


class AchatProduitSerializer(serializers.ModelSerializer):
    # produit = ProduitSerializer()
    prix_achat_total_ttc = serializers.SerializerMethodField()
    produit_nom = serializers.SerializerMethodField()
    
    class Meta:
        model = AchatProduit
        fields = ['id', 'produit', 'produit_nom', 'quantite', 'prix_achat_gramme', 'tax', 'sous_total_prix_achat', 'prix_achat_total_ttc']
        read_only_fields = ['sous_total_prix_achat'] 
        
    def get_prix_achat_total_ttc(self, obj):
        return obj.prix_achat_total_ttc
    
    def get_produit_nom(self, obj):
        return obj.produit.nom if obj.produit else None


class AchatSerializer(serializers.ModelSerializer):
    fournisseur = FournisseurSerializer()
    produits = AchatProduitSerializer(many=True)
    class Meta:
        model = Achat

        fields = ['id', 'created_at',  'produits', 'fournisseur', 'montant_total_ht', 'montant_total_ttc']
        # fields = '__all__'
