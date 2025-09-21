import string
from decimal import Decimal
from random import SystemRandom

from django.db import models
from django.template.defaultfilters import slugify

from django.db.models import Q
from store.models import Produit, Bijouterie

# from shortuuid.django_fields import ShortUUIDField



from django.core.exceptions import ValidationError
from django.db import models

class Stock(models.Model):
    # un seul enregistrement de stock par produit
    produit = models.OneToOneField(
        Produit,
        on_delete=models.PROTECT,
        related_name="stock",
    )
    quantite = models.PositiveIntegerField(default=0)

    date_ajout = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Stock"
        verbose_name_plural = "Stocks"
        ordering = ["-id"]
        indexes = [models.Index(fields=["produit"])]

    def clean(self):
        if self.quantite < 0:
            raise ValidationError("La quantité doit être ≥ 0.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.produit} • qte={self.quantite}"


# add bijouterie


from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

class Stock(models.Model):
    produit = models.ForeignKey(
        Produit, on_delete=models.PROTECT, related_name="stocks"
    )
    bijouterie = models.ForeignKey(
        Bijouterie, on_delete=models.PROTECT, related_name="stocks"
    )
    quantite = models.PositiveIntegerField(default=0)

    date_ajout = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Stock"
        verbose_name_plural = "Stocks"
        ordering = ["-id"]
        constraints = [
            models.CheckConstraint(name="stock_quantite_gte_0", check=Q(quantite__gte=0)),
            # Un seul enregistrement par (produit, bijouterie)
            models.UniqueConstraint(
                fields=["produit", "bijouterie"],
                name="uniq_stock_produit_bijouterie",
            ),
        ]
        indexes = [models.Index(fields=["bijouterie", "produit"])]

    def clean(self):
        if self.quantite < 0:
            raise ValidationError("La quantité doit être ≥ 0.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.bijouterie} • {self.produit} • qte={self.quantite}"

    
# class Stock(models.Model):
#     produit = models.ForeignKey(Produit, on_delete=models.SET_NULL, null=True, blank=True)
#     quantite = models.PositiveIntegerField(default=0)
#     date_ajout = models.DateTimeField(auto_now_add=True) 
#     date_modification = models.DateTimeField(auto_now=True)
    
#     def save(self, *args, **kwargs):
#         if self.quantite < 0:  # or any other validation logic
#             raise ValueError("Quantite must be non-negative")
#         super().save(*args, **kwargs)
    
#     @property
#     def calcul_total_poids_achat(self):
#         total_poids_achat = self.produit.poids * self.quantite
#         return total_poids_achat
    
#     @property
#     def calcul_total_achat(self):
#         total_achat = Decimal((self.produit.poids * self.quantite) * self.prix_achat_gramme)
#         return total_achat

#     def __str__(self):
#         # return f"{self.produit} - {self.fournisseur}"
#         return f"{self.produit}"


# class Stock(models.Model):
#     produit = models.ForeignKey(
#         Produit, on_delete=models.PROTECT, related_name="stocks"
#     )
#     bijouterie = models.ForeignKey(
#         Bijouterie, on_delete=models.PROTECT, related_name="stocks"
#     )
#     quantite = models.PositiveIntegerField(default=0)
#     prix_achat_gramme = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

#     date_ajout = models.DateTimeField(auto_now_add=True)
#     date_modification = models.DateTimeField(auto_now=True)

#     class Meta:
#         verbose_name = "Stock"
#         verbose_name_plural = "Stocks"
#         ordering = ["-id"]
#         constraints = [
#             models.CheckConstraint(name="stock_quantite_gte_0", check=Q(quantite__gte=0)),
#             models.CheckConstraint(name="stock_prix_gte_0", check=Q(prix_achat_gramme__gte=0)),
#         ]
#         indexes = [
#             models.Index(fields=["bijouterie", "produit"]),
#         ]
#         # Un seul enregistrement de stock par produit et par magasin :
#         unique_together = ("produit", "bijouterie")

#     def clean(self):
#         # si ton Produit a déjà un lien bijouterie unique, tu peux imposer la cohérence :
#         # if self.produit.bijouterie and self.produit.bijouterie_id != self.bijouterie_id:
#         #     raise ValidationError("Le produit n'appartient pas à cette bijouterie.")
#         pass

#     def save(self, *args, **kwargs):
#         # PositiveIntegerField empêche déjà les négatifs, mais on garde la garde-fou :
#         if self.quantite < 0:
#             raise ValueError("Quantité invalide (négative).")
#         super().save(*args, **kwargs)

#     @property
#     def calcul_total_poids_achat(self) -> Decimal:
#         if not self.produit:
#             return Decimal("0")
#         # produit.poids est un DecimalField → multiplication sûre
#         return (self.produit.poids or Decimal("0")) * Decimal(self.quantite)

#     @property
#     def calcul_total_achat(self) -> Decimal:
#         if not self.produit:
#             return Decimal("0")
#         return (self.produit.poids or Decimal("0")) * Decimal(self.quantite) * (self.prix_achat_gramme or Decimal("0"))

#     def __str__(self):
#         return f"{self.bijouterie} • {self.produit} • qte={self.quantite}"

# class Stock(models.Model):
#     produit = models.ForeignKey(
#         Produit, on_delete=models.PROTECT, related_name="stocks"
#     )
#     bijouterie = models.ForeignKey(
#         Bijouterie, on_delete=models.PROTECT, related_name="stocks"
#     )
#     quantite = models.PositiveIntegerField(default=0)
#     prix_achat_gramme = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

#     date_ajout = models.DateTimeField(auto_now_add=True)
#     date_modification = models.DateTimeField(auto_now=True)

#     class Meta:
#         verbose_name = "Stock"
#         verbose_name_plural = "Stocks"
#         ordering = ["-id"]
#         constraints = [
#             models.CheckConstraint(name="stock_quantite_gte_0", check=Q(quantite__gte=0)),
#             models.CheckConstraint(name="stock_prix_gte_0", check=Q(prix_achat_gramme__gte=0)),
#         ]
#         indexes = [
#             models.Index(fields=["bijouterie", "produit"]),
#         ]
#         # Un seul enregistrement de stock par produit et par magasin :
#         unique_together = ("produit", "bijouterie")

#     def clean(self):
#         # si ton Produit a déjà un lien bijouterie unique, tu peux imposer la cohérence :
#         # if self.produit.bijouterie and self.produit.bijouterie_id != self.bijouterie_id:
#         #     raise ValidationError("Le produit n'appartient pas à cette bijouterie.")
#         pass

#     def save(self, *args, **kwargs):
#         # PositiveIntegerField empêche déjà les négatifs, mais on garde la garde-fou :
#         if self.quantite < 0:
#             raise ValueError("Quantité invalide (négative).")
#         super().save(*args, **kwargs)

#     # @property
#     # def calcul_total_poids_achat(self) -> Decimal:
#     #     if not self.produit:
#     #         return Decimal("0")
#     #     # produit.poids est un DecimalField → multiplication sûre
#     #     return (self.produit.poids or Decimal("0")) * Decimal(self.quantite)

#     @property
#     def calcul_total_achat(self) -> Decimal:
#         if not self.produit:
#             return Decimal("0")
#         return (self.produit.poids or Decimal("0")) * Decimal(self.quantite) * (self.prix_achat_gramme or Decimal("0"))

#     def __str__(self):
#         return f"{self.bijouterie} • {self.produit} • qte={self.quantite}"


class Stock(models.Model):
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, related_name="stocks")
    bijouterie = models.ForeignKey(Bijouterie, on_delete=models.PROTECT, related_name="stocks")
    quantite = models.PositiveIntegerField(default=0)
    prix_achat_gramme = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    date_ajout = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Stock"
        verbose_name_plural = "Stocks"
        ordering = ["-id"]
        constraints = [
            models.CheckConstraint(name="stock_quantite_gte_0", check=Q(quantite__gte=0)),
            models.CheckConstraint(name="stock_prix_gte_0", check=Q(prix_achat_gramme__gte=0)),
            models.UniqueConstraint(fields=["produit", "bijouterie"], name="uniq_stock_produit_bijouterie"),
        ]
        indexes = [models.Index(fields=["bijouterie", "produit"])]

    def clean(self):
        if self.quantite < 0:
            raise ValidationError("La quantité doit être ≥ 0.")

    def save(self, *args, **kwargs):
        self.full_clean()   # active clean() + validations de champs
        super().save(*args, **kwargs)

    @property
    def calcul_total_poids_achat(self) -> Decimal:
        if not self.produit:
            return Decimal("0")
        return (self.produit.poids or Decimal("0")) * Decimal(self.quantite)

    @property
    def calcul_total_achat(self) -> Decimal:
        if not self.produit:
            return Decimal("0")
        return (self.produit.poids or Decimal("0")) * Decimal(self.quantite) * (self.prix_achat_gramme or Decimal("0"))

    def __str__(self):
        return f"{self.bijouterie} • {self.produit} • qte={self.quantite}"
