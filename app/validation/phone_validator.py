"""
Phone Number Validation System
Supports Indian and US formats
"""

import re
from typing import Dict
from .databases import VALID_MOBILE_PREFIXES, VALID_LANDLINE_CODES


def has_repeated_chars(text: str, threshold: int = 5) -> bool:
    """Check if text has suspicious repeated characters."""
    for i in range(len(text) - threshold + 1):
        if len(set(text[i:i+threshold])) == 1:
            return True
    return False


def is_sequential(digits: str, threshold: int = 5) -> bool:
    """Check if digits are sequential (12345, 98765)."""
    for i in range(len(digits) - threshold + 1):
        segment = digits[i:i+threshold]
        # Check ascending
        is_asc = all(int(segment[j+1]) == int(segment[j]) + 1 for j in range(len(segment)-1))
        # Check descending
        is_desc = all(int(segment[j+1]) == int(segment[j]) - 1 for j in range(len(segment)-1))
        if is_asc or is_desc:
            return True
    return False


def format_phone_indian(digits: str) -> str:
    """Format Indian phone number."""
    if len(digits) == 10:
        return f"+91-{digits[:5]}-{digits[5:]}"
    elif len(digits) == 11 and digits[0] == '0':
        return f"0{digits[1:3]}-{digits[3:]}"
    return digits


def validate_phone_number(phone: str, country: str = "IN") -> Dict:
    """
    Validate phone number format and check if it's real.
    
    Args:
        phone: Phone number string
        country: Country code ("IN" for India, "US" for USA)
    
    Returns:
        {
            "valid": bool,
            "confidence": float,
            "issues": list,
            "formatted": formatted phone number,
            "type": "mobile" or "landline"
        }
    """
    if not phone or not isinstance(phone, str):
        return {
            "valid": False,
            "confidence": 0.0,
            "issues": ["No phone number provided"],
            "formatted": None,
            "type": None
        }
    
    issues = []
    confidence = 1.0
    phone_type = None
    
    # Remove formatting characters
    phone_digits = re.sub(r'[^\d+]', '', phone)
    
    if country == "IN":
        # Indian format validation
        
        # Remove country code if present
        if phone_digits.startswith('+91'):
            phone_digits = phone_digits[3:]
        elif phone_digits.startswith('91') and len(phone_digits) == 12:
            phone_digits = phone_digits[2:]
        elif phone_digits.startswith('0'):
            # Landline with STD code
            pass
        
        # Check length
        if len(phone_digits) == 10:
            # Mobile number
            phone_type = "mobile"
            
            # Check valid starting digits for mobile
            if phone_digits[0] not in VALID_MOBILE_PREFIXES:
                issues.append(f"Invalid mobile prefix: {phone_digits[0]}")
                confidence -= 0.4
        
        elif len(phone_digits) == 11 and phone_digits[0] == '0':
            # Landline with STD code
            phone_type = "landline"
            std_code = phone_digits[1:3]
            
            if std_code not in VALID_LANDLINE_CODES:
                # Try 3-digit STD code
                std_code = phone_digits[1:4]
                if std_code not in VALID_LANDLINE_CODES:
                    issues.append(f"Invalid STD code: {std_code}")
                    confidence -= 0.3
        
        else:
            issues.append(f"Invalid phone number length: {len(phone_digits)} digits")
            confidence -= 0.5
        
        # Check for repeated digits (common in fake numbers)
        if has_repeated_chars(phone_digits, threshold=5):
            issues.append("Suspicious repeated digits (e.g., 99999)")
            confidence -= 0.5
        
        # Check for sequential digits
        if is_sequential(phone_digits, threshold=5):
            issues.append("Sequential digits detected (e.g., 12345)")
            confidence -= 0.6
        
        # Check for all same digits
        if len(set(phone_digits)) == 1:
            issues.append("All digits are the same")
            confidence -= 0.8
        
        # Check for common fake patterns
        fake_patterns = ['1234567890', '9999999999', '0000000000', '1111111111']
        if phone_digits in fake_patterns:
            issues.append("Known fake phone pattern")
            confidence -= 0.9
        
        formatted = format_phone_indian(phone_digits)
    
    elif country == "US":
        # US format validation
        
        # Remove country code if present
        if phone_digits.startswith('+1'):
            phone_digits = phone_digits[2:]
        elif phone_digits.startswith('1') and len(phone_digits) == 11:
            phone_digits = phone_digits[1:]
        
        # Should be 10 digits
        if len(phone_digits) != 10:
            issues.append(f"Invalid US phone length: {len(phone_digits)} digits")
            confidence -= 0.5
        else:
            phone_type = "mobile"
            
            # Check area code (first 3 digits)
            area_code = phone_digits[:3]
            if area_code[0] in ['0', '1']:
                issues.append(f"Invalid area code: {area_code}")
                confidence -= 0.4
            
            # Check for repeated/sequential
            if has_repeated_chars(phone_digits, threshold=5):
                issues.append("Suspicious repeated digits")
                confidence -= 0.5
            
            if is_sequential(phone_digits, threshold=5):
                issues.append("Sequential digits detected")
                confidence -= 0.6
        
        formatted = f"+1-{phone_digits[:3]}-{phone_digits[3:6]}-{phone_digits[6:]}" if len(phone_digits) == 10 else phone_digits
    
    else:
        return {
            "valid": False,
            "confidence": 0.0,
            "issues": [f"Unsupported country: {country}"],
            "formatted": phone,
            "type": None
        }
    
    return {
        "valid": confidence > 0.5,
        "confidence": max(0, confidence),
        "issues": issues,
        "formatted": formatted,
        "type": phone_type
    }


def extract_phone_from_text(text: str) -> list:
    """
    Extract phone numbers from text.
    
    Args:
        text: Text containing phone numbers
    
    Returns:
        List of extracted phone numbers
    """
    if not text:
        return []
    
    # Patterns for Indian phone numbers
    patterns = [
        r'\+91[-\s]?\d{5}[-\s]?\d{5}',  # +91-XXXXX-XXXXX
        r'\b\d{10}\b',                    # 10 digits
        r'\b0\d{2,3}[-\s]?\d{7,8}\b',    # Landline with STD
    ]
    
    phones = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        phones.extend(matches)
    
    return list(set(phones))  # Remove duplicates
