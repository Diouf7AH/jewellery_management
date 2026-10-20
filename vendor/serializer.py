

# vendor/serializer.py
from rest_framework import serializers

from vendor.models import Vendor


class VendorSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = Vendor
        fields = ['email', 'bijouterie', 'verifie']


class VendorStockVendorSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        source="user.email",
        read_only=True,
    )

    full_name = serializers.SerializerMethodField()

    bijouterie_id = serializers.IntegerField(
        source="bijouterie.id",
        read_only=True,
    )

    bijouterie_nom = serializers.CharField(
        source="bijouterie.nom",
        read_only=True,
    )

    class Meta:
        model = Vendor

        fields = [
            "id",
            "email",
            "full_name",
            "bijouterie_id",
            "bijouterie_nom",
        ]

        read_only_fields = fields

    def get_full_name(self, obj):
        user = obj.user

        full_name = " ".join(
            value
            for value in [
                user.first_name,
                user.last_name,
            ]
            if value
        ).strip()

        return full_name or user.email


class VendorStockFiltreSerializer(serializers.Serializer):
    annee = serializers.IntegerField()


class VendorStockTotauxSerializer(serializers.Serializer):
    quantite_allouee = serializers.IntegerField(
        min_value=0,
    )

    quantite_vendue = serializers.IntegerField(
        min_value=0,
    )

    quantite_disponible = serializers.IntegerField(
        min_value=0,
    )

    poids_disponible = serializers.DecimalField(
        max_digits=18,
        decimal_places=3,
    )


class VendorStockPaginationSerializer(serializers.Serializer):
    page = serializers.IntegerField(
        min_value=1,
    )

    page_size = serializers.IntegerField(
        min_value=1,
    )

    total_pages = serializers.IntegerField(
        min_value=0,
    )

    total_results = serializers.IntegerField(
        min_value=0,
    )

    has_next = serializers.BooleanField()

    has_previous = serializers.BooleanField()

class VendorStockResponseSerializer(serializers.Serializer):

    vendor = VendorStockVendorSerializer()

    filtre = VendorStockFiltreSerializer()

    totaux = VendorStockTotauxSerializer()

    pagination = VendorStockPaginationSerializer()

    count = serializers.IntegerField(
        min_value=0,
    )

    produits = serializers.ListField(
        child=serializers.DictField(),
    )





