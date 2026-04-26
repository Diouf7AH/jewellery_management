from django.contrib import admin

from .models import ClientDepot, CompteDepot, CompteDepotTransaction


@admin.register(ClientDepot)
class ClientDepotAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "prenom", "telephone", "CNI", "address")
    search_fields = ("nom", "prenom", "telephone", "CNI", "address")
    list_per_page = 50


class TransactionInline(admin.TabularInline):
    model = CompteDepotTransaction
    extra = 0
    fields = (
        "type_transaction",
        "montant",
        "statut",
        "reference",
        "commentaire",
        "user",
        "date_transaction",
    )
    readonly_fields = ("date_transaction",)
    raw_id_fields = ("user",)
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CompteDepot)
class CompteDepotAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "numero_compte",
        "client",
        "client_telephone",
        "solde",
        "created_by",
        "date_creation",
    )
    search_fields = (
        "numero_compte",
        "client__nom",
        "client__prenom",
        "client__telephone",
        "client__CNI",
        "created_by__username",
    )
    list_filter = ("date_creation",)
    readonly_fields = ("date_creation",)
    autocomplete_fields = ["client"]
    raw_id_fields = ("created_by",)
    inlines = [TransactionInline]
    list_select_related = ("client", "created_by")
    list_per_page = 50

    @admin.display(description="Téléphone", ordering="client__telephone")
    def client_telephone(self, obj):
        client = getattr(obj, "client", None)
        return getattr(client, "telephone", "-") if client else "-"


@admin.register(CompteDepotTransaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "compte",
        "numero_compte",
        "client_nom",
        "type_transaction",
        "montant",
        "statut",
        "reference",
        "user",
        "date_transaction",
    )
    search_fields = (
        "compte__numero_compte",
        "compte__client__nom",
        "compte__client__prenom",
        "compte__client__telephone",
        "reference",
        "user__username",
    )
    list_filter = ("type_transaction", "statut", "date_transaction")
    readonly_fields = ("date_transaction",)
    autocomplete_fields = ("compte",)
    raw_id_fields = ("user",)
    list_select_related = ("compte", "compte__client", "user")
    list_per_page = 50

    @admin.display(description="N° compte", ordering="compte__numero_compte")
    def numero_compte(self, obj):
        compte = getattr(obj, "compte", None)
        return getattr(compte, "numero_compte", "-") if compte else "-"

    @admin.display(description="Client", ordering="compte__client__nom")
    def client_nom(self, obj):
        compte = getattr(obj, "compte", None)
        client = getattr(compte, "client", None) if compte else None
        if not client:
            return "-"
        return f"{getattr(client, 'prenom', '')} {getattr(client, 'nom', '')}".strip() or "-"