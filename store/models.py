import base64
import random
import string
from decimal import Decimal
from io import BytesIO
from random import SystemRandom

import qrcode
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
    ("homme", "Homme"),
    ("femme", "Femme"),
    ("enfant", "Enfant")
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
    nom = models.CharField(max_length = 30, unique=True, null=True)
    telephone_portable_1 = models.CharField(max_length = 30, unique=True, null=True)
    telephone_portable_2 = models.CharField(max_length = 30, unique=True, null=True)
    telephone_portable_3 = models.CharField(max_length = 30, unique=True, null=True)
    telephone_portable_4 = models.CharField(max_length = 30, unique=True, null=True)
    telephone_portable_5 = models.CharField(max_length = 30, unique=True, null=True)
    telephone_fix = models.CharField(max_length = 30, unique=True, null=True)
    adresse = models.CharField(max_length = 30, unique=True, null=True)
    logo_blanc = models.ImageField(upload_to='logo/', default="logo_blanc.jpg", null=True, blank=True)
    logo_noir = models.ImageField(upload_to='logo/', default="logo_noir.jpg", null=True, blank=True)
    nom_de_domaine = models.CharField(max_length = 30, unique=True, null=True)
    tiktok = models.CharField(max_length = 30, unique=True, null=True)
    facebook = models.CharField(max_length = 30, unique=True, null=True)
    intagram = models.CharField(max_length = 30, unique=True, null=True)
    
    class Meta:
        verbose_name_plural = "Bijouteries"

    # Returns an HTML image tag for the category's image
    # def thumbnail(self):
    #     return mark_safe('<img src="%s" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />' % (self.image.url))

    def __str__(self):
        return self.nom

# Model for Product Categories
class Categorie(models.Model):
    # Category titre
    nom = models.CharField(max_length=30, unique=True, null=True)
    # Image for the category
    image = models.ImageField(upload_to='categorie/', unique=True, default="category.jpg", null=True, blank=True)
    # Is the category active?
    active = models.BooleanField(default=True)
    # Slug for SEO-friendly URLs
    slug = models.SlugField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "Categories"

    # Returns an HTML image tag for the category's image
    # def thumbnail(self):
    #     return mark_safe('<img src="%s" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />' % (self.image.url))

    def __str__(self):
        return self.nom
    
    # Returns the count of produits in this category
    # def product_count(self):
    #     product_count = Product.objects.filter(category=self).count()
    #     return product_count
    
    # Returns the produits in this category
    # def cat_produits(self):
    #     cat_produits = Product.objects.filter(category=self)
    #     return cat_produits

    # Custom save method to generate a slug if it's empty
    def save(self, *args, **kwargs):
        if self.slug == "" or self.slug is None:
            rand_letters = ''.join(SystemRandom().choices(string.ascii_letters + string.digits, k=15))
            # self.slug = slugify(rand_letters)
            
            # uuid_key = shortuuid.uuid()
            # uniqueid = uuid_key[:4]
            # self.slug = slugify(self.title) + "-" + str(uniqueid.lower())
            self.slug = slugify(self.nom) + "-" + str(rand_letters)
        super(Categorie, self).save(*args, **kwargs) 


    
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
    # matiere = models.CharField(choices=MATIERE, max_length=50, default="or")
    # modele = models.ForeignKey(Modele, on_delete=models.SET_NULL, null=True, blank=True, related_name="modele_marque")
    creation_date = models.DateTimeField(auto_now_add=True)
    # modification_date = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Marques"
    
    def __str__(self):
        return self.marque
    

# # Model model
# class Model(models.Model):
#     nom = models.CharField(max_length=255)
#     type = models.ForeignKey(Type, on_delete=models.SET_NULL, null=True, blank=True, related_name="type_model")
#     description = models.TextField(blank=True)

# def generate_sku(length=7):
#     return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# Model for Produits
class Produit(models.Model):
    nom = models.CharField(max_length=100)
    image = models.FileField(upload_to='produits/', blank=True, null=True)
    description = models.TextField(null=True, blank=True)
    
    categorie = models.ForeignKey(Categorie, on_delete=models.SET_NULL, null=True, blank=True, related_name="categorie_produit")
    purete = models.ForeignKey(Purete, on_delete=models.SET_NULL, null=True, blank=True, related_name="purete_produit", default=get_default_purete)
    marque = models.ForeignKey(Marque, on_delete=models.SET_NULL, null=True, blank=True, related_name="marque_produit")
    matiere = models.CharField(choices=MATIERE, max_length=50, default="or", null=True, blank=True)
    modele = models.ForeignKey(Modele, on_delete=models.SET_NULL, null=True, blank=True, related_name="modele_produit")

    poids = models.DecimalField(default=0.00, decimal_places=2, max_digits=12) 
    taille = models.DecimalField(blank=True, null=True, default=0.00, decimal_places=2, max_digits=12)
    genre = models.CharField(choices=GENRE, default="femme", max_length=10, blank=True, null=True)
    status = models.CharField(choices=STATUS, max_length=50, default="publié", null=True, blank=True)
    
    slug = models.SlugField(unique=True, max_length=50, null=True, blank=True)
    sku = models.CharField( max_length=15, blank=True, unique=True)
    
    #prix par defaut
    # prix_vente_grammes = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
    # prix avec redution
    prix_vente_grammes = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
    prix_avec_tax = models.DecimalField(blank=True, null=True, default=0.00, decimal_places=2, max_digits=12)
    
    quantite_en_stock = models.PositiveIntegerField(default=0)
    
    # Date of product creation
    date_ajout = models.DateTimeField(auto_now_add=True) 
    date_modification = models.DateTimeField(auto_now=True) 
    # stock = models.IntegerField(default=0)
    
    # Unique short UUIDs for SKU and product
    # Exemple SKU
    # Style : pantalon
    # Type : casual
    # Modèle : 4355
    # Couleur : vert
    # Saison : printemps / été
    # Sexe : femme
    # Taille : 36
    # Lieu de stockage : entrepôt A
    
    # Ce système de numérotation permet de reconnaître efficacement et facilement un article. 
    # Par exemple, le code SKU généré avec les variantes précédentes pourrait être : 
    # PANT-4355-VRT-36.

    # Plusieurs unités disponibles pour une même référence sont identifiées via un code SKU identique : 
    # tous les pantalons verts du modèle n° 4355 en taille 36 femme ont donc le même numéro.
    
    # sku = ShortUUIDField(unique=True, length=5, max_length=50, prefix="SKU", alphabet="1234567890")
    
    # sku = models.CharField( max_length=13, blank=True, unique=True, default=generate_sku)
    # qr_code = models.ImageField(upload_to='qr_codes', blank=True)
    # qr_code = models.CharField(max_length=255, blank=True, null=True)
    # Slug for SEO-friendly URLs
    
    
    
    
    # def calcule_prix_vente(self):
    #     prix_vente = self.poids * self.marque.prix
    #     return prix_vente
    
    def slugGet(self):
        rand_letters = ''.join(SystemRandom().choices(string.ascii_letters + string.digits, k=15))
        slug = slugify(self.nom) + "-" + str(rand_letters)
        return slug
    
    def skuGet(self):
        # rend_alphanumerique = ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))
        rand_category = self.categorie.nom
        rand_category_4 = rand_category[:4]
        rand_modele = self.modele.modele
        rand_modele_4 = rand_modele[:4]
        rand_marque = self.marque.marque
        rand_marque_4 = rand_marque[:3]    
        rand_poids = str(Decimal(self.poids))
        rand_taille = str(Decimal(self.taille))
        sku = str(rand_category_4.upper()) + "-" + str(rand_modele_4.upper()) + "-" + str(rand_marque_4.upper()) + "-" + rand_poids + "-" + rand_taille
        return sku
    
    # def qr_codeGet(self):
    #     # qr code
    #     if self.qr_code == "" or self.qr_code is None:
    #         # Generate the content for the QR code
    #         qr_content = str(self.sku)
    #         # Generate the QR code image
    #         qr = qrcode.make(qr_content)
    #         # Save the QR code image to a BytesIO buffer
    #         buffer = BytesIO()
    #         qr.save(buffer, format='PNG')
    #         # Encode the QR code image to base64
    #         qr_base64 = base64.b64encode(buffer.getvalue()).decode()
    #         # Save the base64 string to the qr_code field
    #         self.qr_code = qr_base64
    #         qr_code = self.qr_code
    #         return qr_code

    def save(self, *args, **kwargs):

        if self.nom is not None:
            rand_nom = f'{self.categorie} {self.modele}'
            self.nom = rand_nom
        
        # self.prix_vente = self.calcule_prix_vente()
        self.prix_vente = Decimal(self.poids) * Decimal(self.marque.prix)
        self.slug = self.slugGet()
        self.sku = self.skuGet()
            
        # if self.prix_vente is not None:
        #     rand_prix_vente = self.poids * self.marque.prix
        #     self.prix_vente = rand_prix_vente
            
        # if self.slug == "" or self.slug is None:
        #     rand_letters = ''.join(SystemRandom().choices(string.ascii_letters + string.digits, k=10))
        #     self.slug = slugify(self.nom) + "-" + str(rand_letters)
            
        # if self.sku == "" or self.sku is None:
        #     rand_category = self.categorie.nom
        #     rand_category_4 = rand_category[:4]
            
        #     rand_modele = self.modele.modele
        #     rand_modele_4 = rand_modele[:4]
            
        #     rand_marque = self.marque.marque
        #     rand_marque_4 = rand_marque[:4]
            
        #     rand_poids = str(decimal.Decimal(self.poids))
            
        #     rand_taille = str(decimal.Decimal(self.taille))
            
        #     self.sku = str(rand_category_4.upper()) + "-" + str(rand_modele_4.upper()) + "-" + str(rand_marque_4.upper()) +  "-" + rand_taille+ "-" + rand_poids
        
        # # qr code
        # if self.qr_code == "" or self.qr_code is None:
        #     # Generate the content for the QR code
        #     qr_content = str(self.sku)
        #     # Generate the QR code image
        #     qr = qrcode.make(qr_content)
        #     # Save the QR code image to a BytesIO buffer
        #     buffer = BytesIO()
        #     qr.save(buffer, format='PNG')
        #     # Encode the QR code image to base64
        #     qr_base64 = base64.b64encode(buffer.getvalue()).decode()
        #     # Save the base64 string to the qr_code field
        #     self.qr_code = qr_base64
            
        # if self.prix_gramme == "" or self.prix_gramme is None:
        #     rand_prix = self.marque_product.prix * self.poids
        #     self.prix_vente = rand_prix
        
        super(Produit, self).save(*args, **kwargs)

    def __str__(self):
        return f'{self.sku}'
    
    class Meta:
        ordering = ['-id']
        verbose_name_plural = "Produits"
        


# Model for Product Gallery
class Gallery(models.Model):
    # Product associated with the gallery
    product = models.ForeignKey(Produit, on_delete=models.CASCADE, null=True, related_name="produit_gallery")
    # Image for the gallery
    image = models.FileField(upload_to='gallery/', default="gallery.jpg")
    # Is the image active?
    active = models.BooleanField(default=True)
    # Date of gallery image creation
    date = models.DateTimeField(auto_now_add=True)
    # Unique short UUID for gallery image
    gid = ShortUUIDField(max_length=25, alphabet="abcdefghijklmnopqrstuvxyz")

    class Meta:
        ordering = ["date"]
        verbose_name_plural = "Product Images"

    def __str__(self):
        return "Image"
        

class HistoriquePrix(models.Model):
    marque = models.ForeignKey(Marque, on_delete=models.CASCADE, null=True)
    prix_achat = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
    prix_vente = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
    # Date of creation
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)
    
