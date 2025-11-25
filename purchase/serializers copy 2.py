# from decimal import Decimal, InvalidOperation
# from typing import List

# from django.contrib.auth import get_user_model
# from rest_framework import serializers

# from purchase.models import Achat, Lot, ProduitLine
# from store.models import Bijouterie, Marque, Modele, Produit, Purete

# from .models import Achat, Fournisseur, Lot

# User = get_user_model()


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
    


# # class FournisseurSerializer(serializers.ModelSerializer):
# #     class Meta:
# #         model = Fournisseur
# #         fields = ["id", "nom", "prenom", "telephone", "address", "slug", "date_ajout", "date_modification"]
# #         read_only_fields = ["id", "slug", "date_ajout", "date_modification"]

# # Référence produit
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
    


# # # # ===== IN =====
# class FournisseurInlineSerializer(serializers.Serializer):
#     nom = serializers.CharField()
#     prenom = serializers.CharField(required=False, allow_blank=True)
#     telephone = serializers.CharField(required=False, allow_blank=True)


# class LotLineInSerializer(serializers.Serializer):
#     produit_id = serializers.IntegerField()
#     quantite = serializers.IntegerField(min_value=1)
#     prix_achat_gramme = serializers.DecimalField(
#         max_digits=14,
#         decimal_places=2,
#         required=False,
#     )



# # class AchatListSerializer(serializers.ModelSerializer):
# #     """
# #     Version compacte pour listing éventuel des achats.
# #     (Actuellement non utilisée par AchatListView, qui utilise AchatSerializer.)
# #     """
# #     fournisseur_nom = serializers.CharField(source="fournisseur.nom", read_only=True)
# #     fournisseur_prenom = serializers.CharField(source="fournisseur.prenom", read_only=True)
# #     fournisseur_telephone = serializers.CharField(source="fournisseur.telephone", read_only=True)
# #     nb_lots = serializers.IntegerField(source="lots.count", read_only=True)

# #     class Meta:
# #         model = Achat
# #         fields = [
# #             "id", "numero_achat", "created_at", "status",
# #             "fournisseur_nom", "fournisseur_prenom", "fournisseur_telephone",
# #             "montant_total_ttc", "nb_lots",
# #         ]
# #         read_only_fields = fields

# # ------------------ ArrivageCreateInSerializer ------------------

# # ------------------Inventory mouvement-----------------
# class ProduitSlimForArrivageSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Produit
#         fields = ["id", "nom", "sku", "poids", "purete", "marque", "modele"]
# # -------------------------End Inventory mouvement-----------------

# class ArrivageCreateInSerializer(serializers.Serializer):
#     fournisseur = FournisseurInlineSerializer()
#     description = serializers.CharField(required=False, allow_blank=True)
#     frais_transport = serializers.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         required=False,
#         default=Decimal("0.00"),
#     )
#     frais_douane = serializers.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         required=False,
#         default=Decimal("0.00"),
#     )
#     lots = LotLineInSerializer(many=True)

# # --------------------End creeate arrivage serializer --------------------



# # Détail ProduitLine / Lot / Achat
# class ProduitLineOutSerializer(serializers.ModelSerializer):
#     produit_id = serializers.IntegerField(source="produit.id", read_only=True)
#     produit_nom = serializers.CharField(source="produit.nom", read_only=True)
#     prix_achat_gramme = serializers.DecimalField(
#         max_digits=14,
#         decimal_places=2,
#         read_only=True,
#     )

# #     class Meta:
# #         model = ProduitLine
# #         fields = [
# #             "id",
# #             "produit_id",
# #             "produit_nom",
# #             "quantite",
# #             "prix_achat_gramme",
# #         ]


# # ---------------------------------Achat / Lots (détail) ----------------------

# class FournisseurMiniSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Fournisseur
#         fields = ["id", "nom", "prenom", "telephone"]


# class LotOutSerializer(serializers.ModelSerializer):
#     lignes = ProduitLineOutSerializer(many=True, read_only=True)

#     class Meta:
#         model = Lot
#         fields = ["id", "numero_lot", "description", "received_at", "lignes"]


# class AchatSerializer(serializers.ModelSerializer):
#     """Serializer DÉTAIL achat (avec lots + lignes)."""
#     fournisseur = FournisseurMiniSerializer(read_only=True)
#     lots = LotOutSerializer(many=True, read_only=True)

#     class Meta:
#         model = Achat
#         fields = [
#             "id",
#             "numero_achat",
#             "created_at",
#             "status",
#             "description",
#             "frais_transport",
#             "frais_douane",
#             "montant_total_ht",
#             "montant_total_ttc",
#             "fournisseur",
#             "lots",
#         ]
#         read_only_fields = fields
# # ------------------------------End Achat détail ----------------------------



# # OUT
# class AchatCreateResponseSerializer(serializers.ModelSerializer):
#     lignes = ProduitLineOutSerializer(many=True, read_only=True)
#     # achat_id = serializers.IntegerField(source="achat.id", read_only=True)
#     achat = AchatSerializer(read_only=True)
#     numero_achat = serializers.CharField(source="achat.numero_achat", read_only=True)
#     created_at = serializers.DateTimeField(source="achat.created_at", read_only=True)
#     frais_transport = serializers.DecimalField(
#         source="achat.frais_transport",
#         max_digits=12,
#         decimal_places=2,
#         read_only=True,
#     )
#     frais_douane = serializers.DecimalField(
#         source="achat.frais_douane",
#         max_digits=12,
#         decimal_places=2,
#         read_only=True,
#     )
#     montant_total_ht = serializers.DecimalField(
#         source="achat.montant_total_ht",
#         max_digits=14,
#         decimal_places=2,
#         read_only=True,
#     )
#     montant_total_ttc = serializers.DecimalField(
#         source="achat.montant_total_ttc",
#         max_digits=14,
#         decimal_places=2,
#         read_only=True,
#     )
#     status = serializers.CharField(source="achat.status", read_only=True)

#     class Meta:
#         model = Lot
#         fields = [
#             "id", "numero_lot", "description", "received_at",
#             "achat_id", "numero_achat", "created_at", "status",
#             "frais_transport", "frais_douane",
#             "montant_total_ht", "montant_total_ttc",
#             "lignes",
#         ]

# # -----------------End Create Response Serializer---------------


# # ------------------------- Lot Display ------------------------
# # --- Fournisseur compact pour affichage ---
# # class FournisseurOutSerializer(serializers.ModelSerializer):
# #     class Meta:
# #         model = Fournisseur
# #         fields = ["nom", "prenom", "telephone"]
# #         ref_name = "FournisseurOut_V1"


# # --- Ligne produit dans un lot ---
# # class LotDisplayLineSerializer(serializers.ModelSerializer):
# #     # on expose produit_id + quantite + prix_achat_gramme
# #     produit_id = serializers.IntegerField(source="produit.id", read_only=True)
# #     quantite = serializers.IntegerField(source="quantite_total", read_only=True)
# #     prix_achat_gramme = serializers.DecimalField(
# #         source="prix_gramme_achat",
# #         max_digits=14,
# #         decimal_places=2,
# #         read_only=True,
# #     )

# #     class Meta:
# #         model = ProduitLine
# #         fields = ["produit_id", "quantite", "prix_achat_gramme"]
# #         ref_name = "LotDisplayLine_V1"


# # --- Lot pour affichage ---
# # class LotDisplaySerializer(serializers.ModelSerializer):
# #     fournisseur = FournisseurOutSerializer(
# #         source="achat.fournisseur", read_only=True
# #     )
# #     frais_transport = serializers.DecimalField(
# #         source="achat.frais_transport",
# #         max_digits=12,
# #         decimal_places=2,
# #         read_only=True,
# #     )
# #     frais_douane = serializers.DecimalField(
# #         source="achat.frais_douane",
# #         max_digits=12,
# #         decimal_places=2,
# #         read_only=True,
# #     )
# #     # lignes du lot
# #     lots = LotDisplayLineSerializer(source="lignes", many=True, read_only=True)

# #     class Meta:
# #         model = Lot
# #         fields = [
# #             "fournisseur",
# #             "description",
# #             "frais_transport",
# #             "frais_douane",
# #             "numero_lot",
# #             "lots",
# #         ]
# #         ref_name = "LotDisplay_V1"
# # ---------------------------End lot details---------------------------

# # LISTE DES LOTS
# # class LotListSerializer(serializers.ModelSerializer):
# #     achat_id = serializers.IntegerField(source="achat.id", read_only=True)
# #     numero_achat = serializers.CharField(source="achat.numero_achat", read_only=True)
# #     fournisseur_id = serializers.IntegerField(source="achat.fournisseur.id", read_only=True)
# #     fournisseur_nom = serializers.CharField(source="achat.fournisseur.nom", read_only=True)
# #     fournisseur_prenom = serializers.CharField(source="achat.fournisseur.prenom", read_only=True)
# #     fournisseur_telephone = serializers.CharField(source="achat.fournisseur.telephone", read_only=True)

# #     nb_lignes = serializers.IntegerField(read_only=True)
# #     quantite = serializers.IntegerField(read_only=True)

# #     # Poids calculés à la volée (annotés dans la queryset)
# #     poids_total = serializers.DecimalField(max_digits=18, decimal_places=3, read_only=True)
# #     poids_restant = serializers.DecimalField(max_digits=18, decimal_places=3, read_only=True)

# #     class Meta:
# #         model = Lot
# #         fields = [
# #             "id", "numero_lot", "description", "received_at",
# #             "achat_id", "numero_achat",
# #             "fournisseur_id", "fournisseur_nom", "fournisseur_prenom", "fournisseur_telephone",
# #             "nb_lignes", "quantite",
# #             "poids_total", "poids_restant",
# #         ]
# # -------------------------End List Lot------------------------


# # # -----------------------------ArrivageMetaUpdateView---------------
# # class FournisseurRefSerializer(serializers.Serializer):
# #     """
# #     Référence de fournisseur pour la MAJ meta achat.
# #     Soit id, soit (nom/prenom/telephone) pour créer / upsert.
# #     """
# #     id = serializers.IntegerField(required=False)
# #     nom = serializers.CharField(max_length=100, required=False, allow_blank=True)
# #     prenom = serializers.CharField(max_length=100, required=False, allow_blank=True)
# #     telephone = serializers.CharField(
# #         max_length=15,
# #         required=False,
# #         allow_blank=True,
# #         allow_null=True,
# #     )

# #     def validate(self, attrs):
# #         if not attrs.get("id") and not attrs.get("telephone"):
# #             raise serializers.ValidationError(
# #                 "Spécifier soit 'id', soit au minimum 'telephone' pour le fournisseur."
# #             )
# #         return attrs


# # class ArrivageMetaAchatSerializer(serializers.Serializer):
# #     description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
# #     frais_transport = serializers.DecimalField(
# #         max_digits=12,
# #         decimal_places=2,
# #         required=False,
# #         min_value=Decimal("0.00"),
# #     )
# #     frais_douane = serializers.DecimalField(
# #         max_digits=12,
# #         decimal_places=2,
# #         required=False,
# #         min_value=Decimal("0.00"),
# #     )
# #     fournisseur = FournisseurRefSerializer(required=False)


# # class ArrivageMetaLotSerializer(serializers.Serializer):
# #     description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
# #     received_at = serializers.DateTimeField(required=False)

# # class ArrivageMetaUpdateInSerializer(serializers.Serializer):
# #     """
# #     Payload pour PATCH /arrivage/<lot_id>/meta/
# #     Tous les champs sont optionnels, mais au moins 'achat' ou 'lot' doit être présent.
# #     """
# #     achat = ArrivageMetaAchatSerializer(required=False)
# #     lot = ArrivageMetaLotSerializer(required=False)

# #     def validate(self, attrs):
# #         if "achat" not in attrs and "lot" not in attrs:
# #             raise serializers.ValidationError(
# #                 "Fournir au moins la clé 'achat' ou 'lot'."
# #             )
# #         return attrs
    
# # # -----------------------------End ArrivageMetaUpdateView---------------
