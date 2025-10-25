from django.contrib import admin

from .models import *

# Register your models here.

admin.site.register(User)
admin.site.register(Role)


@admin.register(OutboxEmail)
class OutboxEmailAdmin(admin.ModelAdmin):
    list_display = ("to", "template", "attempts", "next_try_at", "created_at")
    list_filter = ("template",)
    search_fields = ("to",)
    readonly_fields = ("created_at",)