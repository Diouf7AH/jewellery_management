import random
import string
import uuid

from django.db import models
from decimal import Decimal
from store.models import Produit
import datetime
from django.core.validators import MinValueValidator
from django.utils import timezone

# Create your models here.
class Fournisseur(models.Model):
    nom = models.CharField(max_length=100, blank=True, null=True)
    prenom = models.CharField(max_length=100, blank=True, null=True)
    address = models.CharField(max_length=100, blank=True, null=True)
    telephone = models.CharField(max_length=15, unique=True, blank=True, null=True)
    slug = models.SlugField(max_length=30, null=True, blank=True, unique=True)
    date_ajout = models.DateTimeField(auto_now_add=True) 
    date_modification = models.DateTimeField(auto_now=True) 
    
    def __str__(self):
        return f'{self.nom} {self.prenom} {self.telephone}'


# Achat  Model
class Achat(models.Model):
    fournisseur = models.ForeignKey('Fournisseur', related_name="achat", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    montant_total_ht = models.DecimalField(default=0.00, null=True, max_digits=12, decimal_places=2)
    montant_total_ttc = models.DecimalField(default=0.00, null=True, max_digits=12, decimal_places=2)

    # une propriété pour les taxes globales
    @property
    def montant_total_tax(self):
        return self.montant_total_ttc - self.montant_total_ht
    
    def update_total(self):
        """
        Met à jour les montants HT et TTC de l'achat
        en recalculant à partir des produits liés.
        """
        total = sum(p.sous_total_prix_achat for p in self.produits.all())
        tax_total = sum(p.tax or 0 for p in self.produits.all())
        self.montant_total_ht = total
        self.montant_total_ttc = total + tax_total
        self.save()
    
    def get_produits_details(self):
        return [
            {
                "produit": p.produit.nom,
                "quantite": p.quantite,
                "prix_gramme": p.prix_achat_gramme,
                "sous_total": p.sous_total_prix_achat,
                "tax": p.tax,
            }
            for p in self.produits.all()
        ]

    def __str__(self):
        return f"Achat Fournisseur: {self.fournisseur.nom if self.fournisseur else 'N/A'}"


    # def save(self, *args, **kwargs):
    #         super().save(*args, **kwargs)
    #         if self.achat:
    #             # appel update_total() automatiquement à chaque fois qu’un produit est ajouté/modifié.
    #             self.achat.update_total()
    
    
# VenteProduit (Product in Sale) Model
class AchatProduit(models.Model):
    achat = models.ForeignKey(Achat, related_name="produits", on_delete=models.CASCADE)
    produit = models.ForeignKey(Produit, related_name="achats_produits", on_delete=models.CASCADE)
    numero_achat_produit = models.CharField(max_length=25, unique=True, null=True, blank=True)
    quantite = models.PositiveIntegerField(default=0, validators=[MinValueValidator(1)])
    prix_achat_gramme = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
    fournisseur = models.ForeignKey(Fournisseur, on_delete=models.SET_NULL, null=True, blank=True)
    tax = models.DecimalField(default=0.00, decimal_places=2, max_digits=12, null=True, blank=True)
    sous_total_prix_achat = models.DecimalField(default=0.00, null=True, decimal_places=2, max_digits=12)

    class Meta:
        verbose_name = "Produit acheté"
        verbose_name_plural = "Produits achetés"

    def __str__(self):
        return f"{self.quantite} x {self.produit.nom if self.produit else 'N/A'} in Achat {self.achat.id if self.achat else 'N/A'}"
    
    @property
    def prix_achat_total_ttc(self):
        return (self.sous_total_prix_achat or Decimal(0)) + (self.tax or Decimal(0))

    def save(self, *args, **kwargs):
        # Générer numéro unique si vide
        if not self.numero_achat_produit:
            today = timezone.now().strftime('%Y%m%d')
            prefix = f"ACH-PROD-{today}"
            for _ in range(10):
                suffix = ''.join(random.choices('0123456789', k=4))
                numero = f"{prefix}-{suffix}"
                if not AchatProduit.objects.filter(numero_achat_produit=numero).exists():
                    self.numero_achat_produit = numero
                    break
            else:
                raise Exception("Impossible de générer un numéro d'achat produit unique.")

        # ⚙️ Calcul automatique du sous-total
        poids = self.produit.poids or Decimal(0)
        self.sous_total_prix_achat = self.prix_achat_gramme * self.quantite * poids

        super().save(*args, **kwargs)
        
        # 🔁 Met à jour automatiquement les montants HT/TTC dans Achat
        if self.achat:
            self.achat.update_total()

    def to_dict(self):
        return {
            "produit": self.produit.nom,
            "quantite": self.quantite,
            "prix_achat_gramme": self.prix_achat_gramme,
            "sous_total_prix_achat": self.sous_total_prix_achat,
            "tax": self.tax,
            "prix_achat_total_ttc": self.prix_achat_total_ttc,
        }