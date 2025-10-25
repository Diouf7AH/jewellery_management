from django.contrib import admin

from .models import Stock, VendorStock


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ("id", "produit_line", "bijouterie", "quantite_allouee", "quantite_disponible", "updated_at")
    list_filter = ("bijouterie",)
    search_fields = ("produit_line__id",)

@admin.register(VendorStock)
class VendorStockAdmin(admin.ModelAdmin):
    list_display = ("id", "produit_line", "vendor", "quantite_allouee", "quantite_disponible", "updated_at")
    list_filter = ("vendor",)
    search_fields = ("produit_line__id", "vendor__id")