from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q


class Stock(models.Model):
    """
    Stock par ligne de lot et par bijouterie.
    - Réserve = bijouterie NULL
    - Quantités uniquement
    Invariants: disponible <= allouée, (produit_line, bijouterie) unique
    """
    produit_line = models.ForeignKey(
        "purchase.ProduitLine",
        on_delete=models.CASCADE,
        related_name="stocks",
    )
    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="stocks_par_produitline",  # NULL = Réserve
    )

    quantite_allouee = models.PositiveIntegerField(null=True, blank=True, default=None)
    quantite_disponible = models.PositiveIntegerField(null=True, blank=True, default=None)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # pratique pour l’audit

    class Meta:
        indexes = [
            models.Index(fields=["bijouterie"]),
            models.Index(fields=["produit_line", "bijouterie"]),
        ]
        constraints = [
            # 1 seul enregistrement par (ligne, bijouterie)
            models.UniqueConstraint(
                fields=["produit_line", "bijouterie"],
                name="uq_stock_pl_bijouterie",
            ),
            # disponible <= allouée (ou tous deux NULL)
            models.CheckConstraint(
                check=(
                    models.Q(quantite_allouee__isnull=True, quantite_disponible__isnull=True)
                    | models.Q(quantite_allouee__gte=models.F("quantite_disponible"))
                ),
                name="ck_stock_qty_disp_lte_alloue",
            ),
        ]
        verbose_name = "Stock (bijouterie)"
        verbose_name_plural = "Stocks (bijouterie)"

    # ---------- Validation applicative ----------
    def clean(self):
        # Autoriser (None, None) – utile comme placeholder au début
        if self.quantite_allouee is None and self.quantite_disponible is None:
            return
        if self.quantite_allouee is not None and self.quantite_allouee < 0:
            raise ValidationError({"quantite_allouee": "Doit être ≥ 0."})
        if self.quantite_disponible is not None and self.quantite_disponible < 0:
            raise ValidationError({"quantite_disponible": "Doit être ≥ 0."})
        if (
            self.quantite_allouee is not None
            and self.quantite_disponible is not None
            and self.quantite_disponible > self.quantite_allouee
        ):
            raise ValidationError("quantite_disponible ne peut pas dépasser quantite_allouee.")

    # ---------- Helpers ----------
    @property
    def est_reserve(self) -> bool:
        return self.bijouterie_id is None

    def incremente(self, *, qte: int, save=True):
        if qte is None or qte <= 0:
            raise ValidationError("qte doit être > 0.")
        self.quantite_allouee = (self.quantite_allouee or 0) + int(qte)
        self.quantite_disponible = (self.quantite_disponible or 0) + int(qte)
        if save:
            self.full_clean()
            self.save(update_fields=["quantite_allouee", "quantite_disponible", "updated_at"])

    def decremente_disponible(self, *, qte: int, save=True):
        if qte is None or qte <= 0:
            raise ValidationError("qte doit être > 0.")
        new_disp = (self.quantite_disponible or 0) - int(qte)
        if new_disp < 0:
            raise ValidationError("Stock disponible insuffisant.")
        self.quantite_disponible = new_disp
        if save:
            self.full_clean()
            self.save(update_fields=["quantite_disponible", "updated_at"])

    def transferer_vers(self, autre: "Stock", *, qte: int, save=True):
        """
        Transfère du disponible de self → autre (même produit_line).
        N’affecte pas 'allouée' côté source; incrémente 'allouée' & 'disponible' côté destination.
        """
        if autre.produit_line_id != self.produit_line_id:
            raise ValidationError("Transfer: produit_line différent.")
        if qte is None or qte <= 0:
            raise ValidationError("qte doit être > 0.")
        # décrémente source (disponible)
        self.decremente_disponible(qte=qte, save=False)
        # incrémente destination (allouée & disponible)
        autre.incremente(qte=qte, save=False)
        if save:
            self.full_clean()
            autre.full_clean()
            self.save(update_fields=["quantite_disponible", "updated_at"])
            autre.save(update_fields=["quantite_allouee", "quantite_disponible", "updated_at"])

    def __str__(self):
        cible = getattr(self.bijouterie, "nom", None) if self.bijouterie_id else "Réserve"
        return f"Stock(PL={self.produit_line_id} → {cible})"


class VendorStock(models.Model):
    """
    Stock logique par vendeur et par ligne produit (ProduitLine).
    - quantite_allouee : total affecté au vendeur (VENDOR_ASSIGN)
    - quantite_vendue  : total vendu confirmé (SALE_OUT confirmé)
    - quantite_disponible = quantite_allouee - quantite_vendue (calculé)
    """
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

    quantite_allouee = models.PositiveIntegerField(default=0)
    quantite_vendue = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["produit_line", "vendor"],
                name="uq_vendorstock_pl_vendor",
            ),
            models.CheckConstraint(
                check=Q(quantite_allouee__gte=0) &
                      Q(quantite_vendue__gte=0) &
                      Q(quantite_vendue__lte=F("quantite_allouee")),
                name="ck_vendorstock_nonneg_and_vendue_lte_allouee",
            ),
        ]
        indexes = [
            models.Index(fields=["vendor"]),
            models.Index(fields=["produit_line"]),
        ]
        verbose_name = "Stock vendeur"
        verbose_name_plural = "Stocks vendeur"

    # --------- Propriétés ---------
    @property
    def quantite_disponible(self) -> int:
        return max(0, int(self.quantite_allouee) - int(self.quantite_vendue))

    # --------- Helpers (utiles en scripts/tests ; en prod, préférez des services @transaction.atomic) ---------
    def add_allocation(self, qte: int, save=True):
        """Incrémente l'alloué (utiliser lors d’un VENDOR_ASSIGN)."""
        if not qte or qte <= 0:
            raise ValidationError("qte doit être > 0.")
        self.quantite_allouee += int(qte)
        if save:
            self.full_clean()
            self.save(update_fields=["quantite_allouee", "updated_at"])

    def add_sale(self, qte: int, save=True):
        """Incrémente le vendu (utiliser lors d’un SALE_OUT confirmé)."""
        if not qte or qte <= 0:
            raise ValidationError("qte doit être > 0.")
        nv = self.quantite_vendue + int(qte)
        if nv > self.quantite_allouee:
            raise ValidationError("Vente dépasse l'alloué vendeur.")
        self.quantite_vendue = nv
        if save:
            self.full_clean()
            self.save(update_fields=["quantite_vendue", "updated_at"])

    def __str__(self):
        return f"VendorStock(PL={self.produit_line_id} → Vendor={self.vendor_id}, disp={self.quantite_disponible})"


