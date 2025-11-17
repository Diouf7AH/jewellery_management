# from django.contrib import admin
# from django.contrib.admin.sites import NotRegistered
# from django.contrib.auth import get_user_model

# from store.models import Bijouterie

# from .models import Vendor

# User = get_user_model()


# # --- User admin (pour l'autocomplete sur Vendor.user) ---
# try:
#     admin.site.unregister(User)
# except NotRegistered:
#     pass

# @admin.register(User)
# class UserAdmin(admin.ModelAdmin):
#     search_fields = ("email", "username", "first_name", "last_name", "telephone", "slug")
#     list_display  = ("id", "email", "username", "first_name", "last_name", "telephone", "slug")
#     ordering      = ("-id",)

# # --- Bijouterie admin (pour l'autocomplete sur Vendor.bijouterie) ---
# try:
#     admin.site.unregister(Bijouterie)
# except NotRegistered:
#     pass

# @admin.register(Bijouterie)
# class BijouterieAdmin(admin.ModelAdmin):
#     search_fields = ("nom", "slug")
#     list_display  = ("id", "nom")
#     ordering      = ("nom",)

# # Register your models here.
# # @admin.register(Vendor)
# # class VendorAdmin(admin.ModelAdmin):
# #     list_display = ("id", "user_full_name", "user_email", "user_slug", "bijouterie", "verifie")
# #     search_fields = ("user__slug", "user__email", "user__first_name", "user__last_name", "bijouterie__nom")
# #     list_filter = ("verifie", "bijouterie")
# #     readonly_fields = ("user_slug",)
# #     autocomplete_fields = ("user", "bijouterie")
# #     list_select_related = ("user", "bijouterie")
# #     ordering = ("-id",)

# #     @admin.display(description="Nom complet")
# #     def user_full_name(self, obj):
# #         u = obj.user
# #         if not u: return "—"
# #         return f"{(u.first_name or '').strip()} {(u.last_name or '').strip()}".strip() or "—"

# #     @admin.display(description="Email")
# #     def user_email(self, obj):
# #         return getattr(obj.user, "email", "—") or "—"

# #     @admin.display(description="Slug (user)")
# #     def user_slug(self, obj):
# #         return getattr(obj.user, "slug", "—") or "—"

# @admin.register(Vendor)
# class VendorAdmin(admin.ModelAdmin):
#     list_display = ("id", "user_email", "user_full_name", "bijouterie", "slug", "verifie")
#     autocomplete_fields = ("user", "bijouterie")   # ✅ maintenant OK
#     list_select_related = ("user", "bijouterie")
#     search_fields = ("user__email", "user__first_name", "user__last_name", "user__telephone", "user__slug")

#     @admin.display(description="Email")
#     def user_email(self, obj):
#         return getattr(obj.user, "email", "—") or "—"

#     @admin.display(description="Nom complet")
#     def user_full_name(self, obj):
#         u = obj.user
#         if not u: return "—"
#         return f"{(u.first_name or '').strip()} {(u.last_name or '').strip()}".strip() or "—"



# # @admin.register(Vendor)
# # class VendorAdmin(admin.ModelAdmin):
# #     list_display = ("id", "user", "slug", "verifie")
# #     search_fields = ("user__email", "user__first_name", "user__last_name", "slug")
# #     readonly_fields = ("slug",)  # si tu verrouilles la modif côté admin
# #     list_filter = ("verifie",)


from django.contrib import admin
from django.utils.html import format_html

from .models import Vendor  # ajoute Cashier, Manager ici si tu en as

# --- Base admin réutilisable pour tous les staff (Vendor, Cashier, etc.) ---

class StaffBaseAdmin(admin.ModelAdmin):
    """
    Admin générique pour les modèles qui héritent de StaffBase.
    Tu peux l’utiliser pour Vendor, Cashier, Manager, etc.
    """
    list_display = (
        "id",
        "user_email",
        "user_full_name",
        "bijouterie",
        "verifie",
        "is_user_active",
        "created_at",
    )
    list_filter = (
        "verifie",
        "bijouterie",
        "user__is_active",
        "user__is_email_verified",
    )
    search_fields = (
        "user__email",
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__telephone",
    )
    # autocomplete_fields = ("user", "bijouterie")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)

    # --------- Helpers affichage ---------

    @admin.display(description="Email", ordering="user__email")
    def user_email(self, obj):
        return obj.user.email

    @admin.display(description="Nom complet")
    def user_full_name(self, obj):
        full_name = obj.user.get_full_name()
        return full_name or obj.user.username or obj.user.email

    @admin.display(description="Actif ?", boolean=True)
    def is_user_active(self, obj):
        return obj.user.is_active

    def get_queryset(self, request):
        """
        Optimisation: prefetch user + bijouterie
        """
        qs = super().get_queryset(request)
        return qs.select_related("user", "bijouterie")


# --- Vendor ---

@admin.register(Vendor)
class VendorAdmin(StaffBaseAdmin):
    """
    Admin pour les vendors. Hérite de StaffBaseAdmin.
    Tu peux ajouter ici des colonnes spécifiques au vendor.
    """
    # Si tu ajoutes des champs spécifiques dans Vendor, tu peux les exposer ici :
    # list_display = StaffBaseAdmin.list_display + ("mon_champ",)
    # list_filter = StaffBaseAdmin.list_filter + ("mon_champ",)

    pass


# Si tu as d’autres modèles staff-like (ex: Cashier, Manager),
# tu peux les enregistrer comme ceci :

# from .models import Cashier, Manager

# @admin.register(Cashier)
# class CashierAdmin(StaffBaseAdmin):
#     pass
#
# @admin.register(Manager)
# class ManagerAdmin(StaffBaseAdmin):
#     pass