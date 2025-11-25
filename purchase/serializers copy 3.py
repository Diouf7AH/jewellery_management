from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import serializers

from store.models import Produit

from .models import Achat, Fournisseur, Lot, ProduitLine

User = get_user_model()





# =============================
#  IN : payload ArrivageCreate
# =============================

class FournisseurInlineSerializer(serializers.Serializer):
    nom = serializers.CharField()
    prenom = serializers.CharField(required=False, allow_blank=True)
    telephone = serializers.CharField(required=True, allow_blank=True)


class LotLineInSerializer(serializers.Serializer):
    produit_id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1)
    prix_achat_gramme = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=True,
    )


class ArrivageCreateInSerializer(serializers.Serializer):
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
#  OUT : lignes produit d’un lot
# =============================

class ProduitLineOutSerializer(serializers.ModelSerializer):
    produit_id = serializers.IntegerField(source="produit.id", read_only=True)
    produit_nom = serializers.CharField(source="produit.nom", read_only=True)

    class Meta:
        model = ProduitLine
        fields = [
            "id",
            "produit_id",
            "produit_nom",
            "quantite",
            "prix_achat_gramme",
        ]
        read_only_fields = fields


class LotOutSerializer(serializers.ModelSerializer):
    lignes = ProduitLineOutSerializer(many=True, read_only=True)

    class Meta:
        model = Lot
        fields = ["id", "numero_lot", "description", "received_at", "lignes"]
        read_only_fields = fields


# =============================
#  DÉTAIL Achat (bloc inclus dans la réponse)
# =============================

class FournisseurMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fournisseur
        fields = ["id", "nom", "prenom", "telephone"]
        read_only_fields = fields


class AchatDetailSerializer(serializers.ModelSerializer):
    fournisseur = FournisseurMiniSerializer(read_only=True)

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
        ]
        read_only_fields = fields


# =============================
#  OUT : réponse ArrivageCreate
# =============================

class AchatCreateResponseSerializer(serializers.ModelSerializer):
    """
    Réponse de ArrivageCreateView :
    On renvoie le lot créé avec :
      - ses lignes produits (lignes)
      - un bloc 'achat' avec les infos principales
    """
    lignes = ProduitLineOutSerializer(many=True, read_only=True)
    achat = AchatDetailSerializer(read_only=True)

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


# -----------------------------------------------------------------
# -----------------List Lot-
# ------------------------------------------------------------------
class LotListSerializer(serializers.ModelSerializer):
    achat_id = serializers.IntegerField(source="achat.id", read_only=True)
    numero_achat = serializers.CharField(source="achat.numero_achat", read_only=True)

    fournisseur_nom = serializers.CharField(
        source="achat.fournisseur.nom", read_only=True
    )
    fournisseur_prenom = serializers.CharField(
        source="achat.fournisseur.prenom", read_only=True
    )
    fournisseur_telephone = serializers.CharField(
        source="achat.fournisseur.telephone", read_only=True
    )

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
            "achat_id",
            "numero_achat",
            "fournisseur_nom",
            "fournisseur_prenom",
            "fournisseur_telephone",
            "nb_lignes",
            "quantite_total",
        ]
        
# -----------------------------end Lot list----------------------


# ------------------------------List achts-----------------------------

# ---------- Serializer LISTE / DÉTAIL simple d'un achat ----------
class AchatSerializer(serializers.ModelSerializer):
    """
    Utilisé par AchatListView :
    - infos principales de l'achat
    - mini-fournisseur
    (pas de détails de lots ici pour garder la liste légère)
    """
    fournisseur = FournisseurMiniSerializer(read_only=True)

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
        ]
        read_only_fields = fields

# ---------------------------end achat list---------------------------


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
        

# -----------------------------Update------------------------------

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
    produit_id = serializers.IntegerField(required=True, min_value=1)
    prix_achat_gramme = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=True,
    )

    # POUR CANCEL_PURCHASE
    produit_line_id = serializers.IntegerField(required=True, min_value=1)

    # Commentaire libre
    reason = serializers.CharField(required=False, allow_blank=True)

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