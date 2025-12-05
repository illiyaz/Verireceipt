"""
Address Validation System
100% Offline validation
"""

import re
from typing import Dict, Optional

# Try to use data loader for full database, fallback to static data
try:
    from .data_loader import get_database
    USE_DATA_LOADER = True
except ImportError:
    USE_DATA_LOADER = False

# Always import fallback data
from .databases import PIN_CODE_DB, CITY_STATE_MAP, AIRPORT_PINS


def has_repeated_chars(text: str, threshold: int = 5) -> bool:
    """Check if text has suspicious repeated characters."""
    for i in range(len(text) - threshold + 1):
        if len(set(text[i:i+threshold])) == 1:
            return True
    return False


def validate_address_format(address: str) -> Dict:
    """
    Validate address structure and format.
    Works 100% offline.
    
    Args:
        address: Full address string
    
    Returns:
        {
            "valid": bool,
            "confidence": float (0-1),
            "issues": list of issues,
            "pin_code": extracted PIN code,
            "zip_code": extracted ZIP code
        }
    """
    if not address or not isinstance(address, str):
        return {
            "valid": False,
            "confidence": 0.0,
            "issues": ["No address provided"],
            "pin_code": None,
            "zip_code": None
        }
    
    issues = []
    confidence = 1.0
    
    # 1. Check minimum length
    if len(address) < 10:
        issues.append("Address too short (< 10 characters)")
        confidence -= 0.3
    
    # 2. Check for gibberish (repeated chars, no spaces)
    if has_repeated_chars(address, threshold=5):
        issues.append("Suspicious repeated characters")
        confidence -= 0.4
    
    if ' ' not in address:
        issues.append("No spaces in address")
        confidence -= 0.3
    
    # 3. Check for numeric component (house/building number)
    if not re.search(r'\d+', address):
        issues.append("No building/house number found")
        confidence -= 0.2
    
    # 4. Check for common address keywords
    address_keywords = [
        'road', 'street', 'avenue', 'lane', 'nagar', 'colony', 
        'sector', 'block', 'floor', 'building', 'plot', 'house',
        'apartment', 'flat', 'tower', 'complex', 'phase', 'main',
        'cross', 'circle', 'junction', 'area', 'layout', 'extension'
    ]
    
    address_lower = address.lower()
    if not any(kw in address_lower for kw in address_keywords):
        issues.append("Missing common address keywords")
        confidence -= 0.2
    
    # 5. Check for PIN/ZIP code
    pin_match = re.search(r'\b\d{6}\b', address)  # Indian PIN
    zip_match = re.search(r'\b\d{5}(-\d{4})?\b', address)  # US ZIP
    
    pin_code = None
    zip_code = None
    
    if pin_match:
        pin_code = pin_match.group()
    elif zip_match:
        zip_code = zip_match.group()
    else:
        issues.append("No PIN/ZIP code found")
        confidence -= 0.3
    
    # 6. Check for all caps (common in fake receipts)
    if address.isupper() and len(address) > 20:
        issues.append("All caps address (suspicious)")
        confidence -= 0.1
    
    # 7. Check for special characters abuse
    special_count = len(re.findall(r'[^a-zA-Z0-9\s,.\-/]', address))
    if special_count > 5:
        issues.append("Too many special characters")
        confidence -= 0.2
    
    return {
        "valid": confidence > 0.5,
        "confidence": max(0, confidence),
        "issues": issues,
        "pin_code": pin_code,
        "zip_code": zip_code
    }


def validate_geography(address: str, pin_code: str) -> Dict:
    """
    Validate geographic consistency.
    100% offline using local database.
    
    Args:
        address: Full address
        pin_code: Extracted PIN code
    
    Returns:
        {
            "valid": bool,
            "confidence": float,
            "issues": list,
            "verified_location": dict
        }
    """
    if not pin_code:
        return {
            "valid": False,
            "confidence": 0.3,
            "issues": ["No PIN code to validate"],
            "verified_location": None
        }
    
    issues = []
    confidence = 1.0
    
    # 1. Validate PIN code exists
    if USE_DATA_LOADER:
        pin_data = get_database().lookup_pin(pin_code)
    else:
        pin_data = PIN_CODE_DB.get(pin_code)
    
    if not pin_data:
        issues.append(f"PIN code {pin_code} not found in database")
        confidence = 0.3
        return {
            "valid": False,
            "confidence": confidence,
            "issues": issues,
            "verified_location": None
        }
    
    # 2. Check city-state consistency
    address_lower = address.lower()
    
    # Extract mentioned city
    mentioned_city = None
    for city in CITY_STATE_MAP.keys():
        if city in address_lower:
            mentioned_city = city
            break
    
    if mentioned_city:
        expected_city = pin_data["city"].lower()
        
        # Handle city name variations
        city_variations = {
            "bangalore": ["bengaluru", "bangalore"],
            "bengaluru": ["bengaluru", "bangalore"],
            "mumbai": ["mumbai", "bombay"],
        }
        
        expected_variations = city_variations.get(expected_city, [expected_city])
        
        if mentioned_city not in expected_variations and expected_city not in [mentioned_city]:
            issues.append(f"City mismatch: '{mentioned_city}' in address but PIN {pin_code} is for {expected_city}")
            confidence -= 0.4
    
    # 3. Check state consistency
    mentioned_state = None
    states = ["telangana", "karnataka", "maharashtra", "delhi", "tamil nadu", 
              "west bengal", "gujarat", "rajasthan", "uttar pradesh", "andhra pradesh"]
    
    for state in states:
        if state in address_lower:
            mentioned_state = state
            break
    
    if mentioned_state:
        expected_state = pin_data["state"].lower()
        if mentioned_state != expected_state:
            issues.append(f"State mismatch: '{mentioned_state}' in address but PIN {pin_code} is for {expected_state}")
            confidence -= 0.5
    
    return {
        "valid": confidence > 0.5,
        "confidence": max(0, confidence),
        "issues": issues,
        "verified_location": pin_data
    }


def validate_merchant_address_distance(merchant_name: str, pin_code: str) -> Dict:
    """
    Check if merchant type matches location type.
    Example: "Airport Duty Free" should be near airport PIN codes.
    
    Args:
        merchant_name: Merchant name
        pin_code: PIN code
    
    Returns:
        {
            "valid": bool,
            "confidence": float,
            "issues": list
        }
    """
    if not merchant_name or not pin_code:
        return {"valid": True, "confidence": 0.5, "issues": []}
    
    issues = []
    confidence = 1.0
    merchant_lower = merchant_name.lower()
    
    # Airport merchants
    if any(kw in merchant_lower for kw in ['airport', 'duty free', 'terminal', 'aviation']):
        if pin_code not in AIRPORT_PINS:
            # Check if PIN prefix matches airport area
            airport_prefixes = [p[:3] for p in AIRPORT_PINS.keys()]
            if pin_code[:3] not in airport_prefixes:
                issues.append(f"Airport merchant but address PIN {pin_code} not near any airport")
                confidence -= 0.4
    
    # Railway station
    if any(kw in merchant_lower for kw in ['railway', 'station', 'irctc']):
        # Railway stations typically in central areas (ending in 001, 002)
        if not pin_code.endswith(('001', '002', '003')):
            issues.append("Railway merchant but not in typical station area")
            confidence -= 0.2
    
    return {
        "valid": confidence > 0.6,
        "confidence": confidence,
        "issues": issues
    }


def validate_address_complete(
    address: str,
    merchant_name: Optional[str] = None
) -> Dict:
    """
    Complete address validation pipeline.
    
    Args:
        address: Full address
        merchant_name: Optional merchant name for context
    
    Returns:
        Complete validation results
    """
    # Step 1: Format validation
    format_result = validate_address_format(address)
    
    if not format_result["valid"]:
        return {
            "valid": False,
            "confidence": format_result["confidence"],
            "issues": format_result["issues"],
            "details": {
                "format": format_result,
                "geography": None,
                "merchant_distance": None
            }
        }
    
    # Step 2: Geographic validation
    pin_code = format_result.get("pin_code")
    geography_result = None
    
    if pin_code:
        geography_result = validate_geography(address, pin_code)
    
    # Step 3: Merchant-location validation
    merchant_distance_result = None
    if merchant_name and pin_code:
        merchant_distance_result = validate_merchant_address_distance(merchant_name, pin_code)
    
    # Combine results
    all_issues = format_result["issues"].copy()
    if geography_result:
        all_issues.extend(geography_result["issues"])
    if merchant_distance_result:
        all_issues.extend(merchant_distance_result["issues"])
    
    # Calculate overall confidence
    confidences = [format_result["confidence"]]
    if geography_result:
        confidences.append(geography_result["confidence"])
    if merchant_distance_result:
        confidences.append(merchant_distance_result["confidence"])
    
    overall_confidence = sum(confidences) / len(confidences)
    
    return {
        "valid": overall_confidence > 0.6,
        "confidence": overall_confidence,
        "issues": all_issues,
        "pin_code": pin_code,
        "verified_location": geography_result.get("verified_location") if geography_result else None,
        "details": {
            "format": format_result,
            "geography": geography_result,
            "merchant_distance": merchant_distance_result
        }
    }
