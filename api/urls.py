from django.urls import include, path

from compte_depot import views as compte_depot_views
from inventory import views as inv_views
from order import views as order_views
from purchase import views as achat_views
# Vente, achat, stock
from sale import views as sale_views
from staff import views as staff_views
from stock import views as stock_views
# Produits & structure
from store import views as store_views
# Authentification
from userauths import views as userauths_views
from vendor import views as vendor_views

urlpatterns = [
    
    # Store API Endpoints
    # path('', userauths_views.getRoutes),
    
    path("vendor/dashboard/", vendor_views.VendorDashboardView.as_view(), name="vendor-dashboar"),
    # path('dashboard/achat/dashboard', achat_views.AchatDashboardView.as_view(), name='dashboard-achat'),
    # path('vendor/me/', vendor_views.VendorMeView.as_view(), name='vendor-me'),
    
    # path('vendor/dashboard/profile', vendor_views.VendorProfileView.as_view(), name='vendor-profile'),
    path('vendor/produits/', vendor_views.VendorProduitListView.as_view(), name='vendor-produits'),
    path("manager/vendor/produits/", vendor_views.VendorProduitListView.as_view(), name="manager-vendor-produits"),
    # Pour l’utilisateur connecté
    # Pour un admin qui consulte un vendeur par ID
    # path('vendor/<int:user_id>/', vendor_views.VendorProfileView.as_view(), name='admin-vendor-view'),
    # path('vendor/<int:user_id>/toggle-status/', vendor_views.ToggleVendorStatusView.as_view(), name='toggle-vendor-status'),
    
    # path('register', userauths_views.UserRegistrationView.as_view(), name='register'),
    path('login', userauths_views.UserLoginView.as_view(), name='login'),
    path('logout/', userauths_views.UserLogoutView.as_view(), name='logout'),
    # path('changepassword/<int:pk>', userauths_views.UserChangePasswordView.as_view(), name='changepassword'),
    path('user/register', userauths_views.UserRegistrationView.as_view(), name='register'),
    path("auth/resend-verification/", userauths_views.ResendVerificationEmailView.as_view(), name="resend-verification"),
    
    path('verify-email/', userauths_views.EmailVerificationView.as_view(), name='verify-email'),
    # path('resend-confirmation/', userauths_views.ResendConfirmationView.as_view(), name='resend-confirmation'),
    path('resend-confirmation-form/', userauths_views.resend_confirmation_form, name='resend-confirmation-form'),
    path('resend-confirmation-submit/', userauths_views.resend_confirmation_submit, name='resend-confirmation-submit'),
    
    path('user/<int:pk>',userauths_views.UserDetailUpdateView.as_view(),name="detail"),
    path('user/list',userauths_views.UsersView.as_view(),name="users_list"),
    
    path('role/list',userauths_views.ListRolesAPIView.as_view(),name="list-roles"),
    path('role/create',userauths_views.CreateRoleAPIView.as_view(),name="create-role"),
    path('role/get-one/<int:pk>',userauths_views.GetOneRoleAPIView.as_view(),name="get-one-role"),
    path('role/update/<int:pk>',userauths_views.UpdateRoleAPIView.as_view(),name="update-role"),
    path('role/delete/<int:pk>',userauths_views.DeleteRoleAPIView.as_view(),name="delete-role"),
    
    # path('user/profile/<user_id>', userauths_views.ProfileView.as_view(), name='profile'),
    path("me/profile/", userauths_views.ProfileView.as_view(), name="me-profile"),
    
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
    # path('categorie/update/<int:pk>', store_views.CategorieUpdateAPIView.as_view(), name='categorie_put'),
    path('categorie/update-par-nom/<str:nom>/', store_views.CategorieUpdateAPIView.as_view(), name='update_categorie_par_nom'),
    path('categorie/delete/<int:pk>', store_views.CategorieDeleteAPIView.as_view(), name='categorie_delete'),
    # Purete
    path('purete/list/', store_views.PureteListAPIView.as_view(), name='purete_list'),
    path('purete/create', store_views.PureteCreateAPIView.as_view(), name='purete_create'),
    path('purete/update/<int:pk>', store_views.PureteUpdateAPIView.as_view(), name='purity_update'),
    path('purete/delete/<int:pk>', store_views.PureteDeleteAPIView.as_view(), name='purety_Delete'),
    # Marque
    path('marque/list/', store_views.MarqueListAPIView.as_view(), name='marque_list'),
    path('marque-purete/list/', store_views.ListMarquePureteView.as_view(), name='list-marque-purete'),
    path('marque-purete/history-prix/', store_views.MarquePureteHistoryListView.as_view(), name='marque-purete-history-prix'),
    # path('marque/create', store_views.MarqueCreateAPIView.as_view(), name='marque_create'),
    path("marque/marque-puretes/", store_views.CreateMarquePureteView.as_view(), name="create-marque-puretes"),
    path('marque/update/<int:pk>', store_views.MarqueUpdateAPIView.as_view(), name='marque_update'),
    path('marque/delete/<int:pk>', store_views.MarqueDeleteAPIView.as_view(), name='marque_delete'),
    # Model
    path('modele/list/', store_views.ModeleListAPIView.as_view(), name='modele_list'),
    path('modele/create', store_views.ModeleCreateAPIView.as_view(), name='modele_create'),
    path('modele/update/<int:pk>', store_views.ModeleUpdateAPIView.as_view(), name='modele_put'),
    path('modele/delete/<int:pk>', store_views.ModeleDeleteAPIView.as_view(), name='modele_delete'),
    #categorie-Modeles
    # path('categorie-modeles/update-modeles/', store_views.CategorieUpdateModelesView.as_view(), name='update-modeles'),
    # path('categorie-modeles/update-modeles/', store_views.ModeleUpdateView.as_view(), name='Ajouter-de-nouveaux-modeles'),
    
    # selecte option
    # path('marque-par-categorie/', store_views.PureteParCategorieAPIView.as_view(), name='puretes-par-categorie'),
    # path('marques-par-categorie/', store_views.MarqueParCategorieAPIView.as_view(), name='marques-par-categorie'),
    # path('modeles-par-marque/', store_views.ModeleParMarqueAPIView.as_view(), name='modeles-par-marque'),
    
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
    path("achat/liste/", achat_views.AchatListView.as_view(), name="achat-list"),
    path('achat/get-one-achat/<int:pk>', achat_views.AchatProduitGetOneView.as_view(), name='get_achat_produit'),
    # path("achat/lots/", achat_views.LotListView.as_view(), name="lots-list"),
    path("achat/lots/<int:pk>", achat_views.LotDetailView.as_view(), name="lot-detail"),
    path("achat/arrivage", achat_views.ArrivageCreateView.as_view(), name="arrivage-create"),
    path("achat/lots/", achat_views.LotListView.as_view(), name="lot-list"),
    path("achat/arrivage/<int:lot_id>/meta/", achat_views.ArrivageMetaUpdateView.as_view(), name="arrivage-meta-update"),
    path("achat/arrivage/<int:lot_id>/adjustments/", achat_views.ArrivageAdjustmentsView.as_view(), name="arrivage-adjustments"),
    path("achat/produit-lines/", achat_views.ProduitLineWithInventoryListView.as_view(),name="produitline-list",),
    
    
    # path("achat/lots/export/csv", achat_views.LotExportCSVView.as_view(), name="lots-export-csv"),
    # path("achat/lots/export/xlsx", achat_views.LotExportExcelView.as_view(), name="lots-export-xlsx"),
    # path('achat-produit/create-achats', achat_views.AchatCreateView.as_view(), name='achats-create'),
    # path("achats-produit-update/<int:achat_id>/", achat_views.AchatUpdateView.as_view(), name="achats-update"),
    path("stocks/list", stock_views.StockListView.as_view(), name="stock-list"),
    path("stocks/transfer/reserve-to-bijouterie", stock_views.ReserveToBijouterieTransferView.as_view(), name="reserve-to-bijouterie"),
    # path("stock/affectations/reserve", achat_views.StockReserveAffectationView.as_view(), name="stock-reserve-affect"),
    path("stocks/transfer/bijouterie-to-vendor", stock_views.BijouterieToVendorTransferView.as_view(),name="bijouterie-to-vendor"),
    # path("stocks/summary", stock_views.StockSummaryView.as_view(), name="stock-summary"),
    
    # path("achats/<int:achat_id>/cancel", achat_views.AchatCancelView.as_view(), name="achat-cancel"),
    # path('achat-produit/update-achat/<int:achat_id>', achat_views.AchatUpdateAPIView.as_view(), name='achat_update_achat'),
    # path('achat-produit/update-achat-produit/<int:achatproduit_id>', achat_views.AchatUpdateAchatProduitAPIView.as_view(), name='achat_produit_update_achat'),
    # path('achat-produit/<int:achatproduit_id>/produits/<int:achat_id>', achat_views.AchatProduitUpdate    APIView.as_view(),name='achat-produit-update'),
    # path('achat-produit/list-achat', achat_views.AchatListView.as_view(), name='achat_produit_list'),
    # path('achat-produit/<int:pk>/facture-pdf', achat_views.AchatPDFView.as_view(), name='achat-facture-pdf'),
    # path('achat-produit/<int:pk>/facture-pdf', achat_views.AchatProduitPDFView.as_view(), name='achat-produit-facture-pdf'),
    # END ACHAT
    
    # INVENTORY
    # Journal détaillé des mouvements
     # 🔹 Journal détaillé des mouvements (grand livre inventaire)
    path("inventory/movements/", inv_views.InventoryMovementListView.as_view(),name="movement-list",),
    # 🔹 Tableau d’inventaire par PRODUIT ET BIJOUTERIE
    # path("inventory/table-per-bijouterie/", inv_views.InventoryMovementTablePerBijouterieView.as_view(),name="table-per-bijouterie",),
    # 🔹 V3 combinée : inventaire bijouterie + vendor (par produit)
    # path("inventory/bijouterie-vendor/", inv_views.InventoryBijouterieVendorTableView.as_view(),name="bijouterie-vendor-table",),
    # 🔹 Stats d’allocations par vendor / année
    # path("inventory/vendors/<int:vendor_id>/allocations/", inv_views.VendorAllocationStatsView.as_view(),name="vendor-allocation-stats",),
    path("inventory/produit-lines/", inv_views.ProduitLineWithInventoryListView.as_view(),name="inventory-produitline-list",),
    # END INVENTORY
    
    # staff
    path('staff/add-staff', staff_views.CreateStaffMemberView.as_view(), name='add_staff'),
    path("staff/<int:staff_id>/update", staff_views.UpdateStaffView.as_view(), name="staff-update"),
    
    #VENDOR
    path('vendor/list/', vendor_views.ListVendorAPIView.as_view(), name='vendor_list'),
    # path('vendor/add-vendor', vendor_views.CreateVendorView.as_view(), name='add_vendor'),
    path("staff/vendor/create", vendor_views.CreateVendorView.as_view(), name="create-vendor"),
    # path("vendor/<int:id>/", vendor_views.VendorDetailView.as_view(), name="vendor-detail"),
    # path("vendor/by-slug/<slug:slug>/", vendor_views.VendorDetailView.as_view(), name="vendor-detail-by-slug"),
    path("vendor/<int:vendor_id>/update", vendor_views.VendorUpdateView.as_view(), name="vendor-update"),
    path('vendor/association-produit-to-vendor', vendor_views.VendorProduitAssociationAPIView.as_view(), name='association-du-produit-au-vendor'),
    # path("vendor/<int:user_id>/status", vendor_views.UpdateVendorStatusAPIView.as_view(), name="vendor-status"),
    # path('vendor/find', vendor_views.RetrieveVendorView.as_view(), name='vendor-find'),
    # path('vendor/<int:user_id>/update-status', vendor_views.UpdateVendorStatusAPIView.as_view(), name='update_vendor_status'),
    # END VENDOR
    
    
    # CASHIER
    path("cashiers/", staff_views.CashierListView.as_view(), name="cashier-list"),
    path("cashiers/<int:id>/", staff_views.CashierDetailView.as_view(), name="cashier-detail"),
    path("cashiers/by-slug/<slug:slug>/", staff_views.CashierDetailView.as_view(), name="cashier-detail-by-slug"),
    # END CASHIER
    
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
    
    path('vente/list-produit', sale_views.VenteListAPIView.as_view(), name='vente-produit-list'),
    path('vente/rapport-mensuel/', sale_views.RapportVentesMensuelAPIView.as_view(), name='rapport-ventes-mensuel'),
    
    # path('facture/recherche-facture/<str:numero_facture>', sale_views.RechercherFactureView.as_view(), name='Recherche-facture-par-numero'),
    path('facture/List-factures', sale_views.ListFactureView.as_view(), name='list-factures'),
    # path("facture/List-factures-a-payer", sale_views.ListFacturesAPayerView.as_view(),name="list_factures_a_payer",),
    path('facture/paiement-facture/<str:facture_numero>', sale_views.PaiementFactureView.as_view(), name='Paiement-facture-par-numero'),
    path("ventes/<int:vente_id>/livraison/confirm/", sale_views.ConfirmerLivraisonView.as_view(), name="vente-confirmer-livraison"),
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
    path('commande-client/list', order_views.ListCommandeClientView.as_view(), name='liste-commandes'),
    path('commande-client/<str:numero_commande>/modifier/', order_views.UpdateCommandeByNumeroView.as_view(), name='modifier-commande-par-numero'),
    path('commande-client/<str:numero_commande>/changer-statut/', order_views.ChangeCommandeStatusView.as_view(), name='changer-statut-commande'),
    path("commande-client/paiement-acompte-bon/<str:numero_bon>/acompte/", order_views.PaiementAcompteBonCommandeView.as_view(), name="paiement-acompte-bon")
    
    # path('', include('userauths.urls')),
    # path('', include('store.urls')),
    # path('', include('stock.urls')),
    # path('', include('sale.urls')),
    
]