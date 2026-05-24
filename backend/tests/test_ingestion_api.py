"""
tests/test_ingestion_api.py
===========================
Integration tests for the three upload endpoints.

Uses Django's TestClient (no real HTTP) and an in-memory SQLite database.
No mocking of the adapter layer – the full pipeline runs end-to-end.

Test matrix
-----------
SAP     parse/normalize/db persistence, partial failure, empty file, wrong content-type
UTILITY parse/normalize/db persistence, derived consumption from reads
TRAVEL  parse/normalize/db persistence, mixed segment types
Common  tenant resolution, missing file, 422 on all-failed batch
"""

import io
import json
import textwrap
from decimal import Decimal

import pytest

from django.test import TestCase, Client
from django.urls import reverse

from core.models import (
    DataSource,
    NormalizedRecord,
    RawRecord,
    Tenant,
    UploadBatch,
    User,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

class IngestionTestBase(TestCase):
    """Shared setUp creating a tenant, a staff user, and a plain user."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Acme Corp", slug="acme-corp")
        cls.user = User.objects.create_user(
            username="analyst",
            password="testpass123",
            tenant=cls.tenant,
        )
        cls.admin = User.objects.create_user(
            username="admin",
            password="adminpass123",
            tenant=cls.tenant,
            is_staff=True,
        )

    def _client(self, user=None) -> Client:
        c = Client()
        u = user or self.user
        c.force_login(u)
        return c

    def _file(self, content: str | bytes, name: str = "test.csv") -> io.BytesIO:
        if isinstance(content, str):
            content = textwrap.dedent(content).strip().encode("utf-8")
        buf = io.BytesIO(content)
        buf.name = name
        return buf


# ===========================================================================
# SAP Upload Tests
# ===========================================================================

class TestSAPUploadView(IngestionTestBase):

    URL = "/api/upload/sap/"

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_successful_upload_returns_200(self):
        csv = """
            posting_date;plant_code;material_group;quantity;unit;document_number
            2024-01-15;P001;Diesel;100;L;DOC001
            2024-02-01;P002;Strom;500;kWh;DOC002
            2024-03-10;P003;Rohstoff;250;kg;DOC003
        """
        resp = self._client().post(
            self.URL,
            data={"file": self._file(csv), "source_name": "SAP Test"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["uploaded"], 3)
        self.assertEqual(data["normalized"], 3)
        self.assertEqual(data["failed"], 0)
        self.assertEqual(data["source_type"], "SAP")
        self.assertIn("batch_id", data)

    def test_creates_upload_batch(self):
        csv = "posting_date;plant_code;material_group;quantity;unit\n2024-01-01;P1;Diesel;50;L"
        before = UploadBatch.objects.count()
        self._client().post(self.URL, data={"file": self._file(csv)}, format="multipart")
        self.assertEqual(UploadBatch.objects.count(), before + 1)

    def test_creates_raw_records(self):
        csv = """
            posting_date;plant_code;material_group;quantity;unit
            2024-01-01;P1;Diesel;50;L
            2024-01-02;P2;Strom;200;kWh
        """
        before = RawRecord.objects.count()
        self._client().post(self.URL, data={"file": self._file(csv)}, format="multipart")
        self.assertEqual(RawRecord.objects.count(), before + 2)

    def test_creates_normalized_records(self):
        csv = """
            posting_date;plant_code;material_group;quantity;unit
            2024-01-01;P1;Diesel;50;L
            2024-01-02;P2;Strom;200;kWh
        """
        before = NormalizedRecord.objects.filter(tenant=self.tenant).count()
        self._client().post(self.URL, data={"file": self._file(csv)}, format="multipart")
        self.assertEqual(NormalizedRecord.objects.filter(tenant=self.tenant).count(), before + 2)

    def test_normalized_record_fields(self):
        csv = "posting_date;plant_code;material_group;quantity;unit;document_number\n2024-01-15;P001;Diesel;100;L;DOC001"
        self._client().post(self.URL, data={"file": self._file(csv), "source_name": "SAP Fields Test"}, format="multipart")
        rec = NormalizedRecord.objects.filter(
            tenant=self.tenant,
            source_type=DataSource.SourceType.SAP,
            activity_type="fuel",
        ).order_by("-pk").first()
        self.assertIsNotNone(rec)
        self.assertEqual(rec.normalized_unit, "L")
        self.assertEqual(rec.normalized_value, Decimal("100.000000"))
        self.assertEqual(rec.scope, NormalizedRecord.Scope.SCOPE1)
        self.assertEqual(rec.approval_status, NormalizedRecord.ApprovalStatus.PENDING)
        self.assertEqual(rec.source_reference, "DOC001")
        self.assertEqual(rec.activity_date.isoformat(), "2024-01-15")

    def test_german_number_format_handled(self):
        csv = "posting_date;plant_code;material_group;quantity;unit\n15.01.2024;W001;Diesel;1.234,56;L"
        resp = self._client().post(self.URL, data={"file": self._file(csv)}, format="multipart")
        self.assertEqual(resp.status_code, 200)
        rec = NormalizedRecord.objects.filter(
            tenant=self.tenant, activity_type="fuel"
        ).order_by("-pk").first()
        self.assertEqual(rec.original_value, Decimal("1234.56"))

    def test_batch_status_is_completed_on_success(self):
        csv = "posting_date;plant_code;material_group;quantity;unit\n2024-01-01;P1;Diesel;50;L"
        resp = self._client().post(self.URL, data={"file": self._file(csv)}, format="multipart")
        batch = UploadBatch.objects.get(pk=resp.json()["batch_id"])
        self.assertEqual(batch.status, UploadBatch.BatchStatus.COMPLETED)

    def test_custom_delimiter(self):
        csv = "posting_date,plant_code,material_group,quantity,unit\n2024-01-01,P1,Diesel,50,L"
        resp = self._client().post(
            self.URL,
            data={"file": self._file(csv), "delimiter": ","},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["normalized"], 1)

    # ------------------------------------------------------------------
    # Partial failure
    # ------------------------------------------------------------------

    def test_partial_failure_returns_correct_counts(self):
        """One row is invalid (negative qty); the rest should normalize."""
        csv = """
            posting_date;plant_code;material_group;quantity;unit
            2024-01-01;P1;Diesel;100;L
            2024-01-02;P2;Strom;NOT_A_NUMBER;kWh
            2024-01-03;P3;Rohstoff;75;kg
        """
        resp = self._client().post(self.URL, data={"file": self._file(csv)}, format="multipart")
        data = resp.json()
        self.assertEqual(data["uploaded"], 3)
        # 1 invalid row → 2 normalized, 1 failed
        self.assertEqual(data["failed"], 1)
        self.assertIn("validation_errors", data)

    def test_failed_raw_records_store_errors(self):
        csv = """
            posting_date;plant_code;material_group;quantity;unit
            2024-01-01;P1;Diesel;100;L
            BAD_DATE;P2;Strom;500;kWh
        """
        resp = self._client().post(self.URL, data={"file": self._file(csv)}, format="multipart")
        batch_id = resp.json()["batch_id"]
        failed_rr = RawRecord.objects.filter(
            batch_id=batch_id,
            parsing_status=RawRecord.ParsingStatus.FAILED,
        )
        self.assertTrue(failed_rr.exists())
        # Errors must be stored on the raw record
        self.assertIsNotNone(failed_rr.first().parsing_errors)

    # ------------------------------------------------------------------
    # Error cases
    # ------------------------------------------------------------------

    def test_missing_file_returns_400(self):
        resp = self._client().post(self.URL, data={}, format="multipart")
        self.assertEqual(resp.status_code, 400)

    def test_empty_file_returns_400(self):
        buf = io.BytesIO(b"")
        buf.name = "empty.csv"
        resp = self._client().post(self.URL, data={"file": buf}, format="multipart")
        self.assertEqual(resp.status_code, 400)

    def test_unauthenticated_returns_403(self):
        csv = "posting_date;plant_code;material_group;quantity;unit\n2024-01-01;P1;Diesel;50;L"
        resp = Client().post(self.URL, data={"file": self._file(csv)}, format="multipart")
        self.assertIn(resp.status_code, [401, 403])

    def test_response_schema_keys_present(self):
        csv = "posting_date;plant_code;material_group;quantity;unit\n2024-01-01;P1;Diesel;50;L"
        resp = self._client().post(self.URL, data={"file": self._file(csv)}, format="multipart")
        data = resp.json()
        for key in ("batch_id", "source_type", "uploaded", "normalized", "failed", "batch_status"):
            self.assertIn(key, data, f"Key '{key}' missing from response.")


# ===========================================================================
# Utility Upload Tests
# ===========================================================================

class TestUtilityUploadView(IngestionTestBase):

    URL = "/api/upload/utility/"

    def test_successful_electricity_upload(self):
        csv = """
            period_start,period_end,commodity,consumption,unit,meter_id,account_ref
            2024-01-01,2024-01-31,electricity,1500,kWh,MTR001,INV-2024-001
            2024-02-01,2024-02-29,electricity,1200,kWh,MTR001,INV-2024-002
        """
        resp = self._client().post(self.URL, data={"file": self._file(csv)}, format="multipart")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["uploaded"], 2)
        self.assertEqual(data["normalized"], 2)
        self.assertEqual(data["failed"], 0)

    def test_gas_consumption_converted_to_kwh(self):
        csv = "period_start,period_end,commodity,consumption,unit\n2024-01-01,2024-01-31,gas,100,m3"
        self._client().post(self.URL, data={"file": self._file(csv)}, format="multipart")
        rec = NormalizedRecord.objects.filter(
            tenant=self.tenant, activity_type="gas"
        ).order_by("-pk").first()
        self.assertEqual(rec.normalized_unit, "kWh")
        expected = Decimal("100") * Decimal("10.55")
        self.assertAlmostEqual(float(rec.normalized_value), float(expected), places=4)

    def test_meter_read_derived_consumption(self):
        csv = "period_start,period_end,commodity,opening_read,closing_read,unit\n2024-01-01,2024-01-31,electricity,10000,11500,kWh"
        resp = self._client().post(self.URL, data={"file": self._file(csv)}, format="multipart")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["normalized"], 1)
        rec = NormalizedRecord.objects.filter(
            tenant=self.tenant, activity_type="electricity"
        ).order_by("-pk").first()
        self.assertEqual(rec.normalized_value, Decimal("1500.000000"))

    def test_mixed_commodities_single_file(self):
        csv = """
            period_start,period_end,commodity,consumption,unit
            2024-01-01,2024-01-31,electricity,800,kWh
            2024-01-01,2024-01-31,gas,120,m3
            2024-01-01,2024-01-31,water,45,m3
        """
        resp = self._client().post(self.URL, data={"file": self._file(csv)}, format="multipart")
        self.assertEqual(resp.json()["normalized"], 3)
        activity_types = set(
            NormalizedRecord.objects.filter(tenant=self.tenant)
            .order_by("-pk")[:3]
            .values_list("activity_type", flat=True)
        )
        self.assertIn("electricity", activity_types)
        self.assertIn("gas", activity_types)
        self.assertIn("water", activity_types)

    def test_water_scope_is_scope3(self):
        csv = "period_start,period_end,commodity,consumption,unit\n2024-01-01,2024-01-31,water,50,m3"
        self._client().post(self.URL, data={"file": self._file(csv)}, format="multipart")
        rec = NormalizedRecord.objects.filter(
            tenant=self.tenant, activity_type="water"
        ).order_by("-pk").first()
        self.assertEqual(rec.scope, NormalizedRecord.Scope.SCOPE3)

    def test_electricity_scope_is_scope2(self):
        csv = "period_start,period_end,commodity,consumption,unit\n2024-01-01,2024-01-31,electricity,100,kWh"
        self._client().post(self.URL, data={"file": self._file(csv)}, format="multipart")
        rec = NormalizedRecord.objects.filter(
            tenant=self.tenant, activity_type="electricity"
        ).order_by("-pk").first()
        self.assertEqual(rec.scope, NormalizedRecord.Scope.SCOPE2)

    def test_source_type_is_utility(self):
        csv = "period_start,period_end,commodity,consumption,unit\n2024-01-01,2024-01-31,electricity,100,kWh"
        self._client().post(self.URL, data={"file": self._file(csv)}, format="multipart")
        rec = NormalizedRecord.objects.filter(
            tenant=self.tenant, activity_type="electricity"
        ).order_by("-pk").first()
        self.assertEqual(rec.source_type, DataSource.SourceType.UTILITY)

    def test_missing_file_returns_400(self):
        resp = self._client().post(self.URL, data={}, format="multipart")
        self.assertEqual(resp.status_code, 400)


# ===========================================================================
# Travel Upload Tests
# ===========================================================================

class TestTravelUploadView(IngestionTestBase):

    URL = "/api/upload/travel/"

    def _json_file(self, data, name="travel.json") -> io.BytesIO:
        buf = io.BytesIO(json.dumps(data).encode("utf-8"))
        buf.name = name
        return buf

    def test_successful_flight_upload(self):
        payload = [
            {"type": "flight", "date": "2024-03-01", "origin": "LHR",
             "destination": "JFK", "cabin_class": "economy", "booking_id": "BK001"},
            {"type": "flight", "date": "2024-03-15", "origin": "SIN",
             "destination": "SYD", "booking_id": "BK002"},
        ]
        resp = self._client().post(
            self.URL,
            data={"file": self._json_file(payload), "source_name": "Concur Q1"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["uploaded"], 2)
        self.assertEqual(data["normalized"], 2)
        self.assertEqual(data["failed"], 0)

    def test_flight_distance_computed_from_iata(self):
        payload = [{"type": "flight", "date": "2024-01-10", "origin": "LHR", "destination": "JFK"}]
        self._client().post(self.URL, data={"file": self._json_file(payload)}, format="multipart")
        rec = NormalizedRecord.objects.filter(
            tenant=self.tenant, activity_type="flight"
        ).order_by("-pk").first()
        self.assertEqual(rec.normalized_unit, "km")
        self.assertGreater(rec.normalized_value, Decimal("5000"))
        self.assertLess(rec.normalized_value, Decimal("6000"))

    def test_hotel_stays_normalized_to_nights(self):
        payload = [
            {"type": "hotel", "date": "2024-04-01", "hotel_name": "Marriott",
             "city": "Paris", "country": "FR", "nights": 3, "booking_id": "HTL-42"}
        ]
        resp = self._client().post(self.URL, data={"file": self._json_file(payload)}, format="multipart")
        self.assertEqual(resp.status_code, 200)
        rec = NormalizedRecord.objects.filter(
            tenant=self.tenant, activity_type="hotel"
        ).order_by("-pk").first()
        self.assertEqual(rec.normalized_unit, "night")
        self.assertEqual(rec.normalized_value, Decimal("3.000000"))

    def test_ground_transport_normalized_to_km(self):
        payload = [{"type": "taxi", "date": "2024-04-05", "distance_km": 42.5, "city": "Berlin"}]
        self._client().post(self.URL, data={"file": self._json_file(payload)}, format="multipart")
        rec = NormalizedRecord.objects.filter(
            tenant=self.tenant, activity_type="ground_transport"
        ).order_by("-pk").first()
        self.assertEqual(rec.normalized_unit, "km")
        self.assertEqual(rec.normalized_value, Decimal("42.50"))

    def test_mixed_segments_in_one_file(self):
        payload = [
            {"type": "flight", "date": "2024-05-01", "origin": "FRA", "destination": "AMS"},
            {"type": "hotel", "date": "2024-05-02", "hotel_name": "Hilton", "nights": 2},
            {"type": "car",   "date": "2024-05-04", "distance_km": 80},
        ]
        resp = self._client().post(self.URL, data={"file": self._json_file(payload)}, format="multipart")
        self.assertEqual(resp.json()["normalized"], 3)

    def test_concur_wrapper_object_parsed(self):
        payload = {
            "report_id": "RPT-2024-Q2",
            "expenses": [
                {"type": "flight", "date": "2024-06-01", "origin": "CDG", "destination": "SIN"},
            ],
        }
        resp = self._client().post(self.URL, data={"file": self._json_file(payload)}, format="multipart")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["uploaded"], 1)

    def test_flight_scope_is_scope3(self):
        payload = [{"type": "flight", "date": "2024-01-10", "origin": "LHR", "destination": "JFK"}]
        self._client().post(self.URL, data={"file": self._json_file(payload)}, format="multipart")
        rec = NormalizedRecord.objects.filter(
            tenant=self.tenant, activity_type="flight"
        ).order_by("-pk").first()
        self.assertEqual(rec.scope, NormalizedRecord.Scope.SCOPE3)

    def test_unknown_segment_type_returns_validation_error(self):
        payload = [{"type": "submarine", "date": "2024-01-01"}]
        resp = self._client().post(self.URL, data={"file": self._json_file(payload)}, format="multipart")
        # 422 because all rows failed
        self.assertEqual(resp.status_code, 422)
        self.assertIn("validation_errors", resp.json())

    def test_missing_file_returns_400(self):
        resp = self._client().post(self.URL, data={}, format="multipart")
        self.assertEqual(resp.status_code, 400)

    def test_source_type_is_travel(self):
        payload = [{"type": "flight", "date": "2024-01-10", "origin": "LHR", "destination": "CDG"}]
        self._client().post(self.URL, data={"file": self._json_file(payload)}, format="multipart")
        rec = NormalizedRecord.objects.filter(
            tenant=self.tenant, activity_type="flight"
        ).order_by("-pk").first()
        self.assertEqual(rec.source_type, DataSource.SourceType.TRAVEL)


# ===========================================================================
# Tenant / Auth edge cases
# ===========================================================================

class TestIngestionTenantResolution(IngestionTestBase):

    def test_user_without_tenant_returns_400(self):
        """A user not assigned to any tenant cannot upload without tenant_id."""
        orphan = User.objects.create_user(username="orphan", password="pass123", tenant=None)
        c = Client()
        c.force_login(orphan)
        csv = "posting_date;plant_code;material_group;quantity;unit\n2024-01-01;P1;Diesel;50;L"
        buf = io.BytesIO(csv.encode())
        buf.name = "test.csv"
        resp = c.post("/api/upload/sap/", data={"file": buf}, format="multipart")
        self.assertEqual(resp.status_code, 400)

    def test_admin_can_specify_tenant_id(self):
        csv = "posting_date;plant_code;material_group;quantity;unit\n2024-01-01;P1;Diesel;50;L"
        buf = io.BytesIO(csv.encode())
        buf.name = "test.csv"
        c = Client()
        c.force_login(self.admin)
        resp = c.post(
            "/api/upload/sap/",
            data={"file": buf, "tenant_id": self.tenant.pk},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200)

    def test_non_admin_cannot_specify_tenant_id(self):
        csv = "posting_date;plant_code;material_group;quantity;unit\n2024-01-01;P1;Diesel;50;L"
        buf = io.BytesIO(csv.encode())
        buf.name = "test.csv"
        resp = self._client().post(
            "/api/upload/sap/",
            data={"file": buf, "tenant_id": self.tenant.pk},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 403)

    def test_invalid_tenant_id_returns_404(self):
        csv = "posting_date;plant_code;material_group;quantity;unit\n2024-01-01;P1;Diesel;50;L"
        buf = io.BytesIO(csv.encode())
        buf.name = "test.csv"
        c = Client()
        c.force_login(self.admin)
        resp = c.post(
            "/api/upload/sap/",
            data={"file": buf, "tenant_id": 99999},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 404)
