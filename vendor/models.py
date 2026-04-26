from django.conf import settings
from django.db import models

from staff.models import StaffCore


class Vendor(StaffCore):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_vendor_profile",
        related_query_name="vendor_profile",
    )
    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vendors",
        related_query_name="vendor",
    )

    class Meta:
        verbose_name = "Vendeur"
        verbose_name_plural = "Vendeurs"
        ordering = ["-id"]

    def __str__(self):
        return self.full_name or f"Vendeur #{self.pk}"
    
    

