# store/models.py
import re
import unicodedata
import uuid
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from io import BytesIO
from random import SystemRandom

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import CheckConstraint, Q
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify
from shortuuid.django_fields import ShortUUIDField


@receiver(post_migrate)
def create_default_instances(sender, **kwargs):
    if sender.name != "store":
        return
    Purete.objects.get_or_create(id=1, defaults={'purete': 21})
    Purete.objects.get_or_create(id=2, defaults={'purete': 18})
    
def get_default_purete():
    # return Purete.objects.get_or_create(id=1, defaults={'purete': 21})[0].id
    return Purete.objects.get_or_create(id=2, defaults={'purete': 18})[0].id

MATIERE = (
    ("or", "Or"),
    ("argent", "Argent"),
    ("mixte", "Mixte")
)

STATUS = (
    ("désactivé", "Désactivé"),
    ("rejetée", "Rejetée"),
    ("en_revue", "En Revue"),
    ("publié", "Publié"),
)

GENRE = (
    ("H", "Homme"),
    ("F", "Femme"),
    ("E", "Enfant"),
    ("U", "Unisexe")
)


class Bijouterie(models.Model):
    nom = models.CharField(
        max_length=100,
        unique=True,
    )

    # ============================================================
    # CONTACT
    # ============================================================

    telephone_portable_1 = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )

    telephone_portable_2 = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )

    telephone_portable_3 = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )

    telephone_portable_4 = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )

    telephone_portable_5 = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )

    telephone_fix = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )

    adresse = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    # ============================================================
    # INFORMATIONS LÉGALES
    # ============================================================

    ninea = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Numéro NINEA de la bijouterie",
    )

    # ============================================================
    # TVA
    # ============================================================

    appliquer_tva = models.BooleanField(
        default=False,
    )

    taux_tva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
    )

    # ============================================================
    # LOGOS
    # ============================================================

    logo_blanc = models.ImageField(
        upload_to="logo/",
        default="logo_blanc.jpg",
        null=True,
        blank=True,
    )

    logo_noir = models.ImageField(
        upload_to="logo/",
        default="logo_noir.jpg",
        null=True,
        blank=True,
    )

    # ============================================================
    # WEB / RÉSEAUX SOCIAUX
    # ============================================================

    nom_de_domaine = models.URLField(
        max_length=200,
        null=True,
        blank=True,
    )

    tiktok = models.URLField(
        max_length=200,
        null=True,
        blank=True,
    )

    facebook = models.URLField(
        max_length=200,
        null=True,
        blank=True,
    )

    instagram = models.URLField(
        max_length=200,
        null=True,
        blank=True,
    )

    # ============================================================
    # DATES
    # ============================================================

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    # ============================================================
    # META
    # ============================================================

    class Meta:
        verbose_name = "Bijouterie"
        verbose_name_plural = "Bijouteries"
        ordering = ["nom"]

    def __str__(self):
        return self.nom or f"Bijouterie #{self.pk}"

    # ============================================================
    # VALIDATION
    # ============================================================

    def clean(self):
        super().clean()

        errors = {}

        # --------------------------------------------------------
        # NOM
        # --------------------------------------------------------

        if self.nom:
            self.nom = self.nom.strip()

        if not self.nom:
            errors["nom"] = (
                "Le nom de la bijouterie est obligatoire."
            )

        # --------------------------------------------------------
        # NINEA
        # --------------------------------------------------------

        if self.ninea:
            self.ninea = self.ninea.strip().upper()

            if not re.fullmatch(r"[A-Z0-9]+", self.ninea):
                errors["ninea"] = (
                    "Le NINEA doit contenir uniquement "
                    "des lettres et des chiffres."
                )
        else:
            self.ninea = None

        # --------------------------------------------------------
        # TVA
        # --------------------------------------------------------

        if not self.appliquer_tva:
            self.taux_tva = None

        else:
            if self.taux_tva is None:
                errors["taux_tva"] = (
                    "Le taux de TVA est obligatoire "
                    "si la TVA est activée."
                )

            elif not (
                Decimal("0.00")
                <= self.taux_tva
                <= Decimal("100.00")
            ):
                errors["taux_tva"] = (
                    "Le taux de TVA doit être compris "
                    "entre 0 et 100."
                )

        if errors:
            raise ValidationError(errors)

    # ============================================================
    # SAVE
    # ============================================================

    def save(self, *args, **kwargs):
        self.full_clean()

        update_fields = kwargs.get("update_fields")

        if update_fields is not None:
            update_fields = set(update_fields)

            if update_fields:
                update_fields.update({
                    "nom",
                    "ninea",
                    "taux_tva",
                })

            kwargs["update_fields"] = update_fields

        return super().save(*args, **kwargs)
    
    
# Model for Produit Categories
class Categorie(models.Model):
    nom = models.CharField(max_length=30, unique=True, blank=True, default="")
    image = models.ImageField(upload_to='categorie/', default="category.jpg", null=True, blank=True)
    # bijouterie = models.ForeignKey(Bijouterie, on_delete=models.CASCADE, null=True, blank=True, related_name="bijouterie_categorie")

    class Meta:
        verbose_name_plural = "Catégories"
        ordering = ['nom']  # Tri par nom dans l’admin

    def __str__(self):
        return self.nom or "Sans nom"

    def save(self, *args, **kwargs):
        # Optionnel : tu peux faire un nettoyage ou un formatage du nom ici si besoin
        if self.nom:
            self.nom = self.nom.strip().title()
        super().save(*args, **kwargs)



# Type model
class Modele(models.Model):
    modele = models.CharField(
        max_length=55,
        unique=True,
        null=True,
    )

    categorie = models.ForeignKey(
        Categorie,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="modele_categorie",
    )

    def __str__(self):
        categorie = self.categorie.nom if self.categorie else "Aucune"
        return f"{self.modele or 'Sans modèle'} (Catégorie: {categorie})"

# Purity model
class Purete(models.Model):
    # purete = models.IntegerField()
    purete = models.CharField(unique=True, max_length=15)
    
    def __str__(self):  
        return f"{self.purete}K"
    

class Marque(models.Model):
    marque = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.marque
    
    def save(self, *args, **kwargs):
        if self.marque:
            self.marque = self.marque.strip().title()  # Ex: "strass" → "Strass"
        super().save(*args, **kwargs)
    


class MarquePurete(models.Model):
    marque = models.ForeignKey("Marque", on_delete=models.CASCADE, related_name="marque_puretes")
    purete = models.ForeignKey("Purete", on_delete=models.CASCADE, related_name="purete_marques")
    prix = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    date_ajout = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)  # utile pour l’historiquex
    
    class Meta:
        unique_together = ('marque', 'purete')  # évite les doublons
        verbose_name = "Liaison Marque–Pureté"
        verbose_name_plural = "Liaisons Marque–Pureté"
        indexes = [
            models.Index(fields=["marque", "purete"]),  # filtres plus rapides
        ]

    def __str__(self):
        # Purete a un champ "purete" (ex: "18" ou "18K")
        # Si tu stockes "18" sans K et veux afficher "18K", décommente la ligne suivante:
        # affichage_purete = f"{self.purete.purete}K" if not self.purete.purete.endswith("K") else self.purete.purete
        affichage_purete = self.purete.purete
        return f"{self.marque.marque} – {affichage_purete} : {self.prix} FCFA"

    # Optionnel mais conseillé : empêcher un prix négatif
    def clean(self):
        if self.prix is not None and self.prix < 0:
            raise ValidationError({"prix": "Le prix ne peut pas être négatif."})

    def save(self, *args, **kwargs):
        self.full_clean()  # déclenche clean() + validations de champs
        super().save(*args, **kwargs)

class MarquePuretePrixHistory(models.Model):
    SOURCE_API = "api"
    SOURCE_ADMIN = "admin"
    SOURCE_IMPORT = "import_excel"
    SOURCE_ROLLBACK = "rollback"

    SOURCE_CHOICES = (
        (SOURCE_API, "API"),
        (SOURCE_ADMIN, "Admin"),
        (SOURCE_IMPORT, "Import Excel"),
        (SOURCE_ROLLBACK, "Rollback"),
    )

    marque_purete = models.ForeignKey(
        "store.MarquePurete",
        on_delete=models.CASCADE,
        related_name="historiques_prix",
    )
    marque = models.ForeignKey(
        "store.Marque",
        on_delete=models.PROTECT,
        related_name="historiques_prix",
    )
    purete = models.ForeignKey(
        "store.Purete",
        on_delete=models.PROTECT,
        related_name="historiques_prix",
    )
    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="historiques_prix_marque_purete",
    )

    ancien_prix = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    nouveau_prix = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    modifier_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="changements_prix_marque_purete",
    )

    date_modification = models.DateTimeField(auto_now_add=True)

    source = models.CharField(
        max_length=30,
        choices=SOURCE_CHOICES,
        blank=True,
        null=True,
        help_text="Origine du changement",
    )
    note = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ["-date_modification", "-id"]
        indexes = [
            models.Index(fields=["date_modification"]),
            models.Index(fields=["marque_purete", "date_modification"]),
            models.Index(fields=["marque", "purete"]),
            models.Index(fields=["bijouterie"]),
            models.Index(fields=["source"]),
            models.Index(fields=["modifier_par"]),
        ]
        constraints = [
            CheckConstraint(check=Q(ancien_prix__gte=0), name="mph_ancien_prix_gte_0"),
            CheckConstraint(check=Q(nouveau_prix__gte=0), name="mph_nouveau_prix_gte_0"),
        ]

    def __str__(self):
        return (
            f"{self.marque} / {self.purete} : "
            f"{self.ancien_prix} -> {self.nouveau_prix} "
            f"({self.date_modification:%d/%m/%Y %H:%M})"
        )


class Produit(models.Model):
    """
    Catalogue unique des produits Rio-Gold.

    Un produit est identifié par six caractéristiques :
        - categorie
        - modele
        - marque
        - purete
        - poids
        - taille

    Un produit neuf et un produit d'occasion ayant les
    mêmes caractéristiques utilisent la même référence.

    L'état du bijou appartient à ProduitLine.
    """

    # ========================================================
    # IDENTIFIANTS
    # ========================================================

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    sku = models.CharField(
        max_length=120,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
    )

    slug = models.SlugField(
        max_length=120,
        unique=True,
        null=True,
        blank=True,
    )

    # ========================================================
    # INFORMATIONS GÉNÉRALES
    # ========================================================

    nom = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    image = models.ImageField(
        upload_to="produits/",
        null=True,
        blank=True,
    )

    description = models.TextField(
        null=True,
        blank=True,
    )

    # ========================================================
    # CARACTÉRISTIQUES DU PRODUIT
    # ========================================================

    categorie = models.ForeignKey(
        "Categorie",
        on_delete=models.PROTECT,
        related_name="categorie_produit",
    )

    modele = models.ForeignKey(
        "Modele",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="modele_produit",
    )

    marque = models.ForeignKey(
        "Marque",
        on_delete=models.PROTECT,
        related_name="marque_produit",
    )

    purete = models.ForeignKey(
        "Purete",
        on_delete=models.PROTECT,
        related_name="purete_produit",
    )

    matiere = models.CharField(
        max_length=50,
        choices=MATIERE,
        default="or",
    )

    genre = models.CharField(
        max_length=10,
        choices=GENRE,
        default="F",
    )

    poids = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    taille = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # ========================================================
    # DATES
    # ========================================================

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    # ========================================================
    # META
    # ========================================================

    class Meta:
        verbose_name = "Produit"
        verbose_name_plural = "Produits"
        ordering = ["-id"]

        indexes = [
            models.Index(
                fields=[
                    "categorie",
                    "modele",
                    "marque",
                    "purete",
                    "poids",
                    "taille",
                ],
                name="idx_produit_catalogue",
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=Q(poids__gt=0),
                name="ck_produit_poids_positif",
            ),
            models.CheckConstraint(
                condition=(
                    Q(taille__isnull=True)
                    | Q(taille__gte=0)
                ),
                name="ck_produit_taille_positive",
            ),
        ]

    def __str__(self):
        return self.nom or f"Produit #{self.pk}"

    # ========================================================
    # NORMALISATION DES DÉCIMAUX
    # ========================================================

    @staticmethod
    def _decimal(value):
        """
        Normalise poids et taille à deux décimales.
        """

        if value is None or value == "":
            return None

        try:
            return Decimal(str(value)).quantize(
                Decimal("0.01")
            )

        except (
            InvalidOperation,
            ValueError,
            TypeError,
        ):
            raise ValidationError(
                "Valeur décimale invalide."
            )

    # ========================================================
    # NORMALISATION DES CODES
    # ========================================================

    @staticmethod
    def _code(value, longueur):
        """
        Ignore :
            - majuscules / minuscules
            - accents
            - espaces
            - caractères spéciaux

        Exemple :
            Cartier -> CART
            CARTIER -> CART
            cartier -> CART
        """

        texte = unicodedata.normalize(
            "NFKD",
            str(value or ""),
        )

        texte = slugify(texte)

        texte = re.sub(
            r"[^a-zA-Z0-9]",
            "",
            texte,
        ).upper()

        return texte[:longueur] or "NA"

    # ========================================================
    # GÉNÉRATION DU SKU
    # ========================================================

    def skuGet(self):
        """
        Format :

        CAT(3)-MODELE(4)-MARQUE(4)-PURETE(2)-POIDS-TAILLE(2)

        Exemple :
        BAG-ALLI-CART-18-5.50-18

        L'état neuf/occasion n'entre pas dans le SKU.
        """

        categorie = self._code(
            self.categorie.nom,
            3,
        )

        modele = (
            self._code(
                self.modele.modele,
                4,
            )
            if self.modele_id
            else "NA"
        )

        marque = self._code(
            self.marque.marque,
            4,
        )

        purete = self._code(
            self.purete.purete,
            2,
        )

        poids = f"{self._decimal(self.poids):.2f}"

        taille = (
            self._code(
                f"{self._decimal(self.taille):.2f}",
                2,
            )
            if self.taille is not None
            else "NA"
        )

        return (
            f"{categorie}-"
            f"{modele}-"
            f"{marque}-"
            f"{purete}-"
            f"{poids}-"
            f"{taille}"
        )

    # ========================================================
    # RECHERCHE DU PRODUIT EXISTANT
    # ========================================================

    @classmethod
    def rechercher_existant(
        cls,
        *,
        categorie_id,
        modele_id=None,
        marque_id,
        purete_id,
        poids,
        taille=None,
        exclude_pk=None,
    ):
        """
        Recherche selon les six caractéristiques.

        Le SKU n'est pas utilisé comme identité métier,
        car deux produits différents peuvent avoir
        les mêmes abréviations.

        Les majuscules/minuscules des noms ne jouent
        aucun rôle lorsque les relations pointent vers
        les mêmes identifiants.
        """

        queryset = cls.objects.filter(
            categorie_id=categorie_id,
            modele_id=modele_id,
            marque_id=marque_id,
            purete_id=purete_id,
            poids=cls._decimal(poids),
            taille=cls._decimal(taille),
        )

        if exclude_pk is not None:
            queryset = queryset.exclude(
                pk=exclude_pk
            )

        return queryset.order_by("id").first()

    # ========================================================
    # GÉNÉRATION DU NOM
    # ========================================================

    def generer_nom(self):
        parties = []

        if self.categorie_id:
            parties.append(
                str(self.categorie.nom)
            )

        if self.modele_id:
            parties.append(
                str(self.modele.modele)
            )

        if self.marque_id:
            parties.append(
                str(self.marque.marque)
            )

        return (
            " ".join(parties)[:100]
            or "Produit"
        )

    # ========================================================
    # GÉNÉRATION DU SLUG
    # ========================================================

    def _generate_unique_slug(self):
        """
        Le UUID permet de limiter les collisions
        entre les slugs.
        """

        base = slugify(
            self.nom or "produit"
        )[:90] or "produit"

        return (
            f"{base[:80]}-"
            f"{self.uuid.hex[:16]}"
        )

    # ========================================================
    # URL DU PRODUIT
    # ========================================================

    @property
    def produit_url(self):
        if not self.slug:
            return None

        return f"/produits/{self.slug}/"

    # ========================================================
    # VALIDATION
    # ========================================================

    def clean(self):
        super().clean()

        errors = {}

        # Poids obligatoire et positif.
        if self.poids is not None and self.poids <= 0:
            errors["poids"] = (
                "Le poids doit être supérieur à zéro."
            )

        # Taille facultative mais non négative.
        if self.taille is not None and self.taille < 0:
            errors["taille"] = (
                "La taille ne peut pas être négative."
            )

        # Cohérence modèle / catégorie.
        if self.modele_id and self.categorie_id:
            if (
                self.modele.categorie_id
                != self.categorie_id
            ):
                errors["modele"] = (
                    "Le modèle sélectionné n'appartient "
                    "pas à cette catégorie."
                )

        # Recherche d'un doublon.
        if (
            self.categorie_id
            and self.marque_id
            and self.purete_id
            and self.poids is not None
        ):
            existant = self.rechercher_existant(
                categorie_id=self.categorie_id,
                modele_id=self.modele_id,
                marque_id=self.marque_id,
                purete_id=self.purete_id,
                poids=self.poids,
                taille=self.taille,
                exclude_pk=self.pk,
            )

            if existant:
                errors["categorie"] = (
                    "Ce produit existe déjà dans "
                    "le catalogue. "
                    f"ID : {existant.pk}. "
                    "Aucun doublon n'est autorisé."
                )

        if errors:
            raise ValidationError(errors)

    # ========================================================
    # ENREGISTREMENT
    # ========================================================

    def save(self, *args, **kwargs):
        """
        Génère automatiquement :
            - nom
            - sku
            - slug

        Vérifie les doublons avant l'enregistrement.
        """

        if not self.nom:
            self.nom = self.generer_nom()

        if not self.sku:
            base_sku = self.skuGet()

            candidat = base_sku
            compteur = 2

            # Deux produits distincts peuvent partager
            # le même préfixe SKU abrégé.
            while type(self).objects.filter(
                sku__iexact=candidat
            ).exclude(pk=self.pk).exists():

                candidat = (
                    f"{base_sku}-{compteur}"
                )

                compteur += 1

            self.sku = candidat

        if not self.slug:
            self.slug = self._generate_unique_slug()

        self.full_clean()

        return super().save(*args, **kwargs)

    # ========================================================
    # CRÉATION SANS DOUBLON
    # ========================================================

    @classmethod
    def get_or_create_catalogue(
        cls,
        *,
        categorie_id,
        modele_id=None,
        marque_id,
        purete_id,
        poids,
        taille=None,
        **defaults,
    ):
        """
        Recherche ou crée un produit.

        Retour :
            (produit, True)
                Nouveau produit créé.

            (produit, False)
                Produit déjà existant.

        La vue API peut utiliser created pour
        afficher le message d'information approprié.
        """

        poids = cls._decimal(poids)
        taille = cls._decimal(taille)

        with transaction.atomic():

            # Verrouillage de la catégorie.
            categorie_model = cls._meta.get_field(
                "categorie"
            ).remote_field.model

            categorie_model.objects.select_for_update().get(
                pk=categorie_id
            )

            # Vérifier si le produit existe.
            existant = cls.rechercher_existant(
                categorie_id=categorie_id,
                modele_id=modele_id,
                marque_id=marque_id,
                purete_id=purete_id,
                poids=poids,
                taille=taille,
            )

            if existant:
                return existant, False

            # Créer uniquement si inexistant.
            produit = cls(
                categorie_id=categorie_id,
                modele_id=modele_id,
                marque_id=marque_id,
                purete_id=purete_id,
                poids=poids,
                taille=taille,
                **defaults,
            )

            produit.save()

            return produit, True



class Gallery(models.Model):
    produit = models.ForeignKey(
        Produit,
        on_delete=models.CASCADE,
        related_name="produit_gallery",
    )

    image = models.ImageField(
        upload_to="produit_gallery/",
    )

    active = models.BooleanField(
        default=True,
        db_index=True,
    )

    date = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        verbose_name_plural = "Galerie"
        ordering = ["-date"]

    def __str__(self):
        return f"Image de {self.produit.nom or self.produit}"

    @property
    def image_url(self):
        if self.image:
            return self.image.url

        return None
    
    