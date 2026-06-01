from django.urls import path
from . import views

urlpatterns = [
    # ── Template pages ───────────────────────────────────────
    path('',            views.index,       name='index'),
    path('dashboard/',  views.dashboard,   name='dashboard'),
    path('upload/',     views.upload_page, name='upload'),

    # ── API endpoints ────────────────────────────────────────
    path('api/contracts/',
         views.ContractListAPIView.as_view(),   name='api_contracts'),

    path('api/contracts/upload/',
         views.ContractUploadAPIView.as_view(), name='api_upload'),

    path('api/contracts/<int:pk>/',
         views.ContractDetailAPIView.as_view(), name='api_contract_detail'),

    path('api/contracts/<int:pk>/status/',
         views.ContractStatusAPIView.as_view(), name='api_contract_status'),

    path('api/contracts/<int:pk>/text/',
         views.ContractTextAPIView.as_view(), name='api_contract_text'),
    
    path('api/dashboard/stats/',
         views.DashboardStatsAPIView.as_view(), name='api_dashboard_stats'),
]