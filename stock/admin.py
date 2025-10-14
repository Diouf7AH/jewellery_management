# Register your models here.
from django.contrib import admin

from stock.models import Stock
from store.models import Produit


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    # list_display = ('id', 'produit', 'fournisseur', 'poids', 'prix_achat_gramm', 'quantite', 'total_prix_achat', 'date_ajout')
    # list_display = ('id', 'produit', 'fournisseur','produit__categorie__nom','produit__marque__marque', 'produit__purete__purete', 'produit__poids', 'produit__prix_vente_grammes','calcul_total_poids_achat','prix_achat_gramme', 'calcul_total_achat', 'quantite', 'date_ajout', 'date_modification',)
    list_display=('id', 'lot', 'quantite', 'reservation_key', 'is_reserved')
    search_fields = ('produit',)
    exclude = ('total_prix_achat', 'date_ajout',)
    search_fields = ('produit__nom' , 'produit__categorie__nom')
    
    # # call faction in model
    # def calcul_total_poids_achat(self, obj):
    #     return obj.calcul_total_poids_achat()
    
    # def calcul_total_achat(self, obj):
    #     return obj.calcul_total_achat()

# @admin.register(Fournisseur)
# class FournisseurAdmin(admin.ModelAdmin):
#     list_display = ('id','slug', 'nom', 'prenom', 'address', 'telephone')
#     search_fields = ('nom',)
    

# @admin.register(CommandeStock)
# class CommandeStockAdmin(admin.ModelAdmin):
#     list_display = ('id','fournisseur','date_commande_stock','etat',)
#     # search_fields = ('nom',)


# @admin.register(LigneCommandeStock)
# class LigneCommandeStockAdmin(admin.ModelAdmin):
#     list_display = ('id','commande_stock','produit', 'quantite', 'prix_par_unite',)
#     # search_fields = ('nom',)

