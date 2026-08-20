from decimal import ROUND_HALF_UP, Decimal

from rest_framework import serializers

from store.models import Produit

from .models import Achat, Fournisseur, Lot, ProduitLine

# =============================
# IN : payload ArrivageCreate
# =============================


# Fournisseur--------------------------------------------------
class FournisseurMiniSerializer(serializers.ModelSerializer):
    """
    Informations minimales du fournisseur.

    Le téléphone est conservé dans la réponse puisqu'il constitue
    la clé métier du fournisseur.
    """

    class Meta:
        model = Fournisseur
        fields = [
            "id",
            "nom",
            "prenom",
            "telephone",
        ]
        read_only_fields = fields


class FournisseurOutSerializer(serializers.ModelSerializer):
    """
    Représentation complète en lecture seule d'un fournisseur.

    Le téléphone est exposé car il constitue la clé métier
    du fournisseur dans l'ERP Rio Gold.
    """

    class Meta:
        model = Fournisseur
        fields = [
            "id",
            "nom",
            "prenom",
            "telephone",
            "address",
            "slug",
        ]
        read_only_fields = fields
# end fournisseur----------------------------------------------------


# Produit ------------------------------------------------------------

class ProduitMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Produit
        fields = [
            "id",
            "nom",
            "poids",
        ]
        read_only_fields = fields


DECIMAL_2_PLACES = Decimal("0.01")

class ProduitLineOutSerializer(serializers.ModelSerializer):
    """
    Ligne d'un lot avec les informations minimales du produit
    et les montants calculés.
    """

    produit = ProduitMiniSerializer(
        read_only=True,
    )

    poids_total = serializers.DecimalField(
        max_digits=16,
        decimal_places=2,
        read_only=True,
    )

    montant_ht = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = ProduitLine
        fields = [
            "id",
            "produit",
            "quantite",
            "prix_achat_gramme",
            "poids_total",
            "montant_ht",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)

        poids_unitaire = getattr(
            instance.produit,
            "poids",
            None,
        )

        quantite = instance.quantite or 0
        prix_achat_gramme = instance.prix_achat_gramme

        # =====================================================
        # Poids total
        # quantité × poids unitaire
        # =====================================================

        if poids_unitaire is None:
            data["poids_total"] = None
        else:
            poids_total = (
                Decimal(str(quantite))
                * Decimal(str(poids_unitaire))
            ).quantize(
                DECIMAL_2_PLACES,
                rounding=ROUND_HALF_UP,
            )

            data["poids_total"] = format(
                poids_total,
                ".2f",
            )

        # =====================================================
        # Montant HT
        # quantité × poids unitaire × prix d'achat au gramme
        # =====================================================

        if (
            poids_unitaire is None
            or prix_achat_gramme is None
        ):
            data["montant_ht"] = None
        else:
            montant_ht = (
                Decimal(str(quantite))
                * Decimal(str(poids_unitaire))
                * Decimal(str(prix_achat_gramme))
            ).quantize(
                DECIMAL_2_PLACES,
                rounding=ROUND_HALF_UP,
            )

            data["montant_ht"] = format(
                montant_ht,
                ".2f",
            )

        return data



class ProduitLineMiniSerializer(serializers.ModelSerializer):
    """
    Représentation d'une ligne d'achat avec son lot, son produit
    et le stock actuellement présent en bijouterie.

    Les champs quantite_totale et en_stock proviennent des annotations
    réalisées dans le queryset de InventoryPhotoView.
    """

    # ============================================================
    # Achat
    # ============================================================

    achat_id = serializers.IntegerField(
        source="lot.achat.id",
        read_only=True,
    )

    numero_achat = serializers.CharField(
        source="lot.achat.numero_achat",
        read_only=True,
    )

    reference_commande = serializers.CharField(
        source="lot.achat.reference_commande",
        read_only=True,
        allow_null=True,
        default=None,
    )

    # ============================================================
    # Lot
    # ============================================================

    lot_id = serializers.IntegerField(
        source="lot.id",
        read_only=True,
    )

    numero_lot = serializers.CharField(
        source="lot.numero_lot",
        read_only=True,
    )

    received_at = serializers.DateTimeField(
        source="lot.received_at",
        read_only=True,
    )

    # ============================================================
    # Bijouterie
    # ============================================================

    bijouterie_id = serializers.IntegerField(
        source="lot.achat.bijouterie.id",
        read_only=True,
    )

    bijouterie_nom = serializers.CharField(
        source="lot.achat.bijouterie.nom",
        read_only=True,
    )

    # ============================================================
    # Fournisseur
    # ============================================================

    fournisseur_id = serializers.IntegerField(
        source="lot.achat.fournisseur.id",
        read_only=True,
    )

    fournisseur_nom = serializers.CharField(
        source="lot.achat.fournisseur.nom",
        read_only=True,
    )

    # ============================================================
    # Produit
    # ============================================================

    produit_id = serializers.IntegerField(
        source="produit.id",
        read_only=True,
    )

    produit_uuid = serializers.UUIDField(
        source="produit.uuid",
        read_only=True,
    )

    produit_nom = serializers.CharField(
        source="produit.nom",
        read_only=True,
    )

    produit_sku = serializers.CharField(
        source="produit.sku",
        read_only=True,
        allow_null=True,
        default=None,
    )

    purete = serializers.CharField(
        source="produit.purete",
        read_only=True,
        allow_null=True,
        default=None,
    )

    poids_unitaire = serializers.DecimalField(
        source="produit.poids",
        max_digits=12,
        decimal_places=3,
        read_only=True,
        allow_null=True,
    )

    # ============================================================
    # Ligne achat
    # ============================================================

    quantite_recue = serializers.IntegerField(
        source="quantite",
        read_only=True,
    )

    poids_total = serializers.DecimalField(
        source="poids_total_calc",
        max_digits=14,
        decimal_places=3,
        read_only=True,
        allow_null=True,
    )

    prix_achat_gramme = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
        allow_null=True,
    )

    # ============================================================
    # Stock annoté dans InventoryPhotoView
    # ============================================================

    quantite_totale = serializers.IntegerField(
        source="quantite_totale_total",
        read_only=True,
    )

    en_stock = serializers.IntegerField(
        source="en_stock_total",
        read_only=True,
    )

    class Meta:
        model = ProduitLine
        fields = [
            "id",

            # Achat
            "achat_id",
            "numero_achat",
            "reference_commande",

            # Lot
            "lot_id",
            "numero_lot",
            "received_at",

            # Bijouterie
            "bijouterie_id",
            "bijouterie_nom",

            # Fournisseur
            "fournisseur_id",
            "fournisseur_nom",

            # Produit
            "produit_id",
            "produit_uuid",
            "produit_nom",
            "produit_sku",
            "purete",
            "poids_unitaire",

            # Ligne achat
            "quantite_recue",
            "poids_total",
            "prix_achat_gramme",

            # Stock magasin
            "quantite_totale",
            "en_stock",
        ]

        read_only_fields = fields

# end produit------------------------------------------------

## Achat


class AchatBaseOutSerializer(serializers.ModelSerializer):
    """
    Base commune des serializers de sortie d'un achat.
    """

    fournisseur = FournisseurOutSerializer(
        read_only=True,
    )

    bijouterie_id = serializers.IntegerField(
        source="bijouterie.id",
        read_only=True,
        allow_null=True,
    )

    bijouterie_nom = serializers.CharField(
        source="bijouterie.nom",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Achat
        fields = [
            "id",
            "numero_achat",
            "reference_commande",
            "status",
            "description",
            "note",
            "created_at",
            "frais_transport",
            "frais_douane",
            "montant_total_ht",
            "montant_total_ttc",
            "bijouterie_id",
            "bijouterie_nom",
            "fournisseur",
        ]
        read_only_fields = fields



class AchatOutSerializer(AchatBaseOutSerializer):
    """
    Représentation complète d'un achat sans ses lots.

    """

    class Meta(AchatBaseOutSerializer.Meta):
        fields = AchatBaseOutSerializer.Meta.fields
        read_only_fields = fields



### end achat


# Lot


class LotOutSerializer(serializers.ModelSerializer):
    """
    Lot avec ses lignes produit.
    """

    lignes = ProduitLineOutSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = Lot
        fields = [
            "id",
            "numero_lot",
            "description",
            "received_at",
            "lignes",
        ]
        read_only_fields = fields




class AchatDetailSerializer(AchatBaseOutSerializer):
    """
    Vue détaillée d'un achat avec sa bijouterie,
    son fournisseur, ses lots et leurs lignes produit.
    """

    lots = LotOutSerializer(
        many=True,
        read_only=True,
    )

    class Meta(AchatBaseOutSerializer.Meta):
        fields = [
            *AchatBaseOutSerializer.Meta.fields,
            "lots",
        ]
        read_only_fields = fields
        


class LotListSerializer(serializers.ModelSerializer):
    """
    Liste des lots avec achat, fournisseur et lignes produit.

    Les champs nb_lignes et quantite_totale doivent être fournis
    par annotate() dans le queryset.
    """

    achat = AchatOutSerializer(read_only=True)

    fournisseur = FournisseurMiniSerializer(
        source="achat.fournisseur",
        read_only=True,
    )

    lignes = ProduitLineOutSerializer(
        many=True,
        read_only=True,
    )

    bijouterie_id = serializers.IntegerField(
        source="achat.bijouterie.id",
        read_only=True,
    )

    bijouterie_nom = serializers.CharField(
        source="achat.bijouterie.nom",
        read_only=True,
    )

    nb_lignes = serializers.IntegerField(read_only=True)

    quantite_totale = serializers.IntegerField(read_only=True)

    class Meta:
        model = Lot
        fields = [
            "id",
            "numero_lot",
            "description",
            "received_at",
            "bijouterie_id",
            "bijouterie_nom",
            "fournisseur",
            "nb_lignes",
            "quantite_totale",
            "achat",
            "lignes",
        ]
        read_only_fields = fields

# end lot

# respose

class ArrivageCreateResponseSerializer(serializers.Serializer):
    """
    Réponse globale d'un arrivage.

    Structure :
        {
            "achat": {...},
            "lots": [...]
        }
    """

    achat = AchatOutSerializer(
        read_only=True,
    )

    lots = LotOutSerializer(
        many=True,
        read_only=True,
    )

# end response


class FournisseurPatchSerializer(serializers.Serializer):
    id = serializers.IntegerField(
        required=False,
        min_value=1,
    )

    nom = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=False,
        trim_whitespace=True,
    )

    prenom = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
        allow_null=True,
        trim_whitespace=True,
    )

    telephone = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=False,
        allow_null=False,
        trim_whitespace=True,
    )

    address = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        trim_whitespace=True,
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                "Aucune donnée fournisseur fournie."
            )

        fournisseur_id = attrs.get("id")

        if fournisseur_id:
            return attrs

        telephone = (
            attrs.get("telephone")
            or ""
        ).strip()

        if not telephone:
            raise serializers.ValidationError({
                "telephone": (
                    "Le téléphone est obligatoire pour identifier "
                    "le fournisseur."
                )
            })

        attrs["telephone"] = telephone

        return attrs
    

class FournisseurSerializer(serializers.ModelSerializer):

    class Meta:
        model = Fournisseur
        fields = [
            "id",
            "nom",
            "prenom",
            "telephone",
            "address",
            "slug",
            "date_ajout",
            "date_modification",
        ]
        read_only_fields = [
            "id",
            "slug",
            "date_ajout",
            "date_modification",
        ]

    def validate_nom(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Le nom du fournisseur est obligatoire."
            )

        return value

    def validate_telephone(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Le téléphone du fournisseur est obligatoire."
            )

        return value
    


class FournisseurInlineSerializer(serializers.Serializer):
    """
    Fournisseur transmis lors de la création d'un arrivage.

    Le téléphone est la clé métier utilisée pour rechercher
    ou créer le fournisseur.
    """

    nom = serializers.CharField(
        max_length=150,
        required=True,
        allow_blank=False,
        trim_whitespace=True,
    )

    prenom = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
        allow_null=True,
        trim_whitespace=True,
        default="",
    )

    telephone = serializers.CharField(
        max_length=30,
        required=True,
        allow_blank=False,
        allow_null=False,
        trim_whitespace=True,
    )

    address = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        trim_whitespace=True,
        default="",
    )

    def validate_nom(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Le nom du fournisseur est obligatoire."
            )

        return value

    def validate_telephone(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Le téléphone du fournisseur est obligatoire."
            )

        return value
    


class LotLineInSerializer(serializers.Serializer):
    """
    Ligne produit reçue dans un lot.
    """

    produit_id = serializers.IntegerField(
        min_value=1,
    )

    quantite = serializers.IntegerField(
        min_value=1,
    )

    prix_achat_gramme = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=True,
        min_value=Decimal("0.00"),
    )


class LotInSerializer(serializers.Serializer):
    """
    Lot fournisseur contenant une ou plusieurs lignes produit.
    """

    received_at = serializers.DateTimeField(
        required=False,
    )

    description = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        trim_whitespace=True,
        default="",
    )

    lignes = LotLineInSerializer(
        many=True,
        allow_empty=False,
    )

    def validate_description(self, value):
        return (
            value.strip()
            if value
            else ""
        )

    def validate_lignes(self, lignes):
        produit_ids = [
            ligne["produit_id"]
            for ligne in lignes
        ]

        if len(produit_ids) != len(set(produit_ids)):
            raise serializers.ValidationError(
                "Un produit ne peut apparaître qu'une seule fois "
                "dans un même lot."
            )

        return lignes


class ArrivageCreateInSerializer(serializers.Serializer):
    """
    Payload complet pour :

        POST /api/achat/arrivage/

    Structure :

        1 Achat
            ↓
        N Lots
            ↓
        N ProduitLine

    Mouvement généré :

        PURCHASE_IN
        EXTERNAL → BIJOUTERIE
    """

    bijouterie_id = serializers.IntegerField(
        min_value=1,
    )

    fournisseur = FournisseurInlineSerializer()

    reference_commande = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        trim_whitespace=True,
        default="",
    )

    description = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        trim_whitespace=True,
        default="",
    )

    frais_transport = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.00"),
        default=Decimal("0.00"),
    )

    frais_douane = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.00"),
        default=Decimal("0.00"),
    )

    lots = LotInSerializer(
        many=True,
        allow_empty=False,
    )

    def validate_reference_commande(self, value):
        return (
            value.strip()
            if value
            else ""
        )

    def validate_description(self, value):
        return (
            value.strip()
            if value
            else ""
        )


class ArrivageCreateInSerializer(serializers.Serializer):
    bijouterie_id = serializers.IntegerField(
        min_value=1,
        required=False,
    )

    fournisseur = FournisseurInlineSerializer()

    reference_commande = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        trim_whitespace=True,
        default="",
    )

    description = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        trim_whitespace=True,
        default="",
    )

    frais_transport = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.00"),
        default=Decimal("0.00"),
    )

    frais_douane = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.00"),
        default=Decimal("0.00"),
    )

    lots = LotInSerializer(
        many=True,
        allow_empty=False,
    )
    


# ============================================================
# PATCH Arrivage (métadonnées uniquement)
# ============================================================

class ArrivageMetaAchatOutSerializer(serializers.Serializer):
    """
    Champs modifiables de l'achat.
    """

    description = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        trim_whitespace=True,
    )

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

    fournisseur = FournisseurPatchSerializer(required=False,)
    
    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                "Aucune donnée d'achat à modifier."
            )
        return attrs


class ArrivageMetaLotSerializer(serializers.Serializer):
    """
    Champs modifiables du lot.
    """

    description = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        trim_whitespace=True,
    )

    received_at = serializers.DateTimeField(
        required=False,
    )
    
    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                "Aucune donnée de lot à modifier."
            )
        return attrs


class ArrivageMetaUpdateInSerializer(serializers.Serializer):
    """
    Payload de mise à jour documentaire d'un arrivage.

    Aucun impact sur :
    - ProduitLine
    - Stock
    - InventoryMovement
    """

    achat = ArrivageMetaAchatOutSerializer(
        required=False,
    )

    lot = ArrivageMetaLotSerializer(
        required=False,
    )

    def validate(self, attrs):
        if not attrs.get("achat") and not attrs.get("lot"):
            raise serializers.ValidationError(
                "Au moins 'achat' ou 'lot' doit être renseigné."
            )
        return attrs
    

