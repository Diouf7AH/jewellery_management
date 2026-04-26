from django.contrib import admin

from person.models import Employee, Ouvrier


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "person_image",
        "full_name",
        "telephone",
        "bijouterie",
        "active",
        "created_at",
    )
    list_filter = ("active", "bijouterie", "sexe", "created_at")
    search_fields = ("nom", "prenom", "telephone", "bijouterie__nom")
    readonly_fields = ("person_image", "created_at", "updated_at")
    ordering = ("-id",)


@admin.register(Ouvrier)
class OuvrierAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "person_image",
        "full_name",
        "telephone",
        "specialite",
        "bijouterie",
        "active",
        "created_at",
    )
    list_filter = ("active", "bijouterie", "sexe", "created_at")
    search_fields = ("nom", "prenom", "telephone", "specialite", "bijouterie__nom")
    readonly_fields = ("person_image", "created_at", "updated_at")
    ordering = ("-id",)


    