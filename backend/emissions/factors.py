"""
emissions/factors.py
====================
Seed data for GHG emission factors (DEFRA 2023 / GHG Protocol).

Call ``seed_emission_factors()`` in a migration or management command to
populate the EmissionFactor table.

Factor sources
--------------
- DEFRA 2023 GHG Conversion Factors for Company Reporting
- ICAO Carbon Emissions Calculator methodology
- GHG Protocol Scope 2 Guidance

All factors are expressed as kgCO₂e per normalised unit.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

# Each entry: (activity_type, unit, factor_kgco2e, region, source, notes)
SEED_FACTORS: list[dict[str, Any]] = [
    # -------------------------------------------------------------------------
    # Scope 1 – Fuel (Litres)
    # -------------------------------------------------------------------------
    {
        "activity_type": "fuel",
        "unit": "L",
        "factor_kgco2e": Decimal("2.68858"),
        "region": "GLOBAL",
        "source": "DEFRA 2023",
        "notes": "Diesel combustion (market basket average), includes CO₂+CH₄+N₂O.",
        "valid_from": date(2023, 1, 1),
    },
    # -------------------------------------------------------------------------
    # Scope 2 – Electricity (kWh)
    # -------------------------------------------------------------------------
    {
        "activity_type": "electricity",
        "unit": "kWh",
        "factor_kgco2e": Decimal("0.23314"),
        "region": "UK",
        "source": "DEFRA 2023",
        "notes": "UK grid average electricity (location-based).",
        "valid_from": date(2023, 1, 1),
    },
    {
        "activity_type": "electricity",
        "unit": "kWh",
        "factor_kgco2e": Decimal("0.23300"),
        "region": "EU",
        "source": "IEA 2022",
        "notes": "EU-27 grid average electricity.",
        "valid_from": date(2022, 1, 1),
    },
    {
        "activity_type": "electricity",
        "unit": "kWh",
        "factor_kgco2e": Decimal("0.38600"),
        "region": "US",
        "source": "EPA eGRID 2022",
        "notes": "US national average grid electricity.",
        "valid_from": date(2022, 1, 1),
    },
    {
        "activity_type": "electricity",
        "unit": "kWh",
        "factor_kgco2e": Decimal("0.40600"),
        "region": "AU",
        "source": "Australian NGER 2022",
        "notes": "Australian national grid average.",
        "valid_from": date(2022, 1, 1),
    },
    {
        "activity_type": "electricity",
        "unit": "kWh",
        "factor_kgco2e": Decimal("0.36600"),
        "region": "DE",
        "source": "German UBA 2022",
        "notes": "German grid electricity factor.",
        "valid_from": date(2022, 1, 1),
    },
    {
        "activity_type": "electricity",
        "unit": "kWh",
        "factor_kgco2e": Decimal("0.28300"),
        "region": "GLOBAL",
        "source": "IEA 2022",
        "notes": "Global weighted average grid electricity (fallback).",
        "valid_from": date(2022, 1, 1),
    },
    # -------------------------------------------------------------------------
    # Scope 2 – Natural Gas (kWh)  [already converted from m³ by adapter]
    # -------------------------------------------------------------------------
    {
        "activity_type": "gas",
        "unit": "kWh",
        "factor_kgco2e": Decimal("0.18316"),
        "region": "UK",
        "source": "DEFRA 2023",
        "notes": "UK natural gas (gross calorific value basis).",
        "valid_from": date(2023, 1, 1),
    },
    {
        "activity_type": "gas",
        "unit": "kWh",
        "factor_kgco2e": Decimal("0.20200"),
        "region": "GLOBAL",
        "source": "GHG Protocol",
        "notes": "Global average natural gas (fallback).",
        "valid_from": date(2022, 1, 1),
    },
    # -------------------------------------------------------------------------
    # Scope 2 – District Heat (kWh)
    # -------------------------------------------------------------------------
    {
        "activity_type": "heat",
        "unit": "kWh",
        "factor_kgco2e": Decimal("0.12700"),
        "region": "GLOBAL",
        "source": "DEFRA 2023",
        "notes": "District heating and steam (global average).",
        "valid_from": date(2023, 1, 1),
    },
    # -------------------------------------------------------------------------
    # Scope 3 – Water (m³)
    # -------------------------------------------------------------------------
    {
        "activity_type": "water",
        "unit": "m3",
        "factor_kgco2e": Decimal("0.14900"),
        "region": "UK",
        "source": "DEFRA 2023",
        "notes": "Water supply and treatment (UK).",
        "valid_from": date(2023, 1, 1),
    },
    {
        "activity_type": "water",
        "unit": "m3",
        "factor_kgco2e": Decimal("0.34400"),
        "region": "GLOBAL",
        "source": "GHG Protocol",
        "notes": "Global average water supply (fallback).",
        "valid_from": date(2022, 1, 1),
    },
    # -------------------------------------------------------------------------
    # Scope 3 – Flights (km per passenger)
    # Note: cabin class multipliers are applied in the service layer.
    # This base factor is for economy class.
    # -------------------------------------------------------------------------
    {
        "activity_type": "flight",
        "unit": "km",
        "factor_kgco2e": Decimal("0.25500"),
        "region": "GLOBAL",
        "source": "DEFRA 2023 / ICAO",
        "notes": (
            "Economy class, per passenger-km, includes radiative forcing (RFI=2.0). "
            "Business class: ×2.0, First class: ×3.0."
        ),
        "valid_from": date(2023, 1, 1),
    },
    # -------------------------------------------------------------------------
    # Scope 3 – Hotel stays (room-nights)
    # -------------------------------------------------------------------------
    {
        "activity_type": "hotel",
        "unit": "night",
        "factor_kgco2e": Decimal("30.35000"),
        "region": "GLOBAL",
        "source": "DEFRA 2023",
        "notes": "Average hotel room per night (all star ratings combined).",
        "valid_from": date(2023, 1, 1),
    },
    # -------------------------------------------------------------------------
    # Scope 3 – Ground transport (km)
    # -------------------------------------------------------------------------
    {
        "activity_type": "ground_transport",
        "unit": "km",
        "factor_kgco2e": Decimal("0.16844"),
        "region": "UK",
        "source": "DEFRA 2023",
        "notes": "Average car (unknown fuel) per vehicle-km (UK).",
        "valid_from": date(2023, 1, 1),
    },
    {
        "activity_type": "ground_transport",
        "unit": "km",
        "factor_kgco2e": Decimal("0.17100"),
        "region": "GLOBAL",
        "source": "GHG Protocol",
        "notes": "Global average passenger car per vehicle-km (fallback).",
        "valid_from": date(2022, 1, 1),
    },
    # -------------------------------------------------------------------------
    # Scope 3 – Procurement (kg of purchased goods)
    # -------------------------------------------------------------------------
    {
        "activity_type": "procurement",
        "unit": "kg",
        "factor_kgco2e": Decimal("0.43800"),
        "region": "GLOBAL",
        "source": "Ecoinvent 3.9",
        "notes": "Generic manufactured goods average (proxy factor).",
        "valid_from": date(2022, 1, 1),
    },
]


def seed_emission_factors() -> int:
    """
    Insert SEED_FACTORS into the EmissionFactor table.
    Skips rows that already exist (matched on activity_type + unit + region + valid_from).
    Returns the count of newly created rows.
    """
    # Import here to avoid circular import at module load time
    from emissions.models import EmissionFactor

    created = 0
    for entry in SEED_FACTORS:
        _, was_created = EmissionFactor.objects.get_or_create(
            activity_type=entry["activity_type"],
            unit=entry["unit"],
            region=entry["region"],
            valid_from=entry["valid_from"],
            defaults={
                "factor_kgco2e": entry["factor_kgco2e"],
                "source": entry["source"],
                "notes": entry.get("notes", ""),
            },
        )
        if was_created:
            created += 1
    return created
