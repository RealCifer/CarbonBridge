"""
emissions/tasks.py
==================
Celery tasks for async GHG emission calculation.

Tasks
-----
calculate_batch_emissions_task   – calculate emissions for one UploadBatch
calculate_tenant_emissions_task  – (re)calculate all records for a tenant
seed_factors_task                – populate EmissionFactor table from seed data

Usage
-----
From Django code:
    from emissions.tasks import calculate_batch_emissions_task
    calculate_batch_emissions_task.delay(batch_id=42)

Celery worker startup:
    celery -A carbonbridge worker --loglevel=info
"""

from __future__ import annotations

import logging
from typing import Optional

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="emissions.calculate_batch",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def calculate_batch_emissions_task(
    self,
    batch_id: int,
    preferred_region: str = "GLOBAL",
) -> dict:
    """
    Async Celery task: calculate GHG emissions for all NormalizedRecords
    in the given UploadBatch.

    Parameters
    ----------
    batch_id : int
        PK of the UploadBatch to process.
    preferred_region : str
        Region code for factor resolution (default 'GLOBAL').

    Returns
    -------
    dict  – serialisable CalculationSummary fields.
    """
    from emissions.services import calculate_batch_emissions

    logger.info("[Task] calculate_batch_emissions_task starting: batch_id=%d", batch_id)
    try:
        summary = calculate_batch_emissions(batch_id, preferred_region)
        result = {
            "batch_id": summary.batch_id,
            "total_records": summary.total_records,
            "calculated": summary.calculated,
            "factor_missing": summary.factor_missing,
            "errors": summary.errors,
            "total_tco2e": str(summary.total_tco2e),
        }
        logger.info("[Task] Batch #%d emission calc done: %s", batch_id, result)
        return result
    except Exception as exc:
        logger.exception("[Task] Batch #%d emission calc failed: %s", batch_id, exc)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name="emissions.calculate_tenant",
    max_retries=2,
    default_retry_delay=60,
)
def calculate_tenant_emissions_task(
    self,
    tenant_id: int,
    preferred_region: str = "GLOBAL",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> dict:
    """
    Async Celery task: (re)calculate all emissions for a tenant.

    Parameters
    ----------
    tenant_id : int
    preferred_region : str
    from_date : str | None   ISO 8601 date string
    to_date   : str | None   ISO 8601 date string
    """
    from datetime import date
    from core.models import Tenant
    from emissions.services import calculate_tenant_emissions

    logger.info(
        "[Task] calculate_tenant_emissions_task: tenant_id=%d region=%s",
        tenant_id, preferred_region,
    )
    try:
        tenant = Tenant.objects.get(pk=tenant_id)
        fd = date.fromisoformat(from_date) if from_date else None
        td = date.fromisoformat(to_date) if to_date else None
        summary = calculate_tenant_emissions(tenant, preferred_region, fd, td)
        return {
            "tenant_id": tenant_id,
            "total_records": summary.total_records,
            "calculated": summary.calculated,
            "factor_missing": summary.factor_missing,
            "errors": summary.errors,
            "total_tco2e": str(summary.total_tco2e),
        }
    except Exception as exc:
        logger.exception("[Task] Tenant #%d emission calc failed: %s", tenant_id, exc)
        raise self.retry(exc=exc)


@shared_task(name="emissions.seed_factors")
def seed_factors_task() -> dict:
    """
    Async task: seed EmissionFactor table from built-in DEFRA/GHG Protocol data.
    Idempotent – safe to call multiple times.
    """
    from emissions.factors import seed_emission_factors

    logger.info("[Task] seed_factors_task starting.")
    created = seed_emission_factors()
    logger.info("[Task] Seeded %d new EmissionFactor rows.", created)
    return {"created": created}
