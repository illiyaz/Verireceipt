"""
Geo-aware document classification system.

This module implements a multi-signal approach to detect:
1. Language (fast heuristic)
2. Country/region (enriched geo inference with postal patterns, cities, terms)
3. Geo-specific document features

Uses the new geo enrichment system (app/geo) for accurate location detection.
"""

import re
from typing import Dict, Any, List, Tuple, Optional
from app.geo import infer_geo


_lang_loader = None
_lang_script_detector = None
_lang_router = None
_lang_normalizer = None


def _get_lang_components():
    global _lang_loader, _lang_script_detector, _lang_router, _lang_normalizer

    if _lang_loader is None:
        from app.pipelines.lang import LangPackLoader, ScriptDetector, LangPackRouter, TextNormalizer

        _lang_loader = LangPackLoader(strict=True)
        _lang_loader.load_all()
        _lang_script_detector = ScriptDetector()
        _lang_router = LangPackRouter(_lang_loader, _lang_script_detector)
        _lang_normalizer = TextNormalizer()

    return _lang_loader, _lang_router, _lang_normalizer


# =============================================================================
# STEP 1: LANGUAGE DETECTION (Fast Heuristic)
# =============================================================================

# Common words by language (high-frequency, receipt-specific)
LANGUAGE_MARKERS = {
    "zh": {  # Chinese (Simplified/Traditional)
        "keywords": [
            "total", "receipt", "invoice", "tax", "vat",  # English fallback
            "rmb", "cny", "yuan", "hkd", "sgd",  # Currency
        ],
        "patterns": [
            r"[\u4e00-\u9fff]{2,}",  # Chinese characters (2+ chars)
            r"总计|小计|合计|发票|收据|税|增值税",  # Total, subtotal, invoice, receipt, tax, VAT
            r"人民币|港币|新币",  # RMB, HKD, SGD
            r"¥\d+",  # Yuan symbol
        ],
    },
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
    "ar": {  # Arabic (UAE, Saudi, etc.) - includes Arabic script
        "keywords": [
            "total", "tax", "vat", "invoice", "receipt", "customer", "date",
            "payment", "cash", "card", "trn", "amount", "aed", "sar", "riyal",
        ],
        "patterns": [
            r"[\u0600-\u06ff]{3,}",  # Arabic script (3+ chars)
            r"\btrn\b",  # Tax Registration Number (UAE)
            r"\bvat\s*\d+%",
            r"ريال|درهم",  # Riyal, Dirham in Arabic
        ],
    },
    "fr": {  # French (France, Canada, Africa)
        "keywords": [
            "total", "sous-total", "tva", "merci", "date", "ticket", "reçu",
            "client", "caisse", "paiement", "espèces", "carte", "facture",
            "montant", "taxe", "numéro", "adresse", "téléphone",
        ],
        "patterns": [
            r"\b(merci|merci beaucoup)\b",
            r"\btva\s*\d+%",
            r"\b(sous-total|sous total)\b",
        ],
    },
    "de": {  # German (Germany, Austria, Switzerland)
        "keywords": [
            "gesamt", "summe", "mwst", "danke", "datum", "rechnung", "beleg",
            "kunde", "kasse", "zahlung", "bargeld", "karte", "betrag",
            "steuer", "nummer", "adresse", "telefon",
        ],
        "patterns": [
            r"\b(danke|vielen dank)\b",
            r"\bmwst\s*\d+%",
            r"\bgesamt\b",
        ],
    },
    "pt": {  # Portuguese (Brazil, Portugal)
        "keywords": [
            "total", "subtotal", "imposto", "obrigado", "data", "recibo", "nota",
            "cliente", "caixa", "pagamento", "dinheiro", "cartão", "compra",
            "valor", "número", "endereço", "telefone", "cnpj", "cpf",
        ],
        "patterns": [
            r"\b(obrigado|muito obrigado)\b",
            r"\bcnpj\b",
            r"\bnota fiscal\b",
        ],
    },
    "ja": {  # Japanese
        "keywords": [
            "total", "receipt", "tax", "yen", "jpy",
        ],
        "patterns": [
            r"[\u3040-\u309f\u30a0-\u30ff]{2,}",  # Hiragana/Katakana
            r"[\u4e00-\u9fff]{2,}",  # Kanji
            r"合計|小計|領収書|税|消費税",  # Total, subtotal, receipt, tax
            r"¥\d+|円",  # Yen
        ],
    },
    "th": {  # Thai
        "keywords": [
            "total", "receipt", "tax", "vat", "baht", "thb",
        ],
        "patterns": [
            r"[\u0e00-\u0e7f]{3,}",  # Thai script
            r"\bvat\s*\d+%",
            r"บาท",  # Baht
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

# Ambiguous signals that match multiple countries (scored lower)
AMBIGUOUS_SIGNALS = {
    "currency": {"$", "¥"},  # USD, MXN, CAD, SGD, HKD, AUD / CNY, JPY
    "postal": {r"\b\d{5}\b"},  # US ZIP, MX C.P., FR/DE/TH
    # NOTE: \b\d{6}\b removed - no longer used for any country (too ambiguous)
    "phone": {r"\b\d{10}\b"},  # MX, US (without formatting)
}

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
            r"\b\d{5}-\d{4}\b",      # ZIP+4 (strong)
            r"\b[A-Z]{2}\s+\d{5}\b", # State + ZIP (strong)
            r"\b\d{5}\b",            # 5 digits (ambiguous; gated)
        ],
        "location_markers": [
            "zip", "zip code", "state", "city", "county",
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
            r"\bpin\s*code?\s*:?\s*\d{6}\b",  # PIN Code: 123456 (contextual only)
            # NOTE: Standalone \b\d{6}\b removed - too ambiguous (overlaps CN, SG, etc.)
        ],
        "location_markers": [
            "mumbai", "delhi", "bangalore", "hyderabad", "chennai", "kolkata",
            "pune", "ahmedabad",
            # NOTE: Removed "nagar", "road", "street" - too generic/ambiguous
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
    "SA": {  # Saudi Arabia
        "currency": ["sar", "riyal", "riyals"],
        "tax_keywords": ["vat", "tax", "ضريبة"],  # Tax in Arabic
        "phone_patterns": [
            r"\+966[\s\-]?\d{9}",
            r"\b0\d{9}\b",
        ],
        "postal_patterns": [
            r"\b\d{5}(-\d{4})?\b",  # Saudi postal code
        ],
        "location_markers": [
            "riyadh", "jeddah", "mecca", "medina", "dammam", "ksa", "saudi",
        ],
        "language_hint": "ar",
    },
    "CN": {  # China
        "currency": ["cny", "rmb", "yuan", "¥"],
        "tax_keywords": ["vat", "tax", "增值税", "税"],  # VAT, Tax in Chinese
        "phone_patterns": [
            r"\+86[\s\-]?1[3-9]\d{9}",  # +86 mobile
            r"\b1[3-9]\d{9}\b",  # Mobile without country code
        ],
        "postal_patterns": [
            r"\b\d{6}\b",  # 6-digit postal code
        ],
        "location_markers": [
            "beijing", "shanghai", "guangzhou", "shenzhen", "chengdu",
            "北京", "上海", "广州", "深圳",  # Cities in Chinese
        ],
        "language_hint": "zh",
    },
    "HK": {  # Hong Kong
        "currency": ["hkd", "hk$", "dollar"],
        "tax_keywords": [],  # Hong Kong has no VAT/GST
        "phone_patterns": [
            r"\+852[\s\-]?\d{8}",
            r"\b[2-9]\d{7}\b",
        ],
        "postal_patterns": [],  # Hong Kong doesn't use postal codes
        "location_markers": [
            "hong kong", "kowloon", "tsim sha tsui", "central", "causeway bay",
            "香港", "九龍",  # Hong Kong, Kowloon in Chinese
        ],
        "language_hint": "zh",
    },
    "SG": {  # Singapore
        "currency": ["sgd", "s$", "dollar"],
        "tax_keywords": ["gst", "tax"],
        "phone_patterns": [
            r"\+65[\s\-]?[689]\d{7}",
            r"\b[689]\d{7}\b",
        ],
        "postal_patterns": [
            r"\b\d{6}\b",  # 6-digit postal code
        ],
        "location_markers": [
            "singapore", "orchard", "marina bay", "sentosa", "changi",
        ],
        "language_hint": "en",
    },
    "FR": {  # France
        "currency": ["eur", "€", "euro"],
        "tax_keywords": ["tva", "taxe"],
        "phone_patterns": [
            r"\+33[\s\-]?[1-9]\d{8}",
            r"\b0[1-9]\d{8}\b",
        ],
        "postal_patterns": [
            r"\b\d{5}\b",  # 5-digit postal code
        ],
        "location_markers": [
            "paris", "lyon", "marseille", "toulouse", "nice", "france",
        ],
        "language_hint": "fr",
    },
    "DE": {  # Germany
        "currency": ["eur", "€", "euro"],
        "tax_keywords": ["mwst", "steuer", "ust"],
        "phone_patterns": [
            r"\+49[\s\-]?\d{10,11}",
            r"\b0\d{9,10}\b",
        ],
        "postal_patterns": [
            r"\b\d{5}\b",  # 5-digit postal code
        ],
        "location_markers": [
            "berlin", "munich", "hamburg", "frankfurt", "cologne", "deutschland",
        ],
        "language_hint": "de",
    },
    "BR": {  # Brazil
        "currency": ["brl", "r$", "real", "reais"],
        "tax_keywords": ["icms", "nota fiscal", "cnpj", "cpf"],
        "phone_patterns": [
            r"\+55[\s\-]?\d{10,11}",
            r"\b\d{10,11}\b",
        ],
        "postal_patterns": [
            r"\b\d{5}-\d{3}\b",  # CEP format: 12345-678
        ],
        "location_markers": [
            "são paulo", "rio", "brasília", "salvador", "fortaleza", "brasil",
        ],
        "language_hint": "pt",
    },
    "JP": {  # Japan
        "currency": ["jpy", "¥", "yen", "円"],
        "tax_keywords": ["tax", "消費税", "税"],  # Consumption tax in Japanese
        "phone_patterns": [
            r"\+81[\s\-]?\d{9,10}",
            r"\b0\d{9,10}\b",
        ],
        "postal_patterns": [
            r"\b\d{3}-\d{4}\b",  # Japanese postal code: 123-4567
        ],
        "location_markers": [
            "tokyo", "osaka", "kyoto", "yokohama", "nagoya",
            "東京", "大阪", "京都",  # Cities in Japanese
        ],
        "language_hint": "ja",
    },
    "TH": {  # Thailand
        "currency": ["thb", "baht", "฿"],
        "tax_keywords": ["vat", "tax"],
        "phone_patterns": [
            r"\+66[\s\-]?[689]\d{8}",
            r"\b0[689]\d{8}\b",
        ],
        "postal_patterns": [
            r"\b\d{5}\b",  # 5-digit postal code
        ],
        "location_markers": [
            "bangkok", "phuket", "chiang mai", "pattaya", "thailand",
        ],
        "language_hint": "th",
    },
}


def _score_geo_signal(text: str, signal_type: str, patterns: List[str], has_strong_signal: bool = False) -> Tuple[int, List[str]]:
    """Score a specific signal type and return (score, evidence).
    
    Args:
        text: Text to search
        signal_type: Type of signal (currency, tax_keywords, etc.)
        patterns: List of patterns to match
        has_strong_signal: Whether a strong signal (tax/phone) already exists
    
    Returns:
        (score, evidence_list)
    """
    score = 0
    evidence = []
    text_raw_lower = (text or "").lower()
    text_lower = text_raw_lower

    routed_packs = []
    routed_script = None
    routed_confidence = 0.0
    normalizer = None
    try:
        _, router, normalizer = _get_lang_components()
        routing = router.route_document(text or "", allow_multi_pack=True)
        routed_packs = routing.all_packs
        routed_script = routing.script
        routed_confidence = float(routing.confidence or 0.0)
        if normalizer and routed_script:
            text_lower = normalizer.normalize_text(text or "", routed_script).lower()
    except Exception:
        routed_packs = []
        routed_script = None
        routed_confidence = 0.0
        normalizer = None
    
    if signal_type == "currency":
        for pattern in patterns:
            if pattern in text_lower:
                # Check if ambiguous
                is_ambiguous = pattern in AMBIGUOUS_SIGNALS.get("currency", set())
                if is_ambiguous:
                    # Only score ambiguous currency if we have strong signals
                    if has_strong_signal:
                        score += 1
                        evidence.append(f"currency:{pattern}(ambiguous)")
                else:
                    score += 2
                    evidence.append(f"currency:{pattern}")
                break  # Only count once per type
    
    elif signal_type == "tax_keywords":
        for pattern in patterns:
            if pattern in text_lower:
                score += 3  # Tax keywords are strong signals
                evidence.append(f"tax:{pattern}")
    
    elif signal_type in ["phone_patterns", "postal_patterns"]:
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                # Check if ambiguous
                signal_key = "phone" if signal_type == "phone_patterns" else "postal"
                is_ambiguous = pattern in AMBIGUOUS_SIGNALS.get(signal_key, set())
                
                if is_ambiguous:
                    # Only score ambiguous patterns if we have strong signals
                    if has_strong_signal:
                        score += 1
                        evidence.append(f"{signal_key}:{pattern[:20]}(ambiguous)")
                else:
                    score += 2
                    evidence.append(f"{signal_key}:{pattern[:20]}")
                break  # Only count once per type
    
    elif signal_type == "location_markers":
        for pattern in patterns:
            if pattern in text_lower:
                score += 1
                evidence.append(f"location:{pattern}")
    
    return score, evidence


def _detect_geo_country(
    text: str,
    lang_hint: Optional[str] = None,
    lang_confidence: Optional[float] = None,
    lang_score: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Multi-signal country/region detection.
    
    Args:
        text: Full text to analyze
        lang_hint: Optional language hint from language detection
        lang_confidence: Optional language confidence score (0.0-1.0)
        lang_score: Optional raw language score from detector
    
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
    
    # FIRST PASS: Check for strong signals (tax keywords, formatted phone/postal)
    strong_signals_by_country = {}
    for country, signals in GEO_SIGNALS.items():
        has_strong = False
        # Tax keywords are always strong
        if "tax_keywords" in signals:
            for pattern in signals["tax_keywords"]:
                if pattern in text.lower():
                    has_strong = True
                    break
        # Formatted phone/postal (non-ambiguous patterns)
        if not has_strong and "phone_patterns" in signals:
            for pattern in signals["phone_patterns"]:
                if pattern not in AMBIGUOUS_SIGNALS.get("phone", set()):
                    if re.search(pattern, text, re.IGNORECASE):
                        has_strong = True
                        break
        strong_signals_by_country[country] = has_strong
    
    # SECOND PASS: Score with ambiguous signal awareness
    for country, signals in GEO_SIGNALS.items():
        total_score = 0
        all_evidence = []
        has_strong = strong_signals_by_country[country]
        
        # Score each signal type
        for signal_type in ["currency", "tax_keywords", "phone_patterns", "postal_patterns", "location_markers"]:
            if signal_type in signals:
                score, evidence = _score_geo_signal(text, signal_type, signals[signal_type], has_strong)
                total_score += score
                all_evidence.extend(evidence)
        
        # Language hint bonus (proportional, not absolute)
        # Language is a prior, not ground truth. Keep it capped and proportional to language strength.
        if lang_hint and signals.get("language_hint") == lang_hint:
            # Prefer an explicit language score if provided; else derive from confidence.
            # - lang_score: raw-ish score from language detector (e.g., keyword/pattern points)
            # - lang_confidence: [0,1] confidence from language detector
            ls = None
            try:
                if lang_score is not None:
                    ls = float(lang_score)
                elif lang_confidence is not None:
                    # Map confidence to an approximate score range; keeps bonus proportional.
                    ls = float(lang_confidence) * 10.0
            except Exception:
                ls = None

            # Proportional bonus (cap at 3). If we don't know language strength, apply a tiny nudge (<= 1).
            if ls is None:
                lang_bonus = 1.0
            else:
                lang_bonus = min(3.0, ls * 0.30)

            total_score += lang_bonus
            all_evidence.append(f"lang_match:{lang_hint}(+{lang_bonus:.2f})")
        
        country_scores[country] = total_score
        country_evidence[country] = all_evidence
    
    # Pick winner
    if not country_scores or max(country_scores.values()) == 0:
        return {
            "geo_country_guess": "UNKNOWN",
            "geo_confidence": 0.0,
            "geo_evidence": [],
            "geo_scores": country_scores,
            "geo_suspicious": False,
            "geo_winner_raw": None,
            "geo_winner_score_raw": 0,
        }

    winner = max(country_scores, key=country_scores.get)
    winner_score = country_scores[winner]
    total_score = sum(country_scores.values()) or 1.0

    # Confidence calculation with minimum score gate
    confidence = min(1.0, winner_score / max(10, total_score))

    # Minimum absolute score gate: penalize weak signals
    if winner_score < 6:
        confidence *= 0.5  # Cut confidence in half for weak signals

    # Boost confidence if winner has strong signals (>= 10)
    if winner_score >= 10:
        confidence = min(1.0, confidence + 0.2)

    # Fix #3: Cap confidence for weak-only matches
    # If winner has no strong signals (only ambiguous/weak signals), cap at 0.25
    has_strong = strong_signals_by_country.get(winner, False)
    if not has_strong and winner_score < 8:
        confidence = min(confidence, 0.25)

    # NEW: Explicit UNKNOWN gating (unknown geo ≠ suspicious receipt)
    # If we don't have enough absolute signal strength, emit UNKNOWN even if a country "wins".
    geo_country_guess = winner
    if confidence < 0.30 or winner_score < 6:
        geo_country_guess = "UNKNOWN"

    # Suspicious geo means: there were some signals, but not enough to be confident.
    geo_suspicious = False
    if geo_country_guess == "UNKNOWN" and winner_score > 0 and confidence < 0.30:
        geo_suspicious = True

    # Zero out confidence for UNKNOWN geo (cleaner semantics)
    final_confidence = round(confidence, 2)
    if geo_country_guess == "UNKNOWN":
        final_confidence = 0.0

    return {
        "geo_country_guess": geo_country_guess,
        "geo_confidence": final_confidence,
        "geo_evidence": country_evidence.get(winner, [])[:10],  # Top 10 signals from raw winner
        "geo_scores": country_scores,
        "geo_suspicious": geo_suspicious,  # Flag for downstream rules
        # Keep raw winner for audit/debugging even when we emit UNKNOWN
        "geo_winner_raw": winner,
        "geo_winner_score_raw": int(winner_score),
        "geo_confidence_raw": round(confidence, 2),  # Raw confidence before UNKNOWN zeroing
        # Echo language prior inputs for debugging/audit
        "lang_hint": lang_hint,
        "lang_confidence": round(float(lang_confidence), 2) if isinstance(lang_confidence, (int, float)) else lang_confidence,
        "lang_score": float(lang_score) if isinstance(lang_score, (int, float)) else lang_score,
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
        "FUEL": ["gas", "fuel", "gallons", "pump", "gasoline", "diesel", "unleaded", "octane"],
        "PARKING": ["parking", "ticket", "meter"],
        "HOTEL_FOLIO": ["hotel", "room", "night", "check-in", "check-out", "folio"],
    },
    "IN": {
        "POS_RESTAURANT": ["restaurant", "hotel", "bill", "waiter", "table"],
        "POS_RETAIL": ["shop", "store", "retail", "item"],
        "TAX_INVOICE": ["tax invoice", "gstin", "hsn", "sac", "bill of supply"],
        "ECOMMERCE": ["order", "delivery", "tracking", "awb"],
        "FUEL": ["petrol", "diesel", "fuel", "litres", "litre", "ltr",
                 "oil", "pump", "petrol pump", "filling station", "nozzle",
                 "essar", "indian oil", "iocl", "hpcl", "bpcl", "reliance"],
        "UTILITY": ["electricity", "water", "gas", "bill", "consumer"],
        "TELECOM": ["mobile", "recharge", "plan", "data"],
        # Logistics/customs documents
        "COMMERCIAL_INVOICE": ["commercial invoice", "export", "import", "exporter", "consignee", "shipper"],
        "AIR_WAYBILL": ["air waybill", "airway bill", "awb", "flight", "cargo"],
        "SHIPPING_BILL": ["shipping bill", "customs", "port", "vessel"],
        "BILL_OF_LADING": ["bill of lading", "container", "vessel", "port"],
    },
    "CN": {  # China
        "POS_RESTAURANT": ["restaurant", "receipt", "bill", "发票", "收据"],
        "POS_RETAIL": ["store", "shop", "retail", "商店", "零售"],
        "TAX_INVOICE": ["invoice", "tax", "vat", "发票", "增值税"],
        "ECOMMERCE": ["order", "delivery", "tracking", "订单", "快递"],
    },
    "HK": {  # Hong Kong
        "POS_RESTAURANT": ["restaurant", "receipt", "bill", "餐廳", "收據"],
        "POS_RETAIL": ["store", "shop", "retail"],
        "TAX_INVOICE": ["invoice", "receipt", "發票"],
        "ECOMMERCE": ["order", "delivery", "tracking"],
    },
    "SG": {  # Singapore
        "POS_RESTAURANT": ["restaurant", "server", "bill", "table"],
        "POS_RETAIL": ["store", "retail", "shop"],
        "TAX_INVOICE": ["invoice", "gst", "tax"],
        "ECOMMERCE": ["order", "delivery", "tracking"],
    },
    "SA": {  # Saudi Arabia
        "POS_RESTAURANT": ["restaurant", "receipt", "bill"],
        "POS_RETAIL": ["store", "shop", "retail"],
        "TAX_INVOICE": ["invoice", "vat", "tax"],
        "ECOMMERCE": ["order", "delivery"],
    },
    "AE": {  # UAE
        "POS_RESTAURANT": ["restaurant", "receipt", "bill"],
        "POS_RETAIL": ["store", "shop", "retail"],
        "TAX_INVOICE": ["invoice", "vat", "trn"],
        "ECOMMERCE": ["order", "delivery"],
    },
    "FR": {  # France
        "POS_RESTAURANT": ["restaurant", "serveur", "pourboire", "table"],
        "POS_RETAIL": ["magasin", "boutique", "vente"],
        "TAX_INVOICE": ["facture", "tva", "taxe"],
        "ECOMMERCE": ["commande", "livraison", "suivi"],
        "PARKING": ["parking", "stationnement"],
    },
    "DE": {  # Germany
        "POS_RESTAURANT": ["restaurant", "kellner", "trinkgeld", "tisch"],
        "POS_RETAIL": ["geschäft", "laden", "verkauf"],
        "TAX_INVOICE": ["rechnung", "mwst", "steuer"],
        "ECOMMERCE": ["bestellung", "lieferung", "sendung"],
        "PARKING": ["parkplatz", "parkschein"],
    },
    "BR": {  # Brazil
        "POS_RESTAURANT": ["restaurante", "garçom", "gorjeta", "mesa"],
        "POS_RETAIL": ["loja", "varejo", "venda"],
        "TAX_INVOICE": ["nota fiscal", "cnpj", "icms"],
        "ECOMMERCE": ["pedido", "entrega", "rastreamento"],
        "FUEL": ["gasolina", "diesel", "combustível"],
    },
    "JP": {  # Japan
        "POS_RESTAURANT": ["restaurant", "receipt", "領収書", "レシート"],
        "POS_RETAIL": ["store", "shop", "店舗"],
        "TAX_INVOICE": ["invoice", "receipt", "領収書", "消費税"],
        "ECOMMERCE": ["order", "delivery"],
    },
    "TH": {  # Thailand
        "POS_RESTAURANT": ["restaurant", "receipt", "bill"],
        "POS_RETAIL": ["store", "shop", "retail"],
        "TAX_INVOICE": ["invoice", "vat", "tax"],
        "ECOMMERCE": ["order", "delivery"],
    },
    "CA": {  # Canada (same as US mostly)
        "POS_RESTAURANT": ["restaurant", "server", "tip", "gratuity", "table"],
        "POS_RETAIL": ["store", "retail", "merchandise"],
        "TAX_INVOICE": ["invoice", "gst", "hst", "pst"],
        "ECOMMERCE": ["order", "shipping", "tracking"],
        "HOTEL_FOLIO": ["hotel", "room", "night"],
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
    text_raw_lower = (text or "").lower()
    text_lower = text_raw_lower
    
    # POS HEURISTIC UPGRADE: Detect POS_RESTAURANT early with structural signals
    # This prevents false negatives when keyword matching alone is insufficient
    pos_score = 0
    pos_evidence = []
    
    # Signal 1: Merchant name in ALL CAPS near top (first 5 lines)
    if lines:
        top_lines = lines[:5]
        for line in top_lines:
            line_stripped = line.strip()
            if len(line_stripped) > 3 and line_stripped.isupper() and not line_stripped.startswith(('BILL', 'INVOICE', 'RECEIPT', 'DATE', 'TIME')):
                pos_score += 1
                pos_evidence.append("merchant_all_caps_top")
                break
    
    # Signal 2: Currency = INR (common for Indian POS)
    # Only add currency_inr if INR/₹ actually detected in text
    if "inr" in text_raw_lower or "₹" in text or "rs." in text_raw_lower or "rs " in text_raw_lower:
        pos_score += 1
        pos_evidence.append("currency_inr")
    
    # Signal 3: GST detected (Indian tax)
    if any(gst_kw in text_raw_lower for gst_kw in ["gst", "gstin", "cgst", "sgst", "igst"]):
        pos_score += 1
        pos_evidence.append("gst_detected")
    
    # Signal 4: Line items with quantity × price pattern
    qty_price_pattern = False
    for line in lines:
        line_lower = line.lower()
        # Look for patterns like: "2 x 100" or "qty: 3" or "@ 50.00"
        if any(pattern in line_lower for pattern in [" x ", "qty", " @ ", "quantity"]):
            qty_price_pattern = True
            break
    if qty_price_pattern:
        pos_score += 1
        pos_evidence.append("qty_price_pattern")
    
    # Signal 5: POS-specific words (Bill, Qty, Amount, Total)
    pos_words = ["bill", "qty", "amount", "total"]
    pos_word_hits = sum(1 for word in pos_words if word in text_raw_lower)
    if pos_word_hits >= 2:
        pos_score += 1
        pos_evidence.append(f"pos_words:{pos_word_hits}")
    
    # Signal 6: NO invoice-specific blocks (Customer GSTIN, Invoice No)
    has_invoice_block = any(inv_kw in text_raw_lower for inv_kw in ["invoice no", "invoice number", "customer gstin", "buyer gstin", "po number"])
    if not has_invoice_block:
        pos_score += 1
        pos_evidence.append("no_invoice_block")
    
    # Early return if POS heuristic triggers (≥3 signals)
    if pos_score >= 3:
        confidence = min(0.85, 0.6 + 0.1 * pos_score)
        return {
            "doc_family_guess": "TRANSACTIONAL",
            "doc_subtype_guess": "POS_RESTAURANT",
            "doc_subtype_confidence": round(confidence, 2),
            "doc_subtype_source": "pos_heuristic",
            "doc_subtype_evidence": pos_evidence,
            "doc_profile_confidence": round(confidence, 2),
            "doc_profile_evidence": pos_evidence,
            "requires_corroboration": False,
            "disable_missing_field_penalties": False,
        }

    routed_packs = []
    routed_script = None
    routed_confidence = 0.0
    normalizer = None
    try:
        _, router, normalizer = _get_lang_components()
        routing = router.route_document(text or "", allow_multi_pack=True)
        routed_packs = routing.all_packs
        routed_script = routing.script
        routed_confidence = float(routing.confidence or 0.0)
        if normalizer and routed_script:
            text_lower = normalizer.normalize_text(text or "", routed_script).lower()
    except Exception:
        routed_packs = []
        routed_script = None
        routed_confidence = 0.0
        normalizer = None
    
    # Get geo-specific keywords (fallback to US if unknown)
    geo_keywords = GEO_SUBTYPE_KEYWORDS.get(geo_country, GEO_SUBTYPE_KEYWORDS.get("US", {}))
    
    # Score each subtype
    subtype_scores: Dict[str, float] = {}
    subtype_evidence: Dict[str, List[str]] = {}

    pack_keywords_by_subtype: Dict[str, List[str]] = {}
    if routed_packs:
        for pack in routed_packs:
            kws = pack.keywords
            pack_keywords_by_subtype.setdefault("TAX_INVOICE", []).extend(kws.tax_invoice)
            pack_keywords_by_subtype.setdefault("ECOMMERCE", []).extend(kws.ecommerce)
            pack_keywords_by_subtype.setdefault("FUEL", []).extend(kws.fuel)
            pack_keywords_by_subtype.setdefault("PARKING", []).extend(kws.parking)
            pack_keywords_by_subtype.setdefault("HOTEL_FOLIO", []).extend(kws.hotel_folio)
            pack_keywords_by_subtype.setdefault("UTILITY", []).extend(kws.utility)
            pack_keywords_by_subtype.setdefault("TELECOM", []).extend(kws.telecom)
            pack_keywords_by_subtype.setdefault("COMMERCIAL_INVOICE", []).extend(kws.commercial_invoice)
            pack_keywords_by_subtype.setdefault("SHIPPING_BILL", []).extend(kws.shipping_bill)
            pack_keywords_by_subtype.setdefault("BILL_OF_LADING", []).extend(kws.bill_of_lading)
            pack_keywords_by_subtype.setdefault("AIR_WAYBILL", []).extend(kws.air_waybill)

            pack_keywords_by_subtype.setdefault("__LOGISTICS__", []).extend(kws.logistics)
    
    pack_inc = 0.7 + 0.3 * max(0.0, min(1.0, routed_confidence))

    for subtype, keywords in geo_keywords.items():
        score = 0.0
        evidence: List[str] = []

        keyword_weights: Dict[str, float] = {}
        for kw in (keywords or []):
            kw_s = str(kw or "").strip()
            if not kw_s:
                continue
            keyword_weights[kw_s] = max(keyword_weights.get(kw_s, 0.0), 1.0)

        for kw in (pack_keywords_by_subtype.get(subtype) or []):
            kw_s = str(kw or "").strip()
            if not kw_s:
                continue
            keyword_weights[kw_s] = max(keyword_weights.get(kw_s, 0.0), pack_inc)

        for kw_s, inc in keyword_weights.items():
            kw_l = kw_s.lower()
            hit = False
            if kw_l and (kw_l in text_raw_lower):
                hit = True
            if (not hit) and normalizer and routed_script:
                kw_n = normalizer.normalize_text(kw_s, routed_script).lower()
                if kw_n and (kw_n in text_lower):
                    hit = True
            if hit:
                score += float(inc)
                evidence.append(kw_s)

        subtype_scores[subtype] = float(score)
        subtype_evidence[subtype] = evidence
    
    # Logistics boost: if we see strong logistics/customs markers, boost logistics subtypes
    logistics_markers = [
        "exporter", "shipper", "consignee",
        "hs code", "hsn", "customs",
        "awb", "airway bill", "bill of lading",
        "shipping bill", "port of loading", "port of discharge",
        "country of export", "country of ultimate destination",
    ]
    logistics_pack_markers = pack_keywords_by_subtype.get("__LOGISTICS__") or []
    logistics_hits = sum(1 for m in logistics_markers if (m in text_lower) or (m in text_raw_lower))
    if logistics_pack_markers:
        for m in logistics_pack_markers:
            m_s = str(m or "").strip()
            if not m_s:
                continue
            m_l = m_s.lower()
            if m_l and ((m_l in text_raw_lower) or (m_l in text_lower)):
                logistics_hits += 1
    if logistics_hits >= 2:
        # Boost logistics-related subtypes
        for st in ["SHIPPING_BILL", "BILL_OF_LADING", "AIR_WAYBILL", "COMMERCIAL_INVOICE", "SHIPPING_INVOICE"]:
            if st in subtype_scores:
                subtype_scores[st] += 3  # Significant boost to overcome UTILITY
    
    # --- subtype winner selection (hypothesis contract) ---
    MIN_SUBTYPE_SCORE = 4

    # SURGICAL FIX: If restaurant keyword found in POS_RESTAURANT, boost it to meet threshold
    # This prevents returning "unknown" when restaurant evidence exists
    restaurant_evidence = subtype_evidence.get("POS_RESTAURANT", [])
    if isinstance(restaurant_evidence, list) and "restaurant" in restaurant_evidence:
        pos_restaurant_score = subtype_scores.get("POS_RESTAURANT", 0.0)
        if pos_restaurant_score > 0 and pos_restaurant_score < MIN_SUBTYPE_SCORE:
            # Boost to meet threshold
            subtype_scores["POS_RESTAURANT"] = MIN_SUBTYPE_SCORE

    if (not subtype_scores) or (max(subtype_scores.values()) == 0):
        return {
            "doc_family_guess": "UNKNOWN",
            "doc_subtype_guess": "unknown",
            "doc_subtype_confidence": 0.0,
            "doc_subtype_source": "geo_profile",
            "doc_subtype_evidence": [],
            "doc_profile_confidence": 0.0,
            "doc_profile_evidence": [],
            "requires_corroboration": True,
            "disable_missing_field_penalties": True,
        }

    winner = max(subtype_scores, key=subtype_scores.get)
    winner_score = float(subtype_scores.get(winner, 0.0) or 0.0)
    total_score = float(sum(subtype_scores.values()) or 0.0)

    # Gate weak subtype picks
    if winner_score < MIN_SUBTYPE_SCORE:
        return {
            "doc_family_guess": "UNKNOWN",
            "doc_subtype_guess": "unknown",
            "doc_subtype_confidence": 0.0,
            "doc_subtype_source": "geo_profile",
            "doc_subtype_evidence": (subtype_evidence.get(winner, [])[:8] if isinstance(subtype_evidence, dict) else []),
            "doc_profile_confidence": 0.0,
            "doc_profile_evidence": (subtype_evidence.get(winner, [])[:8] if isinstance(subtype_evidence, dict) else []),
            "requires_corroboration": True,
            "disable_missing_field_penalties": True,
        }
    
    # Determine family from subtype
    if winner.startswith("POS_") or winner in ["TAX_INVOICE", "ECOMMERCE", "FUEL", "PARKING", "HOTEL_FOLIO", "UTILITY", "TELECOM", "COMMERCIAL_INVOICE", "SHIPPING_INVOICE"]:
        family = "TRANSACTIONAL"
    elif winner in ["SHIPPING_BILL", "BILL_OF_LADING", "AIR_WAYBILL", "DELIVERY_NOTE"]:
        family = "LOGISTICS"
    else:
        family = "PAYMENT"
    
    # Special confidence boost for POS_RESTAURANT: restaurant keyword alone should reach >= 0.5
    # Many restaurant invoices won't have tip/table/server depending on country
    if winner == "POS_RESTAURANT":
        restaurant_evidence = subtype_evidence.get("POS_RESTAURANT", [])
        if isinstance(restaurant_evidence, list) and "restaurant" in restaurant_evidence:
            # Base: 0.55 for restaurant keyword
            confidence = 0.55
            # Bonus signals from merged features (passed via text analysis)
            evidence_count = len(restaurant_evidence)
            if evidence_count > 1:
                # +0.05 per additional evidence (e.g., amounts, date/time, other POS signals)
                confidence = min(0.75, 0.55 + (evidence_count - 1) * 0.05)
        else:
            confidence = min(1.0, float(winner_score) / max(10.0, float(total_score)))
    else:
        confidence = min(1.0, float(winner_score) / max(10.0, float(total_score)))

    # Geo-corroboration boost: strong geo detection validates subtype classification
    # If geo is confident (>= 0.6), boost subtype confidence by up to 0.15
    if geo_confidence >= 0.6 and confidence >= 0.35:
        geo_boost = min(0.15, geo_confidence * 0.15)
        confidence = min(1.0, confidence + geo_boost)

    return {
        "doc_family_guess": family,
        "doc_subtype_guess": winner,
        "doc_subtype_confidence": round(float(confidence), 2),
        "doc_subtype_source": "geo_profile",
        "doc_subtype_evidence": (subtype_evidence.get(winner, [])[:8] if isinstance(subtype_evidence, dict) else []),
        "doc_profile_confidence": round(float(confidence), 2),
        "doc_profile_evidence": (subtype_evidence.get(winner, [])[:8] if isinstance(subtype_evidence, dict) else []),
        "requires_corroboration": False,
        "disable_missing_field_penalties": False,  # Normal subtypes use standard rules
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
    
    # US State abbreviations (all 50 states + DC)
    us_states = [
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"
    ]
    
    # Strong US signal: State + ZIP pattern (e.g., "TN 37087")
    state_zip_pattern = r'\b(' + '|'.join(us_states) + r')\s+(\d{5}(?:-\d{4})?)\b'
    state_zip_match = re.search(state_zip_pattern, text)
    if state_zip_match:
        features["us_state"] = state_zip_match.group(1)
        features["us_zip"] = state_zip_match.group(2)
        features["us_confidence"] = 0.95  # Very high confidence
    
    # ZIP Code (standalone)
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


def extract_cn_specific(text: str) -> Dict[str, Any]:
    """Extract China-specific fields (tax ID, postal code, etc.)."""
    features = {}
    
    # Chinese tax ID (统一社会信用代码) - 18 digits/chars
    tax_id_pattern = r'\b[0-9A-Z]{18}\b'
    tax_match = re.search(tax_id_pattern, text)
    if tax_match:
        features["cn_tax_id"] = tax_match.group(0)
    
    # Postal code (6 digits)
    postal_pattern = r'\b\d{6}\b'
    postal_matches = re.findall(postal_pattern, text)
    if postal_matches:
        features["cn_postal_code"] = postal_matches[0]
    
    # Phone (China format)
    phone_pattern = r'\+?86[\s\-]?(1[3-9]\d{9})'
    phone_match = re.search(phone_pattern, text)
    if phone_match:
        features["cn_phone"] = phone_match.group(1)
    
    return features


def extract_sa_specific(text: str) -> Dict[str, Any]:
    """Extract Saudi Arabia-specific fields."""
    features = {}
    
    # VAT number (15 digits)
    vat_pattern = r'\b\d{15}\b'
    vat_match = re.search(vat_pattern, text)
    if vat_match:
        features["sa_vat_number"] = vat_match.group(0)
    
    # Phone (Saudi format)
    phone_pattern = r'\+?966[\s\-]?(\d{9})'
    phone_match = re.search(phone_pattern, text)
    if phone_match:
        features["sa_phone"] = phone_match.group(1)
    
    return features


def extract_br_specific(text: str) -> Dict[str, Any]:
    """Extract Brazil-specific fields (CNPJ, CPF, CEP)."""
    features = {}
    
    # CNPJ (14 digits with formatting)
    cnpj_pattern = r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b'
    cnpj_match = re.search(cnpj_pattern, text)
    if cnpj_match:
        features["br_cnpj"] = cnpj_match.group(0)
    
    # CPF (11 digits with formatting)
    cpf_pattern = r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b'
    cpf_match = re.search(cpf_pattern, text)
    if cpf_match:
        features["br_cpf"] = cpf_match.group(0)
    
    # CEP (postal code)
    cep_pattern = r'\b(\d{5}-\d{3})\b'
    cep_match = re.search(cep_pattern, text)
    if cep_match:
        features["br_cep"] = cep_match.group(1)
    
    return features


def extract_jp_specific(text: str) -> Dict[str, Any]:
    """Extract Japan-specific fields."""
    features = {}
    
    # Postal code (Japanese format: 123-4567)
    postal_pattern = r'\b(\d{3}-\d{4})\b'
    postal_match = re.search(postal_pattern, text)
    if postal_match:
        features["jp_postal_code"] = postal_match.group(1)
    
    # Phone (Japan format)
    phone_pattern = r'\+?81[\s\-]?(\d{9,10})'
    phone_match = re.search(phone_pattern, text)
    if phone_match:
        features["jp_phone"] = phone_match.group(1)
    
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
        return extract_us_specific(text)  # Canada similar to US
    elif geo_country == "CN":
        return extract_cn_specific(text)
    elif geo_country == "SA":
        return extract_sa_specific(text)
    elif geo_country == "BR":
        return extract_br_specific(text)
    elif geo_country == "JP":
        return extract_jp_specific(text)
    elif geo_country in ["HK", "SG", "AE", "FR", "DE", "TH"]:
        # Generic extraction for these countries (can be expanded later)
        return {}
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
    
    # Step 2: Use ENRICHED geo inference system (NEW)
    # This replaces the old _detect_geo_country with database-backed inference
    geo_enriched = infer_geo(text)
    
    # Map enriched result to expected format
    geo_result = {
        "geo_country_guess": geo_enriched["geo_country_guess"],
        "geo_confidence": geo_enriched["geo_confidence"],
        "geo_evidence": geo_enriched["geo_evidence"],
        "geo_candidates": geo_enriched["candidates"],
        "geo_mixed": geo_enriched["geo_mixed"],
    }
    
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
