"""
ingest/services.py
==================
Core ingestion service layer.

Responsibilities
----------------
1. Resolve or create the DataSource for the tenant + source type.
2. Create an UploadBatch in PARSING state.
3. Feed raw file bytes to the adapter's ``parse()`` method to get row dicts.
4. Persist each row as a RawRecord (status=PENDING).
5. For each row attempt ``normalize()`` individually so one bad row doesn't
   abort the entire batch.
6. Persist each successful normalization as a NormalizedRecord.
7. Mark failed rows with FAILED status and store structured errors.
8. Finalize the UploadBatch status (COMPLETED / FAILED).
9. Return an IngestionResult summary.

Design decisions
----------------
- Row-level isolation: normalization is attempted per-row inside a try/except
  so a single malformed row never rolls back the entire upload.
- The adapter's ``validate()`` is called once on the full parsed list first.
  If it raises AdapterValidationError the entire batch is marked FAILED and
  the structured errors are stored on the batch's first RawRecord.
- All DB writes use a single transaction per batch (atomic), except that
  individual NormalizedRecord creation is wrapped in a savepoint so a
  constraint violation on one record doesn't abort the rest.
- No emission math is performed here – NormalizedRecord values come straight
  from the adapter's NormalizedActivityRecord dataclass.
"""

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from django.db import transaction, IntegrityError

from core.models import (
    DataSource,
    NormalizedRecord,
    RawRecord,
    Tenant,
    UploadBatch,
    User,
)
from adapters.base import AdapterValidationError, NormalizedActivityRecord
from adapters.sap_adapter import SAPAdapter
from adapters.utility_adapter import UtilityAdapter
from adapters.travel_adapter import TravelAdapter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON serialization helper
# ---------------------------------------------------------------------------

def _make_json_safe(obj: Any) -> Any:
    """
    Recursively coerce a Python object so it can be stored in a JSONField.

    Handles:
    • Decimal  → str
    • date / datetime → ISO 8601 str
    • bytes    → hex str
    • dict / list recursion
    """
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_safe(v) for v in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.hex()
    return obj


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class IngestionResult:
    batch_id: int
    source_type: str
    uploaded: int = 0
    normalized: int = 0
    failed: int = 0
    batch_status: str = UploadBatch.BatchStatus.PENDING
    validation_errors: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Scope inference helper
# ---------------------------------------------------------------------------

_ACTIVITY_SCOPE_MAP: dict[str, str] = {
    "fuel":             NormalizedRecord.Scope.SCOPE1,
    "electricity":      NormalizedRecord.Scope.SCOPE2,
    "gas":              NormalizedRecord.Scope.SCOPE2,
    "heat":             NormalizedRecord.Scope.SCOPE2,
    "water":            NormalizedRecord.Scope.SCOPE3,
    "procurement":      NormalizedRecord.Scope.SCOPE3,
    "flight":           NormalizedRecord.Scope.SCOPE3,
    "hotel":            NormalizedRecord.Scope.SCOPE3,
    "ground_transport": NormalizedRecord.Scope.SCOPE3,
}

_SOURCE_TYPE_CHOICES: dict[str, str] = {
    "SAP":     DataSource.SourceType.SAP,
    "UTILITY": DataSource.SourceType.UTILITY,
    "TRAVEL":  DataSource.SourceType.TRAVEL,
}


def _infer_scope(activity_type: str) -> str:
    return _ACTIVITY_SCOPE_MAP.get(activity_type, NormalizedRecord.Scope.SCOPE3)


# ---------------------------------------------------------------------------
# Adapter factory
# ---------------------------------------------------------------------------

def _build_adapter(source_type: str, delimiter: str = ","):
    if source_type == "SAP":
        return SAPAdapter(delimiter=delimiter)
    if source_type == "UTILITY":
        return UtilityAdapter(delimiter=delimiter)
    if source_type == "TRAVEL":
        return TravelAdapter()
    raise ValueError(f"Unknown source_type: {source_type!r}")


# ---------------------------------------------------------------------------
# DataSource resolver
# ---------------------------------------------------------------------------

def _resolve_data_source(
    tenant: Tenant, source_type: str, source_name: str
) -> DataSource:
    """
    Get-or-create the DataSource for this tenant + type + name.
    Uses name as a uniqueness key within a tenant+type combination.
    """
    ds, _ = DataSource.objects.get_or_create(
        tenant=tenant,
        source_type=_SOURCE_TYPE_CHOICES[source_type],
        name=source_name,
    )
    return ds


# ---------------------------------------------------------------------------
# NormalizedRecord builder
# ---------------------------------------------------------------------------

def _build_normalized_record(
    tenant: Tenant,
    source_type: str,
    record: NormalizedActivityRecord,
) -> NormalizedRecord:
    """
    Convert a NormalizedActivityRecord dataclass into a Django NormalizedRecord
    ORM instance (not yet saved).
    """
    return NormalizedRecord(
        tenant=tenant,
        source_type=_SOURCE_TYPE_CHOICES[source_type],
        activity_type=record.activity_type,
        scope=_infer_scope(record.activity_type),
        original_unit=record.original_unit,
        normalized_unit=record.unit,
        original_value=record.original_quantity,
        normalized_value=record.quantity,
        activity_date=record.activity_date,
        source_reference=record.source_reference,
        approval_status=NormalizedRecord.ApprovalStatus.PENDING,
    )


# ---------------------------------------------------------------------------
# Main ingestion service
# ---------------------------------------------------------------------------

@transaction.atomic
def run_ingestion(
    *,
    raw_bytes: bytes,
    source_type: str,
    source_name: str,
    tenant: Tenant,
    uploaded_by: Optional[User] = None,
    delimiter: str = ",",
) -> IngestionResult:
    """
    Execute the full ingestion pipeline for one uploaded file.

    Parameters
    ----------
    raw_bytes : bytes
        Raw content of the uploaded file.
    source_type : str
        One of 'SAP', 'UTILITY', 'TRAVEL'.
    source_name : str
        Human-readable label for the DataSource.
    tenant : Tenant
        Owning tenant.
    uploaded_by : User | None
        Authenticated user who triggered the upload.
    delimiter : str
        CSV delimiter passed to SAP / Utility adapters.

    Returns
    -------
    IngestionResult
    """
    result = IngestionResult(batch_id=0, source_type=source_type)

    # ------------------------------------------------------------------
    # 1. Resolve DataSource + create UploadBatch
    # ------------------------------------------------------------------
    data_source = _resolve_data_source(tenant, source_type, source_name)
    batch = UploadBatch.objects.create(
        source=data_source,
        uploaded_by=uploaded_by,
        status=UploadBatch.BatchStatus.PARSING,
    )
    result.batch_id = batch.pk
    logger.info(
        "[Ingest] Batch #%d created for source '%s' (tenant=%s).",
        batch.pk, source_name, tenant.name,
    )

    adapter = _build_adapter(source_type, delimiter)

    # ------------------------------------------------------------------
    # 2. Parse
    # ------------------------------------------------------------------
    try:
        rows = adapter.parse(raw_bytes)
    except Exception as exc:
        logger.exception("[Ingest] Parse failure on batch #%d.", batch.pk)
        batch.status = UploadBatch.BatchStatus.FAILED
        batch.save(update_fields=["status"])
        # Store the parse error as a single RawRecord
        RawRecord.objects.create(
            batch=batch,
            original_payload_json={"_error": "parse_failure", "detail": str(exc)},
            parsing_status=RawRecord.ParsingStatus.FAILED,
            parsing_errors=[{"row": "ALL", "field": "_file", "message": str(exc)}],
        )
        result.batch_status = UploadBatch.BatchStatus.FAILED
        result.validation_errors = [{"row": "ALL", "field": "_file", "message": str(exc)}]
        return result

    result.uploaded = len(rows)
    logger.info("[Ingest] Batch #%d: parsed %d row(s).", batch.pk, result.uploaded)

    # ------------------------------------------------------------------
    # 3. Persist RawRecords (one per parsed row)
    # ------------------------------------------------------------------
    raw_records: list[RawRecord] = []
    for row_dict in rows:
        rr = RawRecord(
            batch=batch,
            original_payload_json=_make_json_safe(row_dict),
            parsing_status=RawRecord.ParsingStatus.PENDING,
        )
        raw_records.append(rr)

    RawRecord.objects.bulk_create(raw_records)
    # Re-fetch with PKs assigned
    raw_records = list(
        RawRecord.objects.filter(batch=batch).order_by("pk")
    )

    # ------------------------------------------------------------------
    # 4. Validate entire parsed list
    # ------------------------------------------------------------------
    validation_errors: list[dict[str, Any]] = []
    try:
        adapter.validate(rows)
    except AdapterValidationError as ve:
        validation_errors = ve.errors
        logger.warning(
            "[Ingest] Batch #%d: %d validation error(s). Proceeding row-by-row.",
            batch.pk, len(validation_errors),
        )
        # Record errors on the batch but don't abort – we still process row-by-row

    # Build a quick error index: row_number (1-based) → list[error_dict]
    error_index: dict[int, list[dict]] = {}
    for err in validation_errors:
        row_num = err.get("row")
        if isinstance(row_num, int):
            error_index.setdefault(row_num, []).append(err)

    # ------------------------------------------------------------------
    # 5. Normalize row-by-row and persist NormalizedRecords
    # ------------------------------------------------------------------
    normalized_records_to_create: list[NormalizedRecord] = []
    failed_raw_ids: list[int] = []
    successful_raw_ids: list[int] = []

    for idx, (row_dict, raw_record) in enumerate(zip(rows, raw_records), start=1):
        # Skip rows that already have validation errors
        if idx in error_index:
            raw_record.parsing_status = RawRecord.ParsingStatus.FAILED
            raw_record.parsing_errors = error_index[idx]
            failed_raw_ids.append(raw_record.pk)
            result.failed += 1
            continue

        try:
            norm_list: list[NormalizedActivityRecord] = adapter.normalize([row_dict])
            if not norm_list:
                raise ValueError("normalize() returned an empty list for a non-empty input.")

            for norm_record in norm_list:
                orm_record = _build_normalized_record(tenant, source_type, norm_record)
                normalized_records_to_create.append(orm_record)

            raw_record.parsing_status = RawRecord.ParsingStatus.PARSED
            successful_raw_ids.append(raw_record.pk)

        except Exception as exc:
            error_detail = {
                "row": idx,
                "field": "_normalize",
                "message": str(exc),
                "traceback": traceback.format_exc(limit=5),
            }
            raw_record.parsing_status = RawRecord.ParsingStatus.FAILED
            raw_record.parsing_errors = [error_detail]
            validation_errors.append(error_detail)
            failed_raw_ids.append(raw_record.pk)
            result.failed += 1
            logger.warning(
                "[Ingest] Batch #%d row %d normalization error: %s",
                batch.pk, idx, exc,
            )

    # ------------------------------------------------------------------
    # 6. Bulk-save NormalizedRecords (per-record savepoints on error)
    # ------------------------------------------------------------------
    saved_count = 0
    for orm_record in normalized_records_to_create:
        try:
            with transaction.atomic():
                orm_record.save()
                saved_count += 1
        except (IntegrityError, Exception) as exc:
            result.failed += 1
            validation_errors.append({
                "row": "bulk_save",
                "field": "_db",
                "message": str(exc),
            })
            logger.error("[Ingest] Batch #%d DB save error: %s", batch.pk, exc)

    result.normalized = saved_count

    # ------------------------------------------------------------------
    # 7. Bulk-update RawRecord statuses
    # ------------------------------------------------------------------
    # Update parsed rows
    if successful_raw_ids:
        RawRecord.objects.filter(pk__in=successful_raw_ids).update(
            parsing_status=RawRecord.ParsingStatus.PARSED
        )
    # Update failed rows (with per-row errors already set above)
    for rr in raw_records:
        if rr.pk in failed_raw_ids:
            rr.save(update_fields=["parsing_status", "parsing_errors"])

    # ------------------------------------------------------------------
    # 8. Finalize batch status
    # ------------------------------------------------------------------
    if result.failed == 0:
        batch.status = UploadBatch.BatchStatus.COMPLETED
    elif result.normalized == 0:
        batch.status = UploadBatch.BatchStatus.FAILED
    else:
        # Partial success – mark COMPLETED with errors stored in raw records
        batch.status = UploadBatch.BatchStatus.COMPLETED

    batch.save(update_fields=["status"])
    result.batch_status = batch.status
    result.validation_errors = validation_errors

    logger.info(
        "[Ingest] Batch #%d DONE: uploaded=%d normalized=%d failed=%d status=%s",
        batch.pk, result.uploaded, result.normalized, result.failed, batch.status,
    )
    return result
