from rest_framework import serializers
from .models import Client, Vente, VenteProduit, Facture, Paiement
from store.serializers import ProduitSerializer
class ClientSerializers(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['id', 'nom', 'prenom',]


class VenteProduitSerializer(serializers.ModelSerializer):
    # produit = ProduitSerializer()
    # class Meta:
    #     model = VenteProduit
    #     fields = ['id', 'produit', 'quantite', 'prix_vente_grammes', 'sous_total_prix_vent', 'tax', 'tax_inclue']
    produit_id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1)
    prix_vente_grammes = serializers.FloatField(required=False)
    # remise = serializers.FloatField(required=False, min_value=0.0, max_value=100.0)
    class Meta:
        model = VenteProduit
        fields = ['id', 'produit', 'produit_id', 'quantite', 'prix_vente_grammes', 'sous_total_prix_vent', 'tax', 'tax_inclue']
    
    
class VenteSerializers(serializers.ModelSerializer):
    client = ClientSerializers()
    produits = VenteProduitSerializer(many=True)
    class Meta:
        model = Vente
        fields = ['id', 'client', 'produits', 'created_at', 'montant_total',]


class FactureSerializers(serializers.ModelSerializer):
    vente = VenteSerializers()
    class Meta:
        model = Facture
        fields = ['id', 'numero_facture', 'vente', 'date_creation', 'montant_total']


class PaiementSerializers(serializers.ModelSerializer):
    facture = FactureSerializers()
    class Meta:
        model = Paiement
        fields = '__all__'