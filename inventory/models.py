# inventory/models.py
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class MovementType(models.TextChoices):
    PURCHASE_IN     = "PURCHASE_IN", "Entrée achat"
    CANCEL_PURCHASE = "CANCEL_PURCHASE", "Annulation achat (sortie)"
    ALLOCATE        = "ALLOCATE", "Affectation réservé → bijouterie"
    TRANSFER        = "TRANSFER", "Transfert entre bijouteries"
    ADJUSTMENT      = "ADJUSTMENT", "Ajustement manuel"
    SALE_OUT        = "SALE_OUT", "Sortie vente"
    RETURN_IN       = "RETURN_IN", "Retour client (entrée)"
    CANCEL_SALE     = "CANCEL_SALE", "Annulation vente"
    VENDOR_ASSIGN   = "VENDOR_ASSIGN", "Affectation à un vendeur"
    RECEIVE         = "RECEIVE", "Mise en rayon (rend vendable)"

class Bucket(models.TextChoices):
    EXTERNAL   = "EXTERNAL", "Externe (hors système)"
    RESERVED   = "RESERVED", "Réservé (bijouterie=NULL)"
    BIJOUTERIE = "BIJOUTERIE", "Bijouterie"


class InventoryMovement(models.Model):
    # ----- Quoi -----
    produit = models.ForeignKey(
        "store.Produit",
        on_delete=models.PROTECT,
        related_name="movements",
    )
    movement_type = models.CharField(max_length=32, choices=MovementType.choices)

    qty = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Traçabilité lot
    lot = models.ForeignKey("purchase.Lot", null=True, blank=True, on_delete=models.SET_NULL)
    reason = models.TextField(null=True, blank=True)

    # ----- D’où → vers -----
    src_bucket = models.CharField(max_length=16, choices=Bucket.choices, null=True, blank=True)
    src_bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movements_as_source",
    )
    dst_bucket = models.CharField(max_length=16, choices=Bucket.choices, null=True, blank=True)
    dst_bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movements_as_destination",
    )
    
    # ✅ Référence achat
    achat_ligne = models.ForeignKey(
        "purchase.ProduitLine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements",
    )

    # ✅ Référence FIFO/lot
    produit_line = models.ForeignKey(
        "purchase.ProduitLine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_movements",
    )

    # ----- Liens achats (optionnel / legacy) -----
    achat = models.ForeignKey(
        "purchase.Achat",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements",
    )

    # ----- Liens vente/facturation -----
    facture = models.ForeignKey(
        "sale.Facture",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements",
    )
    vente = models.ForeignKey(
        "sale.Vente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements",
        db_index=True,
    )
    vente_ligne = models.ForeignKey(
        "sale.VenteProduit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements",
    )

    stock_consumed = models.BooleanField(default=False, db_index=True)

    # ----- Qui / quand -----
    occurred_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    vendor = models.ForeignKey(
        "vendor.Vendor",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="movements",
    )

    is_locked = models.BooleanField(default=False)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(fields=["movement_type", "occurred_at"]),
            models.Index(fields=["facture"]),
            models.Index(fields=["vente"]),
            models.Index(fields=["produit", "occurred_at"]),
            models.Index(fields=["src_bijouterie"]),
            models.Index(fields=["dst_bijouterie"]),
            models.Index(fields=["vendor", "occurred_at"]),
            models.Index(fields=["movement_type", "vendor"]),

            # ✅ amélioration perf (filtrage fréquent)
            models.Index(fields=["vente_ligne", "movement_type"]),
            models.Index(fields=["produit_line", "movement_type"]),
        ]
        constraints = [
            # quantité
            models.CheckConstraint(check=Q(qty__gt=0), name="inv_move_qty_gt_0"),

            # buckets/bijouterie coherence (DB-safe: *_id__isnull)
            models.CheckConstraint(
                check=~Q(src_bucket=Bucket.BIJOUTERIE) | Q(src_bijouterie_id__isnull=False),
                name="inv_move_src_bijouterie_required_when_src_bucket_is_shop",
            ),
            models.CheckConstraint(
                check=~Q(dst_bucket=Bucket.BIJOUTERIE) | Q(dst_bijouterie_id__isnull=False),
                name="inv_move_dst_bijouterie_required_when_dst_bucket_is_shop",
            ),

            # ===== SALE_OUT =====
            models.CheckConstraint(
                check=~Q(movement_type=MovementType.SALE_OUT) | Q(vendor_id__isnull=False),
                name="ck_sale_out_requires_vendor",
            ),
            models.CheckConstraint(
                check=~Q(movement_type=MovementType.SALE_OUT) | Q(vente_ligne_id__isnull=False),
                name="ck_sale_out_requires_sale_line",
            ),
            models.CheckConstraint(
                check=~Q(movement_type=MovementType.SALE_OUT) | Q(produit_line_id__isnull=False),
                name="ck_sale_out_requires_produit_line",
            ),
            models.CheckConstraint(
                check=~Q(movement_type=MovementType.SALE_OUT) | Q(src_bijouterie_id__isnull=False),
                name="ck_sale_out_requires_src_bijouterie",
            ),
            models.CheckConstraint(
                check=~Q(movement_type=MovementType.SALE_OUT) | (
                    Q(src_bucket=Bucket.BIJOUTERIE) &
                    Q(dst_bucket=Bucket.EXTERNAL)
                ),
                name="ck_sale_out_bijouterie_to_external",
            ),
            models.CheckConstraint(
                check=~Q(movement_type=MovementType.SALE_OUT) | (
                    Q(src_bucket__isnull=False) &
                    Q(dst_bucket__isnull=False)
                ),
                name="ck_sale_out_requires_buckets",
            ),

            # ===== VENDOR_ASSIGN =====
            models.CheckConstraint(
                check=~Q(movement_type=MovementType.VENDOR_ASSIGN) | Q(vendor_id__isnull=False),
                name="ck_vendor_assign_requires_vendor",
            ),
            models.CheckConstraint(
                check=~Q(movement_type=MovementType.VENDOR_ASSIGN) | Q(produit_line_id__isnull=False),
                name="ck_vendor_assign_requires_produit_line",
            ),
            models.CheckConstraint(
                check=~Q(movement_type=MovementType.VENDOR_ASSIGN) | Q(lot_id__isnull=False),
                name="ck_vendor_assign_requires_lot",
            ),
            models.CheckConstraint(
                check=~Q(movement_type=MovementType.VENDOR_ASSIGN) | (
                    Q(src_bucket=Bucket.RESERVED) &
                    Q(dst_bucket=Bucket.BIJOUTERIE) &
                    Q(dst_bijouterie_id__isnull=False)
                ),
                name="ck_vendor_assign_reserved_to_shop",
            ),

            # ✅ idempotence FIFO (SALE_OUT seulement)
            models.UniqueConstraint(
                fields=["vente_ligne", "produit_line"],
                condition=Q(movement_type=MovementType.SALE_OUT),
                name="uniq_sale_out_per_sale_line_source",
            ),
        ]

    def __str__(self):
        def side(bucket, bid):
            if bucket == Bucket.BIJOUTERIE and bid:
                return f"{bucket}({bid})"
            return f"{bucket or '-'}"
        return (
            f"[{self.movement_type}] p#{self.produit_id} "
            f"{side(self.src_bucket, self.src_bijouterie_id)} → {side(self.dst_bucket, self.dst_bijouterie_id)} "
            f"• qty={self.qty}"
        )

    def clean(self):
        super().clean()

        if not self.produit_id:
            raise ValidationError({"produit": "Produit requis."})
        if not self.movement_type:
            raise ValidationError({"movement_type": "Type de mouvement requis."})
        if not self.qty or self.qty <= 0:
            raise ValidationError({"qty": "La quantité doit être > 0."})

        if self.src_bucket == Bucket.BIJOUTERIE and not self.src_bijouterie_id:
            raise ValidationError({"src_bijouterie": "src_bijouterie requis quand src_bucket=BIJOUTERIE."})
        if self.dst_bucket == Bucket.BIJOUTERIE and not self.dst_bijouterie_id:
            raise ValidationError({"dst_bijouterie": "dst_bijouterie requis quand dst_bucket=BIJOUTERIE."})

        mt = self.movement_type

        if mt == MovementType.SALE_OUT:
            if not (self.src_bucket == Bucket.BIJOUTERIE and self.dst_bucket == Bucket.EXTERNAL):
                raise ValidationError("SALE_OUT : src_bucket=BIJOUTERIE et dst_bucket=EXTERNAL requis.")
            if not self.src_bijouterie_id:
                raise ValidationError({"src_bijouterie": "Obligatoire pour SALE_OUT."})
            if not self.vente_ligne_id:
                raise ValidationError({"vente_ligne": "Obligatoire pour SALE_OUT."})
            if not self.produit_line_id:
                raise ValidationError({"produit_line": "Obligatoire pour SALE_OUT (FIFO source)."})
            if not self.vendor_id:
                raise ValidationError({"vendor": "Obligatoire pour SALE_OUT."})

        elif mt == MovementType.VENDOR_ASSIGN:
            if not self.vendor_id:
                raise ValidationError({"vendor": "Obligatoire pour VENDOR_ASSIGN."})
            if not self.produit_line_id:
                raise ValidationError({"produit_line": "Obligatoire pour VENDOR_ASSIGN (FIFO / lot / audit)."})
            if not self.lot_id:
                raise ValidationError({"lot": "Obligatoire pour VENDOR_ASSIGN (traçabilité)."})
            if self.src_bucket != Bucket.RESERVED:
                raise ValidationError({"src_bucket": "VENDOR_ASSIGN : src_bucket=RESERVED requis."})
            if self.dst_bucket != Bucket.BIJOUTERIE:
                raise ValidationError({"dst_bucket": "VENDOR_ASSIGN : dst_bucket=BIJOUTERIE requis."})
            if self.dst_bijouterie_id is None:
                raise ValidationError({"dst_bijouterie": "VENDOR_ASSIGN : dst_bijouterie requis."})

        # cohérence vente/facture
        if self.vente_ligne_id and self.vente_id and self.vente_ligne and self.vente_ligne.vente_id != self.vente_id:
            raise ValidationError({"vente": "La vente ne correspond pas à la ligne de vente fournie."})
        if self.facture_id and self.vente_id and getattr(self.facture, "vente_id", None) not in (None, self.vente_id):
            raise ValidationError({"facture": "La facture n’est pas liée à la même vente."})

    @property
    def total_cost(self) -> Decimal:
        return Decimal(self.qty or 0) * Decimal(self.unit_cost or 0)

    def save(self, *args, **kwargs):
        if self.pk and self.is_locked:
            raise ValidationError("Mouvement verrouillé. Crée un mouvement inverse.")

        # ✅ Auto-fill lot + achat depuis produit_line
        if self.produit_line_id:
            pl_lot_id = getattr(self.produit_line, "lot_id", None)

            if not self.lot_id and pl_lot_id:
                self.lot_id = pl_lot_id

            if self.lot_id and pl_lot_id and self.lot_id != pl_lot_id:
                raise ValidationError({"lot": "Le lot ne correspond pas à produit_line.lot."})

            if self.lot_id and not self.achat_id:
                lot_obj = getattr(self, "lot", None)
                if lot_obj is None:
                    from purchase.models import Lot
                    lot_obj = Lot.objects.only("id", "achat_id").filter(id=self.lot_id).first()
                if lot_obj and getattr(lot_obj, "achat_id", None):
                    self.achat_id = lot_obj.achat_id

        if self.occurred_at is None:
            self.occurred_at = timezone.now()

        self.full_clean()
        return super().save(*args, **kwargs)

    def freeze(self, by_user=None):
        if self.pk and not self.is_locked:
            self.is_locked = True
            if by_user and not self.created_by_id:
                self.created_by = by_user
            super().save(update_fields=["is_locked", "created_by"])


