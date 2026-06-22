from django.contrib import admin

from .models import EcommerceBanner, EcommerceHomeProduct


@admin.register(EcommerceBanner)
class EcommerceBannerAdmin(admin.ModelAdmin):
    list_display = [
        "titre",
        "position",
        "type_media",
        "active",
        "ordre_affichage",
        "updated_at",
    ]
    list_filter = [
        "position",
        "type_media",
        "active",
    ]
    search_fields = [
        "titre",
        "description",
    ]
    list_editable = [
        "active",
        "ordre_affichage",
    ]
    readonly_fields = [
        "uuid",
        "created_at",
        "updated_at",
    ]
    

@admin.register(EcommerceHomeProduct)
class EcommerceHomeProductAdmin(admin.ModelAdmin):
    list_display = [
        "produit",
        "bijouterie",
        "section",
        "badge",
        "active",
        "ordre_affichage",
        "updated_at",
    ]
    list_filter = [
        "section",
        "bijouterie",
        "active",
        "badge",
    ]
    search_fields = [
        "produit__nom",
        "produit__sku",
        "titre_personnalise",
        "badge",
    ]
    list_editable = [
        "active",
        "ordre_affichage",
    ]
    autocomplete_fields = [
        "produit",
        "bijouterie",
    ]
    readonly_fields = [
        "created_at",
        "updated_at",
    ]
    
