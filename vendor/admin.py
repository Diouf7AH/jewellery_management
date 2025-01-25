from django.contrib import admin

from .models import Vendor


# Register your models here.
@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('id', 'slug','nom', 'image', 'description',)
    exclude = ("slug",)
    search_fields = ('slug','nom',)
