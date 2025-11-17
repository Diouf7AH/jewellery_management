# from django.urls import include, path

# from sale import views as sale_views
# from stock import views as stock_views
# from store import views as store_views

# urlpatterns = [
#     #sale endpoint
#     path('vente/add-vente', sale_views.VenteProduitCreateView.as_view(), name='creation-vente'),
    
#     path('vente-produit', sale_views.VentProduitsListAPIView.as_view(), name='vente-produit-list'),
#     # path('paiement/update/<int:pk>', sale_views.PaiementUpdateView.as_view(), name='paiement-update'),
    
#     path('recherche-facture/<str:numero_facture>', sale_views.RechercherFactureView.as_view(), name='Recherche-facture-par-numero'),
#     path('List-factures-a-payer', sale_views.ListFactureView.as_view(), name='list-factures-a-payer'),
#     path('paiement-facture/<str:facture_numero>', sale_views.PaiementFactureView.as_view(), name='Paiement-facture-par-numero'),
    
#     # path('facture/<str:facture_numero>/pdf', sale_views.GenerateFacturePDF.as_view(), name='generate-facture-pdf'),
    
#     # path('update-payment-status/<int:id>', sale_views.PaiementUpdateView.as_view(), name='paiement-update'),
#     # path('vente-produit/<slug:slug>', sale_views.VenteProduitDetailAPIView.as_view(), name='vente-produit-detail'),
#     # path('facture/', sale_views.FactureListAPIView.as_view(), name='facture-list'),
#     # path('facture-update-status/<str:slug>', sale_views.FactureDetailAPIView.as_view(), name='facture-detail'),
# ]