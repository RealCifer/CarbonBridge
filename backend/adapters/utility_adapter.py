"""
utility_adapter.py – Utility portal CSV export adapter.

Assumptions
-----------
• Input is a CSV exported from a utility supplier portal (electricity,
  gas, water, district heating, etc.).
• Each row represents a single **billing period** (period_start / period_end).
• Rows may contain meter readings (opening / closing) and net consumption.
• Tariff information (tariff code, rate, currency) is included per row.
• Multiple commodity types (electricity, gas, water, heat) may appear in
  the same file, differentiated by a 'commodity' or 'service_type' column.

Supported activity types normalised by this adapter
----------------------------------------------------
electricity   → kWh
gas           → kWh  (converted from m³ using 10.55 kWh/m³ calorific value)
water         → m³   (kept as-is; no energy conversion)
heat          → kWh  (converted from GJ: 1 GJ = 277.778 kWh)

Normalised unit rationale
-------------------------
• Electricity and gas are expressed in kWh to align with energy emission factors.
• Water is expressed in m³ (volumetric) as its GHG factor is water-specific.
• District heat is expressed in kWh for consistency with energy factors.

Header aliases handled
----------------------
Period columns   : period_start, billing_start, from_date, start_date, von
                   period_end,   billing_end,   to_date,   end_date,   bis
Meter readings   : opening_read, meter_read_open, reading_start, zaehlerstand_anfang
                   closing_read, meter_read_close, reading_end,  zaehlerstand_ende
Consumption      : consumption, net_consumption, usage, verbrauch, menge
Unit             : unit, uom, einheit, commodity_unit
Commodity        : commodity, service_type, utility_type, medium, energietraeger
Tariff           : tariff_code, tariff, rate_code, tarifnummer
Rate             : rate, unit_rate, price_per_unit, tarif_preis
Currency         : currency, curr, waehrung
Meter ID         : meter_id, meter_number, zaehler_id, zaehler_nummer, mpan, mprn
Account ref      : account_ref, account_number, invoice_number, rechnungsnummer
Site / location  : site, site_id, site_name, location, standort
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from .base import (
    AdapterValidationError,
    BaseAdapter,
    NormalizedActivityRecord,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Header mapping tables
# ---------------------------------------------------------------------------

_HEADER_MAP: dict[str, str] = {
    # Period start
    "period_start": "period_start",
    "billing_start": "period_start",
    "from_date": "period_start",
    "from": "period_start",
    "start_date": "period_start",
    "von": "period_start",
    "startdatum": "period_start",
    # Period end
    "period_end": "period_end",
    "billing_end": "period_end",
    "to_date": "period_end",
    "to": "period_end",
    "end_date": "period_end",
    "bis": "period_end",
    "enddatum": "period_end",
    # Opening meter read
    "opening_read": "opening_read",
    "meter_read_open": "opening_read",
    "reading_start": "opening_read",
    "open_read": "opening_read",
    "zaehlerstand_anfang": "opening_read",
    "zaehlerstand anfang": "opening_read",
    "prev_read": "opening_read",
    # Closing meter read
    "closing_read": "closing_read",
    "meter_read_close": "closing_read",
    "reading_end": "closing_read",
    "close_read": "closing_read",
    "zaehlerstand_ende": "closing_read",
    "zaehlerstand ende": "closing_read",
    "curr_read": "closing_read",
    # Net consumption
    "consumption": "consumption",
    "net_consumption": "consumption",
    "usage": "consumption",
    "verbrauch": "consumption",
    "menge": "consumption",
    "quantity": "consumption",
    # Unit
    "unit": "unit",
    "uom": "unit",
    "einheit": "unit",
    "commodity_unit": "unit",
    "mengeneinheit": "unit",
    # Commodity type
    "commodity": "commodity",
    "service_type": "commodity",
    "utility_type": "commodity",
    "medium": "commodity",
    "energietraeger": "commodity",
    "energy_carrier": "commodity",
    "type": "commodity",
    # Tariff
    "tariff_code": "tariff_code",
    "tariff": "tariff_code",
    "rate_code": "tariff_code",
    "tarifnummer": "tariff_code",
    "tarif": "tariff_code",
    # Rate / price
    "rate": "unit_rate",
    "unit_rate": "unit_rate",
    "price_per_unit": "unit_rate",
    "tarif_preis": "unit_rate",
    "preis": "unit_rate",
    # Currency
    "currency": "currency",
    "curr": "currency",
    "waehrung": "currency",
    "währung": "currency",
    # Meter identifier
    "meter_id": "meter_id",
    "meter_number": "meter_id",
    "zaehler_id": "meter_id",
    "zaehler_nummer": "meter_id",
    "mpan": "meter_id",
    "mprn": "meter_id",
    "meternr": "meter_id",
    # Account / invoice reference
    "account_ref": "account_ref",
    "account_number": "account_ref",
    "invoice_number": "account_ref",
    "rechnungsnummer": "account_ref",
    "invoice_no": "account_ref",
    # Site / location
    "site": "site",
    "site_id": "site",
    "site_name": "site",
    "location": "site",
    "standort": "site",
    "address": "site",
}

# Commodity keyword → canonical activity_type
_COMMODITY_ACTIVITY_MAP: dict[str, str] = {
    "electricity": "electricity",
    "strom": "electricity",
    "electric": "electricity",
    "power": "electricity",
    "gas": "gas",
    "erdgas": "gas",
    "natural gas": "gas",
    "naturalgas": "gas",
    "biogas": "gas",
    "lpg": "gas",
    "water": "water",
    "wasser": "water",
    "potable": "water",
    "heat": "heat",
    "heating": "heat",
    "district heat": "heat",
    "fernwärme": "heat",
    "fernwaerme": "heat",
    "steam": "heat",
    "thermal": "heat",
}

# (source_unit_lower) → (normalised_unit, multiplier)
_UNIT_NORMALISATION: dict[str, tuple[str, Decimal]] = {
    # Electricity
    "kwh": ("kWh", Decimal("1")),
    "mwh": ("kWh", Decimal("1000")),
    "gwh": ("kWh", Decimal("1_000_000")),
    # Gas – volumetric (convert using standard calorific value 10.55 kWh/m³)
    "m3": ("kWh", Decimal("10.55")),
    "m³": ("kWh", Decimal("10.55")),
    "cbm": ("kWh", Decimal("10.55")),
    "nm3": ("kWh", Decimal("10.55")),    # normal cubic metre
    # Gas – energy
    "gj": ("kWh", Decimal("277.778")),
    "mj": ("kWh", Decimal("0.277778")),
    "therm": ("kWh", Decimal("29.3071")),
    # Water (keep as m³ – no energy conversion)
    "liter": ("m3", Decimal("0.001")),
    "litre": ("m3", Decimal("0.001")),
    "l": ("m3", Decimal("0.001")),
    # District heat (GJ → kWh)
    "gj_heat": ("kWh", Decimal("277.778")),
}

# Activity type → fallback normalised unit when no unit mapping found
_ACTIVITY_DEFAULT_UNIT: dict[str, str] = {
    "electricity": "kWh",
    "gas": "kWh",
    "water": "m3",
    "heat": "kWh",
}

_REQUIRED_FIELDS = ["period_start", "commodity"]
_REQUIRED_CONSUMPTION_FIELDS = ["consumption"]  # OR opening+closing reads


# ---------------------------------------------------------------------------
# Utility Adapter
# ---------------------------------------------------------------------------

class UtilityAdapter(BaseAdapter):
    """
    Adapter for utility portal CSV exports.

    Parameters
    ----------
    delimiter : str
        CSV column separator. Defaults to ','.
    encoding : str
        File encoding. Defaults to 'utf-8-sig'.
    date_formats : list[str]
        strptime format strings tried in order when parsing date fields.
    gas_calorific_value : Decimal
        kWh per m³ for gas volume-to-energy conversion. Defaults to 10.55.
    """

    SOURCE_TYPE = "UTILITY"

    _DEFAULT_DATE_FORMATS = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d.%m.%Y",
        "%d-%m-%Y",
        "%Y%m%d",
    ]

    def __init__(
        self,
        delimiter: str = ",",
        encoding: str = "utf-8-sig",
        date_formats: Optional[list[str]] = None,
        gas_calorific_value: Decimal = Decimal("10.55"),
    ) -> None:
        self.delimiter = delimiter
        self.encoding = encoding
        self.date_formats = date_formats or self._DEFAULT_DATE_FORMATS
        self.gas_calorific_value = gas_calorific_value

    # ------------------------------------------------------------------
    # parse
    # ------------------------------------------------------------------

    def parse(self, raw: str | bytes) -> list[dict[str, Any]]:
        """
        Decode CSV and map all headers to canonical keys.

        If a row contains no explicit 'consumption' field but has
        opening and closing meter reads, the net consumption is derived
        here so that downstream stages have a consistent 'consumption' key.
        """
        if isinstance(raw, bytes):
            try:
                text = raw.decode(self.encoding)
            except UnicodeDecodeError:
                text = raw.decode("latin-1")
        else:
            text = raw

        reader = csv.DictReader(io.StringIO(text), delimiter=self.delimiter)
        rows: list[dict[str, Any]] = []

        for raw_row in reader:
            row = self._canonicalise_row(raw_row)

            # Derive consumption from meter reads if not explicitly present
            if not row.get("consumption"):
                opening = self._safe_decimal(row.get("opening_read"))
                closing = self._safe_decimal(row.get("closing_read"))
                if opening is not None and closing is not None:
                    row["consumption"] = str(closing - opening)
                    row["_consumption_derived"] = True

            rows.append(row)

        logger.debug("[UTILITY] parse() produced %d raw rows.", len(rows))
        return rows

    # ------------------------------------------------------------------
    # validate
    # ------------------------------------------------------------------

    def validate(self, rows: list[dict[str, Any]]) -> None:
        """
        Validate utility rows.

        Checks
        ------
        • period_start and commodity are present.
        • At least one of: consumption, or (opening_read + closing_read).
        • Dates parse correctly.
        • Consumption is a positive number.
        • period_end is after period_start when both present.
        """
        errors: list[dict[str, Any]] = []

        for idx, row in enumerate(rows, start=1):
            # Required fields
            for field_name in _REQUIRED_FIELDS:
                self._require_field(row, field_name, idx, errors)

            # Must have consumption or meter reads
            has_consumption = bool(row.get("consumption"))
            has_reads = bool(row.get("opening_read")) and bool(row.get("closing_read"))
            if not has_consumption and not has_reads:
                errors.append({
                    "row": idx,
                    "field": "consumption",
                    "message": (
                        "Row must provide either 'consumption' or both "
                        "'opening_read' and 'closing_read'."
                    ),
                })

            # Date checks
            for date_field in ("period_start", "period_end"):
                val = row.get(date_field)
                if val:
                    if self._parse_date(str(val)) is None:
                        errors.append({
                            "row": idx,
                            "field": date_field,
                            "message": (
                                f"Cannot parse date '{val}'. "
                                f"Tried formats: {self.date_formats}"
                            ),
                        })

            # Period ordering
            start_val = row.get("period_start")
            end_val = row.get("period_end")
            if start_val and end_val:
                d_start = self._parse_date(str(start_val))
                d_end = self._parse_date(str(end_val))
                if d_start and d_end and d_end < d_start:
                    errors.append({
                        "row": idx,
                        "field": "period_end",
                        "message": (
                            f"period_end ({end_val}) is before period_start ({start_val})."
                        ),
                    })

            # Positive consumption
            cons_val = row.get("consumption")
            if cons_val:
                d = self._safe_decimal(cons_val)
                if d is None:
                    errors.append({
                        "row": idx,
                        "field": "consumption",
                        "message": f"Non-numeric consumption: '{cons_val}'.",
                    })
                elif d <= 0:
                    errors.append({
                        "row": idx,
                        "field": "consumption",
                        "message": (
                            f"Consumption must be > 0; got '{cons_val}'."
                        ),
                    })

        if errors:
            raise AdapterValidationError(errors)

    # ------------------------------------------------------------------
    # normalize
    # ------------------------------------------------------------------

    def normalize(self, rows: list[dict[str, Any]]) -> list[NormalizedActivityRecord]:
        """
        Transform validated utility rows into NormalizedActivityRecord instances.

        The activity_date is set to the period_start of the billing period.
        Consumption is converted to the SI energy/volume unit for the commodity.
        """
        records: list[NormalizedActivityRecord] = []

        for row in rows:
            activity_type = self._detect_activity_type(row.get("commodity", ""))
            activity_date = self._parse_date(str(row["period_start"]))

            original_qty = self._safe_decimal(row.get("consumption")) or Decimal("0")
            original_unit = str(row.get("unit", "")).strip()

            normalised_qty, normalised_unit = self._normalise_unit(
                original_qty, original_unit, activity_type
            )

            meter_id = str(row.get("meter_id", "")).strip() or None
            site = str(row.get("site", "")).strip() or None
            account_ref = str(row.get("account_ref", "")).strip() or None
            period_end_str = str(row.get("period_end", "")).strip()
            tariff_code = str(row.get("tariff_code", "")).strip() or None

            # Build a meaningful description
            period_label = period_end_str if period_end_str else "?"
            description = (
                f"{activity_type.capitalize()} consumption "
                f"{original_qty} {original_unit or normalised_unit} "
                f"(period {row['period_start']} – {period_label})"
                + (f" at {site}" if site else "")
            )

            metadata: dict[str, Any] = {
                "period_start": str(row.get("period_start", "")),
                "period_end": period_end_str or None,
                "meter_id": meter_id,
                "tariff_code": tariff_code,
                "unit_rate": str(row.get("unit_rate", "")) or None,
                "currency": str(row.get("currency", "")).strip() or None,
                "opening_read": str(row.get("opening_read", "")) or None,
                "closing_read": str(row.get("closing_read", "")) or None,
                "consumption_derived": row.get("_consumption_derived", False),
                "commodity": row.get("commodity"),
            }
            metadata = {k: v for k, v in metadata.items() if v is not None}

            records.append(
                NormalizedActivityRecord(
                    source_type=self.SOURCE_TYPE,
                    activity_type=activity_type,
                    activity_date=activity_date,
                    quantity=normalised_qty,
                    unit=normalised_unit,
                    original_quantity=original_qty,
                    original_unit=original_unit or normalised_unit,
                    description=description,
                    source_reference=account_ref,
                    location=site or meter_id,
                    metadata=metadata,
                )
            )

        return records

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _canonicalise_row(self, raw_row: dict[str, Any]) -> dict[str, Any]:
        canonical: dict[str, Any] = {}
        for raw_key, value in raw_row.items():
            if raw_key is None:
                continue
            normalised_key = raw_key.strip().lower().replace(" ", "_").replace("-", "_")
            mapped = _HEADER_MAP.get(normalised_key) or _HEADER_MAP.get(raw_key.strip().lower())
            canonical_key = mapped or normalised_key
            canonical[canonical_key] = value.strip() if isinstance(value, str) else value
        return canonical

    def _parse_date(self, value: str) -> Optional[date]:
        value = value.strip()
        for fmt in self.date_formats:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _safe_decimal(value: Any) -> Optional[Decimal]:
        if value is None or str(value).strip() == "":
            return None
        try:
            cleaned = str(value).strip().replace(",", ".")
            return Decimal(cleaned)
        except InvalidOperation:
            return None

    @staticmethod
    def _detect_activity_type(commodity: str) -> str:
        commodity_lower = commodity.lower().strip()
        for keyword, activity in _COMMODITY_ACTIVITY_MAP.items():
            if keyword in commodity_lower:
                return activity
        logger.warning(
            "[UTILITY] Unrecognised commodity '%s'; defaulting to 'electricity'.",
            commodity,
        )
        return "electricity"

    @staticmethod
    def _normalise_unit(
        quantity: Decimal, unit: str, activity_type: str
    ) -> tuple[Decimal, str]:
        unit_key = unit.strip().lower()

        # Special case: water should stay in m³ regardless of general table
        if activity_type == "water":
            if unit_key in ("m3", "m³", "cbm"):
                return quantity.quantize(Decimal("0.000001")), "m3"
            if unit_key in ("l", "liter", "litre"):
                return (quantity * Decimal("0.001")).quantize(Decimal("0.000001")), "m3"
            return quantity.quantize(Decimal("0.000001")), "m3"

        if unit_key in _UNIT_NORMALISATION:
            target_unit, factor = _UNIT_NORMALISATION[unit_key]
            return (quantity * factor).quantize(Decimal("0.000001")), target_unit

        # Unknown unit: use activity default
        fallback = _ACTIVITY_DEFAULT_UNIT.get(activity_type, "kWh")
        logger.warning(
            "[UTILITY] Unknown unit '%s' for activity '%s'; using '%s' with no conversion.",
            unit, activity_type, fallback,
        )
        return quantity.quantize(Decimal("0.000001")), fallback
