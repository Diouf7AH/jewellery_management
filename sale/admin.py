# Register your models here.
from django.contrib import admin

from sale.models import Client, Facture, Paiement, Vente, VenteProduit

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    # list_display = ('id', 'produit', 'fournisseur', 'poids', 'prix_achat_gramm', 'quantite', 'total_prix_achat', 'date_ajout')
    list_display = ('id', 'nom', 'prenom',)
    # search_fields = ('telephone',)

@admin.register(Vente)
class VenteAdmin(admin.ModelAdmin):
    list_display = ('id', 'numero_vente', 'client_full_name', 'created_at', 'montant_total',)
    # search_fields = ('nom',)
    # Concatenate the desired fields, e.g. first_name and last_name
    def client_full_name(self, obj):
        return f"{obj.client.prenom} - {obj.client.nom}"


@admin.register(VenteProduit)
class VenteProduitAdmin(admin.ModelAdmin):
    # search_fields = ('nom',)

    # Concatenate the desired fields, e.g. first_name and last_name
    def client_full_name(self, obj):
        return f"{obj.vente.client.prenom} - {obj.vente.client.nom}"
    # client_full_name.short_description = 'Full Name' # Optional: Set the column header
    list_display = ('produit', 'quantite', 'prix_vente_grammes', 'remise', 'autres', 'sous_total_prix_vente_ht',)
    search_fields = ("numero_vente", "client__nom", "client__prenom")


@admin.register(Facture)
class FactureAdmin(admin.ModelAdmin):
    list_display = ('numero_facture', 'vente', 'montant_total', 'status', 'date_creation', 'est_reglee')
    list_filter = ('status', 'date_creation')
    search_fields = ('numero_facture', 'vente__client__nom', 'vente__client__prenom')
    readonly_fields = ('numero_facture', 'date_creation')
    
    
@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = ('id','facture', 'montant_paye', 'date_paiement')
    # search_fields = ('nom',)