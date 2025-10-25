from decimal import Decimal, InvalidOperation
from typing import List

from django.contrib.auth import get_user_model
from rest_framework import serializers

from purchase.models import Achat, Lot, ProduitLine
from store.models import Bijouterie, Marque, Modele, Produit, Purete
from store.serializers import Produit

from .models import Achat, Fournisseur, Lot

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


# class AchatProduitSerializer(serializers.ModelSerializer):
#     produit = ProduitSlimSerializer(read_only=True)

#     class Meta:
#         model = AchatProduit
#         fields = [
#             "id",
#             "produit", "quantite", "prix_achat_gramme",
#             "sous_total_prix_achat", "prix_achat_total_ttc",
#             "created_at", "updated_at",
#         ]
#         read_only_fields = [
#             "id",
#             "sous_total_prix_achat", "prix_achat_total_ttc",
#             "created_at", "updated_at",
#         ]


class FournisseurSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fournisseur
        fields = ["id", "nom", "prenom", "telephone", "address", "slug", "date_ajout", "date_modification"]
        read_only_fields = ["id", "slug", "date_ajout", "date_modification"]

# --------------Create---------------------

# --- Références produit (inchangé) ---
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


# ------------------------------PAYLOAD--------------------------------------
# # --- Référentiels compacts (id + nom) ---
# class MarqueMiniSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Marque        # store.Marque
#         fields = ["id", "nom"]


# class ModeleMiniSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Modele        # store.Modele
#         fields = ["id", "nom"]


# class PureteMiniSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Purete        # store.Purete
#         fields = ["id", "nom"]


# # class MatiereMiniSerializer(serializers.ModelSerializer):
# #     class Meta:
# #         model = Matiere       # store.Matiere
# #         fields = ["id", "nom"]
# MATIERE_CHOICES = (
#     ("OR", "Or"),
#     ("ARGENT", "Argent"),
# )

# # --- Détail produit pour affichage dans un lot ---
# class ProduitDetailForLotSerializer(serializers.ModelSerializer):
#     marque  = MarqueMiniSerializer(read_only=True)
#     modele  = ModeleMiniSerializer(read_only=True)
#     purete  = PureteMiniSerializer(read_only=True)
#     # matiere = MatiereMiniSerializer(read_only=True)
#     matiere = serializers.ChoiceField(choices=MATIERE_CHOICES, required=False)

#     class Meta:
#         model = Produit  # store.Produit
#         fields = [
#             "id", "nom", "sku",
#             "marque", "modele", "purete", "matiere",
#         ]


# # --- Lot avec détail produit enrichi ---
# class LotSerializer(serializers.ModelSerializer):
#     produit = ProduitDetailForLotSerializer(read_only=True)

#     class Meta:
#         model = Lot  # purchase.Lot
#         fields = [
#             "id", "lot_code", "lot_uuid",
#             "produit",              # <- inclut marque/modele/purete/matiere
#             "poids_total", "poids_restant",
#             "prix_achat_gramme",
#             "date_reception",
#             "commentaire",
#         ]
#         read_only_fields = fields


# # --- Achat qui embarque les lots ---
# class AchatSerializer(serializers.ModelSerializer):
#     fournisseur = FournisseurSerializer(read_only=True)
#     lots = LotSerializer(many=True, read_only=True)  # require related_name="lots" sur Lot.achat

#     class Meta:
#         model = Achat
#         fields = [
#             "id", "created_at", "fournisseur", "description",
#             "frais_transport", "frais_douane",
#             "montant_total_ht", "montant_total_ttc", "montant_total_tax",
#             "numero_achat", "status",
#             "lots",
#         ]
#         read_only_fields = fields
# # ----------------------------------END PAYLOAD-------------------------------


# # -------------------------------- Affectation Item ----------------------------------------------
# class AffectationItemCreateSerializer(serializers.Serializer):
#     lot = serializers.PrimaryKeyRelatedField(queryset=Lot.objects.all())
#     bijouterie = serializers.PrimaryKeyRelatedField(queryset=Bijouterie.objects.all())
#     quantite = serializers.IntegerField(required=False, min_value=1, default=0)
#     poids_grammes = serializers.DecimalField(required=False, max_digits=12, decimal_places=3, default=Decimal("0"))
#     note = serializers.CharField(required=False, allow_blank=True, allow_null=True)

#     def validate(self, attrs):
#         q = int(attrs.get("quantite") or 0)
#         w = attrs.get("poids_grammes") or Decimal("0")
#         if q <= 0 and w <= 0:
#             raise serializers.ValidationError("Fournir 'quantite' > 0 ou 'poids_grammes' > 0.")
#         if q > 0 and w > 0:
#             raise serializers.ValidationError("Ne pas mixer 'quantite' et 'poids_grammes'.")
#         return attrs
# # -------------------------------- End Affectation Item ------------------------------------------


# # --- Affectation par poids vers une bijouterie ---
# # Exemple d'énum pour matière (adapte aux tiens)
# class AffectationPoidsSerializer(serializers.Serializer):
#     bijouterie = BijouterieIdNullableField()
#     poids = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))

#     # --- Métadonnées optionnelles pour anti-ambigüité / audit ---
#     # Utilise des IDs si tu as des tables dédiées (Marque, Modele, Purete)
#     purete_id = serializers.IntegerField(required=False, min_value=1)         # ex: "18K", "21K"
#     marque_id = serializers.IntegerField(required=False, min_value=1)
#     modele_id = serializers.IntegerField(required=False, min_value=1)
#     matiere = serializers.ChoiceField(choices=MATIERE_CHOICES, required=False)

#     def validate_bijouterie(self, bid):
#         if not Bijouterie.objects.filter(pk=bid).exists():
#             raise serializers.ValidationError(f"Bijouterie #{bid} introuvable.")
#         return bid

#     def validate(self, attrs):
#         """
#         Vérifie la cohérence des métadonnées (si fournies) avec le Produit
#         passé via self.context['produit'] (ou self.context['produit_id']).
#         """
#         produit = self.context.get("produit")
#         if not produit:
#             # fallback si on n'a que l'id
#             pid = self.context.get("produit_id")
#             if pid:
#                 produit = Produit.objects.filter(pk=pid).select_related("marque", "modele", "purete").first()

#         if not produit:
#             # Si tu attaches ce serializer depuis AchatLigne/Lot, on DOIT lui fournir le produit dans le context
#             # pour valider correctement.
#             return attrs

#         # ---- contrôles de cohérence (seulement si champ fourni) ----
#         # Pureté (ex: champ produit.purete_code ou produit.purete_label)
#         req_purete_id = attrs.get("purete_id")
#         if req_purete_id:
#             prod_purete_id = getattr(produit, "purete", None) or getattr(produit, "purete_code", None) or getattr(produit, "purete_label", None)
#             if prod_purete_id and str(req_purete_id).strip().upper() != str(prod_purete_id).strip().upper():
#                 raise serializers.ValidationError({"purete": f"Incohérence: affectation {req_purete_id} ≠ produit {prod_purete_id}."})

#         # Marque
#         req_marque_id = attrs.get("marque_id")
#         if req_marque_id:
#             prod_marque_id = getattr(getattr(produit, "marque", None), "id", None)
#             if prod_marque_id and int(req_marque_id) != int(prod_marque_id):
#                 raise serializers.ValidationError({"marque_id": f"Incohérence: affectation marque #{req_marque_id} ≠ produit marque #{prod_marque_id}."})

#         # Modèle
#         req_modele_id = attrs.get("modele_id")
#         if req_modele_id:
#             prod_modele_id = getattr(getattr(produit, "modele", None), "id", None)
#             if prod_modele_id and int(req_modele_id) != int(prod_modele_id):
#                 raise serializers.ValidationError({"modele_id": f"Incohérence: affectation modèle #{req_modele_id} ≠ produit modèle #{prod_modele_id}."})

#         # Matière
#         req_matiere = attrs.get("matiere")
#         if req_matiere:
#             prod_matiere = getattr(produit, "matiere", None)
#             if prod_matiere and str(req_matiere) != str(prod_matiere):
#                 raise serializers.ValidationError({"matiere": f"Incohérence: affectation matière {req_matiere} ≠ produit matière {prod_matiere}."})

#         return attrs


# # --- Item de LOT (poids), rattaché au PRODUIT de la ligne / ou explicitement via "produit" si on l’autorise au niveau du lot ---
# class LotItemSerializer(serializers.Serializer):
#     # si tu veux autoriser un produit différent par lot, décommente la ligne ci-dessous et ajuste la validation
#     # produit = ProduitRefField(required=False)

#     lot_code = serializers.CharField(required=False, allow_blank=True, allow_null=True,
#                                     help_text="Laisser vide pour auto-génération (UUID).")
#     quantite = serializers.IntegerField(min_value=1)
#     # ↓↓↓ nouveaux champs (optionnels mais validés si fournis)
#     poids_total = serializers.DecimalField(max_digits=12, decimal_places=3, required=False, min_value=Decimal("0.001"))
#     prix_achat_gramme = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, min_value=Decimal("0.00"))
#     commentaire = serializers.CharField(max_length=255, required=False, allow_blank=True)
#     date_peremption = serializers.DateField(required=False, allow_null=True)
#     affectations = AffectationItemCreateSerializer(many=True, required=False)

#     def validate_lot_code(self, v):
#         if v in (None, ""):
#             return None
#         return v.strip().upper()

#     def validate(self, attrs):
#         # somme des affectations (si présentes) ≤ poids_total
#         affs = attrs.get("affectations") or []
#         if affs:
#             total_aff = sum(Decimal(a["poids"]) for a in affs)
#             if total_aff > attrs["poids_total"]:
#                 raise serializers.ValidationError({
#                     "affectations": f"La somme des affectations ({total_aff} g) dépasse le poids du lot ({attrs['poids_total']} g)."
#                 })
#         return attrs


# # --- Ligne d’entrée (sans AchatProduit) : on peut soit créer des LOTS, soit faire une affectation directe (sans lots) ---
# class AchatLigneInputSerializer(serializers.Serializer):
#     """
#     Une "ligne" d'entrée :
#       - soit 'lots' (chaque lot a son poids_total, son prix_achat_gramme et ses affectations propres)
#       - soit 'affectations' directes (répartition par poids, sans créer de lots → tout le reste ira en RÉSERVE)
#     """
#     produit = ProduitRefField()
#     # prix_achat_gramme ici sert de *valeur par défaut* pour les lots de la ligne s'ils n'en ont pas
#     prix_achat_gramme = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.00"), required=False)
#     # Poids total attendu pour la ligne si on fait une affectation directe (sans lots)
#     poids_total = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"), required=False)
#     # Taxes facultatives (si tu veux stocker des montants de taxe au niveau ligne pour calculer TTC dans Achat)
#     tax = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal("0.00"), min_value=Decimal("0.00"))

#     affectations = AffectationPoidsSerializer(many=True, required=False)
#     lots = LotItemSerializer(many=True, required=False)

#     def validate(self, attrs):
#         # produit doit exister
#         pid = attrs["produit"]
#         if not Produit.objects.filter(pk=pid).exists():
#             raise serializers.ValidationError({"produit": f"Produit #{pid} introuvable."})

#         lots = attrs.get("lots") or []
#         affs = attrs.get("affectations") or []
#         poids_total = attrs.get("poids_total")

#         if lots:
#             # pas d'affectations au niveau ligne si on fournit des lots
#             if affs:
#                 raise serializers.ValidationError({
#                     "affectations": "Ne pas fournir d'affectations au niveau de la ligne quand 'lots' est présent. "
#                                     "Place les affectations dans chaque lot."
#                 })
#             # si certains lots n'ont pas de prix, il faut un prix_achat_gramme défaut au niveau ligne
#             if any("prix_achat_gramme" not in l for l in lots) and ("prix_achat_gramme" not in attrs):
#                 raise serializers.ValidationError({
#                     "prix_achat_gramme": "Prix par gramme requis (soit dans chaque lot, soit au niveau de la ligne)."
#                 })
#             # éviter les doublons de lot_code (ignorer None)
#             codes = [l.get("lot_code") for l in lots if l.get("lot_code")]
#             if len(codes) != len(set(codes)):
#                 raise serializers.ValidationError({"lots": "lot_code en double dans la requête."})
#         else:
#             # mode SANS lots → on exige poids_total
#             if poids_total is None:
#                 raise serializers.ValidationError({"poids_total": "Requis quand 'lots' n'est pas fourni."})
#             # somme des affectations ≤ poids_total (le reste ira en RÉSERVE)
#             s_aff = sum(Decimal(a["poids"]) for a in affs)
#             if s_aff > poids_total:
#                 raise serializers.ValidationError({
#                     "affectations": f"La somme des affectations ({s_aff} g) dépasse le poids_total ({poids_total} g)."
#                 })
#             # il faut un prix à un endroit (ligne)
#             if "prix_achat_gramme" not in attrs:
#                 raise serializers.ValidationError({"prix_achat_gramme": "Requis quand on n'utilise pas de lots."})

#         return attrs


# # --- Fournisseur (upsert) ---
# class FournisseurUpsertSerializer(serializers.Serializer):
#     nom = serializers.CharField(max_length=100)
#     prenom = serializers.CharField(max_length=100)
#     telephone = serializers.CharField(max_length=20)
#     address = serializers.CharField(max_length=200, required=False, allow_blank=True)


# # --- Lecture Achat (read) ---
# class AchatLotReadSerializer(serializers.ModelSerializer):
#     produit = serializers.SerializerMethodField()

#     class Meta:
#         model = Lot
#         fields = [
#             "id", "lot_code", "poids_total", "poids_restant",
#             "prix_achat_gramme", "commentaire", "date_reception", "produit",
#         ]

#     def get_produit(self, obj):
#         p = getattr(obj, "produit", None)
#         if not p:
#             return None
#         return {"id": p.id, "nom": p.nom}


# class AchatSerializer(serializers.ModelSerializer):
#     fournisseur = FournisseurSerializer(read_only=True)
#     lots = AchatLotReadSerializer(many=True, read_only=True)  # related_name='lots' sur Achat.lot_set

#     class Meta:
#         model = Achat
#         fields = [
#             "id", "created_at", "fournisseur", "description",
#             "frais_transport", "frais_douane",
#             "montant_total_ht", "montant_total_ttc", "montant_total_tax",
#             "numero_achat", "status", "lots",
#         ]
#         read_only_fields = [
#             "id", "created_at",
#             "montant_total_ht", "montant_total_ttc", "montant_total_tax",
#             "numero_achat", "status", "lots",
#         ]


# # --- Création Achat (body) ---
# class AchatCreateSerializer(serializers.Serializer):
#     """
#     Body attendu par AchatCreateView (version sans AchatProduit) :

#     Deux modes par "ligne" :
#       1) lots[] : crée N lots (poids_total, prix_achat_gramme par lot), chaque lot peut être en partie affecté à des bijouteries,
#                   le reste du poids va en RÉSERVE.
#       2) affectations[] + poids_total (sans lots) : pas de création de lot détaillé,
#                   on crédite les bijouteries par poids et le reste va en RÉSERVE.
#     """
#     fournisseur = FournisseurUpsertSerializer()
#     produits = AchatLigneInputSerializer(many=True)
#     frais_transport = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal("0.00"), min_value=Decimal("0.00"))
#     frais_douane    = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal("0.00"), min_value=Decimal("0.00"))

#     def validate(self, attrs):
#         if not attrs.get("produits"):
#             raise serializers.ValidationError({"produits": "Au moins une ligne produit est requise."})
#         return attrs

# =========================
#   Sous-serializers
# =========================
# ----------------------------------Create----------------------------------------------
# class FournisseurInlineSerializer(serializers.Serializer):
#     nom = serializers.CharField(allow_blank=True, required=False, default="")
#     prenom = serializers.CharField(allow_blank=True, required=False, default="")
#     telephone = serializers.CharField()  # clé d'upsert dans la View
#     address = serializers.CharField(allow_blank=True, required=False, default="")


# class AffectationSplitSerializer(serializers.Serializer):
#     bijouterie_id = serializers.IntegerField()
#     quantite = serializers.IntegerField(min_value=1)

#     def validate(self, attrs):
#         # on évite les ids négatifs/0 même si IntegerField le gère
#         if attrs["bijouterie_id"] <= 0:
#             raise serializers.ValidationError({"bijouterie_id": "ID bijouterie invalide."})
#         return attrs


# class LotInputSerializer(serializers.Serializer):
#     lot_code = serializers.CharField(allow_null=True, allow_blank=True, required=False, default=None)
#     quantite = serializers.IntegerField(min_value=1)
#     affectations = AffectationSplitSerializer(many=True, required=False)

#     def _check_duplicate_bijouteries(self, splits: List[dict]):
#         ids = [s["bijouterie_id"] for s in splits]
#         dups = sorted(set([x for x in ids if ids.count(x) > 1]))
#         if dups:
#             raise serializers.ValidationError(
#                 {"affectations": f"Bijouterie(s) dupliquée(s) dans ce lot: {dups}. Regroupe les quantités."}
#             )

#     def validate(self, attrs):
#         affs = attrs.get("affectations") or []
#         # Somme des affectations <= quantite du lot
#         if affs:
#             s = sum(a["quantite"] for a in affs)
#             if s > attrs["quantite"]:
#                 raise serializers.ValidationError(
#                     {"affectations": "La somme des affectations du lot dépasse la quantité du lot."}
#                 )
#             self._check_duplicate_bijouteries(affs)
#         return attrs


# class LigneProduitAchatSerializer(serializers.Serializer):
#     """
#     Une ligne d'achat (produit).
#     Deux modes:
#       - avec 'lots' (liste de lots, chacun avec ses affectations)
#       - sans 'lots' (affectations directes au niveau de la ligne)
#       - si aucune affectation fournie -> tout va en réserve
#     """
#     produit = serializers.IntegerField()
#     quantite = serializers.IntegerField(min_value=1)
#     prix_achat_gramme = serializers.DecimalField(max_digits=12, decimal_places=2)
#     lots = LotInputSerializer(many=True, required=False)
#     affectations = AffectationSplitSerializer(many=True, required=False)

#     def _check_duplicate_bijouteries(self, splits: List[dict]):
#         ids = [s["bijouterie_id"] for s in splits]
#         dups = sorted(set([x for x in ids if ids.count(x) > 1]))
#         if dups:
#             raise serializers.ValidationError(
#                 {"affectations": f"Bijouterie(s) dupliquée(s) sur la ligne: {dups}. Regroupe les quantités."}
#             )

#     def validate(self, attrs):
#         lots = attrs.get("lots") or []
#         affs = attrs.get("affectations") or []

#         # Exclusivité lots vs affectations de ligne
#         if lots and affs:
#             raise serializers.ValidationError(
#                 "Ne pas définir 'affectations' au niveau ligne lorsqu'on utilise 'lots'."
#             )

#         q_line = attrs["quantite"]

#         # Avec lots: somme(lots.quantite) == quantite de la ligne
#         if lots:
#             somme_lots = sum(l["quantite"] for l in lots)
#             if somme_lots != q_line:
#                 raise serializers.ValidationError(
#                     {"lots": f"La somme des quantités des lots ({somme_lots}) doit être ÉGALE à la quantité de la ligne ({q_line})."}
#                 )
#         else:
#             # Sans lots: affectations directes (facultatives)
#             if affs:
#                 s_aff = sum(a["quantite"] for a in affs)
#                 if s_aff > q_line:
#                     raise serializers.ValidationError(
#                         {"affectations": f"La somme des affectations ({s_aff}) dépasse la quantité de la ligne ({q_line})."}
#                     )
#                 self._check_duplicate_bijouteries(affs)

#         # Prix au gramme > 0 (plus strict que >= 0)
#         try:
#             p = Decimal(attrs["prix_achat_gramme"])
#         except (InvalidOperation, TypeError):
#             raise serializers.ValidationError({"prix_achat_gramme": "Valeur invalide."})
#         if p <= 0:
#             raise serializers.ValidationError({"prix_achat_gramme": "Doit être > 0."})
#         # normalisation à 2 décimales
#         attrs["prix_achat_gramme"] = p.quantize(Decimal("0.01"))

#         return attrs


# # =========================
# #   Serializer principal
# # =========================

# class AchatCreateSerializer(serializers.Serializer):
#     fournisseur = FournisseurInlineSerializer()
#     produits = LigneProduitAchatSerializer(many=True, allow_empty=False)
#     frais_transport = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal("0.00"))
#     frais_douane = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal("0.00"))

#     # ---------- Validations globales (existence FK + normalisations) ----------
#     def validate(self, attrs):
#         produits = attrs["produits"]

#         # Vérifier l'existence des produits en 1 requête
#         pids = [int(p["produit"]) for p in produits]
#         found_pids = set(Produit.objects.filter(id__in=pids).values_list("id", flat=True))
#         missing = sorted(set(pids) - found_pids)
#         if missing:
#             raise serializers.ValidationError({"produits": [f"Produit introuvable: {missing}"]})

#         # Vérifier l'existence des bijouteries demandées (affectations ligne + lots)
#         bij_ids = []
#         for p in produits:
#             for a in (p.get("affectations") or []):
#                 bij_ids.append(int(a["bijouterie_id"]))
#             for lot in (p.get("lots") or []):
#                 for a in (lot.get("affectations") or []):
#                     bij_ids.append(int(a["bijouterie_id"]))

#         if bij_ids:
#             req = set(bij_ids)
#             found_b = set(Bijouterie.objects.filter(id__in=req).values_list("id", flat=True))
#             miss_b = sorted(req - found_b)
#             if miss_b:
#                 raise serializers.ValidationError({"affectations": [f"Bijouterie introuvable: {miss_b}"]})

#         # Frais normalisés à 2 décimales (et non négatifs)
#         try:
#             ft = (attrs.get("frais_transport") or Decimal("0.00"))
#             fd = (attrs.get("frais_douane") or Decimal("0.00"))
#             if ft < 0 or fd < 0:
#                 raise serializers.ValidationError({"frais": "Les frais ne peuvent pas être négatifs."})
#             attrs["frais_transport"] = ft.quantize(Decimal("0.01"))
#             attrs["frais_douane"] = fd.quantize(Decimal("0.01"))
#         except (InvalidOperation, TypeError):
#             raise serializers.ValidationError({"frais": "Valeurs de frais invalides."})

#         return attrs


# # =========================
# #   (Optionnel) Serializer de réponse
# # =========================

# class AchatSerializer(serializers.ModelSerializer):
#     """Réponse après création (utilisée dans la View). Adapte selon ton modèle Achat réel."""
#     class Meta:
#         model = Achat
#         fields = [
#             "id", "created_at", "description",
#             "frais_transport", "frais_douane",
#             "montant_total_ht", "montant_total_tax", "montant_total_ttc",
#             "numero_achat", "status",
#         ]
#         read_only_fields = fields
        
# # ---------------------------Serializer de sortie-----------------------------

# class StockMiniSerializer(serializers.Serializer):
#     id = serializers.IntegerField()
#     produit_id = serializers.IntegerField()
#     bijouterie_id = serializers.IntegerField(allow_null=True)
#     lot_id = serializers.IntegerField(allow_null=True)
#     quantite = serializers.IntegerField()
#     is_reserved = serializers.BooleanField()

# class AffectationResultSerializer(serializers.Serializer):
#     bijouterie_id = serializers.IntegerField()
#     quantite = serializers.IntegerField()
#     stock = StockMiniSerializer()

# class LotResultSerializer(serializers.Serializer):
#     lot_id = serializers.IntegerField()
#     lot_code = serializers.CharField(allow_null=True)
#     quantite = serializers.IntegerField()
#     reserve = StockMiniSerializer(required=False)
#     affectations = AffectationResultSerializer(many=True)

# class LigneResultSerializer(serializers.Serializer):
#     produit_id = serializers.IntegerField()
#     mode = serializers.ChoiceField(choices=["LOTS", "DIRECT"])
#     quantite_ligne = serializers.IntegerField()
#     lots = LotResultSerializer(many=True, required=False)
#     affectations = AffectationResultSerializer(many=True, required=False)
#     reserve = StockMiniSerializer(required=False)

# class AchatCreateResultSerializer(serializers.Serializer):
#     achat = AchatSerializer()
#     details = LigneResultSerializer(many=True)
# # -----------------END CREATE SERIALZER-------------------------------------

# #----------------Create Response Serializer-------------------
# class _AllocationDetailOutSerializer(serializers.Serializer):
#     bijouterie_id = serializers.IntegerField(min_value=1)
#     bijouterie = serializers.CharField()
#     quantite = serializers.IntegerField(min_value=1)
#     lot_code = serializers.CharField(required=False, allow_blank=True)

# class _LineSummaryOutSerializer(serializers.Serializer):
#     produit_id = serializers.IntegerField(min_value=1)
#     produit = serializers.CharField()
#     total_ligne = serializers.IntegerField(min_value=1)
#     reserved = serializers.IntegerField(min_value=0)
#     details = _AllocationDetailOutSerializer(many=True)

# class AchatCreateResponseSerializer(serializers.Serializer):
#     """
#     Réponse de AchatCreateView :
#     {
#       "message": "...",
#       "achat": { ... AchatSerializer ... },
#       "allocations": [
#         {
#           "produit_id": 12,
#           "produit": "Bague or",
#           "total_ligne": 10,
#           "reserved": 2,
#           "details": [
#             {"bijouterie_id": 2, "bijouterie": "Plateau", "quantite": 6, "lot_code": "LOT-A1"},
#             {"bijouterie_id": 5, "bijouterie": "Almadies", "quantite": 2}
#           ]
#         }
#     ]
#     }
#     """
#     message = serializers.CharField()
#     achat = AchatSerializer()
#     allocations = _LineSummaryOutSerializer(many=True)

# ---------------------------------LIST--------------------------------------------
class LotListSerializer(serializers.ModelSerializer):
    achat_id = serializers.IntegerField(source="achat.id", read_only=True)
    numero_achat = serializers.CharField(source="achat.numero_achat", read_only=True)
    fournisseur = serializers.CharField(source="achat.fournisseur.nom", read_only=True)

    nb_lignes = serializers.IntegerField(read_only=True)
    quantite_total = serializers.IntegerField(read_only=True)
    quantite_restante = serializers.IntegerField(read_only=True)

    # Poids calculés à la volée (annotés ou fallback calcul serializer)
    poids_total = serializers.DecimalField(max_digits=18, decimal_places=3, read_only=True)
    poids_restant = serializers.DecimalField(max_digits=18, decimal_places=3, read_only=True)

    class Meta:
        model = Lot
        fields = [
            "id", "numero_lot", "description", "received_at",
            "achat_id", "numero_achat", "fournisseur",
            "nb_lignes", "quantite_total", "quantite_restante",
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
    quantite = serializers.IntegerField(source="quantite_total", read_only=True)
    prix_achat_gramme = serializers.DecimalField(source="prix_gramme_achat", max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = ProduitLine
        fields = ["produit_id", "quantite", "prix_achat_gramme"]
        ref_name = "LotDisplayLine_V1"

class LotDisplaySerializer(serializers.ModelSerializer):
    fournisseur = FournisseurOutSerializer(source="achat.fournisseur", read_only=True)
    frais_transport = serializers.DecimalField(source="achat.frais_transport", max_digits=12, decimal_places=2, read_only=True)
    frais_douane    = serializers.DecimalField(source="achat.frais_douane",    max_digits=12, decimal_places=2, read_only=True)
    lots = LotDisplayLineSerializer(source="lignes", many=True, read_only=True)

    class Meta:
        model = Lot
        fields = ["fournisseur", "description", "frais_transport", "frais_douane", "numero_lot", "lots"]
        ref_name = "LotDisplay_V1"
# ------------------------------------END LIST---------------------------------------

# ----------------------------------------Lot display---------------------------------------------
class FournisseurOutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fournisseur
        fields = ["nom", "prenom", "telephone"]
        ref_name = "FournisseurOut_V1"

class LotDisplayLineSerializer(serializers.ModelSerializer):
    # renommer les champs pour matcher ton shape
    produit_id = serializers.IntegerField(source="produit.id", read_only=True)
    quantite = serializers.IntegerField(source="quantite_total", read_only=True)
    prix_achat_gramme = serializers.DecimalField(source="prix_gramme_achat", max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = ProduitLine
        fields = ["produit_id", "quantite", "prix_achat_gramme"]
        ref_name = "LotDisplayLine_V1"

class LotDisplaySerializer(serializers.ModelSerializer):
    fournisseur = FournisseurOutSerializer(source="achat.fournisseur", read_only=True)
    frais_transport = serializers.DecimalField(source="achat.frais_transport", max_digits=12, decimal_places=2, read_only=True)
    frais_douane    = serializers.DecimalField(source="achat.frais_douane",    max_digits=12, decimal_places=2, read_only=True)
    lots = LotDisplayLineSerializer(source="lignes", many=True, read_only=True)

    class Meta:
        model = Lot
        fields = ["fournisseur", "description", "frais_transport", "frais_douane", "numero_lot", "lots"]
        ref_name = "LotDisplay_V1"
# -----------------------------------------End lot display----------------------------------------------

# Réutilise tes serializers existants :
# - ProduitLineOutSerializer (déjà défini dans ton message)
# - LotOutSerializer ci-dessous (pour réutiliser ProduitLineOutSerializer)
# --- Lignes produit (dans un lot) ---
class ProduitLineOutSerializer(serializers.ModelSerializer):
    produit_id = serializers.IntegerField(source="produit.id", read_only=True)
    produit_nom = serializers.CharField(source="produit.nom", read_only=True)

    class Meta:
        model = ProduitLine
        fields = [
            "id", "produit_id", "produit_nom",
            "quantite_total", "quantite_restante",
            "prix_gramme_achat",
        ]

class FournisseurSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fournisseur
        fields = ["id", "nom", "prenom", "telephone"]


class LotOutSerializer(serializers.ModelSerializer):
    lignes = ProduitLineOutSerializer(many=True, read_only=True)

    class Meta:
        model = Lot
        fields = ["id", "numero_lot", "description", "received_at", "lignes"]


class AchatSerializer(serializers.ModelSerializer):
    fournisseur = FournisseurSerializer(read_only=True)
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
    fournisseur = serializers.CharField(source="fournisseur.nom", read_only=True)
    nb_lots = serializers.IntegerField(source="lots.count", read_only=True)

    class Meta:
        model = Achat
        fields = [
            "id", "numero_achat", "created_at", "status",
            "fournisseur", "montant_total_ttc", "nb_lots",
        ]
        read_only_fields = fields
        
# -----------------------Arrivage ------------------------------------------

# ===== IN =====
class FournisseurInlineSerializer(serializers.Serializer):
    nom = serializers.CharField()
    prenom = serializers.CharField(required=False, allow_blank=True)
    telephone = serializers.CharField(required=False, allow_blank=True)

class LotLineInSerializer(serializers.Serializer):
    produit_id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1)
    prix_achat_gramme = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)

class ArrivageCreateInSerializer(serializers.Serializer):
    fournisseur = FournisseurInlineSerializer()
    description = serializers.CharField(required=False, allow_blank=True)
    frais_transport = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal("0.00"))
    frais_douane    = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal("0.00"))
    # numero_lot      = serializers.CharField()
    lots            = LotLineInSerializer(many=True)

# ===== OUT =====
class AchatCreateResponseSerializer(serializers.ModelSerializer):
    lignes = ProduitLineOutSerializer(many=True, read_only=True)
    achat_id         = serializers.IntegerField(source="achat.id", read_only=True)
    numero_achat     = serializers.CharField(source="achat.numero_achat", read_only=True)
    created_at       = serializers.DateTimeField(source="achat.created_at", read_only=True)
    frais_transport  = serializers.DecimalField(source="achat.frais_transport", max_digits=12, decimal_places=2, read_only=True)
    frais_douane     = serializers.DecimalField(source="achat.frais_douane", max_digits=12, decimal_places=2, read_only=True)
    montant_total_ht = serializers.DecimalField(source="achat.montant_total_ht", max_digits=14, decimal_places=2, read_only=True)
    montant_total_ttc= serializers.DecimalField(source="achat.montant_total_ttc", max_digits=14, decimal_places=2, read_only=True)
    status           = serializers.CharField(source="achat.status", read_only=True)

    class Meta:
        model  = Lot
        fields = [
            "id", "numero_lot", "description", "received_at",
            "achat_id", "numero_achat", "created_at", "status",
            "frais_transport", "frais_douane",
            "montant_total_ht", "montant_total_ttc",
            "lignes",
        ]

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
    fournisseur = FournisseurInlineSerializer(required=False)
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
        model = Lot
        fields = ["id", "lot_code", "quantite_total", "quantite_restante", "date_reception", "date_peremption"]

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

class AchatListSerializer(serializers.ModelSerializer):
    fournisseur_nom = serializers.CharField(source="fournisseur.nom", read_only=True)
    fournisseur_prenom = serializers.CharField(source="fournisseur.prenom", read_only=True)
    cancelled_by = UserSlimSerializer(read_only=True)
    produits = LotSlimSerializer(many=True, read_only=True)
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