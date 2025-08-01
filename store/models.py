import base64
import random
import string
from decimal import Decimal
from io import BytesIO
from django.core.files import File
from random import SystemRandom
from django.utils import timezone
import uuid
from django.conf import settings
import qrcode
from django.db import models
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.utils.text import slugify
from django.utils import timezone
from shortuuid.django_fields import ShortUUIDField
from django.core.exceptions import ValidationError

@receiver(post_migrate)
def create_default_instances(sender, **kwargs):
    Purete.objects.get_or_create(id=1, defaults={'purete': 21})
    Purete.objects.get_or_create(id=2, defaults={'purete': 18})
    
def get_default_purete():
    # return Purete.objects.get_or_create(id=1, defaults={'purete': 21})[0].id
    return Purete.objects.get_or_create(id=2, defaults={'purete': 18})[0].id

MATIERE = (
    ("or", "Or"),
    ("argent", "Argent"),
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
    nom = models.CharField(max_length=30, unique=True)
    image = models.ImageField(upload_to='categorie/', default="category.jpg", null=True, blank=True)
    # bijouterie = models.ForeignKey(Bijouterie, on_delete=models.CASCADE, null=True, blank=True, related_name="bijouterie_categorie")

    class Meta:
        verbose_name_plural = "Catégories"
        ordering = ['nom']  # Tri par nom dans l’admin

    def __str__(self):
        return self.nom or "Sans nom"

    def save(self, *args, **kwargs):
        # Optionnel : tu peux faire un nettoyage ou un formatage du nom ici si besoin
        if self.nom:
            self.nom = " ".join(self.nom.strip().split()).title()
        super().save(*args, **kwargs)
    
    def get_image_url(self):
        if self.image and hasattr(self.image, 'url'):
            return self.image.url
        return '/media/category.jpg'


    
# Type model
# class Type(models.Model):
#     type = models.CharField(max_length = 55, unique=True, null=True)
#     categorie = models.ForeignKey(Categorie, on_delete=models.SET_NULL, null=True, blank=True, related_name="type_categorie")
    
    
#     class Meta:
#         verbose_name_plural = "Types"
    
#     def __str__(self):
#         return self.type


# Purity model
class Purete(models.Model):
    # purete = models.IntegerField()
    purete = models.CharField(unique=True, max_length=5)    
    
    def __str__(self):  
        return f"{self.purete}K"

# Brand model
class Marque(models.Model):
    marque = models.CharField(unique=True, max_length=25)
    purete = models.ForeignKey(Purete, on_delete=models.SET_NULL, null=True, blank=True, related_name="marques_purete", default=get_default_purete)
    prix = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.marque:
            raise ValueError("Le champ 'marque' ne peut pas être vide.")
        self.marque = " ".join(self.marque.strip().split()).title()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "Marques"

    def __str__(self):
        return f"{self.marque} - {self.purete.purete if self.purete else 'N/A'}"


#implémentation avec une table intermédiaire 
class CategorieMarque(models.Model):
    categorie = models.ForeignKey('Categorie', on_delete=models.SET_NULL, null=True, blank=True, related_name='categorie_marques')
    marque = models.ForeignKey('Marque', on_delete=models.SET_NULL, null=True, blank=True, related_name='marque_categories')
    date_liaison = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['categorie', 'marque'], name='unique_categorie_marque')
        ]

    def __str__(self):
        return f"{self.categorie.nom} ↔ {self.marque.marque}"

# Type model
class Modele(models.Model):
    modele = models.CharField(max_length=55, unique=True, null=True)
    marque = models.ForeignKey(Marque, on_delete=models.SET_NULL, null=True, blank=True, related_name="modele_marque")
    
    def __str__(self):
        # Affiche : "Bague (marque: Nocal)" ou "Bague (Marque: Aucune)"
        return f"{self.modele} (Marque: {self.marque.nom if self.marque else 'Aucune'})"

    @property
    def marque_id(self):
        # Permet d'accéder à modele.marque_id directement (int ou None)
        return self.marque.id if self.marque else None
    
    class Meta:
        ordering = ['modele']
        verbose_name = "Modèle"
        verbose_name_plural = "Modèles"
        
    def save(self, *args, **kwargs):
        if self.modele:
            self.modele = self.modele.strip().title()
        super().save(*args, **kwargs)


# Model for Produits
class Produit(models.Model):
    # bijouterie = models.ForeignKey(Bijouterie, on_delete=models.CASCADE, null=True, blank=True, related_name="bijouterie_produit")
    nom = models.CharField(max_length=100, blank=True, default="")
    image = models.ImageField(upload_to='produits/', blank=True, null=True)
    description = models.TextField(null=True, blank=True)
    qr_code = models.ImageField(upload_to='qr_codes/', null=True, blank=True)
    
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
    slug = models.SlugField(max_length=100, unique=True, blank=True, null=True)

    date_ajout = models.DateTimeField(auto_now_add=True) 
    date_modification = models.DateTimeField(auto_now=True) 
    
    def skuGet(self):
        champs = [self.categorie, self.modele, self.marque, self.poids, self.taille, self.purete, self.etat]
        if not all(champs):
            print("[SKU] Champs manquants pour SKU :", champs)
            return None

        return (
            f"{self.categorie.nom[:4].upper()}-"
            f"{self.modele.modele[:4].upper()}-"
            f"{self.etat}-"
            f"{self.purete.purete}-"
            f"{self.marque.marque[:3].upper()}-"
            f"P{self.poids}-T{self.taille}"
        )
    
    @staticmethod
    def generate_qr_code_image(content):
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(content)
        qr.make(fit=True)

        img = qr.make_image(fill='black', back_color='white')
        buffer = BytesIO()
        
        # Nettoyer le nom du fichier
        safe_name = slugify(content)[:50] if content else uuid.uuid4().hex[:10]
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return File(buffer, name=f'qr_{safe_name}.png')
    
    def regenerate_qr_code(self):
        try:
            qr_content = self.produit_url
            qr_file = self.generate_qr_code_image(qr_content)
            self.qr_code.save(qr_file.name, qr_file, save=True)
            return True
        except Exception as e:
            print(f"[QR ERROR] {e}")
            return False

    def save(self, *args, **kwargs):
        self.full_clean()
        is_new = self.pk is None
        generer_qr = False

        if not self.nom and self.categorie and self.modele and self.marque:
            self.nom = f'{self.categorie.nom} {self.modele.modele} {self.marque.marque}'

        if not self.slug:
            base_slug = slugify(self.nom or "produit")
            self.slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
            generer_qr = True

        if not self.sku:
            base_sku = self.skuGet()
            if base_sku:
                final_sku = base_sku
                suffix = 1
                while Produit.objects.filter(sku=final_sku).exists():
                    final_sku = f"{base_sku}-{suffix}"
                    suffix += 1
                self.sku = final_sku

        super().save(*args, **kwargs)

        if not self.qr_code and generer_qr:
            try:
                qr_content = self.produit_url
                qr_file = self.generate_qr_code_image(qr_content)
                self.qr_code.save(qr_file.name, qr_file, save=False)
                super().save(update_fields=["qr_code"])
            except Exception as e:
                print(f"[QR ERROR] {e}")
                
    @property
    def produit_url(self):
        base_url = getattr(settings, 'SITE_URL', 'https://www.rio-gold.com')
        return f"{base_url}/produit/{self.slug}" if self.slug else None
    
    def clean(self):
        if self.poids < 0:
            raise ValidationError("Le poids ne peut pas être négatif.")
        if self.taille is not None and self.taille < 0:
            raise ValidationError("La taille ne peut pas être négative.")
    
    
    # Achiffage admin.py
    def qr_code_url(self):
        if self.qr_code:
            return self.qr_code.url
        return "Aucun QR code"

    qr_code_url.short_description = "QR Code"
    
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
