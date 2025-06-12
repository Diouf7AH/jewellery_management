from rest_framework import serializers
from .models import ClientBanque, CompteBancaire, Transaction
from django.db import models

class ClientBanqueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientBanque
        fields = ['nom', 'prenom', 'telephone', 'address', 'CNI', 'photo']
        
    def validate_telephone(self, value):
        if not value or len(value) < 9:
            raise serializers.ValidationError("Le numéro de téléphone est requis et doit contenir au moins 9 chiffres.")
        if not value.isdigit():
            raise serializers.ValidationError("Le numéro de téléphone doit contenir uniquement des chiffres.")
        return value


class CompteBancaireSerializer(serializers.ModelSerializer):
    client = ClientBanqueSerializer()
    
    class Meta:
        model = CompteBancaire
        fields = ['id', 'client', 'numero_compte', 'solde', 'date_creation',]
        read_only_fields = ['numero_compte', 'date_creation']


class TransactionSerializer(serializers.ModelSerializer):
    compte = CompteBancaireSerializer(read_only=True)
    compte_id = serializers.PrimaryKeyRelatedField(
        queryset=CompteBancaire.objects.all(),
        source='compte',
        write_only=True
    )
    caissier_prenom = serializers.CharField(source='user.first_name', read_only=True)
    caissier_nom = serializers.CharField(source='user.last_name', read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'id',
            'type_transaction',
            'montant',
            'date_transaction',
            'statut',
            # 'commentaire',
            'compte',
            'compte_id',
            'caissier_prenom',
            'caissier_nom',
        ]
        read_only_fields = ['id', 'date_transaction', 'compte', 'caissier_prenom', 'caissier_nom']
    

# class TransactionSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Transaction
#         fields = ['id', 'compte', 'type_transaction', 'montant', 'date_transaction', 'user']

