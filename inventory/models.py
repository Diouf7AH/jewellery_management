from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import CheckConstraint, F, Q
from django.utils import timezone


class MovementType(models.TextChoices):
    PURCHASE_IN      = "PURCHASE_IN", "Entrée achat"
    CANCEL_PURCHASE  = "CANCEL_PURCHASE", "Annulation achat (sortie)"
    ALLOCATE         = "ALLOCATE", "Affectation réservé → bijouterie"
    TRANSFER         = "TRANSFER", "Transfert entre bijouteries"
    ADJUSTMENT       = "ADJUSTMENT", "Ajustement manuel"
    SALE_OUT         = "SALE_OUT", "Sortie vente"
    RETURN_IN        = "RETURN_IN", "Retour client (entrée)"
    VENDOR_ASSIGN    = "VENDOR_ASSIGN", "Affectation à un vendeur"

class Bucket(models.TextChoices):
    EXTERNAL   = "EXTERNAL", "Externe (hors système)"
    RESERVED   = "RESERVED", "Réservé (bijouterie=NULL)"
    BIJOUTERIE = "BIJOUTERIE", "Bijouterie"

class InventoryMovement(models.Model):
    # Quoi
    produit = models.ForeignKey('store.Produit', on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=32, choices=MovementType.choices)

    qty = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    lot = models.ForeignKey('purchase.AchatProduitLot', null=True, blank=True, on_delete=models.SET_NULL)
    reason = models.TextField(null=True, blank=True)

    # D’où → vers
    src_bucket = models.CharField(max_length=16, choices=Bucket.choices, null=True, blank=True)
    src_bijouterie = models.ForeignKey('store.Bijouterie', on_delete=models.PROTECT, null=True, blank=True,
                                       related_name="movements_as_source")
    dst_bucket = models.CharField(max_length=16, choices=Bucket.choices, null=True, blank=True)
    dst_bijouterie = models.ForeignKey('store.Bijouterie', on_delete=models.PROTECT, null=True, blank=True,
                                       related_name="movements_as_destination")

    # Liens métier (achats)
    achat = models.ForeignKey('purchase.Achat', on_delete=models.SET_NULL, null=True, blank=True, related_name="movements")
    achat_ligne = models.ForeignKey('purchase.AchatProduit', on_delete=models.SET_NULL, null=True, blank=True, related_name="movements")

    # 🔗 Liens vente/facturation
    facture = models.ForeignKey('sale.Facture', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='movements',
                                help_text="Facture liée au mouvement (vente/retour client).")
    vente = models.ForeignKey('sale.Vente', on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='movements', db_index=True,
                              help_text="Vente liée au mouvement (accès direct).")
    vente_ligne = models.ForeignKey('sale.VenteProduit', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='movements',
                                    help_text="Ligne de vente d’origine (si traçable).")

    # 🔑 Clé technique pour unicité SALE_OUT (MySQL/MariaDB safe)
    sale_out_key = models.PositiveIntegerField(null=True, blank=True, editable=False, db_index=True)

    # Qui / quand
    occurred_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    vendor = models.ForeignKey('vendor.Vendor', null=True, blank=True,
                            on_delete=models.SET_NULL, related_name='vendor_assignments')
    # Immutabilité
    is_locked = models.BooleanField(default=False)  # recommandé pour utiliser freeze()

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(fields=['movement_type', 'occurred_at']),
            models.Index(fields=['facture']),
            models.Index(fields=['vente']),
            models.Index(fields=['produit', 'occurred_at']),
            models.Index(fields=['src_bijouterie']),
            models.Index(fields=['dst_bijouterie']),
            # ⛔ supprimé: models.Index(fields=['sale_out_key'])  # doublon avec l'unique
            models.Index(fields=['vendor', 'occurred_at']),
            models.Index(fields=['movement_type', 'vendor']),
        ]
        constraints = [
            # qty > 0 (utile même si champ PositiveIntegerField, car PI autorise 0)
            models.CheckConstraint(
                check=Q(qty__gt=0),
                name="inv_move_qty_gt_0",
            ),
            # src_bucket=BIJOUTERIE => src_bijouterie non nul
            models.CheckConstraint(
                check=~Q(src_bucket=Bucket.BIJOUTERIE) | Q(src_bijouterie__isnull=False),
                name="inv_move_src_bijouterie_required_when_src_bucket_is_shop",
            ),
            # dst_bucket=BIJOUTERIE => dst_bijouterie non nul
            models.CheckConstraint(
                check=~Q(dst_bucket=Bucket.BIJOUTERIE) | Q(dst_bijouterie__isnull=False),
                name="inv_move_dst_bijouterie_required_when_dst_bucket_is_shop",
            ),
            # TRANSFER: BIJOUTERIE->BIJOUTERIE et bijouteries différentes
            models.CheckConstraint(
                check=~Q(movement_type=MovementType.TRANSFER) |
                      (Q(src_bucket=Bucket.BIJOUTERIE, dst_bucket=Bucket.BIJOUTERIE) &
                       ~Q(src_bijouterie=F("dst_bijouterie"))),
                name="inv_move_transfer_src_dst_must_differ",
            ),
            # VENDOR_ASSIGN: vendor obligatoire (pas d’exigence de bucket ici)
            models.CheckConstraint(
                check=~Q(movement_type=MovementType.VENDOR_ASSIGN) | Q(vendor__isnull=False),
                name="ck_vendor_assign_requires_vendor",
            ),
            # Un seul SALE_OUT par ligne de vente (clé technique remplie uniquement pour SALE_OUT)
            models.UniqueConstraint(
                fields=['sale_out_key'],
                name="uniq_sale_out_per_sale_line_key",
            ),
        ]

    

    def __str__(self):
        def side(bucket, bid):
            if bucket == Bucket.BIJOUTERIE and bid:
                return f"{bucket}({bid})"
            return f"{bucket or '-'}"
        return f"[{self.movement_type}] p#{self.produit_id} {side(self.src_bucket, self.src_bijouterie_id)} → {side(self.dst_bucket, self.dst_bijouterie_id)} • qty={self.qty}"

    # --- Validation applicative ---
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

        elif mt == MovementType.SALE_OUT:
            if not (self.src_bucket == Bucket.BIJOUTERIE and self.dst_bucket == Bucket.EXTERNAL):
                raise ValidationError("SALE_OUT : src_bucket=BIJOUTERIE et dst_bucket=EXTERNAL requis.")
            if not self.src_bijouterie_id:
                raise ValidationError({"src_bijouterie": "Obligatoire pour SALE_OUT (origine boutique)."})
            if not self.vente_ligne_id:
                raise ValidationError({"vente_ligne": "Obligatoire pour SALE_OUT (traçabilité ligne)."})
        elif mt == MovementType.RETURN_IN:
            if not (self.src_bucket == Bucket.EXTERNAL and self.dst_bucket == Bucket.BIJOUTERIE):
                raise ValidationError("RETURN_IN : src_bucket=EXTERNAL et dst_bucket=BIJOUTERIE requis.")
            if not self.dst_bijouterie_id:
                raise ValidationError({"dst_bijouterie": "Obligatoire pour RETURN_IN (destination boutique)."})
        
        if mt == MovementType.VENDOR_ASSIGN:
            # Ne pas imposer de src/dst_bucket ici : c’est un log d’affectation interne
            if not self.vendor_id:
                raise ValidationError("VENDOR_ASSIGN : 'vendor' requis.")
            return
        # -> le reste de tes règles pour PURCHASE_IN / ALLOCATE / TRANSFER / SALE_OUT / RETURN_IN
        # Cohérence des liens (utile)
        if self.vente_ligne_id and self.vente_id and self.vente_ligne and self.vente_ligne.vente_id != self.vente_id:
            raise ValidationError({"vente": "La vente ne correspond pas à la ligne de vente fournie."})
        if self.facture_id and self.vente_id and getattr(self.facture, "vente_id", None) not in (None, self.vente_id):
            raise ValidationError({"facture": "La facture n’est pas liée à la même vente."})

    @property
    def total_cost(self) -> Decimal:
        q = Decimal(self.qty or 0)
        p = Decimal(self.unit_cost or 0)
        return q * p

    def save(self, *args, **kwargs):
        # Interdit toute modification si verrouillé
        if self.pk and self.is_locked:
            raise ValidationError("Mouvement verrouillé (immutable). Crée un mouvement inverse pour corriger.")

        # Sale-out key uniquement pour SALE_OUT
        if self.movement_type == MovementType.SALE_OUT:
            self.sale_out_key = self.vente_ligne_id or None
        else:
            self.sale_out_key = None

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

