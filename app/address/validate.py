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
    
    # NEW (V2.1): Address type heuristic (safe, not part of score)
    address_type = "STANDARD"
    if re.search(r"\b(p\.?\s*o\.?\s*box|po\s*box)\b", text_norm, re.IGNORECASE):
        address_type = "PO_BOX"
        evidence.append("address_type:po_box")
    
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
    
    # 5. Country/state explicit mention ( +1 )
    location_found = False
    for kw in LOCATION_KEYWORDS:
        if re.search(rf"\b{kw}\b", text_norm):
            score += 1
            evidence.append(f"location_keyword:{kw}")
            location_found = True
            break
    
    # Classify based on score
    classification = _classify(score)
    
    return {
        "address_score": score,
        "address_classification": classification,
        "address_evidence": evidence,
        # NEW fields (V2.1)
        "address_raw_text": text,
        "address_type": address_type,
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
        "address_evidence": [],
        # V2.1 fields
        "address_raw_text": "",
        "address_type": "UNKNOWN",
    }


def assess_merchant_address_consistency(
    merchant_name: str,
    merchant_confidence: float,
    address_profile: dict,
    doc_profile_confidence: float,
) -> dict:
    """
    Assess semantic consistency between merchant and address.

    This is V2.1: feature-only, safe-by-default, confidence-gated.
    It emits a SOFT mismatch score that downstream learned rules may use later.

    Args:
        merchant_name: Extracted merchant name
        merchant_confidence: Confidence in merchant extraction
        address_profile: Output from validate_address()
        doc_profile_confidence: Document classification confidence

    Returns:
        {
            "status": "CONSISTENT" | "WEAK_MISMATCH" | "MISMATCH" | "UNKNOWN",
            "score": 0.0 - 0.2,
            "evidence": [str, ...]
        }
    """

    # Hard gates: if any core signal is weak -> UNKNOWN
    if (
        not merchant_name
        or (merchant_confidence or 0.0) < 0.6
        or not address_profile
        or address_profile.get("address_classification") not in ("PLAUSIBLE_ADDRESS", "STRONG_ADDRESS")
        or (doc_profile_confidence or 0.0) < 0.55
    ):
        return {"status": "UNKNOWN", "score": 0.0, "evidence": []}

    evidence: List[str] = []
    score = 0.0

    # Token overlap (weak signal)
    merchant_tokens = {
        t.lower()
        for t in re.findall(r"[A-Za-z]{4,}", merchant_name or "")
        if t.lower() not in {"ltd", "llp", "inc", "corp", "company", "co", "pvt", "private", "limited"}
    }

    address_text = address_profile.get("address_raw_text", "") or ""
    address_tokens = {t.lower() for t in re.findall(r"[A-Za-z]{4,}", address_text)}

    overlap = merchant_tokens & address_tokens
    if overlap:
        evidence.append(f"merchant_token_overlap:{','.join(sorted(overlap))}")
        score += 0.1

    # Address type mismatch heuristics (soft)
    address_type = address_profile.get("address_type", "UNKNOWN")

    merchant_is_corporate = bool(
        re.search(r"\b(ltd|llp|inc|corp|company|logistics|services|solutions|industries)\b", merchant_name, re.IGNORECASE)
    )

    if merchant_is_corporate and address_type == "PO_BOX":
        evidence.append("address_type_mismatch:po_box_vs_corporate")
        score += 0.2

    # If nothing triggered, treat as consistent (don't invent mismatch)
    if score == 0.0:
        return {"status": "CONSISTENT", "score": 0.0, "evidence": []}

    status = "WEAK_MISMATCH" if score <= 0.1 else "MISMATCH"

    return {
        "status": status,
        "score": round(min(score, 0.2), 2),
        "evidence": evidence,
    }
