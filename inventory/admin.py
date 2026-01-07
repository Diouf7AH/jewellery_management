# inventory/admin.py
from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import Bucket, InventoryMovement, MovementType


@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    # ---- Colonnes affichées dans la liste ----
    list_display = (
        "id",
        "occurred_at",
        "movement_type",
        "produit",
        "qty",
        "unit_cost",
        "total_cost_display",
        "src_side",
        "dst_side",
        "lot",
        "achat",
        "vente",
        "facture",
        "vendor",
        "is_locked",
        "created_by",
    )

    # ---- Filtres à droite ----
    list_filter = (
        "movement_type",
        "src_bucket",
        "dst_bucket",
        "src_bijouterie",
        "dst_bijouterie",
        "vendor",
        "is_locked",
        ("occurred_at", admin.DateFieldListFilter),
        ("created_at", admin.DateFieldListFilter),
    )

    # ---- Recherche ----
    search_fields = (
        "id",
        "reason",
        "produit__nom",
        "produit__sku",
        "lot__numero_lot",        # si ton Lot a numero_lot
        "lot__lot_code",          # si ton Lot a lot_code
        "achat__numero_achat",    # si ton Achat a numero_achat
        "vente__numero_vente",    # si Vente a numero_vente
        "facture__numero_facture",
        "created_by__email",
        "created_by__username",
        "vendor__user__email",
        "vendor__user__username",
    )

    # ---- Tri ----
    ordering = ("-occurred_at", "-id")

    # ---- Optimisation perf ----
    list_select_related = (
        "produit",
        "lot",
        "achat",
        "vente",
        "facture",
        "src_bijouterie",
        "dst_bijouterie",
        "vendor",
        "created_by",
    )

    # ---- Champs non éditables (recommandé pour l’audit) ----
    readonly_fields = (
        "sale_out_key",
        "created_at",
    )

    # ---- Actions ----
    actions = ("freeze_selected", "unfreeze_selected")

    # ---- Groupement des champs dans la fiche ----
    fieldsets = (
        ("Infos", {
            "fields": (
                "produit",
                "movement_type",
                "qty",
                "unit_cost",
                "reason",
                "occurred_at",
                "created_by",
                "created_at",
                "is_locked",
            )
        }),
        ("Source / Destination", {
            "fields": (
                ("src_bucket", "src_bijouterie"),
                ("dst_bucket", "dst_bijouterie"),
            )
        }),
        ("Liens Achats", {
            "fields": (
                "achat",
                "achat_ligne",
                "lot",
            )
        }),
        ("Liens Ventes / Facturation", {
            "fields": (
                "facture",
                "vente",
                "vente_ligne",
                "sale_out_key",
                "stock_consumed",
            )
        }),
        ("Vendeur", {
            "fields": ("vendor",),
        }),
    )

    # ---- Rendu helpers ----
    @admin.display(description="Source")
    def src_side(self, obj: InventoryMovement):
        if obj.src_bucket == Bucket.BIJOUTERIE and obj.src_bijouterie:
            return f"{obj.src_bucket} ({obj.src_bijouterie.nom})"
        return obj.src_bucket or "-"

    @admin.display(description="Destination")
    def dst_side(self, obj: InventoryMovement):
        if obj.dst_bucket == Bucket.BIJOUTERIE and obj.dst_bijouterie:
            return f"{obj.dst_bucket} ({obj.dst_bijouterie.nom})"
        return obj.dst_bucket or "-"

    @admin.display(description="Total", ordering="unit_cost")
    def total_cost_display(self, obj: InventoryMovement):
        # utilise ta propriété total_cost (qty * unit_cost)
        try:
            v = obj.total_cost
        except Exception:
            v = None
        return "-" if v is None else f"{v:.2f}"

    # ---- Actions freeze/unfreeze ----
    @admin.action(description="Verrouiller (freeze) les mouvements sélectionnés")
    def freeze_selected(self, request, queryset):
        n = 0
        for mv in queryset:
            if not mv.is_locked:
                mv.freeze(by_user=request.user)
                n += 1
        self.message_user(request, f"{n} mouvement(s) verrouillé(s).")

    @admin.action(description="Déverrouiller (unfreeze) les mouvements sélectionnés (⚠️ à éviter)")
    def unfreeze_selected(self, request, queryset):
        # ⚠️ en prod on évite, mais utile en dev
        n = queryset.update(is_locked=False)
        self.message_user(request, f"{n} mouvement(s) déverrouillé(s).")
        