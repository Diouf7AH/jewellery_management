# # staff/admin.py
# from django.contrib import admin
# from django.utils.html import format_html

# from .models import Cashier  # + (éventuelles) autres sous-classes StaffCore


# # --- Filtres custom -----------------------------------------
# class HasUserFilter(admin.SimpleListFilter):
#     title = "a un utilisateur lié ?"
#     parameter_name = "has_user"

#     def lookups(self, request, model_admin):
#         return (("yes", "Oui"), ("no", "Non"))

#     def queryset(self, request, queryset):
#         if self.value() == "yes":
#             return queryset.filter(user__isnull=False)
#         if self.value() == "no":
#             return queryset.filter(user__isnull=True)
#         return queryset


# # --- Base admin réutilisable pour toutes tes sous-classes ----
# class BaseStaffAdmin(admin.ModelAdmin):
#     list_display = ("id", "user_display", "bijouterie", "verifie", "created_at", "updated_at")
#     list_filter = ("verifie", HasUserFilter, "bijouterie", "created_at")
#     search_fields = (
#         "user__username",
#         "user__email",
#         "user__first_name",
#         "user__last_name",
#         "bijouterie__nom",
#     )
#     # ⚠️ Pour que l'autocomplete fonctionne :
#     #  - le UserAdmin a déjà des search_fields par défaut (ok)
#     #  - assure-toi que BijouterieAdmin a bien search_fields = ("nom",) par ex.
#     autocomplete_fields = ("user", "bijouterie")

#     readonly_fields = ("created_at", "updated_at")
#     date_hierarchy = "created_at"
#     ordering = ("-id",)
#     list_editable = ("verifie",)
#     actions = ("action_activate", "action_deactivate", "action_detach_user")

#     def get_queryset(self, request):
#         return (
#             super()
#             .get_queryset(request)
#             .select_related("user", "bijouterie")
#         )

#     @admin.display(ordering="user__username", description="Utilisateur")
#     def user_display(self, obj):
#         u = obj.user
#         if not u:
#             return "—"
#         name = u.get_full_name() or u.get_username()
#         email = f" &lt;{u.email}&gt;" if u.email else ""
#         # petit plus visuel, cliquable vers le change de l’utilisateur
#         return format_html(
#             '<a href="/admin/auth/user/{}/change/">{}</a>{}',
#             u.pk, name, email
#         )

#     # --- Actions de masse ---
#     @admin.action(description="Activer (vérifié = Oui)")
#     def action_activate(self, request, queryset):
#         updated = queryset.update(verifie=True)
#         self.message_user(request, f"{updated} profil(s) activé(s).")

#     @admin.action(description="Désactiver (vérifié = Non)")
#     def action_deactivate(self, request, queryset):
#         updated = queryset.update(verifie=False)
#         self.message_user(request, f"{updated} profil(s) désactivé(s).")

#     @admin.action(description="Détacher l’utilisateur (user = NULL)")
#     def action_detach_user(self, request, queryset):
#         updated = queryset.update(user=None)
#         self.message_user(request, f"{updated} profil(s) détaché(s) de l’utilisateur.")


# # --- Enregistrements ----------------------------------------
# @admin.register(Cashier)
# class CashierAdmin(BaseStaffAdmin):
#     pass


# # Si tu as d'autres sous-classes (ex: Manager), réutilise la base :
# # from .models import Manager
# # @admin.register(Manager)
# # class ManagerAdmin(BaseStaffAdmin):
# #     pass
