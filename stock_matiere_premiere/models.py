from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

# RachatClient = montant total négocié + client + date
# RachatClientItem = description + matière + pureté + poids
# MatierePremiereStock = stock groupé par bijouterie + matière + pureté
# MatierePremiereMovement = historique de chaque ligne

# Create your models here.
class RachatClient(models.Model):
    numero_ticket = models.CharField(max_length=50, unique=True, db_index=True)

    PAYMENT_PENDING = "pending"
    PAYMENT_PAID = "paid"
    PAYMENT_CANCELLED = "cancelled"

    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_PENDING, "En attente paiement"),
        (PAYMENT_PAID, "Payé"),
        (PAYMENT_CANCELLED, "Annulé"),
    ]

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default=PAYMENT_PENDING,
    )

    paid_at = models.DateTimeField(null=True, blank=True)

    paid_by = models.ForeignKey(
        "userauths.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="paid_%(class)s",
    )
    client = models.ForeignKey("sale.Client", on_delete=models.PROTECT)
    cni_client = models.CharField(max_length=100, blank=True, null=True)
    bijouterie = models.ForeignKey("store.Bijouterie", on_delete=models.PROTECT)
    montant_total = models.DecimalField(max_digits=16,decimal_places=2,validators=[MinValueValidator(Decimal("0.01"))],)
    mode_paiement = models.CharField(max_length=30, default="especes")
    created_at = models.DateTimeField(auto_now_add=True)
    # Client.address → peut changer
    # RachatClient.adresse_client → NE CHANGE JAMAIS ✅
    adresse_client = models.CharField(max_length=255)
    mention = models.TextField(blank=True, null=True)
    
    STATUS_CONFIRMED = "confirmed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_CONFIRMED, "Confirmé"),
        (STATUS_CANCELLED, "Annulé"),
    ]
    status = models.CharField(max_length=20,choices=STATUS_CHOICES,default=STATUS_CONFIRMED,)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey("userauths.User",on_delete=models.SET_NULL,null=True,blank=True,related_name="cancelled_%(class)s",)
    cancel_reason = models.TextField(blank=True, null=True)
    

class RachatClientItem(models.Model):
    rachat = models.ForeignKey(RachatClient, related_name="items", on_delete=models.CASCADE)
    description = models.CharField(max_length=255)
    matiere = models.CharField(max_length=50, default="or")
    purete = models.ForeignKey("store.Purete", on_delete=models.PROTECT)
    poids = models.DecimalField(max_digits=14,decimal_places=3,validators=[MinValueValidator(Decimal("0.001"))],)
    movement = models.OneToOneField("stock_matiere_premiere.MatierePremiereMovement",on_delete=models.PROTECT,null=True,blank=True,related_name="rachat_item",)



class MatierePremiereStock(models.Model):
    MATIERE_OR = "or"
    MATIERE_ARGENT = "argent"

    MATIERE_CHOICES = [
        (MATIERE_OR, "Or"),
        (MATIERE_ARGENT, "Argent"),
    ]

    bijouterie = models.ForeignKey("store.Bijouterie",on_delete=models.PROTECT,related_name="stocks_matiere_premiere")
    matiere = models.CharField(max_length=30,choices=MATIERE_CHOICES,default=MATIERE_OR)
    purete = models.ForeignKey("store.Purete",on_delete=models.PROTECT,related_name="stocks_matiere_premiere")
    poids_total = models.DecimalField(max_digits=14,decimal_places=3,default=Decimal("0.000"),validators=[MinValueValidator(Decimal("0.000"))])
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["bijouterie_id", "matiere", "purete_id"]

        constraints = [
            models.UniqueConstraint(
                fields=["bijouterie", "matiere", "purete"],
                name="uq_stock_matiere_unique"
            ),
            models.CheckConstraint(
                check=Q(poids_total__gte=0),
                name="ck_stock_matiere_positive"
            )
        ]

    def __str__(self):
        return f"{self.bijouterie} - {self.matiere} - {self.purete} : {self.poids_total} g"
    


# fournisseur

class AchatMatierePremiere(models.Model):
    numero_ticket = models.CharField(max_length=50, unique=True, db_index=True)

    PAYMENT_PENDING = "pending"
    PAYMENT_PAID = "paid"
    PAYMENT_CANCELLED = "cancelled"

    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_PENDING, "En attente paiement"),
        (PAYMENT_PAID, "Payé"),
        (PAYMENT_CANCELLED, "Annulé"),
    ]

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default=PAYMENT_PAID,  
    )

    paid_at = models.DateTimeField(null=True, blank=True)

    paid_by = models.ForeignKey(
        "userauths.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="paid_%(class)s",
    )
    fournisseur = models.ForeignKey(
        "purchase.Fournisseur",
        on_delete=models.PROTECT,
        related_name="achats_matiere_premiere",
    )
    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        related_name="achats_matiere_premiere",
    )

    reference = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    montant_total = models.DecimalField(max_digits=16, decimal_places=2)
    mode_paiement = models.CharField(max_length=30, default="especes")
    adresse_fournisseur = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    
    STATUS_CONFIRMED = "confirmed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_CONFIRMED, "Confirmé"),
        (STATUS_CANCELLED, "Annulé"),
    ]

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_CONFIRMED,
    )

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        "userauths.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_%(class)s",
    )

    cancel_reason = models.TextField(blank=True, null=True)


    def __str__(self):
        return f"Achat matière #{self.id} - {self.fournisseur}"
    

class AchatMatierePremiereItem(models.Model):
    achat = models.ForeignKey(AchatMatierePremiere,related_name="items",on_delete=models.CASCADE,)
    description = models.CharField(max_length=255, blank=True, null=True)
    matiere = models.CharField(max_length=30,choices=MatierePremiereStock.MATIERE_CHOICES,default=MatierePremiereStock.MATIERE_OR,)
    purete = models.ForeignKey("store.Purete",on_delete=models.PROTECT,)
    poids = models.DecimalField(max_digits=14, decimal_places=3)
    movement = models.OneToOneField("stock_matiere_premiere.MatierePremiereMovement",on_delete=models.PROTECT,null=True,blank=True,related_name="achat_matiere_item",)

    def __str__(self):
        return f"{self.matiere} - {self.purete} - {self.poids} g"


class MatierePremiereMovement(models.Model):
    SOURCE_RACHAT_CLIENT = "rachat_client"
    SOURCE_ACHAT_FOURNISSEUR = "achat_fournisseur"
    SOURCE_RACHAT_CLIENT_CANCEL = "rachat_client_cancel"
    SOURCE_ACHAT_FOURNISSEUR_CANCEL = "achat_fournisseur_cancel"
    SOURCE_REMISE_VENTE = "remise_vente"
    SOURCE_RAFFINAGE_OUT = "raffinage_out"
    SOURCE_RAFFINAGE_IN = "raffinage_in"
    SOURCE_VENTE_POIDS = "vente_poids"
    SOURCE_COMMANDE_CLIENT = "commande_client"
    SOURCE_VENTE_RAFFINE = "vente_raffine"


    SOURCE_CHOICES = [
        (SOURCE_RACHAT_CLIENT, "Rachat client"),
        (SOURCE_ACHAT_FOURNISSEUR, "Achat fournisseur"),
        (SOURCE_RACHAT_CLIENT_CANCEL, "Annulation rachat client"),
        (SOURCE_ACHAT_FOURNISSEUR_CANCEL, "Annulation achat fournisseur"),
        (SOURCE_REMISE_VENTE, "Remise vente"),
        (SOURCE_RAFFINAGE_OUT, "Raffinage sortie"),
        (SOURCE_RAFFINAGE_IN, "Raffinage entrée"),
        (SOURCE_VENTE_POIDS, "Vente par poids"),
        (SOURCE_COMMANDE_CLIENT, "Commande client"),
        (SOURCE_VENTE_RAFFINE, "Vente raffinée"),
    ]

    stock = models.ForeignKey(MatierePremiereStock,on_delete=models.PROTECT,related_name="movements",)
    bijouterie = models.ForeignKey("store.Bijouterie",on_delete=models.PROTECT,related_name="mouvements_matiere",)
    matiere = models.CharField(max_length=30,choices=MatierePremiereStock.MATIERE_CHOICES,)
    purete = models.ForeignKey("store.Purete",on_delete=models.PROTECT,related_name="mouvements_matiere",)
    poids = models.DecimalField(max_digits=14,decimal_places=3,validators=[MinValueValidator(Decimal("0.001"))],)

    # ✔ chaque entrée a son prix
    # ✔ chaque sortie garde son coût
    # ✔ audit facile
    # cout_unitaire = montant_total / poids
    cout_unitaire = models.DecimalField(max_digits=14,decimal_places=2,null=True,blank=True)
    montant_total = models.DecimalField(max_digits=16,decimal_places=2,null=True,blank=True)
    source = models.CharField(max_length=50,choices=SOURCE_CHOICES,default=SOURCE_RACHAT_CLIENT,)
    rachat = models.ForeignKey("stock_matiere_premiere.RachatClient",on_delete=models.SET_NULL,null=True,blank=True,related_name="movements",)
    achat = models.ForeignKey("stock_matiere_premiere.AchatMatierePremiere",on_delete=models.SET_NULL,null=True,blank=True,related_name="movements",)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["source"]),
            models.Index(fields=["bijouterie", "matiere", "purete"]),
        ]

###################################################################
########################  Raffinage   #############################
###################################################################

class Raffinage(models.Model):
    numero_operation = models.CharField(max_length=50, unique=True)
    bijouterie = models.ForeignKey("store.Bijouterie", on_delete=models.PROTECT)
    matiere = models.CharField(max_length=30,choices=MatierePremiereStock.MATIERE_CHOICES,)
    purete_avant = models.ForeignKey("store.Purete",on_delete=models.PROTECT,related_name="+")
    purete_apres = models.ForeignKey("store.Purete",on_delete=models.PROTECT,related_name="+")
    poids_entree = models.DecimalField(max_digits=14, decimal_places=3)
    poids_sortie = models.DecimalField(max_digits=14, decimal_places=3)
    perte = models.DecimalField(max_digits=14,decimal_places=3,default=Decimal("0.000"))
    created_at = models.DateTimeField(auto_now_add=True)

class StockRaffine(models.Model):
    bijouterie = models.ForeignKey("store.Bijouterie", on_delete=models.PROTECT)
    matiere = models.CharField(max_length=30,choices=MatierePremiereStock.MATIERE_CHOICES,)
    purete = models.ForeignKey("store.Purete", on_delete=models.PROTECT)
    poids_total = models.DecimalField(max_digits=14,decimal_places=3,default=Decimal("0.000"),validators=[MinValueValidator(Decimal("0.000"))],)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["bijouterie", "matiere", "purete"],
                name="uq_stock_raffine_unique",
            )
        ]
    


class VenteMatierePremiere(models.Model):
    SOURCE_AVANT_RAFFINAGE = "avant_raffinage"
    SOURCE_APRES_RAFFINAGE = "apres_raffinage"

    SOURCE_CHOICES = [
        (SOURCE_AVANT_RAFFINAGE, "Avant raffinage"),
        (SOURCE_APRES_RAFFINAGE, "Après raffinage"),
    ]

    numero_vente = models.CharField(max_length=50, unique=True, db_index=True)
    source_stock = models.CharField(max_length=30,choices=SOURCE_CHOICES,)
    bijouterie = models.ForeignKey("store.Bijouterie", on_delete=models.PROTECT)
    client = models.ForeignKey("sale.Client", on_delete=models.PROTECT, null=True, blank=True)
    matiere = models.CharField(max_length=30,choices=MatierePremiereStock.MATIERE_CHOICES,)
    purete = models.ForeignKey("store.Purete", on_delete=models.PROTECT)
    poids = models.DecimalField(max_digits=14,decimal_places=3,validators=[MinValueValidator(Decimal("0.001"))],)
    prix_gramme = models.DecimalField(max_digits=14,decimal_places=2,validators=[MinValueValidator(Decimal("0.01"))],)
    montant_total = models.DecimalField(max_digits=16,decimal_places=2,validators=[MinValueValidator(Decimal("0.01"))],)
    created_by = models.ForeignKey("userauths.User",on_delete=models.SET_NULL,null=True,blank=True,related_name="ventes_matiere_premiere",)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.numero_vente} - {self.matiere} - {self.poids} g"
    
    
    