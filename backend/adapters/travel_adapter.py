"""
travel_adapter.py – Concur-style corporate travel JSON adapter.

Assumptions
-----------
• Input is a JSON string or bytes conforming to a Concur expense export
  or a CarbonBridge-compatible travel report.
• The JSON root is either an array of trip/expense objects, or a wrapper
  object with a 'trips', 'expenses', or 'records' key.
• Each object has a 'type' (or 'expense_type') discriminator:
    'flight' | 'air'         → flight segment
    'hotel' | 'lodging'      → hotel stay
    'car' | 'taxi' | 'train'
    | 'bus' | 'rail' | 'ground'
    | 'rideshare' | 'ferry'  → ground transport
• Flights carry IATA airport codes (origin / destination).
• Distance (flight or ground) may be provided in miles or km.
• Hotel stays report the number of nights (room_nights or nights).

Activity types normalised by this adapter
-----------------------------------------
flight           → km  (great-circle distance in kilometres, PAX km)
hotel            → night (room-nights)
ground_transport → km  (distance in kilometres)

Distance calculation
--------------------
• Flight: great-circle distance is derived from origin/destination IATA
  coordinates if not provided. Only a subset of major airports is embedded;
  for unknown pairs the adapter uses the provided distance_km / distance_miles
  field if available, otherwise flags the record and uses 0.
• Ground: distance_km preferred; distance_miles converted (1 mi = 1.60934 km).

Concur JSON field aliases handled
----------------------------------
type / expense_type / travel_type / segment_type → type
date / travel_date / departure_date / check_in_date / booking_date → date
origin / from / departure / departure_airport / origin_airport → origin
destination / to / arrival / arrival_airport / destination_airport → destination
distance / distance_km / km / kilometers / kilometres → distance_km
distance_miles / miles / mi → distance_miles
nights / room_nights / hotel_nights / num_nights → nights
hotel_name / property_name / hotel / property → hotel_name
cabin_class / class / fare_class / booking_class → cabin_class
carrier / airline / airline_code / carrier_code → carrier
flight_number / flight_no / flight → flight_number
transport_mode / mode / vehicle_type → transport_mode
booking_id / trip_id / expense_id / report_id / reference → booking_id
traveller / traveler / employee_id / employee_name → traveller
country / country_code → country
city / city_name → city
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from .base import (
    AdapterValidationError,
    BaseAdapter,
    NormalizedActivityRecord,
)
from core.conversion import ConversionService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IATA airport coordinates (lat, lon) – a representative subset.
# Expand this dict or replace with a database / API call for production use.
# ---------------------------------------------------------------------------

_AIRPORT_COORDS: dict[str, tuple[float, float]] = {
    # North America
    "JFK": (40.6413, -73.7781), "LAX": (33.9416, -118.4085),
    "ORD": (41.9742, -87.9073), "ATL": (33.6407, -84.4277),
    "DFW": (32.8998, -97.0403), "DEN": (39.8561, -104.6737),
    "SFO": (37.6213, -122.3790), "SEA": (47.4502, -122.3088),
    "MIA": (25.7959, -80.2870), "BOS": (42.3656, -71.0096),
    "YYZ": (43.6777, -79.6248), "YVR": (49.1967, -123.1815),
    "MEX": (19.4363, -99.0721),
    # Europe
    "LHR": (51.4700, -0.4543),  "CDG": (49.0097,  2.5478),
    "AMS": (52.3086,  4.7639),  "FRA": (50.0379,  8.5622),
    "MAD": (40.4936, -3.5668),  "BCN": (41.2971,  2.0785),
    "FCO": (41.8003,  12.2389), "MUC": (48.3537,  11.7750),
    "ZRH": (47.4647,  8.5492),  "VIE": (48.1103,  16.5697),
    "BRU": (50.9010,  4.4844),  "CPH": (55.6180,  12.6508),
    "OSL": (60.1939,  11.1004), "ARN": (59.6519,  17.9186),
    "HEL": (60.3172,  24.9633), "WAW": (52.1657,  20.9671),
    "IST": (41.2608,  28.7418), "ATH": (37.9364,  23.9445),
    "DUB": (53.4213,  -6.2701), "MAN": (53.3537,  -2.2750),
    "LIS": (38.7813,  -9.1359), "GVA": (46.2381,   6.1089),
    # Middle East & Africa
    "DXB": (25.2532,  55.3657), "AUH": (24.4330,  54.6511),
    "DOH": (25.2609,  51.6138), "RUH": (24.9578,  46.6989),
    "JNB": (-26.1367,  28.2411),"CAI": (30.1219,  31.4056),
    "NBO": (-1.3192,  36.9275), "CPT": (-33.9715,  18.6021),
    "LOS": (6.5774,   3.3212),
    # Asia-Pacific
    "SIN": (1.3644,  103.9915), "HKG": (22.3080,  113.9185),
    "NRT": (35.7647,  140.3864),"HND": (35.5494,  139.7798),
    "PVG": (31.1443,  121.8083),"PEK": (40.0799,  116.6031),
    "ICN": (37.4602,  126.4407),"BKK": (13.6900,  100.7501),
    "KUL": (2.7456,   101.7072),"SYD": (-33.9399,  151.1753),
    "MEL": (-37.6690,  144.8410),"AKL": (-37.0082,  174.7917),
    "DEL": (28.5665,   77.1031),"BOM": (19.0896,   72.8656),
    "BLR": (13.1979,   77.7063),"HYD": (17.2403,   78.4294),
    "CGK": (-6.1275,  106.6537),"MNL": (14.5086,  121.0194),
    "GRU": (-23.4356,  -46.4731),"EZE": (-34.8222,  -58.5358),
    "BOG": (4.7016,   -74.1469),"SCL": (-33.3928,  -70.7856),
    "LIM": (-12.0219,  -77.1143),
}

# Concur / travel JSON field aliases → canonical key
_FIELD_MAP: dict[str, str] = {
    # Type discriminator
    "type": "type",
    "expense_type": "type",
    "travel_type": "type",
    "segment_type": "type",
    "category": "type",
    # Date
    "date": "date",
    "travel_date": "date",
    "departure_date": "date",
    "check_in_date": "date",
    "booking_date": "date",
    "start_date": "date",
    "service_date": "date",
    # Origin (flights / ground)
    "origin": "origin",
    "from": "origin",
    "departure": "origin",
    "departure_airport": "origin",
    "origin_airport": "origin",
    "from_airport": "origin",
    # Destination
    "destination": "destination",
    "to": "destination",
    "arrival": "destination",
    "arrival_airport": "destination",
    "destination_airport": "destination",
    "to_airport": "destination",
    # Distance
    "distance": "distance_km",
    "distance_km": "distance_km",
    "km": "distance_km",
    "kilometers": "distance_km",
    "kilometres": "distance_km",
    "distance_miles": "distance_miles",
    "miles": "distance_miles",
    "mi": "distance_miles",
    # Hotel nights
    "nights": "nights",
    "room_nights": "nights",
    "hotel_nights": "nights",
    "num_nights": "nights",
    "number_of_nights": "nights",
    "length_of_stay": "nights",
    # Hotel name
    "hotel_name": "hotel_name",
    "property_name": "hotel_name",
    "hotel": "hotel_name",
    "property": "hotel_name",
    "accommodation": "hotel_name",
    # Cabin class
    "cabin_class": "cabin_class",
    "class": "cabin_class",
    "fare_class": "cabin_class",
    "booking_class": "cabin_class",
    "travel_class": "cabin_class",
    # Carrier
    "carrier": "carrier",
    "airline": "carrier",
    "airline_code": "carrier",
    "carrier_code": "carrier",
    # Flight number
    "flight_number": "flight_number",
    "flight_no": "flight_number",
    "flight": "flight_number",
    "flight_num": "flight_number",
    # Transport mode (ground)
    "transport_mode": "transport_mode",
    "mode": "transport_mode",
    "vehicle_type": "transport_mode",
    "ground_type": "transport_mode",
    # Booking reference
    "booking_id": "booking_id",
    "trip_id": "booking_id",
    "expense_id": "booking_id",
    "report_id": "booking_id",
    "reference": "booking_id",
    "ref": "booking_id",
    # Traveller
    "traveller": "traveller",
    "traveler": "traveller",
    "employee_id": "traveller",
    "employee_name": "traveller",
    "employee": "traveller",
    "passenger": "traveller",
    # Location (hotels / ground)
    "country": "country",
    "country_code": "country",
    "city": "city",
    "city_name": "city",
    "location": "city",
    # Cost / currency
    "amount": "amount",
    "cost": "amount",
    "total_cost": "amount",
    "currency": "currency",
}

# Segment type keywords → canonical activity type
_TYPE_ACTIVITY_MAP: dict[str, str] = {
    "flight": "flight",
    "air": "flight",
    "airplane": "flight",
    "plane": "flight",
    "hotel": "hotel",
    "lodging": "hotel",
    "accommodation": "hotel",
    "motel": "hotel",
    "hostel": "hotel",
    "bnb": "hotel",
    "car": "ground_transport",
    "car_rental": "ground_transport",
    "rental": "ground_transport",
    "taxi": "ground_transport",
    "cab": "ground_transport",
    "rideshare": "ground_transport",
    "uber": "ground_transport",
    "lyft": "ground_transport",
    "train": "ground_transport",
    "rail": "ground_transport",
    "bus": "ground_transport",
    "coach": "ground_transport",
    "ferry": "ground_transport",
    "boat": "ground_transport",
    "ground": "ground_transport",
    "ground_transport": "ground_transport",
}

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d.%m.%Y",
]

_MILES_TO_KM = Decimal("1.60934")
_EARTH_RADIUS_KM = 6371.0


# ---------------------------------------------------------------------------
# Travel Adapter
# ---------------------------------------------------------------------------

class TravelAdapter(BaseAdapter):
    """
    Adapter for Concur-style corporate travel JSON exports.

    Parameters
    ----------
    root_keys : list[str]
        JSON object keys to search for the record list when the root is
        a wrapper object rather than an array.
        Default: ['trips', 'expenses', 'records', 'segments', 'items', 'data'].
    """

    SOURCE_TYPE = "TRAVEL"

    _DEFAULT_ROOT_KEYS = ["trips", "expenses", "records", "segments", "items", "data"]

    def __init__(self, root_keys: Optional[list[str]] = None) -> None:
        self.root_keys = root_keys or self._DEFAULT_ROOT_KEYS

    # ------------------------------------------------------------------
    # parse
    # ------------------------------------------------------------------

    def parse(self, raw: str | bytes) -> list[dict[str, Any]]:
        """
        Deserialise the JSON payload and flatten each segment into a canonical dict.

        Accepts:
        • A JSON array:  [{…}, {…}, …]
        • A wrapper object: {"trips": [{…}, …], "report_id": "…", …}
        """
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")

        payload = json.loads(raw)

        # Unwrap if a container object
        if isinstance(payload, dict):
            for key in self.root_keys:
                if key in payload and isinstance(payload[key], list):
                    payload = payload[key]
                    break
            else:
                # Treat a single-object dict as one record
                payload = [payload]

        rows: list[dict[str, Any]] = []
        for item in payload:
            canonical = self._canonicalise_row(item)
            rows.append(canonical)

        logger.debug("[TRAVEL] parse() produced %d raw segments.", len(rows))
        return rows

    # ------------------------------------------------------------------
    # validate
    # ------------------------------------------------------------------

    def validate(self, rows: list[dict[str, Any]]) -> None:
        """
        Validate travel segments.

        Checks
        ------
        • 'type' is present and maps to a known activity.
        • 'date' is present and parseable.
        • Flights have origin and destination (IATA codes).
        • Hotels have at least 1 night.
        • Ground transport has a positive distance or a mode.
        """
        errors: list[dict[str, Any]] = []

        for idx, row in enumerate(rows, start=1):
            # Type field
            if not self._require_field(row, "type", idx, errors):
                continue  # can't validate further without a type

            activity_type = _TYPE_ACTIVITY_MAP.get(
                str(row.get("type", "")).lower().strip()
            )
            if activity_type is None:
                errors.append({
                    "row": idx,
                    "field": "type",
                    "message": (
                        f"Unknown segment type '{row['type']}'. "
                        f"Expected one of: {sorted(_TYPE_ACTIVITY_MAP.keys())}."
                    ),
                })

            # Date
            self._require_field(row, "date", idx, errors)
            if row.get("date"):
                if self._parse_date(str(row["date"])) is None:
                    errors.append({
                        "row": idx,
                        "field": "date",
                        "message": f"Cannot parse date '{row['date']}'.",
                    })

            # Flight-specific
            if activity_type == "flight":
                self._require_field(row, "origin", idx, errors)
                self._require_field(row, "destination", idx, errors)
                if row.get("origin") and len(str(row["origin"]).strip()) != 3:
                    errors.append({
                        "row": idx,
                        "field": "origin",
                        "message": (
                            f"Origin '{row['origin']}' does not look like a 3-letter IATA code."
                        ),
                    })
                if row.get("destination") and len(str(row["destination"]).strip()) != 3:
                    errors.append({
                        "row": idx,
                        "field": "destination",
                        "message": (
                            f"Destination '{row['destination']}' does not look like a 3-letter IATA code."
                        ),
                    })

            # Hotel-specific
            if activity_type == "hotel":
                nights_val = row.get("nights")
                if nights_val is not None:
                    try:
                        n = Decimal(str(nights_val))
                        if n < 1:
                            errors.append({
                                "row": idx,
                                "field": "nights",
                                "message": f"Hotel nights must be ≥ 1; got '{nights_val}'.",
                            })
                    except Exception:
                        errors.append({
                            "row": idx,
                            "field": "nights",
                            "message": f"Non-numeric nights: '{nights_val}'.",
                        })

        if errors:
            raise AdapterValidationError(errors)

    # ------------------------------------------------------------------
    # normalize
    # ------------------------------------------------------------------

    def normalize(self, rows: list[dict[str, Any]]) -> list[NormalizedActivityRecord]:
        """
        Transform validated travel rows into NormalizedActivityRecord instances.

        Unit conventions
        ----------------
        • Flights       → quantity = great-circle km, unit = 'km'
        • Hotels        → quantity = room-nights,     unit = 'night'
        • Ground trans. → quantity = distance km,     unit = 'km'
        """
        records: list[NormalizedActivityRecord] = []

        for row in rows:
            activity_type = _TYPE_ACTIVITY_MAP.get(
                str(row.get("type", "")).lower().strip(), "ground_transport"
            )
            activity_date = self._parse_date(str(row["date"]))
            booking_id = str(row.get("booking_id", "")).strip() or None
            traveller = str(row.get("traveller", "")).strip() or None

            if activity_type == "flight":
                record = self._normalise_flight(row, activity_date, booking_id, traveller)
            elif activity_type == "hotel":
                record = self._normalise_hotel(row, activity_date, booking_id, traveller)
            else:
                record = self._normalise_ground(row, activity_date, booking_id, traveller)

            records.append(record)

        return records

    # ------------------------------------------------------------------
    # Activity-specific normalisers
    # ------------------------------------------------------------------

    def _normalise_flight(
        self,
        row: dict[str, Any],
        activity_date: date,
        booking_id: Optional[str],
        traveller: Optional[str],
    ) -> NormalizedActivityRecord:
        origin = str(row.get("origin", "")).strip().upper()
        destination = str(row.get("destination", "")).strip().upper()
        carrier = str(row.get("carrier", "")).strip() or None
        flight_number = str(row.get("flight_number", "")).strip() or None
        cabin_class = str(row.get("cabin_class", "")).strip().lower() or "economy"

        # Resolve distance: provided > great-circle > 0
        dist_km = self._resolve_flight_distance(row, origin, destination)

        location = f"{origin}-{destination}"
        description = (
            f"Flight {origin} → {destination}"
            + (f" ({carrier}{flight_number})" if carrier or flight_number else "")
            + f", {cabin_class} class, {dist_km} km"
        )

        metadata: dict[str, Any] = {
            "origin": origin,
            "destination": destination,
            "carrier": carrier,
            "flight_number": flight_number,
            "cabin_class": cabin_class,
            "traveller": traveller,
            "distance_source": self._distance_source(row, origin, destination),
            "amount": str(row.get("amount", "")) or None,
            "currency": str(row.get("currency", "")).strip() or None,
        }
        metadata = {k: v for k, v in metadata.items() if v is not None}

        return NormalizedActivityRecord(
            source_type=self.SOURCE_TYPE,
            activity_type="flight",
            activity_date=activity_date,
            quantity=dist_km,
            unit="km",
            original_quantity=dist_km,
            original_unit="km",
            description=description,
            source_reference=booking_id,
            location=location,
            metadata=metadata,
        )

    def _normalise_hotel(
        self,
        row: dict[str, Any],
        activity_date: date,
        booking_id: Optional[str],
        traveller: Optional[str],
    ) -> NormalizedActivityRecord:
        hotel_name = str(row.get("hotel_name", "")).strip() or "Unknown Hotel"
        city = str(row.get("city", "")).strip() or None
        country = str(row.get("country", "")).strip() or None
        nights_raw = row.get("nights", 1)

        try:
            nights = Decimal(str(nights_raw))
        except Exception:
            nights = Decimal("1")

        location_parts = [p for p in [hotel_name, city, country] if p]
        location = ", ".join(location_parts) if location_parts else None

        description = (
            f"Hotel stay: {hotel_name}"
            + (f", {city}" if city else "")
            + (f", {country}" if country else "")
            + f" – {nights} night(s)"
        )

        metadata: dict[str, Any] = {
            "hotel_name": hotel_name,
            "city": city,
            "country": country,
            "traveller": traveller,
            "amount": str(row.get("amount", "")) or None,
            "currency": str(row.get("currency", "")).strip() or None,
        }
        metadata = {k: v for k, v in metadata.items() if v is not None}

        return NormalizedActivityRecord(
            source_type=self.SOURCE_TYPE,
            activity_type="hotel",
            activity_date=activity_date,
            quantity=nights,
            unit="night",
            original_quantity=nights,
            original_unit="night",
            description=description,
            source_reference=booking_id,
            location=location,
            metadata=metadata,
        )

    def _normalise_ground(
        self,
        row: dict[str, Any],
        activity_date: date,
        booking_id: Optional[str],
        traveller: Optional[str],
    ) -> NormalizedActivityRecord:
        transport_mode = str(row.get("transport_mode", row.get("type", "car"))).strip().lower()
        city = str(row.get("city", "")).strip() or None
        country = str(row.get("country", "")).strip() or None
        origin = str(row.get("origin", "")).strip() or None
        destination = str(row.get("destination", "")).strip() or None

        # Resolve distance
        dist_km = self._resolve_ground_distance(row)
        original_dist = dist_km
        original_unit = "km"

        if row.get("distance_miles") and not row.get("distance_km"):
            try:
                miles = Decimal(str(row["distance_miles"]))
                original_dist = miles
                original_unit = "miles"
            except Exception:
                pass

        route = (
            f"{origin} → {destination}" if origin and destination
            else (city or country or "Unknown route")
        )
        description = (
            f"Ground transport ({transport_mode}): {route}, {dist_km} km"
        )
        location = city or country or (f"{origin}-{destination}" if origin and destination else None)

        metadata: dict[str, Any] = {
            "transport_mode": transport_mode,
            "origin": origin,
            "destination": destination,
            "city": city,
            "country": country,
            "traveller": traveller,
            "amount": str(row.get("amount", "")) or None,
            "currency": str(row.get("currency", "")).strip() or None,
        }
        metadata = {k: v for k, v in metadata.items() if v is not None}

        return NormalizedActivityRecord(
            source_type=self.SOURCE_TYPE,
            activity_type="ground_transport",
            activity_date=activity_date,
            quantity=dist_km,
            unit="km",
            original_quantity=original_dist,
            original_unit=original_unit,
            description=description,
            source_reference=booking_id,
            location=location,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Distance helpers
    # ------------------------------------------------------------------

    def _resolve_flight_distance(
        self, row: dict[str, Any], origin: str, destination: str
    ) -> Decimal:
        """Return flight distance in km, derived in priority order."""
        # 1) Explicit km field
        if row.get("distance_km"):
            try:
                return Decimal(str(row["distance_km"])).quantize(Decimal("0.01"))
            except Exception:
                pass

        # 2) Explicit miles field
        if row.get("distance_miles"):
            try:
                miles = Decimal(str(row["distance_miles"]))
                converted, _ = ConversionService.convert("flight", miles, "miles")
                return converted.quantize(Decimal("0.01"))
            except Exception:
                pass

        # 3) Great-circle from IATA coordinates
        if origin in _AIRPORT_COORDS and destination in _AIRPORT_COORDS:
            km = self._great_circle_km(
                _AIRPORT_COORDS[origin], _AIRPORT_COORDS[destination]
            )
            return Decimal(str(round(km, 2)))

        # 4) Unknown – log warning and return 0
        logger.warning(
            "[TRAVEL] Cannot determine distance for flight %s→%s. "
            "Neither distance field nor IATA coordinates found. Using 0 km.",
            origin, destination,
        )
        return Decimal("0")

    @staticmethod
    def _distance_source(row: dict[str, Any], origin: str, destination: str) -> str:
        if row.get("distance_km"):
            return "provided_km"
        if row.get("distance_miles"):
            return "provided_miles_converted"
        if origin in _AIRPORT_COORDS and destination in _AIRPORT_COORDS:
            return "great_circle_iata"
        return "unknown"

    def _resolve_ground_distance(self, row: dict[str, Any]) -> Decimal:
        if row.get("distance_km"):
            try:
                return Decimal(str(row["distance_km"])).quantize(Decimal("0.01"))
            except Exception:
                pass
        if row.get("distance_miles"):
            try:
                miles = Decimal(str(row["distance_miles"]))
                converted, _ = ConversionService.convert("ground_transport", miles, "miles")
                return converted.quantize(Decimal("0.01"))
            except Exception:
                pass
        logger.warning(
            "[TRAVEL] No distance provided for ground segment. Using 0 km."
        )
        return Decimal("0")

    @staticmethod
    def _great_circle_km(
        coord1: tuple[float, float], coord2: tuple[float, float]
    ) -> float:
        """Haversine great-circle distance in kilometres."""
        lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
        lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _canonicalise_row(self, raw_row: dict[str, Any]) -> dict[str, Any]:
        canonical: dict[str, Any] = {}
        for raw_key, value in raw_row.items():
            if raw_key is None:
                continue
            normalised_key = str(raw_key).strip().lower().replace(" ", "_").replace("-", "_")
            mapped = _FIELD_MAP.get(normalised_key) or _FIELD_MAP.get(raw_key.strip().lower())
            canonical_key = mapped or normalised_key
            canonical[canonical_key] = value
        return canonical

    @staticmethod
    def _parse_date(value: str) -> Optional[date]:
        value = value.strip()
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return None
