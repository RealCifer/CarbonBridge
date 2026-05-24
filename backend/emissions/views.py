"""
emissions/views.py
==================
API views for emission calculation triggering and GHG reporting.

Endpoints
---------
POST /api/emissions/calculate/batch/<batch_id>/
    Trigger synchronous calculation for all records in a batch.
    Optionally kicks off a Celery async task when ?async=true.

POST /api/emissions/calculate/tenant/
    Trigger (re)calculation for the authenticated user's entire tenant.

GET  /api/reports/summary/
    Aggregate tCO₂e breakdown by scope + activity type.
    Supports ?from_date, ?to_date, ?scope, ?source_type filters.

GET  /api/reports/batch/<batch_id>/
    Per-batch breakdown showing upload counts + emission totals.

GET  /api/reports/trend/
    Monthly tCO₂e totals for chart rendering.
    Supports ?from_date, ?to_date, ?scope filters.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal

from django.db.models import DecimalField, F, Q, Sum
from django.db.models.functions import TruncMonth
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import NormalizedRecord, Tenant, UploadBatch
from .models import EmissionRecord
from .services import calculate_batch_emissions, calculate_tenant_emissions

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _get_tenant(request: Request) -> Tenant | None:
    return getattr(request.user, "tenant", None)


def _require_tenant(request: Request) -> tuple[Tenant | None, Response | None]:
    tenant = _get_tenant(request)
    if tenant is None:
        return None, Response(
            {"error": "No tenant associated with this account."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return tenant, None


# ---------------------------------------------------------------------------
# Calculation Trigger Views
# ---------------------------------------------------------------------------

class CalculateBatchView(APIView):
    """
    POST /api/emissions/calculate/batch/<batch_id>/

    Trigger GHG calculation for all NormalizedRecords in a batch.

    Query params
    ------------
    region : str   Region code for factor preference (default 'GLOBAL').
    async  : bool  If 'true', dispatch Celery task and return 202.

    Response (sync)
    ---------------
    {
        "batch_id": 12,
        "total_records": 100,
        "calculated": 95,
        "factor_missing": 3,
        "errors": 2,
        "total_tco2e": "12.847300000"
    }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, batch_id: int) -> Response:
        tenant, err = _require_tenant(request)
        if err:
            return err

        # Verify batch belongs to this tenant
        try:
            batch = UploadBatch.objects.select_related("source__tenant").get(pk=batch_id)
        except UploadBatch.DoesNotExist:
            return Response(
                {"error": f"Batch {batch_id} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if batch.source.tenant_id != tenant.pk and not request.user.is_staff:
            return Response(
                {"error": "You do not have access to this batch."},
                status=status.HTTP_403_FORBIDDEN,
            )

        region = request.query_params.get("region", "GLOBAL").upper()
        use_async = request.query_params.get("async", "false").lower() == "true"

        if use_async:
            try:
                from .tasks import calculate_batch_emissions_task
                task = calculate_batch_emissions_task.delay(batch_id, region)
                return Response(
                    {"task_id": task.id, "batch_id": batch_id, "status": "queued"},
                    status=status.HTTP_202_ACCEPTED,
                )
            except Exception as exc:
                logger.warning(
                    "Celery unavailable, falling back to sync: %s", exc
                )
                # Fall through to synchronous calculation

        summary = calculate_batch_emissions(batch_id, region)
        return Response(
            {
                "batch_id": summary.batch_id,
                "total_records": summary.total_records,
                "calculated": summary.calculated,
                "factor_missing": summary.factor_missing,
                "errors": summary.errors,
                "total_tco2e": str(summary.total_tco2e),
            },
            status=status.HTTP_200_OK,
        )


class CalculateTenantView(APIView):
    """
    POST /api/emissions/calculate/tenant/

    (Re)calculate emissions for every NormalizedRecord belonging to the
    authenticated user's tenant.

    Body (JSON, optional)
    ---------------------
    {
        "region": "UK",
        "from_date": "2024-01-01",
        "to_date":   "2024-12-31"
    }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        tenant, err = _require_tenant(request)
        if err:
            return err

        region = request.data.get("region", "GLOBAL").upper()
        from_date = _parse_date(request.data.get("from_date"))
        to_date = _parse_date(request.data.get("to_date"))
        use_async = str(request.data.get("async", "false")).lower() == "true"

        if use_async:
            try:
                from .tasks import calculate_tenant_emissions_task
                task = calculate_tenant_emissions_task.delay(
                    tenant.pk, region,
                    from_date.isoformat() if from_date else None,
                    to_date.isoformat() if to_date else None,
                )
                return Response(
                    {"task_id": task.id, "tenant_id": tenant.pk, "status": "queued"},
                    status=status.HTTP_202_ACCEPTED,
                )
            except Exception as exc:
                logger.warning("Celery unavailable, falling back to sync: %s", exc)

        summary = calculate_tenant_emissions(tenant, region, from_date, to_date)
        return Response(
            {
                "tenant_id": tenant.pk,
                "total_records": summary.total_records,
                "calculated": summary.calculated,
                "factor_missing": summary.factor_missing,
                "errors": summary.errors,
                "total_tco2e": str(summary.total_tco2e),
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Reporting Views
# ---------------------------------------------------------------------------

class EmissionSummaryView(APIView):
    """
    GET /api/reports/summary/

    Aggregated tCO₂e broken down by scope and activity_type.

    Query params
    ------------
    from_date   : YYYY-MM-DD
    to_date     : YYYY-MM-DD
    scope       : Scope1 | Scope2 | Scope3
    source_type : SAP | UTILITY | TRAVEL
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        tenant, err = _require_tenant(request)
        if err:
            return err

        from_date = _parse_date(request.query_params.get("from_date"))
        to_date = _parse_date(request.query_params.get("to_date"))
        scope = request.query_params.get("scope")
        source_type = request.query_params.get("source_type")

        qs = EmissionRecord.objects.filter(
            normalized_record__tenant=tenant,
            status=EmissionRecord.CalculationStatus.CALCULATED,
        ).select_related("normalized_record")

        if from_date:
            qs = qs.filter(normalized_record__activity_date__gte=from_date)
        if to_date:
            qs = qs.filter(normalized_record__activity_date__lte=to_date)
        if scope:
            qs = qs.filter(normalized_record__scope=scope)
        if source_type:
            qs = qs.filter(normalized_record__source_type=source_type)

        # Aggregate by scope + activity_type
        aggregated = (
            qs.values(
                scope_val=F("normalized_record__scope"),
                activity=F("normalized_record__activity_type"),
            )
            .annotate(
                total_tco2e=Sum("emission_tco2e"),
                record_count=Sum(Decimal("1")),
            )
            .order_by("scope_val", "activity")
        )

        # Grand total
        grand_total = qs.aggregate(total=Sum("emission_tco2e"))["total"] or Decimal("0")

        # Scope sub-totals
        scope_totals = {}
        rows = []
        for row in aggregated:
            sc = row["scope_val"]
            scope_totals[sc] = scope_totals.get(sc, Decimal("0")) + (row["total_tco2e"] or Decimal("0"))
            rows.append({
                "scope": sc,
                "activity_type": row["activity"],
                "total_tco2e": str((row["total_tco2e"] or Decimal("0")).quantize(Decimal("0.000001"))),
                "record_count": qs.filter(
                    normalized_record__scope=sc,
                    normalized_record__activity_type=row["activity"],
                ).count(),
            })

        return Response(
            {
                "tenant": tenant.name,
                "filters": {
                    "from_date": str(from_date) if from_date else None,
                    "to_date": str(to_date) if to_date else None,
                    "scope": scope,
                    "source_type": source_type,
                },
                "grand_total_tco2e": str(grand_total.quantize(Decimal("0.000001"))),
                "scope_totals": {
                    k: str(v.quantize(Decimal("0.000001")))
                    for k, v in scope_totals.items()
                },
                "breakdown": rows,
            }
        )


class BatchReportView(APIView):
    """
    GET /api/reports/batch/<batch_id>/

    Per-batch summary: upload counts + emission totals.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, batch_id: int) -> Response:
        tenant, err = _require_tenant(request)
        if err:
            return err

        try:
            batch = UploadBatch.objects.select_related(
                "source", "source__tenant", "uploaded_by"
            ).get(pk=batch_id)
        except UploadBatch.DoesNotExist:
            return Response(
                {"error": f"Batch {batch_id} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if batch.source.tenant_id != tenant.pk and not request.user.is_staff:
            return Response(
                {"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN
            )

        raw_total = batch.raw_records.count()
        raw_parsed = batch.raw_records.filter(parsing_status="PARSED").count()
        raw_failed = batch.raw_records.filter(parsing_status="FAILED").count()

        norm_qs = EmissionRecord.objects.filter(
            normalized_record__tenant=tenant,
            normalized_record__source_type=batch.source.source_type,
            normalized_record__created_at__gte=batch.created_at,
        )
        calculated = norm_qs.filter(status=EmissionRecord.CalculationStatus.CALCULATED).count()
        total_tco2e = norm_qs.filter(
            status=EmissionRecord.CalculationStatus.CALCULATED
        ).aggregate(t=Sum("emission_tco2e"))["t"] or Decimal("0")

        breakdown = list(
            norm_qs.filter(status=EmissionRecord.CalculationStatus.CALCULATED)
            .values(activity=F("normalized_record__activity_type"), scope=F("normalized_record__scope"))
            .annotate(tco2e=Sum("emission_tco2e"))
            .order_by("scope", "activity")
        )

        return Response(
            {
                "batch_id": batch_id,
                "source": batch.source.name,
                "source_type": batch.source.source_type,
                "status": batch.status,
                "uploaded_at": batch.upload_timestamp.isoformat(),
                "uploaded_by": batch.uploaded_by.username if batch.uploaded_by else None,
                "raw_records": {
                    "total": raw_total,
                    "parsed": raw_parsed,
                    "failed": raw_failed,
                },
                "emissions": {
                    "calculated": calculated,
                    "total_tco2e": str(total_tco2e.quantize(Decimal("0.000001"))),
                    "breakdown": [
                        {
                            "scope": r["scope"],
                            "activity_type": r["activity"],
                            "tco2e": str((r["tco2e"] or Decimal("0")).quantize(Decimal("0.000001"))),
                        }
                        for r in breakdown
                    ],
                },
            }
        )


class EmissionTrendView(APIView):
    """
    GET /api/reports/trend/

    Monthly tCO₂e totals for time-series charts.

    Query params
    ------------
    from_date : YYYY-MM-DD
    to_date   : YYYY-MM-DD
    scope     : Scope1 | Scope2 | Scope3
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        tenant, err = _require_tenant(request)
        if err:
            return err

        from_date = _parse_date(request.query_params.get("from_date"))
        to_date = _parse_date(request.query_params.get("to_date"))
        scope = request.query_params.get("scope")

        qs = EmissionRecord.objects.filter(
            normalized_record__tenant=tenant,
            status=EmissionRecord.CalculationStatus.CALCULATED,
        )
        if from_date:
            qs = qs.filter(normalized_record__activity_date__gte=from_date)
        if to_date:
            qs = qs.filter(normalized_record__activity_date__lte=to_date)
        if scope:
            qs = qs.filter(normalized_record__scope=scope)

        monthly = (
            qs.annotate(month=TruncMonth("normalized_record__activity_date"))
            .values("month")
            .annotate(total_tco2e=Sum("emission_tco2e"))
            .order_by("month")
        )

        return Response(
            {
                "tenant": tenant.name,
                "scope_filter": scope,
                "data": [
                    {
                        "month": row["month"].strftime("%Y-%m"),
                        "total_tco2e": str(
                            (row["total_tco2e"] or Decimal("0")).quantize(Decimal("0.000001"))
                        ),
                    }
                    for row in monthly
                ],
            }
        )
