from django.urls import include, path

urlpatterns = [
    
    # Store API Endpoints
    
    path('', include('userauths.urls')),
    path('', include('store.urls')),
    path('', include('stock.urls')),
    path('', include('sale.urls')),
    
]