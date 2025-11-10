from django.contrib import admin
from django.utils.html import format_html

# ⬇️ ADAPTE les chemins si besoin
from staff.models import Cashier, Manager  # ex: app "cashier"
from store.models import Bijouterie  # pour autocomplete_fields
from vendor.models import Vendor  # facultatif si tu veux aussi l’avoir ici


# ---------- Utils communs ----------
class StaffBaseAdmin(admin.ModelAdmin):
    """
    Base admin pour profils staff rattachés à un User et à une Bijouterie.
    Suppose que le modèle a (au moins) : user(FK), bijouterie(FK), verifie(bool?), created_at/updated_at (optionnel).
    """

    # Affichage compact & utile
    list_display = (
        "id",
        "user_email",
        "user_full_name",
        "bijouterie",
        "verifie_badge",
        "created_at",
        "updated_at",
    )
    list_select_related = ("user", "bijouterie")
    list_per_page = 25

    # Filtres et recherche
    list_filter = ("bijouterie", "verifie")
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "user__username",
        "bijouterie__nom",
    )

    # Confort d’édition
    autocomplete_fields = ("user", "bijouterie")
    readonly_fields = ("created_at", "updated_at")

    # Actions rapides
    actions = ("action_activer", "action_desactiver")

    # ---- Helpers colonnes ----
    def user_email(self, obj):
        return getattr(getattr(obj, "user", None), "email", "")
    user_email.short_description = "Email"

    def user_full_name(self, obj):
        u = getattr(obj, "user", None)
        first = getattr(u, "first_name", "") or ""
        last = getattr(u, "last_name", "") or ""
        full = (first + " " + last).strip()
        return full or getattr(u, "username", "") or u.email
    user_full_name.short_description = "Nom complet"

    def verifie_badge(self, obj):
        v = getattr(obj, "verifie", None)
        if v is True:
            return format_html('<b style="color:#15803d;">✔</b>')
        if v is False:
            return format_html('<b style="color:#b91c1c;">✘</b>')
        return "—"
    verifie_badge.short_description = "Vérifié"

    # ---- Actions ----
    def action_activer(self, request, queryset):
        if "verifie" in [f.name for f in queryset.model._meta.fields]:
            queryset.update(verifie=True)
            self.message_user(request, f"{queryset.count()} élément(s) activé(s).")
        else:
            self.message_user(request, "Ce modèle n’a pas de champ 'verifie'.", level="warning")
    action_activer.short_description = "Activer (verifie=True)"

    def action_desactiver(self, request, queryset):
        if "verifie" in [f.name for f in queryset.model._meta.fields]:
            queryset.update(verifie=False)
            self.message_user(request, f"{queryset.count()} élément(s) désactivé(s).")
        else:
            self.message_user(request, "Ce modèle n’a pas de champ 'verifie'.", level="warning")
    action_desactiver.short_description = "Désactiver (verifie=False)"


# ---------- Admins concrets ----------
@admin.register(Manager)
class ManagerAdmin(StaffBaseAdmin):
    """
    Manager : souvent staff avec verifie + bijouterie obligatoire.
    """
    fieldsets = (
        (None, {
            "fields": ("user", "bijouterie", "verifie")
        }),
        ("Métadonnées", {
            "classes": ("collapse",),
            "fields": ("created_at", "updated_at"),
        }),
    )


@admin.register(Cashier)
class CashierAdmin(StaffBaseAdmin):
    """
    Cashier : rattaché à une bijouterie, verifie optionnel selon ton modèle.
    """
    fieldsets = (
        (None, {
            "fields": ("user", "bijouterie", "verifie")
        }),
        ("Métadonnées", {
            "classes": ("collapse",),
            "fields": ("created_at", "updated_at"),
        }),
    )
