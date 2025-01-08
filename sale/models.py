import random
import string
import uuid

from django.db import models
from django.utils import timezone

from store.models import Categorie, Marque, Modele, Produit, Purete


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



# Vente (Sale) Model
class Vente(models.Model):
    slug = models.CharField(max_length=50, unique=True)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, related_name="ventes")
    created_at = models.DateTimeField(auto_now_add=True)
    montant_total = models.DecimalField(default=0.00, null=True, max_digits=12, decimal_places=2)

    def save(self, *args, **kwargs):
        if not self.slug:
            # Générer un numéro de facture unique
            # self.slug = str(uuid.uuid4().hex.upper()[:8])  # Par exemple, "9D6F7B9A"
            self.slug = str(uuid.uuid4().hex.upper()[:9])  # Par exemple, "9D6F7B9A"
        super(Vente, self).save(*args, **kwargs)

    def __str__(self):
        return f"Vente {self.id} - {self.client.nom}"


# VenteProduit (Product in Sale) Model
class VenteProduit(models.Model):
    vente = models.ForeignKey(Vente, on_delete=models.SET_NULL, null=True, blank=True, related_name="produits")
    produit = models.ForeignKey(Produit, on_delete=models.SET_NULL, null=True, blank=True, related_name="venteProduit_produit")
    quantite = models.IntegerField()
    prix_vente_grammes = models.DecimalField(default=0.00, decimal_places=2, max_digits=12) 
    # prix_vente_reel_gramme = models.DecimalField(default=0.00, decimal_places=2, max_digits=12) 
    sous_total_prix_vent = models.DecimalField(default=0.00, decimal_places=2, max_digits=12) 
    tax = models.IntegerField(null=True, blank=True)
    tax_inclue = models.DecimalField(default=0.00, null=True, decimal_places=2, max_digits=12) 
    # total_prix_vente = models.DecimalField(default=0.00, decimal_places=2, max_digits=12)
        
    def __str__(self):
        return f"{self.quantite} x {self.produit.nom} in Vente {self.vente.id}"
    
    # def save(self, *args, **kwargs):
    #     self.sous_total_prix_vent = self.produit.prix_vente * self.quantite
    #     super().save(*args, **kwargs)
    
    def load_client(self):
        return self.client
    
    def load_produit(self):
        return self.produit

# Facture (Invoice) Model
class Facture(models.Model):
    numero_facture = models.CharField(max_length=20, unique=True, editable=False)
    vente = models.OneToOneField(Vente, on_delete=models.SET_NULL, null=True, blank=True, related_name="facture_vente")
    date_creation = models.DateTimeField(auto_now_add=True)
    montant_total = models.DecimalField(default=0.00, null=True, decimal_places=2, max_digits=12)
    # facture_status = models.CharField(default="en attente", max_length=20)
    status = models.CharField(max_length=20, choices=[('En attente', 'En attente'), ('Payé', 'Payé')], default='En attente')

    # categorie = models.ForeignKey(Categorie, on_delete=models.SET_NULL, null=True, blank=True, related_name="sale_categorie")
    # marque = models.ForeignKey(Marque, on_delete=models.SET_NULL, null=True, blank=True, related_name="sale_marque")
    # modele = models.ForeignKey(Modele, on_delete=models.SET_NULL, null=True, blank=True, related_name="sale_modele")
    # purete = models.ForeignKey(Purete, on_delete=models.SET_NULL, null=True, blank=True, related_name="sale_purete")


    # def generate_facture_numero(self):
    #     # Ajouter la date du jour au format YYYYMM
    #     date_str = self.date_creation.strftime('%Y%m')
    #     random_digits = ''.join(random.choices(string.digits, k=7))  # Générer è chiffres aléatoires
    #     numero = f"FAC-{date_str}-{random_digits}"
    #     return numero
    
    # def save(self, *args, **kwargs):
    #     self.numero = self.generate_facture_numero()
    #     super(Facture, self).save(*args, **kwargs)
    
    def save(self, *args, **kwargs):
        if not self.numero_facture:
            self.numero_facture = self.generer_numero_facture()
        super().save(*args, **kwargs)

    def generer_numero_facture(self):
        # Format de la date : YYYYMMDD
        date_part = timezone.now().strftime('%d-%m-%Y')
        date_part_heure = timezone.now().strftime('%H:%M:%S')

        # # Trouver le dernier numéro de facture pour aujourd'hui
        # last_facture = Facture.objects.filter(date_creation__date=timezone.now().date()).order_by('-id').first()
        # if last_facture:
        #     # Si des factures existent déjà aujourd'hui, incrémenter le numéro
        #     last_num = int(last_facture.numero_facture.split('-')[-1])
        #     new_num = last_num + 1
        # else:
        #     # Sinon commencer à 1
        #     new_num = 1
        
        new_num_chaine = ''.join(random.choices(string.digits, k=7))  # Générer è chiffres aléatoires
        new_num = int(new_num_chaine)
        # print(date_part_heure)

        # Format final : FAC-YYYYMMDD-XXXX
        # return f"FAC-{date_part}-{new_num:04d}"
        # return f"FAC-{date_part}-{new_num}"
        return f"FAC-{new_num}"
    
    
    def __str__(self):
        return f'{self.numero_facture}'
    
    class Meta:
        ordering = ['-id']
        verbose_name_plural = "Factures"


class Paiement(models.Model):
    facture = models.OneToOneField(Facture, on_delete=models.SET_NULL, null=True, blank=True, related_name="paiement_facture")
    montant_paye = models.DecimalField(default=0.00, null=True, max_digits=10, decimal_places=2)
    date_paiement = models.DateTimeField(auto_now_add=True)
    # mode_paiement = models.CharField(max_length=50)
    
    def __str__(self):
        return f'{self.facture.numero_facture}'
    
    class Meta:
        ordering = ['-id']
        verbose_name_plural = "Paiements" 