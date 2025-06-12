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

@admin.action(description="Regénérer le QR Code")
def regenerer_qr_code_action(modeladmin, request, queryset):
    for produit in queryset:
        produit.regenerate_qr_code()

# pouvoir regénérer un QR code manuellement depuis l’admin Django
@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = ('id', 'slug', 'nom', 'categorie', 'marque', 'modele', 'poids', 'taille', 'sku', 'qr_code_url')
    actions = [regenerer_qr_code_action]
    # readonly_fields = ('affiche_qr_code',)

    # def affiche_qr_code(self, obj):
    #     if obj.qr_code:
    #         return format_html('<img src="{}" width="100" height="100" />', obj.qr_code.url)
    #     return "Pas de QR code"

    # affiche_qr_code.short_description = "QR Code"
    

@admin.register(Gallery)
class GalleryAdmin(admin.ModelAdmin):
    list_display = ("id", "produit", "image", "date",)
    search_fields = ('',)
    # exclude = ("qr_code", "slug", "prix_achat_avec_tax", "sku", "prix_vente_reel", "pid", )
