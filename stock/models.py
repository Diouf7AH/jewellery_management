from decimal import Decimal
import string
from random import SystemRandom

from django.db import models
from django.template.defaultfilters import slugify
from shortuuid.django_fields import ShortUUIDField
from store.models import Produit


# Create your models here.
class Fournisseur(models.Model):
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    address = models.CharField(max_length=100, blank=True, null=True)
    telephone = models.CharField(max_length=15, unique=True, blank=True, null=True)
    slug = models.SlugField(max_length=30, null=True, blank=True, unique=True)
    date_ajout = models.DateTimeField(auto_now_add=True) 
    date_modification = models.DateTimeField(auto_now=True) 
    
    def __str__(self):
        return f'{self.nom} {self.prenom} {self.telephone}'
    
class Stock(models.Model):
    produit = models.ForeignKey(Produit, on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_produit")
    fournisseur = models.ForeignKey(Fournisseur, on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_fornisseur")
    quantite = models.PositiveIntegerField(default=0)
    # total_poids_achat = models.DecimalField(default=0.00, decimal_places=2, max_digits=12) 
    prix_achat_gramme = models.DecimalField(default=0.00, decimal_places=2, max_digits=12) 
    # # prix_achat_unite = models.DecimalField(default=0.00, decimal_places=2, max_digits=12) 
    # total_prix_achat = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
    date_ajout = models.DateTimeField(auto_now_add=True) 
    date_modification = models.DateTimeField(auto_now=True)  
    
    @property
    def calcul_total_poids_achat(self):
        total_poids_achat = self.produit.poids * self.quantite
        return total_poids_achat
    
    @property
    def calcul_total_achat(self):
        total_achat = Decimal((self.produit.poids * self.quantite) * self.prix_achat_gramme)
        return total_achat
    
    # def save(self, *args, **kwargs):  
    #     # self.total_prix_achat = self.calcule_total_prix_achat() 
    #     self.total_prix_achat = decimal.Decimal(self.total_poids_achat) * decimal.Decimal(Decimal(calcul_total_achat))
    #     super(Stock, self).save(*args, **kwargs)

    def __str__(self):
        return f"{self.produit} - {self.fournisseur}"
    