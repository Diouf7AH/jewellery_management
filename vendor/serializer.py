from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.validators import EmailValidator
from rest_framework import serializers

from stock.models import VendorStock
from store.models import Bijouterie, Produit
from store.serializers import ProduitSerializer
from userauths.models import User

from .models import Vendor

User = get_user_model()
# -------------------------Create vendor----------------------
class CreateVendorSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)

    bijouterie_nom = serializers.SlugRelatedField(
        queryset=Bijouterie.objects.all(),
        slug_field="nom",
        required=True,
        help_text="Nom de la bijouterie (champ 'nom')"
    )

    verifie = serializers.BooleanField(required=False, default=True)

    def validate_email(self, value):
        return value.strip().lower()

# ------------------------------end create vendor-----------------------

# -----------------------------List endor--------------------------------
class VendorListSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)

    bijouterie_id = serializers.IntegerField(source="bijouterie.id", read_only=True, allow_null=True)
    bijouterie_nom = serializers.CharField(source="bijouterie.nom", read_only=True, allow_null=True)

    is_active = serializers.BooleanField(source="user.is_active", read_only=True)

    class Meta:
        model = Vendor
        fields = [
            "id",
            "user_id",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "verifie",
            "raison_desactivation",
            "bijouterie_id",
            "bijouterie_nom",
            "created_at",
        ]

# ------------------------------End List Vendor---------------------------

class VendorStatusInputSerializer(serializers.Serializer):
    verifie = serializers.BooleanField(help_text="True=activer, False=désactiver")
    class Meta:
        model = Vendor
        fields = ['verifie']  # ⚠️ Si tu veux activer/désactiver le vendeur (champ correct = verifie, pas active)

# # ------------------------------------Bijouterie to vendeur----------------------
class BijouterieToVendorLineInSerializer(serializers.Serializer):
    produit_line_id = serializers.IntegerField()
    quantite = serializers.IntegerField(min_value=1)

class BijouterieToVendorInSerializer(serializers.Serializer):
    vendor_id = serializers.IntegerField()  # 👈 canonique
    lignes = BijouterieToVendorLineInSerializer(many=True)
    note = serializers.CharField(required=False, allow_blank=True)
# ----------------------------------End bijouterie to vendeur ---------------


class VendorSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = Vendor
        fields = ['email', 'bijouterie', 'verifie']


class VendorUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)

    bijouterie_id = serializers.IntegerField(required=False, min_value=1)
    bijouterie_nom = serializers.CharField(required=False, allow_blank=True)

    verifie = serializers.BooleanField(required=False)
    raison_desactivation = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_email(self, value):
        email = (value or "").strip().lower()
        user_id = self.context.get("user_id")

        qs = User.objects.filter(email__iexact=email)
        if user_id:
            qs = qs.exclude(id=user_id)
        if qs.exists():
            raise serializers.ValidationError("Cet email est déjà utilisé par un autre utilisateur.")
        return email

    def validate_raison_desactivation(self, value):
        if value is None:
            return None
        v = str(value).strip()
        return v or None

    def validate(self, attrs):
        """
        - Si role=manager => interdit de modifier bijouterie_id / bijouterie_nom
        - Si bijouterie_id + bijouterie_nom => bijouterie_id gagne
        """
        role = (self.context.get("role") or "").lower()

        if role == "manager" and ("bijouterie_id" in attrs or "bijouterie_nom" in attrs):
            raise serializers.ValidationError(
                {"bijouterie": "Seul un admin peut changer la bijouterie d’un vendeur."}
            )

        # priorité à bijouterie_id
        if "bijouterie_id" in attrs and "bijouterie_nom" in attrs:
            attrs.pop("bijouterie_nom", None)

        # transformer bijouterie_id -> instance (si présent, admin uniquement)
        if "bijouterie_id" in attrs:
            bj = Bijouterie.objects.filter(id=attrs["bijouterie_id"]).first()
            if not bj:
                raise serializers.ValidationError({"bijouterie_id": "Bijouterie introuvable."})
            attrs["bijouterie_id"] = bj  # instance

        # transformer bijouterie_nom -> instance (si présent, admin uniquement)
        if "bijouterie_nom" in attrs:
            v = (attrs["bijouterie_nom"] or "").strip()
            if not v:
                attrs["bijouterie_nom"] = None
            else:
                bj = Bijouterie.objects.filter(nom__iexact=v).first()
                if not bj:
                    raise serializers.ValidationError({"bijouterie_nom": "Aucune bijouterie trouvée avec ce nom."})
                attrs["bijouterie_nom"] = bj  # instance

        return attrs
    
# # ----- Lecture -----



class VendorReadSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.SerializerMethodField()
    bijouterie_id = serializers.IntegerField(source="bijouterie.id", read_only=True)
    bijouterie_nom = serializers.CharField(source="bijouterie.nom", read_only=True)

    class Meta:
        model = Vendor
        fields = [
            "id",
            "email",
            "full_name",
            "bijouterie_id",
            "bijouterie_nom",
            "verifie",          # <-- remplace 'active' par 'verifie'
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "email", "bijouterie_id", "bijouterie_nom", "created_at", "updated_at"]

    def get_full_name(self, obj):
        u = getattr(obj, "user", None)
        if not u:
            return ""
        first = (u.first_name or "").strip()
        last  = (u.last_name or "").strip()
        return (first + " " + last).strip() or (u.username or u.email or "")
    


# -------------- List Produit for vendor-----------------------------
# class VendorProduitGroupedSerializer(serializers.Serializer):
#     produit_id = serializers.IntegerField()
#     produit_nom = serializers.CharField()
#     produit_sku = serializers.CharField(allow_null=True, required=False)

#     quantite_allouee = serializers.IntegerField()
#     quantite_vendue = serializers.IntegerField()
#     quantite_disponible = serializers.IntegerField()
#     quantite_lot = serializers.IntegerField()

# class VendorProduitGroupedSerializer(serializers.Serializer):
#     produit_id = serializers.IntegerField()
#     produit_nom = serializers.CharField()
#     produit_sku = serializers.CharField(allow_null=True, required=False)

#     # ✅ STOCK (optionnels si scope=sales)
#     quantite_allouee = serializers.IntegerField(required=False)
#     quantite_vendue = serializers.IntegerField(required=False)
#     quantite_disponible = serializers.IntegerField(required=False)
#     quantite_lot = serializers.IntegerField(required=False)

#     # ✅ SALES (optionnel si scope=stock)
#     vendue_periode = serializers.IntegerField(required=False)


# class VendorProduitLotSerializer(serializers.ModelSerializer):
#     produit_id = serializers.IntegerField(source="produit_line.produit.id", read_only=True)
#     produit_nom = serializers.CharField(source="produit_line.produit.nom", read_only=True)
#     produit_sku = serializers.CharField(source="produit_line.produit.sku", read_only=True)

#     produit_line_id = serializers.IntegerField(source="produit_line.id", read_only=True)
#     lot_id = serializers.IntegerField(source="produit_line.lot.id", read_only=True)
#     lot_received_at = serializers.DateTimeField(source="produit_line.lot.received_at", read_only=True)
#     quantite_lot = serializers.IntegerField(source="produit_line.quantite", read_only=True)
    
#     quantite_disponible = serializers.SerializerMethodField()

#     def get_quantite_disponible(self, obj):
#         return int((obj.quantite_allouee or 0) - (obj.quantite_vendue or 0))

#     class Meta:
#         model = VendorStock
#         fields = [
#             "id",
#             "produit_id", "produit_nom", "produit_sku",
#             "produit_line_id", "lot_id", "lot_received_at",
#             "quantite_allouee", "quantite_vendue", "quantite_disponible",
#             "quantite_lot",
#         ]
# ---------------- End List Produit for vendor ----------------------







class VendorStockListSerializer(serializers.ModelSerializer):
    # --- Vendor ---
    vendor_id = serializers.IntegerField(source="vendor.id", read_only=True)
    vendor_nom = serializers.SerializerMethodField()
    vendor_email = serializers.EmailField(source="vendor.user.email", read_only=True, default=None)

    # --- Bijouterie ---
    bijouterie_id = serializers.IntegerField(source="bijouterie.id", read_only=True)
    bijouterie_nom = serializers.CharField(source="bijouterie.nom", read_only=True, default=None)

    # --- ProduitLine / Lot / Produit ---
    produit_line_id = serializers.IntegerField(source="produit_line.id", read_only=True)
    lot_id = serializers.IntegerField(source="produit_line.lot.id", read_only=True)
    lot_code = serializers.CharField(source="produit_line.lot.lot_code", read_only=True, default=None)
    received_at = serializers.DateTimeField(source="produit_line.lot.received_at", read_only=True)

    produit_id = serializers.IntegerField(source="produit_line.produit.id", read_only=True)
    produit_nom = serializers.CharField(source="produit_line.produit.nom", read_only=True, default=None)
    produit_sku = serializers.CharField(source="produit_line.produit.sku", read_only=True, default=None)
    categorie_nom = serializers.CharField(source="produit_line.produit.categorie.nom", read_only=True, default=None)
    marque_nom = serializers.CharField(source="produit_line.produit.marque.marque", read_only=True, default=None)
    purete_nom = serializers.CharField(source="produit_line.produit.purete.purete", read_only=True, default=None)

    # --- Calcul dispo ---
    quantite_disponible = serializers.SerializerMethodField()

    class Meta:
        model = VendorStock
        fields = [
            "id",
            "bijouterie_id", "bijouterie_nom",
            "vendor_id", "vendor_nom", "vendor_email",
            "produit_line_id", "lot_id", "lot_code", "received_at",
            "produit_id", "produit_nom", "produit_sku",
            "categorie_nom", "marque_nom", "purete_nom",
            "quantite_allouee", "quantite_vendue", "quantite_disponible",
            "created_at", "updated_at",
        ]

    def get_quantite_disponible(self, obj):
        return max(0, int(obj.quantite_allouee or 0) - int(obj.quantite_vendue or 0))

    def get_vendor_nom(self, obj):
        # adapte selon ton modèle Vendor (prenom/nom ?)
        u = getattr(obj.vendor, "user", None)
        if not u:
            return None
        full = " ".join(x for x in [getattr(u, "first_name", None), getattr(u, "last_name", None)] if x)
        return full or getattr(u, "username", None) or getattr(u, "email", None)




class VendorStockSummaryByVendorSerializer(serializers.Serializer):
    vendor_id = serializers.IntegerField()
    vendor_email = serializers.EmailField(allow_null=True)
    vendor_nom = serializers.CharField(allow_null=True)

    bijouterie_id = serializers.IntegerField()
    bijouterie_nom = serializers.CharField(allow_null=True)

    lignes = serializers.IntegerField()
    allouee = serializers.IntegerField()
    vendue = serializers.IntegerField()
    disponible = serializers.IntegerField()
    produits_distincts = serializers.IntegerField()


class VendorStockSummaryByProduitSerializer(serializers.Serializer):
    bijouterie_id = serializers.IntegerField()
    bijouterie_nom = serializers.CharField(allow_null=True)

    produit_id = serializers.IntegerField()
    produit_nom = serializers.CharField(allow_null=True)
    produit_sku = serializers.CharField(allow_null=True)

    lignes = serializers.IntegerField(min_value=0)
    allouee = serializers.IntegerField(min_value=0)
    vendue = serializers.IntegerField(min_value=0)
    disponible = serializers.IntegerField(min_value=0)
    vendors_distincts = serializers.IntegerField(min_value=0)
    

class VendorStockSummaryByProduitSerializer(serializers.Serializer):
    bijouterie_id = serializers.IntegerField()
    bijouterie_nom = serializers.CharField(allow_null=True)

    produit_id = serializers.IntegerField()
    produit_nom = serializers.CharField(allow_null=True)
    produit_sku = serializers.CharField(allow_null=True)

    lignes = serializers.IntegerField(min_value=0)
    allouee = serializers.IntegerField(min_value=0)
    vendue = serializers.IntegerField(min_value=0)
    disponible = serializers.IntegerField(min_value=0)
    vendors_distincts = serializers.IntegerField(min_value=0)  
    

class VendorStockSummaryByVendorProduitSerializer(serializers.Serializer):
    bijouterie_id = serializers.IntegerField()
    bijouterie_nom = serializers.CharField(allow_null=True)

    vendor_id = serializers.IntegerField()
    vendor_email = serializers.EmailField(allow_null=True)
    vendor_nom = serializers.CharField(allow_null=True)

    produit_id = serializers.IntegerField()
    produit_nom = serializers.CharField(allow_null=True)
    produit_sku = serializers.CharField(allow_null=True)

    lignes = serializers.IntegerField(min_value=0)
    allouee = serializers.IntegerField(min_value=0)
    vendue = serializers.IntegerField(min_value=0)
    disponible = serializers.IntegerField(min_value=0)



class VendorDashboardKpiSerializer(serializers.Serializer):
    ventes_count = serializers.IntegerField(min_value=0)


class VendorDashboardSeriesPointSerializer(serializers.Serializer):
    period = serializers.CharField()  # "YYYY-MM-DD" ou "YYYY-MM"
    ventes_count = serializers.IntegerField(min_value=0)


class VendorDashboardSeriesSerializer(serializers.Serializer):
    granularity = serializers.ChoiceField(choices=["day", "month"])
    count = serializers.IntegerField(min_value=0)
    results = VendorDashboardSeriesPointSerializer(many=True)
    