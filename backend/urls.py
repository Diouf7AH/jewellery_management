"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
# from knox import views as knox_views
# drf-yasg imports
# drf-yasg imports
from rest_framework import permissions

from userauths.views import resend_confirmation_form, resend_confirmation_submit

# Define the schema view
schema_view = get_schema_view(
    openapi.Info(
        title="Your API Title",
        default_version='v1',
        description="Description of your API",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="lamzooo555@gmail.com"),
        license=openapi.License(name="MIT License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)
API_DESCRIPTION = 'A Web API for creating and editing.' # new
API_TITLE = 'API' # new

urlpatterns = [
    path('swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    
    # Admin URLbackofficegold/
    path('admin/', admin.site.urls),
    # API V1 Urls
    path("api/", include("api.urls")),
    
    # path('backoffice-dusite-rio-gold-/', admin.site.urls),
    
    path('resend-confirmation-form/', resend_confirmation_form, name='resend-confirmation-form'),
    path('resend-confirmation-submit/', resend_confirmation_submit, name='resend-confirmation-submit'),
    
    # path('logout/',knox_views.LogoutView.as_view(), name='knox_logout'), 
    # path('logoutall/',knox_views.LogoutAllView.as_view(), name='knox_logoutall'), 
    # path('api/password_reset/',include('django_rest_passwordreset.urls', namespace='password_reset')),

]


urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

