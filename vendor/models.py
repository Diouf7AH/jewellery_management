# vendor/models.py

from __future__ import annotations

from django.conf import settings
from django.db import models

from staff.models import StaffCore


class Vendor(StaffCore):
    """
    Vendeur rattaché à une seule bijouterie.

    Le vendeur reçoit du stock avec VENDOR_ASSIGN
    et vend avec SALE_OUT.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="staff_vendor_profile",
        related_query_name="vendor_profile",
    )

    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        related_name="vendors",
        related_query_name="vendor",
    )

    class Meta:
        verbose_name = "Vendeur"
        verbose_name_plural = "Vendeurs"
        ordering = ["-id"]

        indexes = [
            models.Index(
                fields=["bijouterie", "verifie"],
                name="idx_vendor_bij_verif",
            ),
        ]

    def __str__(self):
        return self.full_name
    
    
