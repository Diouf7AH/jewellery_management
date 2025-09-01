import random
import string
import uuid
from django.db.models import Sum
from decimal import Decimal, ROUND_HALF_UP
import random
from django.conf import settings
from django.db import models, IntegrityError, transaction
from django.utils import timezone
from store.models import Categorie, Marque, Modele, Produit, Purete
from vendor.models import Vendor
from django.core.exceptions import ValidationError
from django.db.models import Q, CheckConstraint

TWOPLACES = Decimal('0.01')
ZERO = Decimal('0.00')

# Create your models here.
# Client Model
class Client(models.Model):
    prenom = models.CharField(max_length=100)
    nom = models.CharField(max_length=100)
    telephone = models.CharField(max_length=15, unique=True, blank=True, null=True)
    # phone_number = PhoneNumberField(null=True, blank=True, unique=True)

    @property
    def full_name(self):
        return f"{self.prenom} {self.nom}"

    def __str__(self):
        return self.full_name


# Vente (Sale) Model
# class Vente(models.Model):
#     numero_vente = models.CharField(max_length=30, unique=True, editable=False, blank=True, null=True)
#     client = models.ForeignKey('sale.Client', on_delete=models.SET_NULL, null=True, blank=True, related_name="ventes")
#     created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="ventes_creees")
#     created_at = models.DateTimeField(auto_now_add=True)
#     montant_total = models.DecimalField(default=0.00, null=True, max_digits=12, decimal_places=2)
#     # (champ optionnel)
#     # explication
#     # Vente directe -> Le client achète directement -> la commande_source est null
#     # Vente issue d’une commande -> La commande est validée → vente -> commande
#     # Avantages
#     # Tu peux gérer les deux cas (avec ou sans commande) facilement.
#     # Tu peux suivre le cycle : commande → vente, ou vente directe.
#     # Tu peux afficher l’historique du client complet : ventes + commandes.
#     # commande_source = models.ForeignKey('order.CommandeClient', on_delete=models.SET_NULL, null=True, blank=True,related_name='command_en_ventes')
    
#     def __str__(self):
#         return f"Vente #{self.numero_vente or 'N/A'} - Client: {self.client.full_name if self.client else 'Inconnu'} - {self.created_at.strftime('%d/%m/%Y')}"

#     class Meta:
#         ordering = ['-created_at']
#         verbose_name = "Vente"
#         verbose_name_plural = "Ventes"

#     def generer_numero_vente(self):
#         now = timezone.now()
#         suffixe = ''.join(random.choices('0123456789', k=4))
#         return f"VENTE-{now.strftime('%m%d%Y%H%M%S')}-{suffixe}".upper()

#     @property
#     def produits(self):
#         return self.produits.all()

#     # Utile pour les formats lisibles dans l’admin, Swagger, ou les PDF
#     @property
#     def date_str(self):
#         return self.created_at.strftime('%d/%m/%Y à %H:%M')

#     def save(self, *args, **kwargs):
#         if not self.numero_vente:
#             for _ in range(10):
#                 numero = self.generer_numero_vente()
#                 if not Vente.objects.filter(numero_vente=numero).exists():
#                     self.numero_vente = numero
#                     break
#             else:
#                 raise ValueError("Impossible de générer un numéro de vente unique après 10 tentatives.")
#         super().save(*args, **kwargs)

#     def mettre_a_jour_montant_total(self, commit=True):
#         total = self.produits.aggregate(
#             total=models.Sum('sous_total_prix_vente_ht')
#         )['total'] or Decimal('0.00')
#         self.montant_total = total
#         if commit:
#             self.save(update_fields=['montant_total'])


class Vente(models.Model):
    numero_vente = models.CharField(max_length=30, unique=True, editable=False, blank=True, null=True)
    client = models.ForeignKey('sale.Client', on_delete=models.SET_NULL, null=True, blank=True, related_name="ventes")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="ventes_creees")
    created_at = models.DateTimeField(auto_now_add=True)
    montant_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), null=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Vente"
        verbose_name_plural = "Ventes"
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['numero_vente']),
        ]

    def __str__(self):
        nom_client = getattr(self.client, "full_name", None) or \
                    " ".join(x for x in [getattr(self.client, "prenom", None), getattr(self.client, "nom", None)] if x) or "Inconnu"
        date_txt = self.created_at.strftime('%d/%m/%Y') if self.created_at else ''
        return f"Vente #{self.numero_vente or 'N/A'} - Client: {nom_client} - {date_txt}"

    def generer_numero_vente(self) -> str:
        now = timezone.now()
        suffixe = ''.join(random.choices('0123456789', k=4))
        return f"VENTE-{now.strftime('%m%d%Y%H%M%S')}-{suffixe}".upper()

    def save(self, *args, **kwargs):
        if not self.numero_vente:
            for _ in range(10):
                self.numero_vente = self.generer_numero_vente()
                try:
                    with transaction.atomic():
                        super().save(*args, **kwargs)
                    break
                except IntegrityError:
                    self.numero_vente = None
            else:
                raise ValueError("Impossible de générer un numéro de vente unique après 10 tentatives.")
            return
        return super().save(*args, **kwargs)

    def mettre_a_jour_montant_total(self, commit: bool = True, base: str = "ttc"):
        """base='ttc' (recommandé) ou 'ht'."""
        from django.db.models import Sum
        champ = 'prix_ttc' if base == 'ttc' else 'sous_total_prix_vente_ht'
        total = self.produits.aggregate(t=Sum(champ))['t'] or Decimal('0.00')
        self.montant_total = total
        if commit:
            self.save(update_fields=['montant_total'])
        return total



# class Vente(models.Model):
#     # slug = models.CharField(max_length=50, unique=True)
#     numero_vente = models.CharField(max_length=25, unique=True, null=True, blank=True)
#     client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, related_name="ventes")
#     created_at = models.DateTimeField(auto_now_add=True)
#     montant_total = models.DecimalField(default=0.00, null=True, max_digits=12, decimal_places=2)

#     def save(self, *args, **kwargs):
#         if not self.slug:
#             # Générer un numéro de facture unique
#             # self.slug = str(uuid.uuid4().hex.upper()[:8])  # Par exemple, "9D6F7B9A"
#             self.slug = str(uuid.uuid4().hex.upper()[:9])  # Par exemple, "9D6F7B9A"
#         super(Vente, self).save(*args, **kwargs)

#     def __str__(self):
#         return f"Vente {self.id} - {self.client.nom}"


# VenteProduit (Product in Sale) Model
# class VenteProduit(models.Model):
#     vente = models.ForeignKey('Vente', on_delete=models.CASCADE, related_name="produits")
#     produit = models.ForeignKey(Produit, on_delete=models.SET_NULL, null=True, blank=True, related_name="venteProduit_produit")
#     vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name="venteproduits_vendor")

#     quantite = models.PositiveIntegerField(default=1)
#     prix_vente_grammes = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
#     sous_total_prix_vente_ht = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
#     tax = models.DecimalField(null=True, blank=True, default=0.00, decimal_places=2, max_digits=12)
#     prix_ttc = models.DecimalField(default=0.00, null=True, decimal_places=2, max_digits=12)
#     remise = models.DecimalField(default=0.00, decimal_places=2, max_digits=5, help_text="Discount", null=True, blank=True)
#     autres = models.DecimalField(default=0.00, decimal_places=2, max_digits=5, help_text="Additional info")
    
#     def save(self, *args, **kwargs):
#         prix_base = self.prix_vente_grammes * self.quantite
#         remise_valeur = self.remise or Decimal('0.00')     # remise en FCFA
#         autres_valeur = self.autres or Decimal('0.00')
#         tax = self.tax or Decimal('0.00')
#         self.sous_total_prix_vente_ht = prix_base - remise_valeur + autres_valeur
#         self.prix_ttc = self.sous_total_prix_vente_ht + tax

#         super().save(*args, **kwargs)

#         # Mise à jour du total de la vente liée
#         if self.vente_id:  # plus léger qu'un accès à self.vente
#             try:
#                 self.vente.mettre_a_jour_montant_total()
#             except Exception:
#                 pass

#     def __str__(self):
#         produit_nom = self.produit.nom if self.produit else "Produit supprimé"
#         vente_id = self.vente_id or "N/A"
#         return f"{self.quantite} x {produit_nom} in Vente {vente_id}"

#     def load_produit(self):
#         return self.produit

#     def load_client(self):
#         return self.vente.client if self.vente else None


# class VenteProduit(models.Model):
#     vente = models.ForeignKey('Vente', on_delete=models.CASCADE, related_name="produits")
#     produit = models.ForeignKey(Produit, on_delete=models.SET_NULL, null=True, blank=True,
#                                 related_name="venteProduit_produit")
#     vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True,
#                                related_name="venteproduits_vendor")

#     quantite = models.PositiveIntegerField(default=1)
#     prix_vente_grammes = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
#     sous_total_prix_vente_ht = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
#     tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), null=True, blank=True)
#     prix_ttc = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), null=True)
#     # Remise et autres = montants FCFA (pas %)
#     remise = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), null=True, blank=True, help_text="Discount (montant)")
#     autres = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), help_text="Additional info")

#     class Meta:
#         ordering = ['-id']
#         indexes = [
#             models.Index(fields=['vente']),
#             models.Index(fields=['vendor']),
#         ]
#         constraints = [
#             models.CheckConstraint(check=models.Q(quantite__gte=1), name='vente_produit_quantite_gte_1'),
#         ]

#     def clean(self):
#         for f in ('prix_vente_grammes', 'remise', 'autres', 'tax'):
#             val = getattr(self, f)
#             if val is not None and val < ZERO:
#                 from django.core.exceptions import ValidationError
#                 raise ValidationError({f: "Ne peut pas être négatif."})

#     def save(self, *args, **kwargs):
#         self.full_clean()

#         prix_base = (self.prix_vente_grammes or ZERO) * int(self.quantite or 0)
#         remise_val = self.remise or ZERO
#         autres_val = self.autres or ZERO
#         tax_val = self.tax or ZERO

#         ht = prix_base - remise_val + autres_val
#         if ht < ZERO:
#             ht = ZERO

#         self.sous_total_prix_vente_ht = ht.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
#         self.prix_ttc = (self.sous_total_prix_vente_ht + tax_val).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

#         super().save(*args, **kwargs)

#         if self.vente_id and hasattr(self.vente, "mettre_a_jour_montant_total"):
#             try:
#                 self.vente.mettre_a_jour_montant_total(base="ttc")
#             except Exception:
#                 pass


# class VenteProduit(models.Model):
#     # ⚑ Références explicites par "app_label.Model" → zéro conflit & pas de cycle d'import
#     vente   = models.ForeignKey('sale.Vente', on_delete=models.CASCADE, related_name="produits")
#     produit = models.ForeignKey('store.Produit', on_delete=models.SET_NULL, null=True, blank=True,
#                                 related_name="venteProduit_produit")
#     vendor  = models.ForeignKey('vendor.Vendor', on_delete=models.SET_NULL, null=True, blank=True,
#                                 related_name="venteproduits_vendor")

#     quantite = models.PositiveIntegerField(default=1)

#     # ⚑ Toujours des Decimal 'string' en default (évite les floats)
#     prix_vente_grammes       = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
#     sous_total_prix_vente_ht = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
#     tax                      = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'),
#                                                    null=True, blank=True)
#     prix_ttc                 = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'),
#                                                    null=True)
#     # Remise / autres = montants (FCFA), pas en %
#     remise = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), null=True, blank=True,
#                                  help_text="Discount (montant)")
#     autres = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'),
#                                  help_text="Additional info (montant)")

#     class Meta:
#         ordering = ['-id']
#         indexes = [
#             models.Index(fields=['vente']),
#             models.Index(fields=['vendor']),
#             models.Index(fields=['produit']),
#         ]
#         constraints = [
#             models.CheckConstraint(check=models.Q(quantite__gte=1), name='vente_produit_quantite_gte_1'),
#         ]

#     def clean(self):
#         for f in ('prix_vente_grammes', 'remise', 'autres', 'tax'):
#             v = getattr(self, f)
#             if v is not None and v < ZERO:
#                 raise ValidationError({f: "Ne peut pas être négatif."})

#     def save(self, *args, **kwargs):
#         # Validation/normalisation avant calcul
#         self.full_clean()

#         prix_base   = (self.prix_vente_grammes or ZERO) * int(self.quantite or 0)
#         remise_val  = self.remise or ZERO
#         autres_val  = self.autres or ZERO
#         tax_val     = self.tax or ZERO

#         ht = prix_base - remise_val + autres_val
#         if ht < ZERO:
#             ht = ZERO

#         self.sous_total_prix_vente_ht = ht.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
#         self.prix_ttc = (self.sous_total_prix_vente_ht + tax_val).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

#         super().save(*args, **kwargs)

#         # Mise à jour du total de la vente (base TTC)
#         if self.vente_id and hasattr(self.vente, "mettre_a_jour_montant_total"):
#             try:
#                 self.vente.mettre_a_jour_montant_total(base="ttc")
#             except Exception:
#                 pass

#     def __str__(self):
#         produit_nom = getattr(self.produit, "nom", None) or "Produit supprimé"
#         return f"{self.quantite} x {produit_nom} (Vente {self.vente_id or 'N/A'})"

#     def load_produit(self):
#         return self.produit

#     def load_client(self):
#         return self.vente.client if self.vente else None


# class VenteProduit(models.Model):
#     vente   = models.ForeignKey('sale.Vente', on_delete=models.CASCADE, related_name="produits")
#     produit = models.ForeignKey('store.Produit', on_delete=models.SET_NULL, null=True, blank=True,
#                                 related_name="venteProduit_produit")
#     vendor  = models.ForeignKey('vendor.Vendor', on_delete=models.SET_NULL, null=True, blank=True,
#                                 related_name="venteproduits_vendor")

#     quantite = models.PositiveIntegerField(default=1)
#     prix_vente_grammes       = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
#     sous_total_prix_vente_ht = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
#     tax                      = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'),
#                                                    null=True, blank=True)
#     prix_ttc                 = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'),
#                                                    null=True)
#     remise = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), null=True, blank=True,
#                                  help_text="Discount (montant)")
#     autres = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'),
#                                  help_text="Autres montants (emballage, etc.)")

#     # ...

#     def _resolve_unit_price(self) -> Decimal:
#         """
#         Retourne le prix unitaire (par gramme) à utiliser :
#         - si self.prix_vente_grammes > 0 → le prendre
#         - sinon fallback via MarquePurete(marque, purete) du produit
#         """
#         if self.prix_vente_grammes and self.prix_vente_grammes > ZERO:
#             return self.prix_vente_grammes

#         if not self.produit_id:
#             raise ValidationError({"produit": "Produit requis pour déterminer le prix."})

#         p = self.produit
#         if not getattr(p, "marque_id", None) or not getattr(p, "purete_id", None):
#             raise ValidationError({"prix_vente_grammes": "Produit sans (marque, purete) et aucun prix fourni."})

#         # Import tardif pour éviter les cycles
#         from django.apps import apps
#         MarquePurete = apps.get_model('store', 'MarquePurete')

#         mp_prix = (MarquePurete.objects
#                    .filter(marque_id=p.marque_id, purete_id=p.purete_id)
#                    .values_list('prix', flat=True)
#                    .first())
#         if mp_prix is None:
#             raise ValidationError({"prix_vente_grammes": "Tarif (marque, purete) introuvable pour ce produit."})

#         unit = Decimal(str(mp_prix))
#         if unit <= ZERO:
#             raise ValidationError({"prix_vente_grammes": "Tarif (marque, purete) non valide (<= 0)."})
#         return unit

#     def save(self, *args, **kwargs):
#         self.full_clean()

#         # ✅ prix_base = prix unitaire (payload OU MarquePurete) × quantité
#         unit_price = self._resolve_unit_price()
#         qte = int(self.quantite or 0)
#         prix_base = unit_price * qte

#         remise_val  = self.remise or ZERO     # montants FCFA
#         autres_val  = self.autres or ZERO
#         tax_val     = self.tax or ZERO

#         ht = prix_base - remise_val + autres_val
#         if ht < ZERO:
#             ht = ZERO

#         self.sous_total_prix_vente_ht = ht.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
#         self.prix_ttc = (self.sous_total_prix_vente_ht + tax_val).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

#         super().save(*args, **kwargs)

#         if self.vente_id and hasattr(self.vente, "mettre_a_jour_montant_total"):
#             try:
#                 self.vente.mettre_a_jour_montant_total(base="ttc")
#             except Exception:
#                 pass


class VenteProduit(models.Model):
    vente   = models.ForeignKey('sale.Vente', on_delete=models.CASCADE, related_name="produits")
    produit = models.ForeignKey('store.Produit', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="venteProduit_produit")
    vendor  = models.ForeignKey('vendor.Vendor', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="venteproduits_vendor")

    quantite = models.PositiveIntegerField(default=1)

    # 'prix_vente_grammes' = prix par gramme (saisi vendeur) OU fallback MarquePurete
    prix_vente_grammes       = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sous_total_prix_vente_ht = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax                      = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'),
                                                   null=True, blank=True)
    prix_ttc                 = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'),
                                                   null=True)
    # montants (FCFA)
    remise = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'),
                                 null=True, blank=True, help_text="Remise (montant FCFA)")
    autres = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'),
                                 help_text="Autres montants (emballage, etc.)")

    # ---------- helpers ----------
    def _resolve_unit_price(self) -> Decimal:
        """Prix par gramme: vendeur > 0 sinon tarif MarquePurete(marque, purete)."""
        if self.prix_vente_grammes and self.prix_vente_grammes > ZERO:
            return self.prix_vente_grammes

        if not self.produit_id:
            raise ValidationError({"produit": "Produit requis pour déterminer le prix."})

        p = self.produit
        if not getattr(p, "marque_id", None) or not getattr(p, "purete_id", None):
            raise ValidationError({"produit": "Produit sans (marque, purete) et aucun prix fourni."})

        from django.apps import apps
        MarquePurete = apps.get_model('store', 'MarquePurete')

        mp_val = (MarquePurete.objects
                  .filter(marque_id=p.marque_id, purete_id=p.purete_id)
                  .values_list('prix', flat=True).first())
        if mp_val is None:
            raise ValidationError({"produit": "Tarif (marque, purete) introuvable."})

        unit = Decimal(str(mp_val))
        if unit <= ZERO:
            raise ValidationError({"produit": "Tarif (marque, purete) non valide (<= 0)."})
        return unit

    def _get_product_weight(self) -> Decimal:
        """Poids du produit (grammes) — essaie p.poids puis p.poids_grammes."""
        if not self.produit_id:
            raise ValidationError({"produit": "Produit requis pour récupérer le poids."})
        p = self.produit
        raw = getattr(p, "poids", None)
        if raw in (None, "", 0, "0"):
            raw = getattr(p, "poids_grammes", None)
        if raw in (None, "", 0, "0"):
            raise ValidationError({"produit": "Le produit n'a pas de poids défini."})
        w = Decimal(str(raw))
        if w <= ZERO:
            raise ValidationError({"produit": "Poids produit invalide (<= 0)."})
        return w

    # ---------- validation ----------
    def clean(self):
        for f in ('prix_vente_grammes', 'remise', 'autres', 'tax'):
            v = getattr(self, f)
            if v is not None and v < ZERO:
                raise ValidationError({f: "Ne peut pas être négatif."})
        if self.quantite < 1:
            raise ValidationError({"quantite": "Doit être ≥ 1."})

    # ---------- calculs ----------
    def save(self, *args, **kwargs):
        self.full_clean()

        unit_price = self._resolve_unit_price()   # prix par gramme
        weight     = self._get_product_weight()   # poids du produit (g)
        qte        = int(self.quantite or 0)

        # ✅ Règle demandée : HT = prix_vente_grammes × poids × quantite
        base_ht = (unit_price * weight * qte)

        self.sous_total_prix_vente_ht = base_ht.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        remise_v = (self.remise or ZERO)
        autres_v = (self.autres or ZERO)
        tax_v    = (self.tax or ZERO)

        ttc = self.sous_total_prix_vente_ht - remise_v + autres_v + tax_v
        if ttc < ZERO:
            ttc = ZERO
        self.prix_ttc = ttc.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        super().save(*args, **kwargs)

        if self.vente_id and hasattr(self.vente, "mettre_a_jour_montant_total"):
            try:
                self.vente.mettre_a_jour_montant_total(base="ttc")
            except Exception:
                pass

# Facture (Invoice) Model
# class Facture(models.Model):
    
#     TYPES_FACTURE = (
#         ('vente_directe', 'Vente directe'),
#         ('acompte', 'Facture d’acompte'),
#         ('finale', 'Facture finale')
#     )
#     STATUS = (
#         ('non_payé', 'Non Payé'),
#         ('payé', 'Non Payé'),
#     )
#     numero_facture = models.CharField(max_length=20, unique=True, editable=False)
#     vente = models.OneToOneField('Vente', on_delete=models.SET_NULL, null=True, blank=True, related_name="facture_vente")
#     date_creation = models.DateTimeField(auto_now_add=True)
#     montant_total = models.DecimalField(default=0.00, null=True, decimal_places=2, max_digits=12)
#     status = models.CharField(max_length=20, choices=STATUS, default='non_payé')
#     fichier_pdf = models.FileField(upload_to='factures/', null=True, blank=True)
#     type_facture = models.CharField(max_length=20, choices=TYPES_FACTURE, default='vente_directe')

#     class Meta:
#         ordering = ['-id']
#         verbose_name_plural = "Factures"

#     def __str__(self):
#         return f'{self.numero_facture}'

#     @staticmethod
#     def generer_numero_unique():
#         for _ in range(10):
#             now = timezone.now()
#             suffixe = ''.join(random.choices(string.digits, k=4))
#             numero = f"FAC-{now.strftime('%m%d%Y')}-{suffixe}"
#             if not Facture.objects.filter(numero_facture=numero).exists():
#                 return numero
#         raise Exception("Impossible de générer un numéro de facture unique après 10 tentatives.")

#     def save(self, *args, **kwargs):
#         if not self.numero_facture:
#             self.numero_facture = self.generer_numero_unique()
#         super().save(*args, **kwargs)

#     # def save(self, *args, **kwargs):
#     #     if not self.numero_facture:
#     #         for _ in range(10):
#     #             numero = self.generer_numero_facture()
#     #             if not Facture.objects.filter(numero_facture=numero).exists():
#     #                 self.numero_facture = numero
#     #                 break
#     #         else:
#     #             raise Exception("Impossible de générer un numéro de facture unique après 10 tentatives.")
#     #     super().save(*args, **kwargs)

#     @property
#     def total_paye(self):
#         return self.paiements.aggregate(
#             total=models.Sum('montant_paye')
#         )['total'] or Decimal('0.00')

#     @property
#     def reste_a_payer(self):
#         return max(self.montant_total - self.total_paye, Decimal('0.00'))

#     def est_reglee(self):
#         return self.status == "Payé"
#     est_reglee.boolean = True
#     est_reglee.short_description = "Facture réglée"


class Facture(models.Model):
    # Valeurs "machine" sans accent/espaces, libellés humains avec accents
    TYPE_VENTE_DIRECTE = "vente_directe"
    TYPE_ACOMPTE = "acompte"
    TYPE_FINALE = "finale"

    STAT_NON_PAYE = "non_paye"
    STAT_PAYE = "paye"

    TYPES_FACTURE = (
        (TYPE_VENTE_DIRECTE, "Vente directe"),
        (TYPE_ACOMPTE, "Facture d’acompte"),
        (TYPE_FINALE, "Facture finale"),
    )
    STATUS = (
        (STAT_NON_PAYE, "Non payé"),
        (STAT_PAYE, "Payé"),
    )

    numero_facture = models.CharField(max_length=20, unique=True, editable=False)
    vente = models.OneToOneField(
        "Vente",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="facture_vente",
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    montant_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), null=False)
    status = models.CharField(max_length=20, choices=STATUS, default=STAT_NON_PAYE)
    fichier_pdf = models.FileField(upload_to="factures/", null=True, blank=True)
    type_facture = models.CharField(max_length=20, choices=TYPES_FACTURE, default=TYPE_VENTE_DIRECTE)

    class Meta:
        ordering = ["-id"]
        verbose_name_plural = "Factures"
        indexes = [
            models.Index(fields=["numero_facture"]),
            models.Index(fields=["date_creation"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            # Empêche les montants négatifs
            CheckConstraint(check=Q(montant_total__gte=0), name="facture_montant_total_gte_0"),
        ]

    def __str__(self):
        return self.numero_facture

    @staticmethod
    def generer_numero_unique():
        """
        Génère un numéro FAC-mmddYYYY-XXXX en essayant jusqu’à 10 fois.
        Confiance sur la contrainte unique + retry si collision.
        """
        for _ in range(10):
            now = timezone.now()
            suffixe = "".join(random.choices(string.digits, k=4))
            numero = f"FAC-{now.strftime('%m%d%Y')}-{suffixe}"
            if not Facture.objects.filter(numero_facture=numero).exists():
                return numero
        raise RuntimeError("Impossible de générer un numéro de facture unique après 10 tentatives.")

    def save(self, *args, **kwargs):
        if not self.numero_facture:
            self.numero_facture = self.generer_numero_unique()
        super().save(*args, **kwargs)

    @property
    def total_paye(self) -> Decimal:
        # agrège en base pour éviter les incohérences
        return self.paiements.aggregate(total=Sum("montant_paye"))["total"] or Decimal("0.00")

    @property
    def reste_a_payer(self) -> Decimal:
        # borne à 0 pour éviter les négatifs (arrondis etc.)
        return max((self.montant_total or Decimal("0.00")) - self.total_paye, Decimal("0.00"))

    def est_reglee(self) -> bool:
        return self.status == self.STAT_PAYE

    est_reglee.boolean = True
    est_reglee.short_description = "Facture réglée"


# class Facture(models.Model):
#     numero_facture = models.CharField(max_length=20, unique=True, editable=False)
#     vente = models.OneToOneField(Vente, on_delete=models.SET_NULL, null=True, blank=True, related_name="facture_vente")
#     date_creation = models.DateTimeField(auto_now_add=True)
#     montant_total = models.DecimalField(default=0.00, null=True, decimal_places=2, max_digits=12)
#     # facture_status = models.CharField(default="en attente", max_length=20)
#     status = models.CharField(max_length=20, choices=[('Non Payé', 'Nom Payé'), ('Payé', 'Payé')], default='Nom Payé')
#     fichier_pdf = models.FileField(upload_to='factures/', null=True, blank=True)

#     # categorie = models.ForeignKey(Categorie, on_delete=models.SET_NULL, null=True, blank=True, related_name="sale_categorie")
#     # marque = models.ForeignKey(Marque, on_delete=models.SET_NULL, null=True, blank=True, related_name="sale_marque")
#     # modele = models.ForeignKey(Modele, on_delete=models.SET_NULL, null=True, blank=True, related_name="sale_modele")
#     # purete = models.ForeignKey(Purete, on_delete=models.SET_NULL, null=True, blank=True, related_name="sale_purete")


#     # def generate_facture_numero(self):
#     #     # Ajouter la date du jour au format YYYYMM
#     #     date_str = self.date_creation.strftime('%Y%m')
#     #     random_digits = ''.join(random.choices(string.digits, k=7))  # Générer è chiffres aléatoires
#     #     numero = f"FAC-{date_str}-{random_digits}"
#     #     return numero

#     # def save(self, *args, **kwargs):
#     #     self.numero = self.generate_facture_numero()
#     #     super(Facture, self).save(*args, **kwargs)


#     # def generer_numero_facture(self):
#     #     # Format de la date : YYYYMMDD
#     #     date_part = timezone.now().strftime('%d-%m-%Y')
#     #     date_part_heure = timezone.now().strftime('%H:%M:%S')

#     #     # # Trouver le dernier numéro de facture pour aujourd'hui
#     #     # last_facture = Facture.objects.filter(date_creation__date=timezone.now().date()).order_by('-id').first()
#     #     # if last_facture:
#     #     #     # Si des factures existent déjà aujourd'hui, incrémenter le numéro
#     #     #     last_num = int(last_facture.numero_facture.split('-')[-1])
#     #     #     new_num = last_num + 1
#     #     # else:
#     #     #     # Sinon commencer à 1
#     #     #     new_num = 1

#     #     new_num_chaine = ''.join(random.choices(string.digits, k=7))  # Générer è chiffres aléatoires
#     #     new_num = int(new_num_chaine)
#     #     # print(date_part_heure)

#     #     # Format final : FAC-YYYYMMDD-XXXX
#     #     # return f"FAC-{date_part}-{new_num:04d}"
#     #     # return f"FAC-{date_part}-{new_num}"
#     #     return f"FAC-{new_num}"

#     def generer_numero_facture(self):
#         # Format de la date (séparé)
#         jour = timezone.now().strftime('%d')
#         mois = timezone.now().strftime('%m')
#         annee = timezone.now().strftime('%Y')

#         # Générer 5 à 7 chiffres aléatoires
#         suffixe = ''.join(random.choices(string.digits, k=5))  # ou 7 si tu veux plus long

#         # Format final : FAC-MMDDYYYY-12345
#         return f"FAC-{mois}{jour}{annee}-{suffixe}"

#     def save(self, *args, **kwargs):
#     if not self.numero_facture:
#         for _ in range(10):  # On essaie 10 fois
#             numero = self.generer_numero_facture()
#             if not Facture.objects.filter(numero_facture=numero).exists():
#                 self.numero_facture = numero
#                 break
#         else:
#             raise Exception("Impossible de générer un numéro de facture unique après 10 tentatives.")

#     super(Facture, self).save(*args, **kwargs)

#     # def save(self, *args, **kwargs):
#     #     if not self.numero_facture:
#     #         while True:
#     #             numero = self.generer_numero_facture()
#     #             if not Facture.objects.filter(numero_facture=numero).exists():
#     #                 self.numero_facture = numero
#     #                 break
#     #     super(Facture, self).save(*args, **kwargs)


#     def __str__(self):
#         return f'{self.numero_facture}'

#     class Meta:
#         ordering = ['-id']
#         verbose_name_plural = "Factures"


# class Paiement(models.Model):
#     facture = models.ForeignKey('Facture', on_delete=models.CASCADE, related_name="paiements")
#     montant_paye = models.DecimalField(max_digits=10, decimal_places=2)
#     mode_paiement = models.CharField(max_length=20, choices=[('cash', 'Cash'), ('mobile', 'Mobile')])
#     date_paiement = models.DateTimeField(auto_now_add=True)
#     cashier = models.ForeignKey('vendor.Cashier', null=True, blank=True, on_delete=models.SET_NULL, related_name='paiements')
#     created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="paiements_validation")

#     def __str__(self):
#         facture_num = self.facture.numero_facture if self.facture else "Aucune facture"
#         return f'Paiement de {self.montant_paye} FCFA - {facture_num}'

#     def clean(self):
#         if self.cashier and self.created_by and self.cashier.user_id != self.created_by_id:
#             raise ValidationError("created_by doit correspondre au user du cashier.")
        
#     class Meta:
#         ordering = ['-date_paiement']
#         verbose_name = "Paiement"
#         verbose_name_plural = "Paiements"
#         indexes = [
#             models.Index(fields=['date_paiement']),
#             models.Index(fields=['created_by']),
#             models.Index(fields=['cashier']),
#         ]
#         # CheckConstraint côté DB (empêche montants ≤ 0)
#         constraints = [
#             CheckConstraint(check=Q(montant_paye__gt=0), name="paiement_montant_gt_0"),
#         ]
    
#     def save(self, *args, **kwargs):
#         if not self.cashier and self.created_by_id:
#             from vendor.models import Cashier
#             self.cashier = Cashier.objects.filter(user_id=self.created_by_id).first()
#         super().save(*args, **kwargs)
    
#     def est_reglee(self):
#         return self.facture.status == "Payé"
#     est_reglee.boolean = True
#     est_reglee.short_description = "Facture réglée"


class Paiement(models.Model):
    MODE_CASH = "cash"
    MODE_MOBILE = "mobile"
    MODES = (
        (MODE_CASH, "Cash"),
        (MODE_MOBILE, "Mobile"),
    )

    facture = models.ForeignKey(
        "Facture", on_delete=models.CASCADE, related_name="paiements"
    )
    montant_paye = models.DecimalField(max_digits=10, decimal_places=2)
    mode_paiement = models.CharField(max_length=20, choices=MODES)
    date_paiement = models.DateTimeField(auto_now_add=True)
    cashier = models.ForeignKey(
        "vendor.Cashier", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="paiements"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="paiements_validation"
    )

    def __str__(self):
        facture_num = self.facture.numero_facture if self.facture else "Aucune facture"
        return f"Paiement de {self.montant_paye} FCFA - {facture_num}"

    def clean(self):
        super().clean()
        if self.cashier and self.created_by and self.cashier.user_id != self.created_by_id:
            raise ValidationError("created_by doit correspondre au user du cashier.")
        if not self.facture_id:
            raise ValidationError("La facture est requise.")

    class Meta:
        ordering = ["-date_paiement"]
        verbose_name = "Paiement"
        verbose_name_plural = "Paiements"
        indexes = [
            models.Index(fields=["date_paiement"]),
            models.Index(fields=["created_by"]),
            models.Index(fields=["cashier"]),
            models.Index(fields=["facture", "date_paiement"]),  # 👈 utile en pratique
        ]
        constraints = [
            CheckConstraint(check=Q(montant_paye__gt=0), name="paiement_montant_gt_0"),
        ]

    def save(self, *args, **kwargs):
        # Auto-renseigne le cashier si absent mais created_by présent
        if not self.cashier and self.created_by_id:
            from vendor.models import Cashier
            self.cashier = Cashier.objects.filter(user_id=self.created_by_id).first()

        # Valide règles applicatives (inclut clean())
        self.full_clean()

        # Si tu veux verrouiller en écriture dans un service/vu, fais-le là-bas.
        # Ici on reste neutre : save simple.
        super().save(*args, **kwargs)

    def est_reglee(self):
        # Utilise la constante si définie dans Facture, sinon garde "Payé"
        try:
            from .models import Facture  # même app
            return self.facture.status == getattr(Facture, "STAT_PAYE", "Payé")
        except Exception:
            return self.facture.status == "Payé"

    est_reglee.boolean = True
    est_reglee.short_description = "Facture réglée"


# class Paiement(models.Model):
#     facture = models.OneToOneField(Facture, on_delete=models.SET_NULL, null=True, blank=True, related_name="paiement_facture")
#     montant_paye = models.DecimalField(default=0.00, null=True, max_digits=10, decimal_places=2)
#     date_paiement = models.DateTimeField(auto_now_add=True)
#     # mode_paiement = models.CharField(max_length=50)

#     def __str__(self):
#         return f'{self.facture.numero_facture}'

#     class Meta:
#         ordering = ['-id']
#         verbose_name_plural = "Paiements"