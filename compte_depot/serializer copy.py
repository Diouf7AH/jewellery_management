from django.db import models
from rest_framework import serializers

from userauths.serializers import UserMiniSerializer

from .models import ClientDepot, CompteDepot, CompteDepotTransaction


class ClientDepotSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientDepot
        fields = ['id', 'nom', 'prenom', 'telephone', 'address', 'CNI', 'photo']
        
    def validate_telephone(self, value):
        if not value or len(value) < 9:
            raise serializers.ValidationError("Le numéro de téléphone est requis et doit contenir au moins 9 chiffres.")
        if not value.isdigit():
            raise serializers.ValidationError("Le numéro de téléphone doit contenir uniquement des chiffres.")
        return value


class CompteDepotSerializer(serializers.ModelSerializer):
    client = ClientDepotSerializer()
    telephone = serializers.CharField(source='client.telephone', read_only=True)
    created_by = UserMiniSerializer(read_only=True)
    
    class Meta:
        model = CompteDepot
        fields = ['id', 'client', 'telephone', 'numero_compte', 'solde', 'date_creation', 'created_by']
        read_only_fields = ['id', 'numero_compte', 'date_creation', 'created_by']



class CompteDepotTransactionCreateSerializer(serializers.Serializer):
    montant = serializers.DecimalField(max_digits=12, decimal_places=2)

    def validate_montant(self, v):
        if v is None or v <= 0:
            raise serializers.ValidationError("Le montant doit être strictement positif.")
        return v

class CompteDepotTransactionSerializer(serializers.ModelSerializer):
    compte_numero = serializers.CharField(source="compte.numero_compte", read_only=True)
    client_nom = serializers.CharField(source="compte.client.nom", read_only=True)
    client_prenom = serializers.CharField(source="compte.client.prenom", read_only=True)

    class Meta:
        model = CompteDepotTransaction
        fields = [
            "id", "type_transaction", "montant", "date_transaction",
            "statut", "compte", "compte_numero", "client_nom", "client_prenom"
        ]
        read_only_fields = ["id", "date_transaction", "statut", "type_transaction", "compte"]
        
        

        
        

