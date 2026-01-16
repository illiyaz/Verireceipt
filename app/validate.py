import re
from typing import Dict, Any, List

STREET_KEYWORDS = [
    "street", "st", "road", "rd", "avenue", "ave",
    "boulevard", "blvd", "lane", "ln", "drive", "dr",
    "way", "circle", "cir", "court", "ct"
]

UNIT_KEYWORDS = [
    "apt", "apartment", "suite", "ste", "unit",
    "floor", "fl", "building", "bldg", "#"
]

def validate_address(text: str) -> Dict[str, Any]:
    if not text or len(text) < 15:
        return _empty_result()

    text_norm = text.lower()
    score = 0
    evidence: List[str] = []

    # 1. Street indicators (strong)
    for kw in STREET_KEYWORDS:
        if re.search(rf"\b{kw}\b", text_norm):
            score += 2
            evidence.append(f"street_keyword:{kw}")
            break

    # 2. Unit / building indicators
    for kw in UNIT_KEYWORDS:
        if re.search(rf"\b{kw}\b", text_norm):
            score += 1
            evidence.append(f"unit_keyword:{kw}")
            break

    # 3. City / locality heuristic
    words = re.findall(r"\b[a-zA-Z]{4,}\b", text_norm)
    if len(words) >= 2:
        score += 1
        evidence.append("locality_tokens")

    # 4. Postal-like token (very weak)
    if re.search(r"\b[a-zA-Z0-9]{4,8}\b", text_norm):
        score += 1
        evidence.append("postal_like_token")

    classification = _classify(score)

    return {
        "address_score": score,
        "address_classification": classification,
        "address_evidence": evidence
    }

def _classify(score: int) -> str:
    if score < 3:
        return "NOT_AN_ADDRESS"
    if score <= 4:
        return "WEAK_ADDRESS"
    if score <= 6:
        return "PLAUSIBLE_ADDRESS"
    return "STRONG_ADDRESS"

def _empty_result() -> Dict[str, Any]:
    return {
        "address_score": 0,
        "address_classification": "NOT_AN_ADDRESS",
        "address_evidence": []
    }
