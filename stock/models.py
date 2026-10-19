# stock/models.py
from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.db.models import F, Q


class Stock(models.Model):
    """
    Stock magasin d'une ProduitLine dans une bijouterie.

    ProduitLine.quantite :
        quantité historique reçue lors de l'achat.

    Stock.en_stock :
        quantité actuellement disponible dans le magasin,
        hors quantités affectées aux vendeurs.

    InventoryMovement :
        historique des entrées, affectations, ventes,
        retours et ajustements.
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
    )

    en_stock = models.PositiveIntegerField(
        default=0,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

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
            f"disponible:{self.en_stock}"
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

        elif (
            isinstance(self.en_stock, bool)
            or not isinstance(self.en_stock, int)
            or self.en_stock < 0
        ):
            errors["en_stock"] = (
                "La quantité disponible doit être "
                "un entier positif ou nul."
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

        update_fields = kwargs.get("update_fields")

        if update_fields is not None:
            update_fields = set(update_fields)

            if not update_fields:
                return

            # Conserver la clé calculée lors des sauvegardes
            # partielles modifiant les identifiants.
            if (
                "produit_line" in update_fields
                or "produit_line_id" in update_fields
                or "bijouterie" in update_fields
                or "bijouterie_id" in update_fields
            ):
                update_fields.add("stock_key")

            kwargs["update_fields"] = update_fields

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

    quantite_allouee :
        quantité totale attribuée au vendeur.

    quantite_vendue :
        quantité vendue et définitivement comptabilisée.

    quantite_disponible :
        quantite_allouee - quantite_vendue

    Règles :
    - Le vendeur appartient à la bijouterie du stock.
    - La quantité vendue ne dépasse jamais l'allocation.
    - Les quantités ne sont jamais négatives.
    - Un seul VendorStock par ProduitLine, vendeur
      et bijouterie.
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
        default=0,
    )

    quantite_vendue = models.PositiveIntegerField(
        default=0,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
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
                    quantite_allouee__gte=0,
                ),
                name="ck_vendorstock_allouee_gte_zero",
            ),
            models.CheckConstraint(
                condition=Q(
                    quantite_vendue__gte=0,
                ),
                name="ck_vendorstock_vendue_gte_zero",
            ),
            models.CheckConstraint(
                condition=Q(
                    quantite_vendue__lte=F(
                        "quantite_allouee"
                    ),
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
            f"disponible:{self.quantite_disponible}"
        )

    @property
    def quantite_disponible(self) -> int:
        return max(
            0,
            self.quantite_allouee - self.quantite_vendue,
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

        # ====================================================
        # 1. CHAMPS OBLIGATOIRES
        # ====================================================

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

        # ====================================================
        # 2. VALIDATION DES QUANTITÉS
        # ====================================================

        for field_name, label in (
            ("quantite_allouee", "La quantité allouée"),
            ("quantite_vendue", "La quantité vendue"),
        ):
            value = getattr(self, field_name)

            if value is None:
                errors[field_name] = (
                    f"{label} est obligatoire."
                )

            elif (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                errors[field_name] = (
                    f"{label} doit être un entier "
                    "positif ou nul."
                )

        allouee_valide = (
            "quantite_allouee" not in errors
        )
        vendue_valide = (
            "quantite_vendue" not in errors
        )

        if allouee_valide and vendue_valide:
            if self.quantite_vendue > self.quantite_allouee:
                errors["quantite_vendue"] = (
                    "La quantité vendue ne peut pas "
                    "dépasser la quantité allouée."
                )

        # ====================================================
        # 3. VÉRIFICATION VENDEUR / BIJOUTERIE
        # ====================================================

        if self.vendor_id and self.bijouterie_id:
            try:
                vendor_bijouterie_id = (
                    self.vendor.bijouterie_id
                )

            except ObjectDoesNotExist:
                errors["vendor"] = (
                    "Le vendeur sélectionné est introuvable."
                )

            else:
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

        # ====================================================
        # 4. ERREURS
        # ====================================================

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()

        return super().save(*args, **kwargs)
    

