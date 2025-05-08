from django.contrib import admin

from .models import Vendor, VendorProduit


# Register your models here.
@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('user', 'bijouterie', 'verifie', 'raison_desactivation')
    list_editable = ('raison_desactivation',)  # 👈 rend le champ modifiable directement dans la liste
    list_filter = ('verifie',)
    search_fields = ('user__email', 'user__first_name', 'user__last_name')
    fields = ('id', 'user', 'bijouterie', 'verifie', 'raison_desactivation', 'description')  # 👈 dans la fiche détaillée


@admin.register(VendorProduit)
class VendorProduitAdmin(admin.ModelAdmin):
    list_display = ('id', 'vendor', 'produit', 'quantite',)
    # exclude = ("slug",)
    # search_fields = ('slug','nom',)
