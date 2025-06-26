from django.contrib import admin
from order.models import CommandeProduitClient

# Register your models here.
@admin.register(CommandeProduitClient)
class CommandeProduitClientAdmin(admin.ModelAdmin):
    list_display = ['commande_client', 'nom_produit', 'quantite', 'prix_prevue', 'sous_total']