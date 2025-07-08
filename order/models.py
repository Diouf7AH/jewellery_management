from django.db import models
import uuid
from django.utils import timezone
from django.conf import settings
from store.models import Produit
from django.core.exceptions import ValidationError
from decimal import Decimal
from store.models import get_default_purete

MATIERE = (
    ("or", "Or"),
    ("argent", "Argent"),
    ("mixte", "Mixte")
)

GENRE = (
    ("H", "Homme"),
    ("F", "Femme"),
    ("E", "Enfant")
)
# prise de commande en boutique

# Create your models here.
class CommandeClient(models.Model):
    STATUT_EN_ATTENTE_ACOMPTE = 'en_attente_acompte'
    STATUT_EN_ATTENTE = 'en_attente'
    STATUT_PAYEE = 'payee'

    STATUT_CHOICES = [
        (STATUT_EN_ATTENTE_ACOMPTE, "En attente d'acompte"),
        (STATUT_EN_ATTENTE, "En attente"),
        (STATUT_PAYEE, "Payée"),
    ]
    numero_commande = models.CharField(max_length=30, unique=True, editable=False)
    client = models.ForeignKey('sale.Client', on_delete=models.SET_NULL, null=True, related_name="commandes_client")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    statut = models.CharField(max_length=30, choices=STATUT_CHOICES, default=STATUT_EN_ATTENTE_ACOMPTE)
    date_commande = models.DateTimeField(auto_now_add=True)
    commentaire = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='orders/client', default="order-client.jpg", null=True, blank=True)


    def save(self, *args, **kwargs):
        if not self.numero_commande:
            self.numero_commande = self.generer_numero_commande()
        super().save(*args, **kwargs)

    def generer_numero_commande(self):
        date_str = timezone.now().strftime('%Y%m%d')
        prefix = f"COM-{date_str}-"

        while True:
            suffix = uuid.uuid4().hex[:4].upper()  # Ex: 'A1B2'
            numero = f"{prefix}{suffix}"
            if not CommandeClient.objects.filter(numero_commande=numero).exists():
                return numero

    @property
    def montant_total(self):
        total = self.commandes_produits_client.aggregate(
            total=models.Sum('sous_total')
        )['total'] or Decimal('0.00')
        return total

    class Meta:
        indexes = [
            models.Index(fields=['date_commande']),
            models.Index(fields=['statut']),
        ]

    def __str__(self):
        client_nom = f"{self.client.prenom} {self.client.nom}" if self.client else "Client inconnu"
        return f"{self.numero_commande} - {client_nom}"
# Avantages de cette méthode
# Tu peux gérer les produits officiels et les personnalisés
# Pas de casse si le Produit est supprimé (car SET_NULL)
# Tu peux migrer un produit_libre vers un vrai Produit plus tard
# class CommandeProduitClient(models.Model):
#     commande_client = models.ForeignKey(CommandeClient, on_delete=models.CASCADE, related_name='produits')
#     produit = models.ForeignKey(Produit, on_delete=models.SET_NULL, null=True, blank=True)
#     produit_libre = models.CharField(max_length=255, blank=True, null=True)

#     quantite = models.PositiveIntegerField()
#     prix_prevue = models.DecimalField(max_digits=10, decimal_places=2)
#     sous_total = models.DecimalField(max_digits=12, decimal_places=2, editable=False)

#     # Si tu veux réactiver les "autres frais", décommente ici :
#     # autres = models.DecimalField(max_digits=10, decimal_places=2, default=0)

#     def clean(self):
#         if not self.produit and not self.produit_libre:
#             raise ValidationError("Vous devez soit sélectionner un produit existant, soit entrer un produit libre.")
#         if self.produit_libre and not self.prix_prevue:
#             raise ValidationError("Veuillez spécifier un prix pour le produit libre.")

#     def calculer_sous_total(self):
#         if self.produit:
#             # prix_prevue = self.produit.poids * self.produit.marque.prix
#             prix_prevue = (self.produit.poids or 0) * (self.produit.marque.prix or 0)
#             total =  prix_prevue * self.nquantite
#         else:
#             total = self.quantite * self.prix_prevue


#         # Si tu veux réactiver "autres", ajoute :
#         # total += self.autres

#         return total

# Avantages de cette méthode
# Tu peux gérer les produits officiels et les personnalisés
# Pas de casse si le Produit est supprimé (car SET_NULL)
# Tu peux migrer un produit_libre vers un vrai Produit plus tard
class CommandeProduitClient(models.Model):
    commande_client = models.ForeignKey(CommandeClient, on_delete=models.CASCADE, related_name='commandes_produits_client')
    produit = models.CharField(max_length=255, blank=True, null=True)
    categorie = models.ForeignKey('store.Categorie', on_delete=models.SET_NULL, null=True, blank=True)
    marque = models.ForeignKey('store.Marque', on_delete=models.SET_NULL, null=True, blank=True)
    modele = models.ForeignKey('store.Modele', on_delete=models.SET_NULL, null=True, blank=True)
    genre = models.CharField(choices=GENRE, default="F", max_length=2, blank=True, null=True)
    taille = models.CharField(max_length=7, blank=True, null=True)
    matiere = models.CharField(choices=MATIERE, max_length=50, default="or", null=True, blank=True)
    poids = models.DecimalField(max_digits=6, decimal_places=2)
    purete = models.ForeignKey('store.Purete', on_delete=models.SET_NULL, null=True, blank=True, related_name="commande_produits_purete", default=get_default_purete)
    prix_gramme = models.DecimalField(max_digits=12,decimal_places=2, default=0.00, null=False, blank=False)
    personnalise = models.BooleanField(default=False, help_text="Cochez si ce produit est personnalisé (et non un produit officiel)")
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)

    # Quantité et prix
    quantite = models.PositiveIntegerField()
    prix_prevue = models.DecimalField(max_digits=10, decimal_places=2)
    sous_total = models.DecimalField(max_digits=12, decimal_places=2, editable=False)

    def calculer_prix_prevue(self):
        return self.poids * self.prix_gramme
    
    def calculer_sous_total(self):
        return self.quantite * self.prix_prevue
    
    def clean(self):
        super().clean()

        if self.poids is None:
            raise ValidationError("Le poids ne peut pas être vide.")
        
        if self.prix_gramme is None:
            raise ValidationError("Le prix par gramme ne peut pas être vide.")
        
        if self.prix_gramme < 0:
            raise ValidationError("Le prix par gramme ne peut pas être négatif.")
        
        if self.prix_prevue is None:
            raise ValidationError("Le prix prévu ne peut pas être vide.")

    def save(self, *args, **kwargs):
        self.full_clean()
        self.sous_total = self.calculer_sous_total()
        super().save(*args, **kwargs)

    @property
    def nom_marque(self):
        return self.marque.marque if self.marque else "Marque inconnue"
    
    def __str__(self):
        return f"{self.quantite} x {self.produit} (Commande #{self.commande_client_id})"

class BonCommande(models.Model):
    commande = models.OneToOneField("CommandeClient", on_delete=models.CASCADE, related_name="bon_commande")
    numero_bon = models.CharField(max_length=100, unique=True)  # Même que numero_commande
    montant_total = models.DecimalField(max_digits=12, decimal_places=2)
    acompte = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reste_a_payer = models.DecimalField(max_digits=12, decimal_places=2)
    date_acompte = models.DateTimeField("Date de l'acompte", auto_now_add=True)
    modification_date_acompte = models.DateTimeField("Dernière modification", auto_now=True)
    
    def save(self, *args, **kwargs):
        self.reste_a_payer = max(self.montant_total - self.acompte, 0)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"BonCommande #{self.numero_bon}"
    

# End prise de commande en boutique