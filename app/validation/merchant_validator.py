"""
Merchant Verification System
100% Offline validation
"""

import re
from typing import Dict, List, Optional
from difflib import SequenceMatcher
from .databases import KNOWN_MERCHANTS, FAMOUS_BRANDS, BUSINESS_HOURS


def calculate_similarity(str1: str, str2: str) -> float:
    """Calculate similarity between two strings (0-1)."""
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


def has_repeated_chars(text: str, threshold: int = 3) -> bool:
    """Check if text has suspicious repeated characters."""
    for i in range(len(text) - threshold + 1):
        if len(set(text[i:i+threshold])) == 1:
            return True
    return False


def normalize_merchant_name(name: str) -> str:
    """Normalize merchant name for comparison."""
    return name.lower().replace(" ", "_").replace("'", "").replace("-", "_")


def analyze_merchant_name_patterns(merchant_name: str) -> Dict:
    """
    Detect suspicious patterns in merchant names.
    
    Args:
        merchant_name: Merchant name to analyze
    
    Returns:
        {
            "valid": bool,
            "confidence": float,
            "issues": list
        }
    """
    if not merchant_name or not isinstance(merchant_name, str):
        return {
            "valid": False,
            "confidence": 0.0,
            "issues": ["No merchant name provided"]
        }
    
    issues = []
    confidence = 1.0
    
    # 1. Check for gibberish
    if has_repeated_chars(merchant_name, threshold=3):
        issues.append("Suspicious repeated characters in name")
        confidence -= 0.4
    
    # 2. Check for random/unusual characters
    if re.search(r'[^a-zA-Z0-9\s\-&\'.()]', merchant_name):
        issues.append("Unusual special characters in name")
        confidence -= 0.2
    
    # 3. Check for all caps (common in fake receipts)
    if merchant_name.isupper() and len(merchant_name) > 5:
        issues.append("All caps merchant name (suspicious)")
        confidence -= 0.15
    
    # 4. Check for very short names
    if len(merchant_name) < 3:
        issues.append("Merchant name too short")
        confidence -= 0.3
    
    # 5. Check for very long names (> 50 chars)
    if len(merchant_name) > 50:
        issues.append("Merchant name unusually long")
        confidence -= 0.2
    
    # 6. Check for common fake patterns
    fake_patterns = ['test', 'sample', 'dummy', 'fake', 'xxx', 'zzz', 'abc', 'temp']
    if any(pattern in merchant_name.lower() for pattern in fake_patterns):
        issues.append("Merchant name contains suspicious keywords")
        confidence -= 0.6
    
    # 7. Check for numbers only
    if merchant_name.replace(' ', '').isdigit():
        issues.append("Merchant name is only numbers")
        confidence -= 0.5
    
    # 8. Check for excessive punctuation
    punct_count = len(re.findall(r'[^\w\s]', merchant_name))
    if punct_count > 5:
        issues.append("Excessive punctuation in name")
        confidence -= 0.2
    
    return {
        "valid": confidence > 0.5,
        "confidence": max(0, confidence),
        "issues": issues
    }


def verify_merchant_database(
    merchant_name: str,
    city: Optional[str] = None,
    pin_code: Optional[str] = None
) -> Dict:
    """
    Verify merchant against known database.
    100% offline.
    
    Args:
        merchant_name: Merchant name
        city: City name (optional)
        pin_code: PIN code (optional)
    
    Returns:
        {
            "known_merchant": bool,
            "verified": bool,
            "confidence": float,
            "issues": list,
            "merchant_data": dict or None
        }
    """
    if not merchant_name:
        return {
            "known_merchant": False,
            "verified": False,
            "confidence": 0.5,
            "issues": ["No merchant name provided"],
            "merchant_data": None
        }
    
    issues = []
    confidence = 0.5  # Neutral if not in database
    merchant_key = normalize_merchant_name(merchant_name)
    
    # 1. Check if merchant is in known database
    matched_merchant = None
    for key, data in KNOWN_MERCHANTS.items():
        # Check exact match
        if merchant_key == key:
            matched_merchant = (key, data)
            break
        
        # Check against official names
        for official_name in data["official_names"]:
            if calculate_similarity(merchant_name, official_name) > 0.85:
                matched_merchant = (key, data)
                break
        
        if matched_merchant:
            break
    
    if matched_merchant:
        key, merchant_data = matched_merchant
        confidence = 0.8  # Known merchant
        issues.append(f"✓ Recognized as {merchant_data['official_names'][0]}")
        
        # 2. Verify location if provided
        if city and pin_code:
            city_normalized = city.lower().strip()
            
            if city_normalized in merchant_data["locations"]:
                if pin_code in merchant_data["locations"][city_normalized]:
                    confidence = 1.0
                    issues.append(f"✓ Verified location: {city}, PIN {pin_code}")
                else:
                    issues.append(f"⚠ {merchant_data['official_names'][0]} exists in {city} but not at PIN {pin_code}")
                    confidence = 0.6
            else:
                issues.append(f"⚠ {merchant_data['official_names'][0]} not known to operate in {city}")
                confidence = 0.4
        
        return {
            "known_merchant": True,
            "verified": confidence > 0.7,
            "confidence": confidence,
            "issues": issues,
            "merchant_data": merchant_data
        }
    
    # 3. Check for typos in famous brands
    for brand in FAMOUS_BRANDS:
        similarity = calculate_similarity(merchant_key, brand)
        if 0.7 < similarity < 1.0:
            issues.append(f"⚠ Possible typo: '{merchant_name}' similar to '{brand}' ({similarity:.0%} match)")
            confidence = 0.3
            break
    
    return {
        "known_merchant": False,
        "verified": False,
        "confidence": confidence,
        "issues": issues if issues else ["Unknown merchant (not in database)"],
        "merchant_data": None
    }


def validate_merchant_items(
    merchant_name: str,
    items: List[Dict],
    merchant_data: Optional[Dict] = None
) -> Dict:
    """
    Check if items match merchant category.
    Example: McDonald's shouldn't sell laptops.
    
    Args:
        merchant_name: Merchant name
        items: List of items [{"name": "...", "total": ...}]
        merchant_data: Merchant data from database
    
    Returns:
        {
            "valid": bool,
            "confidence": float,
            "issues": list,
            "mismatched_items": list
        }
    """
    if not items:
        return {
            "valid": True,
            "confidence": 0.5,
            "issues": ["No items to validate"],
            "mismatched_items": []
        }
    
    if not merchant_data or "typical_items" not in merchant_data:
        return {
            "valid": True,
            "confidence": 0.5,
            "issues": ["Unknown merchant - cannot validate items"],
            "mismatched_items": []
        }
    
    issues = []
    confidence = 1.0
    typical_items = merchant_data["typical_items"]
    mismatched_items = []
    
    # Check each item
    for item in items:
        item_name = item.get("name", "").lower()
        if not item_name:
            continue
        
        # Check if item matches merchant category
        matches = any(typical in item_name for typical in typical_items)
        
        if not matches:
            mismatched_items.append(item.get("name"))
    
    if mismatched_items:
        mismatch_ratio = len(mismatched_items) / len(items)
        issues.append(f"Items don't match merchant type: {', '.join(mismatched_items[:3])}")
        confidence -= 0.3 * mismatch_ratio
        
        if mismatch_ratio > 0.5:
            issues.append(f"Over 50% of items don't match {merchant_name}")
            confidence -= 0.3
    
    # Check price range
    total = sum(item.get("total", 0) for item in items if isinstance(item.get("total"), (int, float)))
    price_range = merchant_data.get("price_range", {})
    
    if total > 0:
        if total < price_range.get("min", 0):
            issues.append(f"Total ₹{total:.2f} unusually low for {merchant_name}")
            confidence -= 0.2
        
        if total > price_range.get("max", float('inf')):
            issues.append(f"Total ₹{total:.2f} unusually high for {merchant_name}")
            confidence -= 0.2
    
    return {
        "valid": confidence > 0.6,
        "confidence": max(0, confidence),
        "issues": issues,
        "mismatched_items": mismatched_items
    }


def determine_merchant_category(merchant_name: str) -> str:
    """Determine merchant category from name."""
    name_lower = merchant_name.lower()
    
    if any(kw in name_lower for kw in ['restaurant', 'cafe', 'food', 'pizza', 'burger', 'kitchen']):
        return 'restaurant'
    elif any(kw in name_lower for kw in ['coffee', 'cafe', 'starbucks']):
        return 'cafe'
    elif any(kw in name_lower for kw in ['pharmacy', 'medical', 'chemist', 'drug']):
        return 'pharmacy'
    elif any(kw in name_lower for kw in ['electronics', 'mobile', 'digital', 'croma']):
        return 'electronics'
    elif any(kw in name_lower for kw in ['grocery', 'supermarket', 'mart', 'bazaar']):
        return 'grocery'
    elif any(kw in name_lower for kw in ['mall', 'shopping center', 'plaza']):
        return 'mall'
    elif any(kw in name_lower for kw in ['airport', 'terminal']):
        return 'airport'
    elif any(kw in name_lower for kw in ['gas', 'petrol', 'fuel']):
        return 'gas_station'
    else:
        return 'retail'


def validate_merchant_complete(
    merchant_name: str,
    city: Optional[str] = None,
    pin_code: Optional[str] = None,
    items: Optional[List[Dict]] = None
) -> Dict:
    """
    Complete merchant validation pipeline.
    
    Args:
        merchant_name: Merchant name
        city: City name
        pin_code: PIN code
        items: List of items
    
    Returns:
        Complete validation results
    """
    # Step 1: Name pattern analysis
    pattern_result = analyze_merchant_name_patterns(merchant_name)
    
    # Step 2: Database verification
    db_result = verify_merchant_database(merchant_name, city, pin_code)
    
    # Step 3: Item consistency (if known merchant)
    item_result = None
    if items and db_result.get("merchant_data"):
        item_result = validate_merchant_items(
            merchant_name,
            items,
            db_result["merchant_data"]
        )
    
    # Combine results
    all_issues = pattern_result["issues"].copy()
    all_issues.extend(db_result["issues"])
    if item_result:
        all_issues.extend(item_result["issues"])
    
    # Calculate overall confidence
    confidences = [pattern_result["confidence"], db_result["confidence"]]
    if item_result:
        confidences.append(item_result["confidence"])
    
    overall_confidence = sum(confidences) / len(confidences)
    
    return {
        "valid": overall_confidence > 0.6,
        "confidence": overall_confidence,
        "issues": all_issues,
        "known_merchant": db_result["known_merchant"],
        "verified": db_result["verified"],
        "merchant_data": db_result.get("merchant_data"),
        "category": determine_merchant_category(merchant_name),
        "details": {
            "pattern": pattern_result,
            "database": db_result,
            "items": item_result
        }
    }
