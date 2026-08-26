from django.contrib import admin

from .models import ClientDepot, CompteDepot, CompteDepotTransaction

# ============================================================
# CLIENT DEPOT
# ============================================================

@admin.register(ClientDepot)
class ClientDepotAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "nom",
        "prenom",
        "telephone",
        "bijouterie",
    )

    search_fields = (
        "nom",
        "prenom",
        "telephone",
        "bijouterie__nom",
    )

    list_filter = (
        "bijouterie",
    )

    list_select_related = (
        "bijouterie",
    )

    list_per_page = 50


# ============================================================
# TRANSACTIONS INLINE
# ============================================================

class TransactionInline(admin.TabularInline):
    model = CompteDepotTransaction
    extra = 0

    fields = (
        "type_transaction",
        "montant",
        "solde_avant",
        "solde_apres",
        "statut",
        "reference",
        "commentaire",
        "user",
        "date_transaction",
    )

    readonly_fields = fields

    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ============================================================
# COMPTE DEPOT
# ============================================================

@admin.register(CompteDepot)
class CompteDepotAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "numero_compte",
        "client",
        "client_telephone",
        "client_bijouterie",
        "solde",
        "created_by",
        "created_at",
    )

    search_fields = (
        "numero_compte",
        "client__nom",
        "client__prenom",
        "client__telephone",
        "client__bijouterie__nom",
        "created_by__username",
        "created_by__email",
    )

    list_filter = (
        "client__bijouterie",
        "created_at",
    )

    readonly_fields = (
        "numero_compte",
        "solde",
        "created_by",
        "created_at",
        "client_telephone",
        "client_bijouterie",
    )

    autocomplete_fields = (
        "client",
    )

    inlines = [
        TransactionInline,
    ]

    list_select_related = (
        "client",
        "client__bijouterie",
        "created_by",
    )

    list_per_page = 50

    @admin.display(
        description="Téléphone",
        ordering="client__telephone",
    )
    def client_telephone(self, obj):
        client = getattr(obj, "client", None)

        if not client:
            return "-"

        return client.telephone or "-"

    @admin.display(
        description="Bijouterie",
        ordering="client__bijouterie__nom",
    )
    def client_bijouterie(self, obj):
        client = getattr(obj, "client", None)

        if not client:
            return "-"

        bijouterie = getattr(client, "bijouterie", None)

        return bijouterie or "-"


# ============================================================
# TRANSACTION COMPTE DEPOT
# ============================================================

@admin.register(CompteDepotTransaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "compte",
        "numero_compte",
        "client_nom",
        "client_telephone",
        "client_bijouterie",
        "type_transaction",
        "montant",
        "solde_avant",
        "solde_apres",
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
        "compte__client__bijouterie__nom",
        "reference",
        "user__username",
        "user__email",
    )

    list_filter = (
        "type_transaction",
        "statut",
        "compte__client__bijouterie",
        "date_transaction",
    )

    readonly_fields = (
        "compte",
        "type_transaction",
        "montant",
        "date_transaction",
        "user",
        "statut",
        "reference",
        "commentaire",
        "solde_avant",
        "solde_apres",
    )

    list_select_related = (
        "compte",
        "compte__client",
        "compte__client__bijouterie",
        "user",
    )

    list_per_page = 50

    @admin.display(
        description="N° compte",
        ordering="compte__numero_compte",
    )
    def numero_compte(self, obj):
        compte = getattr(obj, "compte", None)

        if not compte:
            return "-"

        return compte.numero_compte or "-"

    @admin.display(
        description="Client",
        ordering="compte__client__nom",
    )
    def client_nom(self, obj):
        compte = getattr(obj, "compte", None)
        client = getattr(compte, "client", None) if compte else None

        if not client:
            return "-"

        return client.full_name or "-"

    @admin.display(
        description="Téléphone",
        ordering="compte__client__telephone",
    )
    def client_telephone(self, obj):
        compte = getattr(obj, "compte", None)
        client = getattr(compte, "client", None) if compte else None

        if not client:
            return "-"

        return client.telephone or "-"

    @admin.display(
        description="Bijouterie",
        ordering="compte__client__bijouterie__nom",
    )
    def client_bijouterie(self, obj):
        compte = getattr(obj, "compte", None)
        client = getattr(compte, "client", None) if compte else None

        if not client:
            return "-"

        bijouterie = getattr(client, "bijouterie", None)

        return bijouterie or "-"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
    

