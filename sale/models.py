import random
import string
import uuid
from django.db.models import Sum
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.conf import settings
from store.models import Categorie, Marque, Modele, Produit, Purete
from vendor.models import Vendor

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
class Vente(models.Model):
    numero_vente = models.CharField(max_length=30, unique=True, editable=False, blank=True, null=True)
    client = models.ForeignKey('sale.Client', on_delete=models.SET_NULL, null=True, blank=True, related_name="ventes")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="ventes_creees")
    created_at = models.DateTimeField(auto_now_add=True)
    montant_total = models.DecimalField(default=0.00, null=True, max_digits=12, decimal_places=2)
    # (champ optionnel)
    # explication
    # Vente directe -> Le client achète directement -> la commande_source est null
    # Vente issue d’une commande -> La commande est validée → vente -> commande
    # Avantages
    # Tu peux gérer les deux cas (avec ou sans commande) facilement.
    # Tu peux suivre le cycle : commande → vente, ou vente directe.
    # Tu peux afficher l’historique du client complet : ventes + commandes.
    commande_source = models.ForeignKey('order.CommandeClient', on_delete=models.SET_NULL, null=True, blank=True,related_name='commend_en_ventes')
    
    def __str__(self):
        return f"Vente #{self.numero_vente or 'N/A'} - Client: {self.client.full_name if self.client else 'Inconnu'} - {self.created_at.strftime('%d/%m/%Y')}"

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Vente"
        verbose_name_plural = "Ventes"

    def generer_numero_vente(self):
        now = timezone.now()
        suffixe = ''.join(random.choices('0123456789', k=4))
        return f"VENTE-{now.strftime('%m%d%Y%H%M%S')}-{suffixe}".upper()

    @property
    def produits(self):
        return self.produits.all()

    # Utile pour les formats lisibles dans l’admin, Swagger, ou les PDF
    @property
    def date_str(self):
        return self.created_at.strftime('%d/%m/%Y à %H:%M')

    def save(self, *args, **kwargs):
        if not self.numero_vente:
            for _ in range(10):
                numero = self.generer_numero_vente()
                if not Vente.objects.filter(numero_vente=numero).exists():
                    self.numero_vente = numero
                    break
            else:
                raise ValueError("Impossible de générer un numéro de vente unique après 10 tentatives.")
        super().save(*args, **kwargs)

    def mettre_a_jour_montant_total(self, commit=True):
        total = self.produits.aggregate(
            total=models.Sum('sous_total_prix_vente_ht')
        )['total'] or Decimal('0.00')
        self.montant_total = total
        if commit:
            self.save(update_fields=['montant_total'])



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
class VenteProduit(models.Model):
    vente = models.ForeignKey('Vente', on_delete=models.CASCADE, related_name="produits")
    produit = models.ForeignKey(Produit, on_delete=models.SET_NULL, null=True, blank=True, related_name="venteProduit_produit")
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name="venteproduits_vendor")

    quantite = models.PositiveIntegerField(default=1)
    prix_vente_grammes = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
    sous_total_prix_vente_ht = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
    tax = models.DecimalField(null=True, blank=True, default=0.00, decimal_places=2, max_digits=12)
    prix_ttc = models.DecimalField(default=0.00, null=True, decimal_places=2, max_digits=12)
    remise = models.DecimalField(default=0.00, decimal_places=2, max_digits=5, help_text="Discount", null=True, blank=True)
    autres = models.DecimalField(default=0.00, decimal_places=2, max_digits=5, help_text="Additional info")
    
    def save(self, *args, **kwargs):
        prix_base = self.prix_vente_grammes * self.quantite
        remise_valeur = self.remise or Decimal('0.00')     # remise en FCFA
        autres_valeur = self.autres or Decimal('0.00')
        tax = self.tax or Decimal('0.00')
        self.sous_total_prix_vente_ht = prix_base - remise_valeur + autres_valeur
        self.prix_ttc = self.sous_total_prix_vente_ht + tax

        super().save(*args, **kwargs)

        # Mise à jour du total de la vente liée
        if self.vente_id:  # plus léger qu'un accès à self.vente
            try:
                self.vente.mettre_a_jour_montant_total()
            except Exception:
                pass

    def __str__(self):
        produit_nom = self.produit.nom if self.produit else "Produit supprimé"
        vente_id = self.vente_id or "N/A"
        return f"{self.quantite} x {produit_nom} in Vente {vente_id}"

    def load_produit(self):
        return self.produit

    def load_client(self):
        return self.vente.client if self.vente else None



# class VenteProduit(models.Model):
#     vente = models.ForeignKey(Vente, on_delete=models.SET_NULL, null=True, blank=True, related_name="produits")
#     produit = models.ForeignKey(Produit, on_delete=models.SET_NULL, null=True, blank=True, related_name="venteProduit_produit")
#     quantite = models.IntegerField()
#     prix_vente_grammes = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
#     # prix_vente_reel_gramme = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
#     sous_total_prix_vent = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
#     tax = models.IntegerField(null=True, blank=True)
#     tax_inclue = models.DecimalField(default=0.00, null=True, decimal_places=2, max_digits=12)
#     # total_prix_vente = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)

#     def __str__(self):
#         return f"{self.quantite} x {self.produit.nom} in Vente {self.vente.id}"

#     # def save(self, *args, **kwargs):
#     #     self.sous_total_prix_vent = self.produit.prix_vente * self.quantite
#     #     super().save(*args, **kwargs)

#     def load_client(self):
#         return self.client

#     def load_produit(self):
#         return self.produit

# Facture (Invoice) Model
class Facture(models.Model):
    numero_facture = models.CharField(max_length=20, unique=True, editable=False)
    vente = models.OneToOneField('Vente', on_delete=models.SET_NULL, null=True, blank=True, related_name="facture_vente")
    date_creation = models.DateTimeField(auto_now_add=True)
    montant_total = models.DecimalField(default=0.00, null=True, decimal_places=2, max_digits=12)
    status = models.CharField(max_length=20, choices=[('Non Payé', 'Non Payé'), ('Payé', 'Payé')], default='Non Payé')
    fichier_pdf = models.FileField(upload_to='factures/', null=True, blank=True)

    class Meta:
        ordering = ['-id']
        verbose_name_plural = "Factures"

    def __str__(self):
        return f'{self.numero_facture}'

    @staticmethod
    def generer_numero_unique():
        for _ in range(10):
            now = timezone.now()
            suffixe = ''.join(random.choices(string.digits, k=4))
            numero = f"FAC-{now.strftime('%m%d%Y')}-{suffixe}"
            if not Facture.objects.filter(numero_facture=numero).exists():
                return numero
        raise Exception("Impossible de générer un numéro de facture unique après 10 tentatives.")

    def save(self, *args, **kwargs):
        if not self.numero_facture:
            self.numero_facture = self.generer_numero_unique()
        super().save(*args, **kwargs)

    # def save(self, *args, **kwargs):
    #     if not self.numero_facture:
    #         for _ in range(10):
    #             numero = self.generer_numero_facture()
    #             if not Facture.objects.filter(numero_facture=numero).exists():
    #                 self.numero_facture = numero
    #                 break
    #         else:
    #             raise Exception("Impossible de générer un numéro de facture unique après 10 tentatives.")
    #     super().save(*args, **kwargs)

    @property
    def total_paye(self):
        return self.paiements.aggregate(
            total=models.Sum('montant_paye')
        )['total'] or Decimal('0.00')

    @property
    def reste_a_payer(self):
        return max(self.montant_total - self.total_paye, Decimal('0.00'))

    def est_reglee(self):
        return self.status == "Payé"
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


class Paiement(models.Model):
    facture = models.ForeignKey('Facture', on_delete=models.CASCADE, related_name="paiements")
    montant_paye = models.DecimalField(max_digits=10, decimal_places=2)
    mode_paiement = models.CharField(max_length=20, choices=[('cash', 'Cash'), ('mobile', 'Mobile')])
    date_paiement = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="paiements_validation")

    def __str__(self):
        facture_num = self.facture.numero_facture if self.facture else "Aucune facture"
        return f'Paiement de {self.montant_paye} FCFA - {facture_num}'

    class Meta:
        ordering = ['-date_paiement']
        verbose_name = "Paiement"
        verbose_name_plural = "Paiements"

    def est_reglee(self):
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