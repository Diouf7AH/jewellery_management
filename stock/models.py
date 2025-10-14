from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Stock(models.Model):
    produit = models.ForeignKey('store.Produit', on_delete=models.PROTECT, related_name='stocks', db_index=True)

    bijouterie = models.ForeignKey(
        'store.Bijouterie',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='stocks',
        db_index=True,
    )
    lot = models.ForeignKey(
        'purchase.Lot',
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='stocks',
        db_index=True,
    )

    # Réserve: bijouterie = NULL ; clé lisible unique
    reservation_key = models.CharField(max_length=64, null=True, blank=True)

    # Unité unique: PIÈCES
    quantite = models.PositiveIntegerField(default=0)

    is_reserved = models.BooleanField(default=True)

    class Meta:
        ordering = ['-id']
        constraints = [
            # Unicité (produit, bijouterie, lot) pour le stock AFFECTÉ (en boutique)
            models.UniqueConstraint(
                fields=['produit', 'bijouterie', 'lot'],
                condition=Q(is_reserved=False),
                name='uniq_stock_prod_bij_lot_when_assigned',
            ),
            models.CheckConstraint(name='ck_stock_qty_gt_0', check=Q(quantite__gt=0)),
            # Cohérence is_reserved <-> bijouterie NULL
            models.CheckConstraint(
                name='ck_reserved_matches_bijouterie_null',
                check=(Q(is_reserved=True, bijouterie__isnull=True) |
                       Q(is_reserved=False, bijouterie__isnull=False)),
            ),
            # Unicité de la réserve par clé lisible
            models.UniqueConstraint(
                fields=['reservation_key'],
                condition=Q(is_reserved=True),
                name='uniq_reservation_key_when_reserved',
            ),
        ]
        indexes = [
            models.Index(fields=['produit']),
            models.Index(fields=['bijouterie']),
            models.Index(fields=['lot']),
            models.Index(fields=['is_reserved']),
        ]

    def clean(self):
        # Cohérence réserve/bijouterie
        if self.is_reserved and self.bijouterie_id is not None:
            raise ValidationError({'bijouterie': "Doit être NULL quand is_reserved=True."})
        if not self.is_reserved and self.bijouterie_id is None:
            raise ValidationError({'bijouterie': "Obligatoire quand is_reserved=False."})

        # Quantité strictement positive
        if (self.quantite or 0) <= 0:
            raise ValidationError({"quantite": "Doit être > 0."})

        # Si lot fourni, le produit doit matcher
        if self.lot_id and self.produit_id and self.lot.produit_id != self.produit_id:
            raise ValidationError({"produit": "Le produit ne correspond pas à celui du lot."})

    def save(self, *args, **kwargs):
        # Source de vérité : bijouterie -> is_reserved
        self.is_reserved = (self.bijouterie_id is None)
        # Clé unique lisible pour la réserve
        self.reservation_key = f"RES-{self.produit_id}-{self.lot_id or 'NOLOT'}" if self.is_reserved else None
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        scope = "RESERVED" if self.is_reserved else f"BIJ#{self.bijouterie_id}"
        return f"Stock(p#{self.produit_id}, lot={self.lot_id or '-'}, {scope}) = {self.quantite} pcs"
