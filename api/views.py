from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


class CommercialSettings(models.Model):
    REDUCTION_5 = Decimal("5.00")
    REDUCTION_10 = Decimal("10.00")
    REDUCTION_15 = Decimal("15.00")
    REDUCTION_20 = Decimal("20.00")

    REDUCTION_OCCASION_CHOICES = (
        (REDUCTION_5, "5 %"),
        (REDUCTION_10, "10 %"),
        (REDUCTION_15, "15 %"),
        (REDUCTION_20, "20 %"),
    )

    bijouterie = models.OneToOneField(
        "store.Bijouterie",
        on_delete=models.CASCADE,
        related_name="commercial_settings",
    )

    reduction_produit_occasion = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        choices=REDUCTION_OCCASION_CHOICES,
        default=REDUCTION_10,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name = "Paramètre commercial"
        verbose_name_plural = "Paramètres commerciaux"

    def __str__(self):
        return (
            f"{self.bijouterie.nom} - "
            f"Réduction occasion : "
            f"{self.reduction_produit_occasion}%"
        )

    def clean(self):
        super().clean()

        valeurs_autorisees = {
            self.REDUCTION_5,
            self.REDUCTION_10,
            self.REDUCTION_15,
            self.REDUCTION_20,
        }

        if self.reduction_produit_occasion not in valeurs_autorisees:
            raise ValidationError({
                "reduction_produit_occasion": (
                    "La réduction doit être de "
                    "5 %, 10 %, 15 % ou 20 %."
                )
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        

