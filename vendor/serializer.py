from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.validators import EmailValidator
from rest_framework import serializers

from staff.models import Cashier
from store.models import Bijouterie, Produit
from store.serializers import ProduitSerializer
from userauths.models import User

from .models import Vendor

User = get_user_model()

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
        fields = ['email', 'bijouterie', 'active', 'description', 'verifie', 'raison_desactivation']

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


class CreateStaffMemberSerializer(serializers.Serializer):
    email = serializers.EmailField(
        validators=[EmailValidator()],
        help_text="Email de l’utilisateur existant"
    )
    bijouterie = serializers.PrimaryKeyRelatedField(
        queryset=Bijouterie.objects.all(),
        help_text="ID de la bijouterie valide"
    )
    role = serializers.ChoiceField(
        choices=[("vendor", "Vendor"), ("cashier", "Cashier")],
        help_text="Type de staff à créer"
    )
    # description = serializers.CharField(
    #     required=False, allow_blank=True, max_length=255
    # )

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
    user = UserSerializer(read_only=True)
    slug = serializers.CharField(source="user.slug", read_only=True)
    bijouterie = BijouterieMiniSerializer(read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_full_name = serializers.SerializerMethodField(read_only=True)
    user_telephone = serializers.CharField(source="user.telephone", read_only=True)

    class Meta:
        model = Vendor
        fields = [
            "id",
            "slug",
            "user", "user_email", "user_full_name", "user_telephone",
            "bijouterie",
            "verifie", "raison_desactivation",
        ]

    def get_user_full_name(self, obj):
        u = obj.user
        if not u:
            return ""
        fn = (u.first_name or "").strip()
        ln = (u.last_name or "").strip()
        return (f"{fn} {ln}").strip() or (u.username or u.email or "")


# # ----- Écriture / Update -----
# # Permet de mettre à jour Vendor + quelques champs du User.

class VendorUpdateSerializer(serializers.ModelSerializer):
    # lier/délier la bijouterie par id
    bijouterie_id = serializers.PrimaryKeyRelatedField(
        source="bijouterie",
        queryset=Bijouterie.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )
    # patch “user” minimal : email/username/prénom/nom/téléphone
    user = serializers.DictField(write_only=True, required=False)

    class Meta:
        model = Vendor
        fields = ["verifie", "raison_desactivation", "bijouterie_id", "user"]

    def validate_user(self, data):
        """Contrôles simples d’unicité (si fournis)."""
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
        # update Vendor
        bijouterie = validated_data.pop("bijouterie", serializers.empty)
        if bijouterie is not serializers.empty:
            instance.bijouterie = bijouterie

        instance.verifie = validated_data.get("verifie", instance.verifie)
        instance.raison_desactivation = validated_data.get("raison_desactivation", instance.raison_desactivation)
        instance.save()

        # update User (optionnel)
        user_data = validated_data.pop("user", {})
        u = instance.user
        if u and user_data:
            for field in ("email", "username", "first_name", "last_name", "telephone"):
                if field in user_data:
                    setattr(u, field, user_data[field])
            u.save()

        return instance


class CashierSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    class Meta:
        model = Cashier
        fields = ["id", "user", "verifie", "raison_desactivation"]


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

