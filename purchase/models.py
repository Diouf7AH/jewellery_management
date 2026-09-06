import random
import uuid
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Max, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

TWOPLACES = Decimal("0.01")

# Create your models here.
class Fournisseur(models.Model):
    nom = models.CharField(max_length=100, blank=True, null=True)
    prenom = models.CharField(max_length=100, blank=True, null=True)
    address = models.CharField(max_length=100, blank=True, null=True)
    telephone = models.CharField(max_length=30,unique=True,db_index=True,null=False, blank=False)
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
        self.telephone = (self.telephone or "").strip()

        if not self.telephone:
            raise ValidationError({
                "telephone": "Le téléphone du fournisseur est obligatoire."
            })

        if not self.slug:
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

    Les totaux sont calculés à partir des ProduitLine des lots :

    HT = Σ (
        ProduitLine.quantite
        × produit.poids
        × prix_achat_gramme
    ) + frais_transport + frais_douane

    TTC = HT, car aucune TVA fournisseur n'est actuellement appliquée.
    """
    STATUS_CONFIRMED = STATUS_CONFIRMED
    STATUS_CANCELLED = STATUS_CANCELLED
    STATUS_CHOICES   = STATUS_CHOICES

    fournisseur = models.ForeignKey(
        "Fournisseur",
        on_delete=models.PROTECT,
        related_name="achats",
        related_query_name="achat",
    )
    bijouterie = models.ForeignKey("store.Bijouterie",on_delete=models.PROTECT,related_name="achats",related_query_name="achat",)
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
    cancelled_by  = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,on_delete=models.SET_NULL, related_name="achats_annules")
    
    reference_commande = models.CharField(max_length=40, null=True, blank=True, db_index=True,
        help_text="Référence logique de commande fournisseur (ex: CMD-2026-0001)"
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
        expr_ht = ExpressionWrapper(
            F("quantite")
            * Coalesce(F("produit__poids"), Decimal("0.00"))
            * Coalesce(F("prix_achat_gramme"), Decimal("0.00")),
            output_field=DecimalField(max_digits=18, decimal_places=6),  # ✅ laisse de la précision
        )

        agg = (
            ProduitLine.objects
            .filter(lot__achat=self)
            .aggregate(base_ht=Coalesce(Sum(expr_ht), Decimal("0.00")))
        )

        base_ht = Decimal(str(agg["base_ht"] or "0.00"))
        frais_transport = Decimal(str(self.frais_transport or "0.00"))
        frais_douane = Decimal(str(self.frais_douane or "0.00"))

        total_ht = base_ht + frais_transport + frais_douane

        # ✅ arrondi strict à 2 décimales
        self.montant_total_ht = total_ht.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
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
        if not self.numero_achat:
            today = timezone.localdate().strftime("%Y%m%d")
            prefix = f"ACH-{today}"

            for attempt in range(20):
                suffix = "".join(random.choices("0123456789", k=4))
                candidate = f"{prefix}-{suffix}"

                if not Achat.objects.filter(
                    numero_achat=candidate
                ).exists():
                    self.numero_achat = candidate
                    break
            else:
                raise ValidationError({
                    "numero_achat": (
                        "Impossible de générer un numéro d'achat unique."
                    )
                })

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


# class ProduitLine(models.Model):
#     """
#     Une ligne produit dans un lot.
#     On ne stocke que les QUANTITÉS. Les POIDS se déduisent : quantité × produit.poids.
#     """
#     # lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="lignes")
#     lot = models.ForeignKey(Lot,on_delete=models.PROTECT,related_name="lignes",)
#     produit = models.ForeignKey("store.Produit", on_delete=models.PROTECT, related_name="produit_lines")

#     # coût d'achat par gramme (fourni dans le payload: prix_achat_gramme)
#     prix_achat_gramme = models.DecimalField(max_digits=14,decimal_places=2,)

#     # quantités
#     quantite = models.PositiveIntegerField()
    
    
#     numero_ligne_lot = models.PositiveIntegerField(null=True,blank=True,editable=False,)



#     class Meta:
#         indexes = [
#             models.Index(fields=["lot"]),
#             models.Index(fields=["produit"]),
#         ]

#         constraints = [
#             models.CheckConstraint(
#                 condition=Q(quantite__gte=1),
#                 name="ck_pl_qty_gte1",
#             ),
#             models.CheckConstraint(
#                 condition=Q(prix_achat_gramme__gte=0),
#                 name="produit_line_prix_achat_gte_0",
#             ),
#             models.UniqueConstraint(
#                 fields=["lot", "produit"],
#                 name="uniq_produit_per_lot",
#             ),
#             models.UniqueConstraint(
#                 fields=["lot", "numero_ligne_lot"],
#                 name="unique_numero_ligne_par_lot",
#             ),
#         ]

#     def __str__(self):
#         return f"{self.lot.numero_lot} · produit={self.produit_id}"

#     # ---- Helpers (poids dynamiques) ----
#     # @property
#     # def poids_total_calc(self):
#     #     # quantité × poids unitaire courant du produit
#     #     if self.produit.poids is None:
#     #         return None
#     #     return (self.quantite or 0) * self.produit.poids
#     @property
#     def poids_total_calc(self):
#         """
#         Retourne le poids total = quantite × produit.poids
#         (ou None si le produit n’a pas de poids renseigné).
#         """
#         if self.produit.poids is None:
#             return None
#         q = Decimal(self.quantite or 0)
#         p = Decimal(self.produit.poids)
#         return q * p


class ProduitLine(models.Model):
    """
    Une ligne produit dans un lot.

    Règles :
    - un Lot peut contenir plusieurs ProduitLine ;
    - chaque ProduitLine correspond à un Produit précis ;
    - le Produit porte ses caractéristiques :
        catégorie, modèle, marque, pureté, poids, taille, etc. ;
    - plusieurs exemplaires strictement identiques utilisent
      la même ProduitLine avec quantite > 1 ;
    - numero_ligne_lot est unique à l'intérieur du lot.

    Exemple :
        LOT-20260906-0042

        ligne 01 -> Bague 4.20 g
        ligne 02 -> Bague 5.10 g
        ligne 03 -> Collier 12.50 g
        ligne 04 -> Bracelet 8.70 g
    """

    lot = models.ForeignKey(
        "purchase.Lot",
        on_delete=models.PROTECT,
        related_name="lignes",
    )

    produit = models.ForeignKey(
        "store.Produit",
        on_delete=models.PROTECT,
        related_name="produit_lines",
    )

    # Coût d'achat par gramme
    prix_achat_gramme = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    # Nombre d'exemplaires identiques de ce produit dans le lot
    quantite = models.PositiveIntegerField()

    # Position stable de la ligne à l'intérieur du lot :
    # 1, 2, 3, 4...
    numero_ligne_lot = models.PositiveIntegerField(
        null=True,
        blank=True,
        editable=False,
        db_index=True,
    )

    class Meta:
        ordering = [
            "lot_id",
            "numero_ligne_lot",
            "id",
        ]

        indexes = [
            models.Index(
                fields=["lot"],
                name="idx_pl_lot",
            ),
            models.Index(
                fields=["produit"],
                name="idx_pl_produit",
            ),
            models.Index(
                fields=["lot", "numero_ligne_lot"],
                name="idx_pl_lot_numero",
            ),
        ]

        constraints = [
            # Quantité minimum = 1
            models.CheckConstraint(
                condition=Q(quantite__gte=1),
                name="ck_pl_qty_gte1",
            ),

            # Prix d'achat positif ou égal à zéro
            models.CheckConstraint(
                condition=Q(prix_achat_gramme__gte=0),
                name="produit_line_prix_achat_gte_0",
            ),

            # Le même Produit ne doit apparaître
            # qu'une seule fois dans le même lot.
            #
            # Si quantité = 3 :
            # une seule ProduitLine avec quantite=3.
            models.UniqueConstraint(
                fields=["lot", "produit"],
                name="uniq_produit_per_lot",
            ),

            # Numéro de ligne unique dans le lot.
            models.UniqueConstraint(
                fields=["lot", "numero_ligne_lot"],
                name="unique_numero_ligne_par_lot",
            ),
        ]

    def __str__(self):
        numero = (
            f"{self.numero_ligne_lot:02d}"
            if self.numero_ligne_lot
            else "--"
        )

        return (
            f"{self.lot.numero_lot}"
            f" · ligne={numero}"
            f" · produit={self.produit_id}"
        )

    # ============================================================
    # VALIDATION
    # ============================================================

    def clean(self):
        super().clean()

        if self.quantite is not None and self.quantite < 1:
            raise ValidationError({
                "quantite": (
                    "La quantité doit être supérieure "
                    "ou égale à 1."
                )
            })

        if (
            self.prix_achat_gramme is not None
            and self.prix_achat_gramme < 0
        ):
            raise ValidationError({
                "prix_achat_gramme": (
                    "Le prix d'achat par gramme "
                    "ne peut pas être négatif."
                )
            })

        if (
            self.numero_ligne_lot is not None
            and self.numero_ligne_lot < 1
        ):
            raise ValidationError({
                "numero_ligne_lot": (
                    "Le numéro de ligne doit être "
                    "supérieur ou égal à 1."
                )
            })

    # ============================================================
    # NUMÉROTATION AUTOMATIQUE DANS LE LOT
    # ============================================================

    def save(self, *args, **kwargs):
        """
        Attribue automatiquement numero_ligne_lot
        lors de la création.

        Exemple :

        LOT-20260906-0042
            première ligne  -> 1
            deuxième ligne  -> 2
            troisième ligne -> 3

        Le verrou SELECT FOR UPDATE sur le Lot évite que
        deux créations simultanées utilisent le même numéro.
        """

        if self._state.adding and self.numero_ligne_lot is None:

            if not self.lot_id:
                raise ValidationError({
                    "lot": "Le lot est obligatoire."
                })

            with transaction.atomic():

                # Verrou du lot pendant l'attribution du numéro
                Lot.objects.select_for_update().get(
                    pk=self.lot_id
                )

                dernier_numero = (
                    ProduitLine.objects
                    .filter(lot_id=self.lot_id)
                    .aggregate(
                        maximum=Max("numero_ligne_lot")
                    )
                    .get("maximum")
                )

                self.numero_ligne_lot = (
                    (dernier_numero or 0) + 1
                )

                self.full_clean()

                return super().save(*args, **kwargs)

        self.full_clean()

        return super().save(*args, **kwargs)

    # ============================================================
    # POIDS TOTAL
    # ============================================================

    @property
    def poids_total_calc(self):
        """
        Poids total de la ligne :

            quantite × produit.poids

        Exemple :
            quantité = 3
            poids unitaire = 4.20 g

            poids_total = 12.60 g
        """

        if not self.produit_id:
            return None

        if self.produit.poids is None:
            return None

        quantite = Decimal(self.quantite or 0)
        poids = Decimal(str(self.produit.poids))

        return quantite * poids

    # ============================================================
    # NUMÉRO DE LIGNE FORMATÉ
    # ============================================================

    @property
    def numero_ligne_lot_formate(self):
        """
        1  -> 01
        2  -> 02
        12 -> 12
        """
        if self.numero_ligne_lot is None:
            return None

        return f"{self.numero_ligne_lot:02d}"
    
