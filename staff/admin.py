# from django.contrib import admin

# from sale.models import Paiement

# from .models import Cashier


# class PaiementInline(admin.TabularInline):
#     """
#     Liste des paiements associés à ce caissier.
#     Purement informatif dans l'admin.
#     """
#     model = Paiement
#     extra = 0
#     fk_name = "cashier"
#     readonly_fields = (
#         "facture",
#         "montant_total_paye",
#         "date_paiement",
#         "created_by",
#     )
#     fields = (
#         "facture",
#         "montant_total_paye",
#         "date_paiement",
#         "created_by",
#     )
#     can_delete = False
#     show_change_link = True

#     def has_add_permission(self, request, obj=None):
#         return False


# @admin.register(Cashier)
# class CashierAdmin(admin.ModelAdmin):
#     list_display = (
#         "id",
#         "user_full_name",
#         "user_email",
#         "bijouterie",
#         "verifie",
#         "created_at",
#     )
#     list_filter = ("bijouterie", "verifie", "created_at")
#     search_fields = (
#         "user__email",
#         "user__first_name",
#         "user__last_name",
#         "user__username",
#         "bijouterie__nom",
#     )
#     raw_id_fields = ("user", "bijouterie")
#     ordering = ("-created_at",)
#     inlines = [PaiementInline]
#     list_select_related = ("user", "bijouterie")

#     fieldsets = (
#         ("Infos compte", {
#             "fields": ("user", "bijouterie", "verifie")
#         }),
#         ("Suivi", {
#             "fields": ("created_at", "updated_at"),
#         }),
#     )
#     readonly_fields = ("created_at", "updated_at")

#     @admin.display(description="Caissier", ordering="user__last_name")
#     def user_full_name(self, obj):
#         if not obj.user:
#             return "-"
#         return obj.user.get_full_name() or obj.user.username

#     @admin.display(description="Email", ordering="user__email")
#     def user_email(self, obj):
#         return getattr(obj.user, "email", "") or "-"
    
    
from django.contrib import admin

from sale.models import Paiement

from .models import Cashier, Manager


class PaiementInline(admin.TabularInline):
    model = Paiement
    extra = 0
    fk_name = "cashier"
    readonly_fields = (
        "facture",
        "montant_total_paye",
        "date_paiement",
        "created_by",
    )
    fields = (
        "facture",
        "montant_total_paye",
        "date_paiement",
        "created_by",
    )
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Cashier)
class CashierAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_full_name",
        "user_email",
        "bijouterie",
        "verifie",
        "created_at",
    )
    list_filter = ("bijouterie", "verifie", "created_at")
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "user__username",
        "bijouterie__nom",
    )
    raw_id_fields = ("user", "bijouterie")
    ordering = ("-created_at",)
    inlines = [PaiementInline]
    list_select_related = ("user", "bijouterie")

    fieldsets = (
        ("Infos compte", {
            "fields": ("user", "bijouterie", "verifie")
        }),
        ("Suivi", {
            "fields": ("created_at", "updated_at"),
        }),
    )
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Caissier", ordering="user__last_name")
    def user_full_name(self, obj):
        if not obj.user:
            return "-"
        return obj.user.get_full_name() or obj.user.username

    @admin.display(description="Email", ordering="user__email")
    def user_email(self, obj):
        return getattr(obj.user, "email", "") or "-"


@admin.register(Manager)
class ManagerAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_full_name",
        "user_email",
        "get_bijouteries",
        "verifie",
        "created_at",
    )
    list_filter = ("verifie", "bijouteries", "created_at")
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "user__username",
        "bijouteries__nom",
    )
    raw_id_fields = ("user",)
    filter_horizontal = ("bijouteries",)
    ordering = ("-created_at",)
    list_select_related = ("user",)

    fieldsets = (
        ("Infos compte", {
            "fields": ("user", "bijouteries", "verifie")
        }),
        ("Désactivation", {
            "fields": ("raison_desactivation",),
        }),
        ("Suivi", {
            "fields": ("created_at", "updated_at"),
        }),
    )
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Manager", ordering="user__last_name")
    def user_full_name(self, obj):
        if not obj.user:
            return "-"
        return obj.user.get_full_name() or obj.user.username

    @admin.display(description="Email", ordering="user__email")
    def user_email(self, obj):
        return getattr(obj.user, "email", "") or "-"

    @admin.display(description="Bijouteries")
    def get_bijouteries(self, obj):
        return ", ".join(obj.bijouteries.values_list("nom", flat=True)) or "-"
    

