from django.core.exceptions import ValidationError
from django.db import models
from store.models import Produit, Bijouterie
from django.db.models import Q

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
    bijouterie = models.ForeignKey(Bijouterie, on_delete=models.PROTECT, null=True, blank=True, related_name="stocks")
    lot = models.ForeignKey('purchase.AchatProduitLot', null=True, blank=True,
                            on_delete=models.PROTECT, related_name='stocks')  # PROTECT conseillé
    reservation_key = models.CharField(max_length=64, null=True, blank=True, db_index=True)  # ❗ plus unique
    quantite = models.PositiveIntegerField(default=0)
    is_reserved = models.BooleanField(default=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(fields=["produit", "bijouterie", "lot"],
                                    name="uniq_stock_prod_bij_lot"),  # ✅ remplace l’ancienne
            models.CheckConstraint(check=Q(quantite__gte=0), name="stock_qty_gte_0"),
        ]
        indexes = [
            models.Index(fields=["produit", "bijouterie"]),
            models.Index(fields=["lot"]),
            models.Index(fields=["is_reserved"]),
        ]

    def save(self, *args, **kwargs):
        self.is_reserved = self.bijouterie_id is None
        if self.is_reserved:
            self.bijouterie_id = None
            # clé lisible (non unique) utile pour MySQL
            self.reservation_key = f"RES-{self.produit_id}-{self.lot_id or 'NOLOT'}" if self.produit_id else None
        else:
            self.reservation_key = None
        self.full_clean()
        return super().save(*args, **kwargs)


    