from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.validators import EmailValidator
from rest_framework import serializers

from staff.models import Cashier
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
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    bijouterie_id = serializers.IntegerField(source="bijouterie.id", read_only=True)
    bijouterie_nom = serializers.CharField(source="bijouterie.nom", read_only=True)

    class Meta:
        model = Vendor
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
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

# class VendorProduitSerializer(serializers.ModelSerializer):
#     # produit = ProduitSerializer()

#     class Meta:
#         model = VendorProduit
#         fields = ['vendor', 'produit', 'quantite']

# class VendorProduitSerializer(serializers.ModelSerializer):
#     produit = ProduitSerializer(read_only=True)  # Affichage complet du produit
#     produit_id = serializers.PrimaryKeyRelatedField(
#         queryset=Produit.objects.all(),
#         source='produit',
#         write_only=True
#     )
#     vendor = serializers.SerializerMethodField()  # 👈 lecture seule, affiche l'ID de l'utilisateur

#     class Meta:
#         model = VendorProduit
#         fields = ['vendor', 'produit', 'produit_id', 'quantite']

#     def get_vendor(self, obj):
#         return obj.vendor.user.id if obj.vendor and obj.vendor.user else None



class VendorSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = Vendor
        fields = ['email', 'bijouterie', 'verifie']


class VendorUpdateSerializer(serializers.Serializer):
    """
    Serializer pour mettre à jour un vendeur:
      - email (User)
      - bijouterie_nom (-> bijouterie)
      - verifie, raison_desactivation (Vendor)
    """
    email = serializers.EmailField(required=False)
    bijouterie_nom = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Nom de la bijouterie à rattacher (optionnel)."
    )
    verifie = serializers.BooleanField(required=False)
    raison_desactivation = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True
    )

    def validate_email(self, value):
        """
        Vérifie que l’email n’est pas utilisé par un autre utilisateur.
        """
        email = value.strip().lower()
        user_id = self.context.get("user_id")  # on passe ça depuis la vue

        qs = User.objects.filter(email=email)
        if user_id:
            qs = qs.exclude(id=user_id)
        if qs.exists():
            raise serializers.ValidationError("Cet email est déjà utilisé par un autre utilisateur.")
        return email

    def validate_bijouterie_nom(self, value):
        """
        On reçoit le nom de la bijouterie, on le transforme en instance.
        Si string vide → None (pas de changement ou décrochage explicite).
        """
        value = (value or "").strip()
        if not value:
            return None
        try:
            bj = Bijouterie.objects.get(nom=value)
        except Bijouterie.DoesNotExist:
            raise serializers.ValidationError("Aucune bijouterie trouvée avec ce nom.")
        return bj
    


# # class VendorSerializer(serializers.ModelSerializer):
# #     email = serializers.EmailField(source='user.email', read_only=True)
# #     bijouterie = serializers.SerializerMethodField()  # ✅ personnalisation

# #     class Meta:
# #         model = Vendor
# #         fields = '__all__'

# #     def get_bijouterie(self, obj):
# #         if obj.bijouterie:
# #             return {
# #                 "id": obj.bijouterie.id,
# #                 "nom": obj.bijouterie.nom
# #             }
# #         return None

# Pour l'affichage du swagger
# # avoir tous les attributs du vendeur dans swagger
# class CreateVendorSerializer(serializers.Serializer):
#     email = serializers.EmailField(required=True)
#     # username = serializers.CharField(required=False)
#     # phone = serializers.CharField(required=False)
#     bijouterie = serializers.IntegerField(required=True)
#     description = serializers.CharField(required=False, allow_blank=True)

# class CreateVendorSerializer(serializers.Serializer):
#     email = serializers.EmailField()
#     bijouterie = serializers.CharField()
#     # description = serializers.CharField(required=False, allow_blank=True)

#     def validate_bijouterie(self, value):
#         from store.models import Bijouterie
#         try:
#             return Bijouterie.objects.get(nom__iexact=value.strip())
#         except Bijouterie.DoesNotExist:
#             raise serializers.ValidationError("Bijouterie introuvable.")

# # class CreateVendorSerializer(serializers.Serializer):
# #     email = serializers.EmailField()
# #     bijouterie_id = serializers.IntegerField()
# #     description = serializers.CharField(required=False, allow_blank=True)

# #     def validate_bijouterie_id(self, value):
# #         from store.models import Bijouterie
# #         if not Bijouterie.objects.filter(id=value).exists():
# #             raise serializers.ValidationError("Bijouterie introuvable.")
# #         return value


# class UserListeSerializer(serializers.ModelSerializer):
#     full_name = serializers.SerializerMethodField()

#     class Meta:
#         model = User
#         fields = ['id', 'email', 'first_name', 'last_name', 'full_name']

#     def get_full_name(self, obj):
#         return f"{obj.first_name} {obj.last_name}"


# class VendorDashboardSerializer(serializers.Serializer):
#     # Infos du vendeur
#     user_id = serializers.IntegerField()
#     email = serializers.EmailField()
#     first_name = serializers.CharField()
#     last_name = serializers.CharField()
#     bijouterie = serializers.CharField()

#     # Produits associés
#     produits = VendorProduitSerializer(many=True)

#     # Statistiques globales
#     total_produits = serializers.IntegerField()
#     total_ventes = serializers.IntegerField()
#     quantite_totale_vendue = serializers.IntegerField()
#     montant_total_ventes = serializers.DecimalField(max_digits=12, decimal_places=2)
#     stock_restant = serializers.IntegerField()

#     # Statistiques groupées (par mois, semaine, etc.)
#     stats_groupées = serializers.ListField(
#         child=serializers.DictField(), required=False
#     )

#     # Top produits
#     top_produits = serializers.ListField(
#         child=serializers.DictField(), required=False
#     )

#     mode_groupement = serializers.CharField(required=False)

# # ----- Lecture -----

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "slug", "email", "username", "first_name", "last_name", "telephone"]


class BijouterieMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bijouterie
        fields = ["id", "nom"]

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
    


# # ----- Écriture / Update -----
# # Permet de mettre à jour Vendor + quelques champs du User.

# class VendorUpdateSerializer(serializers.ModelSerializer):
#     # lier/délier la bijouterie par id
#     bijouterie_id = serializers.PrimaryKeyRelatedField(
#         source="bijouterie",
#         queryset=Bijouterie.objects.all(),
#         write_only=True,
#         required=False,
#         allow_null=True,
#     )
#     # patch “user” minimal : email/username/prénom/nom/téléphone
#     user = serializers.DictField(write_only=True, required=False)

#     class Meta:
#         model = Vendor
#         fields = ["verifie", "raison_desactivation", "bijouterie_id", "user"]

#     def validate_user(self, data):
#         """Contrôles simples d’unicité (si fournis)."""
#         user = getattr(self.instance, "user", None)
#         if not user:
#             return data

#         email = data.get("email")
#         if email and User.objects.exclude(pk=user.pk).filter(email__iexact=email).exists():
#             raise serializers.ValidationError({"email": "Cet email est déjà utilisé."})

#         username = data.get("username")
#         if username and User.objects.exclude(pk=user.pk).filter(username__iexact=username).exists():
#             raise serializers.ValidationError({"username": "Ce nom d’utilisateur est déjà utilisé."})

#         telephone = data.get("telephone")
#         if telephone and User.objects.exclude(pk=user.pk).filter(telephone__iexact=telephone).exists():
#             raise serializers.ValidationError({"telephone": "Ce téléphone est déjà utilisé."})

#         return data

#     def update(self, instance, validated_data):
#         # update Vendor
#         bijouterie = validated_data.pop("bijouterie", serializers.empty)
#         if bijouterie is not serializers.empty:
#             instance.bijouterie = bijouterie

#         instance.verifie = validated_data.get("verifie", instance.verifie)
#         instance.raison_desactivation = validated_data.get("raison_desactivation", instance.raison_desactivation)
#         instance.save()

#         # update User (optionnel)
#         user_data = validated_data.pop("user", {})
#         u = instance.user
#         if u and user_data:
#             for field in ("email", "username", "first_name", "last_name", "telephone"):
#                 if field in user_data:
#                     setattr(u, field, user_data[field])
#             u.save()

#         return instance


class CashierSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = Cashier
        fields = ['email', 'bijouterie', 'verifie']


class CashierReadSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    slug = serializers.CharField(source="user.slug", read_only=True)
    bijouterie = BijouterieMiniSerializer(read_only=True)

    # bonus "plats" pour le front
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_full_name = serializers.SerializerMethodField(read_only=True)
    user_telephone = serializers.CharField(source="user.telephone", read_only=True)

    # total encaissé (annoté dans la vue)
    total_encaisse = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True, required=False)

    class Meta:
        model = Cashier
        fields = [
            "id",
            "slug",
            "user", "user_email", "user_full_name", "user_telephone",
            "bijouterie",
            "verifie", "raison_desactivation",
            "total_encaisse",
        ]

    def get_user_full_name(self, obj):
        u = obj.user
        if not u:
            return ""
        fn = (u.first_name or "").strip()
        ln = (u.last_name or "").strip()
        return (f"{fn} {ln}").strip() or (u.username or u.email or "")


class CashierUpdateSerializer(serializers.ModelSerializer):
    # lier/délier la bijouterie par id
    bijouterie_id = serializers.PrimaryKeyRelatedField(
        source="bijouterie",
        queryset=Bijouterie.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )
    # patch des champs basiques du user
    user = serializers.DictField(write_only=True, required=False)

    class Meta:
        model = Cashier
        fields = ["verifie", "raison_desactivation", "bijouterie_id", "user"]

    def validate_user(self, data):
        user = getattr(self.instance, "user", None)
        if not user:
            return data

        email = data.get("email")
        if email and User.objects.exclude(pk=user.pk).filter(email__iexact=email).exists():
            raise serializers.ValidationError({"email": "Cet email est déjà utilisé."})

        username = data.get("username")
        if username and User.objects.exclude(pk=user.pk).filter(username__iexact=username).exists():
            raise serializers.ValidationError({"username": "Ce nom d’utilisateur est déjà utilisé."})

        telephone = data.get("telephone")
        if telephone and User.objects.exclude(pk=user.pk).filter(telephone__iexact=telephone).exists():
            raise serializers.ValidationError({"telephone": "Ce téléphone est déjà utilisé."})

        return data

    def update(self, instance, validated_data):
        # Cashier
        bijouterie = validated_data.pop("bijouterie", serializers.empty)
        if bijouterie is not serializers.empty:
            instance.bijouterie = bijouterie

        instance.verifie = validated_data.get("verifie", instance.verifie)
        instance.raison_desactivation = validated_data.get("raison_desactivation", instance.raison_desactivation)
        instance.save()

        # User
        user_data = validated_data.pop("user", {})
        u = instance.user
        if u and user_data:
            for field in ("email", "username", "first_name", "last_name", "telephone"):
                if field in user_data:
                    setattr(u, field, user_data[field])
            u.save()

        return instance


# -------------- List Produit for vendor-----------------------------
# class VendorProduitGroupedSerializer(serializers.Serializer):
#     produit_id = serializers.IntegerField()
#     produit_nom = serializers.CharField()
#     produit_sku = serializers.CharField(allow_null=True, required=False)

#     quantite_allouee = serializers.IntegerField()
#     quantite_vendue = serializers.IntegerField()
#     quantite_disponible = serializers.IntegerField()
#     quantite_lot = serializers.IntegerField()

class VendorProduitGroupedSerializer(serializers.Serializer):
    produit_id = serializers.IntegerField()
    produit_nom = serializers.CharField()
    produit_sku = serializers.CharField(allow_null=True, required=False)

    # ✅ STOCK (optionnels si scope=sales)
    quantite_allouee = serializers.IntegerField(required=False)
    quantite_vendue = serializers.IntegerField(required=False)
    quantite_disponible = serializers.IntegerField(required=False)
    quantite_lot = serializers.IntegerField(required=False)

    # ✅ SALES (optionnel si scope=stock)
    vendue_periode = serializers.IntegerField(required=False)


class VendorProduitLotSerializer(serializers.ModelSerializer):
    produit_id = serializers.IntegerField(source="produit_line.produit.id", read_only=True)
    produit_nom = serializers.CharField(source="produit_line.produit.nom", read_only=True)
    produit_sku = serializers.CharField(source="produit_line.produit.sku", read_only=True)

    produit_line_id = serializers.IntegerField(source="produit_line.id", read_only=True)
    lot_id = serializers.IntegerField(source="produit_line.lot.id", read_only=True)
    lot_received_at = serializers.DateTimeField(source="produit_line.lot.received_at", read_only=True)
    quantite_lot = serializers.IntegerField(source="produit_line.quantite", read_only=True)
    
    quantite_disponible = serializers.SerializerMethodField()

    def get_quantite_disponible(self, obj):
        return int((obj.quantite_allouee or 0) - (obj.quantite_vendue or 0))

    class Meta:
        model = VendorStock
        fields = [
            "id",
            "produit_id", "produit_nom", "produit_sku",
            "produit_line_id", "lot_id", "lot_received_at",
            "quantite_allouee", "quantite_vendue", "quantite_disponible",
            "quantite_lot",
        ]
# ---------------- End List Produit for vendor ----------------------