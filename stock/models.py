from django.core.exceptions import ValidationError
from django.db import models
from store.models import Produit, Bijouterie

# class Stock(models.Model):
#     produit = models.ForeignKey(
#         Produit, on_delete=models.PROTECT, related_name="stocks"
#     )
#     # NULL = non attribué (réservé)
#     bijouterie = models.ForeignKey(
#         Bijouterie, on_delete=models.PROTECT, null=True, blank=True, related_name="stocks"
#     )
#     # True = non attribué ; False = attribué
#     is_reserved = models.BooleanField(default=True, help_text="True = non attribué à une bijouterie")
#     quantite = models.PositiveIntegerField(default=0)

#     date_ajout = models.DateTimeField(auto_now_add=True)
#     date_modification = models.DateTimeField(auto_now=True)

#     class Meta:
#         verbose_name = "Stock"
#         verbose_name_plural = "Stocks"
#         ordering = ["-id"]
#         constraints = [
#             models.CheckConstraint(name="stock_quantite_gte_0", check=Q(quantite__gte=0)),
#             # Cohérence d'état
#             models.CheckConstraint(
#                 name="stock_reserved_vs_bijouterie",
#                 check=(Q(is_reserved=True, bijouterie__isnull=True) | Q(is_reserved=False, bijouterie__isnull=False)),
#             ),
#             # Un seul stock “non attribué” par produit
#             models.UniqueConstraint(
#                 fields=["produit"],
#                 condition=Q(is_reserved=True, bijouterie__isnull=True),
#                 name="uniq_stock_reserve_par_produit",
#             ),
#             # Un seul stock attribué par (produit, bijouterie)
#             models.UniqueConstraint(
#                 fields=["produit", "bijouterie"],
#                 condition=Q(is_reserved=False, bijouterie__isnull=False),
#                 name="uniq_stock_produit_bijouterie",
#             ),
#         ]
#         indexes = [models.Index(fields=["is_reserved", "bijouterie", "produit"])]

#     def clean(self):
#         if self.quantite < 0:
#             raise ValidationError("La quantité doit être ≥ 0.")
#         if self.is_reserved and self.bijouterie_id is not None:
#             raise ValidationError("Stock non attribué ⇒ bijouterie doit être vide.")
#         if not self.is_reserved and self.bijouterie_id is None:
#             raise ValidationError("Stock attribué ⇒ bijouterie requise.")

#     def save(self, *args, **kwargs):
#         self.full_clean()
#         return super().save(*args, **kwargs)

#     def __str__(self):
#         cible = self.bijouterie or "Non attribué"
#         return f"{cible} • {self.produit} • qte={self.quantite}"


class Stock(models.Model):
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, related_name="stocks")
    # NULL = non attribué (réservé)
    bijouterie = models.ForeignKey(Bijouterie, on_delete=models.PROTECT, null=True, blank=True, related_name="stocks")

    # True = non attribué ; False = attribué
    is_reserved = models.BooleanField(default=True, help_text="True = non attribué à une bijouterie")
    quantite = models.PositiveIntegerField(default=0)

    # 👉 clé technique MySQL : 1 seule ligne 'réservée' par produit
    reservation_key = models.CharField(max_length=32, null=True, blank=True, unique=True, editable=False)

    date_ajout = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Stock"
        verbose_name_plural = "Stocks"
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(fields=["produit", "bijouterie"],
                                    name="uniq_stock_produit_bijouterie"),
        ]
        indexes = [
            models.Index(fields=["produit"]),
            models.Index(fields=["bijouterie"]),
            models.Index(fields=["is_reserved"]),
            # ❌ pas d'index supplémentaire sur reservation_key (déjà unique)
        ]

    def clean(self):
        if self.quantite < 0:
            raise ValidationError("La quantité doit être ≥ 0.")
        # Cohérence d’état côté application (MySQL n’applique pas CHECK < 8.0.16)
        if self.is_reserved and self.bijouterie_id is not None:
            raise ValidationError("Stock non attribué ⇒ bijouterie doit être vide.")
        if not self.is_reserved and self.bijouterie_id is None:
            raise ValidationError("Stock attribué ⇒ bijouterie requise.")

    def save(self, *args, **kwargs):
    # Déduire l’état réservé/attribué depuis bijouterie
        self.is_reserved = self.bijouterie_id is None

        if self.is_reserved:
            self.bijouterie_id = None
            self.reservation_key = f"RES-{self.produit_id}" if self.produit_id else None
        else:
            self.reservation_key = None

        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        cible = self.bijouterie or "Non attribué"
        return f"{cible} • {self.produit} • qte={self.quantite}"
