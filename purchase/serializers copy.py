from rest_framework import serializers
from decimal import Decimal
from store.serializers import ProduitSerializer
from .models import Achat, AchatProduit, Fournisseur
from store.models import Produit, Bijouterie
from .models import Achat, AchatProduit, Fournisseur


# class FournisseurSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Fournisseur
#         fields = '__all__' 
#         read_only_fields = ("id", "slug", "date_ajout", "date_modification")


# class AchatProduitSerializer(serializers.ModelSerializer):
#     # produit = ProduitSerializer()
#     prix_achat_total_ttc = serializers.SerializerMethodField()
#     produit_nom = serializers.SerializerMethodField()
    
#     class Meta:
#         model = AchatProduit
#         fields = ['id', 'fournisseur', 'produit', 'produit_nom', 'quantite', 'prix_achat_gramme', 'tax', 'sous_total_prix_achat', 'prix_achat_total_ttc']
#         read_only_fields = ['sous_total_prix_achat'] 
        
#     def get_prix_achat_total_ttc(self, obj):
#         return obj.prix_achat_total_ttc
    
#     def get_produit_nom(self, obj):
#         return obj.produit.nom if obj.produit else None


# class AchatSerializer(serializers.ModelSerializer):
#     fournisseur = FournisseurSerializer()
#     achat_produit = AchatProduitSerializer(many=True)
#     class Meta:
#         model = Achat

#         fields = ['id', 'created_at',  'achat_produit', 'fournisseur', 'montant_total_ht', 'montant_total_ttc']
#         # fields = '__all__'


# # ---------- Helpers champs / sérialiseurs imbriqués ----------
# class ProduitRefField(serializers.Field):
#     """
#     Accepte soit un entier (1), soit {"id": 1}. Retourne toujours un int.
#     """
#     default_error_messages = {
#         "invalid_type": "Format invalide pour 'produit'. Utilise un entier (ex: 1) ou un objet {'id': 1}.",
#         "invalid_id": "ID produit invalide (doit être un entier > 0).",
#     }

#     def to_internal_value(self, data):
#         if isinstance(data, dict):
#             data = data.get("id", None)
#         try:
#             pid = int(data)
#         except (TypeError, ValueError):
#             self.fail("invalid_type")
#         if pid <= 0:
#             self.fail("invalid_id")
#         return pid

#     def to_representation(self, value):
#         try:
#             return int(value)
#         except (TypeError, ValueError):
#             return value


# class FournisseurUpsertSerializer(serializers.Serializer):
#     nom = serializers.CharField(max_length=100)
#     prenom = serializers.CharField(max_length=100)
#     telephone = serializers.CharField(max_length=15)
#     address = serializers.CharField(max_length=100, required=False, allow_blank=True)


# # ---------- Sorties (read) ----------
# class ProduitSlimSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Produit
#         fields = ["id", "nom", "sku", "poids"]


# class AchatProduitSerializer(serializers.ModelSerializer):
#     produit = ProduitSlimSerializer(read_only=True)

#     class Meta:
#         model = AchatProduit
#         fields = [
#             "id", "numero_achat_produit",
#             "produit", "quantite", "prix_achat_gramme", "tax",
#             "sous_total_prix_achat", "prix_achat_total_ttc",
#             "created_at", "updated_at"
#         ]
#         read_only_fields = [
#             "id", "numero_achat_produit",
#             "sous_total_prix_achat", "prix_achat_total_ttc",
#             "created_at", "updated_at"
#         ]


# class FournisseurSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Fournisseur
#         fields = ["id", "nom", "prenom", "telephone", "address", "slug", "date_ajout", "date_modification"]
#         read_only_fields = ["id", "slug", "date_ajout", "date_modification"]


# class AchatSerializer(serializers.ModelSerializer):
#     fournisseur = FournisseurSerializer(read_only=True)
#     produits = AchatProduitSerializer(many=True, read_only=True)   # related_name="produits" requis

#     class Meta:
#         model = Achat
#         fields = [
#             "id", "created_at",
#             "fournisseur",
#             "montant_total_ht", "montant_total_ttc", "montant_total_tax",
#             "produits",
#         ]
#         read_only_fields = [
#             "id", "created_at",
#             "montant_total_ht", "montant_total_ttc", "montant_total_tax",
#             "produits",
#         ]


# class AchatProduitUpdateItemSerializer(serializers.Serializer):
#     id = serializers.IntegerField(required=False)  # id de AchatProduit si on met à jour
#     produit = ProduitRefField(required=False)      # autorisé seulement pour création
#     quantite = serializers.IntegerField(min_value=1, required=False)  # autorisé seulement pour création
#     prix_achat_gramme = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
#     tax = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)

#     def validate(self, attrs):
#         # Si id est présent => update partiel (interdit de modifier quantite/produit ici)
#         if "id" in attrs:
#             if "quantite" in attrs or "produit" in attrs:
#                 raise serializers.ValidationError("Impossible de modifier 'quantite' ou 'produit' d’une ligne existante. Annule et recrée si besoin.")
#         else:
#             # création ⇒ produit et quantite requis
#             if "produit" not in attrs or "quantite" not in attrs:
#                 raise serializers.ValidationError("Pour créer une ligne, 'produit' et 'quantite' sont requis.")
#         return attrs


# class AchatUpdateSerializer(serializers.Serializer):
#     fournisseur = FournisseurUpsertSerializer(required=False)
#     lignes = AchatProduitUpdateItemSerializer(many=True, required=False)

#     def validate(self, attrs):
#         if not attrs:
#             raise serializers.ValidationError("Aucun champ à mettre à jour.")
#         return attrs

# # ---------- Entrées (write) ----------
# class AffectationItemCreateSerializer(serializers.Serializer):
#     bijouterie_id = serializers.IntegerField(min_value=1)
#     quantite = serializers.IntegerField(min_value=1)


# class AchatProduitInputSerializer(serializers.Serializer):
#     produit = ProduitRefField()
#     quantite = serializers.IntegerField(min_value=1)
#     prix_achat_gramme = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.00"))
#     tax = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal("0.00"),
#                                    min_value=Decimal("0.00"))
#     affectations = AffectationItemCreateSerializer(many=True, required=False)

#     def validate(self, attrs):
#         # 1) produit doit exister
#         pid = attrs["produit"]
#         if not Produit.objects.filter(pk=pid).exists():
#             raise serializers.ValidationError({"produit": f"Produit #{pid} introuvable."})

#         # 2) somme des affectations <= quantite
#         q = attrs["quantite"]
#         affectations = attrs.get("affectations") or []
#         if affectations:
#             s = sum(a["quantite"] for a in affectations)
#             if s > q:
#                 raise serializers.ValidationError(
#                     {"affectations": "La somme des quantités affectées dépasse la quantité de la ligne."}
#                 )
#             # 3) bijouteries doivent exister
#             bij_ids = [a["bijouterie_id"] for a in affectations]
#             found = set(Bijouterie.objects.filter(id__in=bij_ids).values_list("id", flat=True))
#             missing = [b for b in bij_ids if b not in found]
#             if missing:
#                 raise serializers.ValidationError(
#                     {"affectations": f"Bijouterie(s) introuvable(s): {missing}"}
#                 )
#         return attrs



# class StockReserveAffectationPayloadSerializer(serializers.Serializer):
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


# class AchatCreateSerializer(serializers.Serializer):
#     fournisseur = FournisseurUpsertSerializer()
#     produits = AchatProduitInputSerializer(many=True)

#     def validate(self, attrs):
#         if not attrs.get("produits"):
#             raise serializers.ValidationError({"produits": "Au moins une ligne produit est requise."})
#         return attrs
    
    
# class AchatUpdateSerializer(serializers.Serializer):
#     """
#     Corps pour AchatUpdateCreateView (mise à jour d’un achat existant) :
#     - MAJ fournisseur (optionnel)
#     - Ajout de nouvelles lignes (optionnel)
#     """
#     fournisseur = FournisseurUpsertSerializer(required=False)
#     produits = AchatProduitInputSerializer(many=True, required=False)

#     def validate(self, attrs):
#         # Rien d'obligatoire ici, mais on pourrait imposer au moins un des deux champs.
#         if not attrs:
#             raise serializers.ValidationError("Aucun champ à mettre à jour.")
#         return attrs


# # ---------- Stock réservé → affectation ----------

# class ReserveAllocationSerializer(serializers.Serializer):
#     """
#     Un mouvement depuis le stock réservé vers une bijouterie.
#     """
#     bijouterie_id = serializers.IntegerField(min_value=1)
#     quantite = serializers.IntegerField(min_value=1)


# class StockReserveAffectationSerializer(serializers.Serializer):
#     """
#     Corps de requête pour StockReserveAffectationView:
#     - Déplace X unités du **réservé** (par produit) vers des bijouteries données.
#     - Exemple:
#       {
#         "produit_id": 12,
#         "movements": [
#           {"bijouterie_id": 2, "quantite": 3},
#           {"bijouterie_id": 5, "quantite": 2}
#         ]
#       }
#     """
#     produit_id = serializers.IntegerField()
#     movements = ReserveAllocationSerializer(many=True)

#     def validate(self, attrs):
#         if not attrs["movements"]:
#             raise serializers.ValidationError({"movements": "Au moins un mouvement est requis."})
#         return attrs


# # ---------- Annulation d’achat ----------

# class CancelBucketSerializer(serializers.Serializer):
#     """
#     Élément d’allocation pour la vue d’annulation.
#     Ici `bijouterie_id` peut être `null`/`0` pour cibler le **réservé**.
#     """
#     bijouterie_id = serializers.IntegerField(required=False, allow_null=True)  # null/0 => réservé
#     quantite = serializers.IntegerField(min_value=1)


# class CancelProductAllocSerializer(serializers.Serializer):
#     produit_id = serializers.IntegerField()
#     allocations = CancelBucketSerializer(many=True)


# class AchatCancelSerializer(serializers.Serializer):
#     """
#     Corps pour AchatCancelView:
#     - reason (optionnel)
#     - reverse_allocations (optionnel) : liste des produits et des retraits par bucket
#     """
#     reason = serializers.CharField(required=False, allow_blank=True)
#     reverse_allocations = CancelProductAllocSerializer(many=True, required=False)

#     def validate(self, attrs):
#         # Ici, on ne peut pas vérifier la somme exacte vs achat sans DB,
#         # on valide juste la structure et des quantités > 0 (fait par CancelBucketSerializer).
#         return attrs


# # ---------- Serializers pour le body du PUT ----------
# from rest_framework import serializers

# class _AllocationSerializer(serializers.Serializer):
#     bijouterie_id = serializers.IntegerField(required=False, allow_null=True)
#     quantite = serializers.IntegerField(min_value=1)

# class _ReverseAllocItemSerializer(serializers.Serializer):
#     produit_id = serializers.IntegerField()
#     allocations = _AllocationSerializer(many=True)

# class AchatUpdateRequestSerializer(serializers.Serializer):
#     reverse_allocations = _ReverseAllocItemSerializer(many=True, required=False)
#     payload = AchatCreateSerializer()   # <-- on réutilise votre sérialiseur de création



# ---------- Champs utilitaires ----------


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


# ---------- Sorties (read) ----------

class ProduitSlimSerializer(serializers.ModelSerializer):
    class Meta:
        model = Produit
        fields = ["id", "nom", "sku", "poids"]


class AchatProduitSerializer(serializers.ModelSerializer):
    produit = ProduitSlimSerializer(read_only=True)

    class Meta:
        model = AchatProduit
        fields = [
            "id",
            "produit", "quantite", "prix_achat_gramme",
            "sous_total_prix_achat", "prix_achat_total_ttc",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id",
            "sous_total_prix_achat", "prix_achat_total_ttc",
            "created_at", "updated_at",
        ]


class FournisseurSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fournisseur
        fields = ["id", "nom", "prenom", "telephone", "address", "slug", "date_ajout", "date_modification"]
        read_only_fields = ["id", "slug", "date_ajout", "date_modification"]

# --------------Create---------------------

class ProduitRefField(serializers.Field):
    """
    Accepte un entier (1), une string "1", ou un objet {"id": 1}.
    Retourne TOUJOURS un int.
    """
    default_error_messages = {
        "invalid_type": "Format invalide pour 'produit'. Utilise un entier (ex: 1) ou un objet {'id': 1}.",
        "invalid_id": "ID produit invalide (doit être un entier > 0).",
    }

    def to_internal_value(self, data):
        if isinstance(data, dict):
            data = data.get("id", None)
        try:
            pid = int(data)
        except (TypeError, ValueError):
            self.fail("invalid_type")
        if pid <= 0:
            self.fail("invalid_id")
        return pid

    def to_representation(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return value


class AffectationItemCreateSerializer(serializers.Serializer):
    bijouterie_id = serializers.IntegerField(min_value=1)
    quantite = serializers.IntegerField(min_value=1)

    def validate_bijouterie_id(self, bid):
        if not Bijouterie.objects.filter(pk=bid).exists():
            raise serializers.ValidationError(f"Bijouterie #{bid} introuvable.")
        return bid


class LotItemSerializer(serializers.Serializer):
    lot_code = serializers.CharField()
    quantite = serializers.IntegerField(min_value=1)
    date_peremption = serializers.DateField(required=False, allow_null=True)
    affectations = AffectationItemCreateSerializer(many=True, required=False)


class AchatProduitInputSerializer(serializers.Serializer):
    """
    Une ligne d'achat : soit 'lots' (avec affectations par lot), soit 'affectations' directes, soit tout réservé.
    """
    produit = ProduitRefField()
    quantite = serializers.IntegerField(min_value=1)
    prix_achat_gramme = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.00"))
    tax = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal("0.00"),
                                    min_value=Decimal("0.00"))
    affectations = AffectationItemCreateSerializer(many=True, required=False)
    lots = LotItemSerializer(many=True, required=False)  # 👈 ICI

    def validate(self, attrs):
        # produit doit exister
        pid = attrs["produit"]
        if not Produit.objects.filter(pk=pid).exists():
            raise serializers.ValidationError({"produit": f"Produit #{pid} introuvable."})

        q_line = attrs["quantite"]
        lots = attrs.get("lots") or []
        affs = attrs.get("affectations") or []

        if lots:
            # somme des lots == quantite ligne
            total_lots = sum(int(l["quantite"]) for l in lots)
            if total_lots != q_line:
                raise serializers.ValidationError({"lots": f"La somme des lots ({total_lots}) doit égaler la quantité de la ligne ({q_line})."})
            # chaque lot : somme affectations <= quantite lot
            for i, l in enumerate(lots):
                s_aff = sum(int(a["quantite"]) for a in (l.get("affectations") or []))
                if s_aff > int(l["quantite"]):
                    raise serializers.ValidationError({"lots": {i: "La somme des affectations dépasse la quantité du lot."}})
        else:
            # sans lots : somme des affectations ≤ quantite (le reste ira au réservé)
            s_aff = sum(int(a["quantite"]) for a in affs)
            if s_aff > q_line:
                raise serializers.ValidationError({"affectations": "La somme des affectations dépasse la quantité de la ligne."})

        return attrs


class AchatSerializer(serializers.ModelSerializer):
    """
    Sérialisation d’un achat pour la **lecture** :
    - fournisseur : objet embarqué (read-only)
    - produits   : lignes d’achat (read-only, via related_name="produits" sur AchatProduit.achat)
    """
    fournisseur = FournisseurSerializer(read_only=True)
    produits = AchatProduitSerializer(many=True, read_only=True)

    class Meta:
        model = Achat
        fields = ["id","created_at","fournisseur","description","montant_total_ht","montant_total_ttc","montant_total_tax","produits",]
        read_only_fields = ["id","created_at","montant_total_ht","montant_total_ttc","montant_total_tax","produits",]


class FournisseurUpsertSerializer(serializers.Serializer):
    nom = serializers.CharField(max_length=100)
    prenom = serializers.CharField(max_length=100)
    telephone = serializers.CharField(max_length=15)
    address = serializers.CharField(max_length=100, required=False, allow_blank=True)


class AchatCreateSerializer(serializers.Serializer):
    """Body de AchatCreateView"""
    fournisseur = FournisseurUpsertSerializer()
    produits = AchatProduitInputSerializer(many=True)

    def validate(self, attrs):
        if not attrs.get("produits"):
            raise serializers.ValidationError({"produits": "Au moins une ligne produit est requise."})
        return attrs
# -----------------END CREATE SERIALZER-------------------------------------

#----------------Create Response Serializer-------------------
class _AllocationDetailOutSerializer(serializers.Serializer):
    bijouterie_id = serializers.IntegerField(min_value=1)
    bijouterie = serializers.CharField()
    quantite = serializers.IntegerField(min_value=1)
    lot_code = serializers.CharField(required=False, allow_blank=True)

class _LineSummaryOutSerializer(serializers.Serializer):
    produit_id = serializers.IntegerField(min_value=1)
    produit = serializers.CharField()
    total_ligne = serializers.IntegerField(min_value=1)
    reserved = serializers.IntegerField(min_value=0)
    details = _AllocationDetailOutSerializer(many=True)

class AchatCreateResponseSerializer(serializers.Serializer):
    """
    Réponse de AchatCreateView :
    {
      "message": "...",
      "achat": { ... AchatSerializer ... },
      "allocations": [
        {
          "produit_id": 12,
          "produit": "Bague or",
          "total_ligne": 10,
          "reserved": 2,
          "details": [
            {"bijouterie_id": 2, "bijouterie": "Plateau", "quantite": 6, "lot_code": "LOT-A1"},
            {"bijouterie_id": 5, "bijouterie": "Almadies", "quantite": 2}
          ]
        }
      ]
    }
    """
    message = serializers.CharField()
    achat = AchatSerializer()
    allocations = _LineSummaryOutSerializer(many=True)
# -----------------End Create Response Serializer---------------

# class AchatSerializer(serializers.ModelSerializer):
#     fournisseur = FournisseurSerializer(read_only=True)
#     produits = AchatProduitSerializer(many=True, read_only=True)  # related_name="produits" requis sur AchatProduit.achat

#     class Meta:
#         model = Achat
#         fields = [
#             "id", "created_at",
#             "fournisseur", "description",
#             "montant_total_ht", "montant_total_ttc", "montant_total_tax",
#             "produits",
#         ]
#         read_only_fields = [
#             "id", "created_at",
#             "montant_total_ht", "montant_total_ttc", "montant_total_tax",
#             "produits",
#         ]

# class _AllocationDetailOutSerializer(serializers.Serializer):
#     bijouterie_id = serializers.IntegerField()
#     bijouterie = serializers.CharField()
#     quantite = serializers.IntegerField()
#     lot_code = serializers.CharField(required=False, allow_blank=True)

# class _LineSummaryOutSerializer(serializers.Serializer):
#     produit_id = serializers.IntegerField()
#     produit = serializers.CharField()
#     total_ligne = serializers.IntegerField()
#     reserved = serializers.IntegerField()
#     details = _AllocationDetailOutSerializer(many=True)

# class AchatCreateResponseSerializer(serializers.Serializer):
#     message = serializers.CharField()
#     achat = AchatSerializer()
#     allocations = _LineSummaryOutSerializer(many=True)

# --------------END Create---------------------




# ---------- Entrées (write) : CREATE + ALLOC RÉSERVÉ ----------


# class AffectationItemCreateSerializer(serializers.Serializer):
#     bijouterie_id = serializers.IntegerField(min_value=1)
#     quantite = serializers.IntegerField(min_value=1)


# class AchatProduitInputSerializer(serializers.Serializer):
#     """
#     Une ligne d'entrée pour AchatCreateView (ET réutilisée pour StockReserveAffectationView).
#     Note: prix/tax seront ignorés par StockReserveAffectationView (documentés dans la vue).
#     """
#     produit = ProduitRefField()
#     quantite = serializers.IntegerField(min_value=1)
#     prix_achat_gramme = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.00"))
#     tax = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal("0.00"),
#                                    min_value=Decimal("0.00"))
#     affectations = AffectationItemCreateSerializer(many=True, required=False)

#     def validate(self, attrs):
#         # 1) produit doit exister
#         pid = attrs["produit"]
#         if not Produit.objects.filter(pk=pid).exists():
#             raise serializers.ValidationError({"produit": f"Produit #{pid} introuvable."})

#         # 2) somme des affectations <= quantite
#         q = attrs["quantite"]
#         affectations = attrs.get("affectations") or []
#         if affectations:
#             s = sum(a["quantite"] for a in affectations)
#             if s > q:
#                 raise serializers.ValidationError(
#                     {"affectations": "La somme des quantités affectées dépasse la quantité de la ligne."}
#                 )
#             # 3) bijouteries doivent exister
#             bij_ids = [a["bijouterie_id"] for a in affectations]
#             found = set(Bijouterie.objects.filter(id__in=bij_ids).values_list("id", flat=True))
#             missing = [b for b in bij_ids if b not in found]
#             if missing:
#                 raise serializers.ValidationError({"affectations": f"Bijouterie(s) introuvable(s): {missing}"})
#         return attrs





# ---------- UPDATE documentaire de l'achat (pas de stock dans cette vue) ----------

class AchatProduitUpdateItemSerializer(serializers.Serializer):
    """
    Item pour mise à jour documentaire :
    - si 'id' présent ⇒ update partiel (prix/taxe), interdit de changer produit/quantite
    - si 'id' absent ⇒ création d'une nouvelle ligne (produit+quantite requis)
    """
    id = serializers.IntegerField(required=False)
    produit = ProduitRefField(required=False)
    quantite = serializers.IntegerField(min_value=1, required=False)
    prix_achat_gramme = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    tax = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)

    def validate(self, attrs):
        if "id" in attrs:
            if "quantite" in attrs or "produit" in attrs:
                raise serializers.ValidationError(
                    "Impossible de modifier 'quantite' ou 'produit' d’une ligne existante. Annule et recrée si besoin."
                )
        else:
            # création ⇒ produit et quantite requis
            if "produit" not in attrs or "quantite" not in attrs:
                raise serializers.ValidationError("Pour créer une ligne, 'produit' et 'quantite' sont requis.")
        return attrs


class AchatUpdateSerializer(serializers.Serializer):
    """
    Body de AchatUpdateView :
    - MAJ fournisseur (optionnel)
    - Ajout / MAJ documentaire de lignes via 'lignes'
    """
    fournisseur = FournisseurUpsertSerializer(required=False)
    lignes = AchatProduitUpdateItemSerializer(many=True, required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Aucun champ à mettre à jour.")
        return attrs


# ---------- Stock réservé → Bijouteries ----------

class ReserveAllocSerializer(serializers.Serializer):
    bijouterie_id = serializers.IntegerField(min_value=1)
    quantite = serializers.IntegerField(min_value=1)

class ReserveAffectationItemSerializer(serializers.Serializer):
    produit = serializers.IntegerField(min_value=1)
    # l'un des deux ou aucun (si tu ne gères pas les lots)
    lot_id = serializers.IntegerField(required=False, allow_null=True)
    lot_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    affectations = ReserveAllocSerializer(many=True)

    def validate(self, attrs):
        allocs = attrs.get("affectations") or []
        total = sum(a["quantite"] for a in allocs)
        if total <= 0:
            raise serializers.ValidationError("La somme des quantités à affecter doit être > 0.")
        # Normaliser lot_code
        code = attrs.get("lot_code")
        if code:
            attrs["lot_code"] = code.strip().upper()
        return attrs

class StockReserveAffectationSerializer(serializers.Serializer):
    items = ReserveAffectationItemSerializer(many=True)

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