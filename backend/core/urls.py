from django.urls import path
from .views import health_check, pending_records, suspicious_records, approve_record, reject_record, approved_records

urlpatterns = [
    path('health/', health_check, name='health-check'),
    path('review/pending/', pending_records, name='review-pending'),
    path('review/suspicious/', suspicious_records, name='review-suspicious'),
    path('review/approved/', approved_records, name='review-approved'),
    path('review/approve/', approve_record, name='review-approve'),
    path('review/reject/', reject_record, name='review-reject'),
]
