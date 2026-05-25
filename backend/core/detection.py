import logging
from decimal import Decimal
from django.db.models import Avg
from django.utils import timezone
from core.models import NormalizedRecord

logger = logging.getLogger(__name__)

class SuspiciousRecordDetector:
    """
    Analyzes NormalizedRecords for suspicious activity and anomalies.
    Flags records and calculates a confidence score (0.0000 to 1.0000).
    """

    def __init__(self, tenant):
        self.tenant = tenant
        self._averages_cache = {}

    def _get_historical_average(self, activity_type: str, unit: str) -> Decimal:
        """
        Retrieves the historical average for a given activity type and unit.
        Uses a simple in-memory cache to prevent N+1 query issues during batch processing.
        """
        cache_key = f"{activity_type}_{unit}"
        if cache_key not in self._averages_cache:
            avg_value = NormalizedRecord.objects.filter(
                tenant=self.tenant,
                activity_type=activity_type,
                normalized_unit=unit
            ).aggregate(Avg('normalized_value'))['normalized_value__avg']
            
            self._averages_cache[cache_key] = avg_value if avg_value is not None else Decimal('0')
            
        return self._averages_cache[cache_key]

    def analyze(self, record: NormalizedRecord) -> None:
        """
        Analyzes a single record.
        Updates `suspicious_flag` and `confidence_score` in place.
        """
        score = 100
        suspicious = False

        # 1. Negative values
        if record.normalized_value < 0:
            score -= 50
            suspicious = True

        # 2. Future dates
        if record.activity_date and record.activity_date > timezone.now().date():
            score -= 50
            suspicious = True

        # 3. Missing units
        if not record.normalized_unit or not record.original_unit:
            score -= 20
            suspicious = True

        # 4. Missing source references
        if not record.source_reference:
            score -= 10

        # 5. Historical averages (Electricity > 10x, Fuel spikes)
        if record.activity_type in ('electricity', 'fuel') and record.normalized_value > 0:
            avg_value = self._get_historical_average(record.activity_type, record.normalized_unit)
            
            if avg_value > 0:
                ratio = record.normalized_value / avg_value
                
                # Electricity > 10x historical average
                if record.activity_type == 'electricity' and ratio > 10:
                    score -= 40
                    suspicious = True
                
                # Fuel usage spikes (e.g., > 5x historical average)
                elif record.activity_type == 'fuel' and ratio > 5:
                    score -= 40
                    suspicious = True

        # Ensure score is between 0 and 100
        score = max(0, min(100, score))
        
        # Convert 0-100 to 0.0000 - 1.0000
        record.confidence_score = Decimal(str(score / 100)).quantize(Decimal('0.0000'))
        record.suspicious_flag = suspicious
