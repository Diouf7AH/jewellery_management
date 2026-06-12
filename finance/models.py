from decimal import Decimal

from django.conf import settings
from django.db import models


class Depense(models.Model):
    TYPE_SALAIRE = "salaire"
    TYPE_LOYER = "loyer"
    TYPE_TRANSPORT = "transport"
    TYPE_ELECTRICITE = "electricite"
    TYPE_EAU = "eau"
    TYPE_INTERNET = "internet"
    TYPE_FOURNITURE = "fourniture"
    TYPE_REPARATION = "reparation"
    TYPE_AUTRE = "autre"

    TYPE_CHOICES = [
        (TYPE_SALAIRE, "Salaire"),
        (TYPE_LOYER, "Loyer"),
        (TYPE_TRANSPORT, "Transport"),
        (TYPE_ELECTRICITE, "Électricité"),
        (TYPE_EAU, "Eau"),
        (TYPE_INTERNET, "Internet"),
        (TYPE_FOURNITURE, "Fourniture"),
        (TYPE_REPARATION, "Réparation"),
        (TYPE_AUTRE, "Autre"),
    ]

    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_PAID, "Payé"),
        (STATUS_CANCELLED, "Annulé"),
    ]

    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        related_name="depenses",
        null=True,
        blank=True,
    )

    type_depense = models.CharField(max_length=30, choices=TYPE_CHOICES)
    titre = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True)

    montant = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    beneficiaire = models.CharField(max_length=150, blank=True, null=True)
    telephone_beneficiaire = models.CharField(max_length=30, blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="depenses_creees",
    )

    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="depenses_payees",
    )
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,related_name="depenses_modifiees",)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="depenses_annulees",
    )

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.titre} - {self.montant} FCFA"
    
    


