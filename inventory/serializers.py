from rest_framework import serializers


class InventoryMovementItemSerializer(serializers.Serializer):
    movement_type = serializers.CharField()
    label         = serializers.CharField()
    count         = serializers.IntegerField()
    total_qty     = serializers.IntegerField()
    total_value   = serializers.CharField()   # "2160000.00"


class InventoryMovementPeriodSerializer(serializers.Serializer):
    mode  = serializers.CharField()  # "year" | "quarter" | "semester" | "custom"
    start = serializers.CharField()  # ISO (Z)
    end   = serializers.CharField()  # ISO (Z)


# ---- Nouveaux blocs "snapshot" ----
class StockByBijouterieItemSerializer(serializers.Serializer):
    bijouterie_id       = serializers.IntegerField(allow_null=True)
    bijouterie_nom      = serializers.CharField(allow_null=True)
    quantite_allouee    = serializers.IntegerField()
    quantite_disponible = serializers.IntegerField()


class StockByVendorItemSerializer(serializers.Serializer):
    vendor_id           = serializers.IntegerField()
    vendor_email        = serializers.CharField(allow_null=True)
    bijouterie_id       = serializers.IntegerField(allow_null=True)
    bijouterie_nom      = serializers.CharField(allow_null=True)
    quantite_allouee    = serializers.IntegerField()
    quantite_disponible = serializers.IntegerField()


class InventoryMovementResponseSerializer(serializers.Serializer):
    period             = InventoryMovementPeriodSerializer()
    scope              = serializers.CharField()  # "admin" | "manager" | "vendor"
    results            = InventoryMovementItemSerializer(many=True)
    stock_by_bijouterie = StockByBijouterieItemSerializer(many=True)
    stock_by_vendor     = StockByVendorItemSerializer(many=True)