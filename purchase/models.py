import datetime
import random
import uuid
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import IntegrityError, models, transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.text import slugify

from store.models import Produit


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


STATUS_CONFIRMED = "confirmed"
STATUS_CANCELLED = "cancelled"
STATUS_CHOICES = [
    (STATUS_CONFIRMED, "Confirmé"),
    (STATUS_CANCELLED,  "Annulé"),
]


class Achat(models.Model):
    """
    Représente un achat fournisseur.

    · Les totaux sont calculés à partir des L O T S rattachés à l'achat :
      HT = Σ (quantite_total * produit.poids * prix_achat_gramme) + frais_transport + frais_douane
      TAX = 0 (sauf si tu rajoutes des taxes sur Lot)
      TTC = HT + TAX

    · Un numero_achat unique est généré si absent (ACH-YYYYMMDD-XXXX).
    """
    STATUS_CONFIRMED = STATUS_CONFIRMED
    STATUS_CANCELLED = STATUS_CANCELLED
    STATUS_CHOICES   = STATUS_CHOICES

    fournisseur = models.ForeignKey(
        "Fournisseur",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="achats", related_query_name="achat",
    )
    created_at   = models.DateTimeField(auto_now_add=True)
    description  = models.TextField(null=True, blank=True, help_text="Note interne (motif, consignes, etc.)")

    # Frais additionnels (ajoutés au HT)
    frais_transport = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    frais_douane    = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    note = models.TextField(blank=True, default="")

    # Identifiant humain lisible (garder UN seul champ)
    numero_achat = models.CharField(max_length=30, unique=True, db_index=True, null=True, blank=True)

    # Totaux (recalculés par update_total)
    montant_total_ht  = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    montant_total_ttc = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_CONFIRMED)
    cancel_reason = models.TextField(null=True, blank=True)
    cancelled_at  = models.DateTimeField(null=True, blank=True)
    cancelled_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="achats_annules"
    )

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["fournisseur"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            models.CheckConstraint(check=Q(frais_transport__gte=0), name="achat_frais_transport_gte_0"),
            models.CheckConstraint(check=Q(frais_douane__gte=0),    name="achat_frais_douane_gte_0"),
            models.CheckConstraint(check=Q(montant_total_ht__gte=0), name="achat_ht_gte_0"),
            models.CheckConstraint(check=Q(montant_total_ttc__gte=0), name="achat_ttc_gte_0"),
            models.CheckConstraint(
                check=Q(montant_total_ttc__gte=F("montant_total_ht")),
                name="achat_ttc_gte_ht",
            ),
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
        """TAX = TTC - HT (ici 0 si tu ne gères pas les taxes)."""
        return (self.montant_total_ttc or Decimal("0.00")) - (self.montant_total_ht or Decimal("0.00"))

    def update_total(self, save: bool = True):
        """
        Calcule :
          base_HT = Σ (ligne.quantite * produit.poids * ligne.prix_achat_gramme)
          HT      = base_HT + frais_transport + frais_douane
          TTC     = HT (pas de TVA pour l'instant)
        """
        # import local pour éviter les imports circulaires
        from purchase.models import ProduitLine

        # quantite * poids * prix_achat_gramme
        expr_ht = ExpressionWrapper(
            F("quantite")
            * Coalesce(F("produit__poids"), Decimal("0.00"))
            * Coalesce(F("prix_achat_gramme"), Decimal("0.00")),
            output_field=DecimalField(max_digits=18, decimal_places=2),
        )

        agg = (
            ProduitLine.objects
            .filter(lot__achat=self)
            .aggregate(base_ht=Coalesce(Sum(expr_ht), Decimal("0.00")))
        )

        base_ht = agg["base_ht"] or Decimal("0.00")

        frais_transport = self.frais_transport or Decimal("0.00")
        frais_douane    = self.frais_douane or Decimal("0.00")

        self.montant_total_ht  = base_ht + frais_transport + frais_douane
        self.montant_total_ttc = self.montant_total_ht  # pas de TVA

        if save:
            self.full_clean()
            self.save(update_fields=["montant_total_ht", "montant_total_ttc"])

    # ----------------- Validation -----------------
    def clean(self):
        if self.montant_total_ht is not None and self.montant_total_ht < 0:
            raise ValidationError({"montant_total_ht": "Le montant HT doit être ≥ 0."})
        if self.montant_total_ttc is not None and self.montant_total_ttc < 0:
            raise ValidationError({"montant_total_ttc": "Le montant TTC doit être ≥ 0."})
        if (self.montant_total_ttc or Decimal("0.00")) < (self.montant_total_ht or Decimal("0.00")):
            raise ValidationError("Le montant TTC ne peut pas être inférieur au montant HT.")
        if self.status == self.STATUS_CANCELLED and (not self.cancelled_at or not self.cancelled_by):
            raise ValidationError("Achat annulé : 'cancelled_at' et 'cancelled_by' sont requis.")
        if self.status == self.STATUS_CONFIRMED and (self.cancelled_at or self.cancelled_by):
            raise ValidationError("Achat confirmé : ne pas renseigner 'cancelled_at' / 'cancelled_by'.")

    # ----------------- Persistance -----------------
    def save(self, *args, **kwargs):
        # Générer un numéro lisible unique si absent
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
            return
        super().save(*args, **kwargs)


class Lot(models.Model):
    achat = models.ForeignKey("purchase.Achat", on_delete=models.PROTECT, related_name="lots")
    numero_lot = models.CharField(max_length=64, unique=True, db_index=True)
    description = models.CharField(max_length=255, blank=True, default="")
    received_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["received_at", "id"]

    def __str__(self):
        return self.numero_lot


class ProduitLine(models.Model):
    """
    Une ligne produit dans un lot.
    On ne stocke que les QUANTITÉS. Les POIDS se déduisent : quantité × produit.poids.
    """
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name="lignes")
    produit = models.ForeignKey("store.Produit", on_delete=models.PROTECT, related_name="produit_lines")

    # coût d'achat par gramme (fourni dans le payload: prix_achat_gramme)
    prix_achat_gramme = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    # quantités
    quantite = models.PositiveIntegerField()

    class Meta:
        indexes = [
            models.Index(fields=["lot"]),
            models.Index(fields=["produit"]),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(quantite__gte=1), name="ck_pl_qty_gte1"),
        ]

    def __str__(self):
        return f"{self.lot.numero_lot} · produit={self.produit_id}"

    # ---- Helpers (poids dynamiques) ----
    @property
    def poids_total_calc(self):
        # quantité × poids unitaire courant du produit
        if self.produit.poids is None:
            return None
        return (self.quantite or 0) * self.produit.poids

    