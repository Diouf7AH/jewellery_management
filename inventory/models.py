# inventory/models.py

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

# ============================================================
# Types de mouvements
# ============================================================

class MovementType(models.TextChoices):
    # Entrées
    PURCHASE_IN = "PURCHASE_IN", "Entrée fournisseur"
    RETURN_IN = "RETURN_IN", "Retour client"

    # Sorties
    SALE_OUT = "SALE_OUT", "Vente"

    # Gestion interne
    VENDOR_ASSIGN = "VENDOR_ASSIGN", "Affectation vendeur"

    # Annulation
    CANCEL_PURCHASE = "CANCEL_PURCHASE", "Annulation achat"

    # Inventaire
    ADJUSTMENT = "ADJUSTMENT", "Ajustement manuel"


# ============================================================
# Emplacements physiques
# ============================================================

class Bucket(models.TextChoices):
    EXTERNAL = "EXTERNAL", "Externe"
    BIJOUTERIE = "BIJOUTERIE", "Bijouterie"
    VENDOR = "VENDOR", "Vendeur"


# ============================================================
# Journal des mouvements d'inventaire
# ============================================================

class InventoryMovement(models.Model):
    produit = models.ForeignKey(
        "store.Produit",
        on_delete=models.PROTECT,
        related_name="movements",
    )

    movement_type = models.CharField(
        max_length=32,
        choices=MovementType.choices,
        db_index=True,
    )

    qty = models.PositiveIntegerField()

    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    lot = models.ForeignKey(
        "purchase.Lot",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="inventory_movements",
    )

    reason = models.TextField(
        null=True,
        blank=True,
    )

    # ========================================================
    # Source
    # ========================================================

    src_bucket = models.CharField(
        max_length=16,
        choices=Bucket.choices,
        null=True,
        blank=True,
    )

    src_bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movements_as_source",
    )

    # ========================================================
    # Destination
    # ========================================================

    dst_bucket = models.CharField(
        max_length=16,
        choices=Bucket.choices,
        null=True,
        blank=True,
    )

    dst_bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movements_as_destination",
    )

    # ========================================================
    # Achat / lot
    # ========================================================

    produit_line = models.ForeignKey(
        "purchase.ProduitLine",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="inventory_movements",
    )

    achat = models.ForeignKey(
        "purchase.Achat",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements",
    )

    # ========================================================
    # Vente / facture
    # ========================================================

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

    # ========================================================
    # Vendeur
    # ========================================================

    vendor = models.ForeignKey(
        "vendor.Vendor",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="movements",
    )

    # ========================================================
    # Contrôle
    # ========================================================

    stock_consumed = models.BooleanField(
        default=False,
        db_index=True,
    )

    is_locked = models.BooleanField(
        default=False,
        db_index=True,
    )

    occurred_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_movements_created",
    )

    class Meta:
        ordering = [
            "-occurred_at",
            "-id",
        ]

        indexes = [
            models.Index(
                fields=["movement_type", "occurred_at"],
                name="inv_mov_type_date_idx",
            ),
            models.Index(
                fields=["facture"],
                name="inv_mov_facture_idx",
            ),
            models.Index(
                fields=["vente"],
                name="inv_mov_vente_idx",
            ),
            models.Index(
                fields=["produit", "occurred_at"],
                name="inv_mov_product_date_idx",
            ),
            models.Index(
                fields=["src_bijouterie"],
                name="inv_mov_src_shop_idx",
            ),
            models.Index(
                fields=["dst_bijouterie"],
                name="inv_mov_dst_shop_idx",
            ),
            models.Index(
                fields=["vendor", "occurred_at"],
                name="inv_mov_vendor_date_idx",
            ),
            models.Index(
                fields=["movement_type", "vendor"],
                name="inv_mov_type_vendor_idx",
            ),
            models.Index(
                fields=["vente_ligne", "movement_type"],
                name="inv_mov_sale_line_type_idx",
            ),
            models.Index(
                fields=["produit_line", "movement_type"],
                name="inv_mov_pline_type_idx",
            ),
        ]

        constraints = [
            # Quantité obligatoirement positive.
            models.CheckConstraint(
                condition=Q(qty__gt=0),
                name="inv_move_qty_gt_0",
            ),

            # Bijouterie source obligatoire lorsque la source
            # est une bijouterie.
            models.CheckConstraint(
                condition=(
                    ~Q(src_bucket=Bucket.BIJOUTERIE)
                    | Q(src_bijouterie_id__isnull=False)
                ),
                name="inv_move_src_bijouterie_required",
            ),

            # Bijouterie destination obligatoire lorsque
            # la destination est une bijouterie.
            models.CheckConstraint(
                condition=(
                    ~Q(dst_bucket=Bucket.BIJOUTERIE)
                    | Q(dst_bijouterie_id__isnull=False)
                ),
                name="inv_move_dst_bijouterie_required",
            ),

            # PURCHASE_IN :
            # fournisseur/externe -> bijouterie.
            models.CheckConstraint(
                condition=(
                    ~Q(movement_type=MovementType.PURCHASE_IN)
                    | (
                        Q(src_bucket=Bucket.EXTERNAL)
                        & Q(dst_bucket=Bucket.BIJOUTERIE)
                        & Q(dst_bijouterie_id__isnull=False)
                        & Q(produit_line_id__isnull=False)
                        & Q(lot_id__isnull=False)
                    )
                ),
                name="ck_purchase_in_external_to_shop",
            ),

            # VENDOR_ASSIGN :
            # bijouterie -> vendeur.
            models.CheckConstraint(
                condition=(
                    ~Q(movement_type=MovementType.VENDOR_ASSIGN)
                    | (
                        Q(src_bucket=Bucket.BIJOUTERIE)
                        & Q(dst_bucket=Bucket.VENDOR)
                        & Q(src_bijouterie_id__isnull=False)
                        & Q(dst_bijouterie_id__isnull=False)
                        & Q(vendor_id__isnull=False)
                        & Q(produit_line_id__isnull=False)
                        & Q(lot_id__isnull=False)
                    )
                ),
                name="ck_vendor_assign_shop_to_vendor",
            ),

            # SALE_OUT :
            # vendeur -> client/externe.
            models.CheckConstraint(
                condition=(
                    ~Q(movement_type=MovementType.SALE_OUT)
                    | (
                        Q(src_bucket=Bucket.VENDOR)
                        & Q(dst_bucket=Bucket.EXTERNAL)
                        & Q(vendor_id__isnull=False)
                        & Q(vente_id__isnull=False)
                        & Q(vente_ligne_id__isnull=False)
                        & Q(produit_line_id__isnull=False)
                    )
                ),
                name="ck_sale_out_vendor_to_external",
            ),

            # RETURN_IN :
            # client/externe -> bijouterie.
            models.CheckConstraint(
                condition=(
                    ~Q(movement_type=MovementType.RETURN_IN)
                    | (
                        Q(src_bucket=Bucket.EXTERNAL)
                        & Q(dst_bucket=Bucket.BIJOUTERIE)
                        & Q(dst_bijouterie_id__isnull=False)
                        & Q(vente_id__isnull=False)
                        & Q(vente_ligne_id__isnull=False)
                        & Q(produit_line_id__isnull=False)
                    )
                ),
                name="ck_return_in_external_to_shop",
            ),

            # CANCEL_PURCHASE :
            # bijouterie -> fournisseur/externe.
            models.CheckConstraint(
                condition=(
                    ~Q(movement_type=MovementType.CANCEL_PURCHASE)
                    | (
                        Q(src_bucket=Bucket.BIJOUTERIE)
                        & Q(dst_bucket=Bucket.EXTERNAL)
                        & Q(src_bijouterie_id__isnull=False)
                        & Q(produit_line_id__isnull=False)
                    )
                ),
                name="ck_cancel_purchase_shop_to_external",
            ),

            # ADJUSTMENT :
            # entrée ou sortie de bijouterie.
            models.CheckConstraint(
                condition=(
                    ~Q(movement_type=MovementType.ADJUSTMENT)
                    | (
                        (
                            Q(src_bucket=Bucket.EXTERNAL)
                            & Q(dst_bucket=Bucket.BIJOUTERIE)
                            & Q(dst_bijouterie_id__isnull=False)
                        )
                        | (
                            Q(src_bucket=Bucket.BIJOUTERIE)
                            & Q(dst_bucket=Bucket.EXTERNAL)
                            & Q(src_bijouterie_id__isnull=False)
                        )
                    )
                ),
                name="ck_adjustment",
            ),

            # Un seul SALE_OUT par ligne de vente et ProduitLine.
            #
            # Cette contrainte est principalement appliquée par les
            # bases prenant en charge les contraintes conditionnelles.
            models.UniqueConstraint(
                fields=[
                    "vente_ligne",
                    "produit_line",
                ],
                condition=Q(
                    movement_type=MovementType.SALE_OUT,
                ),
                name="uniq_sale_out_per_sale_line_product_line",
            ),
        ]

    def __str__(self):
        def side(bucket, bijouterie_id):
            if bucket == Bucket.BIJOUTERIE and bijouterie_id:
                return f"{bucket}({bijouterie_id})"

            if bucket == Bucket.VENDOR and self.vendor_id:
                return f"{bucket}({self.vendor_id})"

            return bucket or "-"

        return (
            f"[{self.movement_type}] "
            f"produit#{self.produit_id} "
            f"{side(self.src_bucket, self.src_bijouterie_id)} → "
            f"{side(self.dst_bucket, self.dst_bijouterie_id)} "
            f"qty={self.qty}"
        )

    # ========================================================
    # Validation générale
    # ========================================================

    def clean(self):
        super().clean()

        errors = {}

        if not self.produit_id:
            errors["produit"] = "Produit requis."

        if not self.movement_type:
            errors["movement_type"] = "Type de mouvement requis."

        if not self.qty or self.qty <= 0:
            errors["qty"] = "La quantité doit être supérieure à zéro."

        if (
            self.src_bucket == Bucket.BIJOUTERIE
            and not self.src_bijouterie_id
        ):
            errors["src_bijouterie"] = (
                "Bijouterie source requise."
            )

        if (
            self.dst_bucket == Bucket.BIJOUTERIE
            and not self.dst_bijouterie_id
        ):
            errors["dst_bijouterie"] = (
                "Bijouterie destination requise."
            )

        if errors:
            raise ValidationError(errors)

        movement_type = self.movement_type

        if movement_type == MovementType.PURCHASE_IN:
            self._validate_purchase_in()

        elif movement_type == MovementType.VENDOR_ASSIGN:
            self._validate_vendor_assign()

        elif movement_type == MovementType.SALE_OUT:
            self._validate_sale_out()

        elif movement_type == MovementType.RETURN_IN:
            self._validate_return_in()

        elif movement_type == MovementType.CANCEL_PURCHASE:
            self._validate_cancel_purchase()

        elif movement_type == MovementType.ADJUSTMENT:
            self._validate_adjustment()

        else:
            raise ValidationError({
                "movement_type": "Type de mouvement non pris en charge."
            })

        self._validate_relations()

    # ========================================================
    # Validation PURCHASE_IN
    # ========================================================

    def _validate_purchase_in(self):
        errors = {}

        if self.src_bucket != Bucket.EXTERNAL:
            errors["src_bucket"] = (
                "PURCHASE_IN doit partir de EXTERNAL."
            )

        if self.dst_bucket != Bucket.BIJOUTERIE:
            errors["dst_bucket"] = (
                "PURCHASE_IN doit arriver dans BIJOUTERIE."
            )

        if not self.dst_bijouterie_id:
            errors["dst_bijouterie"] = (
                "Bijouterie destination requise."
            )

        if not self.produit_line_id:
            errors["produit_line"] = "ProduitLine requise."

        if not self.lot_id:
            errors["lot"] = "Lot requis."

        if errors:
            raise ValidationError(errors)

    # ========================================================
    # Validation VENDOR_ASSIGN
    # ========================================================

    def _validate_vendor_assign(self):
        errors = {}

        if self.src_bucket != Bucket.BIJOUTERIE:
            errors["src_bucket"] = (
                "VENDOR_ASSIGN doit partir de BIJOUTERIE."
            )

        if self.dst_bucket != Bucket.VENDOR:
            errors["dst_bucket"] = (
                "VENDOR_ASSIGN doit arriver chez VENDOR."
            )

        if not self.src_bijouterie_id:
            errors["src_bijouterie"] = (
                "Bijouterie source requise."
            )

        if not self.dst_bijouterie_id:
            errors["dst_bijouterie"] = (
                "Bijouterie du vendeur requise."
            )

        if not self.vendor_id:
            errors["vendor"] = "Vendeur requis."

        if not self.produit_line_id:
            errors["produit_line"] = "ProduitLine requise."

        if not self.lot_id:
            errors["lot"] = "Lot requis."

        if (
            self.vendor_id
            and self.src_bijouterie_id
            and self.vendor.bijouterie_id
            != self.src_bijouterie_id
        ):
            errors["vendor"] = (
                "Le vendeur n'appartient pas à la bijouterie source."
            )

        if (
            self.vendor_id
            and self.dst_bijouterie_id
            and self.vendor.bijouterie_id
            != self.dst_bijouterie_id
        ):
            errors["dst_bijouterie"] = (
                "La bijouterie destination ne correspond pas "
                "à la bijouterie du vendeur."
            )

        if (
            self.src_bijouterie_id
            and self.dst_bijouterie_id
            and self.src_bijouterie_id
            != self.dst_bijouterie_id
        ):
            errors["dst_bijouterie"] = (
                "Pour VENDOR_ASSIGN, la bijouterie source et la "
                "bijouterie du vendeur doivent être identiques."
            )

        if errors:
            raise ValidationError(errors)

    # ========================================================
    # Validation SALE_OUT
    # ========================================================

    def _validate_sale_out(self):
        errors = {}

        if self.src_bucket != Bucket.VENDOR:
            errors["src_bucket"] = (
                "SALE_OUT doit partir de VENDOR."
            )

        if self.dst_bucket != Bucket.EXTERNAL:
            errors["dst_bucket"] = (
                "SALE_OUT doit arriver vers EXTERNAL."
            )

        if not self.vendor_id:
            errors["vendor"] = "Vendeur requis."

        if not self.vente_id:
            errors["vente"] = "Vente requise."

        if not self.vente_ligne_id:
            errors["vente_ligne"] = (
                "Ligne de vente requise."
            )

        if not self.produit_line_id:
            errors["produit_line"] = (
                "ProduitLine requise."
            )

        if errors:
            raise ValidationError(errors)

        # Cette vérification concerne uniquement SALE_OUT.
        #
        # Elle ne bloque donc plus RETURN_IN utilisant la même
        # vente_ligne et la même ProduitLine.
        duplicate_exists = (
            InventoryMovement.objects
            .filter(
                movement_type=MovementType.SALE_OUT,
                vente_ligne_id=self.vente_ligne_id,
                produit_line_id=self.produit_line_id,
            )
            .exclude(pk=self.pk)
            .exists()
        )

        if duplicate_exists:
            raise ValidationError({
                "non_field_errors": (
                    "Un mouvement SALE_OUT existe déjà pour cette "
                    "ligne de vente et cette ProduitLine."
                )
            })

    # ========================================================
    # Validation RETURN_IN
    # ========================================================

    def _validate_return_in(self):
        errors = {}

        if self.src_bucket != Bucket.EXTERNAL:
            errors["src_bucket"] = (
                "RETURN_IN doit partir de EXTERNAL."
            )

        if self.dst_bucket != Bucket.BIJOUTERIE:
            errors["dst_bucket"] = (
                "RETURN_IN doit arriver dans BIJOUTERIE."
            )

        if not self.dst_bijouterie_id:
            errors["dst_bijouterie"] = (
                "Bijouterie destination requise."
            )

        if not self.vente_id:
            errors["vente"] = (
                "Vente d'origine requise."
            )

        if not self.vente_ligne_id:
            errors["vente_ligne"] = (
                "Ligne de vente d'origine requise."
            )

        if not self.produit_line_id:
            errors["produit_line"] = (
                "ProduitLine d'origine requise."
            )

        if errors:
            raise ValidationError(errors)

        # Le retour doit correspondre à une sortie de vente existante.
        sale_out_exists = (
            InventoryMovement.objects
            .filter(
                movement_type=MovementType.SALE_OUT,
                vente_ligne_id=self.vente_ligne_id,
                produit_line_id=self.produit_line_id,
                vendor_id=self.vendor_id,
            )
            .exists()
        )

        if not sale_out_exists:
            raise ValidationError({
                "vente_ligne": (
                    "Aucun mouvement SALE_OUT correspondant n'a été trouvé."
                )
            })

        # Quantité cumulée retournée.
        returned_qty = (
            InventoryMovement.objects
            .filter(
                movement_type=MovementType.RETURN_IN,
                vente_ligne_id=self.vente_ligne_id,
                produit_line_id=self.produit_line_id,
            )
            .exclude(pk=self.pk)
            .aggregate(total=models.Sum("qty"))
            .get("total")
            or 0
        )

        # Quantité réellement vendue sur cette ProduitLine.
        sold_qty = (
            InventoryMovement.objects
            .filter(
                movement_type=MovementType.SALE_OUT,
                vente_ligne_id=self.vente_ligne_id,
                produit_line_id=self.produit_line_id,
            )
            .aggregate(total=models.Sum("qty"))
            .get("total")
            or 0
        )

        if returned_qty + self.qty > sold_qty:
            raise ValidationError({
                "qty": (
                    "La quantité totale retournée ne peut pas dépasser "
                    f"la quantité vendue ({sold_qty})."
                )
            })

    # ========================================================
    # Validation CANCEL_PURCHASE
    # ========================================================

    def _validate_cancel_purchase(self):
        errors = {}

        if self.src_bucket != Bucket.BIJOUTERIE:
            errors["src_bucket"] = (
                "CANCEL_PURCHASE doit partir de BIJOUTERIE."
            )

        if self.dst_bucket != Bucket.EXTERNAL:
            errors["dst_bucket"] = (
                "CANCEL_PURCHASE doit arriver vers EXTERNAL."
            )

        if not self.src_bijouterie_id:
            errors["src_bijouterie"] = (
                "Bijouterie source requise."
            )

        if not self.produit_line_id:
            errors["produit_line"] = (
                "ProduitLine requise."
            )

        if not (self.reason or "").strip():
            errors["reason"] = (
                "La raison de l'annulation est obligatoire."
            )

        if errors:
            raise ValidationError(errors)

    # ========================================================
    # Validation ADJUSTMENT
    # ========================================================

    def _validate_adjustment(self):
        positive_adjustment = (
            self.src_bucket == Bucket.EXTERNAL
            and self.dst_bucket == Bucket.BIJOUTERIE
            and self.dst_bijouterie_id
        )

        negative_adjustment = (
            self.src_bucket == Bucket.BIJOUTERIE
            and self.dst_bucket == Bucket.EXTERNAL
            and self.src_bijouterie_id
        )

        if not positive_adjustment and not negative_adjustment:
            raise ValidationError({
                "movement_type": (
                    "ADJUSTMENT doit être EXTERNAL → BIJOUTERIE "
                    "ou BIJOUTERIE → EXTERNAL."
                )
            })

        if not self.produit_line_id:
            raise ValidationError({
                "produit_line": (
                    "ProduitLine requise pour un ajustement."
                )
            })

        if not (self.reason or "").strip():
            raise ValidationError({
                "reason": (
                    "Une justification est obligatoire "
                    "pour un ajustement."
                )
            })

    # ========================================================
    # Cohérence des relations
    # ========================================================

    def _validate_relations(self):
        errors = {}

        if (
            self.produit_line_id
            and self.produit_line.produit_id
            != self.produit_id
        ):
            errors["produit_line"] = (
                "La ProduitLine ne correspond pas au produit."
            )

        if (
            self.produit_line_id
            and self.lot_id
            and self.produit_line.lot_id
            != self.lot_id
        ):
            errors["lot"] = (
                "Le lot ne correspond pas à la ProduitLine."
            )

        if (
            self.vente_ligne_id
            and self.vente_id
            and self.vente_ligne.vente_id
            != self.vente_id
        ):
            errors["vente"] = (
                "La ligne de vente ne correspond pas à la vente."
            )

        if (
            self.vente_ligne_id
            and self.produit_id
            and self.vente_ligne.produit_id
            != self.produit_id
        ):
            errors["produit"] = (
                "Le produit ne correspond pas à la ligne de vente."
            )

        if (
            self.facture_id
            and self.vente_id
            and getattr(self.facture, "vente_id", None)
            and self.facture.vente_id != self.vente_id
        ):
            errors["facture"] = (
                "La facture ne correspond pas à la vente."
            )

        if errors:
            raise ValidationError(errors)

    # ========================================================
    # Coût
    # ========================================================

    @property
    def total_cost(self) -> Decimal:
        return (
            Decimal(self.qty or 0)
            * Decimal(self.unit_cost or 0)
        )

    # ========================================================
    # Enregistrement
    # ========================================================

    def save(self, *args, **kwargs):
        # Un mouvement verrouillé ne doit jamais être modifié.
        if self.pk and self.is_locked:
            raise ValidationError(
                "Mouvement verrouillé. "
                "Créez un mouvement inverse."
            )

        # Complète automatiquement les relations à partir
        # de la ProduitLine.
        if self.produit_line_id:
            produit_line_lot_id = getattr(
                self.produit_line,
                "lot_id",
                None,
            )

            if not self.lot_id and produit_line_lot_id:
                self.lot_id = produit_line_lot_id

            if (
                self.lot_id
                and produit_line_lot_id
                and self.lot_id != produit_line_lot_id
            ):
                raise ValidationError({
                    "lot": (
                        "Le lot ne correspond pas "
                        "à produit_line.lot."
                    )
                })

            if self.lot_id and not self.achat_id:
                lot_achat_id = getattr(
                    self.produit_line.lot,
                    "achat_id",
                    None,
                )

                if lot_achat_id:
                    self.achat_id = lot_achat_id

        # Complète automatiquement vente depuis vente_ligne.
        if self.vente_ligne_id and not self.vente_id:
            self.vente_id = self.vente_ligne.vente_id

        if self.occurred_at is None:
            self.occurred_at = timezone.now()

        self.full_clean()

        return super().save(*args, **kwargs)

    # ========================================================
    # Verrouillage
    # ========================================================

    def freeze(self, by_user=None):
        if not self.pk or self.is_locked:
            return

        self.is_locked = True

        update_fields = [
            "is_locked",
        ]

        if by_user and not self.created_by_id:
            self.created_by = by_user
            update_fields.append("created_by")

        # Appel direct du save Django pour ne pas déclencher
        # la protection des mouvements verrouillés.
        super().save(
            update_fields=update_fields,
        )
        
    