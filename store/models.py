import base64
import random
import string
from decimal import Decimal
from io import BytesIO
from random import SystemRandom
from django.utils import timezone

# import qrcode
from django.db import models
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.template.defaultfilters import slugify
from django.utils import timezone
from shortuuid.django_fields import ShortUUIDField


@receiver(post_migrate)
def create_default_instances(sender, **kwargs):
    Purete.objects.get_or_create(id=1, defaults={'purete': 21})
    Purete.objects.get_or_create(id=2, defaults={'purete': 18})
    
def get_default_purete():
    # return Purete.objects.get_or_create(id=1, defaults={'purete': 21})[0].id
    return Purete.objects.get_or_create(id=2, defaults={'purete': 18})[0].id

MATIERE = (
    ("or", "Or"),
    ("ar", "Argent"),
    ("mixte", "Mixte")
)

STATUS = (
    ("désactivé", "Désactivé"),
    ("rejetée", "Rejetée"),
    ("en_revue", "En Revue"),
    ("publié", "Publié"),
)

GENRE = (
    ("H", "Homme"),
    ("F", "Femme"),
    ("E", "Enfant")
)

ETAT = (
    ("N", "Neuf"),
    ("R", "Retour")
)

# def get_default_brand():
#     return Marque.objects.get_or_create(id=1, defaults={'titre': 'Default Brand'})[0].id

# def get_default_purity():
#     return Purete.objects.get_or_create(id=1, defaults={'purete': 18})[0].id

# def get_default_type():
#     return Type.objects.get_or_create(id=1, defaults={'type': 'Type par defaut'})[0].id

# def get_default_model():
#     return Model.objects.get_or_create(id=1, defaults={'modele': 'Default Model'})[0].id

# Create your models here.

class Bijouterie(models.Model):
    nom = models.CharField(max_length=30, unique=True, null=True)
    telephone_portable_1 = models.CharField(max_length=30, null=True, blank=True)
    telephone_portable_2 = models.CharField(max_length=30, null=True, blank=True)
    telephone_portable_3 = models.CharField(max_length=30, null=True, blank=True)
    telephone_portable_4 = models.CharField(max_length=30, null=True, blank=True)
    telephone_portable_5 = models.CharField(max_length=30, null=True, blank=True)
    telephone_fix = models.CharField(max_length=30, null=True, blank=True)
    adresse = models.CharField(max_length=255, null=True, blank=True)
    
    logo_blanc = models.ImageField(upload_to='logo/', default="logo_blanc.jpg", null=True, blank=True)
    logo_noir = models.ImageField(upload_to='logo/', default="logo_noir.jpg", null=True, blank=True)
    
    nom_de_domaine = models.URLField(max_length=200, null=True, blank=True)
    tiktok = models.URLField(max_length=200, null=True, blank=True)
    facebook = models.URLField(max_length=200, null=True, blank=True)
    instagram = models.URLField(max_length=200, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Bijouteries"

    def __str__(self):
        return self.nom or "Bijouterie sans nom"
    

# Model for Product Categories
class Categorie(models.Model):
    nom = models.CharField(max_length=30, unique=True, blank=True, default="")
    image = models.ImageField(upload_to='categorie/', default="category.jpg", null=True, blank=True)

    class Meta:
        verbose_name_plural = "Catégories"
        ordering = ['nom']  # Tri par nom dans l’admin

    def __str__(self):
        return self.nom or "Sans nom"

    def save(self, *args, **kwargs):
        # Optionnel : tu peux faire un nettoyage ou un formatage du nom ici si besoin
        if self.nom:
            self.nom = self.nom.strip().title()
        super().save(*args, **kwargs)


    
# Type model
# class Type(models.Model):
#     type = models.CharField(max_length = 55, unique=True, null=True)
#     categorie = models.ForeignKey(Categorie, on_delete=models.SET_NULL, null=True, blank=True, related_name="type_categorie")
    
    
#     class Meta:
#         verbose_name_plural = "Types"
    
#     def __str__(self):
#         return self.type


# Type model
class Modele(models.Model):
    modele = models.CharField(max_length=55, unique=True, null=True)
    categorie = models.ForeignKey(Categorie, on_delete=models.SET_NULL, null=True, blank=True, related_name="modele_categorie")
    
    
    class Meta:
        verbose_name_plural = "Models"
    
    def __str__(self):
        return self.modele



# Purity model
class Purete(models.Model):
    # purete = models.IntegerField()
    purete = models.CharField(unique=True, max_length=15, null=True, blank=True)
    
    def __str__(self):  
        return f"{self.purete}K"
    

# Brand model
class Marque(models.Model):
    marque = models.CharField(unique=True, max_length=25, null=True, blank=True)
    purete = models.ForeignKey(Purete, on_delete=models.SET_NULL, null=True, blank=True, related_name="purete_marque", default=get_default_purete)
    prix = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.marque:
            raise ValueError("Le champ 'marque' ne peut pas être vide.")
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name_plural = "Marques"
    
    def __str__(self):
        return f"{self.marque} - {self.purete.purete if self.purete else 'N/A'}"
    

# # Model model
# class Model(models.Model):
#     nom = models.CharField(max_length=255)
#     type = models.ForeignKey(Type, on_delete=models.SET_NULL, null=True, blank=True, related_name="type_model")
#     description = models.TextField(blank=True)

# def generate_sku(length=7):
#     return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# Model for Produits
class Produit(models.Model):
    nom = models.CharField(max_length=100, blank=True, default="")
    image = models.ImageField(upload_to='produits/', blank=True, null=True)
    description = models.TextField(null=True, blank=True)
    
    categorie = models.ForeignKey(Categorie, on_delete=models.SET_NULL, null=True, blank=True, related_name="categorie_produit")
    purete = models.ForeignKey(Purete, on_delete=models.SET_NULL, null=True, blank=True, related_name="purete_produit", default=get_default_purete)
    marque = models.ForeignKey(Marque, on_delete=models.SET_NULL, null=True, blank=True, related_name="marque_produit")
    matiere = models.CharField(choices=MATIERE, max_length=50, default="or", null=True, blank=True)
    modele = models.ForeignKey(Modele, on_delete=models.SET_NULL, null=True, blank=True, related_name="modele_produit")

    poids = models.DecimalField(default=0.00, decimal_places=2, max_digits=12) 
    taille = models.DecimalField(blank=True, null=True, default=0.00, decimal_places=2, max_digits=12)
    genre = models.CharField(choices=GENRE, default="F", max_length=10, blank=True, null=True)
    status = models.CharField(choices=STATUS, max_length=10, default="publié", null=True, blank=True)
    etat = models.CharField(choices=ETAT, max_length=10, default="N", null=True, blank=True)
    
    sku = models.SlugField(unique=True, max_length=100, null=True, blank=True)
    
   
    date_ajout = models.DateTimeField(auto_now_add=True) 
    date_modification = models.DateTimeField(auto_now=True) 
    
    
    def skuGet(self):
        champs = [self.categorie, self.modele, self.marque, self.poids, self.taille, self.purete, self.etat]
        if not all(champs):
            raise ValueError("Tous les champs nécessaires à la génération du SKU doivent être renseignés.")

        return (
            f"{self.categorie.nom[:4].upper()}-"
            f"{self.modele.modele[:4].upper()}-"
            f"{self.etat}-"
            f"{self.purete.purete}-"
            f"{self.marque.marque[:3].upper()}-"
            f"P{self.poids}-T{self.taille}"
        )
    
    def save(self, *args, **kwargs):
        if not self.nom:
            self.nom = f'{self.categorie} {self.modele}'
        if not self.sku:
            self.sku = self.skuGet()
        
        super().save(*args, **kwargs)

        # Générer le QR code à partir du SKU
            
    
    def __str__(self):
        return f'{self.sku}'
    
    class Meta:
        ordering = ['-id']
        verbose_name_plural = "Produits"


# Model for Product Gallery
class Gallery(models.Model):
    produit = models.ForeignKey(
        Produit, on_delete=models.CASCADE, null=True, related_name="produit_gallery"
    )
    image = models.ImageField(upload_to='produit_gallery/')
    active = models.BooleanField(default=True)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image de {self.produit.nom}"

    def image_url(self):
        if self.image:
            return self.image.url  # <== retourne l'URL utilisable

        return None

    class Meta:
        verbose_name_plural = "Galerie"
        ordering = ['-date']
        

class HistoriquePrix(models.Model):
    marque = models.ForeignKey(Marque, on_delete=models.CASCADE, null=True)
    prix_achat = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
    prix_vente = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
    # Date of creation
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)
