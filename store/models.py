# store/models.py
import re
import uuid
from decimal import Decimal
from io import BytesIO
from random import SystemRandom

import qrcode
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import models
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
    ("ar", "Argent"),
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
    ("E", "Enfant")
)

ETAT = (
    ("N", "Neuf"),
    ("R", "Retour")
)

# store/models.py
class Bijouterie(models.Model):
    nom = models.CharField(max_length=30, unique=True, null=True)

    telephone_portable_1 = models.CharField(max_length=30, null=True, blank=True)
    telephone_portable_2 = models.CharField(max_length=30, null=True, blank=True)
    telephone_portable_3 = models.CharField(max_length=30, null=True, blank=True)
    telephone_portable_4 = models.CharField(max_length=30, null=True, blank=True)
    telephone_portable_5 = models.CharField(max_length=30, null=True, blank=True)
    telephone_fix = models.CharField(max_length=30, null=True, blank=True)

    appliquer_tva = models.BooleanField(default=True)
    taux_tva = models.DecimalField(max_digits=5,decimal_places=2,default=Decimal("18.00"))

    ninea = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Numéro NINEA de la bijouterie"
    )

    adresse = models.CharField(max_length=255, null=True, blank=True)

    logo_blanc = models.ImageField(upload_to="logo/", default="logo_blanc.jpg", null=True, blank=True)
    logo_noir = models.ImageField(upload_to="logo/", default="logo_noir.jpg", null=True, blank=True)

    nom_de_domaine = models.URLField(max_length=200, null=True, blank=True)
    tiktok = models.URLField(max_length=200, null=True, blank=True)
    facebook = models.URLField(max_length=200, null=True, blank=True)
    instagram = models.URLField(max_length=200, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Bijouteries"

    def __str__(self):
        return self.nom or "Bijouterie sans nom"

    def clean(self):
        super().clean()

        if self.ninea:
            self.ninea = self.ninea.strip().upper()

            if not re.match(r"^[A-Z0-9]+$", self.ninea):
                raise ValidationError({
                    "ninea": "Le NINEA doit contenir uniquement des lettres et chiffres."
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        
    

# Model for Product Categories
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
# class Type(models.Model):
#     type = models.CharField(max_length = 55, unique=True, null=True)
#     categorie = models.ForeignKey(Categorie, on_delete=models.SET_NULL, null=True, blank=True, related_name="type_categorie")
    
    
#     class Meta:
#         verbose_name_plural = "Types"
    
#     def __str__(self):
#         return self.type


# Type model
class Modele(models.Model):
    modele = models.CharField(max_length=55, unique=True, null=True)
    categorie = models.ForeignKey(Categorie, on_delete=models.SET_NULL, null=True, blank=True, related_name="modele_categorie")
    
    
    def __str__(self):
        # Affiche : "Bague (Catégorie: Bijoux)" ou "Bague (Catégorie: Aucune)"
        return f"{self.modele} (Catégorie: {self.categorie.nom if self.categorie else 'Aucune'})"

    @property
    def categorie_id(self):
        # Permet d'accéder à modele.categorie_id directement (int ou None)
        return self.categorie.id if self.categorie else None



# Purity model
class Purete(models.Model):
    # purete = models.IntegerField()
    purete = models.CharField(unique=True, max_length=15)
    
    def __str__(self):  
        return f"{self.purete}K"
    

# Brand model
# class Marque(models.Model):
#     marque = models.CharField(unique=True, max_length=25, null=True, blank=True)
#     purete = models.ForeignKey(Purete, on_delete=models.SET_NULL, null=True, blank=True, related_name="purete_marque", default=get_default_purete)
#     prix = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
#     creation_date = models.DateTimeField(auto_now_add=True)
#     modification_date = models.DateTimeField(auto_now=True)

#     def save(self, *args, **kwargs):
#         if not self.marque:
#             raise ValueError("Le champ 'marque' ne peut pas être vide.")
#         super().save(*args, **kwargs)
    
#     class Meta:
#         verbose_name_plural = "Marques"
    
#     def __str__(self):
#         return f"{self.marque} - {self.purete.purete if self.purete else 'N/A'}"


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

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="changements_prix_marque_purete",
    )

    changed_at = models.DateTimeField(auto_now_add=True)

    source = models.CharField(
        max_length=30,
        choices=SOURCE_CHOICES,
        blank=True,
        null=True,
        help_text="Origine du changement",
    )
    note = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ["-changed_at", "-id"]
        indexes = [
            models.Index(fields=["changed_at"]),
            models.Index(fields=["marque_purete", "changed_at"]),
            models.Index(fields=["marque", "purete"]),
            models.Index(fields=["bijouterie"]),
            models.Index(fields=["source"]),
            models.Index(fields=["changed_by"]),
        ]
        constraints = [
            CheckConstraint(check=Q(ancien_prix__gte=0), name="mph_ancien_prix_gte_0"),
            CheckConstraint(check=Q(nouveau_prix__gte=0), name="mph_nouveau_prix_gte_0"),
        ]

    def __str__(self):
        return (
            f"{self.marque} / {self.purete} : "
            f"{self.ancien_prix} -> {self.nouveau_prix} "
            f"({self.changed_at:%d/%m/%Y %H:%M})"
        )
        
    
# # Model model
# class Model(models.Model):
#     nom = models.CharField(max_length=255)
#     type = models.ForeignKey(Type, on_delete=models.SET_NULL, null=True, blank=True, related_name="type_model")
#     description = models.TextField(blank=True)

# def generate_sku(length=7):
#     return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# Model for Produits
# class Produit(models.Model):
#     # bijouterie = models.ForeignKey(Bijouterie, on_delete=models.CASCADE, null=True, blank=True, related_name="bijouterie_produit")
#     nom = models.CharField(max_length=100, blank=True, default="")
#     image = models.ImageField(upload_to='produits/', blank=True, null=True)
#     description = models.TextField(null=True, blank=True)
#     qr_code = models.ImageField(upload_to='qr_codes/', null=True, blank=True)
    
#     categorie = models.ForeignKey(Categorie, on_delete=models.SET_NULL, null=True, blank=True, related_name="categorie_produit")
#     purete = models.ForeignKey(Purete, on_delete=models.SET_NULL, null=True, blank=True, related_name="purete_produit", default=get_default_purete)
#     marque = models.ForeignKey(Marque, on_delete=models.SET_NULL, null=True, blank=True, related_name="marque_produit")
#     matiere = models.CharField(choices=MATIERE, max_length=50, default="or", null=True, blank=True)
#     modele = models.ForeignKey(Modele, on_delete=models.SET_NULL, null=True, blank=True, related_name="modele_produit")

#     poids = models.DecimalField(default=0.00, decimal_places=2, max_digits=12) 
#     taille = models.DecimalField(blank=True, null=True, default=0.00, decimal_places=2, max_digits=12)
#     genre = models.CharField(choices=GENRE, default="F", max_length=10, blank=True, null=True)
#     status = models.CharField(choices=STATUS, max_length=10, default="publié", null=True, blank=True)
#     etat = models.CharField(choices=ETAT, max_length=10, default="N", null=True, blank=True)
    
#     sku = models.SlugField(unique=True, max_length=100, null=True, blank=True)
#     slug = models.SlugField(max_length=100, unique=True, blank=True, null=True)

#     date_ajout = models.DateTimeField(auto_now_add=True) 
#     date_modification = models.DateTimeField(auto_now=True) 
    
#     def skuGet(self):
#         champs = [self.categorie, self.modele, self.marque, self.poids, self.taille, self.purete, self.etat]
#         if not all(champs):
#             return None  # <-- éviter l'erreur fatale

#         return (
#             f"{self.categorie.nom[:4].upper()}-"
#             f"{self.modele.modele[:4].upper()}-"
#             f"{self.etat}-"
#             f"{self.purete.purete}-"
#             f"{self.marque.marque[:3].upper()}-"
#             f"P{self.poids}-T{self.taille}"
#         )
    
#     @staticmethod
#     def generate_qr_code_image(content):
#         qr = qrcode.QRCode(version=1, box_size=10, border=4)
#         qr.add_data(content)
#         qr.make(fit=True)

#         img = qr.make_image(fill='black', back_color='white')
#         buffer = BytesIO()
        
#         # Nettoyer le nom du fichier
#         safe_name = slugify(content)[:50] if content else uuid.uuid4().hex[:10]
#         img.save(buffer, format='PNG')
#         buffer.seek(0)
#         return File(buffer, name=f'qr_{safe_name}.png')
    
#     def regenerate_qr_code(self):
#         try:
#             qr_content = self.produit_url
#             qr_file = self.generate_qr_code_image(qr_content)
#             self.qr_code.save(qr_file.name, qr_file, save=True)
#             return True
#         except Exception as e:
#             print(f"[QR ERROR] {e}")
#             return False

#     def save(self, *args, **kwargs):
#         self.full_clean()  # 🔁 Appelle clean() et valide les champs
#         is_new = self.pk is None
#         generer_qr = False

#         if not self.nom and self.categorie and self.modele and self.marque:
#             self.nom = f'{self.categorie} {self.modele} {self.marque}'

#         if not self.slug:
#             base_slug = slugify(self.nom or "produit")
#             self.slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
#             generer_qr = True  # 🔄 Générer QR uniquement si nouveau slug

#         if not self.sku:
#             sku = self.skuGet()
#             if sku:
#                 self.sku = sku

#         super().save(*args, **kwargs)

#         if not self.qr_code and generer_qr:
#             try:
#                 qr_content = self.produit_url
#                 qr_file = self.generate_qr_code_image(qr_content)
#                 self.qr_code.save(qr_file.name, qr_file, save=False)
#                 super().save(update_fields=["qr_code"])  # ✅ évite double save complet
#             except Exception as e:
#                 print(f"[QR ERROR] {e}")
                
#     @property
#     def produit_url(self):
#         base_url = getattr(settings, 'SITE_URL', 'https://www.rio-gold.com')
#         return f"{base_url}/produit/{self.slug}" if self.slug else None
    
#     def clean(self):
#         if self.poids < 0:
#             raise ValidationError("Le poids ne peut pas être négatif.")
#         if self.taille is not None and self.taille < 0:
#             raise ValidationError("La taille ne peut pas être négative.")
    
    
#     # Achiffage admin.py
#     def qr_code_url(self):
#         if self.qr_code:
#             return self.qr_code.url
#         return "Aucun QR code"

#     qr_code_url.short_description = "QR Code"
    
#     def __str__(self):
#         return f'{self.sku}'
    
#     class Meta:
#         ordering = ['-id']
#         verbose_name_plural = "Produits"


class Produit(models.Model):
    nom = models.CharField(max_length=100, blank=True, default="")
    image = models.ImageField(upload_to="produits/", blank=True, null=True)
    description = models.TextField(null=True, blank=True)

    # QR code sera généré via signal post_save (transaction.on_commit)
    qr_code = models.ImageField(upload_to="qr_codes/", null=True, blank=True)

    categorie = models.ForeignKey("Categorie", on_delete=models.SET_NULL, null=True, blank=True, related_name="categorie_produit")
    purete = models.ForeignKey("Purete", on_delete=models.SET_NULL, null=True, blank=True, related_name="purete_produit", default=get_default_purete)
    marque = models.ForeignKey("Marque", on_delete=models.SET_NULL, null=True, blank=True, related_name="marque_produit")
    matiere = models.CharField(choices=MATIERE, max_length=50, default="or", null=True, blank=True)
    modele = models.ForeignKey("Modele", on_delete=models.SET_NULL, null=True, blank=True, related_name="modele_produit")

    poids = models.DecimalField(default=Decimal("0.00"), decimal_places=2, max_digits=12)
    taille = models.DecimalField(blank=True, null=True, default=Decimal("0.00"), decimal_places=2, max_digits=12)

    genre = models.CharField(choices=GENRE, default="F", max_length=10, blank=True, null=True)
    status = models.CharField(choices=STATUS, max_length=10, default="publié", null=True, blank=True)
    etat = models.CharField(choices=ETAT, max_length=10, default="N", null=True, blank=True)

    sku = models.SlugField(unique=True, max_length=120, null=True, blank=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True, null=True)

    date_ajout = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        verbose_name_plural = "Produits"

    def __str__(self):
        return self.sku or self.nom or (self.slug or f"Produit#{self.pk}")

    @property
    def produit_url(self):
        base_url = getattr(settings, "SITE_URL", "https://www.rio-gold.com")
        return f"{base_url}/produit/{self.slug}" if self.slug else None

    def clean(self):
        if self.poids is not None and self.poids < 0:
            raise ValidationError("Le poids ne peut pas être négatif.")
        if self.taille is not None and self.taille < 0:
            raise ValidationError("La taille ne peut pas être négative.")

    # def skuGet(self):
    #     # Ne pas bloquer sur poids/taille=0.00
    #     if not (self.categorie and self.modele and self.marque and self.purete and self.etat):
    #         return None

    #     poids = self.poids if self.poids is not None else Decimal("0.00")
    #     taille = self.taille if self.taille is not None else Decimal("0.00")

    #     poids_str = str(poids).replace('.', 'g')
    #     taille_str = str(taille).replace('.', 'cm')
            
    #     return (
    #         f"{(self.categorie.nom or '')[:4].upper()}-"
    #         f"{(self.modele.modele or '')[:4].upper()}-"
    #         f"{self.etat}-"
    #         f"{self.purete.purete}-"
    #         f"{(self.marque.marque or '')[:3].upper()}-"
    #         f"P{poids_str}-T{taille_str}"
    #     )

    # def _make_unique_sku(self, base_sku: str) -> str:
    #     if not base_sku:
    #         return base_sku

    #     sku = base_sku
    #     i = 2
    #     while Produit.objects.filter(sku=sku).exclude(pk=self.pk).exists():
    #         sku = f"{base_sku}-{i}"
    #         i += 1
    #     return sku
    
    def skuGet(self):
        if not (self.categorie and self.modele and self.marque and self.purete and self.etat):
            return None

        poids = self.poids if self.poids is not None else Decimal("0.00")
        taille = self.taille if self.taille is not None else Decimal("0.00")

        # 🔥 format exact que tu veux
        poids_str = f"{poids:.2f}".replace(".", "-")
        taille_str = f"{taille:.2f}".replace(".", "-")

        return (
            f"{(self.categorie.nom or '')[:4].upper()}-"
            f"{(self.modele.modele or '')[:4].upper()}-"
            f"{self.etat}-"
            f"{self.purete.purete}-"
            f"{(self.marque.marque or '')[:3].upper()}-"
            f"P{poids_str}-T{taille_str}"
        )


    def _make_unique_sku(self, base_sku: str) -> str:
        if not base_sku:
            return base_sku

        # 🔥 sécurise définitivement (slug valide)
        base_sku = slugify(base_sku).upper()

        sku = base_sku
        i = 2

        while Produit.objects.filter(sku=sku).exclude(pk=self.pk).exists():
            sku = f"{base_sku}-{i}"
            i += 1

        return sku


    # @staticmethod
    # def generate_qr_code_image(*, content: str, filename_hint: str | None = None) -> File:
    #     qr = qrcode.QRCode(version=1, box_size=10, border=4)
    #     qr.add_data(content or "")
    #     qr.make(fit=True)

    #     img = qr.make_image(fill_color="black", back_color="white")
    #     buffer = BytesIO()
    #     img.save(buffer, format="PNG")
    #     buffer.seek(0)

    #     # Nom court et stable
    #     safe_name = slugify(filename_hint or "")[:40] or uuid.uuid4().hex[:10]
    #     return File(buffer, name=f"qr_{safe_name}.png")

    
    @staticmethod
    def generate_qr_code_image(*, produit, filename_hint: str | None = None) -> File:
        """
        Génère un QR code optimisé pour scan POS ultra rapide
        """

        # 🔥 contenu ultra rapide
        qr_content = f"P:{produit.id}"

        qr = qrcode.QRCode(
            version=None,          # auto
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=6,            # 🔥 plus petit = scan plus rapide
            border=2               # 🔥 réduit pour étiquette
        )

        qr.add_data(qr_content)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        safe_name = slugify(filename_hint or "")[:40] or uuid.uuid4().hex[:10]

        return File(buffer, name=f"qr_{safe_name}.png")
    

    def save(self, *args, **kwargs):
        self.full_clean()

        if not self.nom and self.categorie and self.modele and self.marque:
            self.nom = f"{self.categorie} {self.modele} {self.marque}"

        if not self.slug:
            base_slug = slugify(self.nom or "produit")
            self.slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"

        if not self.sku:
            sku = self.skuGet()
            if sku:
                self.sku = self._make_unique_sku(sku)

        super().save(*args, **kwargs)

    # Admin helper
    def qr_code_url(self):
        return self.qr_code.url if self.qr_code else "Aucun QR code"

    qr_code_url.short_description = "QR Code"


# Model for Product Gallery
class Gallery(models.Model):
    produit = models.ForeignKey(
        Produit, on_delete=models.CASCADE, null=True, related_name="produit_gallery"
    )
    image = models.ImageField(upload_to='produit_gallery/')
    active = models.BooleanField(default=True)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image de {self.produit.nom}"

    def image_url(self):
        if self.image:
            return self.image.url  # <== retourne l'URL utilisable

        return None

    class Meta:
        verbose_name_plural = "Galerie"
        ordering = ['-date']
        

