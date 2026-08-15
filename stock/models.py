from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.db.models import F, Q


class Stock(models.Model):
    """
    Stock magasin d'une ProduitLine dans une bijouterie.

    quantite_totale :
        quantité cumulée entrée physiquement dans cette bijouterie :
        - PURCHASE_IN
        - RETURN_IN
        - ADJUSTMENT positif

        Elle ne diminue pas lors d'une affectation vendeur.

    en_stock :
        quantité actuellement disponible physiquement dans le magasin,
        hors quantités affectées aux vendeurs.
    """

    produit_line = models.ForeignKey(
        "purchase.ProduitLine",
        on_delete=models.PROTECT,
        related_name="stocks",
    )

    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        related_name="stocks_par_produitline",
    )

    stock_key = models.CharField(
        max_length=80,
        unique=True,
        null=True,
        blank=True,
        editable=False,
        db_index=True,
    )

    en_stock = models.PositiveIntegerField(default=0)
    quantite_totale = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "bijouterie_id",
            "produit_line_id",
            "id",
        ]

        constraints = [
            models.CheckConstraint(
                condition=Q(en_stock__gte=0),
                name="ck_stock_en_stock_gte_zero",
            ),
            models.CheckConstraint(
                condition=Q(quantite_totale__gte=0),
                name="ck_stock_quantite_totale_gte_zero",
            ),
            models.CheckConstraint(
                condition=Q(
                    quantite_totale__gte=F("en_stock")
                ),
                name="ck_stock_en_stock_lte_quantite_totale",
            ),
            models.UniqueConstraint(
                fields=[
                    "produit_line",
                    "bijouterie",
                ],
                name="uq_stock_produitline_bijouterie",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "bijouterie",
                    "produit_line",
                ],
                name="idx_stock_bij_pl",
            ),
            models.Index(
                fields=[
                    "bijouterie",
                    "en_stock",
                ],
                name="idx_stock_bij_dispo",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"PL#{self.produit_line_id} - "
            f"{self.bijouterie} - "
            f"disponible:{self.en_stock}/"
            f"entrées cumulées:{self.quantite_totale}"
        )

    def clean(self):
        super().clean()

        errors = {}

        if not self.produit_line_id:
            errors["produit_line"] = (
                "La ligne de produit est obligatoire."
            )

        if not self.bijouterie_id:
            errors["bijouterie"] = (
                "La bijouterie est obligatoire."
            )

        if self.en_stock is None:
            errors["en_stock"] = (
                "La quantité disponible est obligatoire."
            )
        elif self.en_stock < 0:
            errors["en_stock"] = (
                "La quantité disponible ne peut pas être négative."
            )

        if self.quantite_totale is None:
            errors["quantite_totale"] = (
                "La quantité totale est obligatoire."
            )
        elif self.quantite_totale < 0:
            errors["quantite_totale"] = (
                "La quantité totale ne peut pas être négative."
            )

        if (
            self.en_stock is not None
            and self.quantite_totale is not None
            and self.en_stock > self.quantite_totale
        ):
            errors["en_stock"] = (
                "La quantité disponible ne peut pas dépasser "
                "les quantités cumulées entrées en bijouterie."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.produit_line_id and self.bijouterie_id:
            self.stock_key = (
                f"PL:{self.produit_line_id}:"
                f"BIJ:{self.bijouterie_id}"
            )
        else:
            self.stock_key = None

        self.full_clean()

        return super().save(*args, **kwargs)

    @property
    def produit_id(self):
        return self.produit_line.produit_id

    @property
    def produit(self):
        return self.produit_line.produit

    @property
    def lot(self):
        return self.produit_line.lot


class VendorStock(models.Model):
    """
    Stock attribué à un vendeur pour une ProduitLine précise.

    Disponible vendeur :
        quantite_allouee - quantite_vendue
    """

    produit_line = models.ForeignKey(
        "purchase.ProduitLine",
        on_delete=models.PROTECT,
        related_name="vendor_stocks",
    )

    vendor = models.ForeignKey(
        "vendor.Vendor",
        on_delete=models.PROTECT,
        related_name="stocks",
    )

    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        related_name="vendor_stocks",
    )

    quantite_allouee = models.PositiveIntegerField(
        default=0
    )

    quantite_vendue = models.PositiveIntegerField(
        default=0
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = [
            "produit_line_id",
            "vendor_id",
            "id",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "produit_line",
                    "vendor",
                    "bijouterie",
                ],
                name="uq_vendorstock_pl_vendor_bij",
            ),
            models.CheckConstraint(
                condition=Q(
                    quantite_allouee__gte=0
                ),
                name="ck_vendorstock_allouee_gte_zero",
            ),
            models.CheckConstraint(
                condition=Q(
                    quantite_vendue__gte=0
                ),
                name="ck_vendorstock_vendue_gte_zero",
            ),
            models.CheckConstraint(
                condition=Q(
                    quantite_vendue__lte=F(
                        "quantite_allouee"
                    )
                ),
                name="ck_vendorstock_vendue_lte_allouee",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "vendor",
                    "bijouterie",
                ],
                name="idx_vendorstock_vendor_bij",
            ),
            models.Index(
                fields=[
                    "vendor",
                    "produit_line",
                ],
                name="idx_vendorstock_vendor_pl",
            ),
            models.Index(
                fields=[
                    "bijouterie",
                    "produit_line",
                ],
                name="idx_vendorstock_bij_pl",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.vendor} - "
            f"PL#{self.produit_line_id} - "
            f"stock:{self.en_stock}"
        )

    @property
    def en_stock(self) -> int:
        return max(
            0,
            int(self.quantite_allouee or 0)
            - int(self.quantite_vendue or 0),
        )

    @property
    def produit_id(self):
        return self.produit_line.produit_id

    @property
    def produit(self):
        return self.produit_line.produit

    @property
    def lot(self):
        return self.produit_line.lot

    def clean(self):
        super().clean()

        errors = {}

        if not self.produit_line_id:
            errors["produit_line"] = (
                "La ligne de produit est obligatoire."
            )

        if not self.vendor_id:
            errors["vendor"] = (
                "Le vendeur est obligatoire."
            )

        if not self.bijouterie_id:
            errors["bijouterie"] = (
                "La bijouterie est obligatoire."
            )

        if self.quantite_allouee is None:
            errors["quantite_allouee"] = (
                "La quantité allouée est obligatoire."
            )
        elif self.quantite_allouee < 0:
            errors["quantite_allouee"] = (
                "La quantité allouée ne peut pas être négative."
            )

        if self.quantite_vendue is None:
            errors["quantite_vendue"] = (
                "La quantité vendue est obligatoire."
            )
        elif self.quantite_vendue < 0:
            errors["quantite_vendue"] = (
                "La quantité vendue ne peut pas être négative."
            )

        if (
            self.quantite_allouee is not None
            and self.quantite_vendue is not None
            and self.quantite_vendue
            > self.quantite_allouee
        ):
            errors["quantite_vendue"] = (
                "La quantité vendue ne peut pas dépasser "
                "la quantité allouée."
            )

        if self.vendor_id and self.bijouterie_id:
            try:
                vendor_bijouterie_id = getattr(
                    self.vendor,
                    "bijouterie_id",
                    None,
                )
            except ObjectDoesNotExist:
                vendor_bijouterie_id = None
                errors["vendor"] = (
                    "Le vendeur sélectionné est introuvable."
                )

            if not vendor_bijouterie_id:
                errors["vendor"] = (
                    "Le vendeur n'est rattaché "
                    "à aucune bijouterie."
                )

            elif (
                vendor_bijouterie_id
                != self.bijouterie_id
            ):
                errors["bijouterie"] = (
                    "Le vendeur n'appartient pas "
                    "à cette bijouterie."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()

        return super().save(*args, **kwargs)
    
