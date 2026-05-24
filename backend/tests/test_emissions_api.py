"""
tests/test_emissions_api.py
"""
import django
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "carbonbridge.settings")

import pytest
from datetime import date
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse

from core.models import Tenant, User, DataSource, UploadBatch, RawRecord, NormalizedRecord
from emissions.models import EmissionFactor, EmissionRecord
from emissions.services import calculate_batch_emissions

class TestEmissionsAPI(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        cls.user = User.objects.create_user(username="testuser", password="testpass", tenant=cls.tenant)
        cls.source = DataSource.objects.create(tenant=cls.tenant, source_type=DataSource.SourceType.SAP, name="SAP")
        
        # Seed test emission factors
        EmissionFactor.objects.create(activity_type="fuel", unit="L", factor_kgco2e=Decimal("2.5"), region="GLOBAL", valid_from=date(2020, 1, 1))
        EmissionFactor.objects.create(activity_type="electricity", unit="kWh", factor_kgco2e=Decimal("0.5"), region="UK", valid_from=date(2020, 1, 1))
        
        cls.batch = UploadBatch.objects.create(source=cls.source, uploaded_by=cls.user, status=UploadBatch.BatchStatus.COMPLETED)
        
        # Create some parsed normalized records linked to the batch
        cls.raw = RawRecord.objects.create(batch=cls.batch, original_payload_json={}, parsing_status=RawRecord.ParsingStatus.PARSED)
        
        cls.nr1 = NormalizedRecord.objects.create(
            tenant=cls.tenant,
            source_type=DataSource.SourceType.SAP,
            activity_type="fuel",
            scope=NormalizedRecord.Scope.SCOPE1,
            original_unit="L",
            normalized_unit="L",
            original_value=Decimal("100"),
            normalized_value=Decimal("100"),
            activity_date=date(2023, 1, 1),
        )
        
        cls.nr2 = NormalizedRecord.objects.create(
            tenant=cls.tenant,
            source_type=DataSource.SourceType.SAP,
            activity_type="electricity",
            scope=NormalizedRecord.Scope.SCOPE2,
            original_unit="kWh",
            normalized_unit="kWh",
            original_value=Decimal("200"),
            normalized_value=Decimal("200"),
            activity_date=date(2023, 1, 1),
        )

    def test_calculation_service(self):
        summary = calculate_batch_emissions(self.batch.pk, preferred_region="UK")
        self.assertEqual(summary.calculated, 2)
        
        # 100 L * 2.5 kg/L = 250 kg = 0.25 t
        # 200 kWh * 0.5 kg/kWh = 100 kg = 0.10 t
        # Total = 0.35 tCO2e
        self.assertEqual(summary.total_tco2e, Decimal("0.350000000"))

    def test_reports_api(self):
        calculate_batch_emissions(self.batch.pk, preferred_region="UK")
        
        c = Client()
        c.force_login(self.user)
        resp = c.get("/api/reports/summary/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        
        self.assertEqual(data["grand_total_tco2e"], "0.350000")
        self.assertEqual(len(data["breakdown"]), 2)
