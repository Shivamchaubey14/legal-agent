from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # ── Template pages ──────────────────────────────────────
    path('login/',    views.login_page,    name='login'),
    path('register/', views.register_page, name='register'),
    path('logout/',   views.logout_view,   name='logout'),

    # ── API endpoints ────────────────────────────────────────
    path('api/register/', views.RegisterAPIView.as_view(), name='api_register'),
    path('api/login/',    views.LoginAPIView.as_view(),    name='api_login'),
    path('api/logout/',   views.LogoutAPIView.as_view(),   name='api_logout'),
    path('api/me/',       views.MeAPIView.as_view(),       name='api_me'),

    # ── JWT token refresh ────────────────────────────────────
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]