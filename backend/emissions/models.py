"""
emissions/models.py
===================
EmissionFactor  – GHG conversion factors (kgCO₂e per normalised unit).
EmissionRecord  – Calculated GHG output for each NormalizedRecord.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils import timezone

from core.models import NormalizedRecord, SoftDeleteModel, TimeStampedModel


class EmissionFactor(TimeStampedModel):
    """
    A GHG emission factor: maps (activity_type, unit) → kgCO₂e per unit.

    Sources: DEFRA 2023 GHG Conversion Factors, GHG Protocol.
    Factors are versioned by valid_from / valid_to so historical batches
    always pick the factor that was current at the time of the activity.
    """

    class Region(models.TextChoices):
        GLOBAL = "GLOBAL", "Global (default)"
        UK = "UK", "United Kingdom"
        EU = "EU", "European Union"
        US = "US", "United States"
        AU = "AU", "Australia"
        DE = "DE", "Germany"

    activity_type = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Must match NormalizedRecord.activity_type values.",
    )
    unit = models.CharField(
        max_length=20,
        help_text="Normalised unit this factor applies to (L, kWh, km, night, kg, m3).",
    )
    factor_kgco2e = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        help_text="kgCO₂e emitted per 1 unit of activity.",
    )
    region = models.CharField(
        max_length=10,
        choices=Region.choices,
        default=Region.GLOBAL,
        db_index=True,
    )
    source = models.CharField(
        max_length=255,
        default="DEFRA 2023",
        help_text="Publication or standard this factor originates from.",
    )
    valid_from = models.DateField(
        default=timezone.now,
        help_text="First date this factor is applicable.",
    )
    valid_to = models.DateField(
        null=True,
        blank=True,
        help_text="Last date this factor is applicable (null = still current).",
    )
    notes = models.TextField(blank=True, help_text="Methodology notes or sub-category details.")

    class Meta:
        verbose_name = "Emission Factor"
        verbose_name_plural = "Emission Factors"
        ordering = ["activity_type", "region", "-valid_from"]
        indexes = [
            models.Index(fields=["activity_type", "unit", "region", "valid_from"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.activity_type} [{self.unit}] = {self.factor_kgco2e} kgCO₂e "
            f"({self.region}, {self.source})"
        )


class EmissionRecord(TimeStampedModel, SoftDeleteModel):
    """
    The calculated GHG output for a single NormalizedRecord.

    Links back to both the source NormalizedRecord and the EmissionFactor
    snapshot used, ensuring full data lineage for external auditors.
    """

    class CalculationStatus(models.TextChoices):
        PENDING = "PENDING", "Pending Calculation"
        CALCULATED = "CALCULATED", "Successfully Calculated"
        FACTOR_MISSING = "FACTOR_MISSING", "No Matching Factor Found"
        ERROR = "ERROR", "Calculation Error"

    normalized_record = models.OneToOneField(
        NormalizedRecord,
        on_delete=models.CASCADE,
        related_name="emission_record",
        help_text="The source normalized activity this calculation was derived from.",
    )
    emission_factor = models.ForeignKey(
        EmissionFactor,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="emission_records",
        help_text="Factor used at calculation time (null if no factor found).",
    )

    # Snapshot fields – preserved even if the factor row is later updated
    factor_snapshot_kgco2e = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="The exact factor value used at calculation time.",
    )
    activity_quantity = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        help_text="NormalizedRecord.normalized_value at calculation time.",
    )
    activity_unit = models.CharField(
        max_length=20,
        help_text="NormalizedRecord.normalized_unit at calculation time.",
    )

    # Results
    emission_kgco2e = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=Decimal("0"),
        help_text="Total GHG output in kilograms of CO₂ equivalent.",
    )
    emission_tco2e = models.DecimalField(
        max_digits=18,
        decimal_places=9,
        default=Decimal("0"),
        help_text="Total GHG output in metric tonnes of CO₂ equivalent (= kgCO₂e / 1000).",
    )

    # Metadata
    status = models.CharField(
        max_length=20,
        choices=CalculationStatus.choices,
        default=CalculationStatus.PENDING,
        db_index=True,
    )
    calculated_at = models.DateTimeField(null=True, blank=True)
    calculation_notes = models.TextField(
        blank=True,
        help_text="Any warnings, fallback decisions, or edge-case notes.",
    )

    class Meta:
        verbose_name = "Emission Record"
        verbose_name_plural = "Emission Records"
        ordering = ["-calculated_at"]

    def __str__(self) -> str:
        return (
            f"EmissionRecord #{self.pk} → "
            f"{self.emission_tco2e} tCO₂e [{self.status}]"
        )
