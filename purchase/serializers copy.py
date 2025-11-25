from decimal import Decimal, InvalidOperation
from typing import List

from django.contrib.auth import get_user_model
from rest_framework import serializers

from purchase.models import Achat, Lot, ProduitLine
from store.models import Bijouterie, Marque, Modele, Produit, Purete

from .models import Achat, Fournisseur, Lot

User = get_user_model()

# ---------- Champs utilitaires ----------


# class BijouterieIdNullableField(serializers.Field):
#     """
#     Accepte: null / "" / 0 -> None (réservé), sinon un id > 0 d’une bijouterie existante.
#     """
#     default_error_messages = {
#         "invalid": "bijouterie_id invalide.",
#         "not_found": "Bijouterie introuvable.",
#     }

#     def to_internal_value(self, data):
#         if data in (None, "", 0, "0"):
#             return None
#         try:
#             bid = int(data)
#         except Exception:
#             self.fail("invalid")
#         if bid <= 0:
#             return None
#         if not Bijouterie.objects.filter(pk=bid).exists():
#             self.fail("not_found")
#         return bid

#     def to_representation(self, value):
#         return value  # None ou int


# # ---------- Sorties (read) ----------

# class ProduitSlimSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Produit
#         fields = ["id", "nom", "sku", "poids"]


# class FournisseurSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Fournisseur
#         fields = ["id", "nom", "prenom", "telephone", "address", "slug", "date_ajout", "date_modification"]
#         read_only_fields = ["id", "slug", "date_ajout", "date_modification"]

# # --------------Create---------------------

# # --- Références produit (inchangé) ---
# class ProduitRefField(serializers.IntegerField):
#     default_error_messages = {
#         "invalid": "Le champ 'produit' doit être un entier (id).",
#         "required": "Le champ 'produit' est requis.",
#         "min_value": "L'id produit doit être > 0.",
#     }
#     def __init__(self, **kwargs):
#         kwargs.setdefault("min_value", 1)
#         super().__init__(**kwargs)

#     swagger_schema_fields = {
#         "type": "integer",
#         "format": "int64",
#         "example": 12,
#         "title": "Produit (id)",
#         "description": "Identifiant entier du produit",
#     }


# # ---------------------------------LIST--------------------------------------------
# class LotListSerializer(serializers.ModelSerializer):
#     achat_id = serializers.IntegerField(source="achat.id", read_only=True)
#     numero_achat = serializers.CharField(source="achat.numero_achat", read_only=True)
#     fournisseur_id = serializers.IntegerField(source="achat.fournisseur.id", read_only=True)
#     fournisseur_nom = serializers.CharField(source="achat.fournisseur.nom", read_only=True)
#     fournisseur_prenom = serializers.CharField(source="achat.fournisseur.prenom", read_only=True)
#     fournisseur_telephone = serializers.CharField(source="achat.fournisseur.telephone", read_only=True)

#     nb_lignes = serializers.IntegerField(read_only=True)
#     quantite = serializers.IntegerField(read_only=True)

#     # Poids calculés à la volée (annotés ou fallback calcul serializer)
#     poids_total = serializers.DecimalField(max_digits=18, decimal_places=3, read_only=True)
#     poids_restant = serializers.DecimalField(max_digits=18, decimal_places=3, read_only=True)

#     class Meta:
#         model = Lot
#         fields = [
#             "id", "numero_lot", "description", "received_at",
#             "achat_id", "numero_achat",
#             "fournisseur_id", "fournisseur_nom", "fournisseur_prenom", "fournisseur_telephone",
#             "nb_lignes", "quantite",
#             "poids_total", "poids_restant",
#         ]
        

# class FournisseurOutSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Fournisseur
#         fields = ["nom", "prenom", "telephone"]
#         ref_name = "FournisseurOut_V1"

# class LotDisplayLineSerializer(serializers.ModelSerializer):
#     # renommer les champs pour matcher ton shape
#     produit_id = serializers.IntegerField(source="produit.id", read_only=True)
#     quantite = serializers.IntegerField(source="quantite", read_only=True)
#     prix_achat_gramme = serializers.DecimalField(source="prix_achat_gramme", max_digits=14, decimal_places=2, read_only=True)

#     class Meta:
#         model = ProduitLine
#         fields = ["produit_id", "quantite", "prix_achat_gramme"]
#         ref_name = "LotDisplayLine_V1"

# class LotDisplaySerializer(serializers.ModelSerializer):
#     fournisseur = FournisseurOutSerializer(source="achat.fournisseur", read_only=True)
#     frais_transport = serializers.DecimalField(source="achat.frais_transport", max_digits=12, decimal_places=2, read_only=True)
#     frais_douane    = serializers.DecimalField(source="achat.frais_douane",    max_digits=12, decimal_places=2, read_only=True)
#     lots = LotDisplayLineSerializer(source="lignes", many=True, read_only=True)

#     class Meta:
#         model = Lot
#         fields = ["fournisseur", "description", "frais_transport", "frais_douane", "numero_lot", "lots"]
#         ref_name = "LotDisplay_V1"
# # ------------------------------------END LIST---------------------------------------

# # ----------------------------------------Lot display---------------------------------------------
# class FournisseurOutSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Fournisseur
#         fields = ["nom", "prenom", "telephone"]
#         ref_name = "FournisseurOut_V1"

# class LotDisplayLineSerializer(serializers.ModelSerializer):
#     # renommer les champs pour matcher ton shape
#     produit_id = serializers.IntegerField(source="produit.id", read_only=True)
#     quantite = serializers.IntegerField(source="quantite", read_only=True)
#     prix_achat_gramme = serializers.DecimalField(source="prix_achat_gramme", max_digits=14, decimal_places=2, read_only=True)

#     class Meta:
#         model = ProduitLine
#         fields = ["produit_id", "quantite", "prix_achat_gramme"]
#         ref_name = "LotDisplayLine_V1"

# class LotDisplaySerializer(serializers.ModelSerializer):
#     fournisseur = FournisseurOutSerializer(source="achat.fournisseur", read_only=True)
#     frais_transport = serializers.DecimalField(source="achat.frais_transport", max_digits=12, decimal_places=2, read_only=True)
#     frais_douane    = serializers.DecimalField(source="achat.frais_douane",    max_digits=12, decimal_places=2, read_only=True)
#     lots = LotDisplayLineSerializer(source="lignes", many=True, read_only=True)

#     class Meta:
#         model = Lot
#         fields = ["fournisseur", "description", "frais_transport", "frais_douane", "numero_lot", "lots"]
#         ref_name = "LotDisplay_V1"
# # -----------------------------------------End lot display----------------------------------------------

# # Réutilise tes serializers existants :
# # - ProduitLineOutSerializer (déjà défini dans ton message)
# # - LotOutSerializer ci-dessous (pour réutiliser ProduitLineOutSerializer)
# # --- Lignes produit (dans un lot) ---
# class ProduitLineOutSerializer(serializers.ModelSerializer):
#     produit_id = serializers.IntegerField(source="produit.id", read_only=True)
#     produit_nom = serializers.CharField(source="produit.nom", read_only=True)

#     class Meta:
#         model = ProduitLine
#         fields = [
#             "id", "produit_id", "produit_nom",
#             "quantite",
#             "prix_achat_gramme",
#         ]

# class FournisseurSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Fournisseur
#         fields = ["id", "nom", "prenom", "telephone"]


# class LotOutSerializer(serializers.ModelSerializer):
#     lignes = ProduitLineOutSerializer(many=True, read_only=True)

#     class Meta:
#         model = Lot
#         fields = ["id", "numero_lot", "description", "received_at", "lignes"]


# class AchatSerializer(serializers.ModelSerializer):
#     fournisseur = FournisseurSerializer(read_only=True)
#     lots = LotOutSerializer(many=True, read_only=True)

#     class Meta:
#         model = Achat
#         fields = [
#             "id", "numero_achat", "created_at", "status",
#             "description",
#             "frais_transport", "frais_douane",
#             "montant_total_ht", "montant_total_ttc",
#             "fournisseur", "lots",
#         ]
#         read_only_fields = fields  # tout en lecture seule pour le détail


# class AchatListSerializer(serializers.ModelSerializer):
#     fournisseur_nom = serializers.CharField(source="fournisseur.nom", read_only=True)
#     fournisseur_prenom = serializers.CharField(source="fournisseur.prenom", read_only=True)
#     fournisseur_telephone = serializers.CharField(source="fournisseur.telephone", read_only=True)
#     nb_lots = serializers.IntegerField(source="lots.count", read_only=True)

#     class Meta:
#         model = Achat
#         fields = [
#             "id", "numero_achat", "created_at", "status",
#             "fournisseur_nom", "fournisseur_prenom", "fournisseur_telephone", "montant_total_ttc", "nb_lots",
#         ]
#         read_only_fields = fields
        
# # -----------------------Arrivage ------------------------------------------

# # ===== IN =====
# class FournisseurInlineSerializer(serializers.Serializer):
#     nom = serializers.CharField()
#     prenom = serializers.CharField(required=False, allow_blank=True)
#     telephone = serializers.CharField(required=False, allow_blank=True)

# class LotLineInSerializer(serializers.Serializer):
#     produit_id = serializers.IntegerField()
#     quantite = serializers.IntegerField(min_value=1)
#     prix_achat_gramme = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)

# class ArrivageCreateInSerializer(serializers.Serializer):
#     fournisseur = FournisseurInlineSerializer()
#     description = serializers.CharField(required=False, allow_blank=True)
#     frais_transport = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal("0.00"))
#     frais_douane    = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal("0.00"))
#     # numero_lot      = serializers.CharField()
#     lots            = LotLineInSerializer(many=True)

# # ===== OUT =====
# class AchatCreateResponseSerializer(serializers.ModelSerializer):
#     lignes = ProduitLineOutSerializer(many=True, read_only=True)
#     achat_id         = serializers.IntegerField(source="achat.id", read_only=True)
#     numero_achat     = serializers.CharField(source="achat.numero_achat", read_only=True)
#     created_at       = serializers.DateTimeField(source="achat.created_at", read_only=True)
#     frais_transport  = serializers.DecimalField(source="achat.frais_transport", max_digits=12, decimal_places=2, read_only=True)
#     frais_douane     = serializers.DecimalField(source="achat.frais_douane", max_digits=12, decimal_places=2, read_only=True)
#     montant_total_ht = serializers.DecimalField(source="achat.montant_total_ht", max_digits=14, decimal_places=2, read_only=True)
#     montant_total_ttc= serializers.DecimalField(source="achat.montant_total_ttc", max_digits=14, decimal_places=2, read_only=True)
#     status           = serializers.CharField(source="achat.status", read_only=True)

#     class Meta:
#         model  = Lot
#         fields = [
#             "id", "numero_lot", "description", "received_at",
#             "achat_id", "numero_achat", "created_at", "status",
#             "frais_transport", "frais_douane",
#             "montant_total_ht", "montant_total_ttc",
#             "lignes",
#         ]

class BijouterieIdNullableField(serializers.Field):
    """
    Accepte: null / "" / 0 -> None (réservé), sinon un id > 0 d’une bijouterie existante.
    """
    default_error_messages = {
        "invalid": "bijouterie_id invalide.",
        "not_found": "Bijouterie introuvable.",
    }

    def to_internal_value(self, data):
        if data in (None, "", 0, "0"):
            return None
        try:
            bid = int(data)
        except Exception:
            self.fail("invalid")
        if bid <= 0:
            return None
        if not Bijouterie.objects.filter(pk=bid).exists():
            self.fail("not_found")
        return bid

    def to_representation(self, value):
        return value  # None ou int
    

# class ProduitSlimSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Produit
#         fields = ["id", "nom", "sku", "poids"]


class FournisseurSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fournisseur
        fields = ["id", "nom", "prenom", "telephone", "address", "slug", "date_ajout", "date_modification"]
        read_only_fields = ["id", "slug", "date_ajout", "date_modification"]

# Référence produit
class ProduitRefField(serializers.IntegerField):
    default_error_messages = {
        "invalid": "Le champ 'produit' doit être un entier (id).",
        "required": "Le champ 'produit' est requis.",
        "min_value": "L'id produit doit être > 0.",
    }

    def __init__(self, **kwargs):
        kwargs.setdefault("min_value", 1)
        super().__init__(**kwargs)

    swagger_schema_fields = {
        "type": "integer",
        "format": "int64",
        "example": 12,
        "title": "Produit (id)",
        "description": "Identifiant entier du produit",
    }
    

# LISTE DES LOTS
class LotListSerializer(serializers.ModelSerializer):
    achat_id = serializers.IntegerField(source="achat.id", read_only=True)
    numero_achat = serializers.CharField(source="achat.numero_achat", read_only=True)
    fournisseur_id = serializers.IntegerField(source="achat.fournisseur.id", read_only=True)
    fournisseur_nom = serializers.CharField(source="achat.fournisseur.nom", read_only=True)
    fournisseur_prenom = serializers.CharField(source="achat.fournisseur.prenom", read_only=True)
    fournisseur_telephone = serializers.CharField(source="achat.fournisseur.telephone", read_only=True)

    nb_lignes = serializers.IntegerField(read_only=True)
    quantite = serializers.IntegerField(read_only=True)

    # Poids calculés à la volée (annotés dans la queryset)
    poids_total = serializers.DecimalField(max_digits=18, decimal_places=3, read_only=True)
    poids_restant = serializers.DecimalField(max_digits=18, decimal_places=3, read_only=True)

    class Meta:
        model = Lot
        fields = [
            "id", "numero_lot", "description", "received_at",
            "achat_id", "numero_achat",
            "fournisseur_id", "fournisseur_nom", "fournisseur_prenom", "fournisseur_telephone",
            "nb_lignes", "quantite",
            "poids_total", "poids_restant",
        ]


class FournisseurOutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fournisseur
        fields = ["nom", "prenom", "telephone"]
        ref_name = "FournisseurOut_V1"


class LotDisplayLineSerializer(serializers.ModelSerializer):
    # renommer les champs pour matcher ton shape
    produit_id = serializers.IntegerField(source="produit.id", read_only=True)
    quantite = serializers.IntegerField(source="quantite", read_only=True)
    prix_achat_gramme = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = ProduitLine
        fields = ["produit_id", "quantite", "prix_achat_gramme"]
        ref_name = "LotDisplayLine_V1"


class LotDisplaySerializer(serializers.ModelSerializer):
    fournisseur = FournisseurOutSerializer(source="achat.fournisseur", read_only=True)
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


# Détail ProduitLine / Lot / Achat
class ProduitLineOutSerializer(serializers.ModelSerializer):
    produit_id = serializers.IntegerField(source="produit.id", read_only=True)
    produit_nom = serializers.CharField(source="produit.nom", read_only=True)
    prix_achat_gramme = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = ProduitLine
        fields = [
            "id",
            "produit_id",
            "produit_nom",
            "quantite",
            "prix_achat_gramme",
        ]


class FournisseurMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fournisseur
        fields = ["id", "nom", "prenom", "telephone"]

class LotOutSerializer(serializers.ModelSerializer):
    lignes = ProduitLineOutSerializer(many=True, read_only=True)

    class Meta:
        model = Lot
        fields = ["id", "numero_lot", "description", "received_at", "lignes"]

class AchatSerializer(serializers.ModelSerializer):
    fournisseur = FournisseurMiniSerializer(read_only=True)
    lots = LotOutSerializer(many=True, read_only=True)

    class Meta:
        model = Achat
        fields = [
            "id", "numero_achat", "created_at", "status",
            "description",
            "frais_transport", "frais_douane",
            "montant_total_ht", "montant_total_ttc",
            "fournisseur", "lots",
        ]
        read_only_fields = fields  # tout en lecture seule pour le détail

class AchatListSerializer(serializers.ModelSerializer):
    fournisseur_nom = serializers.CharField(source="fournisseur.nom", read_only=True)
    fournisseur_prenom = serializers.CharField(source="fournisseur.prenom", read_only=True)
    fournisseur_telephone = serializers.CharField(source="fournisseur.telephone", read_only=True)
    nb_lots = serializers.IntegerField(source="lots.count", read_only=True)

    class Meta:
        model = Achat
        fields = [
            "id", "numero_achat", "created_at", "status",
            "fournisseur_nom", "fournisseur_prenom", "fournisseur_telephone",
            "montant_total_ttc", "nb_lots",
        ]
        read_only_fields = fields
        

# Arrivage (IN / OUT)
# IN
class FournisseurInlineSerializer(serializers.Serializer):
    nom = serializers.CharField()
    prenom = serializers.CharField(required=False, allow_blank=True)
    telephone = serializers.CharField(required=False, allow_blank=True)


class LotLineInSerializer(serializers.Serializer):
    produit_id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1)
    prix_achat_gramme = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
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

# OUT
class AchatCreateResponseSerializer(serializers.ModelSerializer):
    lignes = ProduitLineOutSerializer(many=True, read_only=True)
    achat_id = serializers.IntegerField(source="achat.id", read_only=True)
    numero_achat = serializers.CharField(source="achat.numero_achat", read_only=True)
    created_at = serializers.DateTimeField(source="achat.created_at", read_only=True)
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
    montant_total_ht = serializers.DecimalField(
        source="achat.montant_total_ht",
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    montant_total_ttc = serializers.DecimalField(
        source="achat.montant_total_ttc",
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    status = serializers.CharField(source="achat.status", read_only=True)

    class Meta:
        model = Lot
        fields = [
            "id", "numero_lot", "description", "received_at",
            "achat_id", "numero_achat", "created_at", "status",
            "frais_transport", "frais_douane",
            "montant_total_ht", "montant_total_ttc",
            "lignes",
        ]

# -----------------End Create Response Serializer---------------

# ---------- UPDATE documentaire de l'achat (pas de stock dans cette vue) ----------

# class AchatProduitUpdateItemSerializer(serializers.Serializer):
#     """
#     Item pour mise à jour documentaire :
#     - si 'id' présent ⇒ update partiel (prix/taxe), interdit de changer produit/quantite
#     - si 'id' absent ⇒ création d'une nouvelle ligne (produit+quantite requis)
#     """
#     id = serializers.IntegerField(required=False)
#     produit = ProduitRefField(required=False)
#     quantite = serializers.IntegerField(min_value=1, required=False)
#     prix_achat_gramme = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
#     tax = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)

#     def validate(self, attrs):
#         if "id" in attrs:
#             if "quantite" in attrs or "produit" in attrs:
#                 raise serializers.ValidationError(
#                     "Impossible de modifier 'quantite' ou 'produit' d’une ligne existante. Annule et recrée si besoin."
#                 )
#         else:
#             # création ⇒ produit et quantite requis
#             if "produit" not in attrs or "quantite" not in attrs:
#                 raise serializers.ValidationError("Pour créer une ligne, 'produit' et 'quantite' sont requis.")
#         return attrs


# class AchatUpdateSerializer(serializers.Serializer):
#     """
#     Body de AchatUpdateView :
#     - MAJ fournisseur (optionnel)
#     - Ajout / MAJ documentaire de lignes via 'lignes'
#     """
#     fournisseur = FournisseurInlineSerializer(required=False)
#     lignes = AchatProduitUpdateItemSerializer(many=True, required=False)

#     def validate(self, attrs):
#         if not attrs:
#             raise serializers.ValidationError("Aucun champ à mettre à jour.")
#         return attrs

class AchatProduitUpdateItemSerializer(serializers.Serializer):
    """
    Item pour mise à jour documentaire des lignes d'un achat.

    - si 'id' présent  ⇒ update partiel (prix/taxe),
      ⚠️ interdit de changer 'produit' ou 'quantite'.
    - si 'id' absent  ⇒ création d'une nouvelle ligne :
      'produit' et 'quantite' sont requis.
    """
    id = serializers.IntegerField(required=False)
    produit = ProduitRefField(required=False)
    quantite = serializers.IntegerField(min_value=1, required=False)
    prix_achat_gramme = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    tax = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
    )

    def validate(self, attrs):
        has_id = "id" in attrs

        if has_id:
            # ligne existante : on ne touche pas au produit / quantite
            if "quantite" in attrs or "produit" in attrs:
                raise serializers.ValidationError(
                    "Impossible de modifier 'quantite' ou 'produit' d’une ligne existante. "
                    "Annule et recrée si besoin."
                )
            # au moins un champ utile à modifier
            if "prix_achat_gramme" not in attrs and "tax" not in attrs:
                raise serializers.ValidationError(
                    "Pour mettre à jour une ligne existante, fournir au moins 'prix_achat_gramme' ou 'tax'."
                )
        else:
            # création ⇒ produit et quantite requis
            if "produit" not in attrs or "quantite" not in attrs:
                raise serializers.ValidationError(
                    "Pour créer une ligne, 'produit' et 'quantite' sont requis."
                )

        return attrs


class AchatUpdateSerializer(serializers.Serializer):
    """
    Body de AchatUpdateView :
    - MAJ fournisseur (optionnel)
    - Ajout / MAJ documentaire de lignes via 'lignes'
      (sans toucher au stock si tu le souhaites).
    """
    fournisseur = FournisseurInlineSerializer(required=False)
    lignes = AchatProduitUpdateItemSerializer(many=True, required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Aucun champ à mettre à jour.")
        return attrs
    
# ---------- Stock réservé → Bijouteries ----------
# class ReserveAllocSerializer(serializers.Serializer):
#     bijouterie_id = serializers.IntegerField(min_value=1)
#     quantite = serializers.IntegerField(min_value=1)

# class ReserveAffectationItemSerializer(serializers.Serializer):
#     produit = serializers.IntegerField(min_value=1)
#     # l'un des deux ou aucun (si tu ne gères pas les lots)
#     lot_id = serializers.IntegerField(required=False, allow_null=True)
#     lot_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
#     affectations = ReserveAllocSerializer(many=True)

#     def validate(self, attrs):
#         allocs = attrs.get("affectations") or []
#         total = sum(a["quantite"] for a in allocs)
#         if total <= 0:
#             raise serializers.ValidationError("La somme des quantités à affecter doit être > 0.")
#         # Normaliser lot_code
#         code = attrs.get("lot_code")
#         if code:
#             attrs["lot_code"] = code.strip().upper()
#         return attrs

# class StockReserveAffectationSerializer(serializers.Serializer):
#     items = ReserveAffectationItemSerializer(many=True)

# ------------- End StockAffectation--------------

# class StockReserveAffectationPayloadSerializer(serializers.Serializer):
#     """
#     Body de StockReserveAffectationView :
#     { "mouvements": [ AchatProduitInputSerializer, ... ] }
#     - Somme des affectations DOIT == quantite pour chaque mouvement (vérifié ici).
#     - prix/tax présents mais ignorés par la vue (documenté côté vue).
#     """
#     mouvements = AchatProduitInputSerializer(many=True)

#     def validate(self, attrs):
#         mvts = attrs.get("mouvements") or []
#         if not mvts:
#             raise serializers.ValidationError({"mouvements": "Au moins un mouvement est requis."})

#         for i, m in enumerate(mvts):
#             if not m.get("affectations"):
#                 raise serializers.ValidationError({
#                     "mouvements": {i: {"affectations": "Obligatoire pour l’affectation du stock réservé."}}
#                 })
#             total_aff = sum(a["quantite"] for a in m["affectations"])
#             if total_aff != m["quantite"]:
#                 raise serializers.ValidationError({
#                     "mouvements": {i: {"affectations": "La somme des affectations doit être STRICTEMENT égale à 'quantite'."}}
#                 })
#         return attrs


# ---------- Annulation d’achat (inventaire) ----------

class AchatCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)
    cancelled_at = serializers.DateTimeField(required=False)
    
# class CancelAllocationItemSerializer(serializers.Serializer):
#     """
#     Élément d’allocation pour l’annulation :
#     bijouterie_id: null/0 => réservé, sinon id bijouterie existante
#     """
#     bijouterie_id = BijouterieIdNullableField(required=False, allow_null=True)
#     quantite = serializers.IntegerField(min_value=1)

#     def validate(self, attrs):
#         # Normalise si champ manquant
#         if "bijouterie_id" not in attrs:
#             attrs["bijouterie_id"] = None
#         return attrs


# class CancelReverseItemSerializer(serializers.Serializer):
#     produit_id = serializers.IntegerField(min_value=1)
#     allocations = CancelAllocationItemSerializer(many=True)

#     def validate_produit_id(self, pid):
#         if not Produit.objects.filter(pk=pid).exists():
#             raise serializers.ValidationError(f"Produit #{pid} introuvable.")
#         return pid

#     def validate(self, attrs):
#         if not attrs.get("allocations"):
#             raise serializers.ValidationError({"allocations": "Au moins une allocation est requise."})
#         return attrs


# class AchatCancelPayloadSerializer(serializers.Serializer):
#     """
#     Body de AchatCancelView :
#     - reason (optionnel)
#     - reverse_allocations (optionnel, pour mode contrôlé)
#     """
#     reason = serializers.CharField(required=False, allow_blank=True)
#     reverse_allocations = CancelReverseItemSerializer(many=True, required=False)

#     def validate(self, attrs):
#         # La contrainte "somme == quantité achetée" se valide dans la vue (elle connaît l'achat).
#         return attrs


# ------------------------------------------------------------
# ---------------Serializers dédiés à la liste---------------/
# ------------------------------------------------------------
class UserSlimSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name"]

class ProduitSlimSerializer(serializers.ModelSerializer):
    class Meta:
        model = Produit
        fields = ["id", "nom", "sku", "poids","matiere", "purete"]

class LotSlimSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lot
        fields = ["id", "achat", "numero_lot", "description", "received_at"]

# class AchatProduitWithLotsSerializer(serializers.ModelSerializer):
#     produit = ProduitSlimSerializer(read_only=True)
#     lots = LotSlimSerializer(many=True, read_only=True)

#     class Meta:
#         model = AchatProduit
#         fields = [
#             "id",
#             "produit",
#             "quantite",
#             "prix_achat_gramme",
#             "sous_total_prix_achat",
#             "prix_achat_total_ttc",
#             "created_at",
#             "updated_at",
#             "lots",  # ← contient lot_code
#         ]

# class AchatListSerializer(serializers.ModelSerializer):
#     fournisseur_nom = serializers.CharField(source="fournisseur.nom", read_only=True)
#     fournisseur_prenom = serializers.CharField(source="fournisseur.prenom", read_only=True)
#     cancelled_by = UserSlimSerializer(read_only=True)
#     produits = LotSlimSerializer(many=True, read_only=True)
#     lot_codes = serializers.SerializerMethodField()  # agrégé au niveau de l’achat

#     class Meta:
#         model = Achat
#         fields = [
#             "id",
#             "created_at",
#             "numero_achat",        # si ton modèle le possède
#             "status",
#             "description",
#             "fournisseur_nom",
#             "fournisseur_prenom",
#             "montant_total_ht",
#             "montant_total_ttc",
#             # annulation
#             "cancelled_by",
#             "cancelled_at",
#             "cancel_reason",
#             # lignes + lots
#             "produits",
#             # aide liste
#             "lot_codes",
#         ]

#     def get_lot_codes(self, obj):
#         codes = set()
#         for ligne in obj.produits.all():
#             for lot in ligne.lots.all():
#                 if lot.lot_code:
#                     codes.add(lot.lot_code)
#         return sorted(codes)
# ---------------END Serializers dédiés à la liste------------


# -----------update and adjustement---------------------------
# ---------- META ONLY ----------
class FournisseurRefSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    nom = serializers.CharField(required=False, allow_blank=True)
    prenom = serializers.CharField(required=False, allow_blank=True)
    telephone = serializers.CharField(required=False, allow_blank=True)

class AchatMetaSerializer(serializers.Serializer):
    description = serializers.CharField(required=False, allow_blank=True)
    frais_transport = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    frais_douane = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    fournisseur = FournisseurRefSerializer(required=False)

class LotMetaSerializer(serializers.Serializer):
    description = serializers.CharField(required=False, allow_blank=True)
    received_at = serializers.DateTimeField(required=False)

# class ArrivageMetaUpdateInSerializer(serializers.Serializer):
#     achat = AchatMetaSerializer(required=False)
#     lot = LotMetaSerializer(required=False)


# ---------- ADJUSTMENTS ----------
# Ajout d'une nouvelle ligne (amendement) => PURCHASE_IN
class AdjustmentAddLineSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["PURCHASE_IN"])
    produit_id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1)
    prix_achat_gramme = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True)

# Retrait partiel d’une ligne existante => CANCEL_PURCHASE (sortie vers EXTERNAL)
class AdjustmentRemoveQtySerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["CANCEL_PURCHASE"])
    produit_line_id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(required=False, allow_blank=True)

class ArrivageAdjustmentsInSerializer(serializers.Serializer):
    actions = serializers.ListField(
        child=serializers.DictField(), allow_empty=False,
        help_text="Liste d'actions PURCHASE_IN ou CANCEL_PURCHASE"
    )

    def validate(self, data):
        # contrôle simple: chaque dict doit contenir une clé 'type'
        for i, act in enumerate(data["actions"]):
            if "type" not in act:
                raise serializers.ValidationError({f"actions[{i}]": "Champ 'type' requis"})
        return data
    
# -----------And update and adjustement-----------------------

# ------------ Dashboard serializers ------------------
# Serializer pour les stats
class AchatDashboardStatsSerializer(serializers.Serializer):
    total_achats = serializers.IntegerField()
    montant_total_ht = serializers.DecimalField(max_digits=12, decimal_places=2)
    montant_total_ttc = serializers.DecimalField(max_digits=12, decimal_places=2)

# Serializer pour la période
class AchatDashboardPeriodeSerializer(serializers.Serializer):
    mois = serializers.IntegerField()
    depuis = serializers.DateField()
    jusqu_a = serializers.DateField()
    
# Serializer global de réponse
class AchatDashboardResponseSerializer(serializers.Serializer):
    periode = AchatDashboardPeriodeSerializer()
    statistiques = AchatDashboardStatsSerializer()
    achats_recents = AchatSerializer(many=True)

# ------------ End Dashboard serializers ------------------


# ----------- Arrivage meta update (achat + lot) ----------
class ArrivageMetaAchatSerializer(serializers.Serializer):
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    frais_transport = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.00"),
    )
    frais_douane = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.00"),
    )
    fournisseur = FournisseurRefSerializer(required=False)


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
# ----------- End Arrivage meta update (achat + lot) ----------


# ----------- Annulation d’achat (inventaire) ----------
class AchatCancelSerializer(serializers.Serializer):
    reason = serializers.CharField()
    cancelled_at = serializers.DateTimeField(required=False)
# ------------ End Annulation d’achat (inventaire) ----------
