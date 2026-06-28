from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions
from userauths.views import (resend_confirmation_form,
                             resend_confirmation_submit)

schema_view = get_schema_view(
    openapi.Info(
        title="Rio Gold API",
        default_version="v1",
        description="API Rio Gold ERP",
        contact=openapi.Contact(email="lamzooo555@gmail.com"),
        license=openapi.License(name="MIT License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)


urlpatterns = [
    path("admin/", admin.site.urls),

    # API
    path("api/", include("api.urls")),

    # User auth pages
    path("resend-confirmation-form/", resend_confirmation_form, name="resend-confirmation-form"),
    path("resend-confirmation-submit/", resend_confirmation_submit, name="resend-confirmation-submit"),
]


# Swagger uniquement en local / DEBUG
if settings.DEBUG:
    urlpatterns += [
        path("swagger<format>/", schema_view.without_ui(cache_timeout=0), name="schema-json"),
        path("swagger/", schema_view.with_ui("swagger", cache_timeout=0), name="schema-swagger-ui"),
        path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
    ]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    


