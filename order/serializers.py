from rest_framework import serializers
from .models import CommandeClient, CommandeProduitClient
from store.models import Produit
from sale.models import Client
from userauths.serializers import UserMiniSerializer
from rest_framework import serializers
# class ClientCommandeSerializer(serializers.ModelSerializer):
#     telephone = serializers.CharField(max_length=15, unique=True, blank=True, null=True)
#     class Meta:
#         model = Client
#         fields = ['id', 'nom', 'prenom', 'telephone']

    # def validate_telephone(self, value):
    #     if not value:
    #         raise serializers.ValidationError("Le numéro de téléphone est requis.")
    #     return value
    
class InfoClientPassCommandeSerializer(serializers.ModelSerializer):
    telephone = serializers.CharField(
        max_length=15,
        required=True,
        allow_blank=False,
        error_messages={
            'blank': "Le numéro de téléphone est requis.",
            'required': "Le numéro de téléphone est obligatoire.",
        }
    )

    class Meta:
        model = Client
        fields = ['id', 'nom', 'prenom', 'telephone']
        


class CommandeProduitClientSerializer(serializers.ModelSerializer):
    commande_client = serializers.PrimaryKeyRelatedField(queryset=CommandeClient.objects.all(), write_only=True)
    nom_produit = serializers.ReadOnlyField()
    sous_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    marque_affichee = serializers.SerializerMethodField()
    poids_affiche = serializers.SerializerMethodField()

    class Meta:
        model = CommandeProduitClient
        fields = [
            'id',
            'commande_client',
            'produit',
            'produit_libre',
            'poids_prevu',
            'marque_personnalisee',
            'categorie_personnalisee',
            'type_personnalise',
            'quantite',
            'prix_prevue',
            'sous_total',
            'nom_produit',
            'marque_affichee',
            'poids_affiche',
        ]

    def get_marque_affichee(self, obj):
        return obj.marque_affichee

    def get_poids_affiche(self, obj):
        return obj.poids_affiche


class CommandeClientSerializer(serializers.ModelSerializer):
    client = InfoClientPassCommandeSerializer()
    produits = CommandeProduitClientSerializer(source='commandes_produits_client', many=True, read_only=True)
    numero_commande = serializers.ReadOnlyField()
    created_by = UserMiniSerializer(read_only=True)
    date_commande = serializers.DateTimeField(read_only=True)
    montant_total = serializers.SerializerMethodField()

    class Meta:
        model = CommandeClient
        fields = [
            'id',
            'numero_commande',
            'client',
            'created_by',
            'statut',
            'commentaire',
            'image',
            'date_commande',
            'produits',
            'montant_total',
        ]

    def get_montant_total(self, obj):
        return obj.montant_total
