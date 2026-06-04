from django.urls import path
from . import views

urlpatterns = [
    # ── Template pages ───────────────────────────────────────
    path('',            views.index,       name='index'),
    path('dashboard/',  views.dashboard,   name='dashboard'),
    path('upload/',     views.upload_page, name='upload'),
    path('contracts/<int:pk>/review/', views.contract_review_page, name='contract_review_page'),
    path('contracts/<int:pk>/processing/', views.contract_processing_page, name='contract_processing'),         

    # ── API: no-pk endpoints FIRST ───────────────────────────
    path('api/contracts/',
         views.ContractListAPIView.as_view(),    name='api_contracts'),

    path('api/contracts/upload/',
         views.ContractUploadAPIView.as_view(),  name='api_upload'),

    # ── Bulk actions (before <int:pk> routes) ────────────────
    path('api/contracts/bulk/export/',
         views.BulkExportAPIView.as_view(),      name='api_bulk_export'),

    path('api/contracts/bulk/rerun/',
         views.BulkRerunAPIView.as_view(),       name='api_bulk_rerun'),

    path('api/contracts/bulk/assign/',
         views.BulkAssignAPIView.as_view(),      name='api_bulk_assign'),

    path('api/contracts/bulk/delete/',
         views.BulkDeleteAPIView.as_view(),      name='api_bulk_delete'),

    # ── API: per-contract endpoints ──────────────────────────
    path('api/contracts/<int:pk>/',
         views.ContractDetailAPIView.as_view(),  name='api_contract_detail'),

    path('api/contracts/<int:pk>/status/',
         views.ContractStatusAPIView.as_view(),  name='api_contract_status'),

    path('api/contracts/<int:pk>/text/',
         views.ContractTextAPIView.as_view(),    name='api_contract_text'),

    path('api/contracts/<int:pk>/embed/',
         views.ContractEmbedAPIView.as_view(),   name='api_contract_embed'),

    path('api/contracts/<int:pk>/search/',
         views.ContractSearchAPIView.as_view(),  name='api_contract_search'),

    path('api/contracts/<int:pk>/flags/',
         views.ContractFlagsAPIView.as_view(),   name='api_contract_flags'),

    path('api/contracts/<int:pk>/review/',
         views.ContractReviewAPIView.as_view(),  name='api_contract_review'),

    path('api/contracts/<int:pk>/analyze/',
         views.ContractAnalyzeAPIView.as_view(), name='api_contract_analyze'),

    path('api/embed/stats/',
         views.EmbedStatsAPIView.as_view(),      name='api_embed_stats'),

    path('api/dashboard/stats/',
         views.DashboardStatsAPIView.as_view(),  name='api_dashboard_stats'),
]