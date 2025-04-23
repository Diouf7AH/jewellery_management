import string
from random import SystemRandom

from django.db import models
from django.utils.html import mark_safe
from django.utils.text import slugify

from employee.models import Employee
from store.models import Bijouterie, Produit
from userauths.models import User, user_directory_path


# Create your models here.
class Vendor(Employee):
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, related_name="user_vendor")
    bijouterie = models.ForeignKey(Bijouterie, related_name="bijouterie", on_delete=models.SET_NULL, null=True, blank=True)
    verifie = models.BooleanField(default=True)
    raison_desactivation = models.TextField(null=True, blank=True)
    slug = models.SlugField(unique=True, max_length=50, null=True, blank=True)
    
    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name}" if self.user else "Vendeur inconnu"

    def save(self, *args, **kwargs):
        if not self.slug:
            rand_letters = ''.join(SystemRandom().choices(string.ascii_letters + string.digits, k=15))
            self.slug = slugify(rand_letters)
        super().save(*args, **kwargs) 


# VendorProduct is a many-to-many relationship between Product and Vendor 
# that includes the quantity
class VendorProduit(models.Model):
    # related_name='vendor_produits'vous permet d'accéder à tous les produits 
    # liés à un fournisseur à partir du Vendormodèle (c'est-à-dire vendor.products.all()).
    vendor = models.ForeignKey(Vendor, related_name="vendor_produits", on_delete=models.SET_NULL, null=True, blank=True)
    # related_name='vendor_vendors'vous permet d'accéder à tous les vendeur 
    # liés à un produit à partir du Productmodèle (c'est-à-dire product.vendors.all())
    produit = models.ForeignKey(Produit, related_name="vendor_vendors", on_delete=models.SET_NULL, null=True, blank=True)
    quantite = models.PositiveIntegerField()
    # stock_out = models.PositiveIntegerField()
    
    class Meta:
        unique_together = ('vendor', 'produit')  # Prevents duplicate entries of the same product for the same vendor
    
    def __str__(self):
        if self.vendor and self.vendor.user:
            return f'{self.vendor.bijouterie} - {self.vendor.user.first_name} - {self.vendor.user.last_name} - {self.quantite}'
        return f"Produit de vendeur inconnu ({self.produit})"
