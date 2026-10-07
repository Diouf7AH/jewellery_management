# purchase/serializers.py

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
    Ligne d'un lot.

    Les données financières utilisent le snapshot
    enregistré au moment de l'achat :

        poids_unitaire_achat

    et non Produit.poids.

    L'UUID identifie de manière stable la ProduitLine
    et peut être utilisé par les étiquettes / QR codes.
    """

    produit = ProduitMiniSerializer(
        read_only=True,
    )

    poids_unitaire_achat = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
        allow_null=True,
    )

    poids_total = serializers.DecimalField(
        source="poids_total_calc",
        max_digits=16,
        decimal_places=2,
        read_only=True,
        allow_null=True,
    )

    montant_ht = serializers.DecimalField(
        source="montant_achat_calc",
        max_digits=18,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = ProduitLine

        fields = [
            "id",
            "uuid",
            "produit",
            "quantite",
            "poids_unitaire_achat",
            "prix_achat_gramme",
            "poids_total",
            "montant_ht",
        ]

        read_only_fields = fields
        
class ProduitLineMiniSerializer(serializers.ModelSerializer):
    """
    Représentation d'une ligne d'achat avec :

    - achat ;
    - lot ;
    - bijouterie ;
    - fournisseur ;
    - produit ;
    - données historiques d'achat ;
    - stock actuel.

    Règles :

    - quantite_recue :
        quantité historique enregistrée sur ProduitLine.quantite.

    - poids_unitaire_achat :
        snapshot historique du poids au moment de l'achat.

    - en_stock :
        stock actuel de cette ProduitLine dans la bijouterie.
        Cette valeur provient de l'annotation de InventoryPhotoView.

    - produit_line_uuid :
        identifiant stable de la ProduitLine utilisé notamment
        par les QR codes / étiquettes.
    """

    # ========================================================
    # PRODUIT LINE
    # ========================================================

    produit_line_uuid = serializers.UUIDField(
        source="uuid",
        read_only=True,
    )

    # ========================================================
    # ACHAT
    # ========================================================

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

    # ========================================================
    # LOT
    # ========================================================

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

    # ========================================================
    # BIJOUTERIE
    # ========================================================

    bijouterie_id = serializers.IntegerField(
        source="lot.achat.bijouterie.id",
        read_only=True,
    )

    bijouterie_nom = serializers.CharField(
        source="lot.achat.bijouterie.nom",
        read_only=True,
    )

    # ========================================================
    # FOURNISSEUR
    # ========================================================

    fournisseur_id = serializers.IntegerField(
        source="lot.achat.fournisseur.id",
        read_only=True,
    )

    fournisseur_nom = serializers.CharField(
        source="lot.achat.fournisseur.nom",
        read_only=True,
    )

    # ========================================================
    # PRODUIT
    # ========================================================

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

    # Poids actuel du produit.
    # Informatif uniquement.
    # Ne pas utiliser pour recalculer l'historique d'achat.
    poids_produit_actuel = serializers.DecimalField(
        source="produit.poids",
        max_digits=12,
        decimal_places=2,
        read_only=True,
        allow_null=True,
    )

    # ========================================================
    # LIGNE D'ACHAT
    # ========================================================

    quantite_recue = serializers.IntegerField(
        source="quantite",
        read_only=True,
    )

    # Snapshot historique du poids.
    poids_unitaire_achat = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
        allow_null=True,
    )

    poids_total = serializers.DecimalField(
        source="poids_total_calc",
        max_digits=16,
        decimal_places=2,
        read_only=True,
        allow_null=True,
    )

    prix_achat_gramme = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    montant_achat = serializers.DecimalField(
        source="montant_achat_calc",
        max_digits=18,
        decimal_places=2,
        read_only=True,
    )

    # ========================================================
    # STOCK ACTUEL
    # ========================================================

    en_stock = serializers.IntegerField(
        source="en_stock_total",
        read_only=True,
    )

    # ========================================================
    # META
    # ========================================================

    class Meta:
        model = ProduitLine

        fields = [
            "id",
            "produit_line_uuid",

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
            "poids_produit_actuel",

            # Ligne d'achat
            "quantite_recue",
            "poids_unitaire_achat",
            "poids_total",
            "prix_achat_gramme",
            "montant_achat",

            # Stock actuel
            "en_stock",
        ]

        read_only_fields = fields

class AchatBaseOutSerializer(serializers.ModelSerializer):
    """
    Base commune des serializers de sortie d'un achat.

    Contient uniquement les informations générales
    de l'achat.

    Les lots et les ProduitLine sont exposés
    par les serializers détaillés.
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
    Représentation synthétique d'un achat,
    sans ses lots ni ses lignes produit.
    """

    class Meta(AchatBaseOutSerializer.Meta):
        fields = AchatBaseOutSerializer.Meta.fields
        read_only_fields = fields

### end achat


# Lot


class LotOutSerializer(serializers.ModelSerializer):
    """
    Lot avec ses lignes produit.

    Chaque ligne expose son UUID ProduitLine,
    utilisé notamment pour l'identification
    par QR code / étiquette.
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
    Vue détaillée d'un achat avec :

    - la bijouterie ;
    - le fournisseur ;
    - les lots ;
    - les lignes produit de chaque lot.

    Les ProduitLine conservent les données
    historiques de l'achat.
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
    Liste des lots avec :

    - achat ;
    - fournisseur ;
    - bijouterie ;
    - lignes produit ;
    - nombre de lignes ;
    - quantité historique achetée.

    Les champs nb_lignes et quantite_achetee
    doivent être fournis par annotate() dans le queryset.

    quantite_achetee correspond à :

        Sum("lignes__quantite")

    Il s'agit d'une donnée historique d'achat.
    Elle ne représente pas le stock actuel.
    """

    achat = AchatOutSerializer(
        read_only=True,
    )

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

    nb_lignes = serializers.IntegerField(
        read_only=True,
    )

    quantite_achetee = serializers.IntegerField(
        read_only=True,
    )

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
            "quantite_achetee",

            "achat",
            "lignes",
        ]

        read_only_fields = fields
        
# end lot

# respose
class ArrivageCreateResponseSerializer(serializers.Serializer):
    """
    Réponse globale après création d'un arrivage.

    Structure :
        {
            "achat": {...},
            "lots": [...]
        }

    Les lots contiennent leurs ProduitLine,
    avec les données historiques d'achat.
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
    """
    Données permettant de modifier ou d'identifier
    le fournisseur associé à un achat.

    Si l'id est fourni, il est utilisé pour identifier
    directement le fournisseur.

    Sinon, le téléphone est obligatoire.
    """

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

        # Si l'ID est fourni, il permet d'identifier
        # directement le fournisseur.
        if fournisseur_id:
            return attrs

        # Sans ID, le téléphone devient obligatoire.
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
    """
    Serializer principal du fournisseur.

    Les champs techniques sont en lecture seule :
    - id
    - slug
    - date_ajout
    - date_modification
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
        value = (value or "").strip()

        if not value:
            raise serializers.ValidationError(
                "Le nom du fournisseur est obligatoire."
            )

        return value

    def validate_telephone(self, value):
        value = (value or "").strip()

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
        value = (value or "").strip()

        if not value:
            raise serializers.ValidationError(
                "Le nom du fournisseur est obligatoire."
            )

        return value

    def validate_prenom(self, value):
        return (value or "").strip()

    def validate_telephone(self, value):
        value = (value or "").strip()

        if not value:
            raise serializers.ValidationError(
                "Le téléphone du fournisseur est obligatoire."
            )

        return value

    def validate_address(self, value):
        return (value or "").strip()


class LotLineInSerializer(serializers.Serializer):
    """
    Ligne produit reçue dans un lot.

    Le client fournit uniquement :
    - le produit ;
    - la quantité reçue ;
    - le prix d'achat au gramme.

    poids_unitaire_achat n'est volontairement
    pas accepté depuis le client.

    Il est automatiquement copié depuis Produit.poids
    lors de la création de ProduitLine afin de conserver
    le poids historique au moment de l'achat.
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

    Chaque produit ne peut apparaître qu'une seule fois
    dans un même lot.
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
            ↓
        Stock en bijouterie

    Pour chaque ProduitLine créée :

        - quantite :
            quantité historique reçue ;

        - poids_unitaire_achat :
            copié automatiquement depuis Produit.poids ;

        - Stock.en_stock :
            initialisé avec la quantité reçue.

    Mouvement généré :

        PURCHASE_IN
        EXTERNAL → BIJOUTERIE
    """

    bijouterie_id = serializers.IntegerField(
        min_value=1,
        required=True,
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
        return value.strip() if value else ""

    def validate_description(self, value):
        return value.strip() if value else ""
    
# ============================================================
# PATCH Arrivage (métadonnées uniquement)
# ============================================================

class ArrivageMetaAchatPatchSerializer(serializers.Serializer):
    """
    Champs modifiables de l'achat.

    Ce serializer ne modifie jamais :
    - les lots ;
    - les ProduitLine ;
    - les quantités reçues ;
    - le poids_unitaire_achat ;
    - le prix_achat_gramme ;
    - le stock ;
    - les mouvements de stock.
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

    fournisseur = FournisseurPatchSerializer(
        required=False,
    )

    def validate_description(self, value):
        return value.strip() if value else ""

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                "Aucune donnée d'achat à modifier."
            )

        return attrs
    

class ArrivageMetaLotSerializer(serializers.Serializer):
    """
    Champs modifiables du lot.

    Ce serializer permet uniquement de modifier
    les métadonnées du lot.

    Il ne modifie jamais :
    - les ProduitLine ;
    - les quantités reçues ;
    - le poids_unitaire_achat ;
    - les prix d'achat ;
    - le stock ;
    - les mouvements de stock.
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

    def validate_description(self, value):
        return value.strip() if value else ""

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                "Aucune donnée de lot à modifier."
            )

        return attrs


class ArrivageMetaUpdateInSerializer(serializers.Serializer):
    """
    Payload de mise à jour documentaire d'un arrivage.

    Permet uniquement de modifier :
    - certaines métadonnées de l'achat ;
    - certaines métadonnées du lot.

    Aucun impact sur :
    - ProduitLine ;
    - ProduitLine.quantite ;
    - ProduitLine.poids_unitaire_achat ;
    - ProduitLine.prix_achat_gramme ;
    - Stock ;
    - VendorStock ;
    - InventoryMovement.
    """

    achat = ArrivageMetaAchatPatchSerializer(
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
    

