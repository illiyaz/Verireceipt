"""
Geo inference module - infer country from receipt text using postal patterns, cities, and terms.
"""

import re
from typing import Dict, Any, List, Tuple
from .db import query_postal_patterns, query_cities, query_terms

def infer_geo(text: str) -> Dict[str, Any]:
    """
    Infer geographic origin from receipt text.
    
    Returns:
        {
            "geo_country_guess": "IN|US|DE|UK|CA|SG|AE|AU|UNKNOWN",
            "geo_confidence": 0.0-1.0,
            "geo_evidence": [
                {"type": "postal_match", "country": "IN", "match": "600001", "weight": 0.45},
                {"type": "city_match", "country": "IN", "match": "chennai", "weight": 0.25},
                {"type": "tax_term", "country": "IN", "match": "gstin", "weight": 0.20}
            ],
            "candidates": [{"country": "IN", "score": 0.90}, {"country": "DE", "score": 0.20}],
            "geo_mixed": False
        }
    """
    if not text:
        return _unknown_result()
    
    text_lower = text.lower()
    text_norm = re.sub(r'\s+', ' ', text_lower)
    
    # Initialize country scores
    country_scores: Dict[str, float] = {}
    evidence: List[Dict[str, Any]] = []
    
    # 1. Postal pattern matching
    _match_postal_patterns(text, country_scores, evidence)
    
    # 2. City matching
    _match_cities(text_norm, country_scores, evidence)
    
    # 3. Term matching (tax, currency, phone, address keywords)
    _match_terms(text_norm, country_scores, evidence)
    
    # 4. Strong country-specific regex patterns (GSTIN, PAN, EIN, etc.)
    _match_strong_patterns(text, country_scores, evidence)
    
    # 5. Apply caps and compute final scores
    _apply_caps(country_scores, evidence)
    
    # 6. Determine winner and confidence
    return _compute_result(country_scores, evidence)

def _match_postal_patterns(text: str, country_scores: Dict[str, float], evidence: List[Dict[str, Any]]):
    """Match postal patterns and update scores."""
    patterns = query_postal_patterns()
    
    for pattern_row in patterns:
        country = pattern_row["country_code"]
        pattern = pattern_row["pattern"]
        weight = pattern_row["weight"]
        
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            # Take first match for evidence
            match_str = matches[0] if isinstance(matches[0], str) else "".join(matches[0])
            
            country_scores[country] = country_scores.get(country, 0.0) + weight
            evidence.append({
                "type": "postal_match",
                "country": country,
                "match": match_str,
                "weight": weight
            })

def _match_cities(text_norm: str, country_scores: Dict[str, float], evidence: List[Dict[str, Any]]):
    """Match cities and update scores."""
    cities = query_cities()
    
    # Track matches per country to apply cap
    country_city_matches: Dict[str, List[Tuple[str, float]]] = {}
    
    for city_row in cities:
        country = city_row["country_code"]
        name_norm = city_row["name_norm"]
        display_name = city_row["display_name"]
        alt_names = city_row["alt_names"] or ""
        
        # Check main name
        if f" {name_norm} " in f" {text_norm} " or text_norm.startswith(name_norm) or text_norm.endswith(name_norm):
            if country not in country_city_matches:
                country_city_matches[country] = []
            country_city_matches[country].append((display_name, 0.25))
            continue
        
        # Check alt names
        if alt_names:
            for alt in alt_names.split(","):
                alt = alt.strip()
                if alt and (f" {alt} " in f" {text_norm} " or text_norm.startswith(alt) or text_norm.endswith(alt)):
                    if country not in country_city_matches:
                        country_city_matches[country] = []
                    country_city_matches[country].append((display_name, 0.25))
                    break
    
    # Apply city matches with cap of 0.35 per country
    for country, matches in country_city_matches.items():
        total_weight = min(sum(w for _, w in matches), 0.35)
        country_scores[country] = country_scores.get(country, 0.0) + total_weight
        
        # Add evidence for first match only
        if matches:
            evidence.append({
                "type": "city_match",
                "country": country,
                "match": matches[0][0],
                "weight": total_weight
            })

def _match_terms(text_norm: str, country_scores: Dict[str, float], evidence: List[Dict[str, Any]]):
    """Match terms (tax, currency, phone, address keywords) and update scores."""
    terms = query_terms()
    
    # Track matches per country and kind to apply caps
    country_kind_matches: Dict[str, Dict[str, List[Tuple[str, float]]]] = {}
    
    for term_row in terms:
        country = term_row["country_code"]
        kind = term_row["kind"]
        token_norm = term_row["token_norm"]
        weight = term_row["weight"]
        
        # Check if term appears in text with flexible matching
        # Use word boundary regex for better matching
        pattern = r'\b' + re.escape(token_norm) + r'\b'
        if re.search(pattern, text_norm, re.IGNORECASE):
            if country not in country_kind_matches:
                country_kind_matches[country] = {}
            if kind not in country_kind_matches[country]:
                country_kind_matches[country][kind] = []
            
            country_kind_matches[country][kind].append((token_norm, weight))
    
    # Apply term matches with cap of 0.35 per country (across all kinds)
    for country, kind_matches in country_kind_matches.items():
        total_weight = 0.0
        for kind, matches in kind_matches.items():
            kind_weight = sum(w for _, w in matches)
            total_weight += kind_weight
            
            # Add evidence for first match of each kind
            if matches:
                evidence.append({
                    "type": f"{kind}_term",
                    "country": country,
                    "match": matches[0][0],
                    "weight": matches[0][1]
                })
        
        # Cap total term contribution at 0.35
        capped_weight = min(total_weight, 0.35)
        country_scores[country] = country_scores.get(country, 0.0) + capped_weight

# Strong country-specific regex patterns (high confidence, unambiguous)
_STRONG_PATTERNS = [
    # Indian GSTIN: 15 chars — 2-digit state code + 10-char PAN + 1 entity + Z + 1 check
    # e.g. 36ACMPK4116D1ZV, 27AAPFU0939F1ZV
    {
        "country": "IN",
        "pattern": r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b",
        "weight": 0.45,
        "label": "gstin_pattern",
    },
    # Indian PAN: 10 chars — 5 letters + 4 digits + 1 letter (only boost if other India signal present)
    {
        "country": "IN",
        "pattern": r"\bPAN\s*:?\s*[A-Z]{5}\d{4}[A-Z]\b",
        "weight": 0.25,
        "label": "pan_with_label",
    },
    # Indian PIN code with optional space: "500 008", "110001", "PIN: 600001"
    {
        "country": "IN",
        "pattern": r"\b(?:pin\s*(?:code)?\s*:?\s*)?([1-9]\d{2})\s?(\d{3})\b",
        "weight": 0.15,
        "label": "in_pin_code",
        "validator": "_validate_indian_pin",
    },
    # Indian VAT TIN: "VAT TIN" is India-specific (other countries say "VAT No" or "TRN")
    {
        "country": "IN",
        "pattern": r"\bVAT\s+TIN\b",
        "weight": 0.30,
        "label": "vat_tin_india",
    },
]

# Valid Indian PIN code first-digit ranges (1-8, not 0 or 9)
_INDIAN_PIN_PREFIXES = {
    "11", "12", "13", "14", "15", "16", "17", "18", "19",
    "20", "21", "22", "23", "24", "25", "26", "27", "28",
    "30", "31", "32", "33", "34", "36", "37", "38", "39",
    "40", "41", "42", "43", "44", "45", "46", "47", "48", "49",
    "50", "51", "52", "53", "56", "57", "58", "59",
    "60", "61", "62", "63", "64", "67", "68", "69",
    "70", "71", "72", "73", "74", "75", "76", "77", "78", "79",
    "80", "81", "82", "83", "84", "85",
}


def _validate_indian_pin(match_str: str) -> bool:
    """Validate that a 6-digit number looks like a real Indian PIN code."""
    digits = re.sub(r"\s+", "", match_str)
    # Extract just the 6 digits
    m = re.search(r"(\d{6})", digits)
    if not m:
        # Try with space: "500 008"
        m2 = re.search(r"(\d{3})\s+(\d{3})", match_str)
        if m2:
            digits = m2.group(1) + m2.group(2)
        else:
            return False
    else:
        digits = m.group(1)
    return len(digits) == 6 and digits[:2] in _INDIAN_PIN_PREFIXES


def _match_strong_patterns(text: str, country_scores: Dict[str, float], evidence: List[Dict[str, Any]]):
    """Match strong country-specific regex patterns (GSTIN, PAN, VAT TIN, etc.)."""
    for spec in _STRONG_PATTERNS:
        matches = re.findall(spec["pattern"], text, re.IGNORECASE)
        if not matches:
            continue
        
        match_str = matches[0] if isinstance(matches[0], str) else "".join(matches[0])
        
        # Optional validator (e.g., Indian PIN code validation)
        if spec.get("validator") == "_validate_indian_pin":
            if not _validate_indian_pin(match_str):
                continue
        
        country_scores[spec["country"]] = country_scores.get(spec["country"], 0.0) + spec["weight"]
        evidence.append({
            "type": spec["label"],
            "country": spec["country"],
            "match": match_str[:30],  # Truncate for privacy
            "weight": spec["weight"]
        })


def _apply_caps(country_scores: Dict[str, float], evidence: List[Dict[str, Any]]):
    """Apply any additional caps or adjustments."""
    # Currently caps are applied during matching
    # This function is a placeholder for future adjustments
    pass

def _compute_result(country_scores: Dict[str, float], evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute final result with winner, confidence, and candidates."""
    if not country_scores:
        return _unknown_result()
    
    # Sort candidates by score
    candidates = [
        {"country": country, "score": round(score, 2)}
        for country, score in sorted(country_scores.items(), key=lambda x: x[1], reverse=True)
    ]
    
    top_score = candidates[0]["score"]
    top_country = candidates[0]["country"]
    second_score = candidates[1]["score"] if len(candidates) > 1 else 0.0
    
    # Check for mixed signals (multiple countries > 0.35 with close scores)
    high_scorers = [c for c in candidates if c["score"] > 0.35]
    geo_mixed = len(high_scorers) > 1 and (top_score - second_score) < 0.25
    
    # Compute confidence with improved formula
    # Base confidence from score gap and top score strength
    gap_confidence = (top_score - second_score) / max(top_score, 0.01)  # Normalized gap
    strength_bonus = min(0.30, top_score * 0.40)  # Bonus for strong signals
    confidence = min(1.0, max(0.0, gap_confidence * 0.70 + strength_bonus))
    
    # Reduce confidence if mixed signals
    if geo_mixed:
        confidence = max(0.0, confidence - 0.20)
    
    # If top score < 0.30 OR confidence < 0.30, mark as UNKNOWN
    if top_score < 0.30 or confidence < 0.30:
        return {
            "geo_country_guess": "UNKNOWN",
            "geo_confidence": 0.0,  # Zero out confidence for UNKNOWN
            "geo_confidence_raw": round(confidence, 2),  # Keep raw for debugging
            "geo_evidence": evidence,
            "candidates": candidates,
            "geo_mixed": geo_mixed
        }
    
    return {
        "geo_country_guess": top_country,
        "geo_confidence": round(confidence, 2),
        "geo_evidence": evidence,
        "candidates": candidates,
        "geo_mixed": geo_mixed
    }

def _unknown_result() -> Dict[str, Any]:
    """Return UNKNOWN result."""
    return {
        "geo_country_guess": "UNKNOWN",
        "geo_confidence": 0.0,  # Always 0.0 for UNKNOWN
        "geo_confidence_raw": 0.0,
        "geo_evidence": [],
        "candidates": [],
        "geo_mixed": False
    }
