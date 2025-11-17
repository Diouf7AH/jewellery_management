from django.contrib import admin

from employee.models import Employee


# Register your models here.
@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("id", "employee_image", "name", "phone", "bijouterie", "active", "joined_at", "created_at")
    list_filter = ("active", "bijouterie")
    search_fields = ("name", "phone", "description")
    readonly_fields = ("employee_image", "created_at", "updated_at")