from django.contrib import admin

from store.models import Bijouterie, Categorie, Marque, Modele, Produit, Purete, Gallery


# Register your models here.
@admin.register(Bijouterie)
class BijouterieAdmin(admin.ModelAdmin):
    list_display = ('id', 'telephone_portable_1','nom', 'adresse')
    exclude = ("id",)
    search_fields = ('id','nom',)

@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ('id', 'nom', 'image',)
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
    list_display = ("id", "nom", "sku", "image", "categorie", "marque", "modele", "purete", "matiere", "poids", "taille", "description",)
    search_fields = ('nom',)
    # exclude = ("qr_code", "slug", "prix_achat_avec_tax", "sku", "prix_vente_reel", "pid", )


@admin.register(Gallery)
class GalleryAdmin(admin.ModelAdmin):
    list_display = ("id", "produit", "image", "date",)
    search_fields = ('',)
    # exclude = ("qr_code", "slug", "prix_achat_avec_tax", "sku", "prix_vente_reel", "pid", )
