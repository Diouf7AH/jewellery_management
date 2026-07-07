from rest_framework import serializers

from stock.models import Stock
from store.models import Produit
from store.serializers import ProduitSerializer


class MagasinProduitDisponibleSerializer(serializers.ModelSerializer):
    produit_id = serializers.IntegerField(source="produit_line.produit.id", read_only=True)
    produit_nom = serializers.CharField(source="produit_line.produit.nom", read_only=True)
    sku = serializers.CharField(source="produit_line.produit.sku", read_only=True)
    purete = serializers.CharField(source="produit_line.produit.purete", read_only=True)
    marque = serializers.CharField(source="produit_line.produit.marque", read_only=True)
    poids = serializers.DecimalField(source="produit_line.produit.poids", max_digits=10, decimal_places=3, read_only=True)

    lot_id = serializers.IntegerField(source="produit_line.lot.id", read_only=True)
    numero_lot = serializers.CharField(source="produit_line.lot.numero_lot", read_only=True)

    bijouterie_id = serializers.IntegerField(source="bijouterie.id", read_only=True)
    bijouterie = serializers.CharField(source="bijouterie.nom", read_only=True)

    prix_vente_grammes = serializers.DecimalField(
        source="produit_line.prix_vente_grammes",
        max_digits=12,
        decimal_places=2,
        read_only=True
    )

    valeur_stock = serializers.SerializerMethodField()

    class Meta:
        model = Stock
        fields = [
            "id",
            "produit_id",
            "produit_nom",
            "sku",
            "purete",
            "marque",
            "poids",
            "lot_id",
            "numero_lot",
            "bijouterie_id",
            "bijouterie",
            "en_stock",
            "prix_vente_grammes",
            "valeur_stock",
        ]

    def get_valeur_stock(self, obj):
        produit = obj.produit_line.produit
        poids = produit.poids or 0
        prix = obj.produit_line.prix_vente_grammes or 0
        return obj.en_stock * poids * prix
    

class StockSerializer(serializers.ModelSerializer):
    # Infos utiles (lecture)
    # in_reserve = serializers.BooleanField(source="is_reserve", read_only=True)

    bijouterie_id = serializers.IntegerField(source="bijouterie.id", read_only=True)
    bijouterie_nom = serializers.CharField(source="bijouterie.nom", read_only=True)

    produit_line_id = serializers.IntegerField(source="produit_line.id", read_only=True)
    lot_id = serializers.IntegerField(source="produit_line.lot.id", read_only=True)
    numero_lot = serializers.CharField(source="produit_line.lot.numero_lot", read_only=True)

    produit_id = serializers.IntegerField(source="produit_line.produit.id", read_only=True)
    produit_nom = serializers.CharField(source="produit_line.produit.nom", read_only=True)

    # Champs “business” clairs pour le frontend
    stock_total = serializers.IntegerField(source="quantite_disponible", read_only=True)  # total affecté
    stock_reel = serializers.IntegerField(source="en_stock", read_only=True)              # restant réel

    reserve_ou_boutique = serializers.SerializerMethodField()

    class Meta:
        model = Stock
        fields = [
            "id",
            "produit_line_id",
            "produit_id",
            "produit_nom",
            "lot_id",
            "numero_lot",
            "bijouterie_id",
            "bijouterie_nom",
            "is_reserve",
            # "in_reserve",   # ✅ alias compat
            "stock_total",
            "stock_reel",
            "reserve_ou_boutique",
            "created_at",
            "updated_at",
        ]

    def get_reserve_ou_boutique(self, obj) -> str:
        # Petit label simple pour affichage
        if obj.is_reserve:
            return "reserve"
        return "boutique"


# ReserveToVendor
# -------- IN ----------
class MagasinToVendorLineInSerializer(serializers.Serializer):
    produit_line_id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1)


class MagasinToVendorInSerializer(serializers.Serializer):
    vendor_email = serializers.EmailField()
    lignes = MagasinToVendorLineInSerializer(many=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate_lignes(self, lignes):
        if not lignes:
            raise serializers.ValidationError("Au moins une ligne est requise.")

        seen = set()
        for item in lignes:
            pl_id = item.get("produit_line_id")

            if pl_id in seen:
                raise serializers.ValidationError(
                    f"produit_line_id {pl_id} dupliqué dans les lignes."
                )

            seen.add(pl_id)

        return lignes


class MagasinToVendorLineOutSerializer(serializers.Serializer):
    produit_line_id = serializers.IntegerField()
    transfere = serializers.IntegerField()

    magasin_en_stock = serializers.IntegerField()
    magasin_disponible = serializers.IntegerField()

    vendor_allouee = serializers.IntegerField()
    vendor_vendue = serializers.IntegerField()
    vendor_disponible = serializers.IntegerField()


class MagasinToVendorOutSerializer(serializers.Serializer):
    vendor_id = serializers.IntegerField()
    vendor_email = serializers.EmailField(allow_null=True)
    bijouterie_id = serializers.IntegerField()
    bijouterie_nom = serializers.CharField(allow_null=True)
    lignes = MagasinToVendorLineOutSerializer(many=True)
    note = serializers.CharField(allow_blank=True)
    movements_created = serializers.IntegerField()
    
    