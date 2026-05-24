from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.utils.html import format_html
from django.urls import reverse
from .models import (
    Tenant,
    User,
    DataSource,
    UploadBatch,
    RawRecord,
    NormalizedRecord,
    AuditLog
)

# ==========================================
# CUSTOM GLOBAL ADMIN ACTIONS
# ==========================================

@admin.action(description="Soft delete selected records")
def soft_delete_action(modeladmin, request, queryset):
    """
    Admin action to soft delete records. Override standard Django delete.
    """
    for obj in queryset:
        obj.delete()
    modeladmin.message_user(request, f"Successfully soft-deleted {queryset.count()} records.")


@admin.action(description="Restore selected soft-deleted records")
def restore_action(modeladmin, request, queryset):
    """
    Admin action to restore soft-deleted records.
    """
    # Query using all_objects to access soft-deleted records
    queryset_to_restore = queryset.model.all_objects.filter(pk__in=queryset.values_list('pk', flat=True))
    count = 0
    for obj in queryset_to_restore:
        if obj.is_deleted:
            obj.restore()
            count += 1
    modeladmin.message_user(request, f"Successfully restored {count} soft-deleted records.")


# ==========================================
# SOFT DELETE FILTER
# ==========================================

class SoftDeleteFilter(admin.SimpleListFilter):
    """
    Filter to display soft-deleted items in the Django admin interface.
    """
    title = 'Deletion Status'
    parameter_name = 'deletion_state'

    def lookups(self, request, model_admin):
        return (
            ('active', 'Active (Default)'),
            ('deleted', 'Deleted / Archived'),
            ('all', 'All Records'),
        )

    def queryset(self, request, queryset):
        # We must use model_admin.model.all_objects if we want to retrieve soft-deleted rows
        if self.value() == 'deleted':
            return model_admin.model.all_objects.filter(is_deleted=True)
        elif self.value() == 'all':
            return model_admin.model.all_objects.all()
        # Default is active records
        return queryset.filter(is_deleted=False)


# ==========================================
# MODEL ADMIN REGISTRATIONS
# ==========================================

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at', 'is_deleted')
    search_fields = ('name', 'slug')
    list_filter = (SoftDeleteFilter, 'created_at')
    prepopulated_fields = {'slug': ('name',)}
    actions = [soft_delete_action, restore_action]


@admin.register(User)
class UserAdmin(DefaultUserAdmin):
    """
    Extends standard Django user admin to support multi-tenant assignments.
    """
    list_display = ('username', 'email', 'tenant', 'is_staff', 'is_active', 'is_deleted')
    list_filter = (SoftDeleteFilter, 'is_staff', 'is_superuser', 'tenant')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    actions = [soft_delete_action, restore_action]

    # Add the tenant field to standard fieldsets
    fieldsets = DefaultUserAdmin.fieldsets + (
        ('Tenant Association', {'fields': ('tenant', 'is_deleted', 'deleted_at')}),
    )


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'source_type', 'tenant', 'created_at', 'is_deleted')
    list_filter = (SoftDeleteFilter, 'source_type', 'tenant')
    search_fields = ('name', 'tenant__name')
    actions = [soft_delete_action, restore_action]


@admin.register(UploadBatch)
class UploadBatchAdmin(admin.ModelAdmin):
    list_display = ('id', 'source', 'upload_timestamp', 'uploaded_by', 'status_badge', 'is_deleted')
    list_filter = (SoftDeleteFilter, 'status', 'source__source_type', 'source__tenant')
    search_fields = ('id', 'source__name', 'uploaded_by__username')
    readonly_fields = ('upload_timestamp',)
    actions = [soft_delete_action, restore_action]

    def status_badge(self, obj):
        colors = {
            UploadBatch.BatchStatus.PENDING: '#f59e0b',
            UploadBatch.BatchStatus.PARSING: '#3b82f6',
            UploadBatch.BatchStatus.COMPLETED: '#10b981',
            UploadBatch.BatchStatus.FAILED: '#ef4444',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 0.8rem;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(RawRecord)
class RawRecordAdmin(admin.ModelAdmin):
    list_display = ('id', 'batch_link', 'parsing_status', 'created_at', 'is_deleted')
    list_filter = (SoftDeleteFilter, 'parsing_status', 'batch__source__tenant')
    search_fields = ('id', 'batch__id', 'original_payload_json')
    actions = [soft_delete_action, restore_action]

    def batch_link(self, obj):
        url = reverse("admin:core_uploadbatch_change", args=[obj.batch.id])
        return format_html('<a href="{}">Batch #{}</a>', url, obj.batch.id)
    batch_link.short_description = 'Batch'


@admin.register(NormalizedRecord)
class NormalizedRecordAdmin(admin.ModelAdmin):
    list_display = (
        'id', 
        'tenant', 
        'activity_type', 
        'scope', 
        'value_display', 
        'activity_date', 
        'suspicious_indicator',
        'approval_badge',
        'is_deleted'
    )
    list_filter = (
        SoftDeleteFilter,
        'approval_status',
        'scope',
        'activity_type',
        'suspicious_flag',
        'tenant'
    )
    search_fields = ('source_reference', 'tenant__name', 'original_unit', 'normalized_unit')
    readonly_fields = ('approved_by',)
    actions = [soft_delete_action, restore_action, 'approve_records', 'reject_records']

    def value_display(self, obj):
        return f"{obj.normalized_value} {obj.normalized_unit}"
    value_display.short_description = 'Normalized Value'

    def suspicious_indicator(self, obj):
        if obj.suspicious_flag:
            return format_html('<span style="color: #ef4444; font-weight: bold;">⚠️ Flagged</span>')
        return "Normal"
    suspicious_indicator.short_description = 'Risk Audit'

    def approval_badge(self, obj):
        colors = {
            NormalizedRecord.ApprovalStatus.PENDING: '#f59e0b',
            NormalizedRecord.ApprovalStatus.APPROVED: '#10b981',
            NormalizedRecord.ApprovalStatus.REJECTED: '#ef4444',
        }
        color = colors.get(obj.approval_status, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 0.8rem;">{}</span>',
            color,
            obj.get_approval_status_display()
        )
    approval_badge.short_description = 'Approval Status'

    # Approval and rejection core workflow actions
    @admin.action(description="Approve selected ESG metrics")
    def approve_records(self, request, queryset):
        updated = 0
        for obj in queryset:
            if obj.approval_status != NormalizedRecord.ApprovalStatus.APPROVED:
                obj.approval_status = NormalizedRecord.ApprovalStatus.APPROVED
                obj.approved_by = request.user
                # Set acting user inside the model context for signals to catch it
                obj._acting_user = request.user
                obj.save()
                updated += 1
        self.message_user(request, f"Successfully approved {updated} ESG records.")

    @admin.action(description="Reject selected ESG metrics")
    def reject_records(self, request, queryset):
        updated = 0
        for obj in queryset:
            if obj.approval_status != NormalizedRecord.ApprovalStatus.REJECTED:
                obj.approval_status = NormalizedRecord.ApprovalStatus.REJECTED
                obj.approved_by = None
                obj._acting_user = request.user
                obj.save()
                updated += 1
        self.message_user(request, f"Successfully rejected {updated} ESG records.")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Administrative log panel. Fully read-only to guarantee absolute audit non-repudiation.
    """
    list_display = ('timestamp', 'record_link', 'action', 'user', 'change_summary')
    list_filter = ('action', 'user', 'timestamp')
    search_fields = ('record__id', 'action', 'old_values', 'new_values')
    date_hierarchy = 'timestamp'
    
    # Disable all modification paths
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def record_link(self, obj):
        # Even if record is soft-deleted, we link to all_objects
        url = reverse("admin:core_normalizedrecord_change", args=[obj.record.id])
        return format_html('<a href="{}">Record #{}</a>', url, obj.record.id)
    record_link.short_description = 'Normalized Record'

    def change_summary(self, obj):
        if obj.action == 'CREATE':
            return f"Initial metric created: {obj.new_values.get('normalized_value', '')} {obj.new_values.get('normalized_unit', '')}"
        elif obj.action == 'UPDATE':
            diffs = []
            old = obj.old_values or {}
            new = obj.new_values or {}
            for k in ['normalized_value', 'approval_status', 'suspicious_flag']:
                if old.get(k) != new.get(k):
                    diffs.append(f"{k}: {old.get(k)} ➜ {new.get(k)}")
            return ", ".join(diffs) if diffs else "No core metric values altered"
        elif obj.action == 'SOFT_DELETE':
            return "Metric soft-deleted / archived"
        elif obj.action == 'RESTORE':
            return "Metric restored / unarchived"
        return f"{obj.action} execution"
    change_summary.short_description = 'Change Summary'
