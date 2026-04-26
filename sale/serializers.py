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

from .models import (Facture, ModePaiement, Paiement, PaiementLigne, Vente,
                     VenteProduit)


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


# class VenteProduitSerializer(serializers.ModelSerializer):
#     slug = serializers.CharField(
#         source="produit.slug",
#         read_only=True,
#     )

#     produit_id = serializers.PrimaryKeyRelatedField(
#         source="produit",
#         queryset=Produit.objects.all(),
#         write_only=True,
#     )

#     vendor_id = serializers.PrimaryKeyRelatedField(
#         source="vendor",
#         queryset=Vendor.objects.all(),
#         write_only=True,
#         required=False,
#         allow_null=True,
#     )

#     produit = ProduitSerializer(read_only=True)
#     vendor = VendorSerializer(read_only=True)

#     sous_total_ht = serializers.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         read_only=True,
#         source="sous_total_prix_vente_ht",
#     )

#     prix_vente_grammes = serializers.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         required=False,
#         allow_null=True,
#     )
#     remise = serializers.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         required=False,
#         allow_null=True,
#     )
#     autres = serializers.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         required=False,
#         allow_null=True,
#     )
#     tax = serializers.DecimalField(max_digits=12,decimal_places=2,required=False,allow_null=True,)

#     class Meta:
#         model = VenteProduit
#         ref_name = "VenteProduitLine"
#         fields = [
#             "id",
#             "slug",
#             "produit_id",
#             "vendor_id",
#             "produit",
#             "vendor",
#             "quantite",
#             "prix_vente_grammes",
#             "remise",
#             "autres",
#             "tax",
#             "sous_total_ht",
#             "sous_total_prix_vente_ht",
#             "prix_ttc",
#         ]
#         read_only_fields = (
#             "id",
#             "sous_total_prix_vente_ht",
#             "prix_ttc",
#         )
#         extra_kwargs = {
#             "quantite": {"min_value": 1},
#         }

#     def to_internal_value(self, data):
#         data = data.copy()

#         for field in ("prix_vente_grammes", "remise", "autres", "tax"):
#             if field in data and data.get(field) == "":
#                 data[field] = None

#         return super().to_internal_value(data)

#     def validate(self, attrs):
#         for f in ("prix_vente_grammes", "remise", "autres", "tax"):
#             v = attrs.get(f)
#             if v is not None and v < 0:
#                 raise serializers.ValidationError({f: "Ne peut pas être négatif."})

#         q = attrs.get("quantite")
#         if q is not None and q < 1:
#             raise serializers.ValidationError({"quantite": "Doit être ≥ 1."})

#         return attrs


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


# class VenteProduitInSerializer(serializers.Serializer):
#     produit_id = serializers.IntegerField(min_value=1)
#     quantite = serializers.IntegerField(min_value=1)

#     prix_vente_grammes = serializers.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         required=False,
#         allow_null=True,
#     )
#     remise = serializers.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         required=False,
#         allow_null=True,
#         default=Decimal("0.00"),
#     )
#     autres = serializers.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         required=False,
#         allow_null=True,
#         default=Decimal("0.00"),
#     )
    

#     class Meta:
#         ref_name = "VenteProduitIn"

#     def to_internal_value(self, data):
#         data = data.copy()

#         # ✅ helper local
#         def clean_decimal_field(field_name, default_zero=False):
#             value = data.get(field_name, None)

#             if value is None:
#                 if default_zero:
#                     data[field_name] = "0.00"
#                 return

#             if isinstance(value, str):
#                 value = value.strip()

#                 if value == "":
#                     data[field_name] = "0.00" if default_zero else None
#                     return

#             data[field_name] = value

#         # prix_vente_grammes peut être absent/null
#         clean_decimal_field("prix_vente_grammes", default_zero=False)

#         # ceux-ci doivent retomber à 0 si vide
#         clean_decimal_field("remise", default_zero=True)
#         clean_decimal_field("autres", default_zero=True)
#         clean_decimal_field("tax", default_zero=True)

#         return super().to_internal_value(data)

#     def validate(self, attrs):
#         for field in ("prix_vente_grammes", "remise", "autres"):
#             value = attrs.get(field)
#             if value is not None and value < 0:
#                 raise serializers.ValidationError({
#                     field: "Ne peut pas être négatif."
#                 })
#         return attrs


class VenteProduitInSerializer(serializers.Serializer):
    produit_id = serializers.IntegerField(required=False)
    sku = serializers.CharField(required=False, allow_blank=True)
    qr = serializers.CharField(required=False, allow_blank=True)

    quantite = serializers.IntegerField(min_value=1)
    prix_vente_grammes = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False
    )
    remise = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        default=0
    )
    autres = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        default=0
    )

    def validate(self, attrs):
        produit_id = attrs.get("produit_id")
        sku = attrs.get("sku")
        qr = attrs.get("qr")

        if not produit_id and not sku and not qr:
            raise serializers.ValidationError(
                "Vous devez fournir produit_id, sku ou qr."
            )

        return attrs

# class VenteCreateInSerializer(serializers.Serializer):
#     """
#     - vendor  : vendor_email non utilisé
#     - manager/admin: vendor_email requis
#     """
#     vendor_email = serializers.EmailField(required=False)
#     client = ClientOptionalInSerializer(required=False)
#     produits = VenteProduitInSerializer(many=True)

#     class Meta:
#         ref_name = "VenteCreateIn"

#     def validate(self, attrs):
#         request = self.context.get("request")
#         role = ""
#         if request and request.user and request.user.is_authenticated:
#             from backend.roles import get_role_name
#             role = (get_role_name(request.user) or "").lower().strip()

#         if role in {"admin", "manager"} and not attrs.get("vendor_email"):
#             raise serializers.ValidationError({"vendor_email": "vendor_email est requis pour manager/admin."})

#         if not attrs.get("produits"):
#             raise serializers.ValidationError({"produits": "Au moins un produit est requis."})

#         return attrs


# class VenteCreateInSerializer(serializers.Serializer):
#     """
#     - vendor : vendor_email non utilisé
#     - manager/admin : vendor_email requis
#     """
#     vendor_email = serializers.EmailField(required=False)
#     client = ClientOptionalInSerializer(required=False)
#     produits = VenteProduitInSerializer(many=True)
#     produit_id = serializers.IntegerField(required=False)
#     sku = serializers.CharField(required=False, allow_blank=True)
#     qr = serializers.CharField(required=False, allow_blank=True)
    
#     class Meta:
#         ref_name = "VenteCreateIn"

#     def validate(self, attrs):
#         request = self.context.get("request")
#         role = ""

#         if request and request.user and request.user.is_authenticated:
#             from backend.roles import ROLE_ADMIN, ROLE_MANAGER, get_role_name
#             role = (get_role_name(request.user) or "").lower().strip()

#         if role in {ROLE_ADMIN, ROLE_MANAGER} and not attrs.get("vendor_email"):
#             raise serializers.ValidationError({
#                 "vendor_email": "vendor_email est requis pour manager/admin."
#             })

#         if not attrs.get("produits"):
#             raise serializers.ValidationError({
#                 "produits": "Au moins un produit est requis."
#             })

#         return attrs


class VenteCreateInSerializer(serializers.Serializer):
    """
    - vendor : vendor_email non utilisé
    - manager/admin : vendor_email requis
    """
    vendor_email = serializers.EmailField(required=False)
    client = ClientOptionalInSerializer(required=False)
    produits = VenteProduitInSerializer(many=True)

    class Meta:
        ref_name = "VenteCreateIn"

    def validate(self, attrs):
        request = self.context.get("request")
        role = ""

        if request and request.user and request.user.is_authenticated:
            from backend.roles import ROLE_ADMIN, ROLE_MANAGER, get_role_name
            role = (get_role_name(request.user) or "").lower().strip()

        if role in {ROLE_ADMIN, ROLE_MANAGER} and not attrs.get("vendor_email"):
            raise serializers.ValidationError({
                "vendor_email": "vendor_email est requis pour manager/admin."
            })

        if not attrs.get("produits"):
            raise serializers.ValidationError({
                "produits": "Au moins un produit est requis."
            })

        return attrs


class FactureSerializer(serializers.ModelSerializer):
    total_paye = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
    )
    reste_a_payer = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
    )

    remise_totale = serializers.SerializerMethodField()
    date_creation = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    client = serializers.SerializerMethodField()
    produits = serializers.SerializerMethodField()
    vente = serializers.SerializerMethodField()

    class Meta:
        model = Facture
        fields = [
            "vente",
            "numero_facture",
            "montant_ht",
            "taux_tva",
            "montant_tva",
            "montant_total",
            "total_paye",
            "remise_totale",
            "reste_a_payer",
            "status",
            "date_creation",
            "client",
            "produits",
        ]

    def get_vente(self, obj):
        vente = getattr(obj, "vente", None)
        if vente:
            return {
                "id": vente.id,
                "numero_vente": vente.numero_vente,
            }
        return None

    def get_client(self, obj):
        vente = getattr(obj, "vente", None)
        client = getattr(vente, "client", None) if vente else None
        if client:
            return {
                "nom": client.nom,
                "prenom": client.prenom,
                "telephone": client.telephone,
            }
        return None

    def get_remise_totale(self, obj):
        vente = getattr(obj, "vente", None)
        if vente:
            return float(sum((ligne.remise or Decimal("0.00")) for ligne in vente.lignes.all()))
        return 0.0

    def get_produits(self, obj):
        vente = getattr(obj, "vente", None)
        if vente:
            return VenteProduitSerializer(vente.lignes.all(), many=True).data
        return []


class FactureListSerializer(serializers.ModelSerializer):
    date_creation = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)

    total_paye = serializers.SerializerMethodField()
    reste_a_payer = serializers.SerializerMethodField()

    client = serializers.SerializerMethodField()
    vente = serializers.SerializerMethodField()
    produits = serializers.SerializerMethodField()

    class Meta:
        model = Facture
        fields = [
            "vente",
            "numero_facture",
            "montant_ht",
            "taux_tva",
            "montant_tva",
            "montant_total",
            "total_paye",
            "reste_a_payer",
            "status",
            "date_creation",
            "client",
            "produits",
        ]

    def get_vente(self, obj):
        v = getattr(obj, "vente", None)
        return {"id": v.id, "numero_vente": v.numero_vente} if v else None

    def get_client(self, obj):
        v = getattr(obj, "vente", None)
        c = getattr(v, "client", None) if v else None
        if not c:
            return None
        return {
            "nom": c.nom,
            "prenom": c.prenom,
            "telephone": c.telephone,
        }

    def get_total_paye(self, obj):
        return f"{Decimal(obj.total_paye):.2f}"

    def get_reste_a_payer(self, obj):
        return f"{Decimal(obj.reste_a_payer):.2f}"

    def get_produits(self, obj):
        vente = getattr(obj, "vente", None)
        if vente:
            return VenteProduitSerializer(vente.lignes.all(), many=True).data
        return []


class FactureDetailSerializer(FactureSerializer):
    produits = serializers.SerializerMethodField()

    class Meta:
        model = Facture
        fields = [
            "vente",
            "numero_facture",
            "montant_ht",
            "taux_tva",
            "montant_tva",
            "montant_total",
            "total_paye",
            "remise_totale",
            "reste_a_payer",
            "status",
            "date_creation",
            "client",
            "produits",
        ]

    def get_produits(self, obj):
        vente = getattr(obj, "vente", None)
        if vente:
            return VenteProduitSerializer(vente.lignes.all(), many=True).data
        return []




# ---------------------------------------------------
# Vente list
# ---------------------------------------------------
class VenteListSerializer(serializers.ModelSerializer):
    client = serializers.SerializerMethodField()
    produits = VenteProduitSerializer(source="lignes", many=True, read_only=True)

    class Meta:
        model = Vente
        fields = ["id", "produits", "numero_vente", "created_at", "montant_total", "client"]
        ref_name = "VenteList_V2"

    def get_client(self, obj):
        c = getattr(obj, "client", None)
        return {
            "prenom": c.prenom,
            "nom": c.nom,
            "telephone": c.telephone,
        } if c else None


# ---------------------------------------------------
# Vente detail
# ---------------------------------------------------
class VenteDetailSerializer(serializers.ModelSerializer):
    client = serializers.SerializerMethodField()
    produits = serializers.SerializerMethodField()
    vente = serializers.SerializerMethodField()
    facture = serializers.SerializerMethodField()
    total_remise = serializers.SerializerMethodField()
    total_ht = serializers.SerializerMethodField()
    total_autres = serializers.SerializerMethodField()
    total_ttc = serializers.SerializerMethodField()
    totaux = serializers.SerializerMethodField()
    bijouterie = BijouterieSerializer(read_only=True)

    class Meta:
        model = Vente
        ref_name = "VenteDetailOut_V2"
        fields = [
            "id",
            "client",
            "produits",
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

    def get_client(self, obj):
        c = getattr(obj, "client", None)
        if not c:
            return None
        return {
            "id": c.id,
            "nom": c.nom,
            "prenom": c.prenom,
            "telephone": c.telephone,
        }

    def get_produits(self, obj):
        qs = obj.lignes.select_related("produit", "vendor", "vendor__user").all().order_by("id")
        return VenteProduitSerializer(qs, many=True).data

    def get_vente(self, obj):
        return {
            "id": obj.id,
            "numero_vente": obj.numero_vente,
            "created_at": obj.created_at.strftime("%Y-%m-%d %H:%M:%S") if obj.created_at else None,
        }

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
            "taux_tva": str(facture.taux_tva),
            "montant_tva": str(facture.montant_tva),
            "montant_total": str(facture.montant_total),
            "total_paye": str(facture.total_paye),
            "reste_a_payer": str(facture.reste_a_payer),
        }

    def get_total_remise(self, obj):
        total = sum((ligne.remise or Decimal("0.00")) for ligne in obj.lignes.all())
        return str(total)

    def get_total_autres(self, obj):
        total = sum((ligne.autres or Decimal("0.00")) for ligne in obj.lignes.all())
        return str(total)

    def get_total_ht(self, obj):
        total = sum((ligne.montant_ht or Decimal("0.00")) for ligne in obj.lignes.all())
        return str(total)

    def get_total_ttc(self, obj):
        facture = getattr(obj, "facture_vente", None)
        if facture:
            return str(facture.montant_total)
        total = sum((ligne.montant_total or Decimal("0.00")) for ligne in obj.lignes.all())
        return str(total)

    def get_totaux(self, obj):
        facture = getattr(obj, "facture_vente", None)

        total_ht = sum((ligne.montant_ht or Decimal("0.00")) for ligne in obj.lignes.all())
        total_remise = sum((ligne.remise or Decimal("0.00")) for ligne in obj.lignes.all())
        total_autres = sum((ligne.autres or Decimal("0.00")) for ligne in obj.lignes.all())
        total_lignes = sum((ligne.montant_total or Decimal("0.00")) for ligne in obj.lignes.all())

        return {
            "montant_ht_lignes": str(total_ht),
            "remise_totale": str(total_remise),
            "autres_total": str(total_autres),
            "montant_total_lignes": str(total_lignes),
            "montant_ht_facture": str(facture.montant_ht) if facture else None,
            "taux_tva": str(facture.taux_tva) if facture else None,
            "montant_tva": str(facture.montant_tva) if facture else None,
            "montant_total_facture": str(facture.montant_total) if facture else None,
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


class PaiementModeItemSerializer(serializers.Serializer):
    mode_paiement = serializers.CharField()
    montant_paye = serializers.DecimalField(max_digits=10, decimal_places=2)
    reference = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_montant_paye(self, value):
        if value <= 0:
            raise serializers.ValidationError("Le montant doit être strictement positif.")
        return value


class PaiementMultiModeSerializer(serializers.Serializer):
    numero_facture = serializers.CharField()
    client = ClientInSerializer(required=True)
    lignes = PaiementModeItemSerializer(many=True)

    def validate(self, attrs):
        numero_facture = (attrs.get("numero_facture") or "").strip()
        lignes = attrs.get("lignes") or []

        try:
            facture = Facture.objects.select_related("vente", "vente__client").get(
                numero_facture__iexact=numero_facture
            )
        except Facture.DoesNotExist:
            raise serializers.ValidationError({"numero_facture": "Facture introuvable."})

        validate_facture_payable(facture)

        if not lignes:
            raise serializers.ValidationError({
                "lignes": "Au moins une ligne de paiement est requise."
            })

        total = Decimal("0.00")
        lignes_preparees = []

        for i, item in enumerate(lignes):
            code = (item.get("mode_paiement") or "").strip()

            try:
                mode = ModePaiement.objects.get(code=code, actif=True)
            except ModePaiement.DoesNotExist:
                raise serializers.ValidationError({
                    "lignes": {
                        i: {
                            "mode_paiement": f"Mode de paiement introuvable ou inactif : {code}"
                        }
                    }
                })

            montant_paye = item["montant_paye"]
            total += montant_paye

            lignes_preparees.append({
                "mode_obj": mode,
                "montant_paye": montant_paye,
                "reference": item.get("reference"),
            })

        if total <= Decimal("0.00"):
            raise serializers.ValidationError({
                "total": "Le total du paiement doit être strictement positif."
            })

        if total > facture.reste_a_payer:
            raise serializers.ValidationError({
                "total": (
                    f"Le total des lignes ({total}) dépasse le reste à payer "
                    f"({facture.reste_a_payer})."
                )
            })

        attrs["facture"] = facture
        attrs["lignes_preparees"] = lignes_preparees
        return attrs


class PaiementLigneResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    mode_paiement = serializers.CharField()
    mode_paiement_nom = serializers.CharField()
    montant_paye = serializers.DecimalField(max_digits=10, decimal_places=2)
    reference = serializers.CharField(allow_null=True, required=False)


class PaiementFactureMultiModeResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    paiement_id = serializers.IntegerField()
    facture_id = serializers.IntegerField()
    numero_facture = serializers.CharField()
    type_facture = serializers.CharField()
    montant_total_facture = serializers.DecimalField(max_digits=12, decimal_places=2)
    montant_operation = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_paye = serializers.DecimalField(max_digits=12, decimal_places=2)
    reste_a_payer = serializers.DecimalField(max_digits=12, decimal_places=2)
    status = serializers.CharField()
    lignes = PaiementLigneResponseSerializer(many=True)
    
    


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
    produit_id = serializers.IntegerField(required=False)
    slug = serializers.CharField(required=False, allow_blank=True)
    sku = serializers.CharField(required=False, allow_blank=True)
    qr = serializers.CharField(required=False, allow_blank=True)

    quantite = serializers.IntegerField(min_value=1)
    prix_vente_grammes = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False
    )
    remise = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        default=0
    )
    autres = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        default=0
    )

    def validate(self, attrs):
        if not attrs.get("produit_id") and not attrs.get("slug") and not attrs.get("sku") and not attrs.get("qr"):
            raise serializers.ValidationError(
                "Vous devez fournir produit_id, slug, sku ou qr."
            )
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



