from django.db import models
from userauths.models import User
from sale.models import Client
from django.conf import settings

# Create your models here.
class ClientDepot(Client):
    CNI = models.CharField(max_length=50, blank=True, null=True)
    address = models.CharField(max_length=255, null=True, blank=True)
    photo = models.ImageField(upload_to='client/', default="client.jpg", null=True, blank=True)    

class CompteDepot(models.Model):
    client = models.ForeignKey('ClientDepot', on_delete=models.SET_NULL, null=True, blank=True, related_name="client_depot")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,related_name='comptes_crees')
    numero_compte = models.CharField(max_length=30, unique=True)
    solde = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    date_creation = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.numero_compte} - {self.client.nom_complet() if self.client else 'Sans client'}"

class Transaction(models.Model):
    TYPE_CHOICES = (
        ("Depot", "Dépôt"),
        ("Retrait", "Retrait"),
    )

    STATUT_CHOICES = (
        ("Terminé", "Terminé"),
        ("Échoué", "Échoué"),
        ("En attente", "En attente"),
    )

    compte = models.ForeignKey( CompteDepot,on_delete=models.CASCADE,related_name='transactions')
    type_transaction = models.CharField(max_length=10,choices=TYPE_CHOICES)
    montant = models.DecimalField(max_digits=12,decimal_places=2)
    date_transaction = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,related_name='transactions_effectuees')
    statut = models.CharField(max_length=20,choices=STATUT_CHOICES,default="Terminé")
    # commentaire = models.TextField(null=True,blank=True,help_text="Optionnel : commentaire ou note liée à la transaction")

    @property
    def full_name(self):
        if self.compte and self.compte.client:
            return self.compte.client.full_name
        return ""

    class Meta:
        ordering = ['-date_transaction']
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"

    def __str__(self):
        return f"{self.type_transaction} de {self.montant} FCFA sur {self.compte.numero_compte}"