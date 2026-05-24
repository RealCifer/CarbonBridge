"""
ingest/serializers.py
=====================
DRF serializers for the upload ingestion endpoints.
"""

from rest_framework import serializers


# ---------------------------------------------------------------------------
# Request serializers
# ---------------------------------------------------------------------------

class SAPUploadSerializer(serializers.Serializer):
    """
    Validates a multipart SAP CSV file upload.
    Optional query/form params allow callers to override the CSV delimiter
    and explicitly name the data source.
    """
    file = serializers.FileField(help_text="SAP ERP CSV export file.")
    source_name = serializers.CharField(
        max_length=255,
        required=False,
        default="SAP ERP Import",
        help_text="Human-readable label for the DataSource record.",
    )
    delimiter = serializers.CharField(
        max_length=1,
        required=False,
        default=";",
        help_text="CSV column delimiter (default ';').",
    )
    tenant_id = serializers.IntegerField(
        required=False,
        help_text="Tenant PK to associate with this batch. Defaults to the authenticated user's tenant.",
    )


class UtilityUploadSerializer(serializers.Serializer):
    """
    Validates a multipart Utility portal CSV file upload.
    """
    file = serializers.FileField(help_text="Utility portal CSV export file.")
    source_name = serializers.CharField(
        max_length=255,
        required=False,
        default="Utility Portal Import",
    )
    delimiter = serializers.CharField(
        max_length=1,
        required=False,
        default=",",
    )
    tenant_id = serializers.IntegerField(required=False)


class TravelUploadSerializer(serializers.Serializer):
    """
    Validates a multipart Concur-style JSON file upload.
    """
    file = serializers.FileField(help_text="Concur-style JSON travel export file.")
    source_name = serializers.CharField(
        max_length=255,
        required=False,
        default="Concur Travel Import",
    )
    tenant_id = serializers.IntegerField(required=False)


# ---------------------------------------------------------------------------
# Response serializers (documentation / schema only – we build dicts manually)
# ---------------------------------------------------------------------------

class IngestionSummarySerializer(serializers.Serializer):
    """
    Represents the JSON body returned by every upload endpoint.
    Used for DRF schema / Swagger generation.
    """
    batch_id = serializers.IntegerField()
    source_type = serializers.CharField()
    uploaded = serializers.IntegerField(help_text="Total rows parsed from the file.")
    normalized = serializers.IntegerField(help_text="Rows successfully written as NormalizedRecords.")
    failed = serializers.IntegerField(help_text="Rows that could not be normalised.")
    batch_status = serializers.CharField()
    validation_errors = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text="Structured per-row error list when partial failures occur.",
    )
