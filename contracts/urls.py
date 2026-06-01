from django.urls import path
from . import views

urlpatterns = [
    # ── Template pages ───────────────────────────────────────
    path('',           views.index,     name='index'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # ── API endpoints ────────────────────────────────────────
    path('api/contracts/',      views.ContractListAPIView.as_view(),   name='api_contracts'),
    path('api/contracts/<int:pk>/', views.ContractDetailAPIView.as_view(), name='api_contract_detail'),
]