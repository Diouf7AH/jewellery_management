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

# Create your models here.
# class Vendor(Employee):
#     user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, related_name="user_vendor")
#     bijouterie = models.ForeignKey(Bijouterie, related_name="bijouterie", on_delete=models.SET_NULL, null=True, blank=True)
#     verifie = models.BooleanField(default=True)
#     raison_desactivation = models.TextField(null=True, blank=True)
#     slug = models.SlugField(unique=True, max_length=20, null=True, blank=True)
    
#     def __str__(self):
#         return f"{self.user.first_name} {self.user.last_name}" if self.user else "Vendeur inconnu"

#     def save(self, *args, **kwargs):
#         if not self.slug and self.user:
#             base = slugify(f"{self.user.first_name}-{self.user.last_name}")
#             suffix = ''.join(SystemRandom().choices(string.digits, k=4))
#             self.slug = f"{base}-{suffix}"[:20]  # assure-toi que ça ne dépasse pas 20
#         elif not self.slug:
#             rand_letters = ''.join(SystemRandom().choices(string.ascii_lowercase + string.digits, k=15))
#             self.slug = slugify(rand_letters)
#         super().save(*args, **kwargs)


# class Vendor(Employee):
#     user = models.OneToOneField(
#         User,
#         on_delete=models.SET_NULL,   # ou PROTECT si tu veux empêcher la suppression du User
#         null=True,
#         related_name="vendor_profile",
#     )
#     # ⚠️ n'ajoute PAS un nouveau champ bijouterie si Employee en a déjà un.
#     # Si tu tiens à le garder ici, supprime-le d'Employee et renomme le related_name :
#     # bijouterie = models.ForeignKey(
#     #     Bijouterie, on_delete=models.SET_NULL, null=True, blank=True, related_name="vendors"
#     # )

#     verifie = models.BooleanField(default=True)
#     raison_desactivation = models.TextField(null=True, blank=True)

#     slug = models.SlugField(unique=True, max_length=20, null=True, blank=True)

#     class Meta:
#         verbose_name = "Vendeur"
#         verbose_name_plural = "Vendeurs"
#         ordering = ["-id"]
#         indexes = [models.Index(fields=["slug"])]

#     def __str__(self):
#         if self.user:
#             full = " ".join(filter(None, [self.user.first_name, self.user.last_name])).strip()
#             return full or (self.user.email or f"Vendor #{self.pk}")
#         return self.slug or f"Vendor #{self.pk}"

#     def _build_base_slug(self):
#         if self.user:
#             base_txt = "-".join(filter(None, [self.user.first_name, self.user.last_name])) or (self.user.email or "vendor")
#         else:
#             base_txt = "vendor"
#         return slugify(base_txt)

#     def save(self, *args, **kwargs):
#         # Génère un slug unique si manquant
#         if not self.slug:
#             base = self._build_base_slug()
#             # Assure max_length=20 tout en gardant la place pour un suffixe
#             base = (base or "vendor")[:14].rstrip("-")
#             for _ in range(20):  # 20 essais suffisent largement
#                 suffix = ''.join(SystemRandom().choices(string.digits, k=4))
#                 candidate = f"{base}-{suffix}"
#                 if not Vendor.objects.filter(slug=candidate).exists():
#                     self.slug = candidate
#                     break
#             else:
#                 # fallback ultra rare
#                 self.slug = ''.join(SystemRandom().choices(string.ascii_lowercase + string.digits, k=20))

#         super().save(*args, **kwargs)



# class StaffProfile(Employee):  # hérite d'Employee pour (bijouterie, image, active, etc.)
#     class Meta:
#         abstract = True

#     user = models.OneToOneField(
#         User,
#         on_delete=models.PROTECT,   # protège la cohérence
#         null=False,
#         related_name="%(class)s_profile",  # ex: vendor_profile / cashier_profile
#     )
#     verifie = models.BooleanField(default=True)
#     raison_desactivation = models.TextField(null=True, blank=True)
#     slug = models.SlugField(unique=True, max_length=20, null=True, blank=True)

#     def __str__(self):
#         if self.user:
#             full = " ".join(filter(None, [self.user.first_name, self.user.last_name])).strip()
#             return full or (self.user.email or f"{self.__class__.__name__} #{self.pk}")
#         return self.slug or f"{self.__class__.__name__} #{self.pk}"

#     def _build_base_slug(self):
#         if self.user:
#             base_txt = "-".join(filter(None, [self.user.first_name, self.user.last_name])) or (self.user.email or self.__class__.__name__)
#         else:
#             base_txt = self.__class__.__name__
#         return slugify(base_txt)

#     def save(self, *args, **kwargs):
#         if not self.slug:
#             base = (self._build_base_slug() or self.__class__.__name__).lower()[:14].rstrip("-")
#             for _ in range(20):
#                 suffix = ''.join(SystemRandom().choices(string.digits, k=4))
#                 candidate = f"{base}-{suffix}"
#                 if not self.__class__.objects.exclude(pk=self.pk).filter(slug=candidate).exists():
#                     self.slug = candidate
#                     break
#             else:
#                 self.slug = ''.join(SystemRandom().choices(string.ascii_lowercase + string.digits, k=20))
#         super().save(*args, **kwargs)


class StaffProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="%(class)s_profile",
    )
    bijouterie = models.ForeignKey(
        Bijouterie,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="%(class)ss",
    )
    verifie = models.BooleanField(default=True)
    raison_desactivation = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ➜ Alias pratique : continue d'exposer .slug mais via User
    @property
    def slug(self):
        return getattr(self.user, "slug", None)

    class Meta:
        abstract = True
        indexes = [models.Index(fields=["verifie"])]



class Vendor(StaffProfile):
    class Meta:
        verbose_name = "Vendeur"
        verbose_name_plural = "Vendeurs"
        ordering = ["-id"]

    def __str__(self):
        return f"Vendeur: {getattr(self.user, 'email', self.pk)}"


class Cashier(StaffProfile):
    class Meta:
        verbose_name = "Caissier"
        verbose_name_plural = "Caissiers"
        ordering = ["-id"]

    def __str__(self):
        email = getattr(self.user, "email", None) if self.user else None
        return f"Caissier: {email or self.pk}"



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
