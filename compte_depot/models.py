# compte_depot/models.py
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import CheckConstraint, F, Q

from sale.models import Client
from sale.services.montant_service import ZERO, money_strict


class ClientDepot(Client):
    photo = models.ImageField(
        upload_to="client/",
        default="client/default.jpg",
        null=True,
        blank=True,
    )

    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clients_depot",
    )

    class Meta:
        verbose_name = "Client (compte dépôt)"
        verbose_name_plural = "Clients (compte dépôt)"
        
        
class CompteDepot(models.Model):
    
    client = models.OneToOneField(
        ClientDepot,
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        related_name="compte",
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
        nom = self.client.full_name if self.client else "Sans client"
        return f"{self.numero_compte} - {nom}"

    def clean(self):
        super().clean()

        if self.solde is not None:
            self.solde = money_strict(
                self.solde,
                field="solde",
            )


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
        "compte_depot.CompteDepot",
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    type_transaction = models.CharField(max_length=20, choices=TYPE_CHOICES)
    montant = models.DecimalField(max_digits=12, decimal_places=2)
    date_transaction = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions_effectuees",
    )
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default=STAT_TERMINE,
    )
    reference = models.CharField(max_length=255, null=True, blank=True)
    commentaire = models.TextField(null=True, blank=True)
    solde_avant = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    solde_apres = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        ordering = ["-date_transaction"]
        verbose_name = "Transaction compte dépôt"
        verbose_name_plural = "Transactions compte dépôt"
        constraints = [
            models.CheckConstraint(
                condition=Q(montant__gt=0),
                name="ck_compte_depot_tx_montant_gt_0",
            ),
            models.CheckConstraint(
                condition=Q(solde_avant__gte=0),
                name="ck_compte_depot_tx_solde_avant_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(solde_apres__gte=0),
                name="ck_compte_depot_tx_solde_apres_gte_0",
            ),
            models.CheckConstraint(
                condition=(
                    (
                        Q(statut="TERMINE")
                        & (
                            (
                                Q(type_transaction="DEPOT")
                                & Q(solde_apres=F("solde_avant") + F("montant"))
                            )
                            | (
                                Q(type_transaction="RETRAIT")
                                & Q(solde_apres=F("solde_avant") - F("montant"))
                            )
                        )
                    )
                    | (
                        Q(statut__in=["ATTENTE", "ECHOUE"])
                        & Q(type_transaction__in=["DEPOT", "RETRAIT"])
                        & Q(solde_apres=F("solde_avant"))
                    )
                ),
                name="ck_compte_depot_tx_coherence_solde",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_type_transaction_display()} de {self.montant} "
            f"FCFA sur {self.compte.numero_compte}"
        )

    def clean(self):
        super().clean()
        errors = {}

        for champ in ("montant", "solde_avant", "solde_apres"):
            valeur = getattr(self, champ)
            if valeur is not None:
                try:
                    setattr(self, champ, money_strict(valeur, field=champ))
                except ValidationError as exc:
                    errors[champ] = exc.messages

        if errors:
            raise ValidationError(errors)

        if self.montant is not None and self.montant <= ZERO:
            errors["montant"] = "Le montant doit être strictement supérieur à zéro."
        for champ in ("solde_avant", "solde_apres"):
            valeur = getattr(self, champ)
            if valeur is not None and valeur < ZERO:
                errors[champ] = "Le solde ne peut pas être négatif."

        if self.type_transaction not in (self.TYPE_DEPOT, self.TYPE_RETRAIT):
            errors["type_transaction"] = "Type de transaction invalide."
        if self.statut not in (self.STAT_TERMINE, self.STAT_ATTENTE, self.STAT_ECHOUE):
            errors["statut"] = "Statut de transaction invalide."

        if not errors and all(
            getattr(self, champ) is not None
            for champ in ("montant", "solde_avant", "solde_apres")
        ):
            if self.statut == self.STAT_TERMINE:
                if self.type_transaction == self.TYPE_DEPOT:
                    attendu = self.solde_avant + self.montant
                else:
                    attendu = self.solde_avant - self.montant
            else:
                attendu = self.solde_avant

            if self.solde_apres != attendu:
                errors["solde_apres"] = (
                    "Le solde après transaction est incohérent "
                    "avec le type et le statut de l'opération."
                )

        if self.pk:
            ancien = type(self).objects.filter(pk=self.pk).values(
                "compte_id", "type_transaction", "montant", "statut",
                "solde_avant", "solde_apres", "user_id", "reference",
                "commentaire", "date_transaction",
            ).first()
            if ancien:
                if ancien["statut"] in (self.STAT_TERMINE, self.STAT_ECHOUE):
                    if any(getattr(self, champ) != valeur for champ, valeur in ancien.items()):
                        errors["statut"] = "Une transaction terminée ou échouée est immuable."
                else:
                    if self.statut not in (self.STAT_ATTENTE, self.STAT_TERMINE, self.STAT_ECHOUE):
                        errors["statut"] = "Transition de statut interdite."
                    for champ in (
                        "compte_id", "type_transaction", "montant", "solde_avant",
                        "user_id", "reference", "commentaire", "date_transaction",
                    ):
                        if getattr(self, champ) != ancien[champ]:
                            errors[champ.removesuffix("_id")] = (
                                "Ce champ ne peut pas être modifié après la création."
                            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def full_name(self):
        client = getattr(self.compte, "client", None)
        if not client:
            return ""
        nom = getattr(client, "full_name", None) or getattr(client, "nom_complet", None)
        return nom() if callable(nom) else (nom or "")

# table de protection contre les doublons
# ============================================================
# PROTECTION CONTRE LES OPÉRATIONS EN DOUBLE
# ============================================================

class DepotIdempotence(models.Model):

    cle = models.UUIDField(
        unique=True,
    )

    empreinte = models.CharField(
        max_length=64,
    )

    reponse = models.JSONField(
        null=True,
        blank=True,
    )

    code_http = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="operations_depot_idempotentes",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return str(self.cle)