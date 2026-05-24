"""
sap_adapter.py – SAP ERP CSV export adapter.

Assumptions
-----------
• Input is a UTF-8 or latin-1 CSV (auto-detected) exported from an SAP system.
• Column headers may be in German (SAP default) or English.
• Values may mix decimal separators (comma vs. period) and unit notations.
• Each row carries a plant code (Werk / Plant) for location tracking.
• Numeric values may use German formatting: "1.234,56" → 1234.56

Supported activity types normalised by this adapter
----------------------------------------------------
fuel          → Liters  (L)
electricity   → kWh
procurement   → kg  (mass of procured material)

German→English header mapping (extend as needed for your SAP layout):
  Buchungsdatum   → posting_date
  Werk            → plant_code
  Materialgruppe  → material_group
  Menge           → quantity
  Mengeneinheit   → unit
  Belegart        → document_type
  Belegnummer     → document_number
  Kostenstelle    → cost_centre
  Betrag          → amount
  Währung         → currency
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from .base import (
    AdapterValidationError,
    BaseAdapter,
    NormalizedActivityRecord,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Header translation tables
# ---------------------------------------------------------------------------

# German SAP header → internal canonical key
_GERMAN_TO_CANONICAL: dict[str, str] = {
    # Date fields
    "buchungsdatum": "posting_date",
    "belegdatum": "posting_date",
    "datum": "posting_date",
    # Plant / location
    "werk": "plant_code",
    "werkskennung": "plant_code",
    # Material / category
    "materialgruppe": "material_group",
    "material": "material_group",
    "materialnummer": "material_group",
    # Quantity
    "menge": "quantity",
    "verbrauchsmenge": "quantity",
    # Unit
    "mengeneinheit": "unit",
    "basismengeneinheit": "unit",
    "me": "unit",
    # Document identifiers
    "belegart": "document_type",
    "belegnummer": "document_number",
    "buchungsbeleg": "document_number",
    # Cost centre
    "kostenstelle": "cost_centre",
    "kostenträger": "cost_centre",
    # Financial
    "betrag": "amount",
    "betrag in hauswährung": "amount",
    "währung": "currency",
    "wahrung": "currency",
}

# English header aliases → canonical key
_ENGLISH_TO_CANONICAL: dict[str, str] = {
    "posting_date": "posting_date",
    "date": "posting_date",
    "plant": "plant_code",
    "plant_code": "plant_code",
    "material_group": "material_group",
    "material group": "material_group",
    "category": "material_group",
    "quantity": "quantity",
    "qty": "quantity",
    "amount": "quantity",          # fallback if only monetary amount is present
    "unit": "unit",
    "uom": "unit",
    "unit of measure": "unit",
    "document_type": "document_type",
    "doc_type": "document_type",
    "document_number": "document_number",
    "doc_number": "document_number",
    "material_doc": "document_number",
    "cost_centre": "cost_centre",
    "cost center": "cost_centre",
    "cost centre": "cost_centre",
    "currency": "currency",
}

# SAP unit → SI-normalised (unit string, conversion factor)
_UNIT_NORMALISATION: dict[str, tuple[str, Decimal]] = {
    # Fuel / liquid volume
    "l": ("L", Decimal("1")),
    "liter": ("L", Decimal("1")),
    "litre": ("L", Decimal("1")),
    "lt": ("L", Decimal("1")),
    "gal": ("L", Decimal("3.78541")),   # US gallon → litres
    "gl": ("L", Decimal("3.78541")),
    "gallon": ("L", Decimal("3.78541")),
    "m3": ("L", Decimal("1000")),       # cubic metre → litres
    "m³": ("L", Decimal("1000")),
    # Mass (procurement)
    "kg": ("kg", Decimal("1")),
    "kilogramm": ("kg", Decimal("1")),
    "kilogram": ("kg", Decimal("1")),
    "t": ("kg", Decimal("1000")),       # metric tonne → kg
    "tonne": ("kg", Decimal("1000")),
    "mt": ("kg", Decimal("1000")),
    "g": ("kg", Decimal("0.001")),
    "lb": ("kg", Decimal("0.453592")),
    "lbs": ("kg", Decimal("0.453592")),
    # Energy
    "kwh": ("kWh", Decimal("1")),
    "kilowattstunde": ("kWh", Decimal("1")),
    "mwh": ("kWh", Decimal("1000")),
    "megawattstunde": ("kWh", Decimal("1000")),
    "gj": ("kWh", Decimal("277.778")),
    "mj": ("kWh", Decimal("0.277778")),
    "kj": ("kWh", Decimal("0.000277778")),
}

# Material group keywords → activity type
_MATERIAL_GROUP_ACTIVITY_MAP: dict[str, str] = {
    # Fuel-related keywords
    "diesel": "fuel",
    "benzin": "fuel",
    "petrol": "fuel",
    "gasoline": "fuel",
    "kerosin": "fuel",
    "kerosene": "fuel",
    "erdgas": "fuel",
    "gas": "fuel",
    "lng": "fuel",
    "lpg": "fuel",
    "heizöl": "fuel",
    "fuel": "fuel",
    # Electricity
    "strom": "electricity",
    "electricity": "electricity",
    "electric": "electricity",
    "energie": "electricity",
    "energy": "electricity",
    "solar": "electricity",
    # Procurement / materials
    "verbrauchsmaterial": "procurement",
    "rohstoff": "procurement",
    "material": "procurement",
    "procurement": "procurement",
    "goods": "procurement",
    "waren": "procurement",
}

# Required canonical fields that every row must carry
_REQUIRED_FIELDS = ["posting_date", "quantity", "unit", "material_group"]


# ---------------------------------------------------------------------------
# SAP Adapter
# ---------------------------------------------------------------------------

class SAPAdapter(BaseAdapter):
    """
    Adapter for SAP ERP CSV exports.

    Parameters
    ----------
    delimiter : str
        CSV column separator. Defaults to ';' (SAP default export).
    encoding : str
        File encoding. Defaults to 'utf-8-sig' (handles BOM). Falls back to
        'latin-1' automatically if UTF-8 decoding fails.
    date_formats : list[str]
        strptime format strings tried in order when parsing date fields.
    """

    SOURCE_TYPE = "SAP"

    _DEFAULT_DATE_FORMATS = [
        "%d.%m.%Y",   # German: 31.01.2024
        "%Y-%m-%d",   # ISO 8601
        "%m/%d/%Y",   # US date
        "%d/%m/%Y",   # EU date
        "%Y%m%d",     # SAP compact
    ]

    def __init__(
        self,
        delimiter: str = ";",
        encoding: str = "utf-8-sig",
        date_formats: Optional[list[str]] = None,
    ) -> None:
        self.delimiter = delimiter
        self.encoding = encoding
        self.date_formats = date_formats or self._DEFAULT_DATE_FORMATS

    # ------------------------------------------------------------------
    # parse
    # ------------------------------------------------------------------

    def parse(self, raw: str | bytes) -> list[dict[str, Any]]:
        """
        Decode the CSV bytes/string and map all headers to canonical keys.

        Handles:
        • UTF-8 / latin-1 encoding auto-detection
        • German numeric formatting  ("1.234,56" → Decimal("1234.56"))
        • Header aliasing (German + English variants)
        """
        if isinstance(raw, bytes):
            try:
                text = raw.decode(self.encoding)
            except UnicodeDecodeError:
                logger.warning(
                    "[SAP] UTF-8 decoding failed, retrying with latin-1."
                )
                text = raw.decode("latin-1")
        else:
            text = raw

        reader = csv.DictReader(
            io.StringIO(text),
            delimiter=self.delimiter,
        )

        rows: list[dict[str, Any]] = []
        for raw_row in reader:
            canonical = self._canonicalise_row(raw_row)
            rows.append(canonical)

        logger.debug("[SAP] parse() produced %d raw rows.", len(rows))
        return rows

    # ------------------------------------------------------------------
    # validate
    # ------------------------------------------------------------------

    def validate(self, rows: list[dict[str, Any]]) -> None:
        """
        Validate all parsed rows.  Collects every error before raising.

        Checks
        ------
        • All required fields are present and non-empty.
        • posting_date can be parsed to a date.
        • quantity is a positive number.
        • unit is a recognised SAP unit.
        """
        errors: list[dict[str, Any]] = []

        for idx, row in enumerate(rows, start=1):
            for field_name in _REQUIRED_FIELDS:
                self._require_field(row, field_name, idx, errors)

            # Date parseable?
            if row.get("posting_date"):
                parsed = self._parse_date(str(row["posting_date"]))
                if parsed is None:
                    errors.append({
                        "row": idx,
                        "field": "posting_date",
                        "message": (
                            f"Cannot parse date '{row['posting_date']}'. "
                            f"Tried formats: {self.date_formats}"
                        ),
                    })

            # Quantity numeric and positive?
            if row.get("quantity") is not None:
                try:
                    qty = self._parse_german_number(str(row["quantity"]))
                    if qty <= 0:
                        errors.append({
                            "row": idx,
                            "field": "quantity",
                            "message": (
                                f"Quantity must be > 0; got '{row['quantity']}'."
                            ),
                        })
                except (ValueError, Exception):
                    errors.append({
                        "row": idx,
                        "field": "quantity",
                        "message": f"Non-numeric quantity: '{row['quantity']}'.",
                    })

            # Unit recognised?
            unit_raw = str(row.get("unit", "")).strip().lower()
            if unit_raw and unit_raw not in _UNIT_NORMALISATION:
                logger.warning(
                    "[SAP] Row %d: unrecognised unit '%s'. Will pass through as-is.",
                    idx, unit_raw,
                )

        if errors:
            raise AdapterValidationError(errors)

    # ------------------------------------------------------------------
    # normalize
    # ------------------------------------------------------------------

    def normalize(self, rows: list[dict[str, Any]]) -> list[NormalizedActivityRecord]:
        """
        Transform validated SAP rows into NormalizedActivityRecord instances.

        Unit conversion
        ---------------
        Quantities are converted to the SI base for the detected activity:
          fuel         → Litres (L)
          electricity  → kWh
          procurement  → kg
        """
        records: list[NormalizedActivityRecord] = []

        for row in rows:
            activity_type = self._detect_activity_type(row.get("material_group", ""))
            activity_date = self._parse_date(str(row["posting_date"]))  # safe – validated

            original_qty = self._parse_german_number(str(row["quantity"]))
            original_unit = str(row.get("unit", "")).strip()

            normalised_qty, normalised_unit = self._normalise_unit(
                original_qty, original_unit
            )

            plant_code = str(row.get("plant_code", "")).strip() or None
            doc_number = str(row.get("document_number", "")).strip() or None
            cost_centre = str(row.get("cost_centre", "")).strip() or None
            material_group = str(row.get("material_group", "")).strip()

            description = (
                f"{activity_type.capitalize()} consumption "
                f"of {original_qty} {original_unit} "
                f"at plant {plant_code or 'N/A'}"
            )

            metadata: dict[str, Any] = {
                "plant_code": plant_code,
                "material_group": material_group,
                "cost_centre": cost_centre,
                "document_type": row.get("document_type"),
                "currency": row.get("currency"),
                "amount": str(row.get("amount", "")) or None,
            }
            # Remove None values from metadata
            metadata = {k: v for k, v in metadata.items() if v is not None}

            records.append(
                NormalizedActivityRecord(
                    source_type=self.SOURCE_TYPE,
                    activity_type=activity_type,
                    activity_date=activity_date,
                    quantity=normalised_qty,
                    unit=normalised_unit,
                    original_quantity=original_qty,
                    original_unit=original_unit,
                    description=description,
                    source_reference=doc_number,
                    location=plant_code,
                    metadata=metadata,
                )
            )

        return records

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _canonicalise_row(self, raw_row: dict[str, Any]) -> dict[str, Any]:
        """Map raw CSV headers to canonical field names."""
        canonical: dict[str, Any] = {}
        for raw_key, value in raw_row.items():
            if raw_key is None:
                continue
            normalised_key = raw_key.strip().lower().replace("-", "_").replace(" ", "_")
            # Try German first, then English
            mapped = (
                _GERMAN_TO_CANONICAL.get(normalised_key)
                or _ENGLISH_TO_CANONICAL.get(normalised_key)
                or _ENGLISH_TO_CANONICAL.get(raw_key.strip().lower())
            )
            canonical_key = mapped or normalised_key  # preserve unknown columns
            canonical[canonical_key] = value.strip() if isinstance(value, str) else value
        return canonical

    def _parse_date(self, value: str) -> Optional[date]:
        """Try each configured format; return None if all fail."""
        value = value.strip()
        for fmt in self.date_formats:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_german_number(value: str) -> Decimal:
        """
        Convert a German-formatted number string to Decimal.
        E.g. "1.234,56" → Decimal("1234.56")
            "1234.56"  → Decimal("1234.56")
        """
        value = value.strip()
        # Detect German format: period as thousands separator, comma as decimal
        if "," in value and "." in value:
            # "1.234,56" style
            value = value.replace(".", "").replace(",", ".")
        elif "," in value:
            # "1234,56" – only comma decimal separator
            value = value.replace(",", ".")
        # else: plain "1234.56" or "1234" – use as-is
        return Decimal(value)

    @staticmethod
    def _detect_activity_type(material_group: str) -> str:
        """
        Infer the activity type from the material group description.
        Falls back to 'procurement' for unrecognised groups.
        """
        mg_lower = material_group.lower()
        for keyword, activity in _MATERIAL_GROUP_ACTIVITY_MAP.items():
            if keyword in mg_lower:
                return activity
        return "procurement"

    @staticmethod
    def _normalise_unit(
        quantity: Decimal, unit: str
    ) -> tuple[Decimal, str]:
        """
        Convert quantity to SI base unit.
        Returns (normalised_quantity, normalised_unit_string).
        """
        unit_key = unit.strip().lower()
        if unit_key in _UNIT_NORMALISATION:
            target_unit, factor = _UNIT_NORMALISATION[unit_key]
            return (quantity * factor).quantize(Decimal("0.000001")), target_unit
        # Unknown unit – pass through unchanged
        logger.warning(
            "[SAP] Unknown unit '%s'; passing quantity through unchanged.", unit
        )
        return quantity, unit
