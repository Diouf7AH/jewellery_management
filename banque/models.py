from django.db import models
from userauths.models import User
from sale.models import Client

# Create your models here.
class ClientBanque(Client):
    # telephone = models.CharField(max_length=100, unique=True)
    CNI = models.CharField(max_length=100, blank=True, null=True)
    photo = models.ImageField(upload_to='client/', default="client.jpg", null=True, blank=True)    

class CompteBancaire(models.Model):
    client_banque  = models.ForeignKey('ClientBanque', on_delete=models.SET_NULL, null=True, blank=True, related_name="client_banque")
    # user = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'client'})
    numero_compte = models.CharField(max_length=20, unique=True)
    solde = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    date_creation = models.DateTimeField(auto_now_add=True)

class Transaction(models.Model):
    compte = models.ForeignKey(CompteBancaire, on_delete=models.CASCADE, related_name='transactions')
    type_transaction = models.CharField(max_length=10, choices=(("Depot", "Dépôt"), ("Retrait", "Retrait")))
    montant = models.DecimalField(max_digits=12, decimal_places=2)
    date_transaction = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)