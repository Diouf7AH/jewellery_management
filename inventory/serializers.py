from django.db.models import Sum
from django.db.models.functions import Coalesce
from rest_framework import serializers

from inventory.models import InventoryMovement
from purchase.models import ProduitLine


class InventoryMovementMiniSerializer(serializers.ModelSerializer):
    src = serializers.SerializerMethodField()
    dst = serializers.SerializerMethodField()

    class Meta:
        model = InventoryMovement
        fields = [
            "id",
            "movement_type",
            "qty",
            "src",
            "dst",
            "occurred_at",
            "reason",
        ]

    def get_src(self, obj):
        return {
            "bucket": obj.src_bucket,
            "bijouterie_id": obj.src_bijouterie_id,
            "bijouterie_nom": getattr(obj.src_bijouterie, "nom", None),
        }

    def get_dst(self, obj):
        return {
            "bucket": obj.dst_bucket,
            "bijouterie_id": obj.dst_bijouterie_id,
            "bijouterie_nom": getattr(obj.dst_bijouterie, "nom", None),
        }


class ProduitLineWithInventorySerializer(serializers.ModelSerializer):
    # --- Infos lot / achat / fournisseur ---
    lot_id = serializers.IntegerField(source="lot.id", read_only=True)
    numero_lot = serializers.CharField(source="lot.numero_lot", read_only=True)
    received_at = serializers.DateTimeField(source="lot.received_at", read_only=True)

    achat_id = serializers.IntegerField(source="lot.achat.id", read_only=True)
    numero_achat = serializers.CharField(source="lot.achat.numero_achat", read_only=True)
    fournisseur_id = serializers.IntegerField(source="lot.achat.fournisseur.id", read_only=True)
    fournisseur_nom = serializers.CharField(source="lot.achat.fournisseur.nom", read_only=True)

    # --- Infos produit ---
    produit_id = serializers.IntegerField(source="produit.id", read_only=True)
    produit_nom = serializers.CharField(source="produit.nom", read_only=True)
    produit_poids = serializers.CharField(source="produit.poids", read_only=True)
    produit_sku = serializers.CharField(source="produit.sku", read_only=True, default=None)
    categorie_nom = serializers.CharField(source="produit.categorie.nom", read_only=True, default=None)
    marque_nom = serializers.CharField(source="produit.marque.marque", read_only=True, default=None)
    purete_nom = serializers.CharField(source="produit.purete.purete", read_only=True, default=None)
    # poids_reference = serializers.DecimalField(
    #     source="produit.poids_reference",
    #     max_digits=10,
    #     decimal_places=3,
    #     read_only=True,
    #     default=None,
    # )

    # --- Infos ligne d’achat ---
    quantite = serializers.IntegerField(read_only=True)
    poids_total = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    # poids_unitaire = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True, default=None)
    prix_achat_gramme = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    # --- Agrégats de stock (annotés dans queryset) ---
    quantite_allouee = serializers.IntegerField(read_only=True)
    quantite_disponible_total = serializers.IntegerField(read_only=True)

    # --- Mouvements d’inventaire ---
    movements = serializers.SerializerMethodField()

    class Meta:
        model = ProduitLine
        fields = [
            "id",
            # Lot / achat
            "lot_id", "numero_lot", "received_at",
            "achat_id", "numero_achat",
            "fournisseur_id", "fournisseur_nom",
            # Produit
            "produit_id", "produit_nom", "produit_poids", "produit_sku",
            "categorie_nom", "marque_nom", "purete_nom",
            # "poids_reference",
            # Ligne achat
            "quantite", "poids_total", "prix_achat_gramme",
            # Stock
            "quantite_allouee", "quantite_disponible_total",
            # Inventaire
            "movements",
        ]

    def get_movements(self, obj):
        """
        On utilise les mouvements préfetchés sur lot (related_name='movements')
        et on filtre par produit pour avoir ceux qui concernent cette ligne.
        """
        lot = obj.lot
        if not hasattr(lot, "movements"):
            qs = InventoryMovement.objects.filter(lot=lot, produit=obj.produit)
        else:
            # lot.movements vient du prefetch_related
            qs = [m for m in lot.movements.all() if m.produit_id == obj.produit_id]

        return InventoryMovementMiniSerializer(qs, many=True).data