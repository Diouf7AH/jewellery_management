from django.urls import include, path

from sale import views as sale_views
from stock import views as stock_views
from store import views as store_views
from userauths import views as userauths_views

urlpatterns = [
    
    # Store API Endpoints
    # path('', userauths_views.getRoutes),
    
    path('register', userauths_views.UserRegistrationView.as_view(), name='register'),
    path('login', userauths_views.UserLoginView.as_view(), name='login'),
    # path('changepassword/<int:pk>', userauths_views.UserChangePasswordView.as_view(), name='changepassword'),
    path('user/<int:pk>',userauths_views.UserDetailUpdateView.as_view(),name="detail"),
    path('user/list',userauths_views.UsersView.as_view(),name="users"),
    
    path('role/get-or-create',userauths_views.RoleListCreateAPIView.as_view(),name="role_get_create"),
    path('role/deatail/<int:pk>', userauths_views.RoleDetailAPIView.as_view(), name='role_detail'),
    
    path('user/profile/<user_id>', userauths_views.ProfileView.as_view(), name='profile'),
    
    path('password_reset', include('django_rest_passwordreset.urls', namespace='password_reset')),
    
    # Validate Token
    path('validate-token',userauths_views.ValidateTokenView.as_view(),name="validate_token"),
    
    # STORE
    
    #Bijouterie
    path('bijouterie/list', store_views.BijouterieListCreateAPIView.as_view(), name='bijouterie'),
    path('bijouterie/<slug:slug>', store_views.BijouterieDetailAPIView.as_view(), name='bijouterie-detail'),
    #Categorie
    path('categorie/list', store_views.CategorieListCreateAPIView.as_view(), name='categorie'),
    path('categorie/<slug:slug>', store_views.CategorieDetailAPIView.as_view(), name='categorie-detail'),
    # # Type
    # path('produits/types', store_views.TypeListCreateAPIView.as_view(), name='type-list-create'),
    # path('produits/types/<int:pk>', store_views.TypeDetailAPIView.as_view(), name='type-detail'),
    # Purete
    path('purete/list', store_views.PureteListCreateAPIView.as_view(), name='purete-list-create'),
    path('purete/<int:pk>', store_views.PureteDetailAPIView.as_view(), name='purete-detail'),
    # Marque
    path('marque/list', store_views.MarqueListCreateAPIView.as_view(), name='marque-list-create'),
    path('marque/<int:pk>', store_views.MarqueDetailAPIView.as_view(), name='marque-detail'),
    # Model
    path('modele/list', store_views.ModeleListCreateAPIView.as_view(), name='modele-list-create'),
    path('modele/<int:pk>', store_views.ModeleDetailAPIView.as_view(), name='modele-detail'),
    # Product
    path('produit/list', store_views.ProduitListCreateAPIView.as_view(), name='product-list-create'),
    path('produit/<int:pk>', store_views.ProduitDetailAPIView.as_view(), name='product-detail'),
    path('produit/<slug:slug>/qr', store_views.QRCodeView.as_view(), name='product-qr-code'),
    
    # END STORE
    
    # STOCK
     # stock endpoint
    path('stock/add-produit-in-stock', stock_views.ProduitStockAPIView.as_view(), name='add-new-product-in-stock'),
    path('stock/produit-stock/<int:produit_id>/<int:fournisseur_id>', stock_views.ProduitStockDetailAPIView.as_view(), name='product-stock-detail'),
    path('stock/produit-stock/<int:pk>/get-product-update-stock', stock_views.UpdateStockAPIView.as_view(), name='get-update-stock'),
    path('stock/produit-stock/update-stock', stock_views.UpdateStockAPIView.as_view(), name='update-stock'),
    
    # END STOCK
    
    # SALE
    path('vente/add-vente', sale_views.VenteProduitCreateView.as_view(), name='creation-vente'),
    
    path('vente/list-produit', sale_views.VentProduitsListAPIView.as_view(), name='vente-produit-list'),
    
    path('facture/recherche-facture/<str:numero_facture>', sale_views.RechercherFactureView.as_view(), name='Recherche-facture-par-numero'),
    path('facture/List-factures-a-payer', sale_views.ListFactureView.as_view(), name='list-factures-a-payer'),
    path('facture/paiement-facture/<str:facture_numero>', sale_views.PaiementFactureView.as_view(), name='Paiement-facture-par-numero'),
    
    # END STOCK
    
    # path('', include('userauths.urls')),
    # path('', include('store.urls')),
    # path('', include('stock.urls')),
    # path('', include('sale.urls')),
    
]