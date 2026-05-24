"""
base.py – Shared foundation for all CarbonBridge source adapters.

Defines:
  • NormalizedActivityRecord  – canonical output dataclass (no emission math)
  • AdapterValidationError    – structured validation exception
  • BaseAdapter               – abstract contract every adapter must fulfil
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical output schema
# ---------------------------------------------------------------------------

@dataclass
class NormalizedActivityRecord:
    """
    Unified, source-agnostic activity record produced by every adapter.

    This is purely an **activity** record – no emission factor is applied here.
    Downstream carbon calculation services consume this schema.

    Fields
    ------
    source_type : str
        One of 'SAP', 'UTILITY', 'TRAVEL'.
    activity_type : str
        Fine-grained activity category, e.g. 'fuel', 'electricity', 'flight'.
    activity_date : date
        Calendar date the activity occurred (or the period start for billing).
    quantity : Decimal
        Numeric magnitude of the activity (e.g. 450 for 450 litres of diesel).
    unit : str
        SI-normalised unit string, e.g. 'L', 'kWh', 'km', 'night', 'km' (PAX-km).
    original_quantity : Decimal
        Raw value as it appeared in the source document (preserved for lineage).
    original_unit : str
        Raw unit string from the source document.
    description : str
        Human-readable summary constructed from source fields.
    source_reference : Optional[str]
        Upstream document reference (invoice no, SAP material doc, booking ID…).
    location : Optional[str]
        Relevant location string – plant code, meter site, airport pair, etc.
    metadata : dict[str, Any]
        Adapter-specific supplementary fields (plant code, tariff, cabin class…).
    """

    source_type: str
    activity_type: str
    activity_date: date
    quantity: Decimal
    unit: str
    original_quantity: Decimal
    original_unit: str
    description: str
    source_reference: Optional[str] = None
    location: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dictionary representation."""
        return {
            "source_type": self.source_type,
            "activity_type": self.activity_type,
            "activity_date": self.activity_date.isoformat(),
            "quantity": str(self.quantity),
            "unit": self.unit,
            "original_quantity": str(self.original_quantity),
            "original_unit": self.original_unit,
            "description": self.description,
            "source_reference": self.source_reference,
            "location": self.location,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class AdapterValidationError(Exception):
    """
    Raised when one or more rows fail structural or semantic validation.

    Attributes
    ----------
    errors : list[dict]
        Each element is {'row': int | str, 'field': str, 'message': str}.
    """

    def __init__(self, errors: list[dict[str, Any]]):
        self.errors = errors
        summary = f"{len(errors)} validation error(s): " + "; ".join(
            f"[row={e.get('row', '?')} field={e.get('field', '?')}] {e.get('message', '')}"
            for e in errors[:5]  # truncate long lists in the exception message
        )
        super().__init__(summary)


# ---------------------------------------------------------------------------
# Abstract base adapter
# ---------------------------------------------------------------------------

class BaseAdapter(ABC):
    """
    Contract that every CarbonBridge source adapter must implement.

    Lifecycle
    ---------
    1. ``parse(raw)``      → list of raw Python dicts (one per source row/object)
    2. ``validate(rows)``  → raises AdapterValidationError if any row is invalid
    3. ``normalize(rows)`` → returns list[NormalizedActivityRecord]

    Convenience
    -----------
    ``run(raw)`` executes the full pipeline in order and returns the records.
    """

    SOURCE_TYPE: str  # Override in each subclass

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def parse(self, raw: str | bytes) -> list[dict[str, Any]]:
        """
        Convert the raw source payload into a list of flat Python dicts.

        Parameters
        ----------
        raw : str | bytes
            The raw document content (CSV text, JSON bytes, etc.).

        Returns
        -------
        list[dict[str, Any]]
            One dict per logical activity row. Keys are source-specific.
        """

    @abstractmethod
    def validate(self, rows: list[dict[str, Any]]) -> None:
        """
        Validate parsed rows.  Raises AdapterValidationError on failure.

        Implementations should collect **all** errors before raising so that
        callers can display a comprehensive error report in a single pass.

        Parameters
        ----------
        rows : list[dict[str, Any]]
            Output from ``parse()``.

        Raises
        ------
        AdapterValidationError
            If any row contains missing required fields, wrong types, or
            out-of-range values.
        """

    @abstractmethod
    def normalize(self, rows: list[dict[str, Any]]) -> list[NormalizedActivityRecord]:
        """
        Transform validated rows into NormalizedActivityRecord instances.

        Parameters
        ----------
        rows : list[dict[str, Any]]
            Output from ``parse()`` (already validated).

        Returns
        -------
        list[NormalizedActivityRecord]
        """

    # ------------------------------------------------------------------
    # Convenience pipeline
    # ------------------------------------------------------------------

    def run(self, raw: str | bytes) -> list[NormalizedActivityRecord]:
        """
        Execute the full parse → validate → normalize pipeline.

        Parameters
        ----------
        raw : str | bytes
            Raw source payload.

        Returns
        -------
        list[NormalizedActivityRecord]

        Raises
        ------
        AdapterValidationError
            Propagated from ``validate()``.
        """
        logger.info("[%s] Starting adapter pipeline.", self.SOURCE_TYPE)
        rows = self.parse(raw)
        logger.info("[%s] Parsed %d row(s).", self.SOURCE_TYPE, len(rows))
        self.validate(rows)
        logger.info("[%s] Validation passed.", self.SOURCE_TYPE)
        records = self.normalize(rows)
        logger.info("[%s] Normalized %d record(s).", self.SOURCE_TYPE, len(records))
        return records

    # ------------------------------------------------------------------
    # Shared helper utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _to_decimal(value: Any, field_name: str, row_index: int) -> Decimal:
        """
        Safely coerce a value to Decimal, raising a structured dict on failure
        (callers collect these into the errors list).
        """
        try:
            return Decimal(str(value).strip().replace(",", "."))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError(
                {"row": row_index, "field": field_name,
                 "message": f"Cannot convert '{value}' to a number."}
            )

    @staticmethod
    def _require_field(row: dict, field_name: str, row_index: int,
                       errors: list[dict]) -> bool:
        """
        Append an error if a required field is missing or blank.
        Returns True when the field is present and non-empty.
        """
        val = row.get(field_name)
        if val is None or str(val).strip() == "":
            errors.append({
                "row": row_index,
                "field": field_name,
                "message": f"Required field '{field_name}' is missing or empty.",
            })
            return False
        return True
