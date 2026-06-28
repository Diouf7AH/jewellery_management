# e_commerce/models.py

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


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

    # uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    uuid = models.UUIDField(default=uuid.uuid4,unique=True,editable=False,db_index=True,)

    client = models.ForeignKey(
        "sale.Client",
        on_delete=models.PROTECT,
        related_name="commandes_ecommerce",
        null=True,
        blank=True,
    )

    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        related_name="commandes_ecommerce",
    )

    nom_client = models.CharField(max_length=150)
    telephone_client = models.CharField(max_length=30)
    email_client = models.EmailField(blank=True, null=True)
    adresse_livraison = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    montant_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    frais_transaction = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    montant_a_payer = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    vente = models.OneToOneField(
        "sale.Vente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commande_ecommerce",
    )

    facture = models.OneToOneField(
        "sale.Facture",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commande_ecommerce",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commandes_ecommerce_creees",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Commande e-commerce #{self.id} - {self.status}"


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

    quantite = models.PositiveIntegerField(default=1)

    prix_unitaire = models.DecimalField(max_digits=14, decimal_places=2)
    montant_total = models.DecimalField(max_digits=14, decimal_places=2)

    def __str__(self):
        return f"{self.produit} x {self.quantite}"


class PaiementEcommerce(models.Model):
    MODE_WAVE = "wave"
    MODE_ORANGE = "orange_money"
    MODE_CARTE = "carte"

    MODE_CHOICES = [
        (MODE_WAVE, "Wave"),
        (MODE_ORANGE, "Orange Money"),
        (MODE_CARTE, "Carte bancaire"),
    ]

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

    # uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    uuid = models.UUIDField(default=uuid.uuid4,unique=True,editable=False,db_index=True,)

    commande = models.ForeignKey(
        CommandeEcommerce,
        on_delete=models.CASCADE,
        related_name="paiements",
    )

    mode = models.CharField(max_length=30, choices=MODE_CHOICES)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    montant = models.DecimalField(max_digits=14, decimal_places=2)
    frais_transaction = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    reference_paiement = models.CharField(max_length=150, blank=True, db_index=True)
    transaction_id = models.CharField(max_length=150, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    
    provider_reference = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
    )

    checkout_url = models.URLField(
        blank=True,
        null=True,
    )

    payment_token = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    callback_received = models.BooleanField(default=False)
    raw_response = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.mode} - {self.status} - {self.montant}"
    
    


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

    # uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    uuid = models.UUIDField(default=uuid.uuid4,unique=True,editable=False,db_index=True,)
    commande = models.OneToOneField(
        "e_commerce.CommandeEcommerce",
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
    telephone_client = models.CharField(max_length=30)

    transporteur = models.CharField(max_length=150, blank=True, null=True)
    numero_suivi = models.CharField(max_length=150, blank=True, null=True)

    frais_livraison = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    note = models.TextField(blank=True, null=True)

    prepared_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Livraison {self.commande.uuid} - {self.status}"
    


class EcommerceBanner(models.Model):
    TYPE_IMAGE = "image"
    TYPE_VIDEO = "video"

    TYPE_CHOICES = [
        (TYPE_IMAGE, "Image"),
        (TYPE_VIDEO, "Vidéo"),
    ]
    
    POSITION_GRANDE_BANNIERE = "grande_banniere"
    POSITION_NOUVEAU_ARRIVAGE = "nouveau_arrivage"
    POSITION_BANNIERE_VIDEO = "banniere_video"
    POSITION_PROMOTION = "promotion"

    POSITION_CHOICES = [
        (POSITION_GRANDE_BANNIERE, "Grande bannière accueil"),
        (POSITION_NOUVEAU_ARRIVAGE, "Bannière nouveau arrivage"),
        (POSITION_BANNIERE_VIDEO, "Bannière vidéo"),
        (POSITION_PROMOTION, "Bannière promotion"),
    ]

    uuid = models.UUIDField(default=uuid.uuid4,unique=True,editable=False, db_index=True,)
    titre = models.CharField(max_length=150, blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    type_media = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_IMAGE,
        db_index=True,
    )
    position = models.CharField(
        max_length=40,
        choices=POSITION_CHOICES,
        default=POSITION_GRANDE_BANNIERE,
        db_index=True,
    )
    image = models.ImageField(
        upload_to="ecommerce/banners/images/",
        blank=True,
        null=True,
    )
    video = models.FileField(
        upload_to="ecommerce/banners/videos/",
        blank=True,
        null=True,
    )

    lien_action = models.URLField(blank=True, null=True)
    texte_bouton = models.CharField(max_length=80, blank=True, null=True)

    active = models.BooleanField(default=True, db_index=True)
    ordre_affichage = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ordre_affichage", "-created_at"]

    def clean(self):

        if self.type_media == self.TYPE_IMAGE and not self.image:
            raise ValidationError({
                "image": "L'image est obligatoire pour une bannière image."
            })

        if self.type_media == self.TYPE_VIDEO and not self.video:
            raise ValidationError({
                "video": "La vidéo est obligatoire pour une bannière vidéo."
            })

    def __str__(self):
        return self.titre or f"Bannière #{self.pk}"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    


class EcommerceHomeProduct(models.Model):
    SECTION_FEATURED = "featured"
    SECTION_NEW_ARRIVAL = "new_arrival"
    SECTION_SLIDER = "slider"
    SECTION_BEST_SELLER = "best_seller"

    SECTION_CHOICES = [
        (SECTION_FEATURED, "Produits sélectionnés"),
        (SECTION_NEW_ARRIVAL, "Nouveaux arrivages"),
        (SECTION_SLIDER, "Carrousel"),
        (SECTION_BEST_SELLER, "Meilleures ventes"),
    ]

    produit = models.ForeignKey(
        "store.Produit",
        on_delete=models.CASCADE,
        related_name="home_ecommerce_items",
    )

    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.CASCADE,
        related_name="home_ecommerce_products",
        null=True,
        blank=True,
    )

    section = models.CharField(
        max_length=30,
        choices=SECTION_CHOICES,
        default=SECTION_FEATURED,
        db_index=True,
    )

    active = models.BooleanField(default=True, db_index=True)
    ordre_affichage = models.PositiveIntegerField(default=0)

    titre_personnalise = models.CharField(max_length=150, blank=True, null=True)
    badge = models.CharField(max_length=50, blank=True, null=True)  # Nouveau, Promo, Top
    image_personnalisee = models.ImageField(
        upload_to="ecommerce/home/products/",
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = [
            "section",
            "ordre_affichage",
            "-created_at",
        ]

        indexes = [
            models.Index(
                fields=[
                    "section",
                    "active",
                ]
            ),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "produit",
                    "bijouterie",
                    "section",
                ],
                name="uniq_home_product_by_shop_section",
            )
        ]

    def __str__(self):
        return f"{self.produit} - {self.section}"

