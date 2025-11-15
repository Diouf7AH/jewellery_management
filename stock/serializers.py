from rest_framework import serializers

from stock.models import Stock
from store.models import Produit
from store.serializers import ProduitSerializer

# class FournisseurSerializer(serializers.ModelSerializer):
    
#     class Meta:
#         model = Fournisseur
#         fields = ['id', 'nom', 'prenom', 'address', 'telephone']


# class StockSerializer(serializers.ModelSerializer):
#     # produit = ProduitSerializer()
#     # fournisseur = FournisseurSerializer()
#     class Meta:
#         model = Stock
#         fields = '__all__'

class StockSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stock
        fields = ["id", "bijouterie", "produit_line", "quantite", "quantite_allouee", "quantite_disponible", "created_at"]
        read_only_fields = ["date_ajout", "created_at"]


# class LigneCommandeStockSerializer(serializers.ModelSerializer):
#     produit = ProduitSerializer()

#     class Meta:
#         model = LigneCommandeStock
#         fields = '__all__'


class ReserveToBijouterieLineInSerializer(serializers.Serializer):
    produit_line_id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1)

class ReserveToBijouterieInSerializer(serializers.Serializer):
    bijouterie_id = serializers.IntegerField()
    lignes = ReserveToBijouterieLineInSerializer(many=True)
    note = serializers.CharField(required=False, allow_blank=True)
    

# ----------------Bijouterie to vendeur--------------------------
class BijouterieToVendorLineInSerializer(serializers.Serializer):
    produit_line_id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1)

class BijouterieToVendorInSerializer(serializers.Serializer):
    vendor_email = serializers.EmailField(
        help_text="Email de l'utilisateur associé au vendeur"
    )
    lignes = BijouterieToVendorLineInSerializer(many=True)
    note = serializers.CharField(required=False, allow_blank=True)
# ---------------End Bijouterie to vendeur-----------------------


# -------------lister les stock par bijouterie--------------------
class StockSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    bijouterie_nom = serializers.CharField(source="bijouterie.nom", read_only=True)

    class Meta:
        model = Stock
        fields = [
            "id", "produit_line", "bijouterie", "bijouterie_nom",
            "quantite_allouee", "quantite_disponible", "status",
            "created_at", "updated_at",
        ]

    def get_status(self, obj):
        if obj.bijouterie_id is None:
            return "reserved"
        return "allocated" if (obj.quantite_allouee or 0) > 0 else "allocated_empty"


class StockSummaryBucketSerializer(serializers.Serializer):
    lignes = serializers.IntegerField(min_value=0)
    allouee = serializers.IntegerField(min_value=0)
    disponible = serializers.IntegerField(min_value=0)
    produits_totaux = serializers.IntegerField(min_value=0)  # NEW

class StockSummarySerializer(serializers.Serializer):
    reserved = StockSummaryBucketSerializer()
    allocated = StockSummaryBucketSerializer()
    in_stock = StockSummaryBucketSerializer()

# ---------------End lister les stock par bijouterie-------------------