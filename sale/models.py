# --- Standard library
import random
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from django.apps import apps
# --- Django
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import CheckConstraint, F, Q, Sum
from django.utils import timezone

from store.models import Bijouterie

from .counters import InvoiceCounter

# ⚠️ Ne pas importer des modèles d'autres apps ici
# from store.models import Categorie, Marque, Modele, Produit, Purete  # ❌
# from vendor.models import Vendor, Cashier  # ❌


TWOPLACES = Decimal("0.01")
ZERO = Decimal("0.00")

# Create your models here.
# Client Model
class Client(models.Model):
    prenom = models.CharField(max_length=100)
    nom = models.CharField(max_length=100)
    telephone = models.CharField(max_length=15, unique=True, blank=True, null=True)
    # phone_number = PhoneNumberField(null=True, blank=True, unique=True)

    @property
    def full_name(self):
        return f"{self.prenom} {self.nom}"

    def __str__(self):
        return self.full_name


class Vente(models.Model):
    numero_vente = models.CharField(max_length=30, unique=True, editable=False, blank=True, null=True)
    client = models.ForeignKey('sale.Client', on_delete=models.SET_NULL, null=True, blank=True, related_name="ventes")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="ventes_creees")
    bijouterie = models.ForeignKey(
        "store.Bijouterie",on_delete=models.PROTECT,
        null=True,           # on laisse nullable pour la migration
        blank=True,related_name="ventes",)
    created_at = models.DateTimeField(auto_now_add=True)
    montant_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), null=True)

    # -----valider SALE_OUT-----
    DELIV_PENDING   = "pending"
    DELIV_DELIVERED = "delivered"
    DELIV_CANCELLED = "cancelled"
    # DELIVERY_STATUS = (
    #     (DELIV_PENDING, "En attente"),
    #     (DELIV_DELIVERED, "Livrée"),
    #     (DELIV_CANCELLED, "Annulée"),
    # )

    # delivery_status = models.CharField(max_length=20, choices=DELIVERY_STATUS, default=DELIV_PENDING)
    delivered_at    = models.DateTimeField(null=True, blank=True)
    delivered_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="ventes_livrees"
    )

    def marquer_livree(self, by_user):
        # self.delivery_status = self.DELIV_DELIVERED
        self.delivered_at = timezone.now()
        if by_user and not self.delivered_by_id:
            self.delivered_by = by_user
        # self.save(update_fields=["delivery_status", "delivered_at", "delivered_by"])
        self.save(update_fields=[ "delivered_at", "delivered_by"])
    # ------End SALE_OUT----------
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Vente"
        verbose_name_plural = "Ventes"
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['numero_vente']),
        ]

    def __str__(self):
        nom_client = getattr(self.client, "full_name", None) or \
                    " ".join(x for x in [getattr(self.client, "prenom", None), getattr(self.client, "nom", None)] if x) or "Inconnu"
        date_txt = self.created_at.strftime('%d/%m/%Y') if self.created_at else ''
        return f"Vente #{self.numero_vente or 'N/A'} - Client: {nom_client} - {date_txt}"

    def generer_numero_vente(self) -> str:
        now = timezone.now()
        suffixe = ''.join(random.choices('0123456789', k=4))
        return f"VENTE-{now.strftime('%m%d%Y%H%M%S')}-{suffixe}".upper()

    def save(self, *args, **kwargs):
        if not self.numero_vente:
            for _ in range(10):
                self.numero_vente = self.generer_numero_vente()
                try:
                    with transaction.atomic():
                        super().save(*args, **kwargs)
                    break
                except IntegrityError:
                    self.numero_vente = None
            else:
                raise ValueError("Impossible de générer un numéro de vente unique après 10 tentatives.")
            return
        return super().save(*args, **kwargs)

    def mettre_a_jour_montant_total(self, commit: bool = True, base: str = "ttc"):
        """base='ttc' (recommandé) ou 'ht'."""
        from django.db.models import Sum
        champ = 'prix_ttc' if base == 'ttc' else 'sous_total_prix_vente_ht'
        total = self.produits.aggregate(t=Sum(champ))['t'] or Decimal('0.00')
        self.montant_total = total
        if commit:
            self.save(update_fields=['montant_total'])
        return total



class VenteProduit(models.Model):
    vente   = models.ForeignKey('sale.Vente', on_delete=models.CASCADE, related_name="produits")
    produit = models.ForeignKey('store.Produit', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="venteProduit_produit")
    vendor  = models.ForeignKey('vendor.Vendor', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="venteproduits_vendor")

    quantite = models.PositiveIntegerField(default=1)

    # 'prix_vente_grammes' = prix par gramme (saisi vendeur) OU fallback MarquePurete
    prix_vente_grammes       = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sous_total_prix_vente_ht = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax                      = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'),
                                                   null=True, blank=True)
    prix_ttc                 = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'),
                                                   null=True)
    # montants (FCFA)
    remise = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'),
                                 null=True, blank=True, help_text="Remise (montant FCFA)")
    autres = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'),
                                 help_text="Autres montants (emballage, etc.)")

    # ---------- helpers ----------
    def _resolve_unit_price(self) -> Decimal:
        """Prix par gramme: vendeur > 0 sinon tarif MarquePurete(marque, purete)."""
        if self.prix_vente_grammes and self.prix_vente_grammes > ZERO:
            return self.prix_vente_grammes

        if not self.produit_id:
            raise ValidationError({"produit": "Produit requis pour déterminer le prix."})

        p = self.produit
        if not getattr(p, "marque_id", None) or not getattr(p, "purete_id", None):
            raise ValidationError({"produit": "Produit sans (marque, purete) et aucun prix fourni."})

        from django.apps import apps
        MarquePurete = apps.get_model('store', 'MarquePurete')

        mp_val = (MarquePurete.objects
                  .filter(marque_id=p.marque_id, purete_id=p.purete_id)
                  .values_list('prix', flat=True).first())
        if mp_val is None:
            raise ValidationError({"produit": "Tarif (marque, purete) introuvable."})

        unit = Decimal(str(mp_val))
        if unit <= ZERO:
            raise ValidationError({"produit": "Tarif (marque, purete) non valide (<= 0)."})
        return unit

    def _get_product_weight(self) -> Decimal:
        """Poids du produit (grammes) — essaie p.poids puis p.poids_grammes."""
        if not self.produit_id:
            raise ValidationError({"produit": "Produit requis pour récupérer le poids."})
        p = self.produit
        raw = getattr(p, "poids", None)
        if raw in (None, "", 0, "0"):
            raw = getattr(p, "poids_grammes", None)
        if raw in (None, "", 0, "0"):
            raise ValidationError({"produit": "Le produit n'a pas de poids défini."})
        w = Decimal(str(raw))
        if w <= ZERO:
            raise ValidationError({"produit": "Poids produit invalide (<= 0)."})
        return w

    # ---------- validation ----------
    def clean(self):
        for f in ('prix_vente_grammes', 'remise', 'autres', 'tax'):
            v = getattr(self, f)
            if v is not None and v < ZERO:
                raise ValidationError({f: "Ne peut pas être négatif."})
        if self.quantite < 1:
            raise ValidationError({"quantite": "Doit être ≥ 1."})

    # ---------- calculs ----------
    def save(self, *args, **kwargs):
        self.full_clean()

        unit_price = self._resolve_unit_price()   # prix par gramme
        weight     = self._get_product_weight()   # poids du produit (g)
        qte        = int(self.quantite or 0)

        # ✅ Règle demandée : HT = prix_vente_grammes × poids × quantite
        base_ht = (unit_price * weight * qte)

        self.sous_total_prix_vente_ht = base_ht.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        remise_v = (self.remise or ZERO)
        autres_v = (self.autres or ZERO)
        tax_v    = (self.tax or ZERO)

        ttc = self.sous_total_prix_vente_ht - remise_v + autres_v + tax_v
        if ttc < ZERO:
            ttc = ZERO
        self.prix_ttc = ttc.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        super().save(*args, **kwargs)

        if self.vente_id and hasattr(self.vente, "mettre_a_jour_montant_total"):
            try:
                self.vente.mettre_a_jour_montant_total(base="ttc")
            except Exception:
                pass


class Facture(models.Model):
    TYPE_PROFORMA       = "proforma"
    TYPES_FACTURE_FACTURE = "facture"
    TYPE_ACOMPTE        = "acompte"
    TYPE_FINALE         = "finale"

    STAT_NON_PAYE = "non_paye"
    STAT_PAYE     = "paye"

    TYPES_FACTURE = (
        (TYPE_PROFORMA, "Proforma"),
        (TYPES_FACTURE_FACTURE, "facture"),
        (TYPE_ACOMPTE, "Facture d’acompte"),
        (TYPE_FINALE, "Facture finale"),
    )
    STATUS = (
        (STAT_NON_PAYE, "Non payé"),
        (STAT_PAYE, "Payé"),
    )

    # ⬇️ PAS de unique=True ici (unicité gérée par la contrainte composite)
    numero_facture = models.CharField(max_length=32, editable=False)

    vente = models.OneToOneField("Vente", on_delete=models.SET_NULL, null=True, blank=True, related_name="facture_vente")
    bijouterie = models.ForeignKey(Bijouterie, on_delete=models.PROTECT, null=False, blank=False, related_name="factures")
    date_creation = models.DateTimeField(auto_now_add=True)
    montant_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=STATUS, default=STAT_NON_PAYE)
    fichier_pdf = models.FileField(upload_to="factures/", null=True, blank=True)
    type_facture = models.CharField(max_length=20, choices=TYPES_FACTURE, default=TYPE_PROFORMA)

    class Meta:
        ordering = ["-id"]
        verbose_name_plural = "Factures"
        indexes = [
            models.Index(fields=["numero_facture"]),
            models.Index(fields=["date_creation"]),
            models.Index(fields=["status"]),
            models.Index(fields=["type_facture"]),
            models.Index(fields=["bijouterie", "date_creation"]),
        ]
        constraints = [
            CheckConstraint(check=Q(montant_total__gte=0), name="facture_montant_total_gte_0"),
            models.UniqueConstraint(fields=["bijouterie", "numero_facture"], name="uniq_invoice_per_shop"),
        ]

    def __str__(self):
        return self.numero_facture

    @staticmethod
    def generer_numero_unique(bijouterie) -> str:
        """Format uniforme par bijouterie, séquentiel/jour : FAC-YYYYMMDD-0001"""
        seq = InvoiceCounter.next_for_today(bijouterie)
        day = timezone.localdate().strftime("%Y%m%d")
        return f"FAC-{day}-{seq:04d}"

    def save(self, *args, **kwargs):
        if not self.numero_facture:
            if not self.bijouterie_id:
                raise ValueError("La bijouterie est obligatoire pour numéroter la facture.")
            self.numero_facture = self.generer_numero_unique(self.bijouterie)
        super().save(*args, **kwargs)

    @property
    def total_paye(self) -> Decimal:
        return self.paiements.aggregate(total=Sum("montant_paye"))["total"] or Decimal("0.00")

    @property
    def reste_a_payer(self) -> Decimal:
        return max((self.montant_total or Decimal("0.00")) - self.total_paye, Decimal("0.00"))

    def est_reglee(self) -> bool:
        return self.status == self.STAT_PAYE

    # est_reglee.boolean = True
    # est_reglee.short_description = "Facture réglée"


class Paiement(models.Model):
    MODE_CASH = "cash"
    MODE_MOBILE = "mobile"
    MODES = (
        (MODE_CASH, "Cash"),
        (MODE_MOBILE, "Mobile"),
    )

    facture = models.ForeignKey("Facture", on_delete=models.CASCADE, related_name="paiements")
    montant_paye = models.DecimalField(max_digits=10, decimal_places=2)
    mode_paiement = models.CharField(max_length=20, choices=MODES, default=MODE_CASH)  # ← petit plus: défaut DB
    date_paiement = models.DateTimeField(auto_now_add=True)
    cashier = models.ForeignKey("staff.Cashier", null=True, blank=True, on_delete=models.SET_NULL, related_name="paiements")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="paiements_validation")

    def __str__(self):
        num = getattr(self.facture, "numero_facture", None) or "Aucune facture"
        return f"Paiement de {self.montant_paye} FCFA - {num}"

    def clean(self):
        super().clean()

        if not self.facture_id:
            raise ValidationError("La facture est requise.")

        # Le created_by doit correspondre au user du cashier si cashier est renseigné
        if self.cashier_id and self.created_by_id and self.cashier.user_id != self.created_by_id:
            raise ValidationError("created_by doit correspondre au user du cashier.")

        # Interdire paiement sur facture déjà soldée
        if getattr(self.facture, "status", None) == getattr(self.facture.__class__, "STAT_PAYE", "paye"):
            raise ValidationError("La facture est déjà réglée.")

        # Interdire surpaiement — on tient compte d'une éventuelle mise à jour d'un paiement existant
        total = self.facture.montant_total or Decimal("0.00")
        qs = self.facture.paiements.all()
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        deja = qs.aggregate(t=Sum("montant_paye"))["t"] or Decimal("0.00")
        restant = max(total - deja, Decimal("0.00"))

        if self.montant_paye is None or self.montant_paye <= 0:
            raise ValidationError("Le montant payé doit être strictement positif.")
        if self.montant_paye > restant:
            raise ValidationError(f"Montant payé ({self.montant_paye}) > restant dû ({restant}).")

    class Meta:
        ordering = ["-date_paiement"]
        verbose_name = "Paiement"
        verbose_name_plural = "Paiements"
        indexes = [
            models.Index(fields=["date_paiement"]),
            models.Index(fields=["created_by"]),
            models.Index(fields=["cashier"]),
            models.Index(fields=["facture", "date_paiement"]),
        ]
        constraints = [
            CheckConstraint(check=Q(montant_paye__gt=0), name="paiement_montant_gt_0"),
        ]

    def save(self, *args, **kwargs):
        # Normaliser à 2 décimales
        if self.montant_paye is not None:
            self.montant_paye = (Decimal(self.montant_paye)
                                 .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        # Auto-renseigner le cashier à partir de created_by si absent
        if not self.cashier_id and self.created_by_id:
            Cashier = apps.get_model("staff", "Cashier")
            self.cashier = Cashier.objects.filter(user_id=self.created_by_id).first()

        self.full_clean()
        super().save(*args, **kwargs)

    def est_reglee(self):
        statut_paye = getattr(self.facture.__class__, "STAT_PAYE", "paye")
        return getattr(self.facture, "status", None) == statut_paye

    est_reglee.boolean = True
    est_reglee.short_description = "Facture réglée"
