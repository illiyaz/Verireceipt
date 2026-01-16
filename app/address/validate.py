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
- Country/state word (explicit word): +1

Confidence Gates:
- Score < 3: NOT_AN_ADDRESS
- Score = 3: WEAK_ADDRESS
- Score 4-5: PLAUSIBLE_ADDRESS
- Score >= 6: STRONG_ADDRESS
"""

import re
from typing import Dict, Any, List, Optional

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

# --- V2.2: Multi-address detection (feature-only) ---------------------------

# Conservative limits to keep runtime bounded
_MAX_BLOCK_CHARS = 250
_MAX_CANDIDATES = 6


def _chunk_lines_windows(lines: List[str], window_sizes: List[int]) -> List[str]:
    """Create sliding windows of N lines (joined) to discover address-like blocks."""
    out: List[str] = []
    clean_lines = [ln.strip() for ln in lines if ln and ln.strip()]
    for w in window_sizes:
        if w <= 0:
            continue
        for i in range(0, max(0, len(clean_lines) - w + 1)):
            block = "\n".join(clean_lines[i : i + w]).strip()
            if block:
                out.append(block)
    return out


def _dedupe_blocks(blocks: List[str]) -> List[str]:
    """Dedupe blocks using a normalized key; keep order."""
    seen = set()
    out: List[str] = []
    for b in blocks:
        key = re.sub(r"\s+", " ", (b or "").strip().lower())
        key = key[:_MAX_BLOCK_CHARS]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append((b or "")[:_MAX_BLOCK_CHARS])
    return out


def _address_signature(address_profile: Dict[str, Any]) -> Dict[str, Any]:
    """Create a light-weight signature for distinctness checks."""
    raw = (address_profile.get("address_raw_text") or "").lower()

    # Postal-like token (weak but useful for distinctness)
    postal = None
    m = re.search(r"\b[a-z0-9]{4,8}\b", raw)
    if m:
        postal = m.group(0)

    # Street keyword present in evidence (preferred) else regex fallback
    street_kw = None
    for ev in address_profile.get("address_evidence", []) or []:
        if ev.startswith("street_keyword:"):
            street_kw = ev.split(":", 1)[1]
            break
    if street_kw is None:
        for kw in STREET_KEYWORDS:
            if re.search(rf"\b{kw}\b", raw):
                street_kw = kw
                break

    # Locality tokens set (coarse)
    locality_tokens = {
        t.lower()
        for t in re.findall(r"\b[a-zA-Z]{4,}\b", raw)
        if t.lower()
        not in {
            "street",
            "road",
            "avenue",
            "boulevard",
            "lane",
            "drive",
            "suite",
            "apartment",
            "building",
        }
    }

    return {
        "postal": postal,
        "street_kw": street_kw,
        "locality": locality_tokens,
        "address_type": address_profile.get("address_type", "UNKNOWN"),
    }


def _is_distinct(sig_a: Dict[str, Any], sig_b: Dict[str, Any]) -> bool:
    """Conservative distinctness heuristic for two address candidates."""
    if not sig_a or not sig_b:
        return False

    # Address type difference is a strong separator (PO_BOX vs STANDARD)
    if sig_a.get("address_type") != sig_b.get("address_type"):
        return True

    # Different postal-like tokens strongly suggest distinct addresses
    pa, pb = sig_a.get("postal"), sig_b.get("postal")
    if pa and pb and pa != pb:
        return True

    # Different street keywords can be a separator (weak-ish)
    sa, sb = sig_a.get("street_kw"), sig_b.get("street_kw")
    if sa and sb and sa != sb:
        la, lb = sig_a.get("locality", set()), sig_b.get("locality", set())
        inter = len(la & lb)
        union = len(la | lb) or 1
        if (inter / union) < 0.5:
            return True

    # Low locality overlap suggests distinct locations
    la, lb = sig_a.get("locality", set()), sig_b.get("locality", set())
    if la and lb:
        inter = len(la & lb)
        union = len(la | lb) or 1
        if (inter / union) < 0.4:
            return True

    return False


def detect_multi_address_profile(
    text: str,
    doc_profile_confidence: float,
    max_candidates: int = _MAX_CANDIDATES,
) -> Dict[str, Any]:
    """V2.2 Multi-address detection (feature-only).

    This is STRUCTURE detection only:
    - Finds multiple distinct address-like blocks in a document
    - Does NOT validate correctness or existence
    - Geo-agnostic by default

    Returns:
        {
          "status": "SINGLE" | "MULTIPLE" | "UNKNOWN",
          "count": int,
          "address_types": ["STANDARD"|"PO_BOX"|"UNKNOWN", ...],
          "evidence": [str, ...]
        }
    """
    # Confidence gating to avoid false positives on uncertain doc types
    if doc_profile_confidence < 0.55:
        return {
            "status": "UNKNOWN",
            "count": 0,
            "address_types": [],
            "evidence": ["gated_low_doc_confidence"],
            "candidates_preview": [],
        }

    if not text or len(text.strip()) < 50:
        return {
            "status": "UNKNOWN",
            "count": 0,
            "address_types": [],
            "evidence": ["insufficient_text"],
            "candidates_preview": [],
        }

    norm = text.replace("\r", "\n")
    lines = [ln.strip() for ln in norm.split("\n")]

    # Candidate blocks: paragraphs + sliding windows
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", norm) if p and p.strip()]
    paragraph_blocks = [p[:_MAX_BLOCK_CHARS] for p in paragraphs]

    window_blocks = _chunk_lines_windows(lines, window_sizes=[2, 3, 4])

    blocks = _dedupe_blocks(paragraph_blocks + window_blocks)

    # Score blocks with existing validator; keep only plausible+ candidates
    candidates: List[Dict[str, Any]] = []
    for b in blocks:
        prof = validate_address(b)
        if prof.get("address_classification") in ("PLAUSIBLE_ADDRESS", "STRONG_ADDRESS"):
            candidates.append(prof)
        if len(candidates) >= max_candidates:
            break

    if len(candidates) < 2:
        if len(candidates) == 1:
            prof = candidates[0]
            raw_text = prof.get("address_raw_text", "")
            preview = raw_text[:50] + "..." if len(raw_text) > 50 else raw_text
            
            return {
                "status": "SINGLE",
                "count": 1,
                "address_types": [prof.get("address_type", "UNKNOWN")],
                "evidence": ["one_address_candidate"],
                "candidates_preview": [{
                    "type": prof.get("address_type", "UNKNOWN"),
                    "confidence": prof.get("address_classification", "UNKNOWN"),
                    "preview": preview,
                }],
            }
        return {
            "status": "UNKNOWN",
            "count": 0,
            "address_types": [],
            "evidence": ["no_address_candidates"],
            "candidates_preview": [],
        }

    # Distinctness grouping (greedy clustering)
    groups: List[Dict[str, Any]] = []
    for c in candidates:
        sig = _address_signature(c)
        placed = False
        for g in groups:
            if not _is_distinct(sig, g["sig"]):
                placed = True
                break
        if not placed:
            groups.append({"sig": sig, "profile": c})

    distinct_count = len(groups)
    types = [g["sig"].get("address_type", "UNKNOWN") for g in groups]

    if distinct_count >= 2:
        evidence: List[str] = []
        distinctness_basis: List[str] = []
        
        postals = [g["sig"].get("postal") for g in groups if g["sig"].get("postal")]
        if len(set(postals)) >= 2:
            evidence.append("distinct_postal_tokens")
            distinctness_basis.append("postal_tokens")
        if len(set(types)) >= 2:
            evidence.append("distinct_address_types")
            distinctness_basis.append("address_type")
        
        # V2.2: Add candidates_preview for debugging (truncated text)
        candidates_preview = []
        for g in groups[:5]:  # Limit to top 5 for brevity
            prof = g["profile"]
            raw_text = prof.get("address_raw_text", "")
            preview = raw_text[:50] + "..." if len(raw_text) > 50 else raw_text
            candidates_preview.append({
                "type": prof.get("address_type", "UNKNOWN"),
                "confidence": prof.get("address_classification", "UNKNOWN"),
                "preview": preview,
            })

        return {
            "status": "MULTIPLE",
            "count": distinct_count,
            "address_types": types,
            "evidence": evidence or ["multiple_distinct_address_blocks"],
            "distinctness_basis": distinctness_basis or ["structural_separation"],
            "candidates_preview": candidates_preview,
        }

    # Multiple candidates but none distinct => repeated address
    prof = groups[0]["profile"]
    raw_text = prof.get("address_raw_text", "")
    preview = raw_text[:50] + "..." if len(raw_text) > 50 else raw_text
    
    return {
        "status": "SINGLE",
        "count": 1,
        "address_types": types[:1],
        "evidence": ["repeated_address_blocks"],
        "candidates_preview": [{
            "type": prof.get("address_type", "UNKNOWN"),
            "confidence": prof.get("address_classification", "UNKNOWN"),
            "preview": preview,
        }],
    }


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
