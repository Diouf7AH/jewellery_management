from django.contrib.auth import views as auth_views
from django.urls import include, path

from .views import *

urlpatterns = [
    # Dashboard
    
    # User
    path('register', UserRegistrationView.as_view(), name='register'),
    path('login', UserLoginView.as_view(), name='login'),
    path('roles', RoleListCreateAPIView.as_view(), name='role'),
    path('role/<slug:slug>', RoleDetailAPIView.as_view(), name='role-detail'),
    # path('changepassword/<int:pk>', UserChangePasswordView.as_view(), name='changepassword'),
    path('user/<int:pk>',UserDetailUpdateView.as_view(),name="detail"),
    path('users',UsersView.as_view(),name="users"),
    
    # path('password-reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    # path('password-reset-confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),

    # path('password_reset/', include('django_rest_passwordreset.urls', namespace='password_reset')),
    
    # Validate Token
    path('validate-token',ValidateTokenView.as_view(),name="validate_token"),


]