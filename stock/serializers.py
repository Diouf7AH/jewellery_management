from rest_framework import serializers

from stock.models import Stock
from store.models import Produit
from store.serializers import ProduitSerializer


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
class ReserveToVendorLineInSerializer(serializers.Serializer):
    produit_line_id = serializers.IntegerField(min_value=1)
    quantite = serializers.IntegerField(min_value=1)


class ReserveToVendorInSerializer(serializers.Serializer):
    vendor_email = serializers.EmailField()
    lignes = ReserveToVendorLineInSerializer(many=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate_lignes(self, lignes):
        if not lignes:
            raise serializers.ValidationError("Au moins une ligne est requise.")

        # 🔒 Sécurité anti-doublon (même produit_line répété)
        seen = set()
        for i, item in enumerate(lignes):
            pl_id = item.get("produit_line_id")
            if pl_id in seen:
                raise serializers.ValidationError(
                    f"produit_line_id {pl_id} dupliqué dans les lignes."
                )
            seen.add(pl_id)

        return lignes


# -------- OUT ReserveToVendor ----------
class ReserveToVendorLineOutSerializer(serializers.Serializer):
    produit_line_id = serializers.IntegerField()
    transfere = serializers.IntegerField()
    reserve_en_stock = serializers.IntegerField()
    reserve_disponible = serializers.IntegerField()
    vendor_allouee = serializers.IntegerField()
    vendor_vendue = serializers.IntegerField()
    vendor_disponible = serializers.IntegerField()


class ReserveToVendorOutSerializer(serializers.Serializer):
    vendor_id = serializers.IntegerField()
    vendor_email = serializers.EmailField(allow_null=True)
    bijouterie_id = serializers.IntegerField()
    bijouterie_nom = serializers.CharField(allow_null=True)
    lignes = ReserveToVendorLineOutSerializer(many=True)
    note = serializers.CharField(allow_blank=True)
    movements_created = serializers.IntegerField(read_only=True)

