# inventory/serializers.py

from __future__ import annotations

from rest_framework import serializers

from inventory.models import Bucket, InventoryMovement, MovementType
from purchase.models import ProduitLine

# ============================================================
# Résumé inventaire par bijouterie
# ============================================================

class InventoryBijouterieSerializer(serializers.Serializer):
    """
    Compatible avec InventoryBijouterieView.

    stock_magasin_net :
        Stock encore physiquement présent dans le magasin.

    stock_global_net :
        Stock encore détenu par la bijouterie :
        magasin + vendeurs.
    """

    bijouterie_id = serializers.IntegerField()
    bijouterie_nom = serializers.CharField()

    purchase_in = serializers.IntegerField(min_value=0)
    cancel_purchase_out = serializers.IntegerField(min_value=0)

    vendor_assign_out = serializers.IntegerField(min_value=0)
    sale_out = serializers.IntegerField(min_value=0)

    return_in = serializers.IntegerField(min_value=0)

    adjustment_in = serializers.IntegerField(min_value=0)
    adjustment_out = serializers.IntegerField(min_value=0)

    stock_magasin_net = serializers.IntegerField()
    stock_global_net = serializers.IntegerField()


# ============================================================
# Résumé inventaire par vendeur
# ============================================================

class InventoryVendorSerializer(serializers.Serializer):
    """
    Compatible avec le cycle :

        BIJOUTERIE
            ↓ VENDOR_ASSIGN
        VENDOR
            ↓ SALE_OUT
        EXTERNAL

    RETURN_IN ne retourne pas dans le stock vendeur.
    Il retourne directement dans le stock de la bijouterie.
    """

    vendor_id = serializers.IntegerField()
    vendor_nom = serializers.CharField(
        allow_blank=True,
    )
    vendor_email = serializers.EmailField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    bijouterie_id = serializers.IntegerField(
        allow_null=True,
        required=False,
    )
    bijouterie_nom = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    # Quantité reçue par affectation.
    vendor_assign_in = serializers.IntegerField(
        min_value=0,
    )

    # Quantité vendue.
    sale_out_vendor = serializers.IntegerField(
        min_value=0,
    )

    # VendorStock.quantite_allouee
    quantite_allouee = serializers.IntegerField(
        min_value=0,
        required=False,
        default=0,
    )

    # VendorStock.quantite_vendue
    quantite_vendue = serializers.IntegerField(
        min_value=0,
        required=False,
        default=0,
    )

    # quantite_allouee - quantite_vendue
    stock_restant = serializers.IntegerField(
        min_value=0,
    )


# ============================================================
# Petit serializer d'un mouvement lié à une ProduitLine
# ============================================================

class InventoryMovementSerializer(serializers.ModelSerializer):
    movement_type_label = serializers.CharField(
        source="get_movement_type_display",
        read_only=True,
    )

    src_bucket_label = serializers.CharField(
        source="get_src_bucket_display",
        read_only=True,
    )

    dst_bucket_label = serializers.CharField(
        source="get_dst_bucket_display",
        read_only=True,
    )

    produit_nom = serializers.CharField(
        source="produit.nom",
        read_only=True,
    )

    produit_sku = serializers.CharField(
        source="produit.sku",
        read_only=True,
    )

    numero_lot = serializers.CharField(
        source="lot.numero_lot",
        read_only=True,
        default=None,
    )

    numero_achat = serializers.CharField(
        source="achat.numero_achat",
        read_only=True,
        default=None,
    )

    numero_vente = serializers.CharField(
        source="vente.numero_vente",
        read_only=True,
        default=None,
    )

    numero_facture = serializers.CharField(
        source="facture.numero_facture",
        read_only=True,
        default=None,
    )

    vendor_nom = serializers.SerializerMethodField()
    vendor_email = serializers.EmailField(
        source="vendor.user.email",
        read_only=True,
        default=None,
    )

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

    created_by_nom = serializers.SerializerMethodField()
    created_by_email = serializers.EmailField(
        source="created_by.email",
        read_only=True,
        default=None,
    )

    total_cost = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = InventoryMovement

        fields = [
            "id",
            "occurred_at",
            "created_at",

            "movement_type",
            "movement_type_label",

            "produit_id",
            "produit_nom",
            "produit_sku",

            "produit_line_id",

            "lot_id",
            "numero_lot",

            "achat_id",
            "numero_achat",

            "qty",
            "unit_cost",
            "total_cost",

            "src_bucket",
            "src_bucket_label",
            "src_bijouterie_id",
            "src_bijouterie_nom",

            "dst_bucket",
            "dst_bucket_label",
            "dst_bijouterie_id",
            "dst_bijouterie_nom",

            "vendor_id",
            "vendor_nom",
            "vendor_email",

            "vente_id",
            "numero_vente",
            "vente_ligne_id",

            "facture_id",
            "numero_facture",

            "stock_consumed",
            "is_locked",

            "reason",

            "created_by_id",
            "created_by_nom",
            "created_by_email",
        ]

        read_only_fields = fields

    def get_vendor_nom(self, obj):
        if not obj.vendor:
            return None

        user = obj.vendor.user

        full_name = user.get_full_name().strip()

        return full_name or user.email

    def get_created_by_nom(self, obj):
        if not obj.created_by:
            return None

        full_name = obj.created_by.get_full_name().strip()

        return full_name or obj.created_by.email


# ============================================================
# Stock magasin lié à une ProduitLine
# ============================================================

class ProduitLineStockSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)

    bijouterie_id = serializers.IntegerField(
        read_only=True,
    )

    bijouterie_nom = serializers.CharField(
        source="bijouterie.nom",
        read_only=True,
        default=None,
    )

    en_stock = serializers.IntegerField(
        read_only=True,
    )

    quantite_totale = serializers.IntegerField(
        read_only=True,
    )


# ============================================================
# Stock vendeur lié à une ProduitLine
# ============================================================

class ProduitLineVendorStockSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)

    vendor_id = serializers.IntegerField(
        read_only=True,
    )

    vendor_nom = serializers.SerializerMethodField()

    vendor_email = serializers.EmailField(
        source="vendor.user.email",
        read_only=True,
        default=None,
    )

    bijouterie_id = serializers.IntegerField(
        read_only=True,
    )

    bijouterie_nom = serializers.CharField(
        source="bijouterie.nom",
        read_only=True,
        default=None,
    )

    quantite_allouee = serializers.IntegerField(
        read_only=True,
    )

    quantite_vendue = serializers.IntegerField(
        read_only=True,
    )

    en_stock = serializers.IntegerField(
        read_only=True,
    )

    def get_vendor_nom(self, obj):
        vendor = getattr(obj, "vendor", None)

        if not vendor:
            return None

        user = getattr(vendor, "user", None)

        if not user:
            return f"Vendeur #{vendor.pk}"

        full_name = user.get_full_name().strip()

        return full_name or user.email


# ============================================================
# ProduitLine avec stock et mouvements d'inventaire
# ============================================================

class ProduitLineWithInventorySerializer(
    serializers.ModelSerializer
):
    # ========================================================
    # Achat
    # ========================================================

    achat_id = serializers.IntegerField(
        source="lot.achat_id",
        read_only=True,
    )

    numero_achat = serializers.CharField(
        source="lot.achat.numero_achat",
        read_only=True,
        default=None,
    )

    achat_status = serializers.CharField(
        source="lot.achat.status",
        read_only=True,
        default=None,
    )

    reference_commande = serializers.CharField(
        source="lot.achat.reference_commande",
        read_only=True,
        default=None,
    )

    # ========================================================
    # Bijouterie d'achat
    # ========================================================

    bijouterie_id = serializers.IntegerField(
        source="lot.achat.bijouterie_id",
        read_only=True,
    )

    bijouterie_nom = serializers.CharField(
        source="lot.achat.bijouterie.nom",
        read_only=True,
        default=None,
    )

    # ========================================================
    # Fournisseur
    # ========================================================

    fournisseur_id = serializers.IntegerField(
        source="lot.achat.fournisseur_id",
        read_only=True,
        allow_null=True,
    )

    fournisseur_nom = serializers.SerializerMethodField()

    fournisseur_telephone = serializers.CharField(
        source="lot.achat.fournisseur.telephone",
        read_only=True,
        default=None,
    )

    # ========================================================
    # Lot
    # ========================================================

    lot_id = serializers.IntegerField(
        read_only=True,
    )

    numero_lot = serializers.CharField(
        source="lot.numero_lot",
        read_only=True,
    )

    lot_description = serializers.CharField(
        source="lot.description",
        read_only=True,
        allow_blank=True,
    )

    received_at = serializers.DateTimeField(
        source="lot.received_at",
        read_only=True,
    )

    # ========================================================
    # Produit
    # ========================================================

    produit_id = serializers.IntegerField(
        read_only=True,
    )

    produit_nom = serializers.CharField(
        source="produit.nom",
        read_only=True,
        default=None,
    )

    produit_sku = serializers.CharField(
        source="produit.sku",
        read_only=True,
        default=None,
    )

    produit_slug = serializers.CharField(
        source="produit.slug",
        read_only=True,
        default=None,
    )

    categorie_id = serializers.IntegerField(
        source="produit.categorie_id",
        read_only=True,
        allow_null=True,
    )

    categorie_nom = serializers.CharField(
        source="produit.categorie.nom",
        read_only=True,
        default=None,
    )

    modele_id = serializers.IntegerField(
        source="produit.modele_id",
        read_only=True,
        allow_null=True,
    )

    modele_nom = serializers.CharField(
        source="produit.modele.modele",
        read_only=True,
        default=None,
    )

    marque_id = serializers.IntegerField(
        source="produit.marque_id",
        read_only=True,
        allow_null=True,
    )

    marque_nom = serializers.CharField(
        source="produit.marque.nom",
        read_only=True,
        default=None,
    )

    purete_id = serializers.IntegerField(
        source="produit.purete_id",
        read_only=True,
        allow_null=True,
    )

    purete_nom = serializers.CharField(
        source="produit.purete.purete",
        read_only=True,
        default=None,
    )

    poids_unitaire = serializers.DecimalField(
        source="produit.poids",
        max_digits=14,
        decimal_places=3,
        read_only=True,
        allow_null=True,
    )

    poids_total = serializers.SerializerMethodField()

    # ========================================================
    # Annotations calculées par la vue
    # ========================================================

    stock_magasin = serializers.IntegerField(
        read_only=True,
        default=0,
    )

    quantite_entree_cumulee = serializers.IntegerField(
        read_only=True,
        default=0,
    )

    quantite_allouee_vendeur = serializers.IntegerField(
        read_only=True,
        default=0,
    )

    quantite_vendue = serializers.IntegerField(
        read_only=True,
        default=0,
    )

    quantite_retournee = serializers.IntegerField(
        read_only=True,
        default=0,
    )

    stock_vendeur = serializers.IntegerField(
        read_only=True,
        default=0,
    )

    stock_global = serializers.IntegerField(
        read_only=True,
        default=0,
    )

    # ========================================================
    # Détails des stocks
    # ========================================================

    stocks = ProduitLineStockSerializer(
        many=True,
        read_only=True,
    )

    vendor_stocks = ProduitLineVendorStockSerializer(
        many=True,
        read_only=True,
    )

    # ========================================================
    # Mouvements
    # ========================================================

    movements = InventoryMovementSerializer(
        source="inventory_movements",
        many=True,
        read_only=True,
    )

    class Meta:
        model = ProduitLine

        fields = [
            "id",

            # Achat
            "achat_id",
            "numero_achat",
            "achat_status",
            "reference_commande",

            # Bijouterie
            "bijouterie_id",
            "bijouterie_nom",

            # Fournisseur
            "fournisseur_id",
            "fournisseur_nom",
            "fournisseur_telephone",

            # Lot
            "lot_id",
            "numero_lot",
            "lot_description",
            "received_at",

            # Produit
            "produit_id",
            "produit_nom",
            "produit_sku",
            "produit_slug",

            "categorie_id",
            "categorie_nom",

            "modele_id",
            "modele_nom",

            "marque_id",
            "marque_nom",

            "purete_id",
            "purete_nom",

            "poids_unitaire",
            "poids_total",

            # Données achat
            "prix_achat_gramme",
            "quantite",

            # Résumé stock
            "stock_magasin",
            "quantite_entree_cumulee",
            "quantite_allouee_vendeur",
            "quantite_vendue",
            "quantite_retournee",
            "stock_vendeur",
            "stock_global",

            # Détails
            "stocks",
            "vendor_stocks",
            "movements",
        ]

        read_only_fields = fields

    def get_fournisseur_nom(self, obj):
        achat = getattr(obj.lot, "achat", None)

        if not achat:
            return None

        fournisseur = getattr(
            achat,
            "fournisseur",
            None,
        )

        if not fournisseur:
            return None

        parts = [
            fournisseur.nom,
            fournisseur.prenom,
        ]

        full_name = " ".join(
            part.strip()
            for part in parts
            if part and part.strip()
        )

        return (
            full_name
            or fournisseur.telephone
            or f"Fournisseur #{fournisseur.pk}"
        )

    def get_poids_total(self, obj):
        poids = getattr(
            obj.produit,
            "poids",
            None,
        )

        if poids is None:
            return None

        return poids * obj.quantite
    

