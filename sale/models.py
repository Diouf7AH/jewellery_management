# sale/models.py
from __future__ import annotations

import random
from decimal import ROUND_HALF_UP, Decimal

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import CheckConstraint, F, Q, Sum
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify

from .counters import InvoiceCounter  # OK (dans la même app)

TWOPLACES = Decimal("0.01")
ZERO = Decimal("0.00")


# =========================
# Client
# =========================
# class Client(models.Model):
#     prenom = models.CharField(max_length=100)
#     nom = models.CharField(max_length=100)
#     telephone = models.CharField(max_length=15, unique=True, blank=True, null=True)

#     @property
#     def full_name(self):
#         return f"{self.prenom} {self.nom}".strip()

#     def __str__(self):
#         return self.full_name

class Client(models.Model):
    prenom = models.CharField(max_length=100)
    nom = models.CharField(max_length=100)
    telephone = models.CharField(max_length=15,unique=True,blank=True,null=True,db_index=True)
    cni = models.CharField(max_length=50,unique=True,blank=True,null=True,db_index=True,verbose_name="Numéro CNI")
    address = models.CharField(max_length=255,blank=True,null=True,verbose_name="Adresse")
    #a chaque auto_now_add=True met de
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["telephone"]),
            models.Index(fields=["cni"]),
        ]
        verbose_name = "Client"
        verbose_name_plural = "Clients"

    @property
    def full_name(self):
        return f"{self.prenom} {self.nom}".strip()

    def __str__(self):
        return self.full_name or self.telephone or f"Client #{self.pk}"
    


# =========================
# Vente
# =========================

class Vente(models.Model):
    numero_vente = models.CharField(max_length=30, unique=True, editable=False, blank=True, null=True)

    client = models.ForeignKey("sale.Client", on_delete=models.SET_NULL, null=True, blank=True, related_name="ventes")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="ventes_creees"
    )

    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="ventes",
    )

    vendor = models.ForeignKey(
        "vendor.Vendor",
        on_delete=models.PROTECT,
        related_name="ventes",
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    # total vente avant TVA facture
    montant_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        null=True,
    )

    delivered_at = models.DateTimeField(null=True, blank=True)
    delivered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="ventes_livrees"
    )

    is_cancelled = models.BooleanField(default=False, db_index=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="ventes_annulees",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["numero_vente"]),
            models.Index(fields=["vendor", "created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(montant_total__gte=0),
                name="vente_montant_total_gte_0",
            ),
        ]

    def __str__(self):
        nom_client = getattr(self.client, "full_name", None) or "Inconnu"
        date_txt = self.created_at.strftime("%d/%m/%Y") if self.created_at else ""
        return f"Vente #{self.numero_vente or 'N/A'} - Client: {nom_client} - {date_txt}"

    def generer_numero_vente(self) -> str:
        now = timezone.now()
        suffixe = "".join(random.choices("0123456789", k=4))
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

    def marquer_livree(self, by_user):
        self.delivered_at = timezone.now()
        if by_user and not self.delivered_by_id:
            self.delivered_by = by_user
        self.save(update_fields=["delivered_at", "delivered_by"])

    def mettre_a_jour_montant_total(self, commit: bool = True):
        total = self.lignes.aggregate(t=Sum("montant_total"))["t"] or Decimal("0.00")
        self.montant_total = total
        if commit:
            self.save(update_fields=["montant_total"])
        return total



class VenteProduit(models.Model):
    vente = models.ForeignKey("sale.Vente", on_delete=models.CASCADE, related_name="lignes")
    produit = models.ForeignKey("store.Produit", on_delete=models.PROTECT)

    vendor = models.ForeignKey(
        "vendor.Vendor",
        on_delete=models.PROTECT,
        related_name="vente_produits",
        null=True, blank=True,
        db_index=True,
    )

    quantite = models.PositiveIntegerField(default=1)

    prix_vente_grammes = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    montant_ht = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    montant_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    remise = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), null=True, blank=True)
    autres = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        indexes = [
            models.Index(fields=["vente"]),
            models.Index(fields=["vendor"]),
            models.Index(fields=["produit"]),
        ]
        constraints = [
            CheckConstraint(check=Q(quantite__gte=1), name="ck_venteproduit_qty_gte_1"),
        ]

    def clean(self):
        super().clean()

        if self.quantite < 1:
            raise ValidationError({"quantite": "Doit être ≥ 1."})

        for f in ("prix_vente_grammes", "remise", "autres"):
            v = getattr(self, f)
            if v is not None and Decimal(str(v)) < ZERO:
                raise ValidationError({f: "Ne peut pas être négatif."})

        if self.vente_id:
            if self.vente.vendor_id and self.vendor_id and self.vendor_id != self.vente.vendor_id:
                raise ValidationError({"vendor": "Le vendeur doit être identique à celui de la vente."})
            if self.vente.vendor_id and not self.vendor_id:
                self.vendor = self.vente.vendor
    
    def _resolve_unit_price(self):
        """
        Prix de vente par gramme.

        Priorité :
        1. prix_vente_grammes saisi dans la vente
        2. prix de la marque du produit
        """

        if self.prix_vente_grammes and Decimal(str(self.prix_vente_grammes)) > 0:
            return Decimal(str(self.prix_vente_grammes))

        produit = self.produit

        try:
            prix = produit.marque.prix
        except Exception:
            prix = None

        if prix is None:
            raise ValidationError({
                "prix_vente_grammes": f"Aucun prix disponible pour le produit {produit.nom}."
            })

        return Decimal(str(prix))


    def _get_product_weight(self):
        """
        Récupère le poids du produit.
        """

        produit = self.produit

        poids = getattr(produit, "poids", None) or getattr(produit, "poids_grammes", None)

        if poids is None or Decimal(str(poids)) <= 0:
            raise ValidationError({
                "produit": f"Poids invalide ou manquant pour le produit {produit.nom}."
            })

        return Decimal(str(poids))
    
    def save(self, *args, **kwargs):
        self.full_clean()

        unit_price = self._resolve_unit_price()
        weight = self._get_product_weight()
        qte = int(self.quantite or 0)

        base_ht = unit_price * weight * qte
        self.montant_ht = base_ht.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        remise_v = Decimal(str(self.remise or ZERO))
        autres_v = Decimal(str(self.autres or ZERO))

        total = self.montant_ht - remise_v + autres_v
        if total < ZERO:
            total = ZERO

        self.montant_total = total.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        super().save(*args, **kwargs)

        if self.vente_id and hasattr(self.vente, "mettre_a_jour_montant_total"):
            try:
                self.vente.mettre_a_jour_montant_total()
            except Exception:
                pass
            


ZERO = Decimal("0.00")
TWOPLACES = Decimal("0.01")


class Facture(models.Model):
    TYPE_PROFORMA = "proforma"
    TYPE_FACTURE = "facture"
    TYPE_ACOMPTE = "acompte"
    TYPE_FINALE = "finale"

    STAT_NON_PAYE = "non_paye"
    STAT_PARTIEL = "partiel"
    STAT_PAYE = "paye"

    STATUS = (
        (STAT_NON_PAYE, "Non payé"),
        (STAT_PARTIEL, "Partiellement payé"),
        (STAT_PAYE, "Payé"),
    )

    TYPES_FACTURE = (
        (TYPE_PROFORMA, "Proforma"),
        (TYPE_FACTURE, "Facture"),
        (TYPE_ACOMPTE, "Facture d’acompte"),
        (TYPE_FINALE, "Facture finale"),
    )

    numero_facture = models.CharField(max_length=32, editable=False)

    vente = models.OneToOneField(
        "sale.Vente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="facture_vente",
    )

    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        related_name="factures",
    )

    date_creation = models.DateTimeField(auto_now_add=True)

    # Base HT figée venant de la vente
    montant_ht = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=ZERO,
    )

    # Configuration TVA figée au moment d'émission
    appliquer_tva = models.BooleanField(default=True)

    taux_tva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=ZERO,
    )

    # Montants calculés
    montant_tva = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=ZERO,
    )

    montant_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=ZERO,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS,
        default=STAT_NON_PAYE,
    )

    facture_pdf = models.FileField(
        upload_to="factures/",
        null=True,
        blank=True,
    )

    type_facture = models.CharField(
        max_length=20,
        choices=TYPES_FACTURE,
        default=TYPE_PROFORMA,
    )

    integrity_hash = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
    )

    qr_code_image = models.ImageField(
        upload_to="factures/qr/",
        null=True,
        blank=True,
    )

    signed_at = models.DateTimeField(null=True, blank=True)

    is_locked = models.BooleanField(default=False)
    locked_at = models.DateTimeField(null=True, blank=True)

    commande_client = models.ForeignKey(
        "order.CommandeClient",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="factures",
    )

    stock_consumed = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["numero_facture"]),
            models.Index(fields=["date_creation"]),
            models.Index(fields=["status"]),
            models.Index(fields=["type_facture"]),
            models.Index(fields=["bijouterie", "date_creation"]),
            models.Index(fields=["commande_client"]),
        ]
        constraints = [
            CheckConstraint(check=Q(montant_ht__gte=0), name="facture_montant_ht_gte_0"),
            CheckConstraint(check=Q(taux_tva__gte=0), name="facture_taux_tva_gte_0"),
            CheckConstraint(check=Q(taux_tva__lte=100), name="facture_taux_tva_lte_100"),
            CheckConstraint(check=Q(montant_tva__gte=0), name="facture_montant_tva_gte_0"),
            CheckConstraint(check=Q(montant_total__gte=0), name="facture_montant_total_gte_0"),
            models.UniqueConstraint(
                fields=["bijouterie", "numero_facture"],
                name="uniq_invoice_per_shop",
            ),
        ]

    def __str__(self):
        return self.numero_facture

    @staticmethod
    def generer_numero_unique(bijouterie) -> str:
        seq = InvoiceCounter.next_for_today(bijouterie)
        day = timezone.localdate().strftime("%Y%m%d")
        return f"FAC-{day}-{seq:04d}"

    def recalculer_totaux(self):
        ht = Decimal(str(self.montant_ht or ZERO))

        taux = Decimal(str(self.taux_tva or ZERO))
        if not self.appliquer_tva:
            taux = ZERO

        # on refige la valeur réellement appliquée
        self.taux_tva = taux.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        self.montant_tva = (ht * self.taux_tva / Decimal("100")).quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )

        self.montant_total = (ht + self.montant_tva).quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )

    @staticmethod
    def recompute_facture_status(facture):
        total_paye = facture.total_paye
        reste = facture.reste_a_payer

        if total_paye <= ZERO:
            new_status = facture.__class__.STAT_NON_PAYE
        elif reste == ZERO:
            new_status = facture.__class__.STAT_PAYE
        else:
            new_status = facture.__class__.STAT_PARTIEL

        if facture.status != new_status:
            facture.status = new_status
            facture.save(update_fields=["status"])

    def save(self, *args, **kwargs):
        if not self.numero_facture:
            if not self.bijouterie_id:
                raise ValueError("La bijouterie est obligatoire pour numéroter la facture.")

            self.numero_facture = self.generer_numero_unique(self.bijouterie)

        if self.is_locked:
            raise ValidationError("Facture verrouillée")

        self.recalculer_totaux()
        super().save(*args, **kwargs)

    @property
    def total_paye(self) -> Decimal:
        PaiementLigne = apps.get_model("sale", "PaiementLigne")
        total = PaiementLigne.objects.filter(
            paiement__facture=self
        ).aggregate(total=Sum("montant_paye"))["total"]
        return total or ZERO

    @property
    def reste_a_payer(self) -> Decimal:
        return max((self.montant_total or ZERO) - self.total_paye, ZERO)

    def est_reglee(self) -> bool:
        return self.status == self.STAT_PAYE



class Paiement(models.Model):
    facture = models.ForeignKey(
        "sale.Facture",
        on_delete=models.CASCADE,
        related_name="paiements"
    )

    date_paiement = models.DateTimeField(auto_now_add=True)

    cashier = models.ForeignKey(
        "staff.Cashier",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="paiements"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="paiements_validation"
    )


    class Meta:
        ordering = ["-date_paiement"]

    def __str__(self):
        num = getattr(self.facture, "numero_facture", None) or "Aucune facture"
        return f"Paiement - {num}"

    @property
    def montant_total_paye(self):
        """
        Total payé pour cette opération de paiement
        (somme des lignes de paiement).
        """
        return self.lignes.aggregate(
            total=Sum("montant_paye")
        )["total"] or Decimal("0.00")

    def save(self, *args, **kwargs):
        """
        Si cashier non fourni, on le déduit de l'utilisateur connecté.
        """
        if not self.cashier_id and self.created_by_id:
            Cashier = apps.get_model("staff", "Cashier")
            self.cashier = Cashier.objects.filter(user_id=self.created_by_id).first()

        super().save(*args, **kwargs)
        

def get_default_mode_paiement():
    return ModePaiement.objects.get_or_create(
        code="cash",
        defaults={
            "nom": "Cash",
            "actif": True,
            "ordre_affichage": 1,
            "necessite_reference": False,
            "est_mode_depot": False,
        }
    )[0].id


class ModePaiement(models.Model):
    nom = models.CharField(max_length=100, unique=True)
    code = models.SlugField(max_length=50, unique=True, db_index=True)
    actif = models.BooleanField(default=True)

    est_mode_depot = models.BooleanField(default=False)
    necessite_reference = models.BooleanField(default=False)

    ordre_affichage = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["ordre_affichage", "nom"]

    def __str__(self):
        return f"{self.nom} ({self.code})"

    def clean(self):
        super().clean()

        if self.code:
            self.code = slugify(self.code).replace("-", "_")

        if self.est_mode_depot and self.code != "depot":
            raise ValidationError({
                "code": "Un mode de dépôt doit avoir le code 'depot'."
            })

class PaiementLigne(models.Model):

    paiement = models.ForeignKey(
        "sale.Paiement",
        on_delete=models.CASCADE,
        related_name="lignes"
    )

    montant_paye = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    mode_paiement = models.ForeignKey(
        "sale.ModePaiement",
        on_delete=models.PROTECT,
        related_name="lignes_paiement",
        default=get_default_mode_paiement
    )

    reference = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )

    compte_depot = models.ForeignKey(
        "compte_depot.CompteDepot",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lignes_paiement"
    )

    transaction_depot = models.ForeignKey(
        "compte_depot.CompteDepotTransaction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lignes_paiement"
    )

    class Meta:
        ordering = ["id"]

        constraints = [
            models.CheckConstraint(
                check=Q(montant_paye__gt=0),
                name="paiement_ligne_montant_paye_gt_0"
            ),

            models.UniqueConstraint(
                fields=["paiement", "mode_paiement"],
                name="uniq_mode_par_paiement"
            ),
        ]

        indexes = [
            models.Index(fields=["paiement"]),
            models.Index(fields=["mode_paiement"]),
        ]

    def __str__(self):
        return f"{self.mode_paiement} - {self.montant_paye} FCFA"

    def clean(self):
        super().clean()

        if self.montant_paye is None or Decimal(str(self.montant_paye)) <= 0:
            raise ValidationError(
                "Le montant payé doit être strictement positif."
            )

        if not self.mode_paiement_id:
            raise ValidationError({
                "mode_paiement": "Le mode de paiement est obligatoire."
            })

        mode = self.mode_paiement

        if not mode.actif:
            raise ValidationError({
                "mode_paiement": "Ce mode de paiement est inactif."
            })

        if mode.necessite_reference and not self.reference:
            raise ValidationError({
                "reference": f"Une référence est obligatoire pour le mode '{mode.nom}'."
            })

        if mode.est_mode_depot:
            if not self.compte_depot_id:
                raise ValidationError(
                    "Le compte dépôt est obligatoire pour une ligne dépôt."
                )

            if not self.transaction_depot_id:
                raise ValidationError(
                    "La transaction dépôt est obligatoire pour une ligne dépôt."
                )
        else:
            if self.compte_depot_id or self.transaction_depot_id:
                raise ValidationError(
                    "compte_depot et transaction_depot sont réservés au mode dépôt."
                )

    def save(self, *args, **kwargs):

        if self.montant_paye is not None:
            self.montant_paye = Decimal(self.montant_paye).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP
            )

        self.full_clean()

        super().save(*args, **kwargs)
        
        

