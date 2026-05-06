from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.db.models import CheckConstraint, F, Q

from sale.models import Client


class ClientDepot(Client):
    CNI = models.CharField(max_length=50, blank=True, null=True)
    photo = models.ImageField(upload_to="client/", default="client/default.jpg", null=True, blank=True)

    class Meta:
        verbose_name = "Client (compte dépôt)"
        verbose_name_plural = "Clients (compte dépôt)"


class CompteDepot(models.Model):
    client = models.OneToOneField(
        ClientDepot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="compte"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comptes_crees"
    )
    numero_compte = models.CharField(max_length=30, unique=True, db_index=True)
    solde = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            CheckConstraint(
                check=Q(solde__gte=0),
                name="ck_compte_depot_solde_gte_0",
            ),
        ]
        indexes = [
            models.Index(fields=["client"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        nom = getattr(self.client, "full_name", None) or getattr(self.client, "nom_complet", None)
        if callable(nom):
            nom = nom()
        return f"{self.numero_compte} - {nom or 'Sans client'}"

    def clean(self):
        super().clean()
        if self.solde is not None:
            self.solde = Decimal(self.solde).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class CompteDepotTransaction(models.Model):
    TYPE_DEPOT = "DEPOT"
    TYPE_RETRAIT = "RETRAIT"
    TYPE_CHOICES = (
        (TYPE_DEPOT, "Dépôt"),
        (TYPE_RETRAIT, "Retrait"),
    )

    STAT_TERMINE = "TERMINE"
    STAT_ECHOUE = "ECHOUE"
    STAT_ATTENTE = "ATTENTE"
    STATUT_CHOICES = (
        (STAT_TERMINE, "Terminé"),
        (STAT_ECHOUE, "Échoué"),
        (STAT_ATTENTE, "En attente"),
    )

    compte = models.ForeignKey(
        CompteDepot,
        on_delete=models.CASCADE,
        related_name="transactions"
    )
    type_transaction = models.CharField(max_length=20, choices=TYPE_CHOICES)
    montant = models.DecimalField(max_digits=12, decimal_places=2)
    date_transaction = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions_effectuees"
    )
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default=STAT_TERMINE)

    reference = models.CharField(max_length=255, null=True, blank=True)
    commentaire = models.TextField(null=True, blank=True)

    solde_avant = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    solde_apres = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["-date_transaction"]
        verbose_name = "Transaction compte dépôt"
        verbose_name_plural = "Transactions compte dépôt"

        constraints = [
            CheckConstraint(
                check=Q(montant__gt=0),
                name="ck_compte_depot_tx_montant_gt_0"
            ),

            CheckConstraint(
                check=Q(solde_avant__gte=0),
                name="ck_compte_depot_tx_solde_avant_gte_0"
            ),

            CheckConstraint(
                check=Q(solde_apres__gte=0),
                name="ck_compte_depot_tx_solde_apres_gte_0"
            ),

            # 🔥 CONTRAINTE COHÉRENCE
            CheckConstraint(
            check=(
                # DEPOT
                (
                    Q(type_transaction='DEPOT') &
                    Q(solde_apres=F('solde_avant') + F('montant'))
                )
                |
                # RETRAIT
                (
                    Q(type_transaction='RETRAIT') &
                    Q(solde_apres=F('solde_avant') - F('montant'))
                )
            ),
            name="ck_compte_depot_tx_coherence_solde"
        ),
        ]

    def __str__(self):
        return f"{self.get_type_transaction_display()} de {self.montant} FCFA sur {self.compte.numero_compte}"

    def clean(self):
        super().clean()
        if self.montant is not None:
            self.montant = Decimal(self.montant).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if self.solde_avant is not None:
            self.solde_avant = Decimal(self.solde_avant).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if self.solde_apres is not None:
            self.solde_apres = Decimal(self.solde_apres).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def full_name(self):
        c = getattr(self.compte, "client", None)
        if not c:
            return ""
        nom = getattr(c, "full_name", None) or getattr(c, "nom_complet", None)
        return nom() if callable(nom) else (nom or "")
