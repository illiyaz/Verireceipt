"""
Geo-agnostic address validation for VeriReceipt.

Design Principles:
- Validate structure, not correctness
- Country-agnostic by default
- Use patterns that generalize globally
- Gate all strict logic on doc_profile_confidence

This module does NOT:
- Make India-only assumptions
- Perform postal DB lookups
- Check if address exists
- Use heavy regex per country

Scoring Rubric:
- Street indicator (street, st, road, rd, ave, blvd, lane, ln): +2
- Building/unit (apt, suite, unit, floor, fl, #): +1
- City/locality token (alphabetic word >3 chars): +1
- Postal-like token (alphanumeric 4-8 chars): +1
- Country/state word (explicit word): +2

Confidence Gates:
- Score < 3: NOT_AN_ADDRESS
- Score 3-4: WEAK_ADDRESS
- Score 5-6: PLAUSIBLE_ADDRESS
- Score >= 7: STRONG_ADDRESS
"""

import re
from typing import Dict, Any, List

# Universal street indicators (English-based, expandable)
STREET_KEYWORDS = [
    "street", "st", "road", "rd", "avenue", "ave",
    "boulevard", "blvd", "lane", "ln", "drive", "dr",
    "way", "circle", "cir", "court", "ct", "place", "pl",
    "terrace", "ter", "parkway", "pkwy", "highway", "hwy"
]

# Building/unit indicators
UNIT_KEYWORDS = [
    "apt", "apartment", "suite", "ste", "unit",
    "floor", "fl", "building", "bldg", "#", "no",
    "room", "rm"
]

# Country/state indicators (explicit mentions)
LOCATION_KEYWORDS = [
    "usa", "canada", "india", "uk", "australia",
    "singapore", "malaysia", "thailand", "indonesia",
    "california", "texas", "ontario", "delhi", "mumbai"
]


def validate_address(text: str) -> Dict[str, Any]:
    """
    Validate address structure in text.
    
    Args:
        text: Full text to analyze for address patterns
        
    Returns:
        Dict with:
        - address_score: int (0-10+)
        - address_classification: str (NOT_AN_ADDRESS, WEAK_ADDRESS, PLAUSIBLE_ADDRESS, STRONG_ADDRESS)
        - address_evidence: List[str] (signals found)
    """
    if not text or len(text) < 10:
        return _empty_result()
    
    text_norm = text.lower()
    score = 0
    evidence: List[str] = []
    
    # 1. Street indicators (strong signal, +2)
    street_found = False
    for kw in STREET_KEYWORDS:
        if re.search(rf"\b{kw}\b", text_norm):
            score += 2
            evidence.append(f"street_keyword:{kw}")
            street_found = True
            break
    
    # 2. Unit/building indicators (+1)
    unit_found = False
    for kw in UNIT_KEYWORDS:
        if re.search(rf"\b{kw}\b", text_norm):
            score += 1
            evidence.append(f"unit_keyword:{kw}")
            unit_found = True
            break
    
    # 3. City/locality heuristic (+1 to +2 based on count)
    # Look for alphabetic words >= 4 chars (potential city names)
    words = re.findall(r"\b[a-zA-Z]{4,}\b", text_norm)
    if len(words) >= 3:
        score += 2
        evidence.append("multiple_locality_tokens")
    elif len(words) >= 2:
        score += 1
        evidence.append("locality_tokens")
    
    # 4. Postal-like token (very weak, +1)
    # Alphanumeric 4-8 chars (could be postal code)
    postal_matches = re.findall(r"\b[a-zA-Z0-9]{4,8}\b", text_norm)
    if len(postal_matches) >= 1:
        score += 1
        evidence.append("postal_like_token")
    
    # 5. Country/state explicit mention (+2)
    location_found = False
    for kw in LOCATION_KEYWORDS:
        if re.search(rf"\b{kw}\b", text_norm):
            score += 2
            evidence.append(f"location_keyword:{kw}")
            location_found = True
            break
    
    # Classify based on score
    classification = _classify(score)
    
    return {
        "address_score": score,
        "address_classification": classification,
        "address_evidence": evidence
    }


def _classify(score: int) -> str:
    """Classify address confidence based on score."""
    if score < 3:
        return "NOT_AN_ADDRESS"
    if score == 3:
        return "WEAK_ADDRESS"
    if score <= 5:
        return "PLAUSIBLE_ADDRESS"
    return "STRONG_ADDRESS"


def _empty_result() -> Dict[str, Any]:
    """Return empty result for invalid input."""
    return {
        "address_score": 0,
        "address_classification": "NOT_AN_ADDRESS",
        "address_evidence": []
    }
