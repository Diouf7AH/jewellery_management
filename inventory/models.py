from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, F, CheckConstraint
from django.utils import timezone

class MovementType(models.TextChoices):
    PURCHASE_IN      = "PURCHASE_IN", "Entrée achat"
    CANCEL_PURCHASE  = "CANCEL_PURCHASE", "Annulation achat (sortie)"
    ALLOCATE         = "ALLOCATE", "Affectation réservé → bijouterie"
    TRANSFER         = "TRANSFER", "Transfert entre bijouteries"
    ADJUSTMENT       = "ADJUSTMENT", "Ajustement manuel"
    SALE_OUT         = "SALE_OUT", "Sortie vente"
    RETURN_IN        = "RETURN_IN", "Retour client (entrée)"

class Bucket(models.TextChoices):
    EXTERNAL   = "EXTERNAL", "Externe (hors système)"
    RESERVED   = "RESERVED", "Réservé (bijouterie=NULL)"
    BIJOUTERIE = "BIJOUTERIE", "Bijouterie"

class InventoryMovement(models.Model):
    # Quoi
    produit = models.ForeignKey('store.Produit', on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=32, choices=MovementType.choices)

    qty = models.PositiveIntegerField()  # > 0
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    lot_code = models.CharField(max_length=50, null=True, blank=True)
    reason = models.TextField(null=True, blank=True)

    # D’où → vers
    src_bucket = models.CharField(max_length=16, choices=Bucket.choices, null=True, blank=True)
    src_bijouterie = models.ForeignKey('store.Bijouterie', on_delete=models.PROTECT, null=True, blank=True,
                                       related_name="movements_as_source")

    dst_bucket = models.CharField(max_length=16, choices=Bucket.choices, null=True, blank=True)
    dst_bijouterie = models.ForeignKey('store.Bijouterie', on_delete=models.PROTECT, null=True, blank=True,
                                       related_name="movements_as_destination")

    # Liens métier (paresseux pour éviter les imports circulaires)
    achat = models.ForeignKey('purchase.Achat', on_delete=models.SET_NULL, null=True, blank=True, related_name="movements")
    achat_ligne = models.ForeignKey('purchase.AchatProduit', on_delete=models.SET_NULL, null=True, blank=True, related_name="movements")

    # Qui / quand
    occurred_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    # Immutabilité
    is_locked = models.BooleanField(default=True)

    class Meta:
        constraints = [
            CheckConstraint(check=Q(qty__gt=0), name="inv_move_qty_gt_0"),
            CheckConstraint(
                check=~Q(src_bucket="BIJOUTERIE") | Q(src_bijouterie__isnull=False),
                name="inv_move_src_bijouterie_required_when_src_bucket_is_shop",
            ),
            CheckConstraint(
                check=~Q(dst_bucket="BIJOUTERIE") | Q(dst_bijouterie__isnull=False),
                name="inv_move_dst_bijouterie_required_when_dst_bucket_is_shop",
            ),
            CheckConstraint(
                check=~Q(movement_type="TRANSFER") |
                    (Q(src_bucket="BIJOUTERIE", dst_bucket="BIJOUTERIE") & ~Q(src_bijouterie=F("dst_bijouterie"))),
                name="inv_move_transfer_src_dst_must_differ",
            ),
        ]

    @property
    def total_cost(self) -> Decimal:
        q = Decimal(self.qty or 0)
        p = Decimal(self.unit_cost or 0)
        return q * p

    def __str__(self):
        def side(bucket, bid):
            if bucket == Bucket.BIJOUTERIE and bid:
                return f"{bucket}({bid})"
            return f"{bucket or '-'}"
        return f"[{self.movement_type}] p#{self.produit_id} {side(self.src_bucket, self.src_bijouterie_id)} → {side(self.dst_bucket, self.dst_bijouterie_id)} • qty={self.qty}"

    # --- Validation applicative (utile si MySQL < 8.0.16) ---
    def clean(self):
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
        if mt == MovementType.PURCHASE_IN:
            if self.src_bucket != Bucket.EXTERNAL:
                raise ValidationError("PURCHASE_IN : src_bucket doit être EXTERNAL.")
            if self.dst_bucket not in (Bucket.RESERVED, Bucket.BIJOUTERIE):
                raise ValidationError("PURCHASE_IN : dst_bucket doit être RESERVED ou BIJOUTERIE.")
        elif mt == MovementType.CANCEL_PURCHASE:
            if self.dst_bucket != Bucket.EXTERNAL:
                raise ValidationError("CANCEL_PURCHASE : dst_bucket doit être EXTERNAL.")
            if self.src_bucket not in (Bucket.RESERVED, Bucket.BIJOUTERIE):
                raise ValidationError("CANCEL_PURCHASE : src_bucket doit être RESERVED ou BIJOUTERIE.")
        elif mt == MovementType.ALLOCATE:
            if not (self.src_bucket == Bucket.RESERVED and self.dst_bucket == Bucket.BIJOUTERIE):
                raise ValidationError("ALLOCATE : src_bucket=RESERVED et dst_bucket=BIJOUTERIE requis.")
        elif mt == MovementType.TRANSFER:
            if not (self.src_bucket == Bucket.BIJOUTERIE and self.dst_bucket == Bucket.BIJOUTERIE):
                raise ValidationError("TRANSFER : src_bucket=BIJOUTERIE et dst_bucket=BIJOUTERIE requis.")
            if self.src_bijouterie_id == self.dst_bijouterie_id:
                raise ValidationError("TRANSFER : source et destination doivent être différentes.")
        elif mt == MovementType.ADJUSTMENT:
            if bool(self.src_bucket) == bool(self.dst_bucket):
                raise ValidationError("ADJUSTMENT : préciser soit src (perte) soit dst (gain), pas les deux.")

    def save(self, *args, **kwargs):
        if self.pk and self.is_locked:
            raise ValidationError("Mouvement verrouillé (immutable). Crée un mouvement inverse pour corriger.")
        self.full_clean()
        if self.occurred_at is None:
            self.occurred_at = timezone.now()
        super().save(*args, **kwargs)

    def freeze(self, by_user=None):
        if self.pk and not self.is_locked:
            self.is_locked = True
            if by_user and not self.created_by_id:
                self.created_by = by_user
            super().save(update_fields=["is_locked", "created_by"])

