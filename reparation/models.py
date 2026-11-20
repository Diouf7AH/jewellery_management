"""Modèles de réparation Rio-Gold, indépendants des ventes."""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from sale.models import ClientBijouterie

ZERO = Decimal("0.00")


# ============================================================
# COMPTEUR DES RÉPARATIONS
# ============================================================

class ReparationCounter(models.Model):
    """Compteur quotidien par bijouterie."""

    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        related_name="compteurs_reparation",
    )

    jour = models.DateField()

    derniere_valeur = models.PositiveIntegerField(
        default=0,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["bijouterie", "jour"],
                name="uniq_reparation_counter_shop_day",
            ),
        ]

    def __str__(self):
        return (
            f"{self.bijouterie_id} - "
            f"{self.jour} - "
            f"{self.derniere_valeur}"
        )


# ============================================================
# DOSSIER DE RÉPARATION
# ============================================================

class Reparation(models.Model):
    """
    Dossier de réparation.

    Un dossier contient un ou plusieurs bijoux.

    Le paiement concerne le dossier complet.
    La restitution concerne tous les bijoux du dossier.
    """

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        EN_COURS = "en_cours", "En cours"
        PRET = "pret", "Prêt"
        RESTITUE = "restitue", "Restitué"
        ANNULE = "annule", "Annulé"

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    numero_reparation = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
        db_index=True,
    )

    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        related_name="reparations",
    )

    client = models.ForeignKey(
        "sale.Client",
        on_delete=models.PROTECT,
        related_name="reparations",
    )

    # Vendeur ayant reçu les bijoux.
    # Référence historique immuable.
    vendeur = models.ForeignKey(
        "vendor.Vendor",
        on_delete=models.PROTECT,
        related_name="reparations",
    )

    # Total de tous les bijoux du dossier.
    # Calculé par le service métier.
    prix_convenu = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    date_depot = models.DateTimeField(
        default=timezone.now,
        editable=False,
    )

    date_prevue = models.DateField(
        null=True,
        blank=True,
    )

    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.EN_ATTENTE,
        db_index=True,
    )

    date_restitution = models.DateTimeField(
        null=True,
        blank=True,
    )

    restitue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reparations_restituees",
    )

    class Meta:
        ordering = ["-date_depot"]

        constraints = [
            models.CheckConstraint(
                condition=Q(prix_convenu__gt=0),
                name="reparation_prix_positif",
            ),
        ]

        indexes = [
            models.Index(
                fields=["bijouterie", "statut"],
                name="idx_rep_shop_statut",
            ),
            models.Index(
                fields=["bijouterie", "date_depot"],
                name="idx_rep_shop_depot",
            ),
        ]

    def __str__(self):
        return (
            self.numero_reparation
            or "Nouvelle réparation"
        )

    @property
    def montant_total_bijoux(self):
        """Somme des prix des bijoux du dossier."""

        if not self.pk:
            return ZERO

        total = self.bijoux.aggregate(
            total=Sum("prix_reparation")
        )["total"]

        return total if total is not None else ZERO

    @property
    def nombre_bijoux(self):
        """Nombre de bijoux du dossier."""

        if not self.pk:
            return 0

        return self.bijoux.count()

    @property
    def paiement_effectue(self):
        """Indique si un paiement existe."""

        if not self.pk:
            return False

        return PaiementReparation.objects.filter(
            reparation_id=self.pk
        ).exists()

    @property
    def est_restituee(self):
        """Indique si la restitution est confirmée."""

        return (
            self.statut == self.Statut.RESTITUE
            and self.date_restitution is not None
            and self.restitue_par_id is not None
        )

    def verifier_total_bijoux(self):
        """
        À appeler après création des lignes et
        avant paiement ou restitution.
        """

        if not self.pk:
            raise ValidationError(
                "Le dossier doit être enregistré."
            )

        if not self.bijoux.exists():
            raise ValidationError({
                "bijoux": (
                    "Le dossier doit contenir "
                    "au moins un bijou."
                )
            })

        if self.montant_total_bijoux != self.prix_convenu:
            raise ValidationError({
                "prix_convenu": (
                    "Le montant du dossier ne correspond "
                    "pas au total des bijoux."
                )
            })

        return True

    def clean(self):
        super().clean()

        errors = {}

        if self.vendeur_id and self.bijouterie_id:
            if (
                self.vendeur.bijouterie_id
                != self.bijouterie_id
            ):
                errors["vendeur"] = (
                    "Le vendeur n'appartient pas "
                    "à cette bijouterie."
                )

        # Vérification uniquement au dépôt.
        if (
            self._state.adding
            and self.client_id
            and self.bijouterie_id
        ):
            association = ClientBijouterie.objects.filter(
                client_id=self.client_id,
                bijouterie_id=self.bijouterie_id,
            ).exists()

            if not association:
                errors["client"] = (
                    "Le client n'est pas associé "
                    "à cette bijouterie."
                )

        if self.pk:
            ancien = type(self).objects.filter(
                pk=self.pk
            ).values(
                "vendeur_id",
                "bijouterie_id",
                "client_id",
                "prix_convenu",
                "statut",
            ).first()

            if ancien:
                for champ in (
                    "vendeur_id",
                    "bijouterie_id",
                    "client_id",
                ):
                    if getattr(self, champ) != ancien[champ]:
                        errors[champ.removesuffix("_id")] = (
                            "Cette référence historique "
                            "ne peut pas être modifiée."
                        )

                paiement = PaiementReparation.objects.filter(
                    reparation_id=self.pk
                ).exists()

                if (
                    paiement
                    and self.prix_convenu
                    != ancien["prix_convenu"]
                ):
                    errors["prix_convenu"] = (
                        "Impossible de modifier le prix "
                        "après paiement."
                    )

                if ancien["statut"] == self.Statut.RESTITUE:
                    if self.statut != self.Statut.RESTITUE:
                        errors["statut"] = (
                            "Une réparation restituée "
                            "ne peut pas être réouverte."
                        )

                if ancien["statut"] == self.Statut.ANNULE:
                    if self.statut != self.Statut.ANNULE:
                        errors["statut"] = (
                            "Une réparation annulée "
                            "ne peut pas être réouverte."
                        )

        if (
            self.prix_convenu is None
            or self.prix_convenu <= ZERO
        ):
            errors["prix_convenu"] = (
                "Le prix convenu doit être positif."
            )

        if (
            self.date_prevue
            and self.date_depot
            and self.date_prevue
            < timezone.localdate(self.date_depot)
        ):
            errors["date_prevue"] = (
                "La date prévue ne peut pas "
                "précéder le dépôt."
            )

        if self.statut == self.Statut.RESTITUE:
            if (
                self.date_restitution is None
                or self.restitue_par_id is None
            ):
                errors["statut"] = (
                    "La restitution exige une date "
                    "et un utilisateur."
                )

            if self.pk:
                paiement_integral = (
                    PaiementReparation.objects.filter(
                        reparation_id=self.pk,
                        montant_paye=self.prix_convenu,
                    ).exists()
                )

                if not paiement_integral:
                    errors["statut"] = (
                        "Le paiement intégral est "
                        "obligatoire avant restitution."
                    )
                else:
                    try:
                        self.verifier_total_bijoux()
                    except ValidationError as exc:
                        errors["prix_convenu"] = exc.messages

        elif (
            self.date_restitution is not None
            or self.restitue_par_id is not None
        ):
            errors["date_restitution"] = (
                "Les informations de restitution "
                "exigent le statut RESTITUE."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self._state.adding:
            if not self.numero_reparation:
                raise ValidationError({
                    "numero_reparation": (
                        "Utilisez le service "
                        "creer_reparation."
                    )
                })

            if self.statut != self.Statut.EN_ATTENTE:
                raise ValidationError({
                    "statut": (
                        "Une nouvelle réparation doit "
                        "être en attente."
                    )
                })

        self.full_clean()

        return super().save(*args, **kwargs)


# ============================================================
# BIJOUX D'UNE RÉPARATION
# ============================================================

class ReparationBijou(models.Model):
    """
    Bijou déposé dans un dossier de réparation.

    Chaque bijou possède ses informations,
    son travail et son prix.
    """

    reparation = models.ForeignKey(
        "reparation.Reparation",
        on_delete=models.PROTECT,
        related_name="bijoux",
    )

    numero_ligne = models.PositiveIntegerField()

    type_bijou = models.CharField(
        max_length=100,
    )

    description_bijou = models.TextField()

    poids = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
    )

    purete = models.CharField(
        max_length=30,
        blank=True,
    )

    etat_reception = models.TextField()

    travail_demande = models.TextField()

    travail_effectue = models.TextField(
        blank=True,
    )

    prix_reparation = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    class Meta:
        ordering = ["numero_ligne"]

        constraints = [
            models.UniqueConstraint(
                fields=["reparation", "numero_ligne"],
                name="uniq_reparation_bijou_ligne",
            ),
            models.CheckConstraint(
                condition=Q(numero_ligne__gt=0),
                name="reparation_bijou_ligne_positive",
            ),
            models.CheckConstraint(
                condition=Q(prix_reparation__gt=0),
                name="reparation_bijou_prix_positif",
            ),
            models.CheckConstraint(
                condition=(
                    Q(poids__isnull=True)
                    | Q(poids__gt=0)
                ),
                name="reparation_bijou_poids_positif",
            ),
        ]

    def __str__(self):
        return (
            f"{self.reparation.numero_reparation} "
            f"- Bijou {self.numero_ligne}"
        )

    def clean(self):
        super().clean()

        errors = {}

        if (
            self.numero_ligne is None
            or self.numero_ligne <= 0
        ):
            errors["numero_ligne"] = (
                "Le numéro de ligne doit être positif."
            )

        if (
            self.prix_reparation is None
            or self.prix_reparation <= ZERO
        ):
            errors["prix_reparation"] = (
                "Le prix de réparation doit être positif."
            )

        if (
            self.poids is not None
            and self.poids <= 0
        ):
            errors["poids"] = (
                "Le poids doit être positif."
            )

        ancien = None

        if self.pk:
            ancien = type(self).objects.filter(
                pk=self.pk
            ).first()

            if ancien:
                if (
                    self.reparation_id
                    != ancien.reparation_id
                ):
                    errors["reparation"] = (
                        "Impossible de déplacer un bijou "
                        "vers un autre dossier."
                    )

                if (
                    self.numero_ligne
                    != ancien.numero_ligne
                ):
                    errors["numero_ligne"] = (
                        "Le numéro de ligne est immuable."
                    )

        if self.reparation_id:
            reparation = self.reparation

            if reparation.statut in (
                Reparation.Statut.RESTITUE,
                Reparation.Statut.ANNULE,
            ):
                errors["reparation"] = (
                    "Impossible de modifier les bijoux "
                    "d'un dossier clôturé."
                )

            paiement_existe = (
                PaiementReparation.objects.filter(
                    reparation_id=self.reparation_id
                ).exists()
            )

            if paiement_existe:
                if self._state.adding:
                    errors["reparation"] = (
                        "Impossible d'ajouter un bijou "
                        "après paiement."
                    )

                elif ancien:
                    champs_proteges = (
                        "type_bijou",
                        "description_bijou",
                        "poids",
                        "purete",
                        "etat_reception",
                        "travail_demande",
                        "travail_effectue",
                        "prix_reparation",
                    )

                    modification = any(
                        getattr(self, champ)
                        != getattr(ancien, champ)
                        for champ in champs_proteges
                    )

                    if modification:
                        errors["reparation"] = (
                            "Impossible de modifier un bijou "
                            "après paiement."
                        )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()

        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        reparation = self.reparation

        if reparation.statut in (
            Reparation.Statut.RESTITUE,
            Reparation.Statut.ANNULE,
        ):
            raise ValidationError(
                "Impossible de supprimer un bijou "
                "d'un dossier clôturé."
            )

        if PaiementReparation.objects.filter(
            reparation_id=self.reparation_id
        ).exists():
            raise ValidationError(
                "Impossible de supprimer un bijou "
                "après paiement."
            )

        return super().delete(*args, **kwargs)


# ============================================================
# PAIEMENT D'UNE RÉPARATION
# ============================================================

class PaiementReparation(models.Model):
    """
    Un dossier = au maximum un paiement intégral.

    Un paiement = un seul mode.

    Aucun paiement partiel.
    """

    reparation = models.OneToOneField(
        "reparation.Reparation",
        on_delete=models.PROTECT,
        related_name="paiement",
    )

    mode_paiement = models.ForeignKey(
        "sale.ModePaiement",
        on_delete=models.PROTECT,
        related_name="paiements_reparation",
    )

    montant_paye = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    compte_depot = models.ForeignKey(
        "compte_depot.CompteDepot",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    transaction_depot = models.ForeignKey(
        "compte_depot.CompteDepotTransaction",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    reference = models.CharField(
        max_length=150,
        blank=True,
    )

    idempotency_key = models.UUIDField(
        unique=True,
    )

    request_fingerprint = models.CharField(
        max_length=64,
    )

    response_snapshot = models.JSONField(
        null=True,
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="paiements_reparation",
    )

    date_paiement = models.DateTimeField(
        default=timezone.now,
    )

    class Meta:
        ordering = ["-date_paiement"]

        constraints = [
            models.CheckConstraint(
                condition=Q(montant_paye__gt=0),
                name="paiement_reparation_montant_positif",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        compte_depot__isnull=True,
                        transaction_depot__isnull=True,
                    )
                    | Q(
                        compte_depot__isnull=False,
                        transaction_depot__isnull=False,
                    )
                ),
                name="paiement_rep_depot_transaction_coherents",
            ),
        ]

    def __str__(self):
        return (
            "Paiement réparation "
            f"{self.reparation.numero_reparation}"
        )

    def clean(self):
        super().clean()

        errors = {}

        if self.reparation_id:
            reparation = self.reparation

            if (
                self.montant_paye is not None
                and self.montant_paye
                != reparation.prix_convenu
            ):
                errors["montant_paye"] = (
                    "Le paiement doit couvrir exactement "
                    "le prix convenu."
                )

            if self._state.adding:
                if reparation.statut != Reparation.Statut.PRET:
                    errors["reparation"] = (
                        "La réparation doit être prête "
                        "avant paiement."
                    )

                try:
                    reparation.verifier_total_bijoux()
                except ValidationError as exc:
                    errors["reparation"] = exc.messages

        if self.mode_paiement_id:
            mode = self.mode_paiement

            if self._state.adding and not mode.active:
                errors["mode_paiement"] = (
                    "Ce mode de paiement est inactif."
                )

            if mode.code == "depot":
                if (
                    not self.compte_depot_id
                    or not self.transaction_depot_id
                ):
                    errors["compte_depot"] = (
                        "Le mode dépôt exige un compte "
                        "et une transaction de retrait."
                    )

            elif (
                self.compte_depot_id
                or self.transaction_depot_id
            ):
                errors["mode_paiement"] = (
                    "Un compte dépôt n'est autorisé "
                    "qu'avec le mode dépôt."
                )

            if (
                self._state.adding
                and mode.necessite_reference
                and not self.reference.strip()
            ):
                errors["reference"] = (
                    "Une référence est obligatoire."
                )

        if (
            self.compte_depot_id
            and self.transaction_depot_id
        ):
            transaction = self.transaction_depot

            if (
                transaction.compte_id
                != self.compte_depot_id
            ):
                errors["transaction_depot"] = (
                    "La transaction ne correspond pas "
                    "au compte dépôt."
                )

            elif (
                transaction.type_transaction
                != transaction.TYPE_RETRAIT
            ):
                errors["transaction_depot"] = (
                    "La transaction doit être un retrait."
                )

            elif (
                transaction.statut
                != transaction.STAT_TERMINE
            ):
                errors["transaction_depot"] = (
                    "Le retrait doit être terminé."
                )

            elif (
                transaction.montant
                != self.montant_paye
            ):
                errors["transaction_depot"] = (
                    "Le retrait doit correspondre "
                    "au montant payé."
                )

            if (
                self.reparation_id
                and self.compte_depot.client_id
                != self.reparation.client_id
            ):
                errors["compte_depot"] = (
                    "Ce compte dépôt n'appartient pas "
                    "au client."
                )

        if (
            bool(self.compte_depot_id)
            != bool(self.transaction_depot_id)
        ):
            errors["compte_depot"] = (
                "Le compte dépôt et sa transaction "
                "doivent être renseignés ensemble."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            ancien = type(self).objects.filter(
                pk=self.pk
            ).values(
                "reparation_id",
                "mode_paiement_id",
                "montant_paye",
                "compte_depot_id",
                "transaction_depot_id",
                "reference",
                "idempotency_key",
                "request_fingerprint",
                "created_by_id",
                "date_paiement",
            ).first()

            if ancien:
                for champ, valeur in ancien.items():
                    if getattr(self, champ) != valeur:
                        raise ValidationError(
                            "Les informations d'un paiement "
                            "validé sont immuables."
                        )

        self.full_clean()

        return super().save(*args, **kwargs)

