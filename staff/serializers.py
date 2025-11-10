from django.contrib.auth import get_user_model
from rest_framework import serializers

from store.models import Bijouterie  # adapte
from vendor.models import Vendor

from .models import Cashier  # adapte si ton app diffère

User = get_user_model()

class AddStaffSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["vendor", "cashier"])
    email = serializers.EmailField()
    bijouterie_id = serializers.IntegerField(required=False)

    def validate(self, data):
        role = data["role"]
        if role == "vendor" and not data.get("bijouterie_id"):
            raise serializers.ValidationError({"bijouterie_id": "Requis pour un vendeur."})
        return data

    def create(self, validated):
        email = validated["email"].lower()

        user, _ = User.objects.get_or_create(
            email=email,
        )
        
        user.save()

        role = validated["role"]
        if role == "vendor":
            bijouterie = Bijouterie.objects.get(id=validated["bijouterie_id"])
            vendor, _ = Vendor.objects.get_or_create(user=user, defaults={"bijouterie": bijouterie})
            if vendor.bijouterie_id != bijouterie.id:
                vendor.bijouterie = bijouterie
                vendor.save()
            return {"user": user, "role": "vendor", "profile_id": vendor.id}

        # cashier
        cashier, _ = Cashier.objects.get_or_create(user=user)
        return {"user": user, "role": "cashier", "profile_id": cashier.id}

# ---------------------------  out-put ---------------------------
class BijouterieMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bijouterie
        fields = ["id", "nom", "adresse", "telephone"]  # adapte aux champs que tu as

class UserMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "telephone"]  # adapte

class VendorOutSerializer(serializers.ModelSerializer):
    user = UserMiniSerializer(read_only=True)
    bijouterie = BijouterieMiniSerializer(read_only=True)

    class Meta:
        model = Vendor
        fields = ["id", "verifie", "created_at", "user", "bijouterie"]
        
# ---------------------------  end out-put ---------------------------


# -------------------------------addd-----------------------------------
ROLE_ADMIN   = "admin"
ROLE_MANAGER = "manager"
ROLE_VENDOR  = "vendor"
ROLE_CASHIER = "cashier"

class AddStaffSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=[ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR, ROLE_CASHIER])
    email = serializers.EmailField()
    bijouterie_id = serializers.IntegerField(required=False)
    verifie = serializers.BooleanField(required=False, default=True)
    
# ---------------------------------End Add------------------------------