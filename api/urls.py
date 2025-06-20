from django.urls import include, path

# Authentification
from userauths import views as userauths_views


# Vente, achat, stock
from sale import views as sale_views
from purchase import views as achat_views
from stock import views as stock_views

# Produits & structure
from store import views as store_views
from vendor import views as vendor_views
from compte_depot import views as compte_depot_views
from order import views as order_views

urlpatterns = [
    
    # Store API Endpoints
    # path('', userauths_views.getRoutes),
    
    path('dashboard/vendor/dashboard', vendor_views.VendorDashboardView.as_view(), name='dashboard-vendeur'),
    path('dashboard/achat/dashboard', achat_views.AchatDashboardView.as_view(), name='dashboard-achat'),
    # path('vendor/me/', vendor_views.VendorMeView.as_view(), name='vendor-me'),
    
    path('vendor/dashboard/profile', vendor_views.VendorProfileView.as_view(), name='vendor-profile'),
    path('vendor/produits/', vendor_views.VendorProduitListView.as_view(), name='vendor-produits'),
    # Pour l’utilisateur connecté
    # Pour un admin qui consulte un vendeur par ID
    path('vendor/<int:user_id>/', vendor_views.VendorProfileView.as_view(), name='admin-vendor-view'),
    path('vendor/<int:user_id>/toggle-status/', vendor_views.ToggleVendorStatusView.as_view(), name='toggle-vendor-status'),
    path('api/ventes/rapport-pdf/', vendor_views.RapportVentesMensuellesPDFView.as_view(), name='rapport-ventes-pdf'),
    
    # path('register', userauths_views.UserRegistrationView.as_view(), name='register'),
    path('login', userauths_views.UserLoginView.as_view(), name='login'),
    path('logout/', userauths_views.UserLogoutView.as_view(), name='logout'),
    # path('changepassword/<int:pk>', userauths_views.UserChangePasswordView.as_view(), name='changepassword'),
    path('user/register', userauths_views.UserRegistrationView.as_view(), name='register'),
    
    path('verify-email/', userauths_views.EmailVerificationView.as_view(), name='verify-email'),
    # path('resend-confirmation/', userauths_views.ResendConfirmationView.as_view(), name='resend-confirmation'),
    # path('resend-confirmation-form/', userauths_views.resend_confirmation_form, name='resend-confirmation-form'),
    # path('resend-confirmation-submit/', userauths_views.resend_confirmation_submit, name='resend-confirmation-submit'),
    
    path('user/<int:pk>',userauths_views.UserDetailUpdateView.as_view(),name="detail"),
    path('user/list',userauths_views.UsersView.as_view(),name="users_list"),
    
    path('role/list',userauths_views.ListRolesAPIView.as_view(),name="list-roles"),
    path('role/create',userauths_views.CreateRoleAPIView.as_view(),name="create-role"),
    path('role/get-one/<int:pk>',userauths_views.GetOneRoleAPIView.as_view(),name="get-one-role"),
    path('role/update/<int:pk>',userauths_views.UpdateRoleAPIView.as_view(),name="update-role"),
    path('role/delete/<int:pk>',userauths_views.DeleteRoleAPIView.as_view(),name="delete-role"),
    
    path('user/profile/<user_id>', userauths_views.ProfileView.as_view(), name='profile'),
    
    path('password_reset/', include('django_rest_passwordreset.urls')),
    # Validate Token
    path('validate-token',userauths_views.ValidateTokenView.as_view(),name="validate_token"),
    
    # STORE
    
    #Bijouterie
    path('bijouterie/list/', store_views.BijouterieListAPIView.as_view(), name='bijouterie_list'),
    path('bijouterie/create', store_views.BijouterieCreateAPIView.as_view(), name='bijouterie_create'),
    path('bijouterie/update/<int:pk>', store_views.BijouterieUpdateAPIView.as_view(), name='bijouterie_update'),
    path('bijouterie/delete/<int:pk>', store_views.BijouterieDeleteAPIView.as_view(), name='bijouterie_delete'),
    #Categorie
    path('categorie/list/', store_views.CategorieListAPIView.as_view(), name='categorie-list'),
    path('categorie/create', store_views.CategorieCreateAPIView.as_view(), name='categorie-create'),
    path('categorie/update/<int:pk>', store_views.CategorieUpdateAPIView.as_view(), name='categorie_put'),
    path('categorie/delete/<int:pk>', store_views.CategorieDeleteAPIView.as_view(), name='categorie_delete'),
    # Purete
    path('purete/list/', store_views.PureteListAPIView.as_view(), name='purete_list'),
    path('purete/create', store_views.PureteCreateAPIView.as_view(), name='purete_create'),
    path('purete/update/<int:pk>', store_views.PureteUpdateAPIView.as_view(), name='purity_update'),
    path('purete/delete/<int:pk>', store_views.PureteDeleteAPIView.as_view(), name='purety_Delete'),
    # Marque
    path('marque/list/', store_views.MarqueListAPIView.as_view(), name='marque_list'),
    path('marque/create', store_views.MarqueCreateAPIView.as_view(), name='marque_create'),
    path('marque/update/<int:pk>', store_views.MarqueUpdateAPIView.as_view(), name='marque_update'),
    path('marque/delete/<int:pk>', store_views.MarqueDeleteAPIView.as_view(), name='marque_delete'),
    # Model
    path('modele/list/', store_views.ModeleListAPIView.as_view(), name='modele_list'),
    path('modele/create', store_views.ModeleCreateAPIView.as_view(), name='modele_create'),
    path('modele/update/<int:pk>', store_views.ModeleUpdateAPIView.as_view(), name='modele_put'),
    path('modele/delete/<int:pk>', store_views.ModeleDeleteAPIView.as_view(), name='modele_delete'),
    # Product
    path('produit/list/', store_views.ProduitListAPIView.as_view(), name='product_list'),
    path('produit/create', store_views.ProduitCreateAPIView.as_view(), name='product_create'),
    path('produit/update/<int:pk>', store_views.ProduitUpdateAPIView.as_view(), name='product_update'),
    path('produit/delete/<int:pk>', store_views.ProduitDeleteAPIView.as_view(), name='product_delete'),
    # path('gallery/by-produit/', store_views.GetGalleryByProduitAPIView.as_view(), name='get-gallery-by-produit'),
    path('produit/recent-list', store_views.ProduitRecentListAPIView.as_view(), name='produit-recent-list'),
    
    path('produit/<int:pk>/qr', store_views.QRCodeView.as_view(), name='product-qr-code'),
    # path('produit/export/qr-codes/', store_views.ExportQRCodeExcelAPIView.as_view(), name='export-qr-codes'),
    path('produit/export/qr-code/<slug:slug>', store_views.ExportOneQRCodeExcelAPIView.as_view(), name='export-one-qr-code'),
    # path('api/products/<int:pk>/qrcode/', ProductQRCodeView.as_view(), name='product-qrcode'),
    path("produit/<slug:slug>/", store_views.ProduitDetailSlugView.as_view(), name="produit-detail-slug"),
    
    # END STORE
    
    #FOURNISEUR
    path('fournisseur/get-one/<int:pk>', achat_views.FournisseurGetView.as_view(), name='fournisseur_get_one'),
    path('fournisseur/update/<int:pk>', achat_views.FournisseurUpdateView.as_view(), name='fournisseur_update_one'),
    path('fournisseur/list/', achat_views.FournisseurListView.as_view(), name='fournisseur-list'),
    
    # ACHAT
    path('achat-produit/get-one-achat/<int:pk>', achat_views.AchatProduitGetOneView.as_view(), name='get_achat_produit'),
    path('achat-produit/add-achat', achat_views.AchatProduitCreateView.as_view(), name='achat_add_achat'),
    # path('achat-produit/update-achat/<int:achat_id>', achat_views.AchatUpdateAPIView.as_view(), name='achat_update_achat'),
    # path('achat-produit/update-achat-produit/<int:achatproduit_id>', achat_views.AchatUpdateAchatProduitAPIView.as_view(), name='achat_produit_update_achat'),
    path('achat-produit/<int:achatproduit_id>/produits/<int:achat_id>', achat_views.AchatProduitUpdateAPIView.as_view(),name='achat-produit-update'),
    path('achat-produit/list-achat', achat_views.AchatListView.as_view(), name='achat_produit_list'),
    # path('achat-produit/<int:pk>/facture-pdf', achat_views.AchatPDFView.as_view(), name='achat-facture-pdf'),
    path('achat-produit/<int:pk>/facture-pdf', achat_views.AchatProduitPDFView.as_view(), name='achat-produit-facture-pdf'),
    # END ACHAT
    
    
    #VENDOR
    path('vendor/list/', vendor_views.ListVendorAPIView.as_view(), name='vendor_list'),
    path('vendor/add-vendor', vendor_views.CreateVendorView.as_view(), name='add_vendor'),
    path('vendor/association-produit-to-vendor', vendor_views.VendorProduitAssociationAPIView.as_view(), name='association-du-produit-au-vendor'),
    path('vendor/find', vendor_views.RetrieveVendorView.as_view(), name='vendor-find'),
    path('vendor/<int:user_id>/update-status', vendor_views.UpdateVendorStatusAPIView.as_view(), name='update_vendor_status'),
    # END VENDOR
    
    
    # STOCK
    # stock endpoint
    # path('stock/add-produit-in-stock', stock_views.ProduitStockAPIView.as_view(), name='add-new-product-in-stock'),
    # path('stock/produit-stock/<int:produit_id>/<int:fournisseur_id>', stock_views.ProduitStockDetailAPIView.as_view(), name='product-stock-detail'),
    # path('stock/produit-stock/<int:pk>/get-product-update-stock', stock_views.UpdateStockAPIView.as_view(), name='get-update-stock'),
    # path('stock/produit-stock/update-stock', stock_views.UpdateStockAPIView.as_view(), name='update-stock'),
    # path('stock/add-commande-stock', stock_views.CommandeFournisseurView.as_view(), name='Stock-commande'),
    # path('commande-fournisseur/<int:commande_id>', stock_views.CommandeFournisseurView.as_view(), name='commande-fournisseur-detail'),
    # END STOCK
    
    # SALE
    path('vente/add-vente', sale_views.VenteProduitCreateView.as_view(), name='creation-vente'),
    
    path('vente/list-produit', sale_views.VentListAPIView.as_view(), name='vente-produit-list'),
    
    path('facture/recherche-facture/<str:numero_facture>', sale_views.RechercherFactureView.as_view(), name='Recherche-facture-par-numero'),
    path('facture/List-factures-a-payer', sale_views.ListFactureView.as_view(), name='list-factures-a-payer'),
    path('facture/paiement-facture/<str:facture_numero>', sale_views.PaiementFactureView.as_view(), name='Paiement-facture-par-numero'),
    # END STOCK
    
    # BANK
    path('compte-depot/lister-tous-comptes-depot', compte_depot_views.ListerTousComptesAPIView.as_view(), name='lister-tous-comptes-depot'),
    path('compte-depot/Lister-toutes-transactions', compte_depot_views.ListerToutesTransactionsAPIView.as_view(), name='Lister-toutes-transactions'),
    path('compte-depot/client-compte-depot/create/', compte_depot_views.CreateClientAndCompteView.as_view(), name='create-client-compte-depot'),
    path('compte-depot/get-sold-view', compte_depot_views.GetSoldeAPIView.as_view(), name='get-sold-view'),
    path('compte-depot/depot-view', compte_depot_views.DepotView.as_view(), name='depot-view'),
    path('compte-depot/retrait-view', compte_depot_views.RetraitView.as_view(), name='retrait-view'),
    # END BANK
    
    path('commande-client/create/', order_views.CreateCommandeClientView.as_view(), name='create-commande-client'),
    path('commandes/', order_views.ListCommandeClientView.as_view(), name='liste-commandes'),
    path('commandes/<str:numero_commande>/modifier/', order_views.UpdateCommandeByNumeroView.as_view(), name='modifier-commande-par-numero'),
    path('commandes/<str:numero_commande>/changer-statut/', order_views.ChangeCommandeStatusView.as_view(), name='changer-statut-commande'),
    
    # path('', include('userauths.urls')),
    # path('', include('store.urls')),
    # path('', include('stock.urls')),
    # path('', include('sale.urls')),
    
]