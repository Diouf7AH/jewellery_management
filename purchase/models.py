import random
from django.conf import settings

from django.db import models
from decimal import Decimal
from store.models import Produit
import datetime
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.db.models.functions import Coalesce
import uuid
from django.db import models, IntegrityError
from django.utils.text import slugify

# Create your models here.
class Fournisseur(models.Model):
    nom = models.CharField(max_length=100, blank=True, null=True)
    prenom = models.CharField(max_length=100, blank=True, null=True)
    address = models.CharField(max_length=100, blank=True, null=True)
    telephone = models.CharField(max_length=15, unique=True, blank=True, null=True)
    slug = models.SlugField(max_length=30, unique=True, blank=True, null=True)  # <- important
    date_ajout = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    def __str__(self):
        # évite "None None None"
        parts = [p for p in [self.nom, self.prenom, self.telephone] if p]
        return " ".join(parts) or f"Fournisseur #{self.pk}"

    def _gen_unique_slug(self) -> str:
        MAX = 30
        # essaie quelques UUID courts pour éviter une (très) improbable collision
        for _ in range(5):
            cand = uuid.uuid4().hex[:MAX]
            if not Fournisseur.objects.filter(slug=cand).exists():
                return cand
        return uuid.uuid4().hex[:MAX]

    def save(self, *args, **kwargs):
        # normalise téléphone vide -> None (évite unique='' en base)
        if self.telephone == "":
            self.telephone = None

        if not self.slug:
            self.slug = self._gen_unique_slug()
        try:
            super().save(*args, **kwargs)
        except IntegrityError:
            # collision concurrente rarissime : on regénère une fois
            self.slug = self._gen_unique_slug()
            super().save(*args, **kwargs)
            
# Achat  Model
# class Achat(models.Model):
#     fournisseur = models.ForeignKey("Fournisseur",on_delete=models.SET_NULL,null=True, blank=True,
#         related_name="achats",        # manager côté Fournisseur
#         related_query_name="achat",   # lookups dans les requêtes
#     )
#     # fournisseur = models.ForeignKey('Fournisseur', related_name="achat", on_delete=models.SET_NULL, null=True, blank=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     montant_total_ht = models.DecimalField(default=0.00, null=True, max_digits=12, decimal_places=2)
#     montant_total_ttc = models.DecimalField(default=0.00, null=True, max_digits=12, decimal_places=2)

#     # une propriété pour les taxes globales
#     @property
#     def montant_total_tax(self):
#         return self.montant_total_ttc - self.montant_total_ht
    
#     def update_total(self):
#         """
#         Met à jour les montants HT et TTC de l'achat
#         en recalculant à partir des produits liés.
#         """
#         total = sum(p.sous_total_prix_achat for p in self.produits.all())
#         tax_total = sum(p.tax or 0 for p in self.produits.all())
#         self.montant_total_ht = total
#         self.montant_total_ttc = total + tax_total
#         self.save()
    
#     def get_produits_details(self):
#         return [
#             {
#                 "produit": p.produit.nom,
#                 "quantite": p.quantite,
#                 "prix_gramme": p.prix_achat_gramme,
#                 "sous_total": p.sous_total_prix_achat,
#                 "tax": p.tax,
#             }
#             for p in self.produits.all()
#         ]

#     def __str__(self):
#         return f"Achat Fournisseur: {self.fournisseur.nom if self.fournisseur else 'N/A'}"


class Achat(models.Model):
    fournisseur = models.ForeignKey("Fournisseur",on_delete=models.SET_NULL,null=True, blank=True,related_name="achats",related_query_name="achat",)
    created_at = models.DateTimeField(auto_now_add=True)
    montant_total_ht = models.DecimalField(default=Decimal("0.00"), null=True, max_digits=12, decimal_places=2)
    montant_total_ttc = models.DecimalField(default=Decimal("0.00"), null=True, max_digits=12, decimal_places=2)

    status = models.CharField(
        max_length=20,
        choices=[("confirmed", "Confirmé"), ("cancelled", "Annulé")],
        default="confirmed",
    )
    cancel_reason = models.TextField(null=True, blank=True)   # ✅ on persiste la raison
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="achats_annules"
    )
    
    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["fournisseur"]),
        ]
        verbose_name = "Achat"
        verbose_name_plural = "Achats"

    @property
    def montant_total_tax(self) -> Decimal:
        ht = self.montant_total_ht or Decimal("0.00")
        ttc = self.montant_total_ttc or Decimal("0.00")
        return ttc - ht

    def clean(self):
        if self.montant_total_ht is not None and self.montant_total_ht < 0:
            raise ValidationError({"montant_total_ht": "Le montant HT doit être ≥ 0."})
        if self.montant_total_ttc is not None and self.montant_total_ttc < 0:
            raise ValidationError({"montant_total_ttc": "Le montant TTC doit être ≥ 0."})
        if (self.montant_total_ht is not None and self.montant_total_ttc is not None
                and self.montant_total_ttc < self.montant_total_ht):
            raise ValidationError("Le montant TTC ne peut pas être inférieur au montant HT.")

    def update_total(self, save: bool = True):
        """
        Recalcule HT/TTC via agrégations SQL sur les lignes (AchatProduit).
        Suppose AchatProduit.achat has related_name='produits'.
        """
        agg = self.produits.aggregate(
            total_ht=Coalesce(Sum("sous_total_prix_achat"), Decimal("0.00")),
            total_tax=Coalesce(Sum("tax"), Decimal("0.00")),
        )
        self.montant_total_ht = agg["total_ht"]
        self.montant_total_ttc = agg["total_ht"] + agg["total_tax"]

        if save:
            self.full_clean()
            self.save(update_fields=["montant_total_ht", "montant_total_ttc"])

    def get_produits_details(self):
        qs = self.produits.select_related("produit").all()
        return [
            {
                "produit": (p.produit.nom if p.produit else None),
                "quantite": p.quantite,
                "prix_gramme": p.prix_achat_gramme,
                "sous_total": p.sous_total_prix_achat,
                "tax": p.tax,
            }
            for p in qs
        ]

    def __str__(self):
        nom = self.fournisseur.nom if getattr(self.fournisseur, "nom", None) else "N/A"
        return f"Achat Fournisseur: {nom}"


    # def save(self, *args, **kwargs):
    #         super().save(*args, **kwargs)
    #         if self.achat:
    #             # appel update_total() automatiquement à chaque fois qu’un produit est ajouté/modifié.
    #             self.achat.update_total()
    
    
# VenteProduit (Product in Sale) Model
# class AchatProduit(models.Model):
#     achat = models.ForeignKey(Achat, related_name="achat", on_delete=models.CASCADE)
#     produit = models.ForeignKey(Produit, related_name="achats_produits", on_delete=models.CASCADE)
#     numero_achat_produit = models.CharField(max_length=25, unique=True, null=True, blank=True)
#     quantite = models.PositiveIntegerField(default=0, validators=[MinValueValidator(1)])
#     prix_achat_gramme = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
#     fournisseur = models.ForeignKey(Fournisseur, on_delete=models.SET_NULL, null=True, blank=True)
#     tax = models.DecimalField(default=0.00, decimal_places=2, max_digits=12, null=True, blank=True)
#     sous_total_prix_achat = models.DecimalField(default=0.00, null=True, decimal_places=2, max_digits=12)

#     class Meta:
#         verbose_name = "Produit acheté"
#         verbose_name_plural = "Produits achetés"

#     def __str__(self):
#         return f"{self.quantite} x {self.produit.nom if self.produit else 'N/A'} in Achat {self.achat.id if self.achat else 'N/A'}"
    
#     @property
#     def prix_achat_total_ttc(self):
#         return (self.sous_total_prix_achat or Decimal(0)) + (self.tax or Decimal(0))

#     def save(self, *args, **kwargs):
#         # Générer numéro unique si vide
#         if not self.numero_achat_produit:
#             today = timezone.now().strftime('%Y%m%d')
#             prefix = f"ACH-PROD-{today}"
#             for _ in range(10):
#                 suffix = ''.join(random.choices('0123456789', k=4))
#                 numero = f"{prefix}-{suffix}"
#                 if not AchatProduit.objects.filter(numero_achat_produit=numero).exists():
#                     self.numero_achat_produit = numero
#                     break
#             else:
#                 raise Exception("Impossible de générer un numéro d'achat produit unique.")

#         # ⚙️ Calcul automatique du sous-total
#         poids = self.produit.poids or Decimal(0)
#         self.sous_total_prix_achat = self.prix_achat_gramme * self.quantite * poids

#         super().save(*args, **kwargs)
        
#         # 🔁 Met à jour automatiquement les montants HT/TTC dans Achat
#         if self.achat:
#             self.achat.update_total()

#     def to_dict(self):
#         return {
#             "produit": self.produit.nom,
#             "quantite": self.quantite,
#             "prix_achat_gramme": self.prix_achat_gramme,
#             "sous_total_prix_achat": self.sous_total_prix_achat,
#             "tax": self.tax,
#             "prix_achat_total_ttc": self.prix_achat_total_ttc,
#         }


class AchatProduit(models.Model):
    achat = models.ForeignKey(
        Achat,
        related_name="produits",                # ✅ correspond à Achat.update_total()
        on_delete=models.CASCADE
    )
    produit = models.ForeignKey(
        Produit,
        related_name="achats_produits",
        on_delete=models.CASCADE
    )

    numero_achat_produit = models.CharField(max_length=25, unique=True, null=True, blank=True)
    lot_code = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    quantite = models.PositiveIntegerField(
        default=1,                              # ✅ cohérent avec MinValueValidator(1)
        validators=[MinValueValidator(1)]
    )
    prix_achat_gramme = models.DecimalField(
        default=Decimal("0.00"),                # ✅ Decimal, pas float
        decimal_places=2, max_digits=12,
        validators=[MinValueValidator(Decimal("0.00"))]
    )
    fournisseur = models.ForeignKey(Fournisseur, on_delete=models.SET_NULL, null=True, blank=True)
    tax = models.DecimalField(
        default=Decimal("0.00"),
        decimal_places=2, max_digits=12, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.00"))]
    )
    sous_total_prix_achat = models.DecimalField(
        default=Decimal("0.00"),
        null=True, decimal_places=2, max_digits=12
    )

    created_at = models.DateTimeField(auto_now_add=True)       # 👍 pratique
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Produit acheté"
        verbose_name_plural = "Produits achetés"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["achat"]),
            models.Index(fields=["produit"]),
            models.Index(fields=["numero_achat_produit"]),
        ]

    def __str__(self):
        return f"{self.quantite} x {self.produit.nom if self.produit else 'N/A'} (Achat #{self.achat_id or 'N/A'})"

    @property
    def prix_achat_total_ttc(self):
        return (self.sous_total_prix_achat or Decimal("0.00")) + (self.tax or Decimal("0.00"))

    def save(self, *args, **kwargs):
        # 🔢 Numéro unique si manquant
        if not self.numero_achat_produit:
            today = timezone.now().strftime("%Y%m%d")
            prefix = f"ACH-PROD-{today}"
            for _ in range(10):
                suffix = "".join(random.choices("0123456789", k=4))
                candidate = f"{prefix}-{suffix}"
                if not AchatProduit.objects.filter(numero_achat_produit=candidate).exists():
                    self.numero_achat_produit = candidate
                    break
            else:
                raise Exception("Impossible de générer un numéro d'achat produit unique.")

        # ⚙️ Calcul sous-total (quantité * poids * prix/gramme)
        poids = (self.produit.poids or Decimal("0.00"))
        self.sous_total_prix_achat = (self.prix_achat_gramme or Decimal("0.00")) * Decimal(self.quantite) * poids

        super().save(*args, **kwargs)

        # 🔁 Recalcule les totaux de l'achat
        if self.achat_id:
            self.achat.update_total()