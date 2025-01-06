from django.contrib import admin

from store.models import Categorie, Marque, Modele, Produit, Purete


# Register your models here.
@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ('id', 'slug','nom', 'image', 'active',)
    exclude = ("slug",)
    search_fields = ('slug','nom',)
    
@admin.register(Purete)
class PureteAdmin(admin.ModelAdmin):
    list_display = ('purete',)
    search_fields = ('id','purete',)
    
@admin.register(Modele)
class ModeleAdmin(admin.ModelAdmin):
    list_display = ('id','modele', 'categorie',)
    search_fields = ('categorie',)
    

@admin.register(Marque)
class MarqueAdmin(admin.ModelAdmin):
    list_display = ('marque', 'purete', 'prix',)
    exclude = ('creation_date', 'modification_date',)
    search_fields = ('categorie',)


@admin.register(Produit)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("id", "quantite_en_stock", "slug", "nom", "sku", "image", "marque__prix", "prix_vente_grammes", "prix_avec_tax", "categorie", "marque", "modele", "purete", "matiere", "poids", "taille", "description",)
    search_fields = ('nom',)
    exclude = ("qr_code", "slug", "prix_avec_tax", "sku", "prix_vente_reel", "pid", )
