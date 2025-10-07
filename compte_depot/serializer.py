from rest_framework import serializers
from .models import ClientDepot, CompteDepot, Transaction
from django.db import models
from userauths.serializers import UserMiniSerializer 

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


# class TransactionSerializer(serializers.ModelSerializer):
#     client_full_name = serializers.SerializerMethodField()
#     telephone = serializers.CharField(source='client.telephone', read_only=True)
#     user_full_name = serializers.SerializerMethodField()
#     compte_numero = serializers.CharField(source='compte.numero_compte', read_only=True)

#     class Meta:
#         model = Transaction
#         fields = [
#             'id',
#             'type_transaction',
#             'client_full_name',
#             'telephone',
#             'compte_numero',
#             'montant',
#             'date_transaction',
#             'statut',
#             'user_full_name',
#         ]

#     def get_user_full_name(self, obj):
#         if obj.user:
#             return f"{obj.user.last_name} {obj.user.first_name}".strip()
#         return None

#     def get_client_full_name(self, obj):
#         client = obj.compte.client
#         if client:
#             return f"{client.prenom} {client.nom}".strip()
#         return None

class TransactionCreateSerializer(serializers.Serializer):
    montant = serializers.DecimalField(max_digits=12, decimal_places=2)

    def validate_montant(self, v):
        if v is None or v <= 0:
            raise serializers.ValidationError("Le montant doit être strictement positif.")
        return v

class TransactionSerializer(serializers.ModelSerializer):
    compte_numero = serializers.CharField(source="compte.numero_compte", read_only=True)
    client_nom = serializers.CharField(source="compte.client.nom", read_only=True)
    client_prenom = serializers.CharField(source="compte.client.prenom", read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id", "type_transaction", "montant", "date_transaction",
            "statut", "compte", "compte_numero", "client_nom", "client_prenom"
        ]
        read_only_fields = ["id", "date_transaction", "statut", "type_transaction", "compte"]