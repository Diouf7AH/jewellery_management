# Register your models here.
from django.contrib import admin
from django.db.models import (Count, DecimalField, ExpressionWrapper, F,
                              IntegerField, Sum)

from store.models import Produit

from .models import Achat, Fournisseur, Lot


@admin.register(Fournisseur)
class FournisseurAdmin(admin.ModelAdmin):
    list_display = ('id', 'nom', 'prenom', 'address', 'telephone')
    search_fields = ('nom',)


@admin.register(Lot)
class LotAdmin(admin.ModelAdmin):
    list_display = ("numero_lot", "received_at", "achat", "nb_lignes_admin", "qte_totale_admin", "poids_total_admin")
    search_fields = ("numero_lot", "description", "achat__numero_achat", "achat__fournisseur__nom")
    list_filter = ("received_at",)

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("achat", "achat__fournisseur")
        poids_total_expr = ExpressionWrapper(
            F("lignes__quantite_total") * F("lignes__produit__poids"),
            output_field=DecimalField(max_digits=18, decimal_places=3)
        )
        return (qs
                .annotate(
                    nb_lignes=Count("lignes", distinct=True),
                    qte_totale=Sum("lignes__quantite_total", output_field=IntegerField()),
                    poids_total=Sum(poids_total_expr),
                ))

    def nb_lignes_admin(self, obj): return obj.nb_lignes
    def qte_totale_admin(self, obj): return obj.qte_totale
    def poids_total_admin(self, obj): return obj.poids_total


# @admin.register(Achat)
# class AchatAdmin(admin.ModelAdmin):
#     # list_display = ('id', 'produit', 'fournisseur', 'poids', 'prix_achat_gramm', 'quantite', 'total_prix_achat', 'date_ajout')
#     # list_display = ('id', 'produit', 'fournisseur','produit__categorie__nom','produit__marque__marque', 'produit__purete__purete', 'produit__poids', 'produit__prix_vente_grammes','calcul_total_poids_achat','prix_achat_gramme', 'calcul_total_achat', 'quantite', 'date_ajout', 'date_modification',)
#     list_display=('id', 'fournisseur', 'montant_total', 'created_at')
#     search_fields = ('fournisseur',)
#     # exclude = ('total_prix_achat', 'date_ajout',)
#     # search_fields = ('produit__nom', 'fournisseur__nom' , 'produit__categorie__nom')
    
#     # # call faction in model
#     # def calcul_total_poids_achat(self, obj):
#     #     return obj.calcul_total_poids_achat()
    
#     # def calcul_total_achat(self, obj):
#     #     return obj.calcul_total_achat()

@admin.register(Achat)
class AchatAdmin(admin.ModelAdmin):
    list_display = ['numero_achat', 'fournisseur', 'created_at', 'montant_total_ht', 'montant_total_ttc']
    search_fields = ['fournisseur__nom', 'fournisseur__telephone']
    list_filter = ['created_at']




