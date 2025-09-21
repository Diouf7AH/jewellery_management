from django.contrib import admin
from .models import Cashier
# Register your models here.
@admin.register(Cashier)
class CashierAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "slug", "verifie")
    search_fields = ("user__email", "user__first_name", "user__last_name", "slug")
    readonly_fields = ("slug",)
    list_filter = ("verifie",)