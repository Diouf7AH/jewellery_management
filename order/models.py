from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.utils import timezone

ZERO = Decimal("0.00")
HALF = Decimal("0.50")


def dec(v) -> Decimal:
    if v in (None, "", "null"):
        return ZERO
    try:
        return Decimal(str(v))
    except Exception:
        raise ValidationError(f"Valeur décimale invalide : {v}")


class Ouvrier(models.Model):
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100, blank=True, default="")
    telephone = models.CharField(max_length=30, blank=True, default="")
    specialite = models.CharField(max_length=120, blank=True, default="")
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nom", "prenom"]

    def __str__(self):
        return f"{self.prenom} {self.nom}".strip()


class CommandeClient(models.Model):
    STATUT_BROUILLON = "BROUILLON"
    STATUT_EN_ATTENTE = "EN_ATTENTE"
    STATUT_EN_PRODUCTION = "EN_PRODUCTION"
    STATUT_TERMINEE = "TERMINEE"
    STATUT_LIVREE = "LIVREE"
    STATUT_ANNULEE = "ANNULEE"

    STATUT_CHOICES = [
        (STATUT_BROUILLON, "Brouillon"),
        (STATUT_EN_ATTENTE, "En attente"),
        (STATUT_EN_PRODUCTION, "En production"),
        (STATUT_TERMINEE, "Terminée"),
        (STATUT_LIVREE, "Livrée"),
        (STATUT_ANNULEE, "Annulée"),
    ]

    numero_commande = models.CharField(max_length=50, unique=True, editable=False)

    client = models.ForeignKey(
        "sale.Client",
        on_delete=models.PROTECT,
        related_name="commandes_clients",
    )
    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        related_name="commandes_clients",
    )
    vendor = models.ForeignKey(
        "vendor.Vendor",
        on_delete=models.PROTECT,
        related_name="commandes_clients",
    )
    ouvrier = models.ForeignKey(
        Ouvrier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commandes_clients",
    )

    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default=STATUT_BROUILLON,
        db_index=True,
    )

    date_commande = models.DateTimeField(default=timezone.now)
    date_debut = models.DateField(null=True, blank=True)
    date_fin_prevue = models.DateField(null=True, blank=True)
    date_fin_reelle = models.DateField(null=True, blank=True)
    date_livraison = models.DateTimeField(null=True, blank=True)

    date_affectation_ouvrier = models.DateTimeField(null=True, blank=True)
    date_depot_boutique = models.DateTimeField(null=True, blank=True)

    montant_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)

    notes_client = models.TextField(blank=True, default="")
    notes_internes = models.TextField(blank=True, default="")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commandes_client_creees",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commandes_client_modifiees",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["numero_commande"]),
            models.Index(fields=["statut"]),
            models.Index(fields=["date_commande"]),
            models.Index(fields=["bijouterie", "statut"]),
            models.Index(fields=["vendor", "statut"]),
        ]

    def __str__(self):
        return self.numero_commande

    def clean(self):
        if self.vendor and self.vendor.bijouterie_id and self.bijouterie_id:
            if self.vendor.bijouterie_id != self.bijouterie_id:
                raise ValidationError("Le vendeur ne dépend pas de cette bijouterie.")

        if self.date_debut and self.date_fin_prevue and self.date_fin_prevue < self.date_debut:
            raise ValidationError("La date de fin prévue ne peut pas être antérieure à la date de début.")

        if self.statut == self.STATUT_EN_PRODUCTION and not self.ouvrier:
            raise ValidationError("Un ouvrier est obligatoire quand la commande est en production.")

        if self.statut == self.STATUT_TERMINEE and not self.date_depot_boutique:
            raise ValidationError("La date de dépôt boutique est obligatoire quand la commande est terminée.")

        if self.statut == self.STATUT_LIVREE and not self.date_livraison:
            raise ValidationError("La date de livraison est obligatoire quand la commande est livrée.")

    def save(self, *args, **kwargs):
        if not self.numero_commande:
            self.numero_commande = self.generate_numero_commande()
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def generate_numero_commande(cls) -> str:
        today = timezone.localdate()
        prefix = f"CMD-{today.strftime('%Y%m%d')}-"
        last_obj = (
            cls.objects
            .filter(numero_commande__startswith=prefix)
            .order_by("-id")
            .first()
        )

        last_seq = 0
        if last_obj and last_obj.numero_commande:
            try:
                last_seq = int(last_obj.numero_commande.split("-")[-1])
            except Exception:
                last_seq = 0

        return f"{prefix}{last_seq + 1:04d}"

    def recalculate_total(self, save=True):
        total = self.lignes.aggregate(total=Sum("sous_total"))["total"] or ZERO
        self.montant_total = dec(total)
        if save:
            self.save(update_fields=["montant_total", "updated_at"])

    @property
    def acompte_minimum_requis(self) -> Decimal:
        return (dec(self.montant_total) * HALF).quantize(Decimal("0.01"))

    @property
    def total_acompte_paye(self) -> Decimal:
        return sum(
            (facture.total_paye for facture in self.factures.filter(type_facture="acompte")),
            ZERO
        )

    @property
    def total_paye_global(self):
        from django.apps import apps
        PaiementLigne = apps.get_model("sale", "PaiementLigne")

        total = PaiementLigne.objects.filter(
            paiement__facture__commande_client=self
        ).aggregate(total=Sum("montant_paye"))["total"]

        return total or ZERO

    @property
    def reste_global(self) -> Decimal:
        return max(dec(self.montant_total) - dec(self.total_paye_global), ZERO)

    @property
    def acompte_regle(self) -> bool:
        return self.total_acompte_paye >= self.acompte_minimum_requis

    @property
    def peut_passer_en_production(self) -> bool:
        return self.acompte_regle and self.statut in [self.STATUT_BROUILLON, self.STATUT_EN_ATTENTE]

    @property
    def peut_etre_livree(self) -> bool:
        return self.statut == self.STATUT_TERMINEE and self.reste_global == ZERO

    # on ne stock pas le pdf du bon de commande, on le génère à la volée quand nécessaire
    def generate_bon_commande(self):
        from .services.commande_pdf_service import generate_bon_commande_pdf
        return generate_bon_commande_pdf(commande=self)


class CommandeProduitClient(models.Model):
    commande = models.ForeignKey(
        CommandeClient,
        on_delete=models.CASCADE,
        related_name="lignes",
    )

    produit = models.ForeignKey(
        "store.Produit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commande_client_lignes",
    )

    nom_modele = models.CharField(max_length=150)
    categorie = models.ForeignKey(
        "store.Categorie",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commande_client_lignes",
    )
    marque = models.ForeignKey(
        "store.Marque",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commande_client_lignes",
    )
    modele = models.ForeignKey(
        "store.Modele",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commande_client_lignes",
    )
    purete = models.ForeignKey(
        "store.Purete",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commande_client_lignes",
    )

    quantite = models.PositiveIntegerField(default=1)
    poids = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    taille = models.CharField(max_length=50, blank=True, default="")
    prix_gramme = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    sous_total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)

    photo = models.ImageField(upload_to="commandes/produits/", null=True, blank=True)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.commande.numero_commande} - {self.nom_modele}"

    def clean(self):
        if self.quantite < 1:
            raise ValidationError("La quantité doit être >= 1.")
        if dec(self.poids) <= ZERO:
            raise ValidationError("Le poids doit être > 0.")
        if dec(self.prix_gramme) < ZERO:
            raise ValidationError("Le prix/gramme ne peut pas être négatif.")

    def save(self, *args, **kwargs):
        self.sous_total = (dec(self.poids) * dec(self.prix_gramme) * Decimal(self.quantite)).quantize(Decimal("0.01"))
        self.full_clean()
        super().save(*args, **kwargs)


class CommandeClientHistorique(models.Model):
    commande = models.ForeignKey(
        CommandeClient,
        on_delete=models.CASCADE,
        related_name="historiques",
    )
    ancien_statut = models.CharField(max_length=20, blank=True, default="")
    nouveau_statut = models.CharField(max_length=20)
    commentaire = models.TextField(blank=True, default="")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.commande.numero_commande}: {self.ancien_statut} -> {self.nouveau_statut}"
    
    
