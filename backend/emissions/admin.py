"""
emissions/admin.py – Django Admin registration for EmissionFactor and EmissionRecord.
"""
from django.contrib import admin
from .models import EmissionFactor, EmissionRecord


@admin.register(EmissionFactor)
class EmissionFactorAdmin(admin.ModelAdmin):
    list_display = ("activity_type", "unit", "factor_kgco2e", "region", "source", "valid_from", "valid_to")
    list_filter = ("activity_type", "region", "source")
    search_fields = ("activity_type", "unit", "notes")
    ordering = ("activity_type", "region", "-valid_from")


@admin.register(EmissionRecord)
class EmissionRecordAdmin(admin.ModelAdmin):
    list_display = (
        "pk", "normalized_record", "status",
        "emission_kgco2e", "emission_tco2e", "calculated_at",
    )
    list_filter = ("status",)
    search_fields = ("normalized_record__activity_type", "calculation_notes")
    readonly_fields = (
        "normalized_record", "emission_factor", "factor_snapshot_kgco2e",
        "activity_quantity", "activity_unit",
        "emission_kgco2e", "emission_tco2e", "calculated_at",
    )
