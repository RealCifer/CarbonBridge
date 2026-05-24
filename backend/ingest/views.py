"""
ingest/views.py
===============
Upload ingestion API views.

Endpoints
---------
POST /api/upload/sap/      – SAP ERP CSV
POST /api/upload/utility/  – Utility portal CSV
POST /api/upload/travel/   – Concur-style JSON

All three views share the same pipeline via _run_upload(); they differ only
in which serializer and source_type they inject.

Authentication / Permissions
-----------------------------
Endpoints use IsAuthenticated by default (set in DRF DEFAULT settings).
For unauthenticated dev testing set AllowAny in settings or per-view.

Tenant Resolution
-----------------
If the authenticated user has a tenant, that tenant is used automatically.
If ``tenant_id`` is provided in the form data it overrides the user's tenant
(admin-only feature – guarded by staff check).
"""

from __future__ import annotations

import logging

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Tenant
from .serializers import (
    SAPUploadSerializer,
    TravelUploadSerializer,
    UtilityUploadSerializer,
)
from .services import IngestionResult, run_ingestion

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared upload handler
# ---------------------------------------------------------------------------

def _run_upload(
    request: Request,
    serializer_class,
    source_type: str,
) -> Response:
    """
    Common logic for all three upload endpoints.

    1. Validate the multipart payload.
    2. Resolve the tenant.
    3. Read the uploaded file bytes.
    4. Delegate to run_ingestion().
    5. Return standardised JSON response.
    """
    serializer = serializer_class(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"error": "Invalid request payload.", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    validated = serializer.validated_data
    uploaded_file = validated["file"]
    source_name = validated.get("source_name", f"{source_type} Import")
    delimiter = validated.get("delimiter", ",")

    # ------------------------------------------------------------------
    # Tenant resolution
    # ------------------------------------------------------------------
    tenant_id = validated.get("tenant_id")
    tenant: Tenant | None = None

    if tenant_id:
        if not (request.user.is_staff or request.user.is_superuser):
            return Response(
                {"error": "Only administrators may specify tenant_id."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            tenant = Tenant.objects.get(pk=tenant_id)
        except ObjectDoesNotExist:
            return Response(
                {"error": f"Tenant with id={tenant_id} does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )
    else:
        tenant = getattr(request.user, "tenant", None)

    if tenant is None:
        return Response(
            {
                "error": (
                    "No tenant associated with this account. "
                    "Provide tenant_id or contact an administrator."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ------------------------------------------------------------------
    # Read file bytes
    # ------------------------------------------------------------------
    try:
        raw_bytes: bytes = uploaded_file.read()
    except Exception as exc:
        logger.exception("File read error during %s upload.", source_type)
        return Response(
            {"error": "Could not read uploaded file.", "detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not raw_bytes:
        return Response(
            {"error": "Uploaded file is empty."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ------------------------------------------------------------------
    # Run ingestion pipeline
    # ------------------------------------------------------------------
    try:
        result: IngestionResult = run_ingestion(
            raw_bytes=raw_bytes,
            source_type=source_type,
            source_name=source_name,
            tenant=tenant,
            uploaded_by=request.user if request.user.is_authenticated else None,
            delimiter=delimiter,
        )
    except Exception as exc:
        logger.exception("Unexpected ingestion error for %s batch.", source_type)
        return Response(
            {"error": "Internal ingestion error.", "detail": str(exc)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # ------------------------------------------------------------------
    # Build response
    # ------------------------------------------------------------------
    http_status = (
        status.HTTP_200_OK
        if result.normalized > 0
        else status.HTTP_422_UNPROCESSABLE_ENTITY
    )

    response_body = {
        "batch_id": result.batch_id,
        "source_type": result.source_type,
        "uploaded": result.uploaded,
        "normalized": result.normalized,
        "failed": result.failed,
        "batch_status": result.batch_status,
    }

    # Only include validation_errors in the response when there are failures
    # to keep successful responses clean.
    if result.validation_errors:
        response_body["validation_errors"] = result.validation_errors

    return Response(response_body, status=http_status)


# ---------------------------------------------------------------------------
# Concrete views
# ---------------------------------------------------------------------------

class SAPUploadView(APIView):
    """
    POST /api/upload/sap/

    Accepts a multipart SAP ERP CSV file upload.

    Form fields
    -----------
    file        : required – the CSV file
    source_name : optional – label for the DataSource (default 'SAP ERP Import')
    delimiter   : optional – CSV column separator (default ';')
    tenant_id   : optional – admin-only tenant override

    Returns
    -------
    {
        "batch_id": 12,
        "source_type": "SAP",
        "uploaded": 100,
        "normalized": 95,
        "failed": 5,
        "batch_status": "COMPLETED",
        "validation_errors": [...]   // only present when failed > 0
    }
    """

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        logger.info(
            "SAP upload initiated by user '%s'.",
            getattr(request.user, "username", "anonymous"),
        )
        return _run_upload(request, SAPUploadSerializer, "SAP")


class UtilityUploadView(APIView):
    """
    POST /api/upload/utility/

    Accepts a multipart utility portal CSV file upload.

    Form fields
    -----------
    file        : required – the CSV file
    source_name : optional – label for the DataSource
    delimiter   : optional – CSV column separator (default ',')
    tenant_id   : optional – admin-only tenant override
    """

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        logger.info(
            "Utility upload initiated by user '%s'.",
            getattr(request.user, "username", "anonymous"),
        )
        return _run_upload(request, UtilityUploadSerializer, "UTILITY")


class TravelUploadView(APIView):
    """
    POST /api/upload/travel/

    Accepts a multipart Concur-style JSON file upload.

    Form fields
    -----------
    file        : required – the JSON file
    source_name : optional – label for the DataSource
    tenant_id   : optional – admin-only tenant override
    """

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        logger.info(
            "Travel upload initiated by user '%s'.",
            getattr(request.user, "username", "anonymous"),
        )
        return _run_upload(request, TravelUploadSerializer, "TRAVEL")
