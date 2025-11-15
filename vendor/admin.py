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
