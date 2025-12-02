from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import serializers

from stock.models import Stock

from .models import Achat, Fournisseur, Lot, ProduitLine

User = get_user_model()

# =============================
# IN : payload ArrivageCreate
# =============================


class FournisseurSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fournisseur
        fields = ["id", "nom", "prenom", "telephone", "address", "slug", "date_ajout", "date_modification"]
        read_only_fields = ["id", "slug", "date_ajout", "date_modification"]

        def validate(self, attrs):
            # soit id, soit au moins telephone
            if not attrs.get("id") and not attrs.get("telephone"):
                raise serializers.ValidationError(
                    "Spécifier soit 'id', soit au minimum 'telephone' pour le fournisseur."
                )
            return attrs
        



class FournisseurInlineSerializer(serializers.Serializer):
    """
    Fournisseur dans le payload d'arrivage.
    Utilisé uniquement en entrée.
    """
    nom = serializers.CharField()
    prenom = serializers.CharField(required=False, allow_blank=True)
    telephone = serializers.CharField(required=False, allow_blank=True)


class LotLineInSerializer(serializers.Serializer):
    """
    Ligne produit d'un arrivage.
    """
    produit_id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1)
    prix_achat_gramme = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=True,  # on le rend obligatoire pour que update_total ait toujours une valeur
    )


class ArrivageCreateInSerializer(serializers.Serializer):
    """
    Payload complet pour POST /api/achat/arrivage
    """
    fournisseur = FournisseurInlineSerializer()
    description = serializers.CharField(required=False, allow_blank=True)
    frais_transport = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        default=Decimal("0.00"),
    )
    frais_douane = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        default=Decimal("0.00"),
    )
    lots = LotLineInSerializer(many=True)


# =============================
# OUT : lignes produit d’un lot
# =============================

class ProduitLineOutSerializer(serializers.ModelSerializer):
    """
    Ligne d'un lot en sortie.
    Aligne les noms avec ton modèle actuel ProduitLine :
      - quantite
      - prix_achat_gramme
    """
    produit_id = serializers.IntegerField(source="produit.id", read_only=True)
    produit_nom = serializers.CharField(source="produit.nom", read_only=True)
    produit_purete = serializers.CharField(source="produit.purete", read_only=True)
    poids_total = serializers.DecimalField(source="poids_total_calc",max_digits=14,decimal_places=3,read_only=True,allow_null=True,)

    class Meta:
        model = ProduitLine
        fields = [
            "id",
            "produit_id",
            "produit_nom",
            "produit_purete",
            "quantite",
            "prix_achat_gramme",
            "poids_total",
        ]


class LotOutSerializer(serializers.ModelSerializer):
    """
    Lot + ses lignes (utile si tu listes les lots ailleurs)
    """
    lignes = ProduitLineOutSerializer(many=True, read_only=True)

    class Meta:
        model = Lot
        fields = ["id", "numero_lot", "description", "received_at", "lignes"]


# =============================
# OUT : achat (mini) pour la réponse
# =============================

class FournisseurMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fournisseur
        fields = ["id", "nom", "prenom", "telephone"]


class AchatSerializer(serializers.ModelSerializer):
    """
    Vue compacte d'un achat (utilisée dans la réponse d'arrivage).
    """
    fournisseur = FournisseurMiniSerializer(read_only=True)
    has_bijouterie_allocations = serializers.BooleanField(read_only=True)
    lots = LotOutSerializer(many=True, read_only=True)

    class Meta:
        model = Achat
        fields = [
            "id",
            "numero_achat",
            "lots",
            "created_at",
            "status",
            "description",
            "frais_transport",
            "frais_douane",
            "montant_total_ht",
            "montant_total_ttc",
            "has_bijouterie_allocations",
            "fournisseur",
        ]
        read_only_fields = fields

# -----------------AchatProduitGetOneView-------------------------
class AchatDetailSerializer(serializers.ModelSerializer):
    fournisseur = FournisseurMiniSerializer(read_only=True)
    lots = LotOutSerializer(many=True, read_only=True)
    has_bijouterie_allocations = serializers.SerializerMethodField()

    def get_has_bijouterie_allocations(self, obj):
        # on appelle simplement la propriété du modèle
        return obj.has_bijouterie_allocations

    class Meta:
        model = Achat
        fields = [
            "id",
            "numero_achat",
            "created_at",
            "status",
            "description",
            "frais_transport",
            "frais_douane",
            "montant_total_ht",
            "montant_total_ttc",
            "fournisseur",
            "has_bijouterie_allocations",
            "lots",
        ]
        read_only_fields = fields
# -----------------End AchatProduitGetOneView-------------------------


# -----------------------------------------------------------
class AchatCreateResponseSerializer(serializers.ModelSerializer):
    lignes = ProduitLineOutSerializer(many=True, read_only=True)
    achat = AchatSerializer(read_only=True)
    has_bijouterie_allocations = serializers.SerializerMethodField()

    class Meta:
        model = Lot
        fields = [
            "id",
            "numero_lot",
            "description",
            "received_at",
            "achat",
            "lignes",
            "has_bijouterie_allocations",
        ]

    def get_has_bijouterie_allocations(self, obj: Lot) -> bool:
        # True si AU MOINS UNE ligne du lot est allouée à une bijouterie
        return Stock.objects.filter(
            produit_line__lot=obj,
            bijouterie__isnull=False,
            quantite_allouee__gt=0,
        ).exists()
# ---------------------------------------------------------

# --- Ligne produit dans un lot ---
class LotDisplayLineSerializer(serializers.ModelSerializer):
    # on expose produit_id + quantite + prix_achat_gramme
    produit_id = serializers.IntegerField(source="produit.id", read_only=True)
    quantite = serializers.IntegerField(source="quantite_total", read_only=True)
    prix_achat_gramme = serializers.DecimalField(
        source="prix_gramme_achat",
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = ProduitLine
        fields = ["produit_id", "quantite", "prix_achat_gramme"]
        ref_name = "LotDisplayLine_V1"



class LotDisplaySerializer(serializers.ModelSerializer):
    fournisseur = FournisseurMiniSerializer(source="achat.fournisseur", read_only=True)
    frais_transport = serializers.DecimalField(
        source="achat.frais_transport",
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )
    frais_douane = serializers.DecimalField(
        source="achat.frais_douane",
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )
    lots = LotDisplayLineSerializer(source="lignes", many=True, read_only=True)

    class Meta:
        model = Lot
        fields = ["fournisseur", "description", "frais_transport", "frais_douane", "numero_lot", "lots"]
        ref_name = "LotDisplay_V1"




class LotListSerializer(serializers.ModelSerializer):
    achat = AchatSerializer(read_only=True)
    lignes = ProduitLineOutSerializer(many=True, read_only=True)
    fournisseur = FournisseurMiniSerializer(read_only=True)

    # Seront fournis par annotate() dans la vue
    nb_lignes = serializers.IntegerField(read_only=True)
    quantite_total = serializers.IntegerField(read_only=True)

    class Meta:
        model = Lot
        fields = [
            "id",
            "numero_lot",
            "description",
            "received_at",
            "achat",
            "lignes",
            "fournisseur",
            "nb_lignes",
            "quantite_total",
        ]
        
# -----------------------------end Lot list----------------------


# =============================
# OUT : réponse ArrivageCreate
# =============================

class AchatCreateResponseSerializer(serializers.ModelSerializer):
    """
    Réponse du ArrivageCreateView :
      -> on renvoie le Lot nouvellement créé,
         avec :
           - ses lignes (lignes)
           - l'achat en nested (achat)
    """
    achat = AchatSerializer(read_only=True)
    lignes = ProduitLineOutSerializer(many=True, read_only=True)

    class Meta:
        model = Lot
        fields = [
            "id",
            "numero_lot",
            "description",
            "received_at",
            "achat",
            "lignes",
        ]
        read_only_fields = fields
    

# -------------------Achat Update-------------------------------

class ArrivageMetaAchatSerializer(serializers.Serializer):
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    frais_transport = serializers.DecimalField(max_digits=12, decimal_places=2, required=False,min_value=Decimal("0.00"),)
    frais_douane = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.00"),
    )
    fournisseur = FournisseurSerializer(required=False)


class ArrivageMetaLotSerializer(serializers.Serializer):
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    received_at = serializers.DateTimeField(required=False)

class ArrivageMetaUpdateInSerializer(serializers.Serializer):
    """
    Payload pour PATCH /arrivage/<lot_id>/meta/
    Tous les champs sont optionnels, mais au moins 'achat' ou 'lot' doit être présent.
    """
    achat = ArrivageMetaAchatSerializer(required=False)
    lot = ArrivageMetaLotSerializer(required=False)

    def validate(self, attrs):
        if "achat" not in attrs and "lot" not in attrs:
            raise serializers.ValidationError(
                "Fournir au moins la clé 'achat' ou 'lot'."
            )
        return attrs
# ---------------------------end Update-----------------------------


# ------------------------------Adjustement-----------------------------
class AdjustmentActionSerializer(serializers.Serializer):
    """
    Une action d'ajustement sur un lot :

    - type = "PURCHASE_IN"  → ajout d'une nouvelle ligne (ProduitLine) dans le lot
    - type = "CANCEL_PURCHASE" → retrait partiel d'une ligne existante

    Règles :
    - PURCHASE_IN     → produit_id, quantite requis, prix_achat_gramme optionnel
    - CANCEL_PURCHASE → produit_line_id, quantite requis
    """
    TYPE_CHOICES = ("PURCHASE_IN", "CANCEL_PURCHASE")

    type = serializers.ChoiceField(choices=TYPE_CHOICES)
    quantite = serializers.IntegerField(min_value=1)

    # POUR PURCHASE_IN
    produit_id = serializers.IntegerField(required=False)
    prix_achat_gramme = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=True,
    )

    # POUR CANCEL_PURCHASE
    produit_line_id = serializers.IntegerField(required=False)

    # Commentaire libre
    reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        t = attrs.get("type")

        if t == "PURCHASE_IN":
            if "produit_id" not in attrs:
                raise serializers.ValidationError(
                    {"produit_id": "Obligatoire quand type = PURCHASE_IN."}
                )
        elif t == "CANCEL_PURCHASE":
            if "produit_line_id" not in attrs:
                raise serializers.ValidationError(
                    {"produit_line_id": "Obligatoire quand type = CANCEL_PURCHASE."}
                )
        else:
            raise serializers.ValidationError({"type": f"Type inconnu: {t}"})

        return attrs


class ArrivageAdjustmentsInSerializer(serializers.Serializer):
    """
    Payload pour POST /api/purchase/arrivages/{lot_id}/adjustments/

    {
      "actions": [
        {
          "type": "PURCHASE_IN",
          "produit_id": 55,
          "quantite": 30,
          "prix_achat_gramme": 42000.00,
          "reason": "Complément de réception"
        },
        {
          "type": "CANCEL_PURCHASE",
          "produit_line_id": 101,
          "quantite": 12,
          "reason": "Retour fournisseur (qualité)"
        }
      ]
    }
    """
    actions = AdjustmentActionSerializer(many=True)

    def validate(self, data):
        actions = data.get("actions") or []
        if not actions:
            raise serializers.ValidationError(
                {"actions": "Au moins une action est requise."}
            )
        return data

# ---------------------------end Adjustement-----------------------------

# --------------------------ProduitLineMiniSerializer----------------------
class ProduitLineMiniSerializer(serializers.ModelSerializer):
    # Lot / achat
    numero_lot = serializers.CharField(source="lot.numero_lot", read_only=True)
    received_at = serializers.DateTimeField(source="lot.received_at", read_only=True)
    numero_achat = serializers.CharField(source="lot.achat.numero_achat", read_only=True)
    fournisseur_nom = serializers.CharField(source="lot.achat.fournisseur.nom", read_only=True)

    # Produit
    produit_id = serializers.IntegerField(source="produit.id", read_only=True)
    produit_nom = serializers.CharField(source="produit.nom", read_only=True)
    produit_sku = serializers.CharField(source="produit.sku", read_only=True, default=None)
    purete_purete = serializers.CharField(source="produit.purete", read_only=True, default=None)

    # Ligne achat
    quantite = serializers.IntegerField(read_only=True)
    poids_total = serializers.DecimalField(source="poids_total_calc",max_digits=14,decimal_places=3,read_only=True,allow_null=True,)
    prix_gramme_achat = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    # Stock (annotés dans queryset)
    quantite_allouee = serializers.IntegerField(read_only=True)
    quantite_disponible_total = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProduitLine
        fields = [
            "id",
            # Lot / achat
            "numero_lot", "received_at", "numero_achat", "fournisseur_nom",
            # Produit
            "produit_id", "produit_nom", "produit_sku", "purete_purete",
            # Ligne achat
            "quantite", "poids_total", "prix_gramme_achat",
            # Stock
            "quantite_allouee", "quantite_disponible_total",
        ]
# ---------------------------ProduitLineMiniSerializer------------------------------