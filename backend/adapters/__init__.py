"""
CarbonBridge Source Adapters Package
=====================================
Pluggable adapters for parsing, validating, and normalizing raw activity
data from heterogeneous upstream sources into the unified CarbonBridge schema.

Adapters:
  - SAPAdapter       → SAP ERP CSV exports (Scope 1/2 fuel & energy)
  - UtilityAdapter   → Utility-portal CSV exports (electricity, gas, water)
  - TravelAdapter    → Concur-style JSON exports (flights, hotels, ground)

Each adapter exposes:
  parse()      → convert raw bytes/string into structured Python dicts
  validate()   → check field presence, types, and value ranges
  normalize()  → transform to the unified NormalizedActivityRecord schema
"""

from .base import NormalizedActivityRecord, AdapterValidationError
from .sap_adapter import SAPAdapter
from .utility_adapter import UtilityAdapter
from .travel_adapter import TravelAdapter

__all__ = [
    "NormalizedActivityRecord",
    "AdapterValidationError",
    "SAPAdapter",
    "UtilityAdapter",
    "TravelAdapter",
]
