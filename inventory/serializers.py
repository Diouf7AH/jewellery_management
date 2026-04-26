# inventory/serializers.py
from rest_framework import serializers

from inventory.models import InventoryMovement
from purchase.models import ProduitLine
from store.models import Bijouterie


class InventoryBijouterieSerializer(serializers.Serializer):
    bijouterie_id = serializers.IntegerField()
    bijouterie_nom = serializers.CharField()

    purchase_in = serializers.DecimalField(max_digits=18, decimal_places=2)
    cancel_purchase_out = serializers.DecimalField(max_digits=18, decimal_places=2)
    allocate_in = serializers.DecimalField(max_digits=18, decimal_places=2)
    transfer_in = serializers.DecimalField(max_digits=18, decimal_places=2)
    transfer_out = serializers.DecimalField(max_digits=18, decimal_places=2)
    sale_out = serializers.DecimalField(max_digits=18, decimal_places=2)
    return_in = serializers.DecimalField(max_digits=18, decimal_places=2)
    adjustment_in = serializers.DecimalField(max_digits=18, decimal_places=2)
    adjustment_out = serializers.DecimalField(max_digits=18, decimal_places=2)

    stock_net = serializers.DecimalField(max_digits=18, decimal_places=2)
    


class InventoryVendorSerializer(serializers.Serializer):
    vendor_id = serializers.IntegerField()
    vendor_nom = serializers.CharField()
    vendor_email = serializers.EmailField(allow_null=True)

    bijouterie_id = serializers.IntegerField(allow_null=True)
    bijouterie_nom = serializers.CharField(allow_null=True)

    vendor_assign_in = serializers.DecimalField(max_digits=18, decimal_places=2)
    sale_out_vendor = serializers.DecimalField(max_digits=18, decimal_places=2)
    return_in_vendor = serializers.DecimalField(max_digits=18, decimal_places=2)

    stock_restant = serializers.DecimalField(max_digits=18, decimal_places=2)
    
    

class InventoryMovementListSerializer(serializers.Serializer):
    """
    Serializer plat pour InventoryMovementListView
    (utilisé sur des dicts venant de values()/annotations).
    """
    id = serializers.IntegerField()
    occurred_at = serializers.DateTimeField()
    movement_type = serializers.CharField()

    produit_id = serializers.IntegerField(allow_null=True)
    produit_nom = serializers.CharField(allow_null=True, required=False)
    produit_sku = serializers.CharField(allow_null=True, required=False)

    lot_id = serializers.IntegerField(allow_null=True, required=False)
    lot_code = serializers.CharField(allow_null=True, required=False)

    achat_id = serializers.IntegerField(allow_null=True, required=False)

    qty = serializers.DecimalField(max_digits=18, decimal_places=2)
    signed_qty = serializers.DecimalField(max_digits=18, decimal_places=2)

    unit_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        allow_null=True,
        required=False,
    )
    total_cost = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        allow_null=True,
        required=False,
    )

    vendor_id = serializers.IntegerField(allow_null=True, required=False)
    vendor_email = serializers.CharField(allow_null=True, required=False)

    vente_id = serializers.IntegerField(allow_null=True, required=False)
    numero_vente = serializers.CharField(allow_null=True, required=False)

    facture_id = serializers.IntegerField(allow_null=True, required=False)
    numero_facture = serializers.CharField(allow_null=True, required=False)

    src_bucket = serializers.CharField(allow_null=True, required=False)
    src_bijouterie_id = serializers.IntegerField(allow_null=True, required=False)
    src_bijouterie_nom = serializers.CharField(allow_null=True, required=False)

    dst_bucket = serializers.CharField(allow_null=True, required=False)
    dst_bijouterie_id = serializers.IntegerField(allow_null=True, required=False)
    dst_bijouterie_nom = serializers.CharField(allow_null=True, required=False)

    created_by_id = serializers.IntegerField(allow_null=True, required=False)
    reason = serializers.CharField(allow_null=True, required=False)


class InventoryMovementMiniSerializer(serializers.ModelSerializer):
    """
    Petit serializer pour afficher les mouvements liés à un ProduitLine.
    """
    src_bijouterie_nom = serializers.CharField(
        source="src_bijouterie.nom",
        read_only=True,
        default=None,
    )
    dst_bijouterie_nom = serializers.CharField(
        source="dst_bijouterie.nom",
        read_only=True,
        default=None,
    )

    vendor_id = serializers.IntegerField(source="vendor.id", read_only=True, default=None)
    vendor_email = serializers.EmailField(source="vendor.user.email", read_only=True, default=None)

    vente_id = serializers.IntegerField(source="vente.id", read_only=True, default=None)
    numero_vente = serializers.CharField(source="vente.numero_vente", read_only=True, default=None)

    facture_id = serializers.IntegerField(source="facture.id", read_only=True, default=None)
    numero_facture = serializers.CharField(source="facture.numero_facture", read_only=True, default=None)

    lot_id = serializers.IntegerField(source="lot.id", read_only=True, default=None)
    numero_lot = serializers.CharField(source="lot.numero_lot", read_only=True, default=None)

    class Meta:
        model = InventoryMovement
        fields = [
            "id",
            "occurred_at",
            "movement_type",
            "qty",
            "unit_cost",
            "reason",

            "src_bucket",
            "src_bijouterie_nom",

            "dst_bucket",
            "dst_bijouterie_nom",

            "vendor_id",
            "vendor_email",

            "vente_id",
            "numero_vente",

            "facture_id",
            "numero_facture",

            "lot_id",
            "numero_lot",
        ]


class ProduitLineWithInventorySerializer(serializers.ModelSerializer):
    """
    Serializer détaillé pour ProduitLineWithInventoryListView
    """
    # ----- Lot -----
    lot_id = serializers.IntegerField(source="lot.id", read_only=True, default=None)
    numero_lot = serializers.CharField(source="lot.numero_lot", read_only=True, default=None)
    received_at = serializers.DateTimeField(source="lot.received_at", read_only=True, default=None)

    # ----- Achat / fournisseur -----
    achat_id = serializers.IntegerField(source="lot.achat.id", read_only=True, default=None)
    numero_achat = serializers.CharField(source="lot.achat.numero_achat", read_only=True, default=None)

    fournisseur_id = serializers.IntegerField(
        source="lot.achat.fournisseur.id",
        read_only=True,
        default=None,
    )
    fournisseur_nom = serializers.CharField(
        source="lot.achat.fournisseur.nom",
        read_only=True,
        default=None,
    )

    # ----- Produit -----
    produit_id = serializers.IntegerField(source="produit.id", read_only=True)
    produit_nom = serializers.CharField(source="produit.nom", read_only=True)
    produit_sku = serializers.CharField(source="produit.sku", read_only=True, default=None)
    produit_poids = serializers.CharField(source="produit.poids", read_only=True, default=None)

    categorie_nom = serializers.CharField(
        source="produit.categorie.nom",
        read_only=True,
        default=None,
    )
    marque_nom = serializers.CharField(
        source="produit.marque.marque",
        read_only=True,
        default=None,
    )
    purete_nom = serializers.CharField(
        source="produit.purete.purete",
        read_only=True,
        default=None,
    )

    # ----- Ligne achat -----
    quantite = serializers.IntegerField(read_only=True)
    poids_total = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    prix_achat_gramme = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    # ----- Agrégats stock (annotate dans la vue) -----
    quantite_allouee = serializers.IntegerField(read_only=True, default=0)
    quantite_disponible_total = serializers.IntegerField(read_only=True, default=0)

    # ----- Mouvements -----
    movements = serializers.SerializerMethodField()

    class Meta:
        model = ProduitLine
        fields = [
            "id",

            "lot_id",
            "numero_lot",
            "received_at",

            "achat_id",
            "numero_achat",
            "fournisseur_id",
            "fournisseur_nom",

            "produit_id",
            "produit_nom",
            "produit_sku",
            "produit_poids",
            "categorie_nom",
            "marque_nom",
            "purete_nom",

            "quantite",
            "poids_total",
            "prix_achat_gramme",

            "quantite_allouee",
            "quantite_disponible_total",

            "movements",
        ]

    def get_movements(self, obj):
        # Cas optimal : préchargé dans la vue via
        # Prefetch("inventory_movements", queryset=..., to_attr="prefetched_movements")
        if hasattr(obj, "prefetched_movements"):
            return InventoryMovementMiniSerializer(obj.prefetched_movements, many=True).data

        # Fallback si pas de prefetch
        qs = (
            InventoryMovement.objects
            .select_related(
                "src_bijouterie",
                "dst_bijouterie",
                "vendor",
                "vendor__user",
                "vente",
                "facture",
                "lot",
            )
            .filter(produit_line=obj)
            .order_by("-occurred_at", "-id")
        )
        return InventoryMovementMiniSerializer(qs, many=True).data
    