import string
from decimal import Decimal
from random import SystemRandom

from django.db import models
from django.template.defaultfilters import slugify

from purchase.models import Fournisseur
from store.models import Produit

# from shortuuid.django_fields import ShortUUIDField



# Create your models here.
# class Fournisseur(models.Model):
#     nom = models.CharField(max_length=100)
#     prenom = models.CharField(max_length=100)
#     address = models.CharField(max_length=100, blank=True, null=True)
#     telephone = models.CharField(max_length=15, unique=True, blank=True, null=True)
#     slug = models.SlugField(max_length=30, null=True, blank=True, unique=True)
#     date_ajout = models.DateTimeField(auto_now_add=True) 
#     date_modification = models.DateTimeField(auto_now=True) 
    
#     def __str__(self):
#         return f'{self.nom} {self.prenom} {self.telephone}'
    
class Stock(models.Model):
    produit = models.ForeignKey(Produit, on_delete=models.SET_NULL, null=True, blank=True)
    # fournisseur = models.ForeignKey(Fournisseur, on_delete=models.SET_NULL, null=True, blank=True)
    # quantite = models.PositiveIntegerField(default=0)
    quantite = models.PositiveIntegerField(default=0)
    # total_poids_achat = models.DecimalField(default=0.00, decimal_places=2, max_digits=12) 
    # prix_achat_gramme = models.DecimalField(default=0.00, decimal_places=2, max_digits=12) 
    # # prix_achat_unite = models.DecimalField(default=0.00, decimal_places=2, max_digits=12) 
    # total_prix_achat = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
    date_ajout = models.DateTimeField(auto_now_add=True) 
    date_modification = models.DateTimeField(auto_now=True)
    
    
    # def update_stock(self, quantite):
    #     self.quantite += quantite
    #     self.save()
    
    def save(self, *args, **kwargs):
        if self.quantite < 0:  # or any other validation logic
            raise ValueError("Quantite must be non-negative")
        super().save(*args, **kwargs)
    
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
        # return f"{self.produit} - {self.fournisseur}"
        return f"{self.produit}"
    


# class CommandeStock(models.Model):
#     fournisseur = models.ForeignKey(Fournisseur, on_delete=models.CASCADE)
#     date_commande_stock = models.DateTimeField(auto_now_add=True)
#     etat = models.CharField(max_length=20, choices=[('en attente', 'En attente'), ('livré', 'Livré')])

#     def __str__(self):
#         return f"La Commande fait chez {self.fournisseur.nom} - {self.fournisseur.prenom} - {self.etat}"


# class LigneCommandeStock(models.Model):
#     commande_stock = models.ForeignKey(CommandeStock, related_name='lignes_commande_stock', on_delete=models.CASCADE)
#     produit = models.ForeignKey(Produit, on_delete=models.CASCADE)
#     quantite = models.PositiveIntegerField()
#     prix_par_unite = models.DecimalField(max_digits=10, decimal_places=2)

#     def __str__(self):
#         return f"Ligne de commande pour le {self.produit.nom}, Quantity: {self.quantite}"
    