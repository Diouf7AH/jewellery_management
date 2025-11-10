from django.conf import settings
from django.db import models

from staff.models import StaffCore

# class Vendor(StaffCore):
#     class Meta:
#         verbose_name = "Vendeur"
#         verbose_name_plural = "Vendeurs"
#         ordering = ["-id"]

#     def __str__(self):
#         return f"Vendeur: {getattr(self.user, 'email', self.pk)}"

class Vendor(StaffCore):
    # Ici on fixe les reverse names EXACTS voulus pour Vendor
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="staff_vendor_profile",    # ✅ user.staff_vendor_profile
        related_query_name="vendor_profile",
    )
    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="vendors",                 # ✅ bijouterie.vendor.all()
        related_query_name="vendor",
    )

    @property
    def full_name(self) -> str:
        first = (getattr(self.user, "first_name", "") or "").strip()
        last  = (getattr(self.user, "last_name", "") or "").strip()
        return (f"{first} {last}".strip() or getattr(self.user, "username", "") or getattr(self.user, "email", "") or f"Vendeur #{self.id}")
    
    
    class Meta:
        verbose_name = "Vendor"
        verbose_name_plural = "Vendors"
        ordering = ["-id"]

    def __str__(self):
        return f"Vendor {getattr(self.user, 'username', self.user_id) if self.user else '#'+str(self.pk)}"

