from django.contrib import admin

from .models import Stock, VendorStock


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "produit_line",
        "bijouterie",
        "is_reserve",
        "quantite_totale",  # plafond total affecté
        "en_stock",             # reste réel
        "updated_at",
    )
    list_filter = ("bijouterie", "is_reserve")
    search_fields = ("produit_line__id", "produit_line__produit__nom")


@admin.register(VendorStock)
class VendorStockAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "produit_line",
        "vendor",
        "quantite_allouee",
        "quantite_vendue",
        "disponible",
        "updated_at",
    )
    list_filter = ("vendor", "bijouterie")
    search_fields = ("produit_line__id", "vendor__user__email")

    def disponible(self, obj):
        return obj.quantite_allouee - obj.quantite_vendue
    disponible.short_description = "Disponible"


