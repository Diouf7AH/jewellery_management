import string
from random import SystemRandom

from django.db import models
from django.utils.html import mark_safe
from django.utils.text import slugify
from django.conf import settings
from employee.models import Employee
from store.models import Bijouterie, Produit
from userauths.models import User

from django.db import IntegrityError, transaction
import string
from random import SystemRandom
from staff.models import StaffCore


# class Vendor(StaffCore):
#     class Meta:
#         verbose_name = "Vendeur"
#         verbose_name_plural = "Vendeurs"
#         ordering = ["-id"]

#     def __str__(self):
#         return f"Vendeur: {getattr(self.user, 'email', self.pk)}"

class Vendor(StaffCore):
    # Ici on fixe les reverse names EXACTS voulus pour Vendor
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="staff_vendor_profile",    # ✅ user.staff_vendor_profile
        related_query_name="vendor_profile",
    )
    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="vendors",                 # ✅ bijouterie.vendor.all()
        related_query_name="vendor",
    )

    class Meta:
        verbose_name = "Vendor"
        verbose_name_plural = "Vendors"
        ordering = ["-id"]

    def __str__(self):
        return f"Vendor {getattr(self.user, 'username', self.user_id) if self.user else '#'+str(self.pk)}"


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
