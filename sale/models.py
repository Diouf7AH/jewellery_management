# sale/models.py
from __future__ import annotations

import random
import uuid
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import IntegrityError, models, transaction
from django.db.models import CheckConstraint, F, Q, Sum
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify

from sale.services.montant_service import (ZERO, calculer_montants,
                                           calculer_solde_paiement,
                                           decimal_value, money, money_strict)

from .counters import InvoiceCounter  # OK (dans la même app)

TWOPLACES = Decimal("0.01")
ZERO = Decimal("0.00")



class Client(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="client",
    )

    prenom = models.CharField(
        max_length=100,
    )

    nom = models.CharField(
        max_length=100,
    )

    telephone = models.CharField(
        max_length=15,
        unique=True,
        blank=True,
        null=True,
        db_index=True,
    )

    cni = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Numéro CNI",
    )

    address = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Adresse",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

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
        return (
            self.full_name
            or self.telephone
            or f"Client #{self.pk}"
        )
        

class Vente(models.Model):
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
    )

    SOURCE_MAGASIN = "magasin"
    SOURCE_ECOMMERCE = "ecommerce"
    SOURCE_WHATSAPP = "whatsapp"
    SOURCE_FACEBOOK = "facebook"

    SOURCE_CHOICES = [
        (SOURCE_MAGASIN, "Magasin"),
        (SOURCE_ECOMMERCE, "E-commerce"),
        (SOURCE_WHATSAPP, "WhatsApp"),
        (SOURCE_FACEBOOK, "Facebook"),
    ]

    source_vente = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_MAGASIN,
        db_index=True,
    )

    numero_vente = models.CharField(
        max_length=30,
        unique=True,
        editable=False,
        blank=True,
        null=True,
    )

    client = models.ForeignKey(
        "sale.Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ventes",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ventes_creees",
    )

    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        related_name="ventes",
        db_index=True,
    )

    vendor = models.ForeignKey(
        "vendor.Vendor",
        on_delete=models.PROTECT,
        related_name="ventes",
        db_index=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    # Total de la vente avant TVA facture.
    montant_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    delivered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ventes_livrees",
    )

    is_cancelled = models.BooleanField(
        default=False,
        db_index=True,
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
        related_name="ventes_annulees",
    )
    
    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["created_at"],
            ),
            models.Index(
                fields=["numero_vente"],
            ),
            models.Index(
                fields=["vendor", "created_at"],
            ),
            models.Index(
                fields=["bijouterie", "created_at"],
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=Q(montant_total__gte=0),
                name="vente_montant_total_gte_0",
            ),
        ]

    def __str__(self):
        nom_client = (
            getattr(self.client, "full_name", None)
            or "Inconnu"
        )

        date_txt = (
            self.created_at.strftime("%d/%m/%Y")
            if self.created_at
            else ""
        )

        return (
            f"Vente #{self.numero_vente or 'N/A'} "
            f"- Client: {nom_client} "
            f"- {date_txt}"
        )

    def clean(self):
        super().clean()

        if not self.vendor_id or not self.bijouterie_id:
            return

        vendor_bijouterie_id = (
            self.vendor.bijouterie_id
        )

        if vendor_bijouterie_id != self.bijouterie_id:
            raise ValidationError({
                "vendor": (
                    "Le vendeur sélectionné n'appartient pas "
                    "à la bijouterie de cette vente."
                )
            })

    def generer_numero_vente(self) -> str:
        now = timezone.now()

        suffixe = "".join(
            random.choices(
                "0123456789",
                k=4,
            )
        )

        return (
            f"VENTE-"
            f"{now.strftime('%m%d%Y%H%M%S')}-"
            f"{suffixe}"
        ).upper()

    def save(self, *args, **kwargs):
        if not self.numero_vente:
            for _ in range(10):
                self.numero_vente = (
                    self.generer_numero_vente()
                )

                try:
                    with transaction.atomic():
                        super().save(
                            *args,
                            **kwargs,
                        )
                    break

                except IntegrityError:
                    self.numero_vente = None

            else:
                raise ValueError(
                    "Impossible de générer un numéro "
                    "de vente unique après 10 tentatives."
                )

            return

        return super().save(
            *args,
            **kwargs,
        )

    def marquer_livree(self, by_user):
        self.delivered_at = timezone.now()

        if by_user and not self.delivered_by_id:
            self.delivered_by = by_user

        self.save(
            update_fields=[
                "delivered_at",
                "delivered_by",
            ]
        )

    def mettre_a_jour_montant_total(
        self,
        commit: bool = True,
    ) -> Decimal:

        total_produits = (
            self.lignes.aggregate(
                total=Sum("montant_total")
            )["total"]
            or ZERO
        )

        total_autres = (
            self.autres.aggregate(
                total=Sum("montant_total")
            )["total"]
            or ZERO
        )

        total = (
            total_produits + total_autres
        ).quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )

        self.montant_total = total

        if commit:
            self.save(
                update_fields=["montant_total"]
            )

        return total


POURCENTAGES_OCCASION = {
    Decimal("5.00"),
    Decimal("10.00"),
    Decimal("15.00"),
    Decimal("20.00"),
    Decimal("25.00"),
    Decimal("30.00"),
}


class VenteProduit(models.Model):
    """
    Ligne de vente d'un bijou.

    - Snapshots de ProduitLine à la création.
    - Bijou neuf : remise fixe en FCFA.
    - Bijou occasion : réduction en pourcentage.
    - TVA calculée au niveau de Facture.
    - Aucun SALE_OUT à la création.
    - Modifications financières interdites après paiement.
    """

    # ========================================================
    # 1. RELATIONS
    # ========================================================

    vente = models.ForeignKey(
        "sale.Vente",
        on_delete=models.CASCADE,
        related_name="lignes",
    )

    produit_line = models.ForeignKey(
        "purchase.ProduitLine",
        on_delete=models.PROTECT,
        related_name="vente_lignes",
    )

    vendor = models.ForeignKey(
        "vendor.Vendor",
        on_delete=models.PROTECT,
        related_name="vente_produits",
        null=True,
        blank=True,
        db_index=True,
    )

    # ========================================================
    # 2. QUANTITÉ
    # ========================================================

    quantite = models.PositiveIntegerField(
        default=1,
    )

    # ========================================================
    # 3. SNAPSHOTS HISTORIQUES
    # ========================================================

    etat_vente = models.CharField(
        max_length=1,
        choices=(
            ("N", "Neuf"),
            ("O", "Occasion"),
        ),
        default="N",
        editable=False,
    )

    poids_unitaire_vente = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=ZERO,
        editable=False,
    )

    pourcentage_occasion = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=ZERO,
        editable=False,
    )

    # ========================================================
    # 4. PRIX ET REMISE
    # ========================================================

    prix_vente_grammes = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=ZERO,
    )

    remise = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=ZERO,
        null=True,
        blank=True,
    )

    # ========================================================
    # 5. MONTANTS
    # ========================================================

    montant_brut_ht = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=ZERO,
        editable=False,
    )

    montant_reduction = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=ZERO,
        editable=False,
    )

    montant_ht = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=ZERO,
        editable=False,
    )

    montant_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=ZERO,
        editable=False,
    )

    # ========================================================
    # 6. META
    # ========================================================

    class Meta:
        ordering = ["id"]

        indexes = [
            models.Index(
                fields=["etat_vente"],
                name="idx_vp_etat_vente",
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=Q(quantite__gte=1),
                name="ck_venteproduit_qty_gte_1",
            ),
            models.CheckConstraint(
                condition=Q(prix_vente_grammes__gt=0),
                name="ck_venteproduit_prix_gt_0",
            ),
            models.CheckConstraint(
                condition=Q(poids_unitaire_vente__gt=0),
                name="ck_vp_poids_vente_gt_0",
            ),
            models.CheckConstraint(
                condition=Q(montant_brut_ht__gte=0),
                name="ck_vp_montant_brut_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(montant_ht__gte=0),
                name="ck_venteproduit_montant_ht_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(montant_reduction__gte=0),
                name="ck_vp_reduction_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(
                    montant_reduction__lte=F("montant_brut_ht")
                ),
                name="ck_vp_reduction_lte_brut",
            ),
            models.CheckConstraint(
                condition=Q(montant_total__gte=0),
                name="ck_venteproduit_montant_total_gte_0",
            ),
            models.CheckConstraint(
                condition=(
                    Q(remise__isnull=True)
                    | Q(remise__gte=0)
                ),
                name="ck_venteproduit_remise_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(
                    pourcentage_occasion__in=[
                        ZERO,
                        *sorted(POURCENTAGES_OCCASION),
                    ]
                ),
                name="ck_venteproduit_occasion_values",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        etat_vente="N",
                        pourcentage_occasion=ZERO,
                    )
                    | (
                        Q(etat_vente="O")
                        & (
                            Q(remise__isnull=True)
                            | Q(remise=ZERO)
                        )
                        & Q(
                            pourcentage_occasion__in=sorted(
                                POURCENTAGES_OCCASION
                            )
                        )
                    )
                ),
                name="ck_vp_reduction_selon_etat",
            ),
        ]

    # ========================================================
    # 7. ACCÈS AU PRODUIT
    # ========================================================

    @property
    def produit(self):
        if not self.produit_line_id:
            return None

        return self.produit_line.produit

    # ========================================================
    # 8. REPRÉSENTATION
    # ========================================================

    def __str__(self):
        produit = self.produit

        nom = (
            getattr(produit, "nom", None)
            or f"ProduitLine #{self.produit_line_id}"
        )

        return (
            f"{nom} - "
            f"{self.get_etat_vente_display()} - "
            f"Qté {self.quantite} - "
            f"{self.montant_total} FCFA"
        )

    # ========================================================
    # 9. PROTECTION DES MODIFICATIONS
    # ========================================================

    def _verifier_modification_autorisee(self):
        """
        Interdit la modification d'une ligne existante
        après le premier paiement de sa vente.

        Protège également les lignes d'une vente dont
        le stock a déjà été consommé.
        """

        if not self.pk:
            return

        original = (
            type(self).objects
            .filter(pk=self.pk)
            .values(
                "vente_id",
                "produit_line_id",
                "vendor_id",
                "etat_vente",
                "poids_unitaire_vente",
                "pourcentage_occasion",
                "quantite",
                "prix_vente_grammes",
                "remise",
            )
            .first()
        )

        if original is None:
            return

        # Les snapshots et les relations sont immuables.
        champs_immutables = {
            "vente_id": self.vente_id,
            "produit_line_id": self.produit_line_id,
            "etat_vente": self.etat_vente,
            "poids_unitaire_vente": self.poids_unitaire_vente,
            "pourcentage_occasion": self.pourcentage_occasion,
        }

        for champ, valeur in champs_immutables.items():
            if valeur != original[champ]:
                raise ValidationError({
                    champ: (
                        "Ce champ historique ne peut pas "
                        "être modifié après création."
                    )
                })

        champs_financiers = {
            "quantite": self.quantite,
            "prix_vente_grammes": self.prix_vente_grammes,
            "remise": self.remise,
        }

        modification_financiere = any(
            valeur != original[champ]
            for champ, valeur in champs_financiers.items()
        )

        modification_vendor = (
            self.vendor_id != original["vendor_id"]
        )

        if not modification_financiere and not modification_vendor:
            return

        # Paiements liés à la vente, avec ou sans facture.
        paiement_existant = Paiement.objects.filter(
            vente_id=original["vente_id"],
            lignes__isnull=False,
        ).exists()

        if paiement_existant:
            raise ValidationError({
                "vente": (
                    "Modification interdite : cette vente "
                    "possède déjà un paiement."
                )
            })

        stock_consomme = Facture.objects.filter(
            vente_id=original["vente_id"],
            stock_consumed=True,
        ).exists()

        if stock_consomme:
            raise ValidationError({
                "vente": (
                    "Modification interdite : le stock "
                    "de cette vente a déjà été consommé."
                )
            })

    # ========================================================
    # 10. VALIDATION MÉTIER
    # ========================================================

    def clean(self):
        super().clean()

        errors = {}

        if not self.produit_line_id:
            errors["produit_line"] = (
                "La ligne d'achat du produit est obligatoire."
            )

        if not self.vente_id:
            errors["vente"] = (
                "La vente est obligatoire."
            )

        if self.quantite is None or self.quantite < 1:
            errors["quantite"] = (
                "La quantité doit être supérieure ou égale à 1."
            )

        def lire_decimal(value, field, default=None):
            try:
                return decimal_value(
                    default if value is None else value,
                    field=field,
                )
            except ValidationError:
                errors[field] = "Valeur décimale invalide."
                return ZERO

        prix = lire_decimal(
            self.prix_vente_grammes,
            "prix_vente_grammes",
        )

        poids = lire_decimal(
            self.poids_unitaire_vente,
            "poids_unitaire_vente",
        )

        remise = lire_decimal(
            self.remise,
            "remise",
            default=ZERO,
        )

        pourcentage = lire_decimal(
            self.pourcentage_occasion,
            "pourcentage_occasion",
        )

        if prix <= ZERO:
            errors["prix_vente_grammes"] = (
                "Le prix de vente au gramme doit être "
                "strictement supérieur à zéro."
            )

        if poids <= ZERO:
            errors["poids_unitaire_vente"] = (
                "Le poids unitaire de vente doit être "
                "strictement supérieur à zéro."
            )

        if remise < ZERO:
            errors["remise"] = (
                "La remise ne peut pas être négative."
            )

        if self.etat_vente == "N":
            if pourcentage != ZERO:
                errors["pourcentage_occasion"] = (
                    "Un bijou neuf ne peut pas avoir "
                    "de pourcentage occasion."
                )

        elif self.etat_vente == "O":
            if pourcentage not in POURCENTAGES_OCCASION:
                errors["pourcentage_occasion"] = (
                    "Le pourcentage d'occasion doit être "
                    "5, 10, 15, 20, 25 ou 30 %."
                )

            if remise != ZERO:
                errors["remise"] = (
                    "La remise fixe est interdite "
                    "pour un bijou d'occasion."
                )

        else:
            errors["etat_vente"] = (
                "État historique du bijou invalide."
            )

        # Cohérence vendeur / vente.
        if self.vente_id:
            vente = self.vente

            if not self.vendor_id:
                self.vendor = vente.vendor

            if self.vendor_id != vente.vendor_id:
                errors["vendor"] = (
                    "Le vendeur doit être identique "
                    "à celui de la vente."
                )

            elif (
                self.vendor is not None
                and self.vendor.bijouterie_id
                != vente.bijouterie_id
            ):
                errors["vendor"] = (
                    "Le vendeur n'appartient pas "
                    "à la bijouterie de cette vente."
                )

        if self.pk:
            self._verifier_modification_autorisee()

        if errors:
            raise ValidationError(errors)

    # ========================================================
    # 11. SAUVEGARDE ET CALCUL DES MONTANTS
    # ========================================================

    def save(self, *args, **kwargs):
        is_new = self._state.adding

        if not self.produit_line_id:
            raise ValidationError({
                "produit_line": (
                    "La ligne d'achat du produit est obligatoire."
                )
            })

        # ----------------------------------------------------
        # 1. SNAPSHOTS À LA CRÉATION
        # ----------------------------------------------------

        if is_new:
            ligne = self.produit_line

            self.etat_vente = ligne.etat

            poids_achat = ligne.poids_unitaire_achat

            if poids_achat is None:
                raise ValidationError({
                    "poids_unitaire_vente": (
                        "Le poids unitaire d'achat "
                        "est obligatoire."
                    )
                })

            self.poids_unitaire_vente = decimal_value(
                poids_achat,
                field="poids_unitaire_vente",
            )

            if self.etat_vente == "O":
                if ligne.pourcentage_occasion is None:
                    raise ValidationError({
                        "pourcentage_occasion": (
                            "Le pourcentage occasion "
                            "doit être défini à l'achat."
                        )
                    })

                self.pourcentage_occasion = decimal_value(
                    ligne.pourcentage_occasion,
                    field="pourcentage_occasion",
                )

            elif self.etat_vente == "N":
                self.pourcentage_occasion = ZERO

            else:
                raise ValidationError({
                    "etat_vente": (
                        "État du bijou invalide."
                    )
                })

        # ----------------------------------------------------
        # 2. VALIDATION MÉTIER
        # ----------------------------------------------------

        self.clean()

        # ----------------------------------------------------
        # 3. MONTANT BRUT
        # ----------------------------------------------------

        prix = decimal_value(
            self.prix_vente_grammes,
            field="prix_vente_grammes",
        )

        poids = decimal_value(
            self.poids_unitaire_vente,
            field="poids_unitaire_vente",
        )

        montant_brut = money(
            prix * poids * self.quantite,
            field="montant_brut_ht",
        )

        # ----------------------------------------------------
        # 4. RÉDUCTION
        # ----------------------------------------------------

        if self.etat_vente == "O":
            pourcentage = decimal_value(
                self.pourcentage_occasion,
                field="pourcentage_occasion",
            )

            reduction = money(
                montant_brut
                * pourcentage
                / Decimal("100"),
                field="montant_reduction",
            )

        else:
            reduction = money(
                self.remise if self.remise is not None else ZERO,
                field="remise",
            )

        if reduction > montant_brut:
            raise ValidationError({
                "remise": (
                    "La réduction ne peut pas dépasser "
                    "le montant brut du bijou."
                )
            })

        # ----------------------------------------------------
        # 5. CALCUL CENTRALISÉ
        # ----------------------------------------------------

        montants = calculer_montants(
            montant_brut_ht=montant_brut,
            montant_reduction=reduction,
            taux_tva=ZERO,
        )

        self.montant_brut_ht = montants["montant_brut_ht"]
        self.montant_reduction = montants["montant_reduction"]
        self.montant_ht = montants["montant_ht"]
        self.montant_total = montants["montant_total"]

        # ----------------------------------------------------
        # 6. VALIDATION COMPLÈTE
        # ----------------------------------------------------

        self.full_clean()

        # ----------------------------------------------------
        # 7. update_fields
        # ----------------------------------------------------

        if kwargs.get("update_fields") is not None:
            update_fields = set(kwargs["update_fields"])

            update_fields.update({
                "vendor",
                "montant_brut_ht",
                "montant_reduction",
                "montant_ht",
                "montant_total",
            })

            kwargs["update_fields"] = update_fields

        # ----------------------------------------------------
        # 8. SAUVEGARDE
        # ----------------------------------------------------

        result = super().save(*args, **kwargs)

        # ----------------------------------------------------
        # 9. RECALCUL DE LA VENTE
        # ----------------------------------------------------

        if self.vente_id:
            self.vente.mettre_a_jour_montant_total()

        return result


    
class VenteAutre(models.Model):
    """
    Ligne complémentaire d'une vente :
    - poudre or / argent
    - nettoyage
    - décoration
    - boîte cadeau
    - autre
    """

    TYPE_REPARATION = "REPARATION"
    TYPE_POUDRE_OR_ARGENT = "POUDRE_OR_ARGENT"
    TYPE_NETTOYAGE = "NETTOYAGE"
    TYPE_DECORATION = "DECORATION"
    TYPE_BOITE_CADEAU = "BOITE_CADEAU"
    TYPE_AUTRE = "AUTRE"

    TYPE_CHOICES = [
        (
            TYPE_REPARATION,
            "Réparation",
        ),
        (
            TYPE_POUDRE_OR_ARGENT,
            "Poudre or / argent",
        ),
        (
            TYPE_NETTOYAGE,
            "Nettoyage",
        ),
        (
            TYPE_DECORATION,
            "Décoration",
        ),
        (
            TYPE_BOITE_CADEAU,
            "Boîte cadeau",
        ),
        (
            TYPE_AUTRE,
            "Autre",
        ),
    ]

    vente = models.ForeignKey(
        "sale.Vente",
        on_delete=models.CASCADE,
        related_name="autres",
    )

    type_autre = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
        db_index=True,
    )

    quantite = models.PositiveIntegerField(
        default=1,
    )

    prix_unitaire = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=ZERO,
    )

    montant_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=ZERO,
        editable=False,
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return (
            f"{self.get_type_autre_display()} - "
            f"{self.quantite} x {self.prix_unitaire}"
        )

    def save(self, *args, **kwargs):
        quantite = int(self.quantite or 0)
        prix_unitaire = Decimal(str(self.prix_unitaire or ZERO))

        self.montant_total = (
            prix_unitaire * quantite
        ).quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )

        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = (
                set(kwargs["update_fields"]) | {"montant_total"}
            )

        result = super().save(*args, **kwargs)

        if self.vente_id:
            self.vente.mettre_a_jour_montant_total()

        return result
        

class Facture(models.Model):
    """
    Facture liée à une vente contenant au moins un bijou.

    Types de ventes facturables :
    - bijoux uniquement ;
    - bijoux + prestations.

    Prestations uniquement :
    - pas de proforma ;
    - pas de facture ;
    - paiement direct avec reçu.

    Le montant HT est figé lors de la création.
    """

    # =========================================================
    # TYPES
    # =========================================================

    TYPE_PROFORMA = "proforma"
    TYPE_FACTURE = "facture"
    TYPE_ACOMPTE = "acompte"
    TYPE_FINALE = "finale"

    TYPES_FACTURE = (
        (TYPE_PROFORMA, "Proforma"),
        (TYPE_FACTURE, "Facture"),
        (TYPE_ACOMPTE, "Facture d'acompte"),
        (TYPE_FINALE, "Facture finale"),
    )

    # =========================================================
    # STATUTS
    # =========================================================

    STAT_NON_PAYE = "non_paye"
    STAT_PARTIEL = "partiel"
    STAT_PAYE = "paye"

    STATUS = (
        (STAT_NON_PAYE, "Non payé"),
        (STAT_PARTIEL, "Partiellement payé"),
        (STAT_PAYE, "Payé"),
    )

    # =========================================================
    # IDENTIFICATION
    # =========================================================

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
    )

    numero_facture = models.CharField(
        max_length=32,
        editable=False,
        blank=True,
    )

    # =========================================================
    # VENTE / BIJOUTERIE
    # =========================================================

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

    date_creation = models.DateTimeField(
        auto_now_add=True,
    )

    # =========================================================
    # MONTANTS
    # =========================================================

    montant_ht = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=ZERO,
    )

    appliquer_tva = models.BooleanField(
        default=False,
    )

    taux_tva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
    )

    montant_tva = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
    )

    frais_transaction = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=ZERO,
    )

    montant_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=ZERO,
    )

    # =========================================================
    # STATUT / TYPE
    # =========================================================

    status = models.CharField(
        max_length=20,
        choices=STATUS,
        default=STAT_NON_PAYE,
        db_index=True,
    )

    type_facture = models.CharField(
        max_length=20,
        choices=TYPES_FACTURE,
        default=TYPE_PROFORMA,
        db_index=True,
    )

    # =========================================================
    # PDF / INTÉGRITÉ / QR
    # =========================================================

    facture_pdf = models.FileField(
        upload_to="factures/",
        null=True,
        blank=True,
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

    signed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    # =========================================================
    # VERROUILLAGE
    # =========================================================

    is_locked = models.BooleanField(
        default=False,
        db_index=True,
    )

    locked_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    # =========================================================
    # COMMANDE CLIENT
    # =========================================================

    commande_client = models.ForeignKey(
        "order.CommandeClient",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="factures",
    )

    # =========================================================
    # CONSOMMATION STOCK
    # =========================================================

    stock_consumed = models.BooleanField(
        default=False,
        db_index=True,
    )

    # =========================================================
    # META
    # =========================================================

    class Meta:
        ordering = ["-id"]

        indexes = [
            models.Index(
                fields=["numero_facture"],
            ),
            models.Index(
                fields=["date_creation"],
            ),
            models.Index(
                fields=["status"],
            ),
            models.Index(
                fields=["type_facture"],
            ),
            models.Index(
                fields=["bijouterie", "date_creation"],
            ),
            models.Index(
                fields=["commande_client"],
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=Q(montant_ht__gte=0),
                name="facture_montant_ht_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(frais_transaction__gte=0),
                name="facture_frais_transaction_gte_0",
            ),
            models.CheckConstraint(
                condition=(
                    Q(taux_tva__isnull=True)
                    | (
                        Q(taux_tva__gte=0)
                        & Q(taux_tva__lte=100)
                    )
                ),
                name="facture_taux_tva_range",
            ),
            models.CheckConstraint(
                condition=(
                    Q(montant_tva__isnull=True)
                    | Q(montant_tva__gte=0)
                ),
                name="facture_montant_tva_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(montant_total__gte=0),
                name="facture_montant_total_gte_0",
            ),
            models.UniqueConstraint(
                fields=["bijouterie", "numero_facture"],
                name="uniq_invoice_per_shop",
            ),
        ]

    # =========================================================
    # STRING
    # =========================================================

    def __str__(self):
        return (
            self.numero_facture
            or f"Facture #{self.pk or 'N/A'}"
        )

    # =========================================================
    # VALIDATION
    # =========================================================

    def clean(self):
        super().clean()

        if (
            self.vente_id
            and self.bijouterie_id
            and self.vente.bijouterie_id != self.bijouterie_id
        ):
            raise ValidationError({
                "bijouterie": (
                    "La bijouterie de la facture doit être "
                    "identique à celle de la vente."
                )
            })

        if self.appliquer_tva and self.taux_tva is None:
            raise ValidationError({
                "taux_tva": (
                    "Le taux de TVA est obligatoire "
                    "lorsque la TVA est appliquée."
                )
            })

        if self.taux_tva is not None:
            if not (
                Decimal("0.00")
                <= self.taux_tva
                <= Decimal("100.00")
            ):
                raise ValidationError({
                    "taux_tva": (
                        "Le taux de TVA doit être compris "
                        "entre 0 et 100."
                    )
                })

        # Les ventes de prestations seules ne sont pas
        # facturables dans ce circuit.
        #
        # La présence d'une vente est facultative pour
        # préserver les factures indépendantes existantes.

        if self.vente_id:
            VenteProduit = apps.get_model(
                "sale",
                "VenteProduit",
            )

            contient_bijoux = (
                VenteProduit.objects
                .filter(vente_id=self.vente_id)
                .exists()
            )

            if not contient_bijoux:
                raise ValidationError({
                    "vente": (
                        "Une vente contenant uniquement "
                        "des prestations ne nécessite "
                        "pas de facture. Utilisez le "
                        "paiement direct avec reçu."
                    )
                })

    # =========================================================
    # NUMÉROTATION
    # =========================================================

    @staticmethod
    def generer_numero_unique(bijouterie) -> str:
        if not bijouterie:
            raise ValueError(
                "La bijouterie est obligatoire "
                "pour générer le numéro de facture."
            )

        seq = InvoiceCounter.next_for_today(
            bijouterie
        )

        day = timezone.localdate().strftime(
            "%Y%m%d"
        )

        return f"FAC-{day}-{seq:04d}"

    # =========================================================
    # CALCUL HT DE LA VENTE
    # =========================================================

    def calculer_montant_ht_vente(self) -> Decimal:
        """
        Calcule le montant HT des bijoux et prestations.

        Utilisation uniquement lors de la préparation
        d'une nouvelle facture.

        Ne modifie pas le montant HT déjà figé.
        """

        if not self.vente_id:
            return ZERO

        total_produits = (
            self.vente.lignes.aggregate(
                total=Sum("montant_total")
            )["total"]
            or ZERO
        )

        total_autres = (
            self.vente.autres.aggregate(
                total=Sum("montant_total")
            )["total"]
            or ZERO
        )

        return (
            Decimal(str(total_produits))
            + Decimal(str(total_autres))
        ).quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )

    # =========================================================
    # CALCUL DES TOTAUX
    # =========================================================

    def recalculer_totaux(self):
        """
        Calcule les montants d'une nouvelle facture
        à partir du taux de TVA déjà sélectionné.

        Ne récupère jamais automatiquement le taux
        actuel de la bijouterie.
        """

        ht = Decimal(str(self.montant_ht or ZERO))
        frais = Decimal(str(self.frais_transaction or ZERO))

        if self.appliquer_tva:
            if self.taux_tva is None:
                raise ValidationError({
                    "taux_tva": (
                        "Le taux de TVA est obligatoire "
                        "lorsque la TVA est appliquée."
                    )
                })

            taux = Decimal(str(self.taux_tva))
        else:
            taux = ZERO

        if not ZERO <= taux <= Decimal("100.00"):
            raise ValidationError({
                "taux_tva": (
                    "Le taux de TVA doit être compris "
                    "entre 0 et 100."
                )
            })

        self.taux_tva = taux.quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )

        self.montant_tva = (
            ht * self.taux_tva / Decimal("100")
        ).quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )

        self.montant_total = (
            ht + self.montant_tva + frais
        ).quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )


    # =========================================================
    # STATUT DE PAIEMENT
    # =========================================================

    # =========================================================
    # SAVE
    # =========================================================

    def save(self, *args, **kwargs):
        """
        Sauvegarde sécurisée :
        - Numérotation automatique.
        - Calcul de la TVA uniquement à la création.
        - Conservation des montants historiques.
        - Protection des factures verrouillées.
        """

        update_fields = kwargs.get("update_fields")

        if update_fields is not None:
            update_fields = set(update_fields)

        champs_figes = {
            "bijouterie_id",
            "vente_id",
            "montant_ht",
            "appliquer_tva",
            "taux_tva",
            "montant_tva",
            "frais_transaction",
            "montant_total",
            "numero_facture",
        }

        if not self._state.adding:
            old = Facture.objects.get(pk=self.pk)

            # Interdire la modification des valeurs historiques.
            for champ in champs_figes:
                if getattr(self, champ) != getattr(old, champ):
                    raise ValidationError({
                        champ: (
                            "Ce champ ne peut plus être modifié "
                            "après la création de la facture."
                        )
                    })

            if old.is_locked:
                transition_finale = (
                    update_fields == {"type_facture"}
                    and old.type_facture == self.TYPE_PROFORMA
                    and self.type_facture == self.TYPE_FACTURE
                    and old.status == self.STAT_PAYE
                    and old.stock_consumed
                    and old.reste_a_payer == ZERO
                )

                if not transition_finale:
                    raise ValidationError(
                        "Facture verrouillée."
                    )

        else:
            if not self.bijouterie_id:
                raise ValidationError({
                    "bijouterie": (
                        "La bijouterie est obligatoire."
                    )
                })

            if not self.numero_facture:
                self.numero_facture = (
                    self.generer_numero_unique(
                        self.bijouterie
                    )
                )

            self.recalculer_totaux()

        self.full_clean()

        if update_fields is not None:
            kwargs["update_fields"] = update_fields

        return super().save(*args, **kwargs)


    # =========================================================
    # TOTAL PAYÉ
    # =========================================================

    @property
    def total_paye(self):
        """
        Somme des paiements réellement enregistrés.
        """
        if not self.pk:
            return ZERO

        PaiementLigne = apps.get_model(
            "sale",
            "PaiementLigne",
        )

        total = (
            PaiementLigne.objects
            .filter(paiement__facture_id=self.pk)
            .aggregate(total=Sum("montant_paye"))
            ["total"]
        )

        return money_strict(
            total if total is not None else ZERO,
            "total_paye",
        )

    @property
    def reste_a_payer(self):
        """
        Calcule le solde sans masquer un trop-perçu.
        """
        solde = calculer_solde_paiement(
            montant_total=self.montant_total,
            montant_deja_paye=self.total_paye,
        )

        return solde["reste_a_payer"]

    @staticmethod
    def recompute_facture_status(facture):
        """
        Recalcule le statut à partir des paiements.

        Cette opération ne modifie pas les montants
        et fonctionne même pour une facture verrouillée.
        """
        if not facture.pk:
            raise ValidationError({
                "facture": "La facture doit être enregistrée."
            })

        total_paye = facture.total_paye
        reste = facture.reste_a_payer

        if reste == ZERO:
            nouveau_statut = Facture.STAT_PAYE

        elif total_paye == ZERO:
            nouveau_statut = Facture.STAT_NON_PAYE

        else:
            nouveau_statut = Facture.STAT_PARTIEL

        if facture.status != nouveau_statut:
            Facture.objects.filter(
                pk=facture.pk
            ).update(
                status=nouveau_statut
            )

            facture.status = nouveau_statut

        return nouveau_statut

    def est_reglee(self):
        """
        Vérifie le paiement effectif, sans dépendre
        uniquement du statut enregistré.
        """
        return (
            self.pk is not None
            and self.reste_a_payer == ZERO
            and self.total_paye > ZERO
        )



class Paiement(models.Model):
    """
    Opération d'encaissement.

    BIJOUX UNIQUEMENT :
        Vente -> Facture -> Paiement -> PaiementLigne

    PRESTATIONS UNIQUEMENT :
        Vente -> Paiement -> PaiementLigne
        Aucune Facture.

    VENTE MIXTE :
        Vente -> Facture -> Paiement -> PaiementLigne

    Aucun mouvement SALE_OUT dans ce modèle.
    """

    vente = models.ForeignKey(
        "sale.Vente",
        on_delete=models.PROTECT,
        related_name="paiements",
        null=True,
        blank=True,
    )

    facture = models.ForeignKey(
        "sale.Facture",
        on_delete=models.PROTECT,
        related_name="paiements",
        null=True,
        blank=True,
    )
    
    idempotency_key = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
        editable=False,
        db_index=True,
    )

    request_fingerprint = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        editable=False,
    )
    
    response_snapshot = models.JSONField(
        null=True,
        blank=True,
        editable=False,
    )

    date_paiement = models.DateTimeField(
        auto_now_add=True,
    )

    cashier = models.ForeignKey(
        "staff.Cashier",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="paiements",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="paiements_validation",
    )

    class Meta:
        ordering = ["-date_paiement"]

        indexes = [
            models.Index(
                fields=["vente", "date_paiement"],
            ),
            models.Index(
                fields=["facture", "date_paiement"],
            ),
            models.Index(
                fields=["cashier", "date_paiement"],
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(vente__isnull=False)
                    | models.Q(facture__isnull=False)
                ),
                name="paiement_vente_ou_facture_required",
            ),
        ]

    def __str__(self):
        if self.facture_id:
            return (
                "Paiement - "
                f"{self.facture.numero_facture}"
            )

        if self.vente_id:
            return (
                "Paiement direct - "
                f"{self.vente.numero_vente}"
            )

        return f"Paiement #{self.pk or 'nouveau'}"

    # =========================================================
    # TYPE DE PAIEMENT
    # =========================================================

    @property
    def est_paiement_direct(self):
        return (
            self.vente_id is not None
            and self.facture_id is None
        )

    @property
    def est_paiement_facture(self):
        return self.facture_id is not None

    # =========================================================
    # VALIDATION
    # =========================================================

    def clean(self):
        super().clean()

        # -----------------------------------------------------
        # 1. Vente ou facture obligatoire
        # -----------------------------------------------------

        if not self.vente_id and not self.facture_id:
            raise ValidationError({
                "vente": (
                    "Une vente ou une facture "
                    "doit être renseignée."
                )
            })

        # -----------------------------------------------------
        # 2. Cohérence facture / vente
        # -----------------------------------------------------

        if self.facture_id:

            facture_vente_id = self.facture.vente_id

            if not facture_vente_id:
                raise ValidationError({
                    "facture": (
                        "Cette facture n'est associée "
                        "à aucune vente."
                    )
                })

            if (
                self.vente_id
                and self.vente_id != facture_vente_id
            ):
                raise ValidationError({
                    "vente": (
                        "La vente du paiement doit "
                        "correspondre à celle de la facture."
                    )
                })

            # Une facture doit être utilisée pour
            # les ventes contenant des bijoux.
            if not self.vente_id:
                self.vente_id = facture_vente_id

        # -----------------------------------------------------
        # 3. Paiement direct : prestations uniquement
        # -----------------------------------------------------

        if self.vente_id and not self.facture_id:

            VenteProduit = apps.get_model(
                "sale",
                "VenteProduit",
            )

            contient_bijoux = (
                VenteProduit.objects
                .filter(vente_id=self.vente_id)
                .exists()
            )

            if contient_bijoux:
                raise ValidationError({
                    "facture": (
                        "Une vente contenant des bijoux "
                        "doit être réglée via sa facture."
                    )
                })

            VenteAutre = apps.get_model(
                "sale",
                "VenteAutre",
            )

            contient_prestations = (
                VenteAutre.objects
                .filter(vente_id=self.vente_id)
                .exists()
            )

            if not contient_prestations:
                raise ValidationError({
                    "vente": (
                        "Le paiement direct nécessite "
                        "une vente contenant des prestations."
                    )
                })

        # -----------------------------------------------------
        # 4. Cohérence cashier / created_by
        # -----------------------------------------------------

        if (
            self.cashier_id
            and self.created_by_id
            and self.cashier.user_id != self.created_by_id
        ):
            raise ValidationError({
                "cashier": (
                    "Le caissier doit correspondre "
                    "à l'utilisateur qui valide "
                    "le paiement."
                )
            })

        # -----------------------------------------------------
        # 5. Caissier actif
        # -----------------------------------------------------

        if self.cashier_id:

            if not self.cashier.is_active_staff:
                raise ValidationError({
                    "cashier": (
                        "Ce caissier est désactivé "
                        "et ne peut pas valider "
                        "de paiement."
                    )
                })

        # -----------------------------------------------------
        # 6. Cohérence bijouterie
        # -----------------------------------------------------

        if self.cashier_id:

            if self.facture_id:
                bijouterie_id = (
                    self.facture.bijouterie_id
                )
            else:
                bijouterie_id = (
                    self.vente.bijouterie_id
                )

            cashier_bijouterie_id = (
                self.cashier.bijouterie_id
            )

            if not cashier_bijouterie_id:
                raise ValidationError({
                    "cashier": (
                        "Le caissier n'est rattaché "
                        "à aucune bijouterie."
                    )
                })

            if cashier_bijouterie_id != bijouterie_id:
                raise ValidationError({
                    "cashier": (
                        "Le caissier n'appartient pas "
                        "à la bijouterie de cette vente."
                    )
                })

    # =========================================================
    # TOTAL DE CETTE OPÉRATION
    # =========================================================

    @property
    def montant_total_paye(self) -> Decimal:
        """
        Total des PaiementLigne associés à ce paiement.
        """

        if not self.pk:
            return ZERO

        total = (
            self.lignes
            .aggregate(
                total=Sum("montant_paye")
            )["total"]
        )

        return total or ZERO

    # =========================================================
    # SAVE
    # =========================================================

    def save(self, *args, **kwargs):
        """
        Résolution automatique du caissier.

        Aucun mouvement de stock.
        Aucune création de reçu ici.
        """

        # -----------------------------------------------------
        # 1. Résolution de la vente depuis la facture
        # -----------------------------------------------------

        if self.facture_id and not self.vente_id:
            self.vente_id = self.facture.vente_id

        # -----------------------------------------------------
        # 2. Résolution automatique du caissier
        # -----------------------------------------------------

        if (
            not self.cashier_id
            and self.created_by_id
        ):
            Cashier = apps.get_model(
                "staff",
                "Cashier",
            )

            self.cashier = (
                Cashier.objects
                .filter(
                    user_id=self.created_by_id
                )
                .first()
            )

        # -----------------------------------------------------
        # 3. Validation
        # -----------------------------------------------------

        self.full_clean()

        # -----------------------------------------------------
        # 4. Sauvegarde
        # -----------------------------------------------------

        update_fields = kwargs.get("update_fields")

        if update_fields is not None:
            kwargs["update_fields"] = set(
                update_fields
            ) | {
                "vente",
                "cashier",
            }

        super().save(*args, **kwargs)


def get_default_mode_paiement():
    """
    Retourne l'ID du mode Cash.

    Le mode Cash est créé s'il n'existe pas.
    """

    mode, _ = ModePaiement.objects.get_or_create(
        code="cash",
        defaults={
            "nom": "Cash",
            "active": True,
            "ordre_affichage": 1,
            "necessite_reference": False,
            "est_mode_depot": False,
        },
    )

    return mode.pk


class ModePaiement(models.Model):
    """
    Référentiel des modes de paiement.

    Utilisé pour :
    - les paiements de factures ;
    - les paiements directs des prestations ;
    - les paiements mixtes ;
    - les paiements par compte dépôt.
    """

    nom = models.CharField(
        max_length=100,
        unique=True,
    )

    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        validators=[
            RegexValidator(
                regex=r"^[a-z0-9]+(?:_[a-z0-9]+)*$",
                message=(
                    "Utilisez uniquement des lettres minuscules, "
                    "des chiffres et des underscores."
                ),
            )
        ],
    )

    active = models.BooleanField(
        default=True,
        db_index=True,
    )

    est_mode_depot = models.BooleanField(
        default=False,
    )

    necessite_reference = models.BooleanField(
        default=False,
    )

    ordre_affichage = models.PositiveIntegerField(
        default=0,
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    class Meta:
        ordering = [
            "ordre_affichage",
            "nom",
        ]

        indexes = [
            models.Index(
                fields=["active", "ordre_affichage"],
            ),
        ]

    def __str__(self):
        return f"{self.nom} ({self.code})"

    # =========================================================
    # NORMALISATION
    # =========================================================

    @staticmethod
    def normalize_code(value):
        """
        Conserve les codes API existants :

        cash
        wave
        orange_money
        tpe
        depot
        """

        return (
            slugify(str(value or "").strip())
            .replace("-", "_")
            .lower()
        )

    # =========================================================
    # VALIDATION
    # =========================================================

    def clean(self):
        super().clean()

        self.code = self.normalize_code(self.code)

        if not self.code:
            raise ValidationError({
                "code": (
                    "Le code du mode de paiement "
                    "est obligatoire."
                )
            })

        if self.est_mode_depot and self.code != "depot":
            raise ValidationError({
                "code": (
                    "Un mode de paiement par compte dépôt "
                    "doit avoir le code 'depot'."
                )
            })

        if self.code == "depot" and not self.est_mode_depot:
            raise ValidationError({
                "est_mode_depot": (
                    "Le mode 'depot' doit être identifié "
                    "comme un mode compte dépôt."
                )
            })

    # =========================================================
    # SAVE
    # =========================================================

    def save(self, *args, **kwargs):
        self.code = self.normalize_code(self.code)

        self.full_clean()

        return super().save(*args, **kwargs)
    



class PaiementLigne(models.Model):
    """
    Ligne d'une opération de paiement.

    Compatible avec :
    - Paiement associé à une Facture.
    - Paiement direct associé à une Vente.
    - Paiement multi-modes.

    Aucune consommation de stock.
    Aucune création de facture ou de reçu ici.
    """

    paiement = models.ForeignKey(
        "sale.Paiement",
        on_delete=models.CASCADE,
        related_name="lignes",
    )

    montant_paye = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    mode_paiement = models.ForeignKey(
        "sale.ModePaiement",
        on_delete=models.PROTECT,
        related_name="lignes_paiement",
    )

    reference = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=(
            "Référence transaction Wave / "
            "Orange Money / banque / TPE"
        ),
    )

    # =========================================================
    # COMPTE DÉPÔT
    # =========================================================

    compte_depot = models.ForeignKey(
        "compte_depot.CompteDepot",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lignes_paiement",
    )

    transaction_depot = models.ForeignKey(
        "compte_depot.CompteDepotTransaction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lignes_paiement",
    )

    # =========================================================
    # PAIEMENT EXTERNE
    # =========================================================

    provider_reference = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text=(
            "Référence retournée par Stripe, PayDunya, "
            "CinetPay, banque ou TPE"
        ),
    )

    checkout_url = models.URLField(
        blank=True,
        null=True,
        help_text=(
            "Lien de paiement en ligne si applicable"
        ),
    )

    payment_token = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Token de paiement externe",
    )

    callback_received = models.BooleanField(
        default=False,
        db_index=True,
        help_text=(
            "Indique si le callback ou la confirmation "
            "du fournisseur a été reçu."
        ),
    )

    # =========================================================
    # META
    # =========================================================

    class Meta:
        ordering = ["id"]

        constraints = [
            models.CheckConstraint(
                condition=Q(montant_paye__gt=0),
                name="paiement_ligne_montant_paye_gt_0",
            ),
            models.UniqueConstraint(
                fields=[
                    "paiement",
                    "mode_paiement",
                ],
                name="uniq_mode_par_paiement",
            ),
        ]

        indexes = [
            models.Index(
                fields=["paiement"],
            ),
            models.Index(
                fields=["mode_paiement"],
            ),
        ]

    # =========================================================
    # STRING
    # =========================================================

    def __str__(self):
        return (
            f"{self.mode_paiement} - "
            f"{self.montant_paye} FCFA"
        )

    # =========================================================
    # VALIDATION
    # =========================================================

    def clean(self):
        super().clean()

        # -----------------------------------------------------
        # 1. Montant
        # -----------------------------------------------------

        if self.montant_paye is None:
            raise ValidationError({
                "montant_paye": (
                    "Le montant payé est obligatoire."
                )
            })

        try:
            montant_paye = money_strict(self.montant_paye, "montant_paye")
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError({
                "montant_paye": "Montant payé invalide."
            })

        if not montant_paye.is_finite() or montant_paye <= ZERO:
            raise ValidationError({
                "montant_paye": (
                    "Le montant payé doit être "
                    "strictement positif."
                )
            })

        # -----------------------------------------------------
        # 2. Mode de paiement
        # -----------------------------------------------------

        if not self.mode_paiement_id:
            raise ValidationError({
                "mode_paiement": (
                    "Le mode de paiement est obligatoire."
                )
            })

        mode = self.mode_paiement

        if not mode.active:
            raise ValidationError({
                "mode_paiement": (
                    "Ce mode de paiement est inactif."
                )
            })

        # -----------------------------------------------------
        # 3. Référence
        # -----------------------------------------------------

        if self.reference:
            self.reference = self.reference.strip()

        if (
            mode.necessite_reference
            and not self.reference
        ):
            raise ValidationError({
                "reference": (
                    f"Une référence est obligatoire "
                    f"pour le mode '{mode.nom}'."
                )
            })

        # =====================================================
        # 4. MODE COMPTE DÉPÔT
        # =====================================================

        if mode.est_mode_depot:

            if not self.compte_depot_id:
                raise ValidationError({
                    "compte_depot": (
                        "Le compte dépôt est obligatoire "
                        "pour ce mode de paiement."
                    )
                })

            if not self.transaction_depot_id:
                raise ValidationError({
                    "transaction_depot": (
                        "La transaction dépôt est obligatoire "
                        "pour ce mode de paiement."
                    )
                })

            transaction = self.transaction_depot

            if transaction.compte_id != self.compte_depot_id:
                raise ValidationError({
                    "transaction_depot": (
                        "La transaction n'appartient pas "
                        "au compte dépôt sélectionné."
                    )
                })

            if (
                transaction.type_transaction
                != transaction.TYPE_RETRAIT
            ):
                raise ValidationError({
                    "transaction_depot": (
                        "La transaction utilisée pour payer "
                        "doit être un retrait du compte dépôt."
                    )
                })

            if (
                transaction.statut
                != transaction.STAT_TERMINE
            ):
                raise ValidationError({
                    "transaction_depot": (
                        "La transaction du compte dépôt "
                        "doit être terminée."
                    )
                })

            try:
                montant_transaction = Decimal(
                    str(transaction.montant)
                ).quantize(
                    TWOPLACES,
                    rounding=ROUND_HALF_UP,
                )
            except (InvalidOperation, TypeError, ValueError):
                raise ValidationError({
                    "transaction_depot": (
                        "Montant de transaction invalide."
                    )
                })

            if montant_transaction != montant_paye:
                raise ValidationError({
                    "montant_paye": (
                        "Le montant payé doit être identique "
                        "au montant retiré du compte dépôt."
                    )
                })

        # =====================================================
        # 5. AUTRES MODES
        # =====================================================

        else:

            if self.compte_depot_id:
                raise ValidationError({
                    "compte_depot": (
                        "Le compte dépôt est réservé "
                        "au mode de paiement dépôt."
                    )
                })

            if self.transaction_depot_id:
                raise ValidationError({
                    "transaction_depot": (
                        "La transaction dépôt est réservée "
                        "au mode de paiement dépôt."
                    )
                })

    # =========================================================
    # SAVE
    # =========================================================

    def save(self, *args, **kwargs):

        if self.montant_paye is not None:
            try:
                self.montant_paye = money_strict(self.montant_paye, "montant_paye")
            except (InvalidOperation, TypeError, ValueError):
                raise ValidationError({
                    "montant_paye": "Montant payé invalide."
                })

        for field in (
            "reference",
            "provider_reference",
            "payment_token",
        ):
            value = getattr(self, field)

            if value:
                setattr(self, field, value.strip())

        self.full_clean()

        return super().save(*args, **kwargs)
    

