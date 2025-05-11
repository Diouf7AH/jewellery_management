from django.contrib.auth.models import User
from rest_framework import serializers

from store.serializers import ProduitSerializer
from store.models import Produit
from userauths.models import User
from .models import Vendor, VendorProduit


class VendorUpdateStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ['verifie']  # ⚠️ Si tu veux activer/désactiver le vendeur (champ correct = verifie, pas active)



# class VendorProduitSerializer(serializers.ModelSerializer):
#     # produit = ProduitSerializer()

#     class Meta:
#         model = VendorProduit
#         fields = ['vendor', 'produit', 'quantite']

class VendorProduitSerializer(serializers.ModelSerializer):
    produit = ProduitSerializer(read_only=True)  # Affichage complet du produit
    produit_id = serializers.PrimaryKeyRelatedField(
        queryset=Produit.objects.all(),
        source='produit',
        write_only=True
    )
    vendor = serializers.SerializerMethodField()  # 👈 lecture seule, affiche l'ID de l'utilisateur

    class Meta:
        model = VendorProduit
        fields = ['vendor', 'produit', 'produit_id', 'quantite']

    def get_vendor(self, obj):
        return obj.vendor.user.id if obj.vendor and obj.vendor.user else None



# class VendorSerializer(serializers.ModelSerializer):
#     email = serializers.EmailField(source='user.email', read_only=True)

#     class Meta:
#         model = Vendor
#         fields = ['email', 'bijouterie', 'active', 'description', 'verifie', 'raison_desactivation']

class VendorSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    bijouterie = serializers.SerializerMethodField()  # ✅ personnalisation

    class Meta:
        model = Vendor
        fields = ['email', 'bijouterie', 'active', 'description', 'verifie', 'raison_desactivation']

    def get_bijouterie(self, obj):
        if obj.bijouterie:
            return {
                "id": obj.bijouterie.id,
                "nom": obj.bijouterie.nom
            }
        return None

# Pour l'affichage du swagger
# # avoir tous les attributs du vendeur dans swagger
# class CreateVendorSerializer(serializers.Serializer):
#     email = serializers.EmailField(required=True)
#     # username = serializers.CharField(required=False)
#     # phone = serializers.CharField(required=False)
#     bijouterie = serializers.IntegerField(required=True)
#     description = serializers.CharField(required=False, allow_blank=True)

class CreateVendorSerializer(serializers.Serializer):
    email = serializers.EmailField()
    bijouterie = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)

    def validate_bijouterie(self, value):
        from store.models import Bijouterie
        try:
            return Bijouterie.objects.get(nom__iexact=value.strip())
        except Bijouterie.DoesNotExist:
            raise serializers.ValidationError("Bijouterie introuvable.")

# class CreateVendorSerializer(serializers.Serializer):
#     email = serializers.EmailField()
#     bijouterie_id = serializers.IntegerField()
#     description = serializers.CharField(required=False, allow_blank=True)

#     def validate_bijouterie_id(self, value):
#         from store.models import Bijouterie
#         if not Bijouterie.objects.filter(id=value).exists():
#             raise serializers.ValidationError("Bijouterie introuvable.")
#         return value


class UserListeSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'full_name']

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"


class VendorDashboardSerializer(serializers.Serializer):
    # Infos du vendeur
    user_id = serializers.IntegerField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    bijouterie = serializers.CharField()

    # Produits associés
    produits = VendorProduitSerializer(many=True)

    # Statistiques globales
    total_produits = serializers.IntegerField()
    total_ventes = serializers.IntegerField()
    quantite_totale_vendue = serializers.IntegerField()
    montant_total_ventes = serializers.DecimalField(max_digits=12, decimal_places=2)
    stock_restant = serializers.IntegerField()

    # Statistiques groupées (par mois, semaine, etc.)
    stats_groupées = serializers.ListField(
        child=serializers.DictField(), required=False
    )

    # Top produits
    top_produits = serializers.ListField(
        child=serializers.DictField(), required=False
    )

    mode_groupement = serializers.CharField(required=False)
