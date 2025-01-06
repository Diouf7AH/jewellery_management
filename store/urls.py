from django.urls import include, path

from sale import views as sale_views
from stock import views as stock_views
from store import views as store_views

urlpatterns = [
    
    #Bijouterie
    path('bijouteries', store_views.BijouterieListCreateAPIView.as_view(), name='bijouterie'),
    path('bijouterie/<slug:slug>', store_views.BijouterieDetailAPIView.as_view(), name='bijouterie-detail'),
    
    
    #Categorie
    path('categories', store_views.CategorieListCreateAPIView.as_view(), name='categorie'),
    path('categorie/<slug:slug>', store_views.CategorieDetailAPIView.as_view(), name='categorie-detail'),
    
    # # Type
    # path('produits/types', store_views.TypeListCreateAPIView.as_view(), name='type-list-create'),
    # path('produits/types/<int:pk>', store_views.TypeDetailAPIView.as_view(), name='type-detail'),
    
    # Purete
    path('puretes', store_views.PureteListCreateAPIView.as_view(), name='purete-list-create'),
    path('purete/<int:pk>', store_views.PureteDetailAPIView.as_view(), name='purete-detail'),
    
    # Marque
    path('marques', store_views.MarqueListCreateAPIView.as_view(), name='marque-list-create'),
    path('marque/<int:pk>', store_views.MarqueDetailAPIView.as_view(), name='marque-detail'),

    # Model
    path('modeles', store_views.ModeleListCreateAPIView.as_view(), name='modele-list-create'),
    path('modele/<int:pk>', store_views.ModeleDetailAPIView.as_view(), name='modele-detail'),

    # Product
    path('produits', store_views.ProduitListCreateAPIView.as_view(), name='product-list-create'),
    path('produit/<int:pk>', store_views.ProduitDetailAPIView.as_view(), name='product-detail'),
    path('produit/<slug:slug>/qr', store_views.QRCodeView.as_view(), name='product-qr-code'),

]