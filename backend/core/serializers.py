from rest_framework import serializers
from core.models import NormalizedRecord

class NormalizedRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = NormalizedRecord
        fields = [
            'id', 'source_type', 'activity_type', 'scope', 
            'original_unit', 'normalized_unit', 'original_value', 
            'normalized_value', 'activity_date', 'confidence_score', 
            'suspicious_flag', 'approval_status', 'approved_by', 
            'source_reference', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'approved_by']
