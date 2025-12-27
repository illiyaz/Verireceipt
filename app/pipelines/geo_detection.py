"""
Geo-aware document classification system.

This module implements a multi-signal approach to detect:
1. Language (fast heuristic)
2. Country/region (multi-signal scoring)
3. Geo-specific document features

This enables accurate classification of receipts from different countries
without hardcoding assumptions about currency, tax systems, or formats.
"""

import re
from typing import Dict, Any, List, Tuple, Optional


# =============================================================================
# STEP 1: LANGUAGE DETECTION (Fast Heuristic)
# =============================================================================

# Common words by language (high-frequency, receipt-specific)
LANGUAGE_MARKERS = {
    "es": {  # Spanish (Mexico, Spain, Latin America)
        "keywords": [
            "total", "subtotal", "iva", "gracias", "fecha", "ticket", "sucursal",
            "cliente", "vendedor", "cajero", "pago", "cambio", "efectivo",
            "tarjeta", "compra", "venta", "factura", "recibo", "número",
            "dirección", "teléfono", "rfc", "cfdi", "sat", "folio",
        ],
        "patterns": [
            r"\b(gracias por su compra|muchas gracias)\b",
            r"\b(fecha|hora):\s*\d",
            r"\brfc\b",
        ],
    },
    "en": {  # English (US, Canada, UK, etc.)
        "keywords": [
            "total", "subtotal", "tax", "thank", "date", "receipt", "invoice",
            "customer", "cashier", "payment", "change", "cash", "card", "credit",
            "debit", "purchase", "sale", "number", "address", "phone", "zip",
            "state", "server", "table", "tip", "gratuity",
        ],
        "patterns": [
            r"\b(thank you|thanks)\b",
            r"\bsales tax\b",
            r"\bzip\s*code\b",
        ],
    },
    "hi": {  # Hindi/Indian English mix
        "keywords": [
            "total", "bill", "gstin", "cgst", "sgst", "igst", "invoice", "receipt",
            "customer", "date", "time", "payment", "cash", "card", "upi", "paytm",
            "phone", "mobile", "address", "pin", "hsn", "sac", "gst", "tax",
        ],
        "patterns": [
            r"\bgstin\b",
            r"\b(cgst|sgst|igst)\b",
            r"\bhsn\s*code\b",
        ],
    },
    "ar": {  # Arabic (UAE, Saudi, etc.)
        "keywords": [
            "total", "tax", "vat", "invoice", "receipt", "customer", "date",
            "payment", "cash", "card", "trn", "amount", "aed", "sar", "riyal",
        ],
        "patterns": [
            r"\btrn\b",  # Tax Registration Number (UAE)
            r"\bvat\s*\d+%",
        ],
    },
}


def _detect_language(text: str, sample_size: int = 1000) -> Dict[str, Any]:
    """
    Fast language detection using keyword frequency analysis.
    
    Args:
        text: Full text to analyze
        sample_size: Number of characters to sample (default 1000)
    
    Returns:
        {
            "lang_guess": "es" | "en" | "hi" | "ar" | "unknown",
            "lang_confidence": 0.0 - 1.0,
            "lang_evidence": ["matched_keyword1", "matched_keyword2", ...]
        }
    """
    if not text or len(text.strip()) < 50:
        return {
            "lang_guess": "unknown",
            "lang_confidence": 0.0,
            "lang_evidence": [],
        }
    
    # Sample first N chars (receipts usually have key info at top)
    sample = text[:sample_size].lower()
    
    # Score each language
    scores = {}
    evidence = {}
    
    for lang, markers in LANGUAGE_MARKERS.items():
        score = 0
        matched = []
        
        # Keyword matching (1 point each)
        for keyword in markers["keywords"]:
            if keyword in sample:
                score += 1
                matched.append(keyword)
        
        # Pattern matching (3 points each - more reliable)
        for pattern in markers["patterns"]:
            if re.search(pattern, sample, re.IGNORECASE):
                score += 3
                matched.append(f"pattern:{pattern[:20]}")
        
        scores[lang] = score
        evidence[lang] = matched
    
    # Pick winner
    if not scores or max(scores.values()) == 0:
        return {
            "lang_guess": "unknown",
            "lang_confidence": 0.0,
            "lang_evidence": [],
        }
    
    winner = max(scores, key=scores.get)
    winner_score = scores[winner]
    total_score = sum(scores.values())
    
    # Confidence = winner_score / total_score (normalized)
    confidence = min(1.0, winner_score / max(10, total_score))
    
    return {
        "lang_guess": winner,
        "lang_confidence": round(confidence, 2),
        "lang_evidence": evidence[winner][:5],  # Top 5 matches
    }


# =============================================================================
# STEP 2: GEO/COUNTRY DETECTION (Multi-Signal Scoring)
# =============================================================================

# Signal definitions for each country
GEO_SIGNALS = {
    "MX": {  # Mexico
        "currency": ["mxn", "$", "pesos", "peso"],
        "tax_keywords": ["rfc", "iva", "cfdi", "sat", "folio fiscal"],
        "phone_patterns": [
            r"\+52[\s\-]?\d{10}",  # +52 followed by 10 digits
            r"\b\d{10}\b",  # 10 digits (ambiguous)
        ],
        "postal_patterns": [
            r"\bC\.?P\.?\s*\d{5}\b",  # C.P. 12345
            r"\b\d{5}\b",  # 5 digits (ambiguous with US ZIP)
        ],
        "location_markers": [
            "cdmx", "guadalajara", "monterrey", "puebla", "tijuana",
            "col.", "colonia", "delegación", "municipio",
        ],
        "language_hint": "es",  # Expected language
    },
    "US": {  # United States
        "currency": ["usd", "$", "dollar"],
        "tax_keywords": ["sales tax", "state tax", "tax rate", "subtotal"],
        "phone_patterns": [
            r"\(\d{3}\)\s*\d{3}[-\s]?\d{4}",  # (555) 123-4567
            r"\d{3}[-\s]\d{3}[-\s]\d{4}",  # 555-123-4567
        ],
        "postal_patterns": [
            r"\b\d{5}(-\d{4})?\b",  # ZIP or ZIP+4
            r"\b[A-Z]{2}\s+\d{5}\b",  # State + ZIP
        ],
        "location_markers": [
            "ca", "tx", "ny", "fl", "il", "pa", "oh", "ga", "nc", "mi",
            "zip", "state", "city", "county",
        ],
        "language_hint": "en",
    },
    "IN": {  # India
        "currency": ["inr", "₹", "rs", "rupees", "rupee"],
        "tax_keywords": ["gstin", "gst", "cgst", "sgst", "igst", "hsn", "sac"],
        "phone_patterns": [
            r"\+91[\s\-]?\d{10}",  # +91 followed by 10 digits
            r"\b[6-9]\d{9}\b",  # Mobile: starts with 6-9, 10 digits
        ],
        "postal_patterns": [
            r"\bpin\s*code?\s*:?\s*\d{6}\b",  # PIN Code: 123456
            r"\b\d{6}\b",  # 6 digits
        ],
        "location_markers": [
            "mumbai", "delhi", "bangalore", "hyderabad", "chennai", "kolkata",
            "pune", "ahmedabad", "nagar", "road", "street",
        ],
        "language_hint": "hi",
    },
    "CA": {  # Canada
        "currency": ["cad", "$", "dollar"],
        "tax_keywords": ["gst", "hst", "pst", "qst", "tax"],
        "phone_patterns": [
            r"\+1[\s\-]?\d{3}[\s\-]?\d{3}[\s\-]?\d{4}",
            r"\(\d{3}\)\s*\d{3}[-\s]?\d{4}",
        ],
        "postal_patterns": [
            r"\b[A-Z]\d[A-Z]\s*\d[A-Z]\d\b",  # A1A 1A1
        ],
        "location_markers": [
            "toronto", "vancouver", "montreal", "calgary", "ottawa",
            "on", "bc", "qc", "ab", "province",
        ],
        "language_hint": "en",
    },
    "AE": {  # UAE
        "currency": ["aed", "dhs", "dirham"],
        "tax_keywords": ["vat", "trn", "tax registration"],
        "phone_patterns": [
            r"\+971[\s\-]?\d{8,9}",
            r"\b0\d{8,9}\b",
        ],
        "postal_patterns": [],  # UAE doesn't use postal codes widely
        "location_markers": [
            "dubai", "abu dhabi", "sharjah", "ajman", "uae", "emirates",
        ],
        "language_hint": "ar",
    },
}


def _score_geo_signal(text: str, signal_type: str, patterns: List[str]) -> Tuple[int, List[str]]:
    """Score a specific signal type and return (score, evidence)."""
    score = 0
    evidence = []
    text_lower = text.lower()
    
    if signal_type == "currency":
        for curr in patterns:
            if curr in text_lower:
                score += 2
                evidence.append(f"currency:{curr}")
    
    elif signal_type == "tax_keywords":
        for keyword in patterns:
            if keyword in text_lower:
                score += 3  # Tax keywords are strong signals
                evidence.append(f"tax:{keyword}")
    
    elif signal_type == "phone_patterns":
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                score += 2
                evidence.append(f"phone:{matches[0][:15]}")
    
    elif signal_type == "postal_patterns":
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                score += 2
                evidence.append(f"postal:{matches[0]}")
    
    elif signal_type == "location_markers":
        for marker in patterns:
            if marker in text_lower:
                score += 1
                evidence.append(f"location:{marker}")
    
    return score, evidence


def _detect_geo_country(text: str, lang_hint: Optional[str] = None) -> Dict[str, Any]:
    """
    Multi-signal country/region detection.
    
    Args:
        text: Full text to analyze
        lang_hint: Optional language hint from language detection
    
    Returns:
        {
            "geo_country_guess": "MX" | "US" | "IN" | "CA" | "AE" | "UNKNOWN",
            "geo_confidence": 0.0 - 1.0,
            "geo_evidence": ["signal1", "signal2", ...],
            "geo_scores": {"MX": 10, "US": 5, ...}  # For debugging
        }
    """
    if not text or len(text.strip()) < 50:
        return {
            "geo_country_guess": "UNKNOWN",
            "geo_confidence": 0.0,
            "geo_evidence": [],
            "geo_scores": {},
        }
    
    country_scores = {}
    country_evidence = {}
    
    for country, signals in GEO_SIGNALS.items():
        total_score = 0
        all_evidence = []
        
        # Score each signal type
        for signal_type in ["currency", "tax_keywords", "phone_patterns", "postal_patterns", "location_markers"]:
            if signal_type in signals:
                score, evidence = _score_geo_signal(text, signal_type, signals[signal_type])
                total_score += score
                all_evidence.extend(evidence)
        
        # Language hint bonus (if matches expected language)
        if lang_hint and signals.get("language_hint") == lang_hint:
            total_score += 5
            all_evidence.append(f"lang_match:{lang_hint}")
        
        country_scores[country] = total_score
        country_evidence[country] = all_evidence
    
    # Pick winner
    if not country_scores or max(country_scores.values()) == 0:
        return {
            "geo_country_guess": "UNKNOWN",
            "geo_confidence": 0.0,
            "geo_evidence": [],
            "geo_scores": country_scores,
        }
    
    winner = max(country_scores, key=country_scores.get)
    winner_score = country_scores[winner]
    total_score = sum(country_scores.values())
    
    # Confidence calculation
    # High confidence if winner is clearly ahead
    if total_score > 0:
        confidence = min(1.0, winner_score / max(10, total_score))
    else:
        confidence = 0.0
    
    # Boost confidence if winner has strong signals
    if winner_score >= 10:
        confidence = min(1.0, confidence + 0.2)
    
    return {
        "geo_country_guess": winner,
        "geo_confidence": round(confidence, 2),
        "geo_evidence": country_evidence[winner][:10],  # Top 10 signals
        "geo_scores": country_scores,
    }


# =============================================================================
# STEP 3: GEO-AWARE DOCUMENT SUBTYPE DETECTION
# =============================================================================

# Geo-specific keywords for document subtypes
GEO_SUBTYPE_KEYWORDS = {
    "MX": {
        "POS_RESTAURANT": ["restaurante", "mesero", "propina", "mesa", "comida", "bebida"],
        "POS_RETAIL": ["tienda", "almacén", "venta", "artículo"],
        "TAX_INVOICE": ["factura", "rfc", "cfdi", "folio fiscal", "sat"],
        "ECOMMERCE": ["pedido", "envío", "rastreo", "paquete"],
        "FUEL": ["gasolina", "diesel", "combustible", "litros"],
        "PARKING": ["estacionamiento", "boleto"],
    },
    "US": {
        "POS_RESTAURANT": ["restaurant", "server", "tip", "gratuity", "table", "dine"],
        "POS_RETAIL": ["store", "retail", "merchandise", "item"],
        "TAX_INVOICE": ["invoice", "tax id", "ein", "bill to"],
        "ECOMMERCE": ["order", "shipping", "tracking", "package"],
        "FUEL": ["gas", "fuel", "gallons", "pump"],
        "PARKING": ["parking", "ticket", "meter"],
        "HOTEL_FOLIO": ["hotel", "room", "night", "check-in", "check-out", "folio"],
    },
    "IN": {
        "POS_RESTAURANT": ["restaurant", "hotel", "bill", "waiter", "table"],
        "POS_RETAIL": ["shop", "store", "retail", "item"],
        "TAX_INVOICE": ["tax invoice", "gstin", "hsn", "sac", "bill of supply"],
        "ECOMMERCE": ["order", "delivery", "tracking", "awb"],
        "FUEL": ["petrol", "diesel", "fuel", "litres"],
        "UTILITY": ["electricity", "water", "gas", "bill", "consumer"],
        "TELECOM": ["mobile", "recharge", "plan", "data"],
    },
}


def _detect_doc_subtype_geo_aware(
    text: str,
    lines: List[str],
    geo_country: str,
    geo_confidence: float
) -> Dict[str, Any]:
    """
    Detect document subtype using geo-specific keywords.
    
    Args:
        text: Full normalized text
        lines: Text split into lines
        geo_country: Detected country code (MX, US, IN, etc.)
        geo_confidence: Confidence in geo detection
    
    Returns:
        {
            "doc_family_guess": "TRANSACTIONAL" | "LOGISTICS" | "PAYMENT",
            "doc_subtype_guess": str,
            "doc_profile_confidence": 0.0 - 1.0,
            "doc_profile_evidence": [...]
        }
    """
    text_lower = text.lower()
    
    # Get geo-specific keywords (fallback to US if unknown)
    geo_keywords = GEO_SUBTYPE_KEYWORDS.get(geo_country, GEO_SUBTYPE_KEYWORDS.get("US", {}))
    
    # Score each subtype
    subtype_scores = {}
    subtype_evidence = {}
    
    for subtype, keywords in geo_keywords.items():
        score = 0
        evidence = []
        
        for keyword in keywords:
            if keyword in text_lower:
                score += 1
                evidence.append(keyword)
        
        subtype_scores[subtype] = score
        subtype_evidence[subtype] = evidence
    
    # Pick winner
    if not subtype_scores or max(subtype_scores.values()) == 0:
        # Fallback to generic detection
        return {
            "doc_family_guess": "TRANSACTIONAL",
            "doc_subtype_guess": "MISC",
            "doc_profile_confidence": 0.3,
            "doc_profile_evidence": [],
        }
    
    winner = max(subtype_scores, key=subtype_scores.get)
    winner_score = subtype_scores[winner]
    
    # Determine family from subtype
    if winner.startswith("POS_") or winner in ["TAX_INVOICE", "ECOMMERCE", "FUEL", "PARKING", "HOTEL_FOLIO", "UTILITY", "TELECOM"]:
        family = "TRANSACTIONAL"
    elif winner in ["SHIPPING_BILL", "BILL_OF_LADING", "AIR_WAYBILL", "DELIVERY_NOTE"]:
        family = "LOGISTICS"
    else:
        family = "PAYMENT"
    
    # Confidence = (winner_score / 5) * geo_confidence
    # If we have 3+ keyword matches and high geo confidence, we're confident
    base_confidence = min(1.0, winner_score / 5.0)
    final_confidence = base_confidence * (0.5 + 0.5 * geo_confidence)
    
    return {
        "doc_family_guess": family,
        "doc_subtype_guess": winner,
        "doc_profile_confidence": round(final_confidence, 2),
        "doc_profile_evidence": subtype_evidence[winner][:5],
    }


# =============================================================================
# STEP 4: COUNTRY-SPECIFIC EXTRACTORS
# =============================================================================

def extract_mx_specific(text: str) -> Dict[str, Any]:
    """Extract Mexico-specific fields (RFC, IVA, CP, etc.)."""
    features = {}
    
    # RFC (Registro Federal de Contribuyentes)
    # Format: 12-13 alphanumeric characters
    rfc_pattern = r'\b[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}\b'
    rfc_match = re.search(rfc_pattern, text, re.IGNORECASE)
    if rfc_match:
        features["mx_rfc"] = rfc_match.group(0)
    
    # IVA (tax rate, usually 16%)
    iva_pattern = r'iva\s*:?\s*(\d+(?:\.\d+)?)\s*%?'
    iva_match = re.search(iva_pattern, text, re.IGNORECASE)
    if iva_match:
        features["mx_iva_rate"] = float(iva_match.group(1))
    
    # Código Postal (C.P.)
    cp_pattern = r'C\.?P\.?\s*(\d{5})'
    cp_match = re.search(cp_pattern, text, re.IGNORECASE)
    if cp_match:
        features["mx_postal_code"] = cp_match.group(1)
    
    # Phone (Mexico format)
    phone_pattern = r'\+?52[\s\-]?(\d{10})'
    phone_match = re.search(phone_pattern, text)
    if phone_match:
        features["mx_phone"] = phone_match.group(1)
    
    return features


def extract_us_specific(text: str) -> Dict[str, Any]:
    """Extract US-specific fields (ZIP, State, EIN, etc.)."""
    features = {}
    
    # ZIP Code
    zip_pattern = r'\b(\d{5}(?:-\d{4})?)\b'
    zip_matches = re.findall(zip_pattern, text)
    if zip_matches:
        features["us_zip_code"] = zip_matches[0]
    
    # State abbreviation (before ZIP)
    state_pattern = r'\b([A-Z]{2})\s+\d{5}\b'
    state_match = re.search(state_pattern, text)
    if state_match:
        features["us_state"] = state_match.group(1)
    
    # EIN (Employer Identification Number)
    ein_pattern = r'\b\d{2}-\d{7}\b'
    ein_match = re.search(ein_pattern, text)
    if ein_match:
        features["us_ein"] = ein_match.group(0)
    
    # Phone (US format)
    phone_pattern = r'\((\d{3})\)\s*(\d{3})[-\s]?(\d{4})'
    phone_match = re.search(phone_pattern, text)
    if phone_match:
        features["us_phone"] = f"({phone_match.group(1)}) {phone_match.group(2)}-{phone_match.group(3)}"
    
    return features


def extract_in_specific(text: str) -> Dict[str, Any]:
    """Extract India-specific fields (GSTIN, PIN, HSN, etc.)."""
    features = {}
    
    # GSTIN (15 characters)
    gstin_pattern = r'\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b'
    gstin_match = re.search(gstin_pattern, text, re.IGNORECASE)
    if gstin_match:
        features["in_gstin"] = gstin_match.group(0)
    
    # PIN Code
    pin_pattern = r'\bpin\s*code?\s*:?\s*(\d{6})\b'
    pin_match = re.search(pin_pattern, text, re.IGNORECASE)
    if pin_match:
        features["in_pin_code"] = pin_match.group(1)
    
    # HSN Code
    hsn_pattern = r'\bhsn\s*code?\s*:?\s*(\d{4,8})\b'
    hsn_match = re.search(hsn_pattern, text, re.IGNORECASE)
    if hsn_match:
        features["in_hsn_code"] = hsn_match.group(1)
    
    # Phone (India format)
    phone_pattern = r'\+?91[\s\-]?([6-9]\d{9})'
    phone_match = re.search(phone_pattern, text)
    if phone_match:
        features["in_phone"] = phone_match.group(1)
    
    return features


def extract_geo_specific_features(text: str, geo_country: str) -> Dict[str, Any]:
    """
    Run country-specific extractors based on detected geo.
    
    Args:
        text: Full text
        geo_country: Detected country code
    
    Returns:
        Dict with geo-specific extracted fields
    """
    if geo_country == "MX":
        return extract_mx_specific(text)
    elif geo_country == "US":
        return extract_us_specific(text)
    elif geo_country == "IN":
        return extract_in_specific(text)
    elif geo_country == "CA":
        # Canada is similar to US for now
        return extract_us_specific(text)
    else:
        # Generic fallback
        return {}


# =============================================================================
# PUBLIC API
# =============================================================================

def detect_geo_and_profile(text: str, lines: List[str]) -> Dict[str, Any]:
    """
    Main entry point for geo-aware document classification.
    
    This runs all 4 steps:
    1. Language detection
    2. Country/region detection
    3. Geo-aware document subtype detection
    4. Country-specific feature extraction
    
    Args:
        text: Full normalized text
        lines: Text split into lines
    
    Returns:
        Combined dict with all detection results
    """
    # Step 1: Detect language
    lang_result = _detect_language(text)
    
    # Step 2: Detect country/region
    geo_result = _detect_geo_country(text, lang_hint=lang_result["lang_guess"])
    
    # Step 3: Detect document subtype (geo-aware)
    doc_result = _detect_doc_subtype_geo_aware(
        text,
        lines,
        geo_result["geo_country_guess"],
        geo_result["geo_confidence"]
    )
    
    # Step 4: Extract geo-specific features
    geo_features = extract_geo_specific_features(text, geo_result["geo_country_guess"])
    
    # Combine all results
    return {
        **lang_result,
        **geo_result,
        **doc_result,
        "geo_specific_features": geo_features,
    }
