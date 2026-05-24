"""
emissions/services.py
=====================
GHG emission calculation service.

Pipeline per NormalizedRecord
------------------------------
1. Look up the best-matching EmissionFactor:
   - Match on activity_type + unit
   - Prefer tenant's region; fall back to GLOBAL
   - Pick the factor whose valid_from ≤ activity_date and
     valid_to IS NULL or valid_to ≥ activity_date
2. Apply cabin-class multiplier for flights.
3. Compute emission_kgco2e = quantity × factor_kgco2e × multiplier
4. Compute emission_tco2e  = emission_kgco2e / 1000
5. Persist / update the EmissionRecord.

Factor resolution order
-----------------------
  (activity_type, unit, tenant_region) → (activity_type, unit, GLOBAL) → FACTOR_MISSING
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from core.models import NormalizedRecord, Tenant, UploadBatch
from .models import EmissionFactor, EmissionRecord

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cabin-class multipliers (DEFRA 2023)
# Applied on top of the base economy-class flight factor.
# ---------------------------------------------------------------------------
_CABIN_MULTIPLIERS: dict[str, Decimal] = {
    "economy":       Decimal("1.0"),
    "economy plus":  Decimal("1.6"),
    "premium":       Decimal("1.6"),
    "premium economy": Decimal("1.6"),
    "business":      Decimal("2.0"),
    "first":         Decimal("3.0"),
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class CalculationSummary:
    batch_id: Optional[int]
    total_records: int = 0
    calculated: int = 0
    factor_missing: int = 0
    errors: int = 0
    total_tco2e: Decimal = Decimal("0")
    details: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Factor resolution
# ---------------------------------------------------------------------------

def _resolve_factor(
    activity_type: str,
    unit: str,
    activity_date: date,
    preferred_region: str = "GLOBAL",
) -> Optional[EmissionFactor]:
    """
    Find the most-specific valid EmissionFactor for the given activity.

    Priority: preferred_region > GLOBAL.
    Within each region: latest valid_from ≤ activity_date.
    """
    base_qs = EmissionFactor.objects.filter(
        activity_type=activity_type,
        unit=unit,
        valid_from__lte=activity_date,
    ).filter(
        models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=activity_date)
    ).order_by("-valid_from")

    # Try preferred region first
    if preferred_region and preferred_region != "GLOBAL":
        factor = base_qs.filter(region=preferred_region).first()
        if factor:
            return factor

    # Fall back to GLOBAL
    return base_qs.filter(region="GLOBAL").first()


# Needed for the Q import inside the function above
from django.db import models


# ---------------------------------------------------------------------------
# Per-record calculation
# ---------------------------------------------------------------------------

def _calculate_one(
    norm_rec: NormalizedRecord,
    preferred_region: str = "GLOBAL",
) -> EmissionRecord:
    """
    Calculate or recalculate emissions for a single NormalizedRecord.
    Always upserts the linked EmissionRecord.
    """
    quantity = norm_rec.normalized_value
    unit = norm_rec.normalized_unit
    activity_type = norm_rec.activity_type
    activity_date = norm_rec.activity_date

    # ── Factor lookup ──────────────────────────────────────────────────────
    factor = _resolve_factor(activity_type, unit, activity_date, preferred_region)

    # ── Cabin-class multiplier (flights only) ──────────────────────────────
    multiplier = Decimal("1.0")
    notes_parts: list[str] = []

    if activity_type == "flight" and factor:
        # Try to read cabin_class from the linked RawRecord's payload
        try:
            raw_rr = norm_rec.batch.raw_records.filter(
                parsing_status="PARSED"
            ).first()
            if raw_rr:
                cabin = str(
                    raw_rr.original_payload_json.get("cabin_class", "economy")
                ).lower().strip()
                multiplier = _CABIN_MULTIPLIERS.get(cabin, Decimal("1.0"))
                if multiplier != Decimal("1.0"):
                    notes_parts.append(f"Cabin class '{cabin}' multiplier ×{multiplier}.")
        except Exception:
            pass  # silently use economy

    # ── Compute ────────────────────────────────────────────────────────────
    if factor:
        kg = (quantity * factor.factor_kgco2e * multiplier).quantize(Decimal("0.000001"))
        tco2e = (kg / Decimal("1000")).quantize(Decimal("0.000000001"))
        status = EmissionRecord.CalculationStatus.CALCULATED
        factor_snapshot = factor.factor_kgco2e
        notes_parts.append(
            f"Factor: {factor.factor_kgco2e} kgCO₂e/{unit} "
            f"({factor.region}, {factor.source}, valid from {factor.valid_from})."
        )
    else:
        kg = Decimal("0")
        tco2e = Decimal("0")
        status = EmissionRecord.CalculationStatus.FACTOR_MISSING
        factor_snapshot = None
        notes_parts.append(
            f"No emission factor found for activity_type='{activity_type}' "
            f"unit='{unit}' region='{preferred_region}' date={activity_date}."
        )
        logger.warning(
            "[Emissions] Factor missing: activity=%s unit=%s region=%s date=%s",
            activity_type, unit, preferred_region, activity_date,
        )

    # ── Upsert EmissionRecord ───────────────────────────────────────────────
    em_rec, _ = EmissionRecord.objects.update_or_create(
        normalized_record=norm_rec,
        defaults={
            "emission_factor": factor,
            "factor_snapshot_kgco2e": factor_snapshot,
            "activity_quantity": quantity,
            "activity_unit": unit,
            "emission_kgco2e": kg,
            "emission_tco2e": tco2e,
            "status": status,
            "calculated_at": timezone.now(),
            "calculation_notes": " ".join(notes_parts),
        },
    )
    return em_rec


# ---------------------------------------------------------------------------
# Batch calculation
# ---------------------------------------------------------------------------

def calculate_batch_emissions(
    batch_id: int,
    preferred_region: str = "GLOBAL",
) -> CalculationSummary:
    """
    Calculate emissions for all NormalizedRecords that belong to an UploadBatch.

    Parameters
    ----------
    batch_id : int
        PK of the UploadBatch.
    preferred_region : str
        ISO region code or 'GLOBAL' to prefer regional factors.

    Returns
    -------
    CalculationSummary
    """
    summary = CalculationSummary(batch_id=batch_id)

    try:
        batch = UploadBatch.objects.get(pk=batch_id)
    except UploadBatch.DoesNotExist:
        logger.error("[Emissions] Batch #%d not found.", batch_id)
        summary.errors += 1
        return summary

    # All NormalizedRecords whose RawRecord belongs to this batch
    norm_qs = NormalizedRecord.objects.filter(
        tenant=batch.source.tenant,
        source_type=batch.source.source_type,
    ).select_related("tenant")

    # Filter to records created within this batch via RawRecord link
    raw_ids = batch.raw_records.filter(
        parsing_status="PARSED"
    ).values_list("pk", flat=True)

    # We don't have a direct FK from NormalizedRecord → RawRecord, so we
    # scope to the tenant + source_type + batch creation window as a proxy.
    # For a more precise link, add NormalizedRecord.raw_record FK in a future phase.
    norm_qs = NormalizedRecord.objects.filter(
        tenant=batch.source.tenant,
        source_type=batch.source.source_type,
        created_at__gte=batch.created_at,
    ).select_related("tenant")

    summary.total_records = norm_qs.count()

    for norm_rec in norm_qs.iterator():
        try:
            with transaction.atomic():
                em_rec = _calculate_one(norm_rec, preferred_region)
                if em_rec.status == EmissionRecord.CalculationStatus.CALCULATED:
                    summary.calculated += 1
                    summary.total_tco2e += em_rec.emission_tco2e
                elif em_rec.status == EmissionRecord.CalculationStatus.FACTOR_MISSING:
                    summary.factor_missing += 1
                summary.details.append({
                    "normalized_record_id": norm_rec.pk,
                    "activity_type": norm_rec.activity_type,
                    "status": em_rec.status,
                    "emission_tco2e": str(em_rec.emission_tco2e),
                })
        except Exception as exc:
            summary.errors += 1
            summary.details.append({
                "normalized_record_id": norm_rec.pk,
                "status": "ERROR",
                "error": str(exc),
            })
            logger.exception(
                "[Emissions] Error calculating record #%d: %s", norm_rec.pk, exc
            )

    logger.info(
        "[Emissions] Batch #%d: %d calculated, %d missing factor, %d errors, "
        "total=%.4f tCO₂e",
        batch_id, summary.calculated, summary.factor_missing,
        summary.errors, summary.total_tco2e,
    )
    return summary


def calculate_tenant_emissions(
    tenant: Tenant,
    preferred_region: str = "GLOBAL",
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> CalculationSummary:
    """
    Calculate / recalculate emissions for all NormalizedRecords for a tenant,
    optionally filtered by activity date range.
    """
    summary = CalculationSummary(batch_id=None)
    qs = NormalizedRecord.objects.filter(tenant=tenant)
    if from_date:
        qs = qs.filter(activity_date__gte=from_date)
    if to_date:
        qs = qs.filter(activity_date__lte=to_date)

    summary.total_records = qs.count()

    for norm_rec in qs.iterator():
        try:
            with transaction.atomic():
                em_rec = _calculate_one(norm_rec, preferred_region)
                if em_rec.status == EmissionRecord.CalculationStatus.CALCULATED:
                    summary.calculated += 1
                    summary.total_tco2e += em_rec.emission_tco2e
                else:
                    summary.factor_missing += 1
        except Exception as exc:
            summary.errors += 1
            logger.exception("[Emissions] Tenant calc error record #%d: %s", norm_rec.pk, exc)

    return summary
