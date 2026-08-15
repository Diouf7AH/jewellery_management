# stock/serializers.py
from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from rest_framework import serializers

from stock.models import Stock

# ============================================================
# Stock disponible dans une bijouterie
# ============================================================

class MagasinProduitDisponibleSerializer(
    serializers.ModelSerializer
):
    produit_line_id = serializers.IntegerField(
        source="produit_line.id",
        read_only=True,
    )

    produit_id = serializers.IntegerField(
        source="produit_line.produit.id",
        read_only=True,
    )

    produit_nom = serializers.CharField(
        source="produit_line.produit.nom",
        read_only=True,
    )

    sku = serializers.CharField(
        source="produit_line.produit.sku",
        read_only=True,
        allow_null=True,
    )

    purete = serializers.CharField(
        source="produit_line.produit.purete",
        read_only=True,
        allow_null=True,
    )

    marque = serializers.CharField(
        source="produit_line.produit.marque",
        read_only=True,
        allow_null=True,
    )

    poids = serializers.DecimalField(
        source="produit_line.produit.poids",
        max_digits=10,
        decimal_places=3,
        read_only=True,
        allow_null=True,
    )

    lot_id = serializers.IntegerField(
        source="produit_line.lot.id",
        read_only=True,
        allow_null=True,
    )

    numero_lot = serializers.CharField(
        source="produit_line.lot.numero_lot",
        read_only=True,
        allow_null=True,
    )

    bijouterie_id = serializers.IntegerField(
        source="bijouterie.id",
        read_only=True,
    )

    bijouterie_nom = serializers.CharField(
        source="bijouterie.nom",
        read_only=True,
    )

    class Meta:
        model = Stock

        fields = [
            "id",

            "produit_line_id",
            "produit_id",
            "produit_nom",
            "sku",
            "purete",
            "marque",
            "poids",

            "lot_id",
            "numero_lot",

            "bijouterie_id",
            "bijouterie_nom",

            "en_stock",
            "quantite_totale",

            "created_at",
            "updated_at",
        ]

        read_only_fields = fields
    

# ============================================================
# Serializer général du stock magasin
# ============================================================

class StockSerializer(serializers.ModelSerializer):
    bijouterie_id = serializers.IntegerField(
        source="bijouterie.id",
        read_only=True,
    )

    bijouterie_nom = serializers.CharField(
        source="bijouterie.nom",
        read_only=True,
    )

    produit_line_id = serializers.IntegerField(
        source="produit_line.id",
        read_only=True,
    )

    lot_id = serializers.IntegerField(
        source="produit_line.lot.id",
        read_only=True,
    )

    numero_lot = serializers.CharField(
        source="produit_line.lot.numero_lot",
        read_only=True,
    )

    produit_id = serializers.IntegerField(
        source="produit_line.produit.id",
        read_only=True,
    )

    produit_nom = serializers.CharField(
        source="produit_line.produit.nom",
        read_only=True,
    )

    sku = serializers.CharField(
        source="produit_line.produit.sku",
        read_only=True,
    )

    # Noms explicites pour le frontend.
    quantite_recue = serializers.IntegerField(
        source="quantite_totale",
        read_only=True,
    )

    quantite_magasin_disponible = serializers.IntegerField(
        source="en_stock",
        read_only=True,
    )

    quantite_affectee_ou_sortie = serializers.SerializerMethodField()

    class Meta:
        model = Stock
        fields = [
            "id",
            "stock_key",

            "produit_line_id",
            "produit_id",
            "produit_nom",
            "sku",

            "lot_id",
            "numero_lot",

            "bijouterie_id",
            "bijouterie_nom",

            "quantite_totale",
            "en_stock",

            # Alias frontend explicites.
            "quantite_recue",
            "quantite_magasin_disponible",
            "quantite_affectee_ou_sortie",

            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_quantite_affectee_ou_sortie(self, obj: Stock) -> int:
        """
        Différence entre la quantité historiquement reçue
        et la quantité encore présente dans le magasin.

        Cette différence peut contenir :
        - les quantités affectées aux vendeurs ;
        - les éventuelles sorties ou corrections selon le flux métier.

        Pour connaître précisément les quantités vendues ou détenues par
        les vendeurs, il faut consulter VendorStock et InventoryMovement.
        """

        quantite_totale = int(obj.quantite_totale or 0)
        en_stock = int(obj.en_stock or 0)

        return max(0, quantite_totale - en_stock)


# ============================================================
# Affectation stock magasin -> vendeur
# ============================================================

class StockToVendorAssignmentLineInSerializer(
    serializers.Serializer
):
    produit_line_id = serializers.IntegerField(
        min_value=1,
    )

    quantite = serializers.IntegerField(
        min_value=1,
    )


class StockToVendorAssignmentInSerializer(serializers.Serializer):
    vendor_email = serializers.EmailField()

    lignes = StockToVendorAssignmentLineInSerializer(
        many=True,
        allow_empty=False,
    )

    note = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=500,
        trim_whitespace=True,
    )

    def validate_vendor_email(self, value: str) -> str:
        return value.strip().lower()

    def validate_lignes(self, lignes):
        """
        Refuse les ProduitLine dupliquées dans la requête.

        Le service métier peut aussi les regrouper par sécurité,
        mais il est préférable que l'API refuse une saisie ambiguë.
        """

        seen = set()
        duplicates = set()

        for item in lignes:
            produit_line_id = item["produit_line_id"]

            if produit_line_id in seen:
                duplicates.add(produit_line_id)

            seen.add(produit_line_id)

        if duplicates:
            duplicate_ids = ", ".join(
                str(value)
                for value in sorted(duplicates)
            )

            raise serializers.ValidationError(
                "Les ProduitLine suivantes sont dupliquées : "
                f"{duplicate_ids}."
            )

        return lignes

class StockToVendorAssignmentLineOutSerializer(serializers.Serializer):
    produit_line_id = serializers.IntegerField()

    quantite_affectee = serializers.IntegerField(
        min_value=1,
    )

    magasin_en_stock = serializers.IntegerField(
        min_value=0,
    )

    magasin_quantite_totale = serializers.IntegerField(
        min_value=0,
    )

    vendor_quantite_allouee = serializers.IntegerField(
        min_value=0,
    )

    vendor_quantite_vendue = serializers.IntegerField(
        min_value=0,
    )

    vendor_en_stock = serializers.IntegerField(
        min_value=0,
    )
    

class StockToVendorAssignmentOutSerializer(serializers.Serializer):
    vendor_id = serializers.IntegerField()

    vendor_email = serializers.EmailField(
        allow_null=True,
    )

    bijouterie_id = serializers.IntegerField()

    bijouterie_nom = serializers.CharField(
        allow_null=True,
    )

    nombre_lignes = serializers.IntegerField(
        min_value=0,
    )

    quantite_totale_affectee = serializers.IntegerField(
        min_value=0,
    )

    lignes = StockToVendorAssignmentLineOutSerializer(
        many=True,
    )

    note = serializers.CharField(
        allow_blank=True,
    )

    movements_created = serializers.IntegerField(
        min_value=0,
    )
    


class StockDisponiblePourVendeurSerializer(serializers.ModelSerializer):
    stock_id = serializers.IntegerField(source="id",read_only=True,)
    produit_line_id = serializers.IntegerField(source="produit_line.id",read_only=True,)
    produit_id = serializers.IntegerField(source="produit_line.produit.id",read_only=True,)

    produit_nom = serializers.CharField(
        source="produit_line.produit.nom",
        read_only=True,
    )

    sku = serializers.CharField(
        source="produit_line.produit.sku",
        read_only=True,
        allow_null=True,
    )

    poids = serializers.DecimalField(
        source="produit_line.produit.poids",
        max_digits=10,
        decimal_places=3,
        read_only=True,
        allow_null=True,
    )

    purete = serializers.SerializerMethodField()

    marque = serializers.SerializerMethodField()

    lot_id = serializers.IntegerField(
        source="produit_line.lot.id",
        read_only=True,
        allow_null=True,
    )

    numero_lot = serializers.CharField(
        source="produit_line.lot.numero_lot",
        read_only=True,
        allow_null=True,
    )

    bijouterie_id = serializers.IntegerField(
        source="bijouterie.id",
        read_only=True,
    )

    bijouterie_nom = serializers.CharField(
        source="bijouterie.nom",
        read_only=True,
    )

    stock_disponible = serializers.IntegerField(
        source="en_stock",
        read_only=True,
    )

    quantite_totale_recue = serializers.IntegerField(
        source="quantite_totale",
        read_only=True,
    )

    class Meta:
        model = Stock

        fields = [
            "stock_id",
            "produit_line_id",
            "produit_id",
            "produit_nom",
            "sku",
            "poids",
            "purete",
            "marque",
            "lot_id",
            "numero_lot",
            "bijouterie_id",
            "bijouterie_nom",
            "stock_disponible",
            "quantite_totale_recue",
        ]

        read_only_fields = fields

    def get_purete(self, obj):
        purete = getattr(
            obj.produit_line.produit,
            "purete",
            None,
        )

        if purete is None:
            return None

        return str(purete)

    def get_marque(self, obj):
        marque = getattr(
            obj.produit_line.produit,
            "marque",
            None,
        )

        if marque is None:
            return None

        return str(marque)
    
    
