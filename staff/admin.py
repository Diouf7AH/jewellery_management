from django.contrib import admin
from django.utils.html import format_html

from sale.models import Paiement  # pour voir ses paiements en inline

from .models import Cashier


class PaiementInline(admin.TabularInline):
    """
    Liste des paiements associés à ce caissier.
    Purement informatif dans l'admin.
    """
    model = Paiement
    extra = 0
    fk_name = "cashier"
    readonly_fields = ("facture", "montant_paye", "mode_paiement", "date_paiement", "created_by")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        # on ne crée pas de paiements depuis le profil caissier
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
        "bijouterie__nom",
    )
    raw_id_fields = ("user", "bijouterie")
    ordering = ("-created_at",)
    inlines = [PaiementInline]

    fieldsets = (
        ("Infos compte", {
            "fields": ("user", "bijouterie", "verifie")
        }),
        ("Suivi", {
            "fields": ("created_at", "updated_at"),
        }),
    )
    readonly_fields = ("created_at", "updated_at")

    # ----- helpers pour l'affichage -----
    def user_full_name(self, obj):
        if not obj.user:
            return "-"
        return obj.user.get_full_name() or obj.user.username
    user_full_name.short_description = "Caissier"

    def user_email(self, obj):
        return getattr(obj.user, "email", "") or "-"
    user_email.short_description = "Email"
    