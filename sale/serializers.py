# sale/serializers.py
from decimal import Decimal

from django.apps import apps
from django.db import models
from django.db.models import Sum
from rest_framework import serializers

from backend.permissions import (ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR,
                                 get_role_name)
from sale.services.sale_service import validate_facture_payable
from store.models import Bijouterie, MarquePurete, Produit
from store.serializers import BijouterieSerializer, ProduitSerializer
from vendor.models import Vendor
from vendor.serializer import VendorSerializer

from .models import Facture, ModePaiement, Vente, VenteAutre, VenteProduit


# ---- store serializers light ----
class BijouterieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bijouterie
        fields = ["id", "nom", "telephone_portable_1", "adresse", "nom_de_domaine"]
        ref_name = "BijouterieOut"

class ProduitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Produit
        fields = ["id", "nom", "sku", "slug", "poids", "categorie", "marque", "purete"]
        ref_name = "ProduitOutLight"

# ---- vendor serializer light ----
class VendorSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email    = serializers.EmailField(source="user.email", read_only=True)
    bijouterie = BijouterieSerializer(read_only=True)

    class Meta:
        model = Vendor
        fields = ["id", "username", "email", "bijouterie"]
        ref_name = "VendorOutLight"
# ----End vendor serializer light ----


class VenteProduitSerializer(serializers.ModelSerializer):
    slug = serializers.CharField(source="produit.slug", read_only=True)

    produit_id = serializers.PrimaryKeyRelatedField(
        source="produit",
        queryset=Produit.objects.all(),
        write_only=True,
    )

    vendor_id = serializers.PrimaryKeyRelatedField(
        source="vendor",
        queryset=Vendor.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    produit = ProduitSerializer(read_only=True)
    vendor = VendorSerializer(read_only=True)

    # ✅ NOUVEAUX CHAMPS
    montant_ht = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    montant_total = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    prix_vente_grammes = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        allow_null=True,
    )

    remise = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        allow_null=True,
    )

    autres = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = VenteProduit
        ref_name = "VenteProduitLine"
        fields = [
            "id",
            "slug",
            "produit_id",
            "vendor_id",
            "produit",
            "vendor",
            "quantite",
            "prix_vente_grammes",
            "remise",
            "autres",
            "montant_ht",
            "montant_total",
        ]
        read_only_fields = (
            "id",
            "montant_ht",
            "montant_total",
        )

    def to_internal_value(self, data):
        data = data.copy()

        for field in ("prix_vente_grammes", "remise", "autres"):
            if field in data and data.get(field) == "":
                data[field] = None

        return super().to_internal_value(data)

    def validate(self, attrs):
        for f in ("prix_vente_grammes", "remise", "autres"):
            v = attrs.get(f)
            if v is not None and v < 0:
                raise serializers.ValidationError({f: "Ne peut pas être négatif."})

        q = attrs.get("quantite")
        if q is not None and q < 1:
            raise serializers.ValidationError({"quantite": "Doit être ≥ 1."})

        return attrs
    

class ClientOptionalInSerializer(serializers.Serializer):
    nom = serializers.CharField(required=False, allow_blank=True)
    prenom = serializers.CharField(required=False, allow_blank=True)
    telephone = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        nom = (attrs.get("nom") or "").strip()
        prenom = (attrs.get("prenom") or "").strip()
        tel = (attrs.get("telephone") or "").strip()

        # si le bloc client est vide => ok (optionnel)
        if not nom and not prenom and not tel:
            return {}

        # si partiellement rempli => refuse données sales
        if not nom or not prenom:
            raise serializers.ValidationError("Si client est fourni, nom et prenom sont obligatoires.")
        attrs["nom"] = nom
        attrs["prenom"] = prenom
        attrs["telephone"] = tel
        return attrs
    


class ClientInSerializer(serializers.Serializer):
    nom = serializers.CharField(required=True, allow_blank=False)
    prenom = serializers.CharField(required=True, allow_blank=False)
    telephone = serializers.CharField(required=False, allow_blank=True)


# ============================================================
# 1. LIGNE DE BIJOU POUR CRÉATION D'UNE VENTE
# ============================================================
class VenteProduitSerializer(serializers.ModelSerializer):
    produit_id = serializers.IntegerField(
        source="produit_line.produit_id",
        read_only=True,
    )

    produit_line_id = serializers.IntegerField(
        read_only=True,
    )

    produit_nom = serializers.CharField(
        source="produit_line.produit.nom",
        read_only=True,
    )

    sku = serializers.CharField(
        source="produit_line.produit.sku",
        read_only=True,
    )

    vendor_id = serializers.IntegerField(
        read_only=True,
    )

    class Meta:
        model = VenteProduit

        fields = [
            "id",
            "produit_id",
            "produit_line_id",
            "produit_nom",
            "sku",
            "vendor_id",
            "quantite",
            "etat_vente",
            "poids_unitaire_vente",
            "pourcentage_occasion",
            "prix_vente_grammes",
            "remise",
            "montant_brut_ht",
            "montant_reduction",
            "montant_ht",
            "montant_total",
        ]

        read_only_fields = fields
        
# ============================================================
# 2. PRESTATIONS / AUTRES PRODUITS
# ============================================================

class VenteAutreInSerializer(serializers.Serializer):
    """
    Une prestation ou ligne complémentaire de vente.

    Exemples :
    - réparation ;
    - nettoyage ;
    - autre prestation.

    Le montant total est calculé par VenteAutre.
    """

    type_autre = serializers.ChoiceField(
        choices=VenteAutre.TYPE_CHOICES,
        required=True,
    )

    quantite = serializers.IntegerField(
        min_value=1,
        required=False,
        default=1,
    )

    prix_unitaire = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=True,
    )

# ============================================================
# 3. CRÉATION D'UNE VENTE
# ============================================================

class VenteProduitInSerializer(serializers.Serializer):
    """
    Serializer d'entrée pour une ligne de bijou.

    Identification :
        - produit_line_id : recherche manuelle / SKU
        - qr : scan QR Code

    Un seul identifiant doit être renseigné.

    Prix :
        - prix_vente_grammes facultatif
        - 0 signifie tarif déterminé par le service

    Réduction :
        - bijou neuf : remise fixe en FCFA
        - bijou d'occasion : réduction calculée
          par le service selon ProduitLine

    Les montants sont calculés côté serveur.
    """

    produit_line_id = serializers.IntegerField(
        required=False,
        min_value=1,
    )

    qr = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        trim_whitespace=True,
    )

    quantite = serializers.IntegerField(
        required=False,
        default=1,
        min_value=1,
    )

    prix_vente_grammes = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        default=Decimal("0.00"),
        allow_null=True,
        min_value=Decimal("0.00"),
    )

    remise = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        default=Decimal("0.00"),
        allow_null=True,
        min_value=Decimal("0.00"),
    )

    def validate_prix_vente_grammes(self, value):
        if value is None:
            return Decimal("0.00")

        return value

    def validate_remise(self, value):
        if value is None:
            return Decimal("0.00")

        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)

        produit_line_id = attrs.get("produit_line_id")

        qr = (attrs.get("qr") or "").strip()

        # Aucun identifiant fourni
        if produit_line_id is None and not qr:
            raise serializers.ValidationError({
                "produit_line_id": (
                    "Fournissez produit_line_id ou qr."
                )
            })

        # Deux identifiants fournis
        if produit_line_id is not None and qr:
            raise serializers.ValidationError({
                "qr": (
                    "Fournissez produit_line_id ou qr, "
                    "mais pas les deux simultanément."
                )
            })

        # Identification par QR
        if qr:
            if not qr.upper().startswith("PL:"):
                raise serializers.ValidationError({
                    "qr": (
                        "Format QR invalide. "
                        "Le QR doit commencer par PL:."
                    )
                })

            attrs["qr"] = qr

        # Identification par produit_line_id
        else:
            attrs.pop("qr", None)

        return attrs
    

class VenteCreateInSerializer(serializers.Serializer):
    """
    Création d'une vente Rio-Gold.

    Types :
    - Bijoux uniquement : proforma.
    - Prestations uniquement : paiement direct, sans facture.
    - Bijoux + prestations : proforma.

    Identification des bijoux :
    - produit_line_id : recherche manuelle / SKU.
    - qr : scan QR Code.

    Règles :
    - Au moins un bijou ou une prestation obligatoire.
    - Admin/manager : vendor_email obligatoire.
    - Vendeur : utilise son propre profil.
    - Aucun stock consommé à la création.
    """

    vendor_email = serializers.EmailField(
        required=False,
        allow_null=True,
    )

    client = ClientOptionalInSerializer(
        required=False,
        allow_null=True,
    )

    produits = VenteProduitInSerializer(
        many=True,
        required=False,
        allow_empty=True,
        allow_null=True,
    )

    autres = VenteAutreInSerializer(
        many=True,
        required=False,
        allow_empty=True,
        allow_null=True,
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)

        produits = attrs.get("produits") or []
        autres = attrs.get("autres") or []

        if not produits and not autres:
            raise serializers.ValidationError({
                "vente": (
                    "La vente doit contenir au moins "
                    "un bijou ou une prestation."
                )
            })

        request = self.context.get("request")

        if (
            request is None
            or not request.user.is_authenticated
        ):
            raise serializers.ValidationError({
                "detail": "Authentification requise."
            })

        role = (
            get_role_name(request.user) or ""
        ).strip().lower()

        if role in {ROLE_ADMIN, ROLE_MANAGER}:

            vendor_email = (
                attrs.get("vendor_email") or ""
            ).strip().lower()

            if not vendor_email:
                raise serializers.ValidationError({
                    "vendor_email": (
                        "Le vendeur est obligatoire "
                        "pour un administrateur "
                        "ou un manager."
                    )
                })

            attrs["vendor_email"] = vendor_email

        elif role == ROLE_VENDOR:

            attrs.pop("vendor_email", None)

        else:
            raise serializers.ValidationError({
                "detail": (
                    "Vous n'êtes pas autorisé "
                    "à créer une vente."
                )
            })

        attrs["produits"] = produits
        attrs["autres"] = autres

        return attrs
    

# ============================================================
# PRESTATIONS / AUTRES PRODUITS - SORTIE
# ============================================================

class VenteAutreSerializer(serializers.ModelSerializer):
    type_autre_libelle = serializers.CharField(
        source="get_type_autre_display",
        read_only=True,
    )

    class Meta:
        model = VenteAutre

        fields = [
            "id",
            "type_autre",
            "type_autre_libelle",
            "quantite",
            "prix_unitaire",
            "montant_total",
        ]

        read_only_fields = fields

# ============================================================
# FACTURE - SORTIE
# ============================================================

class FactureSerializer(serializers.ModelSerializer):
    """
    Serializer de lecture des factures Rio-Gold.

    Gère :
    - Vente et client
    - Bijoux vendus
    - Prestations et articles complémentaires
    - Remises sur les bijoux
    - TVA et frais de transaction
    - Paiements et reste à payer
    - Statut réel du règlement
    - Verrouillage de la facture
    - État de consommation du stock

    Les montants financiers sont calculés côté serveur.

    Les relations préchargées par select_related() et
    prefetch_related() sont réutilisées automatiquement.
    """

    uuid = serializers.UUIDField(
        read_only=True,
    )

    # ========================================================
    # INFORMATIONS DE LA BIJOUTERIE
    # ========================================================

    bijouterie = serializers.SerializerMethodField()

    # ========================================================
    # INFORMATIONS DE VENTE
    # ========================================================

    vente = serializers.SerializerMethodField()

    client = serializers.SerializerMethodField()

    produits = serializers.SerializerMethodField()

    prestations = serializers.SerializerMethodField()

    # ========================================================
    # MONTANTS CALCULÉS
    # ========================================================

    remise_totale = serializers.SerializerMethodField()

    total_prestations = serializers.SerializerMethodField()

    total_paye = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
    )

    reste_a_payer = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
    )

    est_reglee = serializers.SerializerMethodField()

    # ========================================================
    # VERROUILLAGE
    # ========================================================

    is_locked = serializers.BooleanField(
        read_only=True,
    )

    locked_at = serializers.DateTimeField(
        format="%Y-%m-%d %H:%M:%S",
        read_only=True,
        allow_null=True,
    )

    # ========================================================
    # STOCK
    # ========================================================

    stock_consumed = serializers.BooleanField(
        read_only=True,
    )

    # ========================================================
    # DATE
    # ========================================================

    date_creation = serializers.DateTimeField(
        format="%Y-%m-%d %H:%M:%S",
        read_only=True,
    )

    # ========================================================
    # META
    # ========================================================

    class Meta:
        model = Facture

        fields = [
            "id",
            "uuid",
            "numero_facture",

            "bijouterie",
            "vente",
            "client",

            "produits",
            "prestations",

            "type_facture",

            "montant_ht",
            "appliquer_tva",
            "taux_tva",
            "montant_tva",
            "frais_transaction",
            "montant_total",

            "remise_totale",
            "total_prestations",

            "total_paye",
            "reste_a_payer",

            "status",
            "est_reglee",

            "is_locked",
            "locked_at",

            "stock_consumed",

            "date_creation",
        ]

        read_only_fields = fields

    # ========================================================
    # HELPERS
    # ========================================================

    @staticmethod
    def _somme(lignes, champ):
        """
        Additionne les montants d'une collection déjà chargée.
        """

        return sum(
            (
                getattr(ligne, champ, None)
                or Decimal("0.00")
                for ligne in lignes
            ),
            Decimal("0.00"),
        )

    @staticmethod
    def _lignes_vente(vente):
        """
        Réutilise le cache de prefetch_related si présent.
        """

        return vente.lignes.all()

    @staticmethod
    def _lignes_prestations(vente):
        """
        Réutilise le cache de prefetch_related si présent.
        """

        return vente.autres.all()

    # ========================================================
    # BIJOUTERIE
    # ========================================================

    def get_bijouterie(self, obj):
        bijouterie = obj.bijouterie

        if bijouterie is None:
            return None

        return {
            "id": bijouterie.pk,
            "nom": bijouterie.nom,
        }

    # ========================================================
    # VENTE
    # ========================================================

    def get_vente(self, obj):
        vente = obj.vente

        if vente is None:
            return None

        return {
            "id": vente.pk,
            "uuid": str(vente.uuid),
            "numero_vente": vente.numero_vente,
        }

    # ========================================================
    # CLIENT
    # ========================================================

    def get_client(self, obj):
        vente = obj.vente

        if vente is None:
            return None

        client = vente.client

        if client is None:
            return None

        return {
            "id": client.pk,
            "nom": getattr(client, "nom", None),
            "prenom": getattr(client, "prenom", None),
            "telephone": getattr(client, "telephone", None),
        }

    # ========================================================
    # BIJOUX VENDUS
    # ========================================================

    def get_produits(self, obj):
        vente = obj.vente

        if vente is None:
            return []

        lignes = self._lignes_vente(vente)

        return VenteProduitSerializer(
            lignes,
            many=True,
            context=self.context,
        ).data

    # ========================================================
    # PRESTATIONS / AUTRES PRODUITS
    # ========================================================

    def get_prestations(self, obj):
        vente = obj.vente

        if vente is None:
            return []

        lignes = self._lignes_prestations(vente)

        return VenteAutreSerializer(
            lignes,
            many=True,
            context=self.context,
        ).data

    # ========================================================
    # REMISE TOTALE SUR LES BIJOUX
    # ========================================================

    def get_remise_totale(self, obj):
        vente = obj.vente

        if vente is None:
            return "0.00"

        total = self._somme(
            self._lignes_vente(vente),
            "montant_reduction",
        )

        return f"{total:.2f}"

    # ========================================================
    # TOTAL DES PRESTATIONS
    # ========================================================

    def get_total_prestations(self, obj):
        vente = obj.vente

        if vente is None:
            return "0.00"

        total = self._somme(
            self._lignes_prestations(vente),
            "montant_total",
        )

        return f"{total:.2f}"

    # ========================================================
    # FACTURE RÉGLÉE
    # ========================================================

    def get_est_reglee(self, obj):
        return obj.est_reglee()


# ============================================================
# FACTURE - DÉTAIL
# ============================================================

class FactureDetailSerializer(FactureSerializer):
    """
    Détail complet d'une facture Rio-Gold.
    """

    pass

class FactureListSerializer(serializers.ModelSerializer):
    """
    Liste optimisée des factures Rio-Gold.

    Lecture seule.
    Compatible avec la pagination et le préchargement.
    """

    uuid = serializers.UUIDField(read_only=True)

    bijouterie = serializers.SerializerMethodField()
    vente = serializers.SerializerMethodField()
    client = serializers.SerializerMethodField()
    produits = serializers.SerializerMethodField()

    total_paye = serializers.SerializerMethodField()
    reste_a_payer = serializers.SerializerMethodField()

    is_locked = serializers.BooleanField(read_only=True)

    locked_at = serializers.DateTimeField(
        format="%Y-%m-%d %H:%M:%S",
        read_only=True,
        allow_null=True,
    )

    stock_consumed = serializers.BooleanField(read_only=True)

    date_creation = serializers.DateTimeField(
        format="%Y-%m-%d %H:%M:%S",
        read_only=True,
    )

    class Meta:
        model = Facture

        fields = [
            "id",
            "uuid",
            "numero_facture",
            "bijouterie",
            "vente",
            "client",
            "produits",
            "type_facture",
            "montant_ht",
            "taux_tva",
            "montant_tva",
            "montant_total",
            "total_paye",
            "reste_a_payer",
            "status",
            "is_locked",
            "locked_at",
            "stock_consumed",
            "date_creation",
        ]

        read_only_fields = fields

    # ========================================================
    # HELPERS
    # ========================================================

    def _total_paye_decimal(self, obj):
        """
        Utilise l'agrégation fournie par la vue.

        Repli sur le modèle si ce serializer est employé
        dans une autre vue sans agrégation.
        """

        montants = self.context.get(
            "totaux_paiements"
        )

        if montants is not None:
            return Decimal(
                str(
                    montants.get(
                        obj.pk,
                        Decimal("0.00"),
                    )
                )
            )

        return Decimal(str(obj.total_paye))

    # ========================================================
    # BIJOUTERIE
    # ========================================================

    def get_bijouterie(self, obj):
        b = obj.bijouterie

        if b is None:
            return None

        return {
            "id": b.pk,
            "nom": b.nom,
        }

    # ========================================================
    # VENTE
    # ========================================================

    def get_vente(self, obj):
        v = obj.vente

        if v is None:
            return None

        return {
            "id": v.pk,
            "numero_vente": v.numero_vente,
        }

    # ========================================================
    # CLIENT
    # ========================================================

    def get_client(self, obj):
        v = obj.vente

        if v is None:
            return None

        c = v.client

        if c is None:
            return None

        return {
            "id": c.pk,
            "nom": getattr(c, "nom", None),
            "prenom": getattr(c, "prenom", None),
            "telephone": getattr(c, "telephone", None),
        }

    # ========================================================
    # PRODUITS
    # ========================================================

    def get_produits(self, obj):
        v = obj.vente

        if v is None:
            return []

        return VenteProduitSerializer(
            v.lignes.all(),
            many=True,
            context=self.context,
        ).data

    # ========================================================
    # PAIEMENTS
    # ========================================================

    def get_total_paye(self, obj):
        total = self._total_paye_decimal(obj)

        return f"{total:.2f}"

    def get_reste_a_payer(self, obj):
        montants = self.context.get(
            "totaux_paiements"
        )

        if montants is None:
            return f"{Decimal(str(obj.reste_a_payer)):.2f}"

        total = self._total_paye_decimal(obj)

        reste = max(
            Decimal("0.00"),
            Decimal(str(obj.montant_total)) - total,
        )

        return f"{reste:.2f}"


class VenteListSerializer(serializers.ModelSerializer):
    client = serializers.SerializerMethodField()
    produits = VenteProduitSerializer(source="lignes", many=True, read_only=True)
    facture = serializers.SerializerMethodField()
    uuid = serializers.UUIDField(read_only=True)

    class Meta:
        model = Vente
        fields = [
            "id",
            "uuid",
            "numero_vente",
            "created_at",
            "montant_total",
            "client",
            "facture",
            "produits",
        ]
        ref_name = "VenteList_V2"

    def get_client(self, obj):
        c = getattr(obj, "client", None)
        return {
            "prenom": c.prenom,
            "nom": c.nom,
            "telephone": c.telephone,
        } if c else None

    def get_facture(self, obj):
        facture = getattr(obj, "facture_vente", None)
        if not facture:
            return None

        return {
            "id": facture.id,
            "numero_facture": facture.numero_facture,
            "type_facture": facture.type_facture,
            "status": facture.status,
            "montant_ht": str(facture.montant_ht),
            "montant_tva": str(facture.montant_tva),
            "montant_total": str(facture.montant_total),
        }

# ---------------------------------------------------
# Vente detail
# ---------------------------------------------------

class VenteDetailSerializer(serializers.ModelSerializer):
    """
    Détail complet d'une vente Rio-Gold.

    - Bijoux depuis VenteProduit.
    - Prestations depuis VenteAutre.
    - Produit identifié par ProduitLine.
    - Facture facultative.
    - Montants calculés côté serveur.
    """

    client = serializers.SerializerMethodField()
    produits = serializers.SerializerMethodField()
    prestations = serializers.SerializerMethodField()
    vente = serializers.SerializerMethodField()
    facture = serializers.SerializerMethodField()

    total_remise = serializers.SerializerMethodField()
    total_ht = serializers.SerializerMethodField()
    total_autres = serializers.SerializerMethodField()
    total_ttc = serializers.SerializerMethodField()
    totaux = serializers.SerializerMethodField()

    bijouterie = BijouterieSerializer(
        read_only=True,
    )

    class Meta:
        model = Vente

        ref_name = "VenteDetailOut_V3"

        fields = [
            "id",
            "uuid",
            "client",
            "produits",
            "prestations",
            "vente",
            "facture",
            "bijouterie",
            "montant_total",
            "total_autres",
            "total_ttc",
            "total_remise",
            "total_ht",
            "totaux",
        ]

        read_only_fields = fields

    # ========================================================
    # HELPERS
    # ========================================================

    def _lignes(self, obj):
        cache = getattr(
            obj,
            "_prefetched_objects_cache",
            {},
        )

        if "lignes" in cache:
            return cache["lignes"]

        return obj.lignes.all()

    def _prestations(self, obj):
        cache = getattr(
            obj,
            "_prefetched_objects_cache",
            {},
        )

        if "autres" in cache:
            return cache["autres"]

        return obj.autres.all()

    def _str_or_none(self, value):
        return str(value) if value is not None else None

    def _somme(self, lignes, champ):
        return sum(
            (
                getattr(ligne, champ, None)
                or Decimal("0.00")
                for ligne in lignes
            ),
            Decimal("0.00"),
        )

    # ========================================================
    # CLIENT
    # ========================================================

    def get_client(self, obj):
        client = getattr(obj, "client", None)

        if client is None:
            return None

        return {
            "id": client.pk,
            "nom": client.nom,
            "prenom": client.prenom,
            "telephone": client.telephone,
        }

    # ========================================================
    # BIJOUX
    # ========================================================

    def get_produits(self, obj):
        lignes = self._lignes(obj)

        return VenteProduitSerializer(
            lignes,
            many=True,
            context=self.context,
        ).data

    # ========================================================
    # PRESTATIONS
    # ========================================================

    def get_prestations(self, obj):
        lignes = self._prestations(obj)

        return VenteAutreSerializer(
            lignes,
            many=True,
            context=self.context,
        ).data

    # ========================================================
    # VENTE
    # ========================================================

    def get_vente(self, obj):
        return {
            "id": obj.pk,
            "uuid": str(obj.uuid),
            "numero_vente": obj.numero_vente,
            "created_at": (
                obj.created_at.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                if obj.created_at
                else None
            ),
        }

    # ========================================================
    # FACTURE
    # ========================================================

    def get_facture(self, obj):
        facture = getattr(
            obj,
            "facture_vente",
            None,
        )

        if facture is None:
            return None

        return {
            "id": facture.pk,
            "uuid": str(facture.uuid),
            "numero_facture": facture.numero_facture,
            "type_facture": facture.type_facture,
            "status": facture.status,

            "montant_ht": str(
                facture.montant_ht
            ),

            "appliquer_tva": facture.appliquer_tva,

            "taux_tva": self._str_or_none(
                facture.taux_tva
            ),

            "montant_tva": self._str_or_none(
                facture.montant_tva
            ),

            "frais_transaction": str(
                facture.frais_transaction
            ),

            "montant_total": str(
                facture.montant_total
            ),

            "total_paye": str(
                facture.total_paye
            ),

            "reste_a_payer": str(
                facture.reste_a_payer
            ),

            "est_reglee": facture.est_reglee(),
            "is_locked": facture.is_locked,
            "stock_consumed": facture.stock_consumed,
        }

    # ========================================================
    # REMISE TOTALE
    # ========================================================

    def get_total_remise(self, obj):
        lignes = self._lignes(obj)

        total = self._somme(
            lignes,
            "montant_reduction",
        )

        return f"{total:.2f}"

    # ========================================================
    # TOTAL PRESTATIONS
    # ========================================================

    def get_total_autres(self, obj):
        prestations = self._prestations(obj)

        total = self._somme(
            prestations,
            "montant_total",
        )

        return f"{total:.2f}"

    # ========================================================
    # TOTAL HT
    # ========================================================

    def get_total_ht(self, obj):
        lignes = self._lignes(obj)
        prestations = self._prestations(obj)

        total_bijoux = self._somme(
            lignes,
            "montant_total",
        )

        total_prestations = self._somme(
            prestations,
            "montant_total",
        )

        return f"{total_bijoux + total_prestations:.2f}"

    # ========================================================
    # TOTAL TTC
    # ========================================================

    def get_total_ttc(self, obj):
        facture = getattr(
            obj,
            "facture_vente",
            None,
        )

        if facture is not None:
            return str(facture.montant_total)

        # Prestations seules : aucune facture.
        return str(
            obj.montant_total or Decimal("0.00")
        )

    # ========================================================
    # RÉCAPITULATIF FINANCIER
    # ========================================================

    def get_totaux(self, obj):
        lignes = self._lignes(obj)
        prestations = self._prestations(obj)

        facture = getattr(
            obj,
            "facture_vente",
            None,
        )

        total_bijoux = self._somme(
            lignes,
            "montant_total",
        )

        remise_totale = self._somme(
            lignes,
            "montant_reduction",
        )

        total_prestations = self._somme(
            prestations,
            "montant_total",
        )

        montant_ht_vente = (
            total_bijoux + total_prestations
        )

        return {
            "montant_ht_lignes": f"{total_bijoux:.2f}",
            "remise_totale": f"{remise_totale:.2f}",
            "autres_total": f"{total_prestations:.2f}",
            "montant_total_lignes": f"{montant_ht_vente:.2f}",

            "montant_ht_facture": (
                str(facture.montant_ht)
                if facture
                else None
            ),

            "taux_tva": (
                self._str_or_none(facture.taux_tva)
                if facture
                else None
            ),

            "montant_tva": (
                self._str_or_none(facture.montant_tva)
                if facture
                else None
            ),

            "frais_transaction": (
                str(facture.frais_transaction)
                if facture
                else None
            ),

            "montant_total_facture": (
                str(facture.montant_total)
                if facture
                else None
            ),
        }

class VenteProduitDetailSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source="produit.nom", read_only=True)

    class Meta:
        model = VenteProduit
        fields = [
            "id",
            "produit_id",
            "produit_nom",
            "quantite",
            "prix_vente_grammes",
            "montant_ht",
            "remise",
            "autres",
            "montant_total",
        ]


class VenteOutWrapperSerializer(serializers.Serializer):
    facture = FactureSerializer()
    vente   = VenteDetailSerializer()

    class Meta:
        ref_name = "VenteCreateOut"
        
        
# -----Serializers de sortie avec HT/TTC, vendor et bijouterie-----------

class ClientInSerializer(serializers.Serializer):
    """
    Client transmis lors du paiement.

    Sans compte dépôt :
        nom et prénom obligatoires si la vente
        n'a pas déjà un client identifié.

    Avec compte dépôt :
        téléphone obligatoire.
        Nom et prénom récupérés du compte.
    """

    nom = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )

    prenom = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )

    telephone = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        trim_whitespace=True,
    )


class PaiementModeItemSerializer(serializers.Serializer):
    """
    Une ligne de paiement.

    telephone et numero_compte ne figurent
    pas dans les lignes.
    """

    mode = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
    )

    montant = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=True,
    )

    reference = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        trim_whitespace=True,
    )

    def validate_mode(self, value):
        return value.strip().lower()

    def validate_reference(self, value):
        return value.strip() or None if value else None


class PaiementMultiModeSerializer(serializers.Serializer):
    """
    Paiement multimode Rio-Gold.

    - Client facultatif à la création de vente.
    - Nom/prénom requis au paiement ordinaire.
    - Téléphone requis pour le compte dépôt.
    - Référence requise selon ModePaiement.
    - Référence dépôt générée par le backend.
    - Un seul passage par mode de paiement.
    - Paiement partiel ou intégral.
    """

    numero_facture = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
    )

    client = ClientInSerializer(
        required=False,
        allow_null=True,
    )

    lignes = PaiementModeItemSerializer(
        many=True,
        allow_empty=False,
        required=True,
    )

    def validate_numero_facture(self, value):
        value = value.strip()

        if not Facture.objects.filter(
            numero_facture__iexact=value
        ).exists():
            raise serializers.ValidationError(
                "Facture introuvable."
            )

        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)

        numero_facture = attrs["numero_facture"]

        facture = (
            Facture.objects
            .select_related(
                "vente",
                "vente__client",
            )
            .filter(
                numero_facture__iexact=numero_facture
            )
            .first()
        )

        if facture is None:
            raise serializers.ValidationError({
                "numero_facture": "Facture introuvable."
            })

        client_data = attrs.get("client") or {}

        client_existant = (
            facture.vente.client
            if facture.vente_id
            else None
        )

        telephone_client = str(
            client_data.get("telephone") or ""
        ).strip()

        total_paiement = Decimal("0.00")
        modes_utilises = set()
        lignes_normalisees = []
        paiement_avec_depot = False

        # ============================================
        # 1. VALIDATION DES MODES
        # ============================================

        for index, ligne in enumerate(
            attrs["lignes"],
            start=1,
        ):
            mode_code = ligne["mode"]
            montant = ligne["montant"]
            reference = ligne.get("reference")

            if mode_code in modes_utilises:
                raise serializers.ValidationError({
                    "lignes": (
                        f"Le mode '{mode_code}' apparaît "
                        "plusieurs fois."
                    )
                })

            modes_utilises.add(mode_code)

            mode_obj = (
                ModePaiement.objects
                .filter(
                    code__iexact=mode_code,
                    active=True,
                )
                .first()
            )

            if mode_obj is None:
                raise serializers.ValidationError({
                    "lignes": (
                        f"Mode invalide ou inactif "
                        f"à la ligne {index} : {mode_code}."
                    )
                })

            # ========================================
            # 2. COMPTE DÉPÔT
            # ========================================

            if mode_obj.est_mode_depot:
                paiement_avec_depot = True

                if not telephone_client:
                    raise serializers.ValidationError({
                        "client": {
                            "telephone": (
                                "Téléphone obligatoire "
                                "pour le compte dépôt."
                            )
                        }
                    })

                if reference:
                    raise serializers.ValidationError({
                        "lignes": (
                            "Ne saisissez pas de référence "
                            "pour le compte dépôt."
                        )
                    })

            # ========================================
            # 3. AUTRES MODES
            # ========================================

            elif (
                mode_obj.necessite_reference
                and not reference
            ):
                raise serializers.ValidationError({
                    "lignes": (
                        f"Référence obligatoire pour "
                        f"le mode '{mode_obj.nom}'."
                    )
                })

            total_paiement += montant

            lignes_normalisees.append({
                "mode": mode_obj.code,
                "montant": montant,
                "reference": reference,
            })

        # ============================================
        # 4. VALIDATION CLIENT
        # ============================================

        if not paiement_avec_depot:

            if client_data:
                nom = str(
                    client_data.get("nom") or ""
                ).strip()

                prenom = str(
                    client_data.get("prenom") or ""
                ).strip()
            else:
                nom = str(
                    getattr(client_existant, "nom", "") or ""
                ).strip()

                prenom = str(
                    getattr(client_existant, "prenom", "") or ""
                ).strip()

            erreurs = {}

            if not nom:
                erreurs["nom"] = (
                    "Nom obligatoire au paiement."
                )

            if not prenom:
                erreurs["prenom"] = (
                    "Prénom obligatoire au paiement."
                )

            if erreurs:
                raise serializers.ValidationError({
                    "client": erreurs
                })

        # ============================================
        # 5. RÉSULTAT
        # ============================================

        attrs["lignes"] = lignes_normalisees
        attrs["total_paiement"] = total_paiement
        attrs["paiement_avec_depot"] = paiement_avec_depot

        return attrs


    
class PaiementLigneResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    mode_paiement = serializers.CharField()
    mode_paiement_nom = serializers.CharField()
    montant_paye = serializers.DecimalField(max_digits=10, decimal_places=2)
    reference = serializers.CharField(allow_null=True, required=False)


# class PaiementFactureMultiModeResponseSerializer(serializers.Serializer):
#     message = serializers.CharField()
#     paiement_id = serializers.IntegerField()
#     facture_id = serializers.IntegerField()
#     numero_facture = serializers.CharField()
#     type_facture = serializers.CharField()
#     montant_total_facture = serializers.DecimalField(max_digits=12, decimal_places=2)
#     montant_operation = serializers.DecimalField(max_digits=12, decimal_places=2)
#     total_paye = serializers.DecimalField(max_digits=12, decimal_places=2)
#     reste_a_payer = serializers.DecimalField(max_digits=12, decimal_places=2)
#     status = serializers.CharField()
#     lignes = PaiementLigneResponseSerializer(many=True)
#     facture_pdf_url = serializers.URLField(required=False,allow_null=True,allow_blank=True,)
    


class FacturePaiementResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    uuid = serializers.UUIDField()
    numero_facture = serializers.CharField()
    type_facture = serializers.CharField()
    status = serializers.CharField()

    montant_total = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    total_paye = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    reste_a_payer = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

class ClientPaiementResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField(
        required=False,
        allow_null=True,
    )

    nom = serializers.CharField(
        required=False,
        allow_null=True,
    )

    prenom = serializers.CharField(
        required=False,
        allow_null=True,
    )

    telephone = serializers.CharField(
        required=False,
        allow_null=True,
    )
    

class StockAuditResponseSerializer(serializers.Serializer):
    created = serializers.IntegerField(default=0)
    already = serializers.IntegerField(default=0)
    lines_done = serializers.IntegerField(default=0)
    

class VentePaiementResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    uuid = serializers.UUIDField()
    numero_vente = serializers.CharField()
    montant_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    
    
class PaiementFactureMultiModeResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    paiement_id = serializers.IntegerField()

    vente = VentePaiementResponseSerializer(required=False, allow_null=True)
    facture = FacturePaiementResponseSerializer()
    client = ClientPaiementResponseSerializer(required=False, allow_null=True)
    lignes = PaiementLigneResponseSerializer(many=True)
    stock = StockAuditResponseSerializer()

    facture_pdf_url = serializers.URLField(required=False, allow_null=True)
    facture_download_url = serializers.URLField(required=False, allow_null=True)

# ==========================================================
# CLIENT INPUT
# ==========================================================

class ClientInputSerializer(serializers.Serializer):
    nom = serializers.CharField(max_length=100)
    prenom = serializers.CharField(max_length=100)
    telephone = serializers.CharField(
        max_length=15,
        required=False,
        allow_blank=True,
        allow_null=True,
    )


# ==========================================================
# UPDATE VENTE AVANT PAIEMENT
# ==========================================================
class UpdateVenteProduitItemSerializer(serializers.Serializer):
    """
    Modification d'une ligne de bijou avant paiement.

    Identification exacte :
    - produit_line_id : recherche manuelle ;
    - qr : scan du QR code ProduitLine.

    Un seul identifiant est autorisé.

    Règles :
    - Quantité strictement positive.
    - Prix de vente au gramme positif ou nul.
    - Remise positive ou nulle.
    - Le pourcentage occasion est géré par le backend.
    - Aucun mouvement SALE_OUT ici.
    """

    produit_line_id = serializers.IntegerField(
        required=False,
        min_value=1,
    )

    qr = serializers.CharField(
        required=False,
        allow_blank=False,
        trim_whitespace=True,
    )

    quantite = serializers.IntegerField(
        required=True,
        min_value=1,
    )

    prix_vente_grammes = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        default=Decimal("0.00"),
        min_value=Decimal("0.00"),
    )

    remise = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        default=Decimal("0.00"),
        min_value=Decimal("0.00"),
    )

    # ========================================================
    # VALIDATION
    # ========================================================

    def validate(self, attrs):
        attrs = super().validate(attrs)

        produit_line_id = attrs.get("produit_line_id")
        qr = attrs.get("qr")

        # 1. Identifiant obligatoire
        if produit_line_id is None and not qr:
            raise serializers.ValidationError({
                "produit_line": (
                    "Vous devez fournir produit_line_id ou qr."
                )
            })

        # 2. Un seul identifiant autorisé
        if produit_line_id is not None and qr:
            raise serializers.ValidationError({
                "produit_line": (
                    "Fournissez uniquement un identifiant : "
                    "produit_line_id ou qr."
                )
            })

        return attrs
    

class UpdateVenteProduitSerializer(serializers.Serializer):
    vendor_email = serializers.EmailField(required=False)

    client = ClientInputSerializer(required=False)

    produits = UpdateVenteProduitItemSerializer(many=True)

    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="Modification vente avant paiement",
    )

    def validate_produits(self, value):
        if not value:
            raise serializers.ValidationError(
                "La liste des produits ne peut pas être vide."
            )
        return value


# ==========================================================
# CANCEL PROFORMA
# ==========================================================

class CancelProformaVenteSerializer(serializers.Serializer):
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="Annulation vente proforma avant paiement",
    )


# ==========================================================
# RETOUR CLIENT APRÈS PAIEMENT
# ==========================================================

class RetourVenteProduitItemSerializer(serializers.Serializer):
    vente_ligne_id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1)


class RetourVenteProduitSerializer(serializers.Serializer):
    produits = RetourVenteProduitItemSerializer(
        many=True,
        required=False,
    )

    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="Retour client sous 72h",
    )

    def validate_produits(self, value):
        """
        Si produits est absent ou vide :
        retour complet.

        Si produits est fourni :
        retour partiel.
        """
        return value



