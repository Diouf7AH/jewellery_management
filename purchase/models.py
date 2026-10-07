# # purchase/models.py
# import random
# import uuid
# from decimal import ROUND_HALF_UP, Decimal

# from django.conf import settings
# from django.core.exceptions import ValidationError
# from django.db import models, transaction
# from django.db.models import DecimalField, ExpressionWrapper, F, Max, Q, Sum
# from django.db.models.functions import Coalesce
# from django.utils import timezone

# TWOPLACES = Decimal("0.01")

# # Create your models here.
# class Fournisseur(models.Model):
#     nom = models.CharField(max_length=100, blank=True, null=True)
#     prenom = models.CharField(max_length=100, blank=True, null=True)
#     address = models.CharField(max_length=100, blank=True, null=True)
#     telephone = models.CharField(max_length=30,unique=True,db_index=True,null=False, blank=False)
#     slug = models.SlugField(max_length=30, unique=True, blank=True, null=True)  # <- important
#     date_ajout = models.DateTimeField(auto_now_add=True)
#     date_modification = models.DateTimeField(auto_now=True)

#     def __str__(self):
#         # évite "None None None"
#         parts = [p for p in [self.nom, self.prenom, self.telephone] if p]
#         return " ".join(parts) or f"Fournisseur #{self.pk}"

#     def _gen_unique_slug(self) -> str:
#         MAX = 30
#         # essaie quelques UUID courts pour éviter une (très) improbable collision
#         for _ in range(5):
#             cand = uuid.uuid4().hex[:MAX]
#             if not Fournisseur.objects.filter(slug=cand).exists():
#                 return cand
#         return uuid.uuid4().hex[:MAX]

#     def save(self, *args, **kwargs):
#         self.telephone = (self.telephone or "").strip()

#         if not self.telephone:
#             raise ValidationError({
#                 "telephone": "Le téléphone du fournisseur est obligatoire."
#             })

#         if not self.slug:
#             self.slug = self._gen_unique_slug()

#         super().save(*args, **kwargs)


# STATUS_CONFIRMED = "confirmed"
# STATUS_CANCELLED = "cancelled"
# STATUS_CHOICES = [
#     (STATUS_CONFIRMED, "Confirmé"),
#     (STATUS_CANCELLED,  "Annulé"),
# ]


# class Achat(models.Model):
#     """
#     Représente un achat fournisseur.

#     Les totaux sont calculés à partir des ProduitLine des lots :

#     HT = Σ (
#         ProduitLine.quantite
#         × produit.poids
#         × prix_achat_gramme
#     ) + frais_transport + frais_douane

#     TTC = HT, car aucune TVA fournisseur n'est actuellement appliquée.
#     """
#     STATUS_CONFIRMED = STATUS_CONFIRMED
#     STATUS_CANCELLED = STATUS_CANCELLED
#     STATUS_CHOICES   = STATUS_CHOICES

#     fournisseur = models.ForeignKey(
#         "Fournisseur",
#         on_delete=models.PROTECT,
#         related_name="achats",
#         related_query_name="achat",
#     )
#     bijouterie = models.ForeignKey("store.Bijouterie",on_delete=models.PROTECT,related_name="achats",related_query_name="achat",)
#     created_at   = models.DateTimeField(auto_now_add=True)
#     description  = models.TextField(null=True, blank=True, help_text="Note interne (motif, consignes, etc.)")

#     # Frais additionnels (ajoutés au HT)
#     frais_transport = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
#     frais_douane    = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

#     note = models.TextField(blank=True, default="")

#     # Identifiant humain lisible (garder UN seul champ)
#     numero_achat = models.CharField(max_length=30, unique=True, db_index=True, null=True, blank=True)

#     # Totaux (recalculés par update_total)
#     montant_total_ht  = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
#     montant_total_ttc = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

#     status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_CONFIRMED)
#     cancel_reason = models.TextField(null=True, blank=True)
#     cancelled_at  = models.DateTimeField(null=True, blank=True)
#     cancelled_by  = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,on_delete=models.SET_NULL, related_name="achats_annules")
    
#     reference_commande = models.CharField(max_length=40, null=True, blank=True, db_index=True,
#         help_text="Référence logique de commande fournisseur (ex: CMD-2026-0001)"
#     )

#     class Meta:
#         ordering = ["-id"]
#         indexes = [
#             models.Index(fields=["created_at"]),
#             models.Index(fields=["fournisseur"]),
#             models.Index(fields=["status"]),
#         ]
#         constraints = [
#             models.CheckConstraint(check=Q(frais_transport__gte=0), name="achat_frais_transport_gte_0"),
#             models.CheckConstraint(check=Q(frais_douane__gte=0),    name="achat_frais_douane_gte_0"),
#             models.CheckConstraint(check=Q(montant_total_ht__gte=0), name="achat_ht_gte_0"),
#             models.CheckConstraint(check=Q(montant_total_ttc__gte=0), name="achat_ttc_gte_0"),
#             models.CheckConstraint(
#                 check=Q(montant_total_ttc__gte=F("montant_total_ht")),
#                 name="achat_ttc_gte_ht",
#             ),
#             models.CheckConstraint(
#                 name="achat_cancel_fields_consistency",
#                 check=(
#                     Q(status=STATUS_CANCELLED, cancelled_at__isnull=False, cancelled_by__isnull=False) |
#                     Q(status=STATUS_CONFIRMED, cancelled_at__isnull=True,  cancelled_by__isnull=True)
#                 ),
#             ),
#         ]

#     def __str__(self):
#         nom = getattr(self.fournisseur, "nom", None) or "N/A"
#         return f"Achat {self.numero_achat or self.pk} – Fournisseur: {nom}"

#     @property
#     def montant_total_tax(self) -> Decimal:
#         """TAX = TTC - HT (ici 0 si tu ne gères pas les taxes)."""
#         return (self.montant_total_ttc or Decimal("0.00")) - (self.montant_total_ht or Decimal("0.00"))

#     def update_total(self, save: bool = True):
#         expr_ht = ExpressionWrapper(
#             F("quantite")
#             * Coalesce(F("produit__poids"), Decimal("0.00"))
#             * Coalesce(F("prix_achat_gramme"), Decimal("0.00")),
#             output_field=DecimalField(max_digits=18, decimal_places=6),  # ✅ laisse de la précision
#         )

#         agg = (
#             ProduitLine.objects
#             .filter(lot__achat=self)
#             .aggregate(base_ht=Coalesce(Sum(expr_ht), Decimal("0.00")))
#         )

#         base_ht = Decimal(str(agg["base_ht"] or "0.00"))
#         frais_transport = Decimal(str(self.frais_transport or "0.00"))
#         frais_douane = Decimal(str(self.frais_douane or "0.00"))

#         total_ht = base_ht + frais_transport + frais_douane

#         # ✅ arrondi strict à 2 décimales
#         self.montant_total_ht = total_ht.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
#         self.montant_total_ttc = self.montant_total_ht  # pas de TVA

#         if save:
#             self.full_clean()
#             self.save(update_fields=["montant_total_ht", "montant_total_ttc"])
            
#     # ----------------- Validation -----------------
#     def clean(self):
#         if self.montant_total_ht is not None and self.montant_total_ht < 0:
#             raise ValidationError({"montant_total_ht": "Le montant HT doit être ≥ 0."})
#         if self.montant_total_ttc is not None and self.montant_total_ttc < 0:
#             raise ValidationError({"montant_total_ttc": "Le montant TTC doit être ≥ 0."})
#         if (self.montant_total_ttc or Decimal("0.00")) < (self.montant_total_ht or Decimal("0.00")):
#             raise ValidationError("Le montant TTC ne peut pas être inférieur au montant HT.")
#         if self.status == self.STATUS_CANCELLED and (not self.cancelled_at or not self.cancelled_by):
#             raise ValidationError("Achat annulé : 'cancelled_at' et 'cancelled_by' sont requis.")
#         if self.status == self.STATUS_CONFIRMED and (self.cancelled_at or self.cancelled_by):
#             raise ValidationError("Achat confirmé : ne pas renseigner 'cancelled_at' / 'cancelled_by'.")

#     # ----------------- Persistance -----------------
#     def save(self, *args, **kwargs):
#         if not self.numero_achat:
#             today = timezone.localdate().strftime("%Y%m%d")
#             prefix = f"ACH-{today}"

#             for attempt in range(20):
#                 suffix = "".join(random.choices("0123456789", k=4))
#                 candidate = f"{prefix}-{suffix}"

#                 if not Achat.objects.filter(
#                     numero_achat=candidate
#                 ).exists():
#                     self.numero_achat = candidate
#                     break
#             else:
#                 raise ValidationError({
#                     "numero_achat": (
#                         "Impossible de générer un numéro d'achat unique."
#                     )
#                 })

#         super().save(*args, **kwargs)


# class Lot(models.Model):
#     achat = models.ForeignKey("purchase.Achat", on_delete=models.PROTECT, related_name="lots")
#     numero_lot = models.CharField(max_length=64, unique=True, db_index=True)
#     description = models.CharField(max_length=255, blank=True, default="")
#     received_at = models.DateTimeField(default=timezone.now, db_index=True)

#     class Meta:
#         ordering = ["received_at", "id"]

#     def __str__(self):
#         return self.numero_lot


# class ProduitLine(models.Model):
#     """
#     Une ligne produit dans un lot.

#     - Un lot peut contenir plusieurs ProduitLine.
#     - Une ProduitLine correspond à un Produit précis.
#     - Plusieurs exemplaires identiques sont regroupés
#       dans la même ligne avec quantite > 1.
#     - numero_ligne_lot identifie la position stable
#       de la ligne dans le lot.
#     - uuid identifie de manière unique la ProduitLine
#       et sert notamment pour le QR Code de l'étiquette.
#     """

#     # ========================================================
#     # IDENTIFIANT UNIQUE DE LA LIGNE / ÉTIQUETTE
#     # ========================================================

#     uuid = models.UUIDField(
#         default=uuid.uuid4,
#         unique=True,
#         editable=False,
#         db_index=True,
#     )

#     # ========================================================
#     # RELATIONS
#     # ========================================================

#     lot = models.ForeignKey(
#         "purchase.Lot",
#         on_delete=models.PROTECT,
#         related_name="lignes",
#     )

#     produit = models.ForeignKey(
#         "store.Produit",
#         on_delete=models.PROTECT,
#         related_name="produit_lines",
#     )

#     # ========================================================
#     # DONNÉES
#     # ========================================================
#     poids_unitaire_achat = models.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         null=True,
#         blank=True,
#         help_text="Poids unitaire du produit constaté au moment de l'achat.",
#     )

#     prix_achat_gramme = models.DecimalField(
#         max_digits=14,
#         decimal_places=2,
#     )

#     # éventuellement
#     purete_achat = models.ForeignKey(
#         "store.Purete",
#         on_delete=models.PROTECT
#     )
    
#     prix_achat_gramme = models.DecimalField(
#         max_digits=14,
#         decimal_places=2,
#     )

#     quantite = models.PositiveIntegerField()

#     numero_ligne_lot = models.PositiveIntegerField(
#         null=True,
#         blank=True,
#         editable=False,
#     )

#     # ========================================================
#     # META
#     # ========================================================

#     class Meta:
#         ordering = [
#             "lot_id",
#             "numero_ligne_lot",
#             "id",
#         ]

#         indexes = [
#             models.Index(
#                 fields=["lot"],
#                 name="idx_pl_lot",
#             ),
#             models.Index(
#                 fields=["produit"],
#                 name="idx_pl_produit",
#             ),
#             models.Index(
#                 fields=["lot", "numero_ligne_lot"],
#                 name="idx_pl_lot_numero",
#             ),
#             # models.Index(
#             #     fields=["uuid"],
#             #     name="idx_pl_uuid",
#             # ),
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

#     # ========================================================
#     # STRING
#     # ========================================================

#     def __str__(self):
#         numero = (
#             f"{self.numero_ligne_lot:02d}"
#             if self.numero_ligne_lot is not None
#             else "--"
#         )

#         return (
#             f"{self.lot.numero_lot}"
#             f" · ligne={numero}"
#             f" · produit={self.produit_id}"
#         )

#     # ========================================================
#     # VALIDATION
#     # ========================================================

#     def clean(self):
#         super().clean()

#         if (
#             self.quantite is not None
#             and self.quantite < 1
#         ):
#             raise ValidationError({
#                 "quantite": (
#                     "La quantité doit être supérieure "
#                     "ou égale à 1."
#                 )
#             })

#         if (
#             self.prix_achat_gramme is not None
#             and self.prix_achat_gramme < 0
#         ):
#             raise ValidationError({
#                 "prix_achat_gramme": (
#                     "Le prix d'achat par gramme "
#                     "ne peut pas être négatif."
#                 )
#             })

#         if (
#             self.numero_ligne_lot is not None
#             and self.numero_ligne_lot < 1
#         ):
#             raise ValidationError({
#                 "numero_ligne_lot": (
#                     "Le numéro de ligne doit être "
#                     "supérieur ou égal à 1."
#                 )
#             })

#     # ========================================================
#     # SAVE
#     # ========================================================

#     def save(self, *args, **kwargs):
#         """
#         Attribue automatiquement et définitivement
#         numero_ligne_lot lors de la création.
#         """

#         if (
#             self._state.adding
#             and self.numero_ligne_lot is None
#         ):
#             if not self.lot_id:
#                 raise ValidationError({
#                     "lot": "Le lot est obligatoire."
#                 })

#             with transaction.atomic():

#                 # Verrouille le lot pendant la numérotation.
#                 Lot.objects.select_for_update().get(
#                     pk=self.lot_id
#                 )

#                 dernier_numero = (
#                     ProduitLine.objects
#                     .filter(
#                         lot_id=self.lot_id
#                     )
#                     .aggregate(
#                         maximum=Max(
#                             "numero_ligne_lot"
#                         )
#                     )
#                     ["maximum"]
#                 )

#                 self.numero_ligne_lot = (
#                     (dernier_numero or 0) + 1
#                 )

#                 return super().save(
#                     *args,
#                     **kwargs,
#                 )

#         return super().save(
#             *args,
#             **kwargs,
#         )

#     # ========================================================
#     # PROPRIÉTÉS
#     # ========================================================

#     @property
#     def poids_total_calc(self):
#         """
#         quantité × poids unitaire du Produit.
#         """

#         if not self.produit_id:
#             return None

#         if self.produit.poids is None:
#             return None

#         quantite = Decimal(
#             self.quantite or 0
#         )

#         poids = Decimal(
#             str(self.produit.poids)
#         )

#         return quantite * poids

#     @property
#     def numero_ligne_lot_formate(self):
#         """
#         1  -> 01
#         2  -> 02
#         12 -> 12
#         """

#         if self.numero_ligne_lot is None:
#             return None

#         return f"{self.numero_ligne_lot:02d}"
    



# purchase/models.py

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


# ============================================================
# FOURNISSEUR
# ============================================================

class Fournisseur(models.Model):

    nom = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    prenom = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    address = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    telephone = models.CharField(
        max_length=30,
        unique=True,
        db_index=True,
        null=False,
        blank=False,
    )

    slug = models.SlugField(
        max_length=30,
        unique=True,
        blank=True,
        null=True,
    )

    date_ajout = models.DateTimeField(
        auto_now_add=True,
    )

    date_modification = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        parts = [
            p
            for p in [
                self.nom,
                self.prenom,
                self.telephone,
            ]
            if p
        ]

        return " ".join(parts) or f"Fournisseur #{self.pk}"

    def _gen_unique_slug(self) -> str:
        max_length = 30

        for _ in range(5):
            candidate = uuid.uuid4().hex[:max_length]

            if not Fournisseur.objects.filter(
                slug=candidate
            ).exists():
                return candidate

        return uuid.uuid4().hex[:max_length]

    def save(self, *args, **kwargs):
        self.telephone = (
            self.telephone or ""
        ).strip()

        if not self.telephone:
            raise ValidationError({
                "telephone": (
                    "Le téléphone du fournisseur est obligatoire."
                )
            })

        if not self.slug:
            self.slug = self._gen_unique_slug()

        super().save(*args, **kwargs)


# ============================================================
# STATUT ACHAT
# ============================================================

STATUS_CONFIRMED = "confirmed"
STATUS_CANCELLED = "cancelled"

STATUS_CHOICES = [
    (STATUS_CONFIRMED, "Confirmé"),
    (STATUS_CANCELLED, "Annulé"),
]


# ============================================================
# ACHAT
# ============================================================

class Achat(models.Model):
    """
    Représente un achat fournisseur.

    Formule :

        HT =
            Σ(
                ProduitLine.quantite
                × ProduitLine.poids_unitaire_achat
                × ProduitLine.prix_achat_gramme
            )
            + frais_transport
            + frais_douane

        TTC = HT

    Le poids utilisé est celui enregistré au moment
    de l'achat dans ProduitLine.
    """

    STATUS_CONFIRMED = STATUS_CONFIRMED
    STATUS_CANCELLED = STATUS_CANCELLED
    STATUS_CHOICES = STATUS_CHOICES

    fournisseur = models.ForeignKey(
        "Fournisseur",
        on_delete=models.PROTECT,
        related_name="achats",
        related_query_name="achat",
    )

    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        related_name="achats",
        related_query_name="achat",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    description = models.TextField(
        null=True,
        blank=True,
        help_text="Note interne (motif, consignes, etc.)",
    )

    # ========================================================
    # FRAIS
    # ========================================================

    frais_transport = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    frais_douane = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    note = models.TextField(
        blank=True,
        default="",
    )

    # ========================================================
    # IDENTIFIANTS
    # ========================================================

    numero_achat = models.CharField(
        max_length=30,
        unique=True,
        db_index=True,
        null=True,
        blank=True,
    )

    reference_commande = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "Référence logique de commande fournisseur "
            "(ex: CMD-2026-0001)"
        ),
    )

    # ========================================================
    # TOTAUX
    # ========================================================

    montant_total_ht = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    montant_total_ttc = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    # ========================================================
    # STATUT
    # ========================================================

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_CONFIRMED,
    )

    cancel_reason = models.TextField(
        null=True,
        blank=True,
    )

    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="achats_annules",
    )

    # ========================================================
    # META
    # ========================================================

    class Meta:
        ordering = ["-id"]

        indexes = [
            models.Index(
                fields=["created_at"],
            ),
            models.Index(
                fields=["fournisseur"],
            ),
            models.Index(
                fields=["status"],
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    frais_transport__gte=0
                ),
                name="achat_frais_transport_gte_0",
            ),

            models.CheckConstraint(
                condition=Q(
                    frais_douane__gte=0
                ),
                name="achat_frais_douane_gte_0",
            ),

            models.CheckConstraint(
                condition=Q(
                    montant_total_ht__gte=0
                ),
                name="achat_ht_gte_0",
            ),

            models.CheckConstraint(
                condition=Q(
                    montant_total_ttc__gte=0
                ),
                name="achat_ttc_gte_0",
            ),

            models.CheckConstraint(
                condition=Q(
                    montant_total_ttc__gte=F(
                        "montant_total_ht"
                    )
                ),
                name="achat_ttc_gte_ht",
            ),

            models.CheckConstraint(
                name="achat_cancel_fields_consistency",
                condition=(
                    Q(
                        status=STATUS_CANCELLED,
                        cancelled_at__isnull=False,
                        cancelled_by__isnull=False,
                    )
                    |
                    Q(
                        status=STATUS_CONFIRMED,
                        cancelled_at__isnull=True,
                        cancelled_by__isnull=True,
                    )
                ),
            ),
        ]

    # ========================================================
    # STRING
    # ========================================================

    def __str__(self):
        nom = (
            getattr(
                self.fournisseur,
                "nom",
                None,
            )
            or "N/A"
        )

        return (
            f"Achat {self.numero_achat or self.pk}"
            f" – Fournisseur: {nom}"
        )

    # ========================================================
    # TAXE
    # ========================================================

    @property
    def montant_total_tax(self) -> Decimal:
        """
        TAX = TTC - HT.

        Actuellement aucune TVA fournisseur.
        """

        return (
            self.montant_total_ttc
            or Decimal("0.00")
        ) - (
            self.montant_total_ht
            or Decimal("0.00")
        )

    # ========================================================
    # CALCUL DU TOTAL
    # ========================================================

    def update_total(self, save: bool = True):
        """
        Recalcule le montant total de l'achat.

        IMPORTANT :
        utilise poids_unitaire_achat et non Produit.poids.
        """

        expr_ht = ExpressionWrapper(
            F("quantite")
            * Coalesce(
                F("poids_unitaire_achat"),
                Decimal("0.00"),
            )
            * Coalesce(
                F("prix_achat_gramme"),
                Decimal("0.00"),
            ),
            output_field=DecimalField(
                max_digits=18,
                decimal_places=6,
            ),
        )

        agg = (
            ProduitLine.objects
            .filter(
                lot__achat=self
            )
            .aggregate(
                base_ht=Coalesce(
                    Sum(expr_ht),
                    Decimal("0.00"),
                )
            )
        )

        base_ht = Decimal(
            str(
                agg["base_ht"]
                or "0.00"
            )
        )

        frais_transport = Decimal(
            str(
                self.frais_transport
                or "0.00"
            )
        )

        frais_douane = Decimal(
            str(
                self.frais_douane
                or "0.00"
            )
        )

        total_ht = (
            base_ht
            + frais_transport
            + frais_douane
        )

        self.montant_total_ht = (
            total_ht.quantize(
                TWOPLACES,
                rounding=ROUND_HALF_UP,
            )
        )

        # Pas de TVA fournisseur actuellement.
        self.montant_total_ttc = (
            self.montant_total_ht
        )

        if save:
            self.full_clean()

            self.save(
                update_fields=[
                    "montant_total_ht",
                    "montant_total_ttc",
                ]
            )

    # ========================================================
    # VALIDATION
    # ========================================================

    def clean(self):
        super().clean()

        if (
            self.montant_total_ht is not None
            and self.montant_total_ht < 0
        ):
            raise ValidationError({
                "montant_total_ht":
                    "Le montant HT doit être ≥ 0."
            })

        if (
            self.montant_total_ttc is not None
            and self.montant_total_ttc < 0
        ):
            raise ValidationError({
                "montant_total_ttc":
                    "Le montant TTC doit être ≥ 0."
            })

        if (
            self.montant_total_ttc
            or Decimal("0.00")
        ) < (
            self.montant_total_ht
            or Decimal("0.00")
        ):
            raise ValidationError(
                "Le montant TTC ne peut pas être "
                "inférieur au montant HT."
            )

        if (
            self.status == self.STATUS_CANCELLED
            and (
                not self.cancelled_at
                or not self.cancelled_by
            )
        ):
            raise ValidationError(
                "Achat annulé : 'cancelled_at' et "
                "'cancelled_by' sont requis."
            )

        if (
            self.status == self.STATUS_CONFIRMED
            and (
                self.cancelled_at
                or self.cancelled_by
            )
        ):
            raise ValidationError(
                "Achat confirmé : ne pas renseigner "
                "'cancelled_at' / 'cancelled_by'."
            )

    # ========================================================
    # SAVE
    # ========================================================

    def save(self, *args, **kwargs):
        if not self.numero_achat:

            today = timezone.localdate().strftime(
                "%Y%m%d"
            )

            prefix = f"ACH-{today}"

            for _ in range(20):

                suffix = "".join(
                    random.choices(
                        "0123456789",
                        k=4,
                    )
                )

                candidate = (
                    f"{prefix}-{suffix}"
                )

                if not Achat.objects.filter(
                    numero_achat=candidate
                ).exists():
                    self.numero_achat = candidate
                    break

            else:
                raise ValidationError({
                    "numero_achat": (
                        "Impossible de générer "
                        "un numéro d'achat unique."
                    )
                })

        super().save(*args, **kwargs)


# ============================================================
# LOT
# ============================================================

class Lot(models.Model):

    achat = models.ForeignKey(
        "purchase.Achat",
        on_delete=models.PROTECT,
        related_name="lots",
    )

    numero_lot = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
    )

    description = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    received_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )

    class Meta:
        ordering = [
            "received_at",
            "id",
        ]

    def __str__(self):
        return self.numero_lot


# ============================================================
# PRODUIT LINE
# ============================================================

class ProduitLine(models.Model):
    """
    Une ligne produit dans un lot.

    poids_unitaire_achat est le snapshot du poids
    au moment de l'achat.

    Cela permet de conserver l'historique même si
    Produit.poids est modifié ultérieurement.
    """

    # ========================================================
    # IDENTIFIANT UNIQUE
    # ========================================================

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )

    # ========================================================
    # RELATIONS
    # ========================================================

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

    # ========================================================
    # DONNÉES D'ACHAT
    # ========================================================

    poids_unitaire_achat = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "Poids unitaire constaté au moment de l'achat."
        ),
    )

    prix_achat_gramme = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    quantite = models.PositiveIntegerField()

    numero_ligne_lot = models.PositiveIntegerField(
        null=True,
        blank=True,
        editable=False,
    )

    # ========================================================
    # META
    # ========================================================

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
                fields=[
                    "lot",
                    "numero_ligne_lot",
                ],
                name="idx_pl_lot_numero",
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=Q(
                    quantite__gte=1
                ),
                name="ck_pl_qty_gte1",
            ),

            models.CheckConstraint(
                condition=Q(
                    prix_achat_gramme__gte=0
                ),
                name="produit_line_prix_achat_gte_0",
            ),

            # null est temporairement autorisé
            # pour permettre la migration
            # des anciennes données.
            models.CheckConstraint(
                condition=(
                    Q(
                        poids_unitaire_achat__isnull=True
                    )
                    |
                    Q(
                        poids_unitaire_achat__gt=0
                    )
                ),
                name="ck_pl_poids_achat_gt_0",
            ),

            models.UniqueConstraint(
                fields=[
                    "lot",
                    "produit",
                ],
                name="uniq_produit_per_lot",
            ),

            models.UniqueConstraint(
                fields=[
                    "lot",
                    "numero_ligne_lot",
                ],
                name="unique_numero_ligne_par_lot",
            ),
        ]

    # ========================================================
    # STRING
    # ========================================================

    def __str__(self):

        numero = (
            f"{self.numero_ligne_lot:02d}"
            if self.numero_ligne_lot is not None
            else "--"
        )

        return (
            f"{self.lot.numero_lot}"
            f" · ligne={numero}"
            f" · produit={self.produit_id}"
        )

    # ========================================================
    # VALIDATION
    # ========================================================

    def clean(self):
        super().clean()

        if (
            self.quantite is not None
            and self.quantite < 1
        ):
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
            self.poids_unitaire_achat is not None
            and self.poids_unitaire_achat <= 0
        ):
            raise ValidationError({
                "poids_unitaire_achat": (
                    "Le poids unitaire d'achat doit "
                    "être supérieur à zéro."
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

    # ========================================================
    # SAVE
    # ========================================================

    def save(self, *args, **kwargs):
        """
        Lors de la création :

        1. copie Produit.poids vers poids_unitaire_achat ;
        2. génère numero_ligne_lot.

        Le poids est donc figé au moment de l'achat.
        """

        is_new = self._state.adding

        # ====================================================
        # SNAPSHOT DU POIDS
        # ====================================================

        if (
            is_new
            and self.poids_unitaire_achat is None
        ):

            if not self.produit_id:
                raise ValidationError({
                    "produit":
                        "Le produit est obligatoire."
                })

            poids_produit = self.produit.poids

            if (
                poids_produit is None
                or poids_produit <= 0
            ):
                raise ValidationError({
                    "poids_unitaire_achat": (
                        "Le produit doit avoir un poids "
                        "strictement supérieur à zéro."
                    )
                })

            self.poids_unitaire_achat = (
                poids_produit
            )

        # ====================================================
        # NUMÉROTATION
        # ====================================================

        if (
            is_new
            and self.numero_ligne_lot is None
        ):

            if not self.lot_id:
                raise ValidationError({
                    "lot":
                        "Le lot est obligatoire."
                })

            with transaction.atomic():

                # Verrouille le lot pendant
                # l'attribution du numéro.
                Lot.objects.select_for_update().get(
                    pk=self.lot_id
                )

                dernier_numero = (
                    ProduitLine.objects
                    .filter(
                        lot_id=self.lot_id
                    )
                    .aggregate(
                        maximum=Max(
                            "numero_ligne_lot"
                        )
                    )
                    ["maximum"]
                )

                self.numero_ligne_lot = (
                    (dernier_numero or 0)
                    + 1
                )

                self.full_clean()

                return super().save(
                    *args,
                    **kwargs,
                )

        self.full_clean()

        return super().save(
            *args,
            **kwargs,
        )

    # ========================================================
    # POIDS TOTAL
    # ========================================================

    @property
    def poids_total_calc(self):
        """
        quantité × poids historique unitaire.
        """

        if self.poids_unitaire_achat is None:
            return None

        quantite = Decimal(
            self.quantite or 0
        )

        poids = Decimal(
            str(
                self.poids_unitaire_achat
            )
        )

        return (
            quantite * poids
        ).quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )

    # ========================================================
    # MONTANT ACHAT
    # ========================================================

    @property
    def montant_achat_calc(self):
        """
        quantité
        × poids_unitaire_achat
        × prix_achat_gramme
        """

        if (
            self.poids_unitaire_achat is None
            or self.prix_achat_gramme is None
        ):
            return Decimal("0.00")

        montant = (
            Decimal(
                self.quantite or 0
            )
            * Decimal(
                str(
                    self.poids_unitaire_achat
                )
            )
            * Decimal(
                str(
                    self.prix_achat_gramme
                )
            )
        )

        return montant.quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )

    # ========================================================
    # NUMÉRO LIGNE FORMATÉ
    # ========================================================

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
    

