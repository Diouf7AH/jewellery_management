# e_commerce/models.py

import uuid
from decimal import Decimal

from django.db import models

# ============================================================
# COMMANDE E-COMMERCE
# ============================================================

class CommandeEcommerce(models.Model):

    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_PAID, "Payée"),
        (STATUS_FAILED, "Échouée"),
        (STATUS_CANCELLED, "Annulée"),
    ]

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )

    # --------------------------------------------------------
    # Bijouterie dont le stock sera utilisé
    # --------------------------------------------------------

    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        related_name="commandes_ecommerce",
    )

    # --------------------------------------------------------
    # Client
    # --------------------------------------------------------

    client = models.ForeignKey(
        "sale.Client",
        on_delete=models.PROTECT,
        related_name="commandes_ecommerce",
        null=True,
        blank=True,
    )

    nom_client = models.CharField(
        max_length=150,
    )

    telephone_client = models.CharField(
        max_length=30,
    )

    email_client = models.EmailField(
        blank=True,
        null=True,
    )

    adresse_livraison = models.TextField(
        blank=True,
        null=True,
    )

    # --------------------------------------------------------
    # Statut
    # --------------------------------------------------------

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    # --------------------------------------------------------
    # Montants
    # --------------------------------------------------------

    montant_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Total des produits avant frais de transaction.",
    )

    frais_transaction = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    montant_a_payer = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="montant_total + frais_transaction",
    )

    # --------------------------------------------------------
    # Vente ERP
    # Créée UNIQUEMENT après paiement confirmé
    # --------------------------------------------------------

    vente = models.OneToOneField(
        "sale.Vente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commande_ecommerce",
    )

    # --------------------------------------------------------
    # Facture ERP
    # Créée UNIQUEMENT après paiement confirmé
    # --------------------------------------------------------

    facture = models.OneToOneField(
        "sale.Facture",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commande_ecommerce",
    )

    # --------------------------------------------------------
    # Dates
    # --------------------------------------------------------

    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    frais_transaction = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["bijouterie", "status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["telephone_client"]),
        ]

    def __str__(self):
        return f"Commande E-commerce {self.uuid} - {self.status}"

    @property
    def est_payee(self):
        return self.status == self.STATUS_PAID


# ============================================================
# LIGNES DE COMMANDE
# ============================================================

class CommandeEcommerceLigne(models.Model):

    commande = models.ForeignKey(
        CommandeEcommerce,
        on_delete=models.CASCADE,
        related_name="lignes",
    )

    # IMPORTANT :
    # ProduitLine permet de savoir exactement
    # quelle ligne de stock doit être consommée.
    produit_line = models.ForeignKey(
        "purchase.ProduitLine",
        on_delete=models.PROTECT,
        related_name="lignes_ecommerce",
    )

    produit = models.ForeignKey(
        "store.Produit",
        on_delete=models.PROTECT,
        related_name="lignes_ecommerce",
    )

    quantite = models.PositiveIntegerField(
        default=1,
    )

    prix_unitaire = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    montant_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["id"]

        indexes = [
            models.Index(fields=["commande"]),
            models.Index(fields=["produit_line"]),
            models.Index(fields=["produit"]),
        ]

    def __str__(self):
        return (
            f"{self.commande.uuid} - "
            f"{self.produit} x {self.quantite}"
        )


# ============================================================
# PAIEMENT E-COMMERCE
# ============================================================

class PaiementEcommerce(models.Model):

    # --------------------------------------------------------
    # Moyens de paiement
    # --------------------------------------------------------

    MODE_WAVE = "wave"
    MODE_ORANGE = "orange_money"
    MODE_CARTE = "carte"

    MODE_CHOICES = [
        (MODE_WAVE, "Wave"),
        (MODE_ORANGE, "Orange Money"),
        (MODE_CARTE, "Carte bancaire"),
    ]

    # --------------------------------------------------------
    # Statuts
    # --------------------------------------------------------

    STATUS_PENDING = "pending"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_SUCCESS, "Réussi"),
        (STATUS_FAILED, "Échoué"),
        (STATUS_CANCELLED, "Annulé"),
    ]

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )

    commande = models.ForeignKey(
        CommandeEcommerce,
        on_delete=models.CASCADE,
        related_name="paiements",
    )

    mode = models.CharField(
        max_length=30,
        choices=MODE_CHOICES,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    # --------------------------------------------------------
    # Montants
    # --------------------------------------------------------

    montant = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    frais_transaction = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    # --------------------------------------------------------
    # Références paiement
    # --------------------------------------------------------

    reference_paiement = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        db_index=True,
    )

    transaction_id = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        db_index=True,
    )

    provider_reference = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
    )

    # --------------------------------------------------------
    # Checkout
    # --------------------------------------------------------

    checkout_url = models.URLField(
        blank=True,
        null=True,
    )

    payment_token = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    # --------------------------------------------------------
    # Webhook
    # --------------------------------------------------------

    callback_received = models.BooleanField(
        default=False,
    )

    raw_response = models.JSONField(
        default=dict,
        blank=True,
    )

    # --------------------------------------------------------
    # Dates
    # --------------------------------------------------------

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["commande", "status"]),
            models.Index(fields=["mode", "status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return (
            f"{self.mode} - "
            f"{self.status} - "
            f"{self.montant} FCFA"
        )


# ============================================================
# LIVRAISON E-COMMERCE
# ============================================================

class LivraisonEcommerce(models.Model):

    STATUS_PREPARATION = "en_preparation"
    STATUS_EXPEDIE = "expedie"
    STATUS_LIVRE = "livre"
    STATUS_ANNULE = "annule"

    STATUS_CHOICES = [
        (STATUS_PREPARATION, "En préparation"),
        (STATUS_EXPEDIE, "Expédié"),
        (STATUS_LIVRE, "Livré"),
        (STATUS_ANNULE, "Annulé"),
    ]

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )

    commande = models.OneToOneField(
        CommandeEcommerce,
        on_delete=models.CASCADE,
        related_name="livraison",
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default=STATUS_PREPARATION,
        db_index=True,
    )

    adresse_livraison = models.TextField()

    telephone_client = models.CharField(
        max_length=30,
    )

    transporteur = models.CharField(
        max_length=150,
        blank=True,
        null=True,
    )

    numero_suivi = models.CharField(
        max_length=150,
        blank=True,
        null=True,
    )

    frais_livraison = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    note = models.TextField(
        blank=True,
        null=True,
    )

    prepared_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    shipped_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Livraison {self.commande.uuid} - "
            f"{self.status}"
        )
        


