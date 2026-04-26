from django.contrib import admin

from sale.models import (Client, Facture, ModePaiement, Paiement,
                         PaiementLigne, Vente, VenteProduit)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "prenom", "telephone")
    search_fields = ("nom", "prenom", "telephone")
    list_per_page = 50


@admin.register(Vente)
class VenteAdmin(admin.ModelAdmin):
    list_display = ("id", "numero_vente", "client_full_name", "created_at", "montant_total")
    search_fields = ("numero_vente", "client__nom", "client__prenom", "client__telephone")
    list_select_related = ("client",)
    list_per_page = 50

    @admin.display(ordering="client__nom", description="Client")
    def client_full_name(self, obj):
        client = getattr(obj, "client", None)
        if not client:
            return "—"
        return f"{getattr(client, 'prenom', '')} {getattr(client, 'nom', '')}".strip() or "—"


@admin.register(VenteProduit)
class VenteProduitAdmin(admin.ModelAdmin):
    list_display = (
            "id",
            "produit_col",
            "quantite",
            "prix_vente_grammes",
            "remise",
            "autres",
            "montant_ht",
            "montant_total",
            "client_full_name",
            "numero_vente",
    )
    search_fields = (
        "vente__numero_vente",
        "vente__client__nom",
        "vente__client__prenom",
        "produit__nom",
    )
    list_select_related = ("vente", "vente__client", "produit")
    list_per_page = 50

    @admin.display(ordering="vente__numero_vente", description="N° vente")
    def numero_vente(self, obj):
        vente = getattr(obj, "vente", None)
        return getattr(vente, "numero_vente", "—") if vente else "—"

    @admin.display(ordering="vente__client__nom", description="Client")
    def client_full_name(self, obj):
        c = getattr(getattr(obj, "vente", None), "client", None)
        if not c:
            return "—"
        return f"{getattr(c, 'prenom', '')} {getattr(c, 'nom', '')}".strip() or "—"

    @admin.display(ordering="produit__nom", description="Produit")
    def produit_col(self, obj):
        p = getattr(obj, "produit", None) or getattr(obj, "article", None)
        if not p:
            return "—"
        return getattr(p, "nom", None) or str(p)


class PaiementLigneInline(admin.TabularInline):
    model = PaiementLigne
    extra = 0
    autocomplete_fields = ("mode_paiement", "compte_depot", "transaction_depot")
    fields = ("mode_paiement", "montant", "reference", "compte_depot", "transaction_depot")
    show_change_link = True


@admin.register(Facture)
class FactureAdmin(admin.ModelAdmin):
    list_display = (
        "numero_facture",
        "vente",
        "bijouterie",
        "type_facture",
        "montant_total",
        "total_paye_col",
        "reste_a_payer_col",
        "status",
        "date_creation",
        "est_reglee",
    )
    list_filter = ("status", "type_facture", "date_creation", "bijouterie")
    search_fields = (
        "numero_facture",
        "vente__numero_vente",
        "vente__client__nom",
        "vente__client__prenom",
    )
    readonly_fields = (
        "numero_facture",
        "date_creation",
        "total_paye_col",
        "reste_a_payer_col",
        "est_reglee",
    )
    list_select_related = ("vente", "bijouterie")
    list_per_page = 50

    @admin.display(description="Total payé")
    def total_paye_col(self, obj):
        return obj.total_paye

    @admin.display(description="Reste à payer")
    def reste_a_payer_col(self, obj):
        return obj.reste_a_payer


@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "facture",
        "numero_facture",
        "montant_total_paye",
        "cashier",
        "created_by",
        "date_paiement",
    )
    list_filter = ("date_paiement", "cashier")
    search_fields = (
        "facture__numero_facture",
        "facture__vente__numero_vente",
        "facture__vente__client__nom",
        "facture__vente__client__prenom",
        "created_by__username",
    )
    readonly_fields = ("date_paiement", "montant_total_paye")
    list_select_related = ("facture", "cashier", "created_by")
    inlines = [PaiementLigneInline]
    raw_id_fields = ("created_by",)
    list_per_page = 50

    @admin.display(ordering="facture__numero_facture", description="N° facture")
    def numero_facture(self, obj):
        facture = getattr(obj, "facture", None)
        return getattr(facture, "numero_facture", "—") if facture else "—"


@admin.register(PaiementLigne)
class PaiementLigneAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "paiement",
        "numero_facture",
        "mode_paiement",
        "montant_paye",
        "reference",
        "compte_depot",
        "transaction_depot",
    )
    list_filter = ("mode_paiement",)
    search_fields = (
        "paiement__facture__numero_facture",
        "mode_paiement__nom",
        "mode_paiement__code",
        "reference",
    )
    list_select_related = (
        "paiement",
        "paiement__facture",
        "mode_paiement",
        "compte_depot",
        "transaction_depot",
    )
    autocomplete_fields = ("paiement", "mode_paiement", "compte_depot", "transaction_depot")
    list_per_page = 50

    @admin.display(ordering="paiement__facture__numero_facture", description="N° facture")
    def numero_facture(self, obj):
        paiement = getattr(obj, "paiement", None)
        facture = getattr(paiement, "facture", None) if paiement else None
        return getattr(facture, "numero_facture", "—") if facture else "—"


@admin.register(ModePaiement)
class ModePaiementAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "nom",
        "code",
        "actif",
        "est_mode_depot",
        "necessite_reference",
        "ordre_affichage",
    )
    list_filter = ("actif", "est_mode_depot", "necessite_reference")
    search_fields = ("nom", "code")
    list_editable = ("actif", "ordre_affichage")
    list_per_page = 50
    