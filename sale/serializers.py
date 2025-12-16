from decimal import Decimal

from django.db import models
from django.db.models import Sum
from rest_framework import serializers

from store.models import Bijouterie, MarquePurete, Produit
from store.serializers import BijouterieSerializer, ProduitSerializer
from vendor.models import Vendor
from vendor.serializer import VendorSerializer

from .models import Client, Facture, Paiement, Vente, VenteProduit


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

# ----------------------------------------
# class VenteProduitSerializer(serializers.ModelSerializer):
#     slug = serializers.SlugField()
#     produit_id = serializers.PrimaryKeyRelatedField(
#         source="produit", queryset=Produit.objects.all(), write_only=True,
#     )
#     vendor_id = serializers.PrimaryKeyRelatedField(
#         source="vendor", queryset=Vendor.objects.all(),
#         write_only=True, required=False, allow_null=True,
#     )

#     produit = ProduitSerializer(read_only=True)
#     vendor  = VendorSerializer(read_only=True)

#     sous_total_ht = serializers.DecimalField(
#         max_digits=12, decimal_places=2, read_only=True, source="sous_total_prix_vente_ht"
#     )

#     class Meta:
#         model = VenteProduit
#         ref_name = "VenteProduitLine"
#         fields = [
#             "id",
#             "slug",
#             "produit_id", "vendor_id",
#             "produit", "vendor",
#             "quantite",
#             "prix_vente_grammes",
#             "remise", "autres", "tax",
#             "sous_total_ht",
#             "sous_total_prix_vente_ht",
#             "prix_ttc",
#         ]
#         read_only_fields = ("id", "sous_total_prix_vente_ht", "prix_ttc")
#         extra_kwargs = {
#             "quantite": {"min_value": 1},
#             "prix_vente_grammes": {"required": False},
#             "remise": {"required": False},
#             "autres": {"required": False},
#             "tax": {"required": False},
#         }

#     def validate(self, attrs):
#         # valeurs non négatives
#         for f in ("prix_vente_grammes", "remise", "autres", "tax"):
#             v = attrs.get(f)
#             if v is not None and v < 0:
#                 raise serializers.ValidationError({f: "Ne peut pas être négatif."})
#         q = attrs.get("quantite")
#         if q is not None and q < 1:
#             raise serializers.ValidationError({"quantite": "Doit être ≥ 1."})
#         return attrs

#     # Optionnel: cohérence slug <-> produit_id
#     def validate_slug(self, value):
#         # Si tu veux forcer cohérence, vérifie ici (ex: Produit.objects.filter(slug=value).exists())
#         return value

class VenteProduitSerializer(serializers.ModelSerializer):
    # 🔥 slug vient du produit, et uniquement en lecture
    slug = serializers.CharField(
        source="produit.slug",
        read_only=True,
    )

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
    vendor  = VendorSerializer(read_only=True)

    sous_total_ht = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
        source="sous_total_prix_vente_ht",
    )
    # marque = serializers.CharField(source="produit.marque.marque", read_only=True)
    # purete = serializers.CharField(source="produit.purete.purete", read_only=True)

    class Meta:
        model = VenteProduit
        ref_name = "VenteProduitLine"
        fields = [
            "id",
            "slug",                 # maintenant: produit.slug en lecture seule
            "produit_id", "vendor_id",
            "produit", "vendor",
            "quantite",
            "prix_vente_grammes",
            "remise", "autres", "tax",
            "sous_total_ht",
            "sous_total_prix_vente_ht",
            "prix_ttc",
        ]
        read_only_fields = ("id", "sous_total_prix_vente_ht", "prix_ttc")
        extra_kwargs = {
            "quantite": {"min_value": 1},
            "prix_vente_grammes": {"required": False},
            "remise": {"required": False},
            "autres": {"required": False},
            "tax": {"required": False},
        }

    def validate(self, attrs):
        # valeurs non négatives
        for f in ("prix_vente_grammes", "remise", "autres", "tax"):
            v = attrs.get(f)
            if v is not None and v < 0:
                raise serializers.ValidationError({f: "Ne peut pas être négatif."})
        q = attrs.get("quantite")
        if q is not None and q < 1:
            raise serializers.ValidationError({"quantite": "Doit être ≥ 1."})
        return attrs

    # validate_slug n’a plus vraiment de sens ici, car slug est read_only
    # Tu peux le supprimer, ou adapter la logique dans un serializer d’INPUT séparé.
# ----------------------------------------

# -----Serializer “in” pour la vue (payload)--
class ClientInSerializer(serializers.ModelSerializer):
    telephone = serializers.CharField(required=False, allow_blank=True)
    class Meta:
        model = Client
        fields = ["prenom", "nom", "telephone"]
        ref_name = "VenteClientIn"


class VenteListSerializer(serializers.ModelSerializer):
    client = serializers.SerializerMethodField()
    produits = VenteProduitSerializer(many=True, read_only=True)

    class Meta:
        model = Vente
        fields = ["id", "produits", "numero_vente", "created_at", "montant_total", "client"]
        ref_name = "VenteList_V1"

    def get_client(self, obj):
        c = getattr(obj, "client", None)
        return {"prenom": c.prenom, "nom": c.nom, "telephone": c.telephone} if c else None


class VenteProduitInSerializer(serializers.Serializer):
    slug = serializers.SlugField()
    quantite = serializers.IntegerField(min_value=1)
    prix_vente_grammes = serializers.DecimalField(max_digits=12,required=False,allow_null=True, decimal_places=2)
    remise = serializers.DecimalField(max_digits=12, required=False,allow_null=True, decimal_places=2, default=Decimal("0.00"),)
    autres = serializers.DecimalField(max_digits=12, required=False,allow_null=True, decimal_places=2, default=Decimal("0.00"),)
    tax    = serializers.DecimalField(max_digits=12, required=False,allow_null=True, decimal_places=2, default=Decimal("0.00"),)
    # Manager uniquement (selection du vendor)
    vendor_email = serializers.EmailField(required=False, allow_null=True, allow_blank=True,)

    class Meta:
        ref_name = "VenteProduitIn"

class VenteCreateInSerializer(serializers.Serializer):
    client   = ClientInSerializer()
    produits = VenteProduitInSerializer(many=True)

    class Meta:
        ref_name = "VenteCreateIn"
# -----End Serializer “in” pour la vue (payload)--

# -----Serializers de sortie avec HT/TTC, vendor et bijouterie-----------

class FactureSerializer(serializers.ModelSerializer):
    total_paye = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, coerce_to_string=True)
    reste_a_payer = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, coerce_to_string=True)
    remise_totale = serializers.SerializerMethodField()
    date_creation = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    client = serializers.SerializerMethodField()
    produits = serializers.SerializerMethodField()
    # paiements = PaiementSerializer(many=True, read_only=True)
    vente = serializers.SerializerMethodField()

    class Meta:
        model = Facture
        fields = [
            'vente', 'numero_facture', 'montant_total',
            'total_paye', 'remise_totale', 'reste_a_payer',
            'status', 'date_creation', 'client',
            'produits'
        ]

    def get_vente(self, obj):
        vente = obj.vente
        if vente:
            return {
                "id": vente.id,
                "numero_vente": vente.numero_vente
            }
        return None

    def get_client(self, obj):
        client = getattr(obj.vente, 'client', None)
        if client:
            return {
                "nom": client.nom,
                "prenom": client.prenom,
                "telephone": client.telephone
            }
        return None

    def get_remise_totale(self, obj):
        if obj.vente and hasattr(obj.vente, 'produits'):
            return float(sum(vp.remise or 0 for vp in obj.vente.produits.all()))
        return 0.0

    def get_produits(self, obj):
        if obj.vente and hasattr(obj.vente, 'produits'):
            return VenteProduitSerializer(obj.vente.produits.all(), many=True).data
        return []


class FactureListSerializer(serializers.ModelSerializer):
    total_paye = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, coerce_to_string=True)
    reste_a_payer = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, coerce_to_string=True)
    date_creation = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    client = serializers.SerializerMethodField()
    vente = serializers.SerializerMethodField()

    class Meta:
        model = Facture
        fields = [
            "vente",
            "numero_facture",
            "montant_total",
            "total_paye",
            "reste_a_payer",
            "status",
            "date_creation",
            "client",
        ]

    def get_vente(self, obj):
        v = obj.vente
        return {"id": v.id, "numero_vente": v.numero_vente} if v else None

    def get_client(self, obj):
        c = getattr(getattr(obj, "vente", None), "client", None)
        if c:
            return {"nom": c.nom, "prenom": c.prenom, "telephone": c.telephone}
        return None


class FactureDetailSerializer(FactureSerializer):
    factureList = FactureListSerializer(many=True, read_only=True)
    produits = serializers.SerializerMethodField()
    
    class Meta:
        model = Facture
        fields = [
            'factureList',
            'produits'
        ]
        
    def get_produits(self, obj):
        if obj.vente and hasattr(obj.vente, 'produits'):
            return VenteProduitSerializer(obj.vente.produits.all(), many=True).data
        return []


class VenteDetailSerializer(serializers.ModelSerializer):
    client = serializers.SerializerMethodField()
    produits = serializers.SerializerMethodField()
    vente = serializers.SerializerMethodField()
    facture = serializers.SerializerMethodField()
    total_remise = serializers.SerializerMethodField()
    total_ht = serializers.SerializerMethodField()
    total_ttc = serializers.SerializerMethodField()
    total_taxes = serializers.SerializerMethodField()
    total_autres = serializers.SerializerMethodField()
    totaux = serializers.SerializerMethodField()
    bijouterie = BijouterieSerializer(read_only=True)

    class Meta:
        model = Vente
        ref_name = "VenteDetailOut_V1"
        fields = [
            'id', 'client', 'produits', 'vente', 'facture', 'bijouterie',
            'montant_total', 'total_autres', 'total_ttc', 'total_remise', 'total_taxes', 'total_ht', 'totaux'
        ]

    def get_client(self, obj):
        c = obj.client
        return {"nom": c.nom, "prenom": c.prenom, "telephone": c.telephone} if c else None

    def get_produits(self, obj):
        # expose HT/TTC ligne + vendor
        data = []
        for p in obj.produits.select_related("produit", "vendor__user", "vendor__bijouterie"):
            data.append({
                "nom": p.produit.nom if p.produit else "Produit supprimé",
                "slug": getattr(p.produit, "slug", None),
                "quantite": p.quantite,
                "prix_vente_grammes": str(p.prix_vente_grammes),
                "sous_total_prix_vente_ht": str(p.sous_total_prix_vente_ht),
                "remise": str(p.remise),
                "autres": str(p.autres),
                "tax": str(p.tax),
                "prix_ttc": str(p.prix_ttc),
                "vendor": {
                    "id": getattr(p.vendor, "id", None),
                    "username": getattr(getattr(p.vendor, "user", None), "username", None),
                    "email": getattr(getattr(p.vendor, "user", None), "email", None),
                    "bijouterie": {
                        "id": getattr(getattr(p.vendor, "bijouterie", None), "id", None),
                        "nom": getattr(getattr(p.vendor, "bijouterie", None), "nom", None),
                        "telephone_portable_1": getattr(getattr(p.vendor, "bijouterie", None), "telephone_portable_1", None),
                        "telephone_fix": getattr(getattr(p.vendor, "bijouterie", None), "telephone_fix", None),
                        "nom_de_domaine": getattr(getattr(p.vendor, "bijouterie", None), "nom_de_domaine", None),
                        "adresse": getattr(getattr(p.vendor, "bijouterie", None), "adresse", None),
                    } if getattr(p.vendor, "bijouterie", None) else None
                } if p.vendor_id else None
            })
        return data

    def get_vente(self, obj):
        return {"id": obj.id, "numero_vente": obj.numero_vente}

    def get_facture(self, obj):
        f = getattr(obj, "facture_vente", None)
        if not f: return None
        return {
            "numero_facture": f.numero_facture,
            "montant_total": str(f.montant_total),
            "status": f.status,
            "date": f.date_creation,
            "bijouterie": {"id": f.bijouterie_id, "nom": getattr(f.bijouterie, "nom", None)} if f.bijouterie_id else None
        }

    from django.db.models import Sum
    def get_total_remise(self, obj): return str(obj.produits.aggregate(total=Sum('remise'))['total'] or 0)
    def get_total_ht(self, obj):     return str(obj.produits.aggregate(total=Sum('sous_total_prix_vente_ht'))['total'] or 0)
    def get_total_ttc(self, obj):    return str(obj.produits.aggregate(total=Sum('prix_ttc'))['total'] or 0)
    def get_total_taxes(self, obj):  return str(obj.produits.aggregate(total=Sum('tax'))['total'] or 0)
    def get_total_autres(self, obj): return str(obj.produits.aggregate(total=Sum('autres'))['total'] or 0)
    def get_totaux(self, obj):
        return {
            "total_ht": self.get_total_ht(obj),
            "total_ttc": self.get_total_ttc(obj),
            "total_taxes": self.get_total_taxes(obj),
            "total_remise": self.get_total_remise(obj),
            "total_autres": self.get_total_autres(obj),
            "montant_total": str(obj.montant_total),
        }

class VenteOutWrapperSerializer(serializers.Serializer):
    facture = FactureSerializer()
    vente   = VenteDetailSerializer()

    class Meta:
        ref_name = "VenteCreateOut"
# -----Serializers de sortie avec HT/TTC, vendor et bijouterie-----------


# PaiementSerializer pour l’input et l’output 
# (mieux d’avoir un serializer d’entrée dédié + validations de montant).
# serializer d’entrée, serializer de sortie, 
# et vue avec verrouillage transactionnel et contrôle anti-surpaiement

class PaiementCreateSerializer(serializers.Serializer):
    montant_paye = serializers.DecimalField(max_digits=10, decimal_places=2)
    mode_paiement = serializers.ChoiceField(
        choices=getattr(Paiement, "MODES", (("cash", "Cash"), ("mobile", "Mobile"))),
        default=getattr(Paiement, "MODE_CASH", "cash"),
        required=False,
    )
    
    def validate_montant_paye(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Le montant doit être strictement positif.")
        return value


class PaiementSerializer(serializers.ModelSerializer):
    numero_facture = serializers.CharField(source="facture.numero_facture", read_only=True)

    class Meta:
        model = Paiement
        fields = [
            "id", "facture", "numero_facture",
            "montant_paye", "mode_paiement", "date_paiement",
            "cashier", "created_by",
        ]
        read_only_fields = ["id", "numero_facture", "date_paiement", "cashier", "created_by"]

