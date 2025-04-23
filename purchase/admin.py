# Register your models here.
from django.contrib import admin

from store.models import Produit

from .models import Achat, AchatProduit, Fournisseur


@admin.register(Fournisseur)
class FournisseurAdmin(admin.ModelAdmin):
    list_display = ('id', 'nom', 'prenom', 'address', 'telephone')
    search_fields = ('nom',)

# @admin.register(Achat)
# class AchatAdmin(admin.ModelAdmin):
#     # list_display = ('id', 'produit', 'fournisseur', 'poids', 'prix_achat_gramm', 'quantite', 'total_prix_achat', 'date_ajout')
#     # list_display = ('id', 'produit', 'fournisseur','produit__categorie__nom','produit__marque__marque', 'produit__purete__purete', 'produit__poids', 'produit__prix_vente_grammes','calcul_total_poids_achat','prix_achat_gramme', 'calcul_total_achat', 'quantite', 'date_ajout', 'date_modification',)
#     list_display=('id', 'fournisseur', 'montant_total', 'created_at')
#     search_fields = ('fournisseur',)
#     # exclude = ('total_prix_achat', 'date_ajout',)
#     # search_fields = ('produit__nom', 'fournisseur__nom' , 'produit__categorie__nom')
    
#     # # call faction in model
#     # def calcul_total_poids_achat(self, obj):
#     #     return obj.calcul_total_poids_achat()
    
#     # def calcul_total_achat(self, obj):
#     #     return obj.calcul_total_achat()

@admin.register(Achat)
class AchatAdmin(admin.ModelAdmin):
    list_display = ['fournisseur', 'created_at', 'montant_total_ht', 'montant_total_ttc']
    search_fields = ['fournisseur__nom', 'fournisseur__telephone']
    list_filter = ['created_at']

@admin.register(AchatProduit)
class AchatProduitAdmin(admin.ModelAdmin):
    list_display = ('id','numero_achat_produit','achat', 'produit', 'quantite', 'prix_achat_gramme', 'tax', 'sous_total_prix_achat')
    # search_fields = ('nom',)



