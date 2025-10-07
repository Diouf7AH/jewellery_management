from rest_framework import serializers
from decimal import Decimal
from django.contrib.auth import get_user_model
from store.serializers import Produit
from .models import Achat, AchatProduit, Fournisseur
from store.models import Produit, Bijouterie
from .models import Achat, AchatProduit, Fournisseur, AchatProduitLot


User = get_user_model()

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
    lot_code = serializers.CharField(required=False, allow_blank=True, allow_null=True,
                                    help_text="Laisser vide pour auto-génération (UUID).")
    quantite = serializers.IntegerField(min_value=1)
    date_peremption = serializers.DateField(required=False, allow_null=True)
    affectations = AffectationItemCreateSerializer(many=True, required=False)

    def validate_lot_code(self, v):
        # None si vide, sinon UPPER + trim
        if v in (None, ""):
            return None
        return v.strip().upper()


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
            # 1) somme(lots.quantite) == quantite ligne
            total_lots = sum(int(l["quantite"]) for l in lots)
            if total_lots != q_line:
                raise serializers.ValidationError({
                    "lots": f"La somme des lots ({total_lots}) doit égaler la quantité de la ligne ({q_line})."
                })

            # 2) chaque lot: somme(affectations) <= quantite du lot
            for i, l in enumerate(lots):
                s_aff = sum(int(a["quantite"]) for a in (l.get("affectations") or []))
                if s_aff > int(l["quantite"]):
                    label = l.get("lot_code") or "(auto)"
                    raise serializers.ValidationError({
                        "lots": {i: f"La somme des affectations ({s_aff}) dépasse la quantité du lot {label} ({l['quantite']})."}
                    })

            # 3) éviter les doublons de lot_code dans la même requête (ignorer None)
            codes = [l.get("lot_code") for l in lots if l.get("lot_code")]
            if len(codes) != len(set(codes)):
                raise serializers.ValidationError({"lots": "lot_code en double dans la requête."})

            # 4) pas d'affectations AU NIVEAU LIGNE quand on utilise des lots
            if affs:
                raise serializers.ValidationError({
                    "affectations": (
                        "Ne pas fournir 'affectations' au niveau de la ligne quand 'lots' est présent. "
                        "Place les affectations dans chaque lot."
                    )
                })
        else:
            # Sans lots → somme(affectations) ≤ quantite (le reste ira au réservé)
            s_aff = sum(int(a["quantite"]) for a in affs)
            if s_aff > q_line:
                raise serializers.ValidationError({
                    "affectations": "La somme des affectations dépasse la quantité de la ligne."
                })
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
        fields = ["id", "nom", "sku", "poids"]

class LotSlimSerializer(serializers.ModelSerializer):
    class Meta:
        model = AchatProduitLot
        fields = ["id", "lot_code", "quantite_total", "quantite_restante", "date_reception", "date_peremption"]

class AchatProduitWithLotsSerializer(serializers.ModelSerializer):
    produit = ProduitSlimSerializer(read_only=True)
    lots = LotSlimSerializer(many=True, read_only=True)

    class Meta:
        model = AchatProduit
        fields = [
            "id",
            "produit",
            "quantite",
            "prix_achat_gramme",
            "sous_total_prix_achat",
            "prix_achat_total_ttc",
            "created_at",
            "updated_at",
            "lots",  # ← contient lot_code
        ]

class AchatListSerializer(serializers.ModelSerializer):
    fournisseur_nom = serializers.CharField(source="fournisseur.nom", read_only=True)
    fournisseur_prenom = serializers.CharField(source="fournisseur.prenom", read_only=True)
    cancelled_by = UserSlimSerializer(read_only=True)
    produits = AchatProduitWithLotsSerializer(many=True, read_only=True)
    lot_codes = serializers.SerializerMethodField()  # agrégé au niveau de l’achat

    class Meta:
        model = Achat
        fields = [
            "id",
            "created_at",
            "numero_achat",        # si ton modèle le possède
            "status",
            "description",
            "fournisseur_nom",
            "fournisseur_prenom",
            "montant_total_ht",
            "montant_total_tax",
            "montant_total_ttc",
            # annulation
            "cancelled_by",
            "cancelled_at",
            "cancel_reason",
            # lignes + lots
            "produits",
            # aide liste
            "lot_codes",
        ]

    def get_lot_codes(self, obj):
        codes = set()
        for ligne in obj.produits.all():
            for lot in ligne.lots.all():
                if lot.lot_code:
                    codes.add(lot.lot_code)
        return sorted(codes)
# ---------------END Serializers dédiés à la liste------------