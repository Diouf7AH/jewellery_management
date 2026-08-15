from django.contrib import admin

from .models import Stock, VendorStock


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "produit_line",
        "produit_affiche",
        "bijouterie",
        "quantite_totale",
        "en_stock",
        "updated_at",
    )

    list_filter = (
        "bijouterie",
    )

    search_fields = (
        "produit_line__produit__nom",
        "produit_line__produit__sku",
        "produit_line__lot__numero_lot",
    )

    readonly_fields = (
        "stock_key",
        "created_at",
        "updated_at",
    )
    
    raw_id_fields = (
        "produit_line",
        "bijouterie",
    )

    ordering = (
        "bijouterie_id",
        "produit_line_id",
    )

    list_select_related = (
        "bijouterie",
        "produit_line",
        "produit_line__produit",
        "produit_line__lot",
    )

    @admin.display(
        description="Produit",
        ordering="produit_line__produit__nom",
    )
    def produit_affiche(self, obj):
        return obj.produit


@admin.register(VendorStock)
class VendorStockAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "produit_line",
        "produit_affiche",
        "vendor",
        "bijouterie",
        "quantite_allouee",
        "quantite_vendue",
        "stock_vendeur",
        "updated_at",
    )

    list_filter = (
        "bijouterie",
        "vendor",
    )

    search_fields = (
        "vendor__user__email",
        "vendor__user__first_name",
        "vendor__user__last_name",
        "produit_line__produit__nom",
        "produit_line__produit__sku",
        "produit_line__lot__numero_lot",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    raw_id_fields = (
        "produit_line",
        "bijouterie",
    )

    autocomplete_fields = (
        "vendor",
    )

    ordering = (
        "bijouterie_id",
        "vendor_id",
        "produit_line_id",
    )

    list_select_related = (
        "vendor",
        "vendor__user",
        "bijouterie",
        "produit_line",
        "produit_line__produit",
        "produit_line__lot",
    )

    @admin.display(
        description="Produit",
        ordering="produit_line__produit__nom",
    )
    def produit_affiche(self, obj):
        return obj.produit

    @admin.display(
        description="Stock vendeur",
    )
    def stock_vendeur(self, obj):
        return obj.en_stock
    

