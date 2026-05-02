from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q


class Stock(models.Model):
    produit_line = models.ForeignKey(
        "purchase.ProduitLine", on_delete=models.CASCADE, related_name="stocks"
    )
    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="stocks_par_produitline",
    )

    # auto-calculé
    is_reserve = models.BooleanField(default=False, db_index=True, editable=False)

    # stock réel dispo
    en_stock = models.PositiveIntegerField(default=0)

    # stock total / plafond (doit être >= en_stock)
    quantite_totale = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["produit_line"],
                condition=Q(is_reserve=True),
                name="uq_stock_one_reserve_per_pl",
            ),
            models.UniqueConstraint(
                fields=["produit_line", "bijouterie"],
                condition=Q(is_reserve=False),
                name="uq_stock_pl_bijouterie_non_reserve",
            ),
            models.CheckConstraint(
                check=Q(is_reserve=True, bijouterie__isnull=True)
                      | Q(is_reserve=False, bijouterie__isnull=False),
                name="ck_stock_is_reserve_matches_bijouterie_null",
            ),
            models.CheckConstraint(
                check=Q(quantite_totale__gte=F("en_stock")),
                name="ck_stock_en_stock_lte_quantite_totale",
            ),
        ]

    def clean(self):
        super().clean()

        # toujours recalculer
        self.is_reserve = (self.bijouterie_id is None)

        if self.en_stock > self.quantite_totale:
            raise ValidationError({"en_stock": "en_stock ne peut pas dépasser quantite_totale."})

    def save(self, *args, **kwargs):
        # recalcul avant validation
        self.is_reserve = (self.bijouterie_id is None)
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def est_reserve(self) -> bool:
        return self.is_reserve

    @property
    def produit_id(self):
        return self.produit_line.produit_id

    @property
    def produit(self):
        return self.produit_line.produit


class VendorStock(models.Model):
    produit_line = models.ForeignKey(
        "purchase.ProduitLine",
        on_delete=models.CASCADE,
        related_name="vendor_stocks",
    )

    vendor = models.ForeignKey(
        "vendor.Vendor",
        on_delete=models.CASCADE,
        related_name="stocks",
    )

    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        related_name="vendor_stocks",
    )

    quantite_allouee = models.PositiveIntegerField(default=0)
    quantite_vendue = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["produit_line_id", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["produit_line", "vendor", "bijouterie"],
                name="uq_vendorstock_pl_vendor_bij",
            ),
            models.CheckConstraint(
                check=Q(quantite_allouee__gte=0)
                & Q(quantite_vendue__gte=0)
                & Q(quantite_vendue__lte=F("quantite_allouee")),
                name="ck_vendorstock_valid_quantities",
            ),
        ]
        indexes = [
            models.Index(fields=["vendor", "bijouterie"]),
            models.Index(fields=["vendor", "produit_line"]),
            models.Index(fields=["bijouterie", "produit_line"]),
        ]

    def __str__(self):
        return f"{self.vendor} - PL#{self.produit_line_id} - stock:{self.en_stock}"

    @property
    def en_stock(self) -> int:
        return max(0, int(self.quantite_allouee) - int(self.quantite_vendue))

    @property
    def produit(self):
        return self.produit_line.produit

    @property
    def lot(self):
        return self.produit_line.lot

    def clean(self):
        super().clean()

        if self.quantite_vendue > self.quantite_allouee:
            raise ValidationError({
                "quantite_vendue": "La quantité vendue ne peut pas dépasser la quantité allouée."
            })

        if self.vendor_id and self.bijouterie_id:
            vendor_bijouterie_id = getattr(self.vendor, "bijouterie_id", None)
            if vendor_bijouterie_id and vendor_bijouterie_id != self.bijouterie_id:
                raise ValidationError({
                    "bijouterie": "Le vendeur n'appartient pas à cette bijouterie."
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

