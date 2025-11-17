# from django.db import models
# from userauths.models import User
# from sale.models import Client
# from django.conf import settings

# # Create your models here.
# class ClientDepot(Client):
#     CNI = models.CharField(max_length=50, blank=True, null=True)
#     address = models.CharField(max_length=255, null=True, blank=True)
#     photo = models.ImageField(upload_to='client/', default="client.jpg", null=True, blank=True)    

# class CompteDepot(models.Model):
#     client = models.ForeignKey('ClientDepot', on_delete=models.SET_NULL, null=True, blank=True, related_name="client_depot")
#     created_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,related_name='comptes_crees')
#     numero_compte = models.CharField(max_length=30, unique=True)
#     solde = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
#     date_creation = models.DateTimeField(auto_now_add=True)
    
#     def __str__(self):
#         return f"{self.numero_compte} - {self.client.nom_complet() if self.client else 'Sans client'}"

# class Transaction(models.Model):
#     TYPE_CHOICES = (
#         ("Depot", "Dépôt"),
#         ("Retrait", "Retrait"),
#     )

#     STATUT_CHOICES = (
#         ("Terminé", "Terminé"),
#         ("Échoué", "Échoué"),
#         ("En attente", "En attente"),
#     )

#     compte = models.ForeignKey( CompteDepot,on_delete=models.CASCADE,related_name='transactions')
#     type_transaction = models.CharField(max_length=10,choices=TYPE_CHOICES)
#     montant = models.DecimalField(max_digits=12,decimal_places=2)
#     date_transaction = models.DateTimeField(auto_now_add=True)
#     user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,related_name='transactions_effectuees')
#     statut = models.CharField(max_length=20,choices=STATUT_CHOICES,default="Terminé")
#     # commentaire = models.TextField(null=True,blank=True,help_text="Optionnel : commentaire ou note liée à la transaction")

#     @property
#     def full_name(self):
#         if self.compte and self.compte.client:
#             return self.compte.client.full_name
#         return ""

#     class Meta:
#         ordering = ['-date_transaction']
#         verbose_name = "Transaction"
#         verbose_name_plural = "Transactions"

#     def __str__(self):
#         return f"{self.type_transaction} de {self.montant} FCFA sur {self.compte.numero_compte}"


from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, CheckConstraint
from django.utils import timezone

from sale.models import Client  # base

class ClientDepot(Client):
    CNI = models.CharField(max_length=50, blank=True, null=True)  # → unique=True si nécessaire
    address = models.CharField(max_length=255, null=True, blank=True)
    photo = models.ImageField(upload_to="client/", default="client/default.jpg", null=True, blank=True)

    class Meta:
        verbose_name = "Client (compte dépôt)"
        verbose_name_plural = "Clients (compte dépôt)"


class CompteDepot(models.Model):
    client = models.ForeignKey(ClientDepot, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="comptes")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="comptes_crees"
    )
    numero_compte = models.CharField(max_length=30, unique=True, db_index=True)
    solde = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_creation"]
        constraints = [
            CheckConstraint(check=Q(solde__gte=0), name="ck_compte_depot_solde_gte_0",),
        ]
        indexes = [
            models.Index(fields=["client"]),
            models.Index(fields=["date_creation"]),
        ]

    def __str__(self):
        nom = getattr(self.client, "full_name", None) or getattr(self.client, "nom_complet", None)
        if callable(nom):
            nom = nom()
        return f"{self.numero_compte} - {nom or 'Sans client'}"

    def clean(self):
        super().clean()
        if self.solde is not None:
            self.solde = (Decimal(self.solde).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class Transaction(models.Model):
    TYPE_DEPOT   = "Depot"
    TYPE_RETRAIT = "Retrait"
    TYPE_CHOICES = (
        (TYPE_DEPOT, "Dépôt"),
        (TYPE_RETRAIT, "Retrait"),
    )

    STAT_TERMINE  = "Terminé"
    STAT_ECHOUE   = "Échoué"
    STAT_ATTENTE  = "En attente"
    STATUT_CHOICES = (
        (STAT_TERMINE, "Terminé"),
        (STAT_ECHOUE, "Échoué"),
        (STAT_ATTENTE, "En attente"),
    )

    compte = models.ForeignKey(CompteDepot, on_delete=models.CASCADE, related_name="transactions")
    type_transaction = models.CharField(max_length=10, choices=TYPE_CHOICES)
    montant = models.DecimalField(max_digits=12, decimal_places=2)
    date_transaction = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="transactions_effectuees"
    )
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default=STAT_TERMINE)

    class Meta:
        ordering = ["-date_transaction"]
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        constraints = [
            CheckConstraint(check=Q(montant__gt=0),name="ck_transaction_montant_gt_0",),
        ]
        indexes = [
            models.Index(fields=["compte", "date_transaction"]),
            models.Index(fields=["statut"]),
            models.Index(fields=["type_transaction"]),
        ]

    def __str__(self):
        return f"{self.type_transaction} de {self.montant} FCFA sur {self.compte.numero_compte}"

    @property
    def full_name(self):
        c = getattr(self.compte, "client", None)
        if not c:
            return ""
        nom = getattr(c, "full_name", None) or getattr(c, "nom_complet", None)
        return nom() if callable(nom) else (nom or "")

