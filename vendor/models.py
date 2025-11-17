# vendor/models.py
from django.conf import settings
from django.db import models

from staff.models import StaffCore


class Vendor(StaffCore):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="staff_vendor_profile",
        related_query_name="vendor_profile",
    )
    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="vendors",
        related_query_name="vendor",
    )

    class Meta:
        verbose_name = "Vendor"
        verbose_name_plural = "Vendors"
        ordering = ["-id"]

    def __str__(self):
        return f"Vendor {getattr(self.user, 'username', self.user_id) if self.user else '#'+str(self.pk)}"


