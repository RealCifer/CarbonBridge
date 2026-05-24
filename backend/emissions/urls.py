"""
emissions/urls.py
"""
from django.urls import path
from .views import (
    CalculateBatchView,
    CalculateTenantView,
    EmissionSummaryView,
    BatchReportView,
    EmissionTrendView,
)

urlpatterns = [
    # Calculation triggers
    path("calculate/batch/<int:batch_id>/", CalculateBatchView.as_view(), name="calc-batch"),
    path("calculate/tenant/",               CalculateTenantView.as_view(), name="calc-tenant"),
    # Reports
    path("reports/summary/",               EmissionSummaryView.as_view(), name="report-summary"),
    path("reports/batch/<int:batch_id>/",  BatchReportView.as_view(),     name="report-batch"),
    path("reports/trend/",                 EmissionTrendView.as_view(),   name="report-trend"),
]
