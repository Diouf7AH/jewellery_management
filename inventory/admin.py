from django.contrib import admin

from .models import Bucket, InventoryMovement


@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
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

    search_fields = (
        "id__exact",
        "reason",
        "produit__nom",
        "produit__sku",
        "lot__numero_lot",
        "lot__lot_code",
        "achat__numero_achat",
        "vente__numero_vente",
        "facture__numero_facture",
        "created_by__email",
        "created_by__username",
        "vendor__user__email",
        "vendor__user__username",
    )

    ordering = ("-occurred_at", "-id")

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

    readonly_fields = (
        "created_at",
        "created_by",
        "is_locked",
    )

    actions = ("freeze_selected", "unfreeze_selected")

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
                "stock_consumed",
            )
        }),
        ("Vendeur", {
            "fields": ("vendor",),
        }),
    )

    @admin.display(description="Source")
    def src_side(self, obj):
        if obj.src_bucket == Bucket.BIJOUTERIE and obj.src_bijouterie:
            return f"{obj.src_bucket} ({obj.src_bijouterie.nom})"
        return obj.src_bucket or "-"

    @admin.display(description="Destination")
    def dst_side(self, obj):
        if obj.dst_bucket == Bucket.BIJOUTERIE and obj.dst_bijouterie:
            return f"{obj.dst_bucket} ({obj.dst_bijouterie.nom})"
        return obj.dst_bucket or "-"

    @admin.display(description="Total")
    def total_cost_display(self, obj):
        try:
            if obj.unit_cost is None or obj.qty is None:
                return "-"
            return f"{(obj.unit_cost * obj.qty):.2f}"
        except Exception:
            return "-"

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
        n = 0
        for mv in queryset:
            if mv.is_locked:
                mv.is_locked = False
                mv.save(update_fields=["is_locked"])
                n += 1
        self.message_user(request, f"{n} mouvement(s) déverrouillé(s).")