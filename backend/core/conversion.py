import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


class ConversionService:
    """
    Normalization Engine / Conversion Service
    Handles unit conversions across different activity types.
    """

    TARGET_UNITS = {
        'fuel': 'liters',
        'electricity': 'kWh',
        'flight': 'km',
        'ground_transport': 'km',
        'travel': 'km',
        'procurement': 'USD',
    }

    CONVERSION_RATES = {
        # Fuel -> liters
        'liters': Decimal('1.0'),
        'liter': Decimal('1.0'),
        'l': Decimal('1.0'),
        'gallons': Decimal('3.78541'),
        'gallon': Decimal('3.78541'),
        'gal': Decimal('3.78541'),
        
        # Electricity -> kWh
        'kwh': Decimal('1.0'),
        'mwh': Decimal('1000.0'),
        
        # Travel / Distance -> km
        'km': Decimal('1.0'),
        'kilometers': Decimal('1.0'),
        'miles': Decimal('1.60934'),
        'mi': Decimal('1.60934'),
        
        # Procurement / Currency -> USD
        'usd': Decimal('1.0'),
        'inr': Decimal('0.012'),
        'eur': Decimal('1.08'),
    }

    @classmethod
    def convert(cls, activity_type: str, original_value: Decimal, original_unit: str) -> tuple[Decimal, str]:
        """
        Convert original value to normalized value based on activity type.
        
        Returns:
            tuple[Decimal, str]: (normalized_value, normalized_unit)
        """
        if not original_unit:
            return original_value, original_unit
            
        unit_lower = str(original_unit).strip().lower()
        
        # Handle cases where activity_type might be broader
        if activity_type in ('flight', 'ground_transport'):
            mapped_activity = 'travel'
        else:
            mapped_activity = activity_type

        target_unit = cls.TARGET_UNITS.get(mapped_activity, original_unit)
        target_unit_fallback = cls.TARGET_UNITS.get(activity_type, target_unit)
        
        if unit_lower in cls.CONVERSION_RATES:
            rate = cls.CONVERSION_RATES[unit_lower]
            normalized_value = (original_value * rate).quantize(Decimal("0.000001"))
            return normalized_value, target_unit_fallback
            
        logger.warning(f"No conversion rate found for unit: {original_unit}")
        return original_value, original_unit
