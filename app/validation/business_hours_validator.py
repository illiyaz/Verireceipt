"""
Business Hours Validation System
Check if transaction time is within normal business hours
"""

from datetime import datetime, time
from typing import Dict, Tuple, Optional
from .databases import BUSINESS_HOURS


def parse_time(time_str: str) -> Optional[int]:
    """
    Parse time string and return hour (0-23).
    
    Args:
        time_str: Time string in various formats
    
    Returns:
        Hour (0-23) or None if parsing fails
    """
    if not time_str:
        return None
    
    # Try different formats
    formats = [
        "%H:%M:%S",    # 14:30:00
        "%H:%M",       # 14:30
        "%I:%M %p",    # 02:30 PM
        "%I:%M%p",     # 02:30PM
    ]
    
    for fmt in formats:
        try:
            time_obj = datetime.strptime(time_str.strip(), fmt)
            return time_obj.hour
        except ValueError:
            continue
    
    return None


def get_business_hours(category: str) -> Tuple[int, int]:
    """
    Get typical business hours for a category.
    
    Args:
        category: Business category
    
    Returns:
        (start_hour, end_hour) tuple
    """
    return BUSINESS_HOURS.get(category, (8, 22))  # Default 8 AM - 10 PM


def validate_business_hours(
    merchant_name: str,
    receipt_time: str,
    receipt_date: Optional[str] = None,
    category: Optional[str] = None
) -> Dict:
    """
    Check if transaction time is within business hours.
    
    Args:
        merchant_name: Merchant name
        receipt_time: Receipt time string
        receipt_date: Receipt date (optional)
        category: Merchant category (optional)
    
    Returns:
        {
            "valid": bool,
            "confidence": float,
            "issues": list,
            "business_hours": (start, end),
            "transaction_hour": int
        }
    """
    if not receipt_time:
        return {
            "valid": True,
            "confidence": 0.5,
            "issues": ["No time provided"],
            "business_hours": None,
            "transaction_hour": None
        }
    
    issues = []
    confidence = 1.0
    
    # Parse time
    hour = parse_time(receipt_time)
    
    if hour is None:
        return {
            "valid": True,
            "confidence": 0.5,
            "issues": [f"Could not parse time: {receipt_time}"],
            "business_hours": None,
            "transaction_hour": None
        }
    
    # Determine category if not provided
    if not category:
        merchant_lower = merchant_name.lower()
        
        if any(kw in merchant_lower for kw in ['restaurant', 'cafe', 'food', 'pizza', 'burger']):
            category = 'restaurant'
        elif any(kw in merchant_lower for kw in ['pharmacy', 'medical', 'chemist']):
            category = 'pharmacy'
        elif any(kw in merchant_lower for kw in ['electronics', 'mobile', 'digital']):
            category = 'electronics'
        elif any(kw in merchant_lower for kw in ['grocery', 'supermarket', 'mart']):
            category = 'grocery'
        elif any(kw in merchant_lower for kw in ['mall', 'shopping']):
            category = 'mall'
        elif any(kw in merchant_lower for kw in ['airport', 'terminal']):
            category = 'airport'
        elif any(kw in merchant_lower for kw in ['gas', 'petrol', 'fuel']):
            category = 'gas_station'
        else:
            category = 'retail'
    
    # Get business hours for category
    hours = get_business_hours(category)
    start_hour, end_hour = hours
    
    # Check if 24/7
    if start_hour == 0 and end_hour == 24:
        return {
            "valid": True,
            "confidence": 1.0,
            "issues": [],
            "business_hours": hours,
            "transaction_hour": hour,
            "category": category
        }
    
    # Check if within hours
    if not (start_hour <= hour < end_hour):
        issues.append(f"Transaction at {receipt_time} ({hour:02d}:00) outside typical hours ({start_hour:02d}:00-{end_hour:02d}:00)")
        confidence -= 0.3
    
    # Check for very unusual times (2 AM - 5 AM)
    if 2 <= hour < 5:
        issues.append("Transaction at unusual time (2-5 AM)")
        confidence -= 0.4
    
    # Check for late night (11 PM - 2 AM) for non-24hr businesses
    if 23 <= hour or hour < 2:
        if category not in ['pharmacy', 'gas_station', 'airport', 'convenience_store']:
            issues.append(f"Late night transaction for {category}")
            confidence -= 0.2
    
    # Check for very early morning (5 AM - 7 AM)
    if 5 <= hour < 7:
        if category not in ['pharmacy', 'gas_station', 'airport', 'restaurant', 'cafe']:
            issues.append(f"Very early transaction for {category}")
            confidence -= 0.2
    
    return {
        "valid": confidence > 0.5,
        "confidence": max(0, confidence),
        "issues": issues,
        "business_hours": hours,
        "transaction_hour": hour,
        "category": category
    }


def validate_day_of_week(
    receipt_date: str,
    merchant_name: str,
    category: Optional[str] = None
) -> Dict:
    """
    Check if business is typically open on this day.
    Some businesses closed on Sundays/Mondays.
    
    Args:
        receipt_date: Receipt date string
        merchant_name: Merchant name
        category: Merchant category
    
    Returns:
        Validation results
    """
    if not receipt_date:
        return {
            "valid": True,
            "confidence": 0.5,
            "issues": ["No date provided"]
        }
    
    try:
        # Try to parse date
        date_formats = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"]
        date_obj = None
        
        for fmt in date_formats:
            try:
                date_obj = datetime.strptime(receipt_date, fmt)
                break
            except ValueError:
                continue
        
        if not date_obj:
            return {
                "valid": True,
                "confidence": 0.5,
                "issues": [f"Could not parse date: {receipt_date}"]
            }
        
        day_of_week = date_obj.weekday()  # 0=Monday, 6=Sunday
        day_name = date_obj.strftime("%A")
        
        issues = []
        confidence = 1.0
        
        # Check Sunday operations
        if day_of_week == 6:  # Sunday
            # Some businesses typically closed on Sunday
            if category in ['electronics', 'retail'] and 'mall' not in merchant_name.lower():
                issues.append(f"Transaction on Sunday - some {category} stores may be closed")
                confidence -= 0.1
        
        return {
            "valid": confidence > 0.5,
            "confidence": confidence,
            "issues": issues,
            "day_of_week": day_name
        }
    
    except Exception as e:
        return {
            "valid": True,
            "confidence": 0.5,
            "issues": [f"Error validating day: {str(e)}"]
        }
