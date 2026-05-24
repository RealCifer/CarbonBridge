"""
tests/test_adapters.py
======================
Unit tests for all three CarbonBridge source adapters.
Run with:  python -m pytest backend/tests/test_adapters.py -v
"""

import json
import sys
import os
import textwrap
from datetime import date
from decimal import Decimal

# Make the backend package importable when running from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from adapters.base import AdapterValidationError, NormalizedActivityRecord
from adapters.sap_adapter import SAPAdapter
from adapters.utility_adapter import UtilityAdapter
from adapters.travel_adapter import TravelAdapter


# =============================================================================
# SAP Adapter Tests
# =============================================================================

class TestSAPAdapterParse:

    def _csv(self, content: str) -> bytes:
        return textwrap.dedent(content).strip().encode("utf-8-sig")

    def test_parse_english_headers(self):
        raw = self._csv("""
            posting_date;plant_code;material_group;quantity;unit;document_number
            2024-01-15;PLANT01;Diesel;450;L;4500001
        """)
        adapter = SAPAdapter()
        rows = adapter.parse(raw)
        assert len(rows) == 1
        assert rows[0]["posting_date"] == "2024-01-15"
        assert rows[0]["plant_code"] == "PLANT01"
        assert rows[0]["quantity"] == "450"

    def test_parse_german_headers(self):
        raw = self._csv("""
            Buchungsdatum;Werk;Materialgruppe;Menge;Mengeneinheit;Belegnummer
            15.01.2024;W001;Diesel;1.234,56;L;4500002
        """)
        adapter = SAPAdapter()
        rows = adapter.parse(raw)
        assert len(rows) == 1
        assert rows[0]["posting_date"] == "15.01.2024"
        assert rows[0]["plant_code"] == "W001"
        assert rows[0]["quantity"] == "1.234,56"

    def test_parse_latin1_encoding(self):
        raw = "Buchungsdatum;Werk;Materialgruppe;Menge;Mengeneinheit\n15.01.2024;W001;Heizöl;100;L".encode("latin-1")
        adapter = SAPAdapter()
        rows = adapter.parse(raw)
        assert len(rows) == 1

    def test_parse_multiple_rows(self):
        raw = self._csv("""
            posting_date;plant;material_group;quantity;unit
            2024-01-01;P1;Diesel;100;L
            2024-01-02;P2;Strom;500;kWh
            2024-01-03;P3;Rohstoff;250;kg
        """)
        rows = SAPAdapter().parse(raw)
        assert len(rows) == 3


class TestSAPAdapterValidate:

    def _make_row(self, **overrides):
        row = {
            "posting_date": "2024-01-15",
            "plant_code": "PLANT01",
            "material_group": "Diesel",
            "quantity": "450",
            "unit": "L",
        }
        row.update(overrides)
        return row

    def test_valid_row_passes(self):
        SAPAdapter().validate([self._make_row()])  # must not raise

    def test_missing_posting_date_raises(self):
        with pytest.raises(AdapterValidationError) as exc_info:
            SAPAdapter().validate([self._make_row(posting_date="")])
        assert any(e["field"] == "posting_date" for e in exc_info.value.errors)

    def test_missing_quantity_raises(self):
        with pytest.raises(AdapterValidationError) as exc_info:
            SAPAdapter().validate([self._make_row(quantity="")])
        assert any(e["field"] == "quantity" for e in exc_info.value.errors)

    def test_negative_quantity_raises(self):
        with pytest.raises(AdapterValidationError) as exc_info:
            SAPAdapter().validate([self._make_row(quantity="-5")])
        assert any(e["field"] == "quantity" for e in exc_info.value.errors)

    def test_non_numeric_quantity_raises(self):
        with pytest.raises(AdapterValidationError) as exc_info:
            SAPAdapter().validate([self._make_row(quantity="abc")])
        assert any(e["field"] == "quantity" for e in exc_info.value.errors)

    def test_unparseable_date_raises(self):
        with pytest.raises(AdapterValidationError) as exc_info:
            SAPAdapter().validate([self._make_row(posting_date="32/13/2024")])
        assert any(e["field"] == "posting_date" for e in exc_info.value.errors)

    def test_multiple_errors_collected(self):
        """All errors in a batch are returned at once, not one-by-one."""
        rows = [
            {"posting_date": "", "material_group": "", "quantity": "", "unit": "L"},
            {"posting_date": "bad", "material_group": "Diesel", "quantity": "abc", "unit": "L"},
        ]
        with pytest.raises(AdapterValidationError) as exc_info:
            SAPAdapter().validate(rows)
        assert len(exc_info.value.errors) >= 4


class TestSAPAdapterNormalize:

    def _run(self, csv_text: str) -> list[NormalizedActivityRecord]:
        raw = textwrap.dedent(csv_text).strip().encode("utf-8-sig")
        return SAPAdapter().run(raw)

    def test_fuel_activity_type(self):
        records = self._run("""
            posting_date;plant_code;material_group;quantity;unit;document_number
            2024-01-15;P1;Diesel;100;L;DOC001
        """)
        assert records[0].activity_type == "fuel"

    def test_electricity_activity_type(self):
        records = self._run("""
            posting_date;plant_code;material_group;quantity;unit
            2024-03-01;P2;Strom;500;kWh
        """)
        assert records[0].activity_type == "electricity"

    def test_procurement_fallback(self):
        records = self._run("""
            posting_date;plant_code;material_group;quantity;unit
            2024-02-10;P3;Office Supplies;20;kg
        """)
        assert records[0].activity_type == "procurement"

    def test_german_number_conversion(self):
        records = self._run("""
            posting_date;plant_code;material_group;quantity;unit
            15.01.2024;W001;Diesel;1.234,56;L
        """)
        assert records[0].original_quantity == Decimal("1234.56")
        assert records[0].quantity == Decimal("1234.560000")

    def test_gallon_to_litre_conversion(self):
        records = self._run("""
            posting_date;plant_code;material_group;quantity;unit
            2024-01-01;P1;Diesel;100;Gal
        """)
        expected = (Decimal("100") * Decimal("3.78541")).quantize(Decimal("0.000001"))
        assert records[0].quantity == expected
        assert records[0].unit == "L"

    def test_mwh_to_kwh_conversion(self):
        records = self._run("""
            posting_date;plant_code;material_group;quantity;unit
            2024-01-01;P1;Strom;2;MWh
        """)
        assert records[0].quantity == Decimal("2000.000000")
        assert records[0].unit == "kWh"

    def test_tonne_to_kg_conversion(self):
        records = self._run("""
            posting_date;plant_code;material_group;quantity;unit
            2024-01-01;P1;Rohstoff;3;T
        """)
        assert records[0].quantity == Decimal("3000.000000")
        assert records[0].unit == "kg"

    def test_source_reference_and_location(self):
        records = self._run("""
            posting_date;plant_code;material_group;quantity;unit;document_number
            2024-01-15;PLANT_DE_01;Diesel;50;L;DOC123
        """)
        assert records[0].source_reference == "DOC123"
        assert records[0].location == "PLANT_DE_01"

    def test_normalized_record_schema_fields(self):
        records = self._run("""
            posting_date;plant_code;material_group;quantity;unit
            2024-01-15;P1;Diesel;100;L
        """)
        r = records[0]
        assert r.source_type == "SAP"
        assert r.activity_date == date(2024, 1, 15)
        assert isinstance(r.quantity, Decimal)
        assert isinstance(r.metadata, dict)
        assert "plant_code" in r.metadata

    def test_to_dict_is_json_safe(self):
        records = SAPAdapter().run(
            "posting_date;plant_code;material_group;quantity;unit\n"
            "2024-01-15;P1;Diesel;100;L".encode()
        )
        d = records[0].to_dict()
        json.dumps(d)  # must not raise


# =============================================================================
# Utility Adapter Tests
# =============================================================================

class TestUtilityAdapterParse:

    def _csv(self, content: str) -> bytes:
        return textwrap.dedent(content).strip().encode("utf-8-sig")

    def test_parse_explicit_consumption(self):
        raw = self._csv("""
            period_start,period_end,commodity,consumption,unit,meter_id
            2024-01-01,2024-01-31,electricity,1500,kWh,MTR001
        """)
        rows = UtilityAdapter().parse(raw)
        assert len(rows) == 1
        assert rows[0]["consumption"] == "1500"
        assert rows[0]["commodity"] == "electricity"

    def test_parse_derives_consumption_from_reads(self):
        raw = self._csv("""
            period_start,period_end,commodity,opening_read,closing_read,unit
            2024-01-01,2024-01-31,gas,1000,1250,m3
        """)
        rows = UtilityAdapter().parse(raw)
        assert rows[0]["consumption"] == "250"
        assert rows[0].get("_consumption_derived") is True

    def test_parse_multiple_commodities(self):
        raw = self._csv("""
            period_start,period_end,commodity,consumption,unit
            2024-01-01,2024-01-31,electricity,800,kWh
            2024-01-01,2024-01-31,gas,120,m3
            2024-01-01,2024-01-31,water,45,m3
        """)
        rows = UtilityAdapter().parse(raw)
        assert len(rows) == 3


class TestUtilityAdapterValidate:

    def _row(self, **kwargs):
        base = {
            "period_start": "2024-01-01",
            "period_end": "2024-01-31",
            "commodity": "electricity",
            "consumption": "1500",
            "unit": "kWh",
        }
        base.update(kwargs)
        return base

    def test_valid_row_passes(self):
        UtilityAdapter().validate([self._row()])

    def test_missing_period_start_raises(self):
        with pytest.raises(AdapterValidationError) as exc:
            UtilityAdapter().validate([self._row(period_start="")])
        assert any(e["field"] == "period_start" for e in exc.value.errors)

    def test_missing_commodity_raises(self):
        with pytest.raises(AdapterValidationError) as exc:
            UtilityAdapter().validate([self._row(commodity="")])
        assert any(e["field"] == "commodity" for e in exc.value.errors)

    def test_no_consumption_no_reads_raises(self):
        row = {"period_start": "2024-01-01", "commodity": "electricity"}
        with pytest.raises(AdapterValidationError) as exc:
            UtilityAdapter().validate([row])
        assert any(e["field"] == "consumption" for e in exc.value.errors)

    def test_period_end_before_start_raises(self):
        with pytest.raises(AdapterValidationError) as exc:
            UtilityAdapter().validate([self._row(
                period_start="2024-02-01", period_end="2024-01-01"
            )])
        assert any(e["field"] == "period_end" for e in exc.value.errors)

    def test_negative_consumption_raises(self):
        with pytest.raises(AdapterValidationError) as exc:
            UtilityAdapter().validate([self._row(consumption="-100")])
        assert any(e["field"] == "consumption" for e in exc.value.errors)


class TestUtilityAdapterNormalize:

    def _run(self, csv_text: str) -> list[NormalizedActivityRecord]:
        raw = textwrap.dedent(csv_text).strip().encode("utf-8-sig")
        return UtilityAdapter().run(raw)

    def test_electricity_passthrough(self):
        records = self._run("""
            period_start,period_end,commodity,consumption,unit
            2024-01-01,2024-01-31,electricity,1500,kWh
        """)
        assert records[0].activity_type == "electricity"
        assert records[0].unit == "kWh"
        assert records[0].quantity == Decimal("1500.000000")

    def test_gas_m3_to_kwh_conversion(self):
        records = self._run("""
            period_start,period_end,commodity,consumption,unit
            2024-01-01,2024-01-31,gas,100,m3
        """)
        expected = (Decimal("100") * Decimal("10.55")).quantize(Decimal("0.000001"))
        assert records[0].quantity == expected
        assert records[0].unit == "kWh"

    def test_water_stays_m3(self):
        records = self._run("""
            period_start,period_end,commodity,consumption,unit
            2024-01-01,2024-01-31,water,55,m3
        """)
        assert records[0].activity_type == "water"
        assert records[0].unit == "m3"
        assert records[0].quantity == Decimal("55.000000")

    def test_heat_gj_to_kwh(self):
        records = self._run("""
            period_start,period_end,commodity,consumption,unit
            2024-01-01,2024-01-31,heat,10,GJ
        """)
        expected = (Decimal("10") * Decimal("277.778")).quantize(Decimal("0.000001"))
        assert records[0].quantity == expected
        assert records[0].unit == "kWh"

    def test_mwh_to_kwh(self):
        records = self._run("""
            period_start,period_end,commodity,consumption,unit
            2024-01-01,2024-01-31,electricity,2,MWh
        """)
        assert records[0].quantity == Decimal("2000.000000")

    def test_activity_date_is_period_start(self):
        records = self._run("""
            period_start,period_end,commodity,consumption,unit
            2024-03-01,2024-03-31,electricity,800,kWh
        """)
        assert records[0].activity_date == date(2024, 3, 1)

    def test_source_type(self):
        records = self._run("""
            period_start,commodity,consumption,unit
            2024-01-01,electricity,100,kWh
        """)
        assert records[0].source_type == "UTILITY"

    def test_metadata_contains_period(self):
        records = self._run("""
            period_start,period_end,commodity,consumption,unit
            2024-01-01,2024-01-31,electricity,100,kWh
        """)
        assert records[0].metadata["period_start"] == "2024-01-01"
        assert records[0].metadata["period_end"] == "2024-01-31"


# =============================================================================
# Travel Adapter Tests
# =============================================================================

class TestTravelAdapterParse:

    def _json(self, data) -> str:
        return json.dumps(data)

    def test_parse_bare_array(self):
        payload = [
            {"type": "flight", "date": "2024-01-10", "origin": "LHR", "destination": "JFK"}
        ]
        rows = TravelAdapter().parse(self._json(payload))
        assert len(rows) == 1
        assert rows[0]["type"] == "flight"

    def test_parse_wrapped_trips_key(self):
        payload = {"report_id": "RPT001", "trips": [
            {"type": "hotel", "date": "2024-01-10", "hotel_name": "Hilton", "nights": 2}
        ]}
        rows = TravelAdapter().parse(self._json(payload))
        assert len(rows) == 1
        assert rows[0]["type"] == "hotel"

    def test_parse_wrapped_expenses_key(self):
        payload = {"expenses": [
            {"expense_type": "flight", "departure_date": "2024-02-01",
             "departure_airport": "FRA", "arrival_airport": "DXB"}
        ]}
        rows = TravelAdapter().parse(self._json(payload))
        assert rows[0]["type"] == "flight"
        assert rows[0]["origin"] == "FRA"
        assert rows[0]["destination"] == "DXB"

    def test_parse_field_aliases_mapped(self):
        payload = [{"segment_type": "car", "travel_date": "2024-01-05",
                    "kilometers": 120, "employee": "John Doe", "trip_id": "T99"}]
        rows = TravelAdapter().parse(json.dumps(payload))
        assert rows[0]["type"] == "car"
        assert rows[0]["distance_km"] == 120
        assert rows[0]["traveller"] == "John Doe"
        assert rows[0]["booking_id"] == "T99"


class TestTravelAdapterValidate:

    def _flight(self, **kwargs):
        base = {"type": "flight", "date": "2024-01-10",
                "origin": "LHR", "destination": "JFK"}
        base.update(kwargs)
        return base

    def _hotel(self, **kwargs):
        base = {"type": "hotel", "date": "2024-01-10",
                "hotel_name": "Hilton", "nights": 2}
        base.update(kwargs)
        return base

    def _car(self, **kwargs):
        base = {"type": "car", "date": "2024-01-10", "distance_km": 80}
        base.update(kwargs)
        return base

    def test_valid_flight_passes(self):
        TravelAdapter().validate([self._flight()])

    def test_valid_hotel_passes(self):
        TravelAdapter().validate([self._hotel()])

    def test_valid_car_passes(self):
        TravelAdapter().validate([self._car()])

    def test_missing_type_raises(self):
        with pytest.raises(AdapterValidationError) as exc:
            TravelAdapter().validate([{"date": "2024-01-01"}])
        assert any(e["field"] == "type" for e in exc.value.errors)

    def test_unknown_type_raises(self):
        with pytest.raises(AdapterValidationError) as exc:
            TravelAdapter().validate([{"type": "spaceship", "date": "2024-01-01"}])
        assert any(e["field"] == "type" for e in exc.value.errors)

    def test_flight_missing_origin_raises(self):
        row = {"type": "flight", "date": "2024-01-10", "destination": "JFK"}
        with pytest.raises(AdapterValidationError) as exc:
            TravelAdapter().validate([row])
        assert any(e["field"] == "origin" for e in exc.value.errors)

    def test_flight_bad_iata_code_raises(self):
        row = {"type": "flight", "date": "2024-01-10", "origin": "LONDON", "destination": "JFK"}
        with pytest.raises(AdapterValidationError) as exc:
            TravelAdapter().validate([row])
        assert any(e["field"] == "origin" for e in exc.value.errors)

    def test_hotel_zero_nights_raises(self):
        row = {"type": "hotel", "date": "2024-01-10", "hotel_name": "X", "nights": 0}
        with pytest.raises(AdapterValidationError) as exc:
            TravelAdapter().validate([row])
        assert any(e["field"] == "nights" for e in exc.value.errors)

    def test_missing_date_raises(self):
        with pytest.raises(AdapterValidationError) as exc:
            TravelAdapter().validate([{"type": "flight", "origin": "LHR", "destination": "JFK"}])
        assert any(e["field"] == "date" for e in exc.value.errors)


class TestTravelAdapterNormalize:

    def _run(self, data) -> list[NormalizedActivityRecord]:
        return TravelAdapter().run(json.dumps(data))

    def test_flight_great_circle_lhr_jfk(self):
        records = self._run([
            {"type": "flight", "date": "2024-01-10", "origin": "LHR", "destination": "JFK"}
        ])
        r = records[0]
        assert r.activity_type == "flight"
        assert r.unit == "km"
        # LHR-JFK great circle ≈ 5539 km; verify it's in a reasonable range
        assert Decimal("5000") <= r.quantity <= Decimal("6000")
        assert r.metadata["distance_source"] == "great_circle_iata"

    def test_flight_explicit_distance_km(self):
        records = self._run([
            {"type": "flight", "date": "2024-01-10", "origin": "FRA",
             "destination": "DXB", "distance_km": 4800}
        ])
        assert records[0].quantity == Decimal("4800")
        assert records[0].metadata["distance_source"] == "provided_km"

    def test_flight_distance_miles_converted(self):
        records = self._run([
            {"type": "flight", "date": "2024-01-10", "origin": "JFK",
             "destination": "LAX", "distance_miles": 2475}
        ])
        expected = (Decimal("2475") * Decimal("1.60934")).quantize(Decimal("0.01"))
        assert records[0].quantity == expected
        assert records[0].metadata["distance_source"] == "provided_miles_converted"

    def test_flight_unknown_airports_returns_zero(self):
        records = self._run([
            {"type": "flight", "date": "2024-01-10", "origin": "XYZ", "destination": "ABC"}
        ])
        assert records[0].quantity == Decimal("0")
        assert records[0].metadata["distance_source"] == "unknown"

    def test_hotel_room_nights(self):
        records = self._run([
            {"type": "hotel", "date": "2024-02-01", "hotel_name": "Sheraton",
             "city": "Berlin", "country": "DE", "nights": 3, "booking_id": "HTL-99"}
        ])
        r = records[0]
        assert r.activity_type == "hotel"
        assert r.unit == "night"
        assert r.quantity == Decimal("3")
        assert r.source_reference == "HTL-99"
        assert "Sheraton" in r.metadata["hotel_name"]

    def test_ground_transport_km(self):
        records = self._run([
            {"type": "taxi", "date": "2024-03-15", "distance_km": 42.5,
             "city": "Paris", "booking_id": "CAB-01"}
        ])
        r = records[0]
        assert r.activity_type == "ground_transport"
        assert r.unit == "km"
        assert r.quantity == Decimal("42.50")

    def test_ground_transport_miles_to_km(self):
        records = self._run([
            {"type": "car", "date": "2024-03-10", "distance_miles": 30}
        ])
        expected = (Decimal("30") * Decimal("1.60934")).quantize(Decimal("0.01"))
        assert records[0].quantity == expected
        assert records[0].unit == "km"

    def test_train_classified_as_ground(self):
        records = self._run([
            {"type": "train", "date": "2024-01-20", "distance_km": 300,
             "origin": "PAR", "destination": "AMS"}
        ])
        assert records[0].activity_type == "ground_transport"

    def test_source_type_is_travel(self):
        records = self._run([
            {"type": "flight", "date": "2024-01-10", "origin": "LHR", "destination": "CDG"}
        ])
        assert records[0].source_type == "TRAVEL"

    def test_to_dict_json_serializable(self):
        records = self._run([
            {"type": "flight", "date": "2024-01-10", "origin": "LHR", "destination": "JFK"}
        ])
        d = records[0].to_dict()
        json.dumps(d)  # must not raise

    def test_mixed_segment_types_in_one_file(self):
        payload = [
            {"type": "flight", "date": "2024-03-01", "origin": "SIN", "destination": "SYD"},
            {"type": "hotel", "date": "2024-03-05", "hotel_name": "Marriott", "nights": 2},
            {"type": "taxi",  "date": "2024-03-07", "distance_km": 15},
        ]
        records = TravelAdapter().run(json.dumps(payload))
        assert len(records) == 3
        types = {r.activity_type for r in records}
        assert types == {"flight", "hotel", "ground_transport"}


# =============================================================================
# Integration – unified schema contract
# =============================================================================

class TestNormalizedActivityRecordContract:
    """
    Cross-adapter tests confirming that all adapters produce records
    conforming to the NormalizedActivityRecord schema contract.
    """

    def _sap_records(self):
        raw = "posting_date;plant_code;material_group;quantity;unit\n2024-01-15;P1;Diesel;100;L".encode()
        return SAPAdapter().run(raw)

    def _utility_records(self):
        raw = "period_start,commodity,consumption,unit\n2024-01-01,electricity,800,kWh".encode()
        return UtilityAdapter().run(raw)

    def _travel_records(self):
        payload = [{"type": "flight", "date": "2024-01-10", "origin": "LHR", "destination": "JFK"}]
        return TravelAdapter().run(json.dumps(payload))

    @pytest.mark.parametrize("adapter_fn", ["_sap_records", "_utility_records", "_travel_records"])
    def test_all_required_schema_fields_present(self, adapter_fn):
        records = getattr(self, adapter_fn)()
        for r in records:
            assert isinstance(r.source_type, str) and r.source_type
            assert isinstance(r.activity_type, str) and r.activity_type
            assert isinstance(r.activity_date, date)
            assert isinstance(r.quantity, Decimal)
            assert isinstance(r.unit, str) and r.unit
            assert isinstance(r.original_quantity, Decimal)
            assert isinstance(r.original_unit, str)
            assert isinstance(r.description, str) and r.description
            assert isinstance(r.metadata, dict)

    @pytest.mark.parametrize("adapter_fn", ["_sap_records", "_utility_records", "_travel_records"])
    def test_to_dict_always_json_serializable(self, adapter_fn):
        records = getattr(self, adapter_fn)()
        for r in records:
            json.dumps(r.to_dict())  # must never raise
