from django.contrib.auth import get_user_model

from vendor.models import Vendor


def get_or_create_ecommerce_vendor(*, bijouterie):
    User = get_user_model()

    email = f"ecommerce-{bijouterie.id}@rio-gold.com"
    username = f"ecommerce_{bijouterie.id}"

    user, _ = User.objects.get_or_create(
        email=email,
        defaults={
            "username": username,
            "is_active": True,
        }
    )

    vendor, _ = Vendor.objects.get_or_create(
        user=user,
        defaults={
            "bijouterie": bijouterie,
            "verifie": True,
        }
    )

    if vendor.bijouterie_id != bijouterie.id:
        vendor.bijouterie = bijouterie
        vendor.verifie = True
        vendor.save(update_fields=["bijouterie", "verifie", "updated_at"])

    return vendor

