import random
from django.conf import settings

from django.db import models
from decimal import Decimal, ROUND_HALF_UP
from store.models import Produit
import datetime
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.db.models.functions import Coalesce
import uuid
from django.db import models, IntegrityError
from django.utils.text import slugify
from django.db.models import Q, F, Sum

# Create your models here.
class Fournisseur(models.Model):
    nom = models.CharField(max_length=100, blank=True, null=True)
    prenom = models.CharField(max_length=100, blank=True, null=True)
    address = models.CharField(max_length=100, blank=True, null=True)
    telephone = models.CharField(max_length=15, unique=True, blank=True, null=True)
    slug = models.SlugField(max_length=30, unique=True, blank=True, null=True)  # <- important
    date_ajout = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    def __str__(self):
        # évite "None None None"
        parts = [p for p in [self.nom, self.prenom, self.telephone] if p]
        return " ".join(parts) or f"Fournisseur #{self.pk}"

    def _gen_unique_slug(self) -> str:
        MAX = 30
        # essaie quelques UUID courts pour éviter une (très) improbable collision
        for _ in range(5):
            cand = uuid.uuid4().hex[:MAX]
            if not Fournisseur.objects.filter(slug=cand).exists():
                return cand
        return uuid.uuid4().hex[:MAX]

    def save(self, *args, **kwargs):
        # normalise téléphone vide -> None (évite unique='' en base)
        if self.telephone == "":
            self.telephone = None

        if not self.slug:
            self.slug = self._gen_unique_slug()
        try:
            super().save(*args, **kwargs)
        except IntegrityError:
            # collision concurrente rarissime : on regénère une fois
            self.slug = self._gen_unique_slug()
            super().save(*args, **kwargs)
            
# Achat  Model
# class Achat(models.Model):
#     fournisseur = models.ForeignKey("Fournisseur",on_delete=models.SET_NULL,null=True, blank=True,
#         related_name="achats",        # manager côté Fournisseur
#         related_query_name="achat",   # lookups dans les requêtes
#     )
#     # fournisseur = models.ForeignKey('Fournisseur', related_name="achat", on_delete=models.SET_NULL, null=True, blank=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     montant_total_ht = models.DecimalField(default=0.00, null=True, max_digits=12, decimal_places=2)
#     montant_total_ttc = models.DecimalField(default=0.00, null=True, max_digits=12, decimal_places=2)

#     # une propriété pour les taxes globales
#     @property
#     def montant_total_tax(self):
#         return self.montant_total_ttc - self.montant_total_ht
    
#     def update_total(self):
#         """
#         Met à jour les montants HT et TTC de l'achat
#         en recalculant à partir des produits liés.
#         """
#         total = sum(p.sous_total_prix_achat for p in self.produits.all())
#         tax_total = sum(p.tax or 0 for p in self.produits.all())
#         self.montant_total_ht = total
#         self.montant_total_ttc = total + tax_total
#         self.save()
    
#     def get_produits_details(self):
#         return [
#             {
#                 "produit": p.produit.nom,
#                 "quantite": p.quantite,
#                 "prix_gramme": p.prix_achat_gramme,
#                 "sous_total": p.sous_total_prix_achat,
#                 "tax": p.tax,
#             }
#             for p in self.produits.all()
#         ]

#     def __str__(self):
#         return f"Achat Fournisseur: {self.fournisseur.nom if self.fournisseur else 'N/A'}"


# class Achat(models.Model):
#     fournisseur = models.ForeignKey("Fournisseur",on_delete=models.SET_NULL,null=True, blank=True,related_name="achats",related_query_name="achat",)
#     created_at = models.DateTimeField(auto_now_add=True)
#     montant_total_ht = models.DecimalField(default=Decimal("0.00"), null=True, max_digits=12, decimal_places=2)
#     montant_total_ttc = models.DecimalField(default=Decimal("0.00"), null=True, max_digits=12, decimal_places=2)
#     numero_achat = models.CharField(max_length=25, unique=True, null=True, blank=True)
#     status = models.CharField(
#         max_length=20,
#         choices=[("confirmed", "Confirmé"), ("cancelled", "Annulé")],
#         default="confirmed",
#     )
#     cancel_reason = models.TextField(null=True, blank=True)   # ✅ on persiste la raison
#     cancelled_at = models.DateTimeField(null=True, blank=True)
#     cancelled_by = models.ForeignKey(
#         settings.AUTH_USER_MODEL, null=True, blank=True,
#         on_delete=models.SET_NULL, related_name="achats_annules"
#     )
    
#     class Meta:
#         ordering = ["-id"]
#         indexes = [
#             models.Index(fields=["created_at"]),
#             models.Index(fields=["fournisseur"]),
#             models.Index(fields=["status"]),
#         ]
#         verbose_name = "Achat"
#         verbose_name_plural = "Achats"

#     @property
#     def montant_total_tax(self) -> Decimal:
#         ht = self.montant_total_ht or Decimal("0.00")
#         ttc = self.montant_total_ttc or Decimal("0.00")
#         return ttc - ht

#     def clean(self):
#         if self.montant_total_ht is not None and self.montant_total_ht < 0:
#             raise ValidationError({"montant_total_ht": "Le montant HT doit être ≥ 0."})
#         if self.montant_total_ttc is not None and self.montant_total_ttc < 0:
#             raise ValidationError({"montant_total_ttc": "Le montant TTC doit être ≥ 0."})
#         if (self.montant_total_ht is not None and self.montant_total_ttc is not None
#                 and self.montant_total_ttc < self.montant_total_ht):
#             raise ValidationError("Le montant TTC ne peut pas être inférieur au montant HT.")

#     def update_total(self, save: bool = True):
#         """
#         Recalcule HT/TTC via agrégations SQL sur les lignes (AchatProduit).
#         Suppose AchatProduit.achat has related_name='produits'.
#         """
#         agg = self.produits.aggregate(
#             total_ht=Coalesce(Sum("sous_total_prix_achat"), Decimal("0.00")),
#             total_tax=Coalesce(Sum("tax"), Decimal("0.00")),
#         )
#         self.montant_total_ht = agg["total_ht"]
#         self.montant_total_ttc = agg["total_ht"] + agg["total_tax"]

#         if save:
#             self.full_clean()
#             self.save(update_fields=["montant_total_ht", "montant_total_ttc"])

#     def get_produits_details(self):
#         qs = self.produits.select_related("produit").all()
#         return [
#             {
#                 "produit": (p.produit.nom if p.produit else None),
#                 "quantite": p.quantite,
#                 "prix_gramme": p.prix_achat_gramme,
#                 "sous_total": p.sous_total_prix_achat,
#             }
#             for p in qs
#         ]

#     def __str__(self):
#         nom = self.fournisseur.nom if getattr(self.fournisseur, "nom", None) else "N/A"
#         return f"Achat Fournisseur: {nom}"
    
#     def save(self, *args, **kwargs):
#         if not self.numero_achat:
#             today = timezone.now().strftime("%Y%m%d")
#             prefix = f"ACH-{today}"
#             for _ in range(15):
#                 suffix = "".join(random.choices("0123456789", k=4))
#                 cand = f"{prefix}-{suffix}"
#                 if not type(self).objects.filter(numero_achat=cand).exists():
#                     self.numero_achat = cand
#                     break
#             else:
#                 raise ValidationError("Impossible de générer un numéro d'achat unique.")
#         super().save(*args, **kwargs)


    # def save(self, *args, **kwargs):
    #         super().save(*args, **kwargs)
    #         if self.achat:
    #             # appel update_total() automatiquement à chaque fois qu’un produit est ajouté/modifié.
    #             self.achat.update_total()
    
    
# VenteProduit (Product in Sale) Model
# class AchatProduit(models.Model):
#     achat = models.ForeignKey(Achat, related_name="achat", on_delete=models.CASCADE)
#     produit = models.ForeignKey(Produit, related_name="achats_produits", on_delete=models.CASCADE)
#     numero_achat_produit = models.CharField(max_length=25, unique=True, null=True, blank=True)
#     quantite = models.PositiveIntegerField(default=0, validators=[MinValueValidator(1)])
#     prix_achat_gramme = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
#     fournisseur = models.ForeignKey(Fournisseur, on_delete=models.SET_NULL, null=True, blank=True)
#     tax = models.DecimalField(default=0.00, decimal_places=2, max_digits=12, null=True, blank=True)
#     sous_total_prix_achat = models.DecimalField(default=0.00, null=True, decimal_places=2, max_digits=12)

#     class Meta:
#         verbose_name = "Produit acheté"
#         verbose_name_plural = "Produits achetés"

#     def __str__(self):
#         return f"{self.quantite} x {self.produit.nom if self.produit else 'N/A'} in Achat {self.achat.id if self.achat else 'N/A'}"
    
#     @property
#     def prix_achat_total_ttc(self):
#         return (self.sous_total_prix_achat or Decimal(0)) + (self.tax or Decimal(0))

#     def save(self, *args, **kwargs):
#         # Générer numéro unique si vide
#         if not self.numero_achat_produit:
#             today = timezone.now().strftime('%Y%m%d')
#             prefix = f"ACH-PROD-{today}"
#             for _ in range(10):
#                 suffix = ''.join(random.choices('0123456789', k=4))
#                 numero = f"{prefix}-{suffix}"
#                 if not AchatProduit.objects.filter(numero_achat_produit=numero).exists():
#                     self.numero_achat_produit = numero
#                     break
#             else:
#                 raise Exception("Impossible de générer un numéro d'achat produit unique.")

#         # ⚙️ Calcul automatique du sous-total
#         poids = self.produit.poids or Decimal(0)
#         self.sous_total_prix_achat = self.prix_achat_gramme * self.quantite * poids

#         super().save(*args, **kwargs)
        
#         # 🔁 Met à jour automatiquement les montants HT/TTC dans Achat
#         if self.achat:
#             self.achat.update_total()

#     def to_dict(self):
#         return {
#             "produit": self.produit.nom,
#             "quantite": self.quantite,
#             "prix_achat_gramme": self.prix_achat_gramme,
#             "sous_total_prix_achat": self.sous_total_prix_achat,
#             "tax": self.tax,
#             "prix_achat_total_ttc": self.prix_achat_total_ttc,
#         }

STATUS_CONFIRMED = "confirmed"
STATUS_CANCELLED = "cancelled"
STATUS_CHOICES = [(STATUS_CONFIRMED, "Confirmé"), (STATUS_CANCELLED, "Annulé")]

class Achat(models.Model):

    STATUS_CONFIRMED = STATUS_CONFIRMED
    STATUS_CANCELLED = STATUS_CANCELLED
    STATUS_CHOICES = STATUS_CHOICES
    fournisseur = models.ForeignKey(
        "Fournisseur",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="achats", related_query_name="achat",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField(null=True, blank=True, help_text="Note interne visible sur l'achat (motif, consignes, etc.)")
    # Totaux (toujours recalculés depuis les lignes)
    montant_total_ht = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    montant_total_ttc = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    numero_achat = models.CharField(max_length=30, unique=True, db_index=True, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_CONFIRMED)
    cancel_reason = models.TextField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,on_delete=models.SET_NULL, related_name="achats_annules")

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["fournisseur"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            models.CheckConstraint(check=Q(montant_total_ht__gte=0), name="achat_ht_gte_0"),
            models.CheckConstraint(check=Q(montant_total_ttc__gte=0), name="achat_ttc_gte_0"),
            models.CheckConstraint(check=Q(montant_total_ttc__gte=F("montant_total_ht")), name="achat_ttc_gte_ht"),
            models.CheckConstraint(
                name="achat_cancel_fields_consistency",
                check=(
                    Q(status=STATUS_CANCELLED, cancelled_at__isnull=False, cancelled_by__isnull=False) |
                    Q(status=STATUS_CONFIRMED, cancelled_at__isnull=True,  cancelled_by__isnull=True)
                ),
            ),
        ]

    def __str__(self):
        nom = getattr(self.fournisseur, "nom", None) or "N/A"
        return f"Achat {self.numero_achat or self.pk} – Fournisseur: {nom}"

    @property
    def montant_total_tax(self) -> Decimal:
        return (self.montant_total_ttc or Decimal("0.00")) - (self.montant_total_ht or Decimal("0.00"))

    def clean(self):
        if self.montant_total_ht < 0:
            raise ValidationError({"montant_total_ht": "Le montant HT doit être ≥ 0."})
        if self.montant_total_ttc < 0:
            raise ValidationError({"montant_total_ttc": "Le montant TTC doit être ≥ 0."})
        if self.montant_total_ttc < self.montant_total_ht:
            raise ValidationError("Le montant TTC ne peut pas être inférieur au montant HT.")
        if self.status == self.STATUS_CANCELLED and (not self.cancelled_at or not self.cancelled_by):
            raise ValidationError("Achat annulé : 'cancelled_at' et 'cancelled_by' sont requis.")
        if self.status == self.STATUS_CONFIRMED and (self.cancelled_at or self.cancelled_by):
            raise ValidationError("Achat confirmé : ne pas renseigner 'cancelled_at' / 'cancelled_by'.")

    def update_total(self, save: bool = True):
        """
        Recalcule HT/TTC via les lignes (AchatProduit).
        Hypothèse: la ligne stocke le montant de taxe 'tax_amount'.
        """
        agg = self.produits.aggregate(
            total_ht=Coalesce(Sum("sous_total_prix_achat"), Decimal("0.00")),
            total_tax=Coalesce(Sum("tax_amount"),          Decimal("0.00")),
        )
        self.montant_total_ht = agg["total_ht"]
        self.montant_total_ttc = agg["total_ht"] + agg["total_tax"]

        if save:
            self.full_clean()
            self.save(update_fields=["montant_total_ht", "montant_total_ttc"])

    def get_produits_details(self):
        qs = self.produits.select_related("produit").all()
        return [
            {
                "produit": (p.produit.nom if p.produit else None),
                "quantite": p.quantite,
                "prix_gramme": p.prix_achat_gramme,
                "sous_total": p.sous_total_prix_achat,  # PHT ligne
                "tax_amount": getattr(p, "tax_amount", None),
                "tax_rate": getattr(p, "tax_rate", None),
            }
            for p in qs
        ]

    def save(self, *args, **kwargs):
        if not self.numero_achat:
            today = timezone.now().strftime("%Y%m%d")
            prefix = f"ACH-{today}"
            for attempt in range(20):
                suffix = "".join(random.choices("0123456789", k=4))
                self.numero_achat = f"{prefix}-{suffix}"
                try:
                    super().save(*args, **kwargs)
                    break
                except IntegrityError:
                    if attempt == 19:
                        raise ValidationError("Impossible de générer un numéro d'achat unique.")
                    # réessaie avec un nouveau suffixe
            return
        super().save(*args, **kwargs)
            
        
        
# class AchatProduit(models.Model):
#     achat = models.ForeignKey(
#         Achat,
#         related_name="produits",                # ✅ correspond à Achat.update_total()
#         on_delete=models.CASCADE
#     )
#     produit = models.ForeignKey(
#         Produit,
#         related_name="achats_produits",
#         on_delete=models.CASCADE
#     )
#     tax = models.DecimalField(
#             default=Decimal("0.00"),
#             decimal_places=2, max_digits=12, null=True, blank=True,
#             validators=[MinValueValidator(Decimal("0.00"))]
#         )
#     lot_code = models.CharField(max_length=50, null=True, blank=True, db_index=True)
#     quantite = models.PositiveIntegerField(
#         default=1,                              # ✅ cohérent avec MinValueValidator(1)
#         validators=[MinValueValidator(1)]
#     )
#     prix_achat_gramme = models.DecimalField(
#         default=Decimal("0.00"),                # ✅ Decimal, pas float
#         decimal_places=2, max_digits=12,
#         validators=[MinValueValidator(Decimal("0.00"))]
#     )
#     sous_total_prix_achat = models.DecimalField(
#         default=Decimal("0.00"),
#         null=True, decimal_places=2, max_digits=12
#     )

#     created_at = models.DateTimeField(auto_now_add=True)       # 👍 pratique
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         verbose_name = "Produit acheté"
#         verbose_name_plural = "Produits achetés"
#         ordering = ["-id"]
#         indexes = [
#             models.Index(fields=["achat"]),
#             models.Index(fields=["produit"]),
#             models.Index(fields=["numero_achat_produit"]),
#         ]

#     def __str__(self):
#         return f"{self.quantite} x {self.produit.nom if self.produit else 'N/A'} (Achat #{self.achat_id or 'N/A'})"

#     @property
#     def prix_achat_total_ttc(self):
#         return (self.sous_total_prix_achat or Decimal("0.00")) + (self.tax or Decimal("0.00"))

#     def save(self, *args, **kwargs):
#         # ⚙️ Calcul sous-total (quantité * poids * prix/gramme)
#         poids = (self.produit.poids or Decimal("0.00"))
#         self.sous_total_prix_achat = (self.prix_achat_gramme or Decimal("0.00")) * Decimal(self.quantite) * poids

#         super().save(*args, **kwargs)

#         # 🔁 Recalcule les totaux de l'achat
#         if self.achat_id:
#             self.achat.update_total()

# TWOPLACES pour l'arrondi
TWOPLACES = Decimal("0.01")

class AchatProduit(models.Model):
    achat = models.ForeignKey('purchase.Achat', related_name="produits", on_delete=models.CASCADE,)
    produit = models.ForeignKey('store.Produit', related_name="achats_produits", on_delete=models.CASCADE,)

    # (optionnel) code lot legacy – pour vraie traçabilité, préférer un modèle AchatProduitLot
    lot_code = models.CharField(max_length=40, null=True, blank=True, db_index=True)

    quantite = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    prix_achat_gramme = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Prix unitaire HT par gramme",
    )

    # Montant HT de la ligne = quantite × poids_produit × prix_gramme
    sous_total_prix_achat = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    # Taxes par ligne
    tax_rate = models.DecimalField(     # en %, ex: 18.00 pour 18%
        max_digits=6, decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Taux de taxe (%) appliqué à la ligne",
    )
    tax_amount = models.DecimalField(   # montant de taxe (à agréger dans Achat)
        max_digits=12, decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Produit acheté"
        verbose_name_plural = "Produits achetés"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["achat"]),
            models.Index(fields=["produit"]),
            models.Index(fields=["lot_code"]),
        ]
        constraints = [
            models.CheckConstraint(name="achatprod_tax_rate_gte_0", check=models.Q(tax_rate__gte=0)),
            models.CheckConstraint(name="achatprod_tax_amount_gte_0", check=models.Q(tax_amount__gte=0)),
        ]

    def __str__(self):
        nom = self.produit.nom if getattr(self.produit, "nom", None) else "N/A"
        return f"{self.quantite} x {nom} (Achat #{self.achat_id or 'N/A'})"

    @property
    def prix_achat_total_ttc(self) -> Decimal:
        """TTC de la ligne = HT + taxe."""
        return (self.sous_total_prix_achat or Decimal("0.00")) + (self.tax_amount or Decimal("0.00"))

    # ---------- Calculs internes ----------
    def _compute_sous_total_ht(self) -> Decimal:
        poids = getattr(self.produit, "poids", None) or Decimal("0.00")
        base = (self.prix_achat_gramme or Decimal("0.00")) * Decimal(self.quantite) * Decimal(poids)
        return base.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    def _compute_tax_amount(self) -> Decimal:
        base = self.sous_total_prix_achat or Decimal("0.00")
        rate = (self.tax_rate or Decimal("0.00")) / Decimal("100")
        return (base * rate).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    # ---------- Persistance ----------
    def save(self, *args, **kwargs):
        # Recalcule systématiquement HT & taxe avant save
        self.sous_total_prix_achat = self._compute_sous_total_ht()
        self.tax_amount = self._compute_tax_amount()
        super().save(*args, **kwargs)

        # Met à jour les totaux de l'achat
        if self.achat_id:
            self.achat.update_total()
            


class AchatProduitLot(models.Model):
    achat_ligne = models.ForeignKey(
        'AchatProduit', related_name='lots', on_delete=models.CASCADE
    )
    lot_code = models.CharField(max_length=40, db_index=True)
    date_reception = models.DateField(auto_now_add=True)

    quantite_total = models.PositiveIntegerField()
    quantite_restante = models.PositiveIntegerField()
    prix_achat_gramme = models.DecimalField(max_digits=12, decimal_places=2)
    date_peremption = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('achat_ligne', 'lot_code'), name='uniq_lot_code_per_achat_ligne'
            ),
            models.CheckConstraint(check=Q(quantite_total__gt=0), name='lot_quantite_total_gt_0'),
            models.CheckConstraint(check=Q(quantite_restante__gte=0), name='lot_quantite_restante_gte_0'),
            models.CheckConstraint(
                check=Q(quantite_restante__lte=F('quantite_total')),
                name='lot_quantite_restante_lte_total',
            ),
            models.CheckConstraint(check=Q(prix_achat_gramme__gte=0), name='lot_prix_achat_gramme_gte_0'),
            models.CheckConstraint(
                check=Q(date_peremption__isnull=True) | Q(date_peremption__gte=F('date_reception')),
                name='lot_peremption_after_or_null',
            ),
        ]
        indexes = [
            models.Index(fields=['lot_code', 'date_reception']),
            models.Index(fields=['achat_ligne', 'date_reception']),
            models.Index(fields=['quantite_restante']),
        ]
        ordering = ['date_reception', 'id']  # FIFO naturel

    def __str__(self):
        p = getattr(self.achat_ligne, 'produit', None)
        prod = getattr(p, 'nom', 'N/A')
        return f"Lot {self.lot_code} • {self.quantite_restante}/{self.quantite_total} • {prod}"

    @property
    def produit(self):
        return self.achat_ligne.produit if self.achat_ligne_id else None

    @property
    def is_epuise(self) -> bool:
        return (self.quantite_restante or 0) == 0

    def clean(self):
        if self.quantite_total is not None and self.quantite_total <= 0:
            raise ValidationError({"quantite_total": "Doit être > 0."})
        if self.quantite_restante is not None and self.quantite_restante < 0:
            raise ValidationError({"quantite_restante": "Doit être ≥ 0."})
        if (self.quantite_total is not None and self.quantite_restante is not None
                and self.quantite_restante > self.quantite_total):
            raise ValidationError({"quantite_restante": "Ne peut pas dépasser la quantité totale."})
        if self.prix_achat_gramme is not None and self.prix_achat_gramme < 0:
            raise ValidationError({"prix_achat_gramme": "Doit être ≥ 0."})
        if self.date_peremption and self.date_reception and self.date_peremption < self.date_reception:
            raise ValidationError({"date_peremption": "Ne peut pas être antérieure à la réception."})

    def save(self, *args, **kwargs):
        if self.lot_code:
            self.lot_code = self.lot_code.strip().upper()
        if self._state.adding and (self.quantite_restante is None or self.quantite_restante == 0):
            self.quantite_restante = self.quantite_total
        super().save(*args, **kwargs)

    # Décrément sécurisé (à appeler dans une transaction + select_for_update sur la ligne concernée)
    def decrement(self, qty: int) -> int:
        if qty <= 0:
            raise ValidationError({"qty": "Doit être > 0."})
        updated = type(self).objects.filter(
            pk=self.pk, quantite_restante__gte=qty
        ).update(quantite_restante=F('quantite_restante') - qty)
        if not updated:
            raise ValidationError("Stock lot insuffisant.")
        self.refresh_from_db(fields=['quantite_restante'])
        return self.quantite_restante