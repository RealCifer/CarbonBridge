"""
ingest/urls.py
==============
URL routes for upload ingestion endpoints.

Mounted under /api/upload/ via the root URLconf.
"""

from django.urls import path
from .views import SAPUploadView, UtilityUploadView, TravelUploadView

urlpatterns = [
    path("sap/",     SAPUploadView.as_view(),     name="upload-sap"),
    path("utility/", UtilityUploadView.as_view(),  name="upload-utility"),
    path("travel/",  TravelUploadView.as_view(),   name="upload-travel"),
]
