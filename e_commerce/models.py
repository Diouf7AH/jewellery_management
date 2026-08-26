# e_commerce/models.py

import uuid
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import models

TWOPLACES = Decimal("0.01")
ZERO = Decimal("0.00")

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

    # client = models.ForeignKey(
    #     "sale.Client",
    #     on_delete=models.PROTECT,
    #     related_name="commandes_ecommerce",
    #     null=True,
    #     blank=True,
    # )
    
    client = models.ForeignKey(
        "sale.Client",
        on_delete=models.PROTECT,
        related_name="commandes_ecommerce",
    )

    nom_client = models.CharField(
        max_length=150,
    )

    telephone_client = models.CharField(
        max_length=30,
    )

    email_client = models.EmailField()

    adresse_livraison = models.TextField()  

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
        default=Decimal("0.00"),
    )

    montant_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Total HT des produits.",
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
        help_text="montant_total + montant_tva + frais_transaction",
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

    
    def recalculer_totaux(self):
        montant_ht = Decimal(
            str(self.montant_total or ZERO)
        )

        frais = Decimal(
            str(self.frais_transaction or ZERO)
        )

        montant_tva = ZERO

        if self.appliquer_tva:
            taux = Decimal(
                str(self.taux_tva or ZERO)
            )

            montant_tva = (
                montant_ht
                * taux
                / Decimal("100")
            ).quantize(
                TWOPLACES,
                rounding=ROUND_HALF_UP,
            )

        self.montant_tva = montant_tva

        self.montant_a_payer = (
            montant_ht
            + montant_tva
            + frais
        ).quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )

        return self.montant_a_payer


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

    prix_gramme = models.DecimalField(
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
    # confirmation_paiement
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
        


# ============================================================
# BANNIÈRE PRINCIPALE E-COMMERCE
# ============================================================

class EcommerceBanner(models.Model):
    """
    Bannière principale affichée en haut
    de la page d'accueil e-commerce.
    """

    # --------------------------------------------------------
    # Contenu
    # --------------------------------------------------------

    titre = models.CharField(
        max_length=200,
        blank=True,
        null=True,
    )

    sous_titre = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    # --------------------------------------------------------
    # Image
    # --------------------------------------------------------

    image = models.ImageField(
        upload_to="ecommerce/banners/",
    )

    # --------------------------------------------------------
    # Bouton / action
    # --------------------------------------------------------

    texte_bouton = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    lien_action = models.CharField(
        max_length=500,
        blank=True,
        null=True,
    )

    # --------------------------------------------------------
    # Affichage
    # --------------------------------------------------------

    ordre_affichage = models.PositiveIntegerField(
        default=0,
        db_index=True,
    )

    active = models.BooleanField(
        default=True,
        db_index=True,
    )

    # --------------------------------------------------------
    # Dates
    # --------------------------------------------------------

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "ordre_affichage",
            "-created_at",
        ]

        indexes = [
            models.Index(
                fields=[
                    "active",
                    "ordre_affichage",
                ],
            ),
        ]

        verbose_name = "Bannière e-commerce"
        verbose_name_plural = "Bannières e-commerce"

    def __str__(self):
        return (
            self.titre
            or f"Bannière e-commerce #{self.pk}"
        )

# ============================================================
# NOUVEAUX ARRIVAGES E-COMMERCE
# ============================================================

class EcommerceBannerNouveauArrivage(models.Model):

    TYPE_IMAGE = "image"
    TYPE_VIDEO = "video"

    TYPE_MEDIA_CHOICES = [
        (TYPE_IMAGE, "Image"),
        (TYPE_VIDEO, "Vidéo"),
    ]

    titre = models.CharField(
        max_length=200,
        blank=True,
        null=True,
    )

    sous_titre = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    type_media = models.CharField(
        max_length=20,
        choices=TYPE_MEDIA_CHOICES,
        default=TYPE_IMAGE,
        db_index=True,
    )

    image = models.ImageField(
        upload_to="ecommerce/nouveaux_arrivages/images/",
        blank=True,
        null=True,
    )

    video = models.FileField(
        upload_to="ecommerce/nouveaux_arrivages/videos/",
        blank=True,
        null=True,
    )

    texte_bouton = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    lien_action = models.CharField(
        max_length=500,
        blank=True,
        null=True,
    )

    ordre_affichage = models.PositiveIntegerField(
        default=0,
        db_index=True,
    )

    active = models.BooleanField(
        default=True,
        db_index=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def clean(self):
        super().clean()

        if self.type_media == self.TYPE_IMAGE:
            if not self.image:
                raise ValidationError({
                    "image": (
                        "Une image est obligatoire "
                        "pour un média de type image."
                    )
                })

            if self.video:
                raise ValidationError({
                    "video": (
                        "Une vidéo ne doit pas être définie "
                        "pour un média de type image."
                    )
                })

        elif self.type_media == self.TYPE_VIDEO:
            if not self.video:
                raise ValidationError({
                    "video": (
                        "Une vidéo est obligatoire "
                        "pour un média de type vidéo."
                    )
                })

            if self.image:
                raise ValidationError({
                    "image": (
                        "Une image ne doit pas être définie "
                        "pour un média de type vidéo."
                    )
                })

    class Meta:
        ordering = [
            "ordre_affichage",
            "-created_at",
        ]

        indexes = [
            models.Index(
                fields=[
                    "active",
                    "ordre_affichage",
                ]
            ),
        ]

        verbose_name = "Nouveau arrivage e-commerce"
        verbose_name_plural = "Nouveaux arrivages e-commerce"

    def __str__(self):
        return (
            self.titre
            or f"Nouveau arrivage #{self.pk}"
        )