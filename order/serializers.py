from rest_framework import serializers
from .models import CommandeClient, CommandeProduitClient
from store.models import Produit
from sale.models import Client
from userauths.serializers import UserMiniSerializer
from rest_framework import serializers
class ClientCommandeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['nom', 'prenom', 'telephone']

    def validate_telephone(self, value):
        if not value:
            raise serializers.ValidationError("Le numéro de téléphone est requis.")
        return value

class CommandeProduitClientSerializer(serializers.ModelSerializer):
    commande_client = serializers.PrimaryKeyRelatedField(
        queryset=CommandeClient.objects.all(), write_only=True
    )
    nom_produit = serializers.ReadOnlyField()
    sous_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = CommandeProduitClient
        fields = [
            'id',
            'commande_client',
            'produit',
            'produit_libre',
            'quantite',
            'prix_prevue',
            'sous_total',
            'nom_produit',
        ]
        # extra_kwargs = {
        #     'commande_client': {'write_only': True}  # ← cohérent avec le champ dans `fields`
        # }


class CommandeClientSerializer(serializers.ModelSerializer):
    client_id = serializers.PrimaryKeyRelatedField(queryset=Client.objects.all(), source="client", write_only=True)
    client = ClientCommandeSerializer()
    produits = CommandeProduitClientSerializer(many=True)
    numero_commande = serializers.ReadOnlyField()
    created_by = UserMiniSerializer(read_only=True)         
    date_commande = serializers.DateTimeField(read_only=True)

    class Meta:
        model = CommandeClient
        fields = [
            'id',
            'numero_commande',
            'client_id',   # champ utilisé lors du POST
            'client',
            'created_by',
            'statut',
            'commentaire',
            'image',
            'date_commande',
            'produits',
        ]
#  la méthode create()
# Puisque tu gères un champ imbriqué produits, 
# tu dois définir la méthode create() pour enregistrer correctement la commande et ses produits.
    def create(self, validated_data):
        produits_data = validated_data.pop('produits')
        created_by = validated_data.pop('created_by', None)

        commande = CommandeClient.objects.create(**validated_data, created_by=created_by)

        for produit_data in produits_data:
            CommandeProduitClient.objects.create(commande_client=commande, **produit_data)

        return commande
