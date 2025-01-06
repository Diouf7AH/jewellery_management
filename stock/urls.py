from django.urls import include, path

from stock import views as stock_views

urlpatterns = [
    # stock endpoint
    path('stock/add-produit-in-stock', stock_views.ProduitStockAPIView.as_view(), name='add-new-product-in-stock'),
    path('stock/produit-stock/<int:produit_id>/<int:fournisseur_id>', stock_views.ProduitStockDetailAPIView.as_view(), name='product-stock-detail'),
    path('stock/produit-stock/<int:pk>/get-product-update-stock', stock_views.UpdateStockAPIView.as_view(), name='get-update-stock'),
    path('stock/produit-stock/update-stock', stock_views.UpdateStockAPIView.as_view(), name='update-stock'),
    
]