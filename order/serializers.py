from rest_framework import serializers
from .models import CommandeClient, CommandeProduitClient, BonCommande
from store.models import Produit
from sale.models import Client
from userauths.serializers import UserMiniSerializer
from rest_framework import serializers
from store.models import (Categorie, Marque, Modele, Produit, Purete)
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
    sous_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    prix_prevue = serializers.DecimalField(max_digits=10, decimal_places=2)  # ✅ Ajout ici

    categorie = serializers.SlugRelatedField(queryset=Categorie.objects.all(), slug_field='nom', write_only=True)
    categorie_detail = serializers.SerializerMethodField(read_only=True)

    marque = serializers.SlugRelatedField(queryset=Marque.objects.all(), slug_field='marque', write_only=True)
    marque_detail = serializers.SerializerMethodField(read_only=True)

    modele = serializers.SlugRelatedField(queryset=Modele.objects.all(), slug_field='modele', write_only=True)
    modele_detail = serializers.SerializerMethodField(read_only=True)

    purete = serializers.SlugRelatedField(queryset=Purete.objects.all(), slug_field='purete', write_only=True)
    purete_detail = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CommandeProduitClient
        fields = [
            'id', 'commande_client', 'produit', 'matiere', 'poids', 'genre', 'quantite',
            'prix_prevue', 'prix_gramme', 'sous_total',
            'categorie', 'categorie_detail',
            'marque', 'marque_detail',
            'modele', 'modele_detail',
            'purete', 'purete_detail',
        ]
        extra_kwargs = {
            'categorie': {'write_only': True},
            'purete': {'write_only': True},
            'marque': {'write_only': True},
            'modele': {'write_only': True},
        }

    def get_categorie_detail(self, obj):
        if obj.categorie:
            return {"id": obj.categorie.id, "nom": obj.categorie.nom}
        return None

    def get_marque_detail(self, obj):
        if obj.marque:
            return {
                "id": obj.marque.id,
                "marque": obj.marque.marque,
                "purete": obj.marque.purete.purete if obj.marque.purete else None,
                "categorie": obj.marque.categorie.nom if obj.marque.categorie else None,
            }
        return None

    def get_modele_detail(self, obj):
        if obj.modele:
            return {"id": obj.modele.id, "modele": obj.modele.modele}
        return None

    def get_purete_detail(self, obj):
        if obj.purete:
            return {"id": obj.purete.id, "purete": obj.purete.purete}
        return None


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


class BonCommandeSerializer(serializers.ModelSerializer):
    commande = CommandeClientSerializer(read_only=True)  # ou PrimaryKeyRelatedField si tu veux juste l'ID

    class Meta:
        model = BonCommande
        fields = [
            "id",
            "numero_bon",
            "commande",
            "montant_total",
            "acompte",
            "reste_a_payer",
        ]
        read_only_fields = ["numero_bon", "montant_total", "reste_a_payer"]


class PaiementAcompteBonCommandeViewSerializer(serializers.ModelSerializer):
    class Meta:
        model = BonCommande
        fields = ["acompte"]