import logging
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.forms import model_to_dict
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from decimal import Decimal

logger = logging.getLogger(__name__)

# ==========================================
# 1. BASE ABSTRACT MODELS (MIXINS)
# ==========================================

class SoftDeleteQuerySet(models.QuerySet):
    """
    Custom QuerySet that overrides bulk delete operation to flag records
    as deleted instead of purging them from the database.
    """
    def delete(self):
        # Perform soft-delete by setting the flag and timestamp in bulk
        return super().update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        # Expose a way to physically remove records if absolutely necessary
        return super().delete()


class SoftDeleteManager(models.Manager):
    """
    Custom Manager that automatically filters out soft-deleted records.
    """
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=False)


class TimeStampedModel(models.Model):
    """
    An abstract base class that provides self-updating created_at and updated_at fields.
    Crucial for auditing records across ingestion phases.
    """
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """
    An abstract base class that provides soft-deletion support for sensitive ESG metrics.
    Ensures that accidental user deletions can be fully audited and recovered.
    """
    is_deleted = models.BooleanField(
        default=False, 
        db_index=True,
        help_text="Flag indicating whether this record has been soft-deleted."
    )
    deleted_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Timestamp of when this record was soft-deleted."
    )

    # Use our custom manager for default queries to automatically hide soft-deleted rows
    objects = SoftDeleteManager()
    
    # Expose a secondary manager to fetch all records (including soft-deleted ones)
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """
        Soft delete the individual instance.
        """
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])

    def restore(self):
        """
        Restore a soft-deleted instance.
        """
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at'])

    def hard_delete(self, using=None, keep_parents=False):
        """
        Physically delete the record from database if required.
        """
        super().delete(using=using, keep_parents=keep_parents)


# ==========================================
# 2. CORE ESG DATA MODELS
# ==========================================

class Tenant(TimeStampedModel, SoftDeleteModel):
    """
    Represents an independent corporate division, client, or enterprise tenant.
    Underpins the multi-tenant architecture to guarantee logical data isolation.
    """
    name = models.CharField(max_length=255, help_text="Enterprise or subsidiary legal name.")
    slug = models.SlugField(max_length=255, unique=True, help_text="Unique URL-friendly identifier.")

    def __str__(self):
        return self.name


class User(AbstractUser, TimeStampedModel, SoftDeleteModel):
    """
    Custom User class extending standard Django authentication.
    Linked directly to a Tenant to establish multi-tenant ownership boundaries.
    """
    tenant = models.ForeignKey(
        Tenant, 
        on_delete=models.CASCADE, 
        related_name='users', 
        null=True, 
        blank=True,
        help_text="The tenant this user belongs to. Leave empty for global system administrators."
    )

    class Meta:
        db_table = 'auth_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return f"{self.username} ({self.tenant.name if self.tenant else 'Global Admin'})"


class DataSource(TimeStampedModel, SoftDeleteModel):
    """
    Defines the origin pipeline from where ESG data was imported (e.g. travel registries, SAP API).
    """
    class SourceType(models.TextChoices):
        SAP = 'SAP', 'SAP ERP System'
        UTILITY = 'UTILITY', 'Utility Invoices'
        TRAVEL = 'TRAVEL', 'Corporate Travel Tracker'

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='data_sources')
    source_type = models.CharField(
        max_length=20, 
        choices=SourceType.choices,
        help_text="Category of upstream supplier system."
    )
    name = models.CharField(max_length=255, help_text="User-friendly name of the pipeline.")

    def __str__(self):
        return f"{self.name} [{self.source_type}] ({self.tenant.name})"


class UploadBatch(TimeStampedModel, SoftDeleteModel):
    """
    Tracks groups of files/records uploaded together in a single ingestion run.
    """
    class BatchStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending Processing'
        PARSING = 'PARSING', 'Currently Parsing'
        COMPLETED = 'COMPLETED', 'Successfully Completed'
        FAILED = 'FAILED', 'Ingestion Failed'

    source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name='batches')
    upload_timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='uploaded_batches')
    status = models.CharField(
        max_length=20, 
        choices=BatchStatus.choices, 
        default=BatchStatus.PENDING
    )

    class Meta:
        verbose_name = 'Upload Batch'
        verbose_name_plural = 'Upload Batches'

    def __str__(self):
        return f"Batch #{self.id} - {self.source.name} ({self.status})"


class RawRecord(TimeStampedModel, SoftDeleteModel):
    """
    Stores unmodified, raw JSON payloads straight from the source.
    Crucial for debugging calculations, re-running parsers, and data lineage audits.
    """
    class ParsingStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending Extraction'
        PARSED = 'PARSED', 'Successfully Parsed'
        FAILED = 'FAILED', 'Parsing Failed'

    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE, related_name='raw_records')
    original_payload_json = models.JSONField(help_text="Exact raw JSON imported from third-party vendor.")
    parsing_status = models.CharField(
        max_length=20, 
        choices=ParsingStatus.choices, 
        default=ParsingStatus.PENDING
    )
    parsing_errors = models.JSONField(
        null=True, 
        blank=True, 
        help_text="Diagnostic message log if extraction failed."
    )

    class Meta:
        verbose_name = 'Raw Record'
        verbose_name_plural = 'Raw Records'

    def __str__(self):
        return f"Raw Record #{self.id} (Batch #{self.batch_id}) - {self.parsing_status}"


class NormalizedRecord(TimeStampedModel, SoftDeleteModel):
    """
    The refined, normalized carbon and ESG record. 
    Ready for sustainability math (e.g. Scope emission calculations).
    """
    class ActivityType(models.TextChoices):
        FUEL = 'fuel', 'Fuel Consumption'
        PROCUREMENT = 'procurement', 'Procured Goods & Services'
        ELECTRICITY = 'electricity', 'Purchased Electricity'
        FLIGHT = 'flight', 'Business Flight'
        HOTEL = 'hotel', 'Hotel Stays'
        GROUND_TRANSPORT = 'ground_transport', 'Ground Transportation'

    class Scope(models.TextChoices):
        SCOPE1 = 'Scope1', 'Scope 1 (Direct Emissions)'
        SCOPE2 = 'Scope2', 'Scope 2 (Indirect Purchased Energy)'
        SCOPE3 = 'Scope3', 'Scope 3 (Other Indirect Value Chain)'

    class ApprovalStatus(models.TextChoices):
        PENDING = 'Pending', 'Pending Auditor Verification'
        APPROVED = 'Approved', 'Approved & Sealed'
        REJECTED = 'Rejected', 'Rejected'

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='normalized_records')
    source_type = models.CharField(max_length=20, choices=DataSource.SourceType.choices)
    
    activity_type = models.CharField(max_length=30, choices=ActivityType.choices)
    scope = models.CharField(max_length=10, choices=Scope.choices)
    
    # Mathematical tracking fields
    original_unit = models.CharField(max_length=50, help_text="E.g., Gallons, kWh, Passenger-Kilometers.")
    normalized_unit = models.CharField(max_length=50, help_text="Standardized unit (e.g., Liters, kWh, kgCO2e).")
    original_value = models.DecimalField(max_digits=18, decimal_places=6, help_text="Original raw numeric value.")
    normalized_value = models.DecimalField(max_digits=18, decimal_places=6, help_text="Value converted to normalized unit scale.")
    
    activity_date = models.DateField(db_index=True, help_text="Date when physical carbon emission activity occurred.")
    
    # Audit confidence & risk indicators
    confidence_score = models.DecimalField(
        max_digits=5, 
        decimal_places=4, 
        default=Decimal('1.0000'),
        help_text="AI/heuristic accuracy confidence (0.0000 to 1.0000)."
    )
    suspicious_flag = models.BooleanField(
        default=False, 
        help_text="Flagged automatically if metric deviates abnormally from baseline."
    )
    
    # Auditor controls
    approval_status = models.CharField(
        max_length=20, 
        choices=ApprovalStatus.choices, 
        default=ApprovalStatus.PENDING,
        db_index=True
    )
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='approved_records'
    )
    source_reference = models.CharField(
        max_length=255, 
        null=True, 
        blank=True, 
        help_text="Upstream reference index (e.g. invoice id, transaction slug)."
    )

    class Meta:
        verbose_name = 'Normalized Record'
        verbose_name_plural = 'Normalized Records'

    def __str__(self):
        return f"{self.activity_type} ({self.scope}) - {self.normalized_value} {self.normalized_unit} ({self.tenant.name})"


class AuditLog(models.Model):
    """
    Immutable ledger of state transformations on normalized ESG metrics.
    Ensures complete non-repudiation for carbon audit trails.
    NO SoftDeleteModel inheritance is used, as audit logs must be truly permanent.
    """
    record = models.ForeignKey(NormalizedRecord, on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=50, help_text="E.g., CREATE, UPDATE, DELETE, APPROVE, REJECT")
    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        help_text="Account that initiated the change."
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    old_values = models.JSONField(null=True, blank=True, help_text="State snapshot prior to transformation.")
    new_values = models.JSONField(null=True, blank=True, help_text="State snapshot following transformation.")

    class Meta:
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.action} on Record #{self.record_id} by {self.user.username if self.user else 'System'} at {self.timestamp}"


# ==========================================
# 3. AUTOMATIC AUDITING VIA SIGNALS
# ==========================================

@receiver(pre_save, sender=NormalizedRecord)
def capture_old_values(sender, instance, **kwargs):
    """
    Pre-save signal to temporarily cache the database state of the record.
    Enables us to log exact diffs inside the post-save signal.
    """
    if instance.pk:
        try:
            original = NormalizedRecord.all_objects.get(pk=instance.pk)
            # Cache the serialized dictionary on the active instance memory
            instance._old_values_dict = model_to_dict(original)
        except NormalizedRecord.DoesNotExist:
            instance._old_values_dict = None
    else:
        instance._old_values_dict = None


@receiver(post_save, sender=NormalizedRecord)
def auto_generate_audit_log(sender, instance, created, **kwargs):
    """
    Post-save signal that automatically logs creations and updates.
    Ensures that no developer code can bypass compliance audit trail compilation.
    """
    action = 'CREATE' if created else 'UPDATE'
    
    # If soft-deleted, adjust action label
    if not created and instance.is_deleted and getattr(instance, '_old_values_dict', {}).get('is_deleted') is False:
        action = 'SOFT_DELETE'
    elif not created and not instance.is_deleted and getattr(instance, '_old_values_dict', {}).get('is_deleted') is True:
        action = 'RESTORE'
    elif not created and instance.approval_status != getattr(instance, '_old_values_dict', {}).get('approval_status'):
        if instance.approval_status == NormalizedRecord.ApprovalStatus.APPROVED:
            action = 'APPROVE'
        elif instance.approval_status == NormalizedRecord.ApprovalStatus.REJECTED:
            action = 'REJECT'

    old_vals = getattr(instance, '_old_values_dict', None)
    new_vals = model_to_dict(instance)

    # Filter out timestamp structures from serialization to reduce clutter
    for d in [old_vals, new_vals]:
        if d:
            d.pop('created_at', None)
            d.pop('updated_at', None)
            # Decimals are not directly JSON-serializable in standard Django forms, convert to strings
            for k, v in d.items():
                if isinstance(v, Decimal):
                    d[k] = str(v)

    # We determine the user acting. If explicitly attached to the thread instance, utilize it.
    # Otherwise, fallback to System.
    acting_user = getattr(instance, '_acting_user', None)
    if not acting_user and instance.approved_by:
        acting_user = instance.approved_by

    AuditLog.objects.create(
        record=instance,
        action=action,
        user=acting_user,
        old_values=old_vals if not created else None,
        new_values=new_vals
    )
    logger.info(f"Audit log generated: {action} on NormalizedRecord #{instance.id}")
