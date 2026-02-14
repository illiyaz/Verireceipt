# app/pipelines/rules.py

import logging
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Union, Tuple
from datetime import datetime, date
import re

from app.pipelines.rule_family_matrix import (
    is_rule_allowed_for_family,
    get_allowed_families_for_rule,
    get_execution_mode,
    ExecutionMode,
)
from app.pipelines.template_quality_signals import (
    detect_keyword_typos,
    detect_spacing_anomaly,
    detect_date_format_anomaly,
)
from app.pipelines.features import build_features
from app.pipelines.ingest import ingest_and_ocr
from app.schemas.receipt import ReceiptDecision, ReceiptFeatures, ReceiptInput ,LearnedRuleAudit
from app.geo.db import (
    query_geo_profile,
    query_vat_rules,
    query_currency_countries,
    query_doc_expectations,
)


logger = logging.getLogger(__name__)

# Version tracking for audit trail
RULE_VERSION = "0.0.1"
POLICY_VERSION = "0.0.1"
ENGINE_VERSION = "rules-v0.0.1"

# -----------------------------------------------------------------------------
# Helper utilities (keep rule logic self-contained)
# -----------------------------------------------------------------------------

@dataclass
class RuleEvent:
    rule_id: str
    severity: str               # HARD_FAIL | CRITICAL | WARNING | INFO
    weight: float               # applied weight (after confidence scaling)
    raw_weight: float           # original rule weight before scaling
    message: str
    evidence: Dict[str, Any]

def _emit_event(
    events: List[RuleEvent],
    reasons: Optional[List[str]],
    rule_id: str,
    severity: str,
    weight: float,
    message: str,
    evidence: Optional[Dict[str, Any]] = None,
    reason_text: Optional[str] = None,
    confidence_factor: float = 1.0
) -> float:
    """
    Emit a structured rule event AND (optionally) a text reason.
    Returns score delta to add.
    """
    sev = (severity or "INFO").upper().strip()
    raw_w = float(weight or 0.0)
    cf = float(confidence_factor or 1.0)

    if sev == "HARD_FAIL":
        applied_w = raw_w
        cf_used = 1.0
    else:
        cf_used = max(0.60, min(1.00, cf))
        applied_w = raw_w * cf_used

    # Copy evidence upfront to avoid mutating caller's dict
    base_evidence = dict(evidence or {})
    base_evidence.setdefault("confidence_factor", cf_used)
    base_evidence.setdefault("raw_weight", raw_w)
    base_evidence.setdefault("applied_weight", applied_w)

    ev = RuleEvent(
        rule_id=rule_id,
        severity=sev,
        weight=applied_w,
        raw_weight=raw_w,
        message=str(message or ""),
        evidence=base_evidence,
    )
    events.append(ev)

    # Keep backward compatibility for UI: append text reasons with tags when requested
    if reasons is not None:
        if reason_text:
            reasons.append(f"[{sev}] {reason_text}")
        else:
            reasons.append(f"[{sev}] {message}")

    return ev.weight

def _join_text(tf: dict, lf: dict) -> str:
    """Best-effort text blob for rules that need raw content.

    Prefer OCR/text pipeline output if available, else fall back to layout lines.
    """
    raw = tf.get("raw_text") or tf.get("text") or ""
    if raw and isinstance(raw, str):
        return raw

    lines = lf.get("lines") or []
    if isinstance(lines, list) and lines:
        return "\n".join([str(x) for x in lines])
    return ""

def _confidence_factor_from_features(
    ff: Dict[str, Any],
    tf: Dict[str, Any],
    lf: Dict[str, Any],
    fr: Dict[str, Any],
) -> float:
    """
    Returns a multiplicative factor in [0.6, 1.0] to scale *soft* rule weights.
    We DO NOT down-weight HARD_FAIL rules.
    
    Priority order:
    1. extraction_confidence_score (canonical 0-1 field)
    2. extraction_confidence_level (canonical "low"/"medium"/"high")
    3. tf["confidence"] (legacy field)
    4. Default to 0.70
    """
    conf: Optional[float] = None
    
    # Priority 1: Use canonical extraction_confidence_score if available
    ext_score = tf.get("extraction_confidence_score")
    if ext_score is not None and isinstance(ext_score, (int, float)):
        try:
            conf = float(ext_score)
        except Exception:
            pass
    
    # Priority 2: Use canonical extraction_confidence_level if available
    if conf is None:
        ext_level = tf.get("extraction_confidence_level")
        if ext_level and isinstance(ext_level, str):
            el = ext_level.strip().lower()
            if el == "high":
                conf = 0.90
            elif el == "medium":
                conf = 0.70
            elif el == "low":
                conf = 0.45
    
    # Priority 3: Fall back to legacy tf["confidence"]
    if conf is None:
        c = tf.get("confidence")
        if isinstance(c, (int, float)):
            try:
                conf = float(c)
            except Exception:
                pass
        elif isinstance(c, str):
            cl = c.strip().lower()
            if cl in ("high", "h"):
                conf = 0.90
            elif cl in ("medium", "med", "m"):
                conf = 0.70
            elif cl in ("low", "l"):
                conf = 0.45
    
    # Priority 4: Default
    if conf is None:
        conf = 0.70

    if conf >= 0.85:
        factor = 1.0
    elif conf >= 0.65:
        factor = 0.85
    else:
        factor = 0.70

    # Optional extra softening when OCR reliability is likely worse
    source_type = (ff.get("source_type") or "").lower()
    if source_type == "image" and not ff.get("exif_present"):
        factor = min(factor, 0.80)

    # Geo-aware softening:
    # UNKNOWN (low confidence) geo should NOT automatically imply a suspicious receipt.
    # We soften *soft* rule weights (never HARD_FAIL) when geo detection is weak.
    # Defensive fix: Source from doc_profile first if available
    try:
        dp = doc_profile or {}
        geo_country = str(dp.get("geo_country") or tf.get("geo_country_guess") or "UNKNOWN").upper().strip()
        geo_conf = dp.get("geo_confidence") or tf.get("geo_confidence")
        geo_conf_f = float(geo_conf) if geo_conf is not None else 0.0
    except Exception:
        geo_country = "UNKNOWN"
        geo_conf_f = 0.0

    if geo_country == "UNKNOWN" and geo_conf_f < 0.30:
        # Reduce the impact of missing-field and pattern-based soft rules.
        factor = min(factor, 0.70)

    # Doc subtype fallback guard: if subtype is MISC/UNKNOWN with low confidence,
    # keep soft rules conservative to avoid false positives.
    try:
        subtype_guess = str(tf.get("doc_subtype_guess") or "UNKNOWN").upper().strip()
        dp_conf = tf.get("doc_profile_confidence")
        dp_conf_f = float(dp_conf) if dp_conf is not None else 0.0
    except Exception:
        subtype_guess = "UNKNOWN"
        dp_conf_f = 0.0

    if subtype_guess in ("MISC", "UNKNOWN") and dp_conf_f < 0.55:
        factor = min(factor, 0.75)

    return max(0.60, min(1.00, float(factor)))

def _normalize_amount_str(val: Any) -> Optional[float]:
    """Normalize a currency/amount string into a float. Returns None if not parseable."""
    if val is None:
        return None

    if isinstance(val, (int, float)):
        try:
            return float(val)
        except Exception:
            return None

    s = str(val).strip()
    if not s:
        return None

    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1].strip()

    kept = []
    for ch in s:
        if ch.isdigit() or ch in {".", ",", "-", " ", "\u00A0"}:
            kept.append(ch)
    s = "".join(kept).replace("\u00A0", " ").strip()

    if "," in s and "." in s:
        s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", "")

    s = s.replace(" ", "")
    if s in {"", "-", "."}:
        return None

    try:
        out = float(s)
        return -out if neg else out
    except Exception:
        return None


def _has_total_value(tf: dict) -> bool:
    """True if we have a usable total value even if TOTAL line keyword wasn't detected."""
    for k in ("total", "total_amount", "grand_total", "amount_total", "total_extracted"):
        if k in tf and tf.get(k) not in (None, ""):
            if _normalize_amount_str(tf.get(k)) is not None:
                return True
    return False
# -----------------------------------------------------------------------------
# Doc-profile aware expectations (used to avoid false-positives)
# -----------------------------------------------------------------------------

# Subtypes where a printed TOTAL line is often absent or irrelevant
_DOC_SUBTYPES_TOTAL_OPTIONAL = {
    # Logistics docs commonly focus on shipment fields, not totals
    "AIR_WAYBILL",
    "BILL_OF_LADING",
    "DELIVERY_NOTE",
}

# Subtypes where *amounts themselves* are optional/rare
_DOC_SUBTYPES_AMOUNTS_OPTIONAL = {
    "DELIVERY_NOTE",
    "BILL_OF_LADING",
}

# Subtypes where a transaction date may be missing/less prominent
_DOC_SUBTYPES_DATE_OPTIONAL = {
    "DELIVERY_NOTE",
    "BILL_OF_LADING",
}


def _get_doc_profile(tf: Dict[str, Any], doc_type_hint: Optional[str] = None) -> Dict[str, Any]:
    """Return doc profile guess from features (preferred) with a safe fallback."""
    family = tf.get("doc_family_guess") or "UNKNOWN"
    subtype = tf.get("doc_subtype_guess") or "UNKNOWN"
    conf = tf.get("doc_profile_confidence")

    try:
        conf_f = float(conf) if conf is not None else 0.0
    except Exception:
        conf_f = 0.0

    # Backward-compatible fallback from older doc_type_hint
    if str(subtype).strip().lower() == "unknown" and doc_type_hint:
        dth = str(doc_type_hint).lower().strip()
        if dth in ("receipt", "tax_invoice", "invoice"):
            family = "TRANSACTIONAL"
            subtype = "TAX_INVOICE" if dth == "tax_invoice" else ("RECEIPT" if dth == "receipt" else "INVOICE")
            conf_f = max(conf_f, 0.55)

    return {
        "family": str(family),
        "subtype": str(subtype),
        "confidence": max(0.0, min(1.0, conf_f)),
        "evidence": tf.get("doc_profile_evidence") or [],
        # Geo-aware tags (may be UNKNOWN / None)
        # Note: This is legacy fallback; prefer doc_profile from detect_geo_and_profile
        "geo_country": str(tf.get("geo_country_guess") or "UNKNOWN"),
        "geo_confidence": tf.get("geo_confidence"),
        "lang": tf.get("lang_guess"),
        "lang_confidence": tf.get("lang_confidence"),
    }


# --------------------------------------------------------------------------
# Geo and doc-profile aware missing-field penalty gating helpers
# --------------------------------------------------------------------------
def _geo_unknown_low(tf: Dict[str, Any], doc_profile: Optional[Dict[str, Any]] = None) -> bool:
    """True when geo detection is too weak to treat missing-field expectations as fraud."""
    try:
        # Defensive fix: Source from doc_profile first (final geo_detection output)
        dp = doc_profile or {}
        geo_country = str(dp.get("geo_country") or tf.get("geo_country_guess") or "UNKNOWN").upper().strip()
        geo_conf = dp.get("geo_confidence") or tf.get("geo_confidence")
        geo_conf_f = float(geo_conf) if geo_conf is not None else 0.0
    except Exception:
        geo_country = "UNKNOWN"
        geo_conf_f = 0.0
    return geo_country == "UNKNOWN" and geo_conf_f < 0.30


def _doc_misc_low(tf: Dict[str, Any], doc_profile: Optional[Dict[str, Any]] = None) -> bool:
    """True when doc subtype is a fallback (MISC/UNKNOWN) with low confidence."""
    try:
        subtype = str(tf.get("doc_subtype_guess") or (doc_profile or {}).get("subtype") or "UNKNOWN").upper().strip()
        dp_conf = tf.get("doc_profile_confidence")
        if dp_conf is None and doc_profile is not None:
            dp_conf = doc_profile.get("confidence")
        dp_conf_f = float(dp_conf) if dp_conf is not None else 0.0
    except Exception:
        subtype = "UNKNOWN"
        dp_conf_f = 0.0
    return subtype in ("MISC", "UNKNOWN") and dp_conf_f < 0.55


def _missing_field_penalties_enabled(
    tf: Dict[str, Any],
    doc_profile: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Missing-field penalties are ONLY allowed when we are confident
    this is a transactional receipt/invoice.
    """

    dp = doc_profile or {}

    try:
        dp_conf = tf.get("doc_profile_confidence") or dp.get("confidence")
        dp_conf = float(dp_conf)
    except Exception:
        dp_conf = 0.0

    # 🚨 Hard gate: low confidence = NO missing-field penalties
    if dp_conf < 0.55:
        return False

    # Existing safety gates
    if _geo_unknown_low(tf, doc_profile=doc_profile):
        return False

    if _doc_misc_low(tf, doc_profile=doc_profile):
        return False

    return True


def _missing_field_gate_evidence(tf: Dict[str, Any], doc_profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Common evidence for audit when missing-field penalties are gated off."""
    dp = doc_profile or {}
    # Defensive fix: Source geo data from final doc_profile (geo_detection output) first, not legacy tf
    return {
        "geo_country_guess": dp.get("geo_country") or tf.get("geo_country_guess"),
        "geo_confidence": dp.get("geo_confidence") or tf.get("geo_confidence"),
        "doc_subtype_guess": dp.get("subtype") or tf.get("doc_subtype_guess"),
        "doc_profile_confidence": dp.get("confidence") or tf.get("doc_profile_confidence"),
        "lang_guess": dp.get("lang") or tf.get("lang_guess"),
        "lang_confidence": dp.get("lang_confidence") or tf.get("lang_confidence"),
    }


def _get_document_intent(tf: Dict[str, Any]) -> Tuple[Optional[str], float]:
    """Best-effort extraction of (intent, confidence) from text_features."""
    try:
        di = tf.get("document_intent")
        if not isinstance(di, dict):
            return (None, 0.0)
        intent = di.get("intent")
        conf = di.get("confidence")
        intent_s = str(intent).strip().lower() if intent is not None else None
        conf_f = float(conf) if conf is not None else 0.0
        return (intent_s, conf_f)
    except Exception:
        return (None, 0.0)


def _emit_missing_field_gate_event(
    events: List[RuleEvent],
    reasons: Optional[List[str]],
    tf: Dict[str, Any],
    doc_profile: Optional[Dict[str, Any]] = None,
    message: Optional[str] = None,
) -> None:
    """
    Emit an INFO RuleEvent indicating missing-field penalties are gated off.

    This is NOT a fraud signal; it prevents false-positives for UNKNOWN geo or low-confidence MISC docs.
    """
    _emit_event(
        events=events,
        reasons=reasons,
        rule_id="GATE_MISSING_FIELDS",
        severity="INFO",
        weight=0.0,
        message=message or "Missing-field penalties disabled due to UNKNOWN geo or low-confidence fallback doc subtype.",
        evidence=_missing_field_gate_evidence(tf, doc_profile=doc_profile),
        reason_text=None,  # keep user-facing reasons clean
        confidence_factor=1.0,
    )


def _expects_total_line(tf: Dict[str, Any], doc_profile: Dict[str, Any]) -> bool:
    intent, intent_conf = _get_document_intent(tf)
    if intent and intent_conf >= 0.55:
        # Strict expectations only for intents where a TOTAL line is meaningful.
        # Keep transport/claims conservative to avoid false positives.
        return intent in {
            "purchase",
            "billing",
            "subscription",
            "proof_of_payment",
            "reimbursement",
        }

    subtype = (doc_profile.get("subtype") or "UNKNOWN").upper()
    # If we are not confident about the subtype, do not be strict
    if float(doc_profile.get("confidence") or 0.0) < 0.55:
        return False
    return subtype not in _DOC_SUBTYPES_TOTAL_OPTIONAL


def _expects_amounts(tf: Dict[str, Any], doc_profile: Dict[str, Any]) -> bool:
    intent, intent_conf = _get_document_intent(tf)
    if intent and intent_conf >= 0.55:
        # Amounts are expected for most transactional/billing-related intents.
        # Transport/claims stay conservative.
        return intent in {
            "purchase",
            "billing",
            "subscription",
            "proof_of_payment",
            "reimbursement",
            "statement",
        }

    subtype = (doc_profile.get("subtype") or "UNKNOWN").upper()
    if float(doc_profile.get("confidence") or 0.0) < 0.55:
        return False
    return subtype not in _DOC_SUBTYPES_AMOUNTS_OPTIONAL


def _expects_date(tf: Dict[str, Any], doc_profile: Dict[str, Any]) -> bool:
    intent, intent_conf = _get_document_intent(tf)
    if intent and intent_conf >= 0.55:
        # Dates are generally expected for transactional/billing/statement docs.
        # Keep claims conservative.
        return intent in {
            "purchase",
            "billing",
            "subscription",
            "proof_of_payment",
            "reimbursement",
            "statement",
            "transport",
        }

    subtype = (doc_profile.get("subtype") or "UNKNOWN").upper()
    if float(doc_profile.get("confidence") or 0.0) < 0.55:
        return False
    return subtype not in _DOC_SUBTYPES_DATE_OPTIONAL

def _has_any_pattern(text: str, patterns: List[str]) -> bool:
    t = (text or "").lower()
    return any(p.lower() in t for p in patterns)


def _looks_like_gstin(text: str) -> bool:
    """Indian GSTIN: 15 chars: 2 digits + 10 PAN chars + 1 + Z + 1.
    Example: 27AAPFU0939F1ZV
    """
    t = (text or "").upper()
    return bool(re.search(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b", t))


def _looks_like_pan(text: str) -> bool:
    """Indian PAN: 10 chars: 5 letters + 4 digits + 1 letter."""
    t = (text or "").upper()
    return bool(re.search(r"\b[A-Z]{5}\d{4}[A-Z]\b", t))


def _looks_like_ein(text: str) -> bool:
    """US EIN: 2 digits hyphen 7 digits (e.g., 12-3456789)."""
    t = (text or "")
    return bool(re.search(r"\b\d{2}-\d{7}\b", t))


def _detect_us_state_hint(text: str) -> bool:
    """Lightweight US signal: state abbreviations or common state names."""
    us_hints = [
        "alabama",
        "alaska",
        "arizona",
        "arkansas",
        "california",
        "colorado",
        "connecticut",
        "delaware",
        "florida",
        "georgia",
        "hawaii",
        "idaho",
        "illinois",
        "indiana",
        "iowa",
        "kansas",
        "kentucky",
        "louisiana",
        "maine",
        "maryland",
        "massachusetts",
        "michigan",
        "minnesota",
        "mississippi",
        "missouri",
        "montana",
        "nebraska",
        "nevada",
        "new york",
        "new jersey",
        "new mexico",
        "north carolina",
        "north dakota",
        "ohio",
        "oklahoma",
        "oregon",
        "pennsylvania",
        "rhode island",
        "south carolina",
        "south dakota",
        "tennessee",
        "texas",
        "utah",
        "vermont",
        "virginia",
        "washington",
        "west virginia",
        "wisconsin",
        "wyoming",
        # common abbreviations (space-padded matching below)
        " ca ",
        " ny ",
        " nj ",
        " tx ",
        " fl ",
        " il ",
        " in ",
        " wa ",
        " ma ",
        " pa ",
    ]
    t = f" {(text or '').lower()} "
    return any(h in t for h in us_hints)


def _detect_india_hint(text: str) -> bool:
    """Lightweight India signal: state names, PIN (6 digits), +91, INR.
    
    IMPORTANT: Requires ≥2 India signals to avoid false positives.
    6-digit PIN alone is NOT sufficient (overlaps with China, Singapore, etc.).
    """
    t = (text or "").lower()
    
    # Count India-specific signals
    india_signals = 0
    
    # Strong signals
    if "+91" in t:
        india_signals += 1
    if "india" in t:
        india_signals += 1
    if " inr" in t or "₹" in t:
        india_signals += 1
    
    # 6-digit PIN only counts if we have India context
    has_pin = bool(re.search(r"\b\d{6}\b", t))
    if has_pin and any(k in t for k in ["india", "+91", "inr", "₹"]):
        india_signals += 1
    # Indian states and cities
    states = [
        "andhra pradesh",
        "telangana",
        "karnataka",
        "tamil nadu",
        "kerala",
        "maharashtra",
        "gujarat",
        "rajasthan",
        "uttar pradesh",
        "madhya pradesh",
        "bihar",
        "jharkhand",
        "west bengal",
        "punjab",
        "haryana",
        "delhi",
        "mumbai",
        "bangalore",
        "hyderabad",
        "chennai",
        "kolkata",
    ]
    for state in states:
        if state in t:
            india_signals += 1
            break  # Only count once
    
    # GST/GSTIN is a strong India signal
    if "gst" in t or "gstin" in t:
        india_signals += 1
    
    # Require at least 2 India signals
    return india_signals >= 2


def _detect_canada_hint(text: str) -> bool:
    """
    Lightweight Canada signal: looks for province names, cities, Canadian postal codes.

    IMPORTANT: Short abbreviations (ON, BC, QC) use word-boundary matching to avoid
    false positives inside words like 'london', 'hilton'. Tax terms (GST, HST, PST)
    require Canada context since they're used in India, Australia, Singapore, etc.
    """
    t = (text or "").lower()
    nt = _normalize_text_for_geo(t)  # " text "

    # Strong signals (unambiguous)
    strong_hints = [
        "canada", "ontario", "toronto", "vancouver", "montreal", "ottawa",
        "calgary", "edmonton", "winnipeg", "british columbia", "alberta",
        "quebec", "nova scotia", "new brunswick", "manitoba", "saskatchewan",
    ]
    if any(h in t for h in strong_hints):
        return True

    # Province abbreviations with word boundaries (avoid matching inside words)
    province_abbrs = [" on ", " bc ", " ab ", " sk ", " mb ", " nb ", " ns ", " pe ", " nl ", " qc "]
    if any(a in nt for a in province_abbrs):
        return True

    # Tax terms only with Canada context (GST/HST/PST are used globally)
    canada_context = any(h in t for h in ["canada", "ontario", "toronto", "vancouver", "calgary", "ottawa"])
    if canada_context and any(tax in t for tax in ["gst", "hst", "pst", "cra"]):
        return True

    # HST is more Canada-specific than GST (only used in Canada)
    if "hst" in t:
        return True

    # "+1" as phone code, but only if another Canada hint is present
    if "+1" in t:
        idx = t.find("+1")
        window = t[max(0, idx - 50): idx + 50]
        if any(h in window for h in ["canada", "ontario", "toronto", "vancouver"]):
            return True

    # Canadian postal code: [A-Z][0-9][A-Z] ?[0-9][A-Z][0-9]
    if re.search(r"\b[abceghjklmnprstvwxyz][0-9][abceghjklmnprstvwxyz][ -]?[0-9][abceghjklmnprstvwxyz][0-9]\b", t, re.I):
        return True

    return False

# -----------------------------------------------------------------------------
# GeoRuleMatrix (data-driven geo/currency/tax consistency)
# -----------------------------------------------------------------------------

def _normalize_text_for_geo(text: str) -> str:
    return f" {(text or '').lower()} "


def _detect_uk_hint(text: str) -> bool:
    """Lightweight UK signal: UK country/city terms, UK postcodes, +44, £/GBP.

    IMPORTANT: Does NOT match on generic "VAT" keyword because VAT is global
    (EU, India, UAE, etc.) — not UK-specific.
    """
    t = (text or "").lower()
    if "+44" in t or "united kingdom" in t or "london" in t or "england" in t or "scotland" in t or "wales" in t:
        return True
    # " uk " with word boundaries to avoid matching "uk" inside words
    if " uk " in _normalize_text_for_geo(t):
        return True
    # UK cities
    if any(city in t for city in ["manchester", "birmingham", "edinburgh", "glasgow", "liverpool", "bristol", "leeds", "sheffield"]):
        return True
    # UK postcode (very loose) e.g., SW1A 1AA, EC1A 1BB
    if re.search(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b", t, re.I):
        return True
    return False


def _detect_eu_hint(text: str) -> bool:
    """Lightweight EU signal: common EU country/city names, EU phone codes, EU VAT IDs.

    IMPORTANT: Does NOT match on currency (€/EUR) or generic "VAT" keyword because:
    - Currency is what we're testing for mismatch — using it as geo creates circular logic
    - "VAT" is global (UK, India, UAE, etc.) — not EU-specific
    """
    t = (text or "").lower()
    eu_hints = [
        "europe", "eu ", "germany", "berlin", "france", "paris", "spain", "madrid", "italy", "rome",
        "netherlands", "amsterdam", "ireland", "dublin", "belgium", "brussels", "austria", "vienna",
        "sweden", "stockholm", "denmark", "copenhagen", "finland", "helsinki", "poland", "warsaw",
        "portugal", "lisbon", "greece", "athens", "czech", "prague", "romania", "bucharest",
    ]
    if any(h in t for h in eu_hints):
        return True
    # EU phone codes
    if any(code in t for code in ["+49", "+33", "+34", "+39", "+31", "+353", "+32", "+43", "+46", "+45", "+358", "+48"]):
        return True
    # EU VAT ID: require known EU country prefix (DE, FR, ES, IT, NL, etc.)
    eu_prefixes = "(?:DE|FR|ES|IT|NL|BE|AT|SE|DK|FI|PL|PT|GR|CZ|RO|HU|BG|HR|SK|SI|LT|LV|EE|CY|MT|LU|IE)"
    if re.search(rf"\b{eu_prefixes}[A-Z0-9]{{8,12}}\b", (text or "").upper()):
        return True
    return False


def _detect_sg_hint(text: str) -> bool:
    """Lightweight Singapore signal: SG/ Singapore, +65, GST (SG), postal codes (6 digits)."""
    t = (text or "").lower()
    if "singapore" in t or " sg " in _normalize_text_for_geo(t) or "+65" in t:
        return True
    # Singapore postal code: 6 digits (note: overlaps India PIN, so require SG context)
    if re.search(r"\b\d{6}\b", t) and ("singapore" in t or "+65" in t or "sg" in t):
        return True
    # Singapore GST is also called GST; require SG context
    if "gst" in t and ("singapore" in t or "+65" in t or "sg" in t):
        return True
    return False


def _detect_au_hint(text: str) -> bool:
    """Lightweight Australia signal: Australia, AU, +61, states, GST (AU), ABN."""
    t = (text or "").lower()
    if "australia" in t or "+61" in t:
        return True
    # Common AU states/territories
    au_hints = ["nsw", "vic", "qld", "wa ", "sa ", "tas", "act", "nt ", "sydney", "melbourne", "brisbane", "perth", "adelaide"]
    if any(h in _normalize_text_for_geo(t) for h in au_hints):
        return True
    # ABN (11 digits, often written as ABN xx xxx xxx xxx)
    if re.search(r"\babn\b", t) and re.search(r"\b\d{2}\s?\d{3}\s?\d{3}\s?\d{3}\b", t):
        return True
    # AU GST: require AU context
    if "gst" in t and ("australia" in t or "+61" in t or "nsw" in t or "vic" in t or "qld" in t):
        return True
    return False

def _detect_uae_hint(text: str) -> bool:
    t = (text or "").lower()
    if any(k in t for k in [
        "united arab emirates", "uae",
        "dubai", "abu dhabi", "sharjah", "ajman",
        "ras al khaimah", "rak", "umm al quwain", "uaq", "fujairah", "al ain",
        "+971",
        "aed", "dirham", "د.إ",
    ]):
        return True
    return False

def _detect_saudi_hint(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in [
        "saudi", "saudi arabia", "kingdom of saudi arabia", "ksa",
        "riyadh", "jeddah", "dammam",
        "+966", "sar", "riyal",
        "السعودية",
    ])

def _detect_oman_hint(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in [
        "oman", "sultanate of oman", "muscat",
        "+968", "omr", "rial",
        "عمان",
    ])

def _detect_qatar_hint(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in ["qatar", "doha", "+974", "qar", "riyal"])

def _detect_kuwait_hint(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in ["kuwait", "kuwait city", "+965", "kwd", "dinar"])

def _detect_bahrain_hint(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in ["bahrain", "manama", "+973", "bhd", "dinar"])

def _detect_jordan_hint(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in [
        "jordan", "amman", "hashemite kingdom",
        "+962", "jod", "dinar",
        "الأردن",
    ])
    

def _detect_nz_hint(text: str) -> bool:
    """Lightweight New Zealand signal: New Zealand, NZ, +64, GST (NZ), IRD, cities."""
    t = (text or "").lower()
    if "new zealand" in t or "+64" in t:
        return True

    # Common NZ city/region hints
    nz_hints = [
        "auckland",
        "wellington",
        "christchurch",
        "hamilton",
        "queenstown",
        "dunedin",
        "tauranga",
        " nz ",
        " n.z",
    ]
    if any(h in _normalize_text_for_geo(t) for h in nz_hints):
        return True

    # NZ GST is also called GST; require NZ context
    if "gst" in t and ("new zealand" in t or "+64" in t or "auckland" in t or "wellington" in t):
        return True

    # NZ IRD number mention (very loose; IRD numbers are 8-9 digits)
    if "ird" in t and re.search(r"\b\d{8,9}\b", t):
        return True

    return False


# -------------------- East Asia geo detectors --------------------
def _detect_jp_hint(text: str) -> bool:
    """Lightweight Japan signal: Japan, JP, +81, common cities, JPY/¥, consumption tax."""
    t = (text or "").lower()
    if "japan" in t or "+81" in t:
        return True
    jp_hints = [
        "tokyo",
        "osaka",
        "kyoto",
        "nagoya",
        "yokohama",
        "sapporo",
        "fukuoka",
        "jp ",
        " jp ",
    ]
    if any(h in _normalize_text_for_geo(t) for h in jp_hints):
        return True
    # Currency hints (JPY / ¥) + a Japan context keyword
    if ("¥" in (text or "") or "jpy" in t or "yen" in t) and any(k in t for k in ["japan", "tokyo", "osaka", "+81"]):
        return True
    # Japan consumption tax keyword (very light)
    if "consumption tax" in t:
        return True
    # Very loose Japanese postal code pattern (e.g., 100-0001); only count if Japan context exists
    if re.search(r"\b\d{3}-\d{4}\b", t) and ("japan" in t or "+81" in t):
        return True
    return False


def _detect_cn_hint(text: str) -> bool:
    """Lightweight China signal: China, PRC, +86, major cities, RMB/CNY/yuan/¥, VAT."""
    t = (text or "").lower()
    if "china" in t or "people's republic of china" in t or "prc" in t or "+86" in t:
        return True
    cn_hints = [
        "beijing",
        "shanghai",
        "shenzhen",
        "guangzhou",
        "hangzhou",
        "chengdu",
        "hong kong",  # sometimes present alongside China context
    ]
    if any(h in t for h in cn_hints):
        return True
    if any(k in t for k in ["cny", "rmb", "yuan", "renminbi"]):
        return True
    # ¥ is ambiguous (JPY/CNY). Require China context.
    if "¥" in (text or "") and any(k in t for k in ["china", "beijing", "shanghai", "shenzhen", "+86", "rmb", "cny"]):
        return True
    # VAT mention is too broad; only count if China context exists
    if "vat" in t and any(k in t for k in ["china", "prc", "+86"]):
        return True
    # Common Chinese characters for China (very light signal)
    if any(k in (text or "") for k in ["中国", "中华人民共和国"]):
        return True
    return False


def _detect_hk_hint(text: str) -> bool:
    """Lightweight Hong Kong signal: Hong Kong, HK, +852, HKD, HK$.

    Note: HK is a special case; we treat it separately from CN.
    """
    t = (text or "").lower()
    if "hong kong" in t or "+852" in t:
        return True
    if "hkd" in t or "hk$" in t:
        return True
    if " hong kong " in _normalize_text_for_geo(t) or " hk " in _normalize_text_for_geo(t):
        return True
    return False


def _detect_tw_hint(text: str) -> bool:
    """Lightweight Taiwan signal: Taiwan, +886, TWD/NT$.

    We use TWD/NT$ as a strong hint.
    """
    t = (text or "").lower()
    if "taiwan" in t or "+886" in t:
        return True
    if "twd" in t or "nt$" in t:
        return True
    if any(k in (text or "") for k in ["臺灣", "台湾"]):
        return True
    return False


def _detect_kr_hint(text: str) -> bool:
    """Lightweight South Korea signal: Korea, South Korea, +82, KRW/₩.

    Note: 'Korea' is ambiguous; keep it light.
    """
    t = (text or "").lower()
    if "south korea" in t or "+82" in t:
        return True
    if "krw" in t or "₩" in (text or ""):
        return True
    if any(k in t for k in ["seoul", "busan", "incheon"]):
        return True
    if any(k in (text or "") for k in ["대한민국", "한국"]):
        return True
    return False

def _is_travel_or_hospitality(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in [
        "airline", "flight", "boarding pass", "pnr", "iata",
        "hotel", "resort", "inn", "lodge", "booking",
        "check-in", "check out", "room", "stay",
        "airport", "terminal", "gate"
    ])

# A simple, data-driven matrix. Add/adjust rows as we expand geo coverage.
# NOTE: This is *heuristic* and should bias to REVIEW (CRITICAL) rather than hard-fail.
GEO_RULE_MATRIX = {
    "US": {
        "geo_fn": _detect_us_state_hint,
        "currencies": {"USD"},
        "tax_regimes": {"SALES_TAX"},
        "tier": "STRICT",
    },
    "CA": {
        "geo_fn": _detect_canada_hint,
        "currencies": {"CAD"},
        "tax_regimes": {"HST", "GST", "PST"},  # Canada uses GST/HST/PST; we map PST under HST for now.
        "tier": "STRICT",
    },
    "IN": {
        "geo_fn": _detect_india_hint,
        "currencies": {"INR"},
        "tax_regimes": {"GST"},
        "tier": "STRICT",
    },
    "UK": {
        "geo_fn": _detect_uk_hint,
        "currencies": {"GBP"},
        "tax_regimes": {"VAT"},
        "tier": "STRICT",
    },
    "EU": {
        "geo_fn": _detect_eu_hint,
        "currencies": {"EUR"},
        "tax_regimes": {"VAT"},
        "tier": "STRICT",
    },
    "AU": {
        "geo_fn": _detect_au_hint,
        "currencies": {"AUD"},
        "tax_regimes": {"GST"},
        "tier": "STRICT",
    },

    # -------------------- Middle East --------------------
    "UAE": {"geo_fn": _detect_uae_hint, "currencies": {"AED"}, "tax_regimes": {"VAT"}, "tier": "STRICT"},
    "SA":  {"geo_fn": _detect_saudi_hint, "currencies": {"SAR"}, "tax_regimes": {"VAT"}, "tier": "STRICT"},
    "OM":  {"geo_fn": _detect_oman_hint, "currencies": {"OMR"}, "tax_regimes": {"VAT"}, "tier": "STRICT"},
    "QA":  {"geo_fn": _detect_qatar_hint, "currencies": {"QAR"}, "tax_regimes": set(), "tier": "RELAXED"},
    "KW":  {"geo_fn": _detect_kuwait_hint, "currencies": {"KWD"}, "tax_regimes": set(), "tier": "RELAXED"},
    "BH":  {"geo_fn": _detect_bahrain_hint, "currencies": {"BHD"}, "tax_regimes": {"VAT"}, "tier": "STRICT"},
    "JO":  {"geo_fn": _detect_jordan_hint, "currencies": {"JOD"}, "tax_regimes": set(), "tier": "RELAXED"},

    # -------------------- Southeast Asia --------------------
    "SG": {
        "geo_fn": _detect_sg_hint,
        "currencies": {"SGD"},
        "tax_regimes": {"GST"},
        "tier": "RELAXED",   # travel + cross-border common
    },

    "MY": {
        "geo_fn": lambda t: "malaysia" in (t or "").lower() or "+60" in (t or ""),
        "currencies": {"MYR"},
        "tax_regimes": {"GST"},
        "tier": "STRICT",
    },

    "TH": {
        "geo_fn": lambda t: "thailand" in (t or "").lower() or "+66" in (t or ""),
        "currencies": {"THB"},
        "tax_regimes": {"VAT"},
        "tier": "STRICT",
    },

    "ID": {
        "geo_fn": lambda t: "indonesia" in (t or "").lower() or "+62" in (t or ""),
        "currencies": {"IDR"},
        "tax_regimes": {"VAT"},
        "tier": "STRICT",
    },

    "PH": {
        "geo_fn": lambda t: "philippines" in (t or "").lower() or "+63" in (t or ""),
        "currencies": {"PHP"},
        "tax_regimes": {"VAT"},
        "tier": "STRICT",
    },

    # -------------------- East Asia --------------------
    "JP": {
        "geo_fn": _detect_jp_hint,
        "currencies": {"JPY"},
        "tax_regimes": set(),
        "tier": "RELAXED",
    },
    "CN": {
        "geo_fn": _detect_cn_hint,
        "currencies": {"CNY"},
        "tax_regimes": {"VAT"},
        "tier": "RELAXED",
    },
    "HK": {
        "geo_fn": _detect_hk_hint,
        "currencies": {"HKD"},
        "tax_regimes": set(),
        "tier": "RELAXED",
    },
    "TW": {
        "geo_fn": _detect_tw_hint,
        "currencies": {"TWD"},
        "tax_regimes": set(),
        "tier": "RELAXED",
    },
    "KR": {
        "geo_fn": _detect_kr_hint,
        "currencies": {"KRW"},
        "tax_regimes": {"VAT"},
        "tier": "RELAXED",
    },

    # -------------------- Oceania --------------------
    "NZ": {
        "geo_fn": _detect_nz_hint,
        "currencies": {"NZD"},
        "tax_regimes": {"GST"},
        "tier": "RELAXED",  # travel + cross-border common
    },
}


def _detect_geo_candidates(text: str) -> List[str]:
    """Return a list of geo candidates (region codes) based on the matrix geo_fn detectors."""
    cands: List[str] = []
    for region, cfg in GEO_RULE_MATRIX.items():
        try:
            if cfg.get("geo_fn") and cfg["geo_fn"](text):
                cands.append(region)
        except Exception:
            # Geo detection must never break analysis
            continue
    return cands



def _currency_hint_extended(text: str) -> Optional[str]:
    """Extend currency detection beyond USD/CAD/INR for global coverage.

    Notes:
    - Prefer explicit currency codes/symbols first.
    - `$` is ambiguous; treat as USD only if nothing else matches.
    """
    t = (text or "")
    tl = t.lower()

    def _has_token(s: str) -> bool:
        return f" {s.lower()} " in f" {tl} "

    # --- INR ---
    if "₹" in t or _has_token("inr") or "rupees" in tl or _has_token("rs") or "rs." in tl:
        return "INR"

    # --- CAD (before generic $) ---
    if _has_token("cad") or "c$" in t or "canadian dollar" in tl:
        return "CAD"

    # --- USD (prefer explicit) ---
    if _has_token("usd") or "us$" in t or "u.s.$" in tl or "united states dollar" in tl:
        return "USD"

    # --- Europe ---
    if "€" in t or _has_token("eur") or "euro" in tl:
        return "EUR"
    if "£" in t or _has_token("gbp") or " pound" in tl or "sterling" in tl:
        return "GBP"
    if _has_token("chf") or " swiss franc" in tl:
        return "CHF"
    if _has_token("sek") or " swedish krona" in tl:
        return "SEK"
    if _has_token("nok") or " norwegian krone" in tl:
        return "NOK"
    if _has_token("dkk") or " danish krone" in tl:
        return "DKK"

    # --- East Asia ---
    if "¥" in t or _has_token("jpy") or " yen" in tl:
        return "JPY"
    if "₩" in t or _has_token("krw") or " won" in tl:
        return "KRW"
    if "₫" in t or _has_token("vnd") or " dong" in tl:
        return "VND"
    if _has_token("cny") or _has_token("rmb") or " yuan" in tl or "renminbi" in tl or "￥" in t:
        return "CNY"
    if _has_token("hkd") or "hk$" in tl or "HK$" in t:
        return "HKD"
    if _has_token("twd") or "nt$" in tl:
        return "TWD"

    # --- Southeast Asia ---
    if _has_token("sgd") or "s$" in t or "singapore dollar" in tl:
        return "SGD"
    if _has_token("myr") or "ringgit" in tl or re.search(r'\brm\b', tl):
        return "MYR"
    if _has_token("thb") or "฿" in t or "baht" in tl:
        return "THB"
    if _has_token("idr") or "rupiah" in tl or re.search(r'\brp\b', tl):
        return "IDR"
    if _has_token("php") or "₱" in t:
        return "PHP"

    # --- Oceania ---
    if _has_token("aud") or "a$" in t or "australian dollar" in tl:
        return "AUD"
    if _has_token("nzd") or "nz$" in tl or "new zealand dollar" in tl:
        return "NZD"

    # --- Middle East ---
    if _has_token("aed") or "د.إ" in t or "dirham" in tl:
        return "AED"
    if _has_token("sar") or "riyals" in tl or " riyal" in tl:
        return "SAR"
    if _has_token("omr") or "omani rial" in tl:
        return "OMR"
    if _has_token("qar"):
        return "QAR"
    if _has_token("kwd"):
        return "KWD"
    if _has_token("bhd"):
        return "BHD"
    if _has_token("jod"):
        return "JOD"

    # --- Generic '$' (ambiguous) ---
    if "$" in t:
        return "USD"

    # Fall back to base hinting
    return _currency_hint_base(text)


def _get_geo_config_from_db(country_code: str) -> Dict[str, Any]:
    """
    Fetch geo + VAT knowledge from DB.
    Returns raw DB-backed facts (no legacy shaping).
    
    Returns:
    {
        "db_source": True/False,
        "geo_profile": {...} or None,
        "vat_rules": [...] or []
    }
    """
    try:
        geo_profile = query_geo_profile(country_code)
        vat_rules = query_vat_rules(country_code) or []

        if not geo_profile:
            return {
                "db_source": False,
                "geo_profile": None,
                "vat_rules": [],
            }

        return {
            "db_source": True,
            "geo_profile": geo_profile,
            "vat_rules": vat_rules,
        }

    except Exception as e:
        logger.warning(f"Geo DB lookup failed for {country_code}: {e}")
        return {
            "db_source": False,
            "geo_profile": None,
            "vat_rules": [],
        }


def _geo_currency_tax_consistency(
    text: str,
    merchant: Optional[str],
    reasons: List[str],
    minor_notes: List[str],
    events: List[RuleEvent],
    features: Optional[Dict] = None,
) -> float:
    """Apply geo/currency/tax consistency checks using DB-backed rules.

    Returns incremental score to add.
    """
    score_delta = 0.0
    # Track if geo-related penalty (currency/tax mismatch) was applied
    geo_penalty_applied = False

    # Extract needed values from features
    blob = text or ""
    geos = features.get("geo_guesses", []) if features else []
    currency = features.get("currency_guess") if features else None
    tax = features.get("tax_regime_guess") if features else None
    currency = _currency_hint_extended(blob)
    tax = _tax_regime_hint(blob)
    geos = _detect_geo_candidates(blob)

    # Control flag: skip geo validation for cross-border or no-geo
    skip_geo_validation = False

    # If multiple geos detected, treat as cross-border (no penalty)
    if len(geos) >= 2:
        skip_geo_validation = True
        minor_notes.append(
            "🌎 Cross-border indicators detected: multiple region hints were found ("
            + ", ".join(geos)
            + "). No penalty applied; review only if other anomalies exist."
        )
        _emit_event(
            events=events,
            reasons=None,
            rule_id="GEO_CROSS_BORDER_HINTS",
            severity="INFO",
            weight=0.0,
            message="Multiple region hints detected; treating as cross-border (no geo penalty)",
            evidence={"geo_candidates": geos, "currency_detected": currency, "tax_detected": tax},
        )

    # No geo detected → can't validate; keep as a minor note (no penalty)
    if len(geos) == 0:
        skip_geo_validation = True
        if currency or tax:
            minor_notes.append(
                f"🌍 Geo consistency could not be validated (no strong region hints). "
                f"Detected currency={currency or 'None'}, tax={tax or 'None'}."
            )
            _emit_event(
                events=events,
                reasons=None,
                rule_id="GEO_NO_REGION_HINT",
                severity="INFO",
                weight=0.0,
                message="Geo consistency not validated (no strong region hints)",
                evidence={"currency_detected": currency, "tax_detected": tax},
            )

    # Only perform geo validation if not skipped
    if not skip_geo_validation:
        country = geos[0]
        # Query DB for geo config
        cfg = _get_geo_config_from_db(country)
        geo = cfg.get("geo_profile")
        vat_rules = cfg.get("vat_rules", [])
        
        # Get geo confidence from features
        geo_confidence = features.get("geo_confidence", 0.0) if features else 0.0

        # Fallback to legacy matrix if DB query failed
        if not cfg.get("db_source"):
            legacy_cfg = GEO_RULE_MATRIX.get(country, {})
            tier = legacy_cfg.get("tier", "RELAXED")
            expected_currencies = legacy_cfg.get("currencies", set())
            expected_taxes = legacy_cfg.get("tax_regimes", set())
            is_travel = tier == "STRICT" and _is_travel_or_hospitality(blob)

            # Legacy currency mismatch
            if currency and expected_currencies and (currency not in expected_currencies):
                # Gate: only CRITICAL if geo confidence is high
                if geo_confidence < 0.6:
                    currency_weight = 0.0
                    currency_severity = "INFO"
                else:
                    currency_weight = 0.15 if is_travel else 0.30
                    currency_severity = "WARNING" if is_travel else "CRITICAL"
                score_delta += _emit_event(
                    events=events,
                    reasons=reasons,
                    rule_id="GEO_CURRENCY_MISMATCH",
                    severity=currency_severity,
                    weight=currency_weight,
                    message="Currency does not match implied region (legacy matrix)",
                    evidence={
                        "country": country,
                        "currency_detected": currency,
                        "expected_currencies": sorted(list(expected_currencies)),
                        "db_source": False,
                        "geo_confidence": geo_confidence,
                        "gated": geo_confidence < 0.6,
                    },
                    reason_text=(
                        f"💵 Currency mismatch:\n"
                        f"• Country: {country}\n"
                        f"• Receipt currency: {currency}\n"
                        f"• Expected: {sorted(list(expected_currencies))}\n"
                        "This inconsistency is uncommon in genuine receipts."
                    ),
                )
                geo_penalty_applied = True

            # Legacy tax mismatch
            if tax and expected_taxes and (tax not in expected_taxes):
                tax_weight = 0.10 if is_travel else 0.18
                tax_severity = "WARNING" if is_travel else "CRITICAL"
                score_delta += _emit_event(
                    events=events,
                    reasons=reasons,
                    rule_id="GEO_TAX_MISMATCH",
                    severity=tax_severity,
                    weight=tax_weight,
                    message="Tax regime does not match implied region (legacy matrix)",
                    evidence={
                        "country": country,
                        "tax_detected": tax,
                        "expected_taxes": sorted(list(expected_taxes)),
                        "db_source": False,
                    },
                )
                geo_penalty_applied = True

            # Travel softener applies only if geo penalty applied
            if is_travel and geo_penalty_applied:
                minor_notes.append(
                    "✈️ Travel/hospitality context detected. Geo mismatches may be legitimate (cross-border). "
                    "Severity downgraded to WARNING and penalties reduced."
                )
                _emit_event(
                    events=events,
                    reasons=None,
                    rule_id="GEO_TRAVEL_SOFTENER",
                    severity="INFO",
                    weight=0.0,
                    message="Travel/hospitality context detected; reduced geo mismatch penalties",
                    evidence={"country": country, "currency_detected": currency, "tier": tier},
                )
        else:
            # -------------------- DB-backed logic --------------------
            # Extract expected currencies from geo profile
            expected_currencies = set()
            if geo:
                if geo.get("primary_currency"):
                    expected_currencies.add(geo["primary_currency"])
                if geo.get("secondary_currencies"):
                    sec_curr = geo["secondary_currencies"]
                    if isinstance(sec_curr, str):
                        import json
                        try:
                            sec_curr = json.loads(sec_curr)
                        except Exception:
                            sec_curr = []
                    if isinstance(sec_curr, list):
                        expected_currencies.update(filter(None, sec_curr))

            # Check for travel/hospitality context
            tier = geo.get("enforcement_tier", "RELAXED").upper() if geo else "RELAXED"
            is_travel = tier == "STRICT" and _is_travel_or_hospitality(blob)

            # -------------------- Currency mismatch (DB-backed) --------------------
            if currency and expected_currencies and currency not in expected_currencies:
                # Gate: only CRITICAL if geo confidence is high
                if geo_confidence < 0.6:
                    currency_weight = 0.0
                    currency_severity = "INFO"
                else:
                    currency_weight = 0.15 if is_travel else 0.25
                    currency_severity = "WARNING" if is_travel else "CRITICAL"

                country_name = geo.get("country_name", country) if geo else country

                score_delta += _emit_event(
                    events=events,
                    reasons=reasons,
                    rule_id="GEO_CURRENCY_MISMATCH",
                    severity=currency_severity,
                    weight=currency_weight,
                    message="Currency inconsistent with country profile (DB-backed)",
                    evidence={
                        "country": country,
                        "country_name": country_name,
                        "currency_detected": currency,
                        "expected_currencies": sorted(expected_currencies),
                        "geo_profile_id": geo.get("id") if geo else None,
                        "geo_confidence": geo_confidence,
                        "gated": geo_confidence < 0.6,
                        "db_source": True,
                        "travel_softened": is_travel,
                    },
                    reason_text=(
                        f"💱 Currency mismatch:\n"
                        f"• Country detected: {country_name} ({country})\n"
                        f"• Receipt currency: {currency}\n"
                        f"• Typical currencies: {', '.join(sorted(expected_currencies))}\n"
                        f"• Source: Database (geo profile #{geo.get('id') if geo else 'N/A'})\n"
                        "This inconsistency is uncommon in genuine receipts."
                    ),
                )
                geo_penalty_applied = True

            # -------------------- VAT/Tax mismatch (DB-backed) --------------------
            if vat_rules and tax:
                # Extract expected tax names from VAT rules
                expected_tax_names = set()
                for rule in vat_rules:
                    if rule.get("tax_name"):
                        expected_tax_names.add(rule["tax_name"])

                if expected_tax_names and tax not in expected_tax_names:
                    tax_weight = 0.10 if is_travel else 0.18
                    tax_severity = "WARNING" if is_travel else "CRITICAL"

                    country_name = geo.get("country_name", country) if geo else country

                    # Build VAT rule summary for evidence
                    vat_summary = []
                    for rule in vat_rules:
                        vat_summary.append({
                            "tax_name": rule.get("tax_name"),
                            "rate": rule.get("rate"),
                            "description": rule.get("description"),
                        })

                    score_delta += _emit_event(
                        events=events,
                        reasons=reasons,
                        rule_id="GEO_TAX_MISMATCH",
                        severity=tax_severity,
                        weight=tax_weight,
                        message="Tax regime inconsistent with country VAT rules (DB-backed)",
                        evidence={
                            "country": country,
                            "country_name": country_name,
                            "tax_detected": tax,
                            "expected_tax_names": sorted(expected_tax_names),
                            "vat_rules": vat_summary,
                            "db_source": True,
                            "travel_softened": is_travel,
                        },
                        reason_text=(
                            f"🧾 Tax regime mismatch:\n"
                            f"• Country: {country_name} ({country})\n"
                            f"• Tax shown: {tax}\n"
                            f"• Expected tax types: {', '.join(sorted(expected_tax_names))}\n"
                            f"• Source: Database ({len(vat_rules)} VAT rule(s))\n"
                            "Such mismatches commonly indicate fabricated receipts."
                        ),
                    )
                    geo_penalty_applied = True

            # Travel softener applies only if geo penalty applied
            if is_travel and geo_penalty_applied:
                minor_notes.append(
                    "✈️ Travel/hospitality context detected. Geo mismatches may be legitimate (cross-border). "
                    "Severity downgraded to WARNING and penalties reduced."
                )
                _emit_event(
                    events=events,
                    reasons=None,
                    rule_id="GEO_TRAVEL_SOFTENER",
                    severity="INFO",
                    weight=0.0,
                    message="Travel/hospitality context detected; reduced geo mismatch penalties",
                    evidence={"country": country, "currency_detected": currency, "tier": tier},
                )

    # -------------------- Merchant–currency plausibility --------------------
    mc_flags = _merchant_currency_plausibility_flags(merchant, currency, blob)

    if "cad_us_healthcare" in mc_flags:
        score_delta += _emit_event(
            events=events,
            reasons=reasons,
            rule_id="MERCHANT_CURRENCY_IMPLAUSIBLE",
            severity="CRITICAL",
            weight=0.22,
            message="US healthcare-like merchant with CAD currency but no Canada hints",
            evidence={
                "merchant": merchant,
                "currency_detected": currency,
                "geo_candidates": geos,
                "flags": mc_flags,
                "note": "US healthcare provider billing in CAD without CA geography/tax evidence",
            },
            reason_text=(
                "🏥💱 Merchant–Currency Plausibility Issue: The merchant looks like a US healthcare provider "
                "(hospital/clinic/medical) but the payable currency appears to be CAD, with no Canadian "
                "geography/tax evidence."
            ),
        )

    if "inr_us_healthcare" in mc_flags:
        score_delta += _emit_event(
            events=events,
            reasons=reasons,
            rule_id="MERCHANT_CURRENCY_IMPLAUSIBLE",
            severity="CRITICAL",
            weight=0.18,
            message="US healthcare-like merchant with INR currency but no India hints",
            evidence={
                "merchant": merchant,
                "currency_detected": currency,
                "geo_candidates": geos,
                "flags": mc_flags,
                "note": "US healthcare provider billing in INR without IN geography/tax evidence",
            },
            reason_text=(
                "🏥💱 Merchant–Currency Plausibility Issue: The merchant looks like a US healthcare provider "
                "but the currency appears INR and there are no India indicators."
            ),
        )

    return score_delta


# -----------------------------------------------------------------------------
# Document type detection helper
# -----------------------------------------------------------------------------
def _currency_hint_base(text: str) -> Optional[str]:
    """Base currency hint detection (fallback for _currency_hint_extended).

    IMPORTANT:
    - `$` is ambiguous (USD, CAD, AUD, SGD, etc.) and MUST be handled last.
    - Prefer explicit currency codes/symbols first.
    - This is called by _currency_hint_extended() as a fallback.
    """
    t = (text or "")
    tl = t.lower()

    def _has_token(s: str) -> bool:
        return f" {s.lower()} " in f" {tl} "

    # --- INR ---
    if "₹" in t or _has_token("inr") or "rupees" in tl or "rs." in tl or _has_token("rs"):
        return "INR"

    # --- CAD (before generic $) ---
    if _has_token("cad") or "c$" in t or "canadian dollar" in tl:
        return "CAD"

    # --- USD (explicit only) ---
    if _has_token("usd") or "us$" in t or "u.s.$" in tl or "united states dollar" in tl:
        return "USD"

    # --- Europe ---
    if "€" in t or _has_token("eur") or "euro" in tl:
        return "EUR"
    if "£" in t or _has_token("gbp") or "pound" in tl or "sterling" in tl:
        return "GBP"

    # --- East Asia ---
    if "¥" in t or _has_token("jpy") or "yen" in tl:
        return "JPY"
    if "₩" in t or _has_token("krw") or "won" in tl:
        return "KRW"
    if _has_token("cny") or _has_token("rmb") or "yuan" in tl or "renminbi" in tl:
        return "CNY"

    # --- Oceania ---
    if _has_token("aud") or "a$" in t or "australian dollar" in tl:
        return "AUD"
    if _has_token("nzd") or "nz$" in t or "new zealand dollar" in tl:
        return "NZD"

    # --- Middle East ---
    if _has_token("aed") or "د.إ" in t or "dirham" in tl:
        return "AED"
    if _has_token("sar") or "riyal" in tl:
        return "SAR"

    # --- Southeast Asia ---
    if _has_token("sgd") or "s$" in t or "singapore dollar" in tl:
        return "SGD"
    if _has_token("myr") or "ringgit" in tl or re.search(r'\brm\b', tl):
        return "MYR"
    if _has_token("thb") or "฿" in t or "baht" in tl:
        return "THB"
    if _has_token("idr") or "rupiah" in tl or re.search(r'\brp\b', tl):
        return "IDR"
    if _has_token("php") or "₱" in t:
        return "PHP"

    # --- Generic '$' fallback (ambiguous) ---
    if "$" in t:
        return "USD"

    return None




def _detect_document_type(text: str) -> str:
    """Best-effort document type detection from OCR text.

    We intentionally keep this lightweight and explainable.

    Returns one of:
      - receipt
      - invoice
      - tax_invoice
      - order_confirmation
      - statement
      - ambiguous (when mixed signals or no clear match)

    Notes:
    - Many fakes mix labels (e.g., "INVOICE" in header but styled like a receipt).
    - We only use this as a *consistency* signal; it's not a sole hard-fail.
    - "ambiguous" is returned for both mixed signals and no matches.
    """
    t = (text or "").lower()

    # Strong signals first
    if "tax invoice" in t or "gst invoice" in t or "vat invoice" in t:
        return "tax_invoice"

    # Common doc types
    invoice_terms = ["invoice", "inv no", "invoice no", "invoice #", "amount due", "bill to", "ship to"]
    receipt_terms = ["receipt", "payment received", "paid", "paid by", "txn id", "transaction id"]
    order_terms = ["order confirmation", "order #", "order id", "tracking", "delivery"]
    statement_terms = ["statement", "account statement", "opening balance", "closing balance"]

    inv = any(s in t for s in invoice_terms)
    rec = any(s in t for s in receipt_terms)
    ordc = any(s in t for s in order_terms)
    stmt = any(s in t for s in statement_terms)

    # If multiple match, we keep a deterministic preference order.
    if stmt:
        return "statement"
    if ordc:
        return "order_confirmation"

    # Distinguish invoice vs receipt.
    # If both appear, treat as ambiguous so downstream can ask for review.
    if inv and rec:
        return "ambiguous"
    if inv:
        return "invoice"
    if rec:
        return "receipt"

    return "ambiguous"

# -----------------------------------------------------------------------------
# Tax regime and merchant–currency helpers (NEW for Rule Group 2D/2E)
# -----------------------------------------------------------------------------

def _tax_regime_hint(text: str) -> Optional[str]:
    """Best-effort tax regime hint: GST/HST/PST/VAT/SALES_TAX/None based on keywords.

    Priority: Explicit tax labels with amounts (e.g., 'VAT 5%', 'GST 18%')
    take precedence over registration numbers (e.g., 'GSTIN').
    """
    t = (text or "").lower()

    # 1. Check for explicit tax-with-percentage patterns first (highest confidence)
    #    These are the actual tax labels on the receipt, not registration numbers
    if re.search(r"\bvat\s*[\d.]+%", t) or re.search(r"\bvalue\s+added\s+tax\b", t):
        return "VAT"
    if re.search(r"\bsales\s+tax\b", t) or re.search(r"\bstate\s+tax\b", t):
        return "SALES_TAX"

    # 2. GST sub-types (always GST — CGST/SGST/IGST are India-specific)
    if "cgst" in t or "sgst" in t or "igst" in t:
        return "GST"

    # 3. GST with word boundary (avoid matching inside 'GSTIN' registration number)
    if re.search(r"\bgst\b", t) and not re.search(r"\bgstin\b", t):
        return "GST"
    # If both 'gst' and 'gstin' are present, check for standalone "GST X%" pattern
    if re.search(r"\bgst\s*[\d.]+%", t) or "goods and services tax" in t:
        return "GST"

    # 4. Canada-specific
    if "qst" in t or "quebec sales tax" in t:
        return "PST"
    if re.search(r"\bpst\b", t) or "provincial sales tax" in t:
        return "PST"
    if re.search(r"\bhst\b", t) or "harmonized sales tax" in t:
        return "HST"

    # 5. VAT without percentage (weaker signal)
    if re.search(r"\bvat\b", t):
        return "VAT"

    # 6. US-style (catch remaining)
    if any(k in t for k in ["county tax", "city tax", "local tax"]):
        return "SALES_TAX"

    # 7. Fallback: if GSTIN is present, the tax regime is GST (registration implies GST country)
    if "gstin" in t:
        return "GST"

    return None


def _merchant_currency_plausibility_flags(merchant: Optional[str], currency: Optional[str], text: str) -> List[str]:
    """
    Heuristic flags for merchant-vs-currency mismatch.
    Examples:
      - US hospital/clinic/providers issuing CAD with only US geography and no Canada hints.
    Returns list of flag identifiers.
    """
    flags: List[str] = []
    if not merchant or not currency:
        return flags

    ml = str(merchant).lower()
    t = (text or "").lower()

    # Identify healthcare-like merchants (common in reimbursements)
    healthcare_terms = ["hospital", "clinic", "health", "medical", "pharmacy", "lab", "urgent care", "dental", "imaging"]
    is_healthcare = any(k in ml for k in healthcare_terms) or any(k in t for k in healthcare_terms)

    has_us = _detect_us_state_hint(text)
    has_canada = _detect_canada_hint(text)

    # CAD + US-only + healthcare-like => suspicious
    if currency == "CAD" and has_us and not has_canada and is_healthcare:
        flags.append("cad_us_healthcare")

    # INR + US-only + healthcare-like => suspicious (rare)
    if currency == "INR" and has_us and not _detect_india_hint(text) and is_healthcare:
        flags.append("inr_us_healthcare")

    return flags


def _numbers_close(a: Optional[float], b: Optional[float], tol: float = 0.02) -> bool:
    """Compare amounts with tolerance (absolute). Default tol=0.02 for cents/paise rounding."""
    if a is None or b is None:
        return False
    return abs(a - b) <= tol

# -----------------------------------------------------------------------------
# Merchant plausibility helpers
# -----------------------------------------------------------------------------
def _merchant_plausibility_issues(merchant: Optional[str]) -> List[str]:
    """Return a list of human-readable issues that make a merchant name implausible.

    This is intentionally heuristic and explainable. We want to catch cases where
    the merchant extracted by LLM/OCR is actually a field label (e.g., 'INVOICE NO 81465-24-SHA')
    or a template artifact.

    We do NOT attempt online verification here.
    """
    if not merchant:
        return ["missing"]

    m = str(merchant).strip()
    ml = m.lower()

    issues: List[str] = []

    # 1) Merchant is actually a label / field name
    label_terms = [
        "invoice", "invoice no", "inv no", "receipt", "receipt no", "order", "order id", "transaction",
        "txn", "bill to", "ship to", "amount due", "total", "subtotal", "date"
    ]
    if any(t in ml for t in label_terms):
        issues.append("looks_like_label")

    # 1b) Merchant starts with a label prefix (e.g., "INVOICE NO ...", "RECEIPT #..."),
    # which often indicates OCR/LLM picked a field label instead of the merchant header.
    starts_with_terms = [
        "invoice", "invoice no", "inv no", "receipt", "receipt no", "order", "order id", "transaction", "txn",
        "bill to", "ship to", "amount due", "total", "subtotal", "date"
    ]
    ml_norm = ml.lstrip(":#- ")
    if any(ml_norm.startswith(t) for t in starts_with_terms):
        issues.append("starts_with_label")

    # 2) Contains too many digits or looks like an identifier
    digits = sum(ch.isdigit() for ch in m)
    letters = sum(ch.isalpha() for ch in m)
    if digits >= 4 and digits >= letters:
        issues.append("looks_like_identifier")

    # 3) Contains path/URL/email-ish artifacts
    if ("http://" in ml) or ("https://" in ml) or ("@" in ml) or (".com" in ml) or ("www." in ml):
        issues.append("contains_url_or_email")

    # 4) Too short or too long to be a merchant name
    if len(m) <= 2:
        issues.append("too_short")
    if len(m) >= 60:
        issues.append("too_long")

    # 5) Mostly punctuation/symbols
    non_alnum = sum(not ch.isalnum() and not ch.isspace() for ch in m)
    if len(m) > 0 and (non_alnum / max(1, len(m))) > 0.35:
        issues.append("too_much_punctuation")

    return issues


def _format_merchant_issue_reason(merchant: str, issues: List[str]) -> str:
    """Create a single reason string for the merchant plausibility issues."""
    if not issues:
        return ""

    pretty = {
        "missing": "merchant not found",
        "looks_like_label": "looks like a field label (e.g., INVOICE/RECEIPT/ORDER/TOTAL) rather than a business name",
        "looks_like_identifier": "looks like an identifier (contains many digits, resembles an invoice/receipt number)",
        "contains_url_or_email": "contains URL/email-like text",
        "too_short": "too short to be a merchant name",
        "too_long": "unusually long for a merchant name",
        "too_much_punctuation": "contains unusually high punctuation/symbol density",
    }

    bullets = [f"- {pretty.get(i, i)}" for i in issues]
    return (
        "🏪 Merchant Plausibility Issue: The extracted merchant name appears implausible.\n"
        f"   • Extracted: '{merchant}'\n"
        "   • Why this matters: Real receipts usually show a clear business/merchant name at the top.\n"
        "   • Detected issues:\n"
        + "\n".join([f"     {b}" for b in bullets])
    )
# -----------------------------------------------------------------------------
# Reason severity helpers
# -----------------------------------------------------------------------------

from datetime import datetime
from typing import Optional
import re

def _parse_date_best_effort(date_str: Optional[str]):
    """
    Parse a date string from OCR/LLM into `datetime.date`.
    
    LOCALE-AWARE: For ambiguous formats like DD/MM/YY, tries DD/MM/YY before MM/DD/YY
    to handle international receipts (India, EU, etc.)

    Returns:
        datetime.date or None
    """
    if not date_str:
        return None

    s = str(date_str).strip()

    # PRIORITY: Try unambiguous ISO 8601 (YYYY-MM-DD) FIRST.
    # Must come before the DD/MM regex, which incorrectly matches substrings
    # of ISO dates (e.g., '2026-02-24' → regex finds '26-02-24' → wrong parse).
    iso_match = re.search(r'\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b', s)
    if iso_match:
        for fmt in ["%Y-%m-%d", "%Y/%m/%d"]:
            try:
                parsed = datetime.strptime(iso_match.group(0), fmt).date()
                if 1990 <= parsed.year <= datetime.now().year + 2:
                    return parsed
            except Exception:
                pass

    # Extract date pattern from text (handles "Date: 13/06/23" or "13/06/23 10:30")
    date_match = re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', s)
    if date_match:
        date_part = date_match.group(0)
        
        # LOCALE-AWARE: Try DD/MM first (international) before MM/DD (US-only)
        # Try DD/MM/YYYY first (international)
        for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"]:
            try:
                parsed = datetime.strptime(date_part, fmt).date()
                # Sanity check: reject if year is in future or before 1990
                if 1990 <= parsed.year <= datetime.now().year + 1:
                    return parsed
            except Exception:
                pass
        
        # Fallback to MM/DD if DD/MM failed (US format)
        for fmt in ["%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y"]:
            try:
                parsed = datetime.strptime(date_part, fmt).date()
                if 1990 <= parsed.year <= datetime.now().year + 1:
                    return parsed
            except Exception:
                pass

    # Try full string, first token, last token (handles "Date: 2024/08/15 10:22")
    candidates = [s]
    parts = s.split()
    if parts:
        candidates.append(parts[0])
        candidates.append(parts[-1])

    # Other common formats (YYYY-MM-DD, YYYY/MM/DD, etc.)
    fmts = [
        "%Y-%m-%d",  # 2024-08-15
        "%Y/%m/%d",  # 2024/08/15
        "%d/%m/%Y",  # 15/08/2024 (international)
        "%d-%m-%Y",  # 15-08-2024
        "%m/%d/%Y",  # 08/15/2024 (US)
        "%m-%d-%Y",  # 08-15-2024
        "%y/%m/%d",  # 24/08/15 (YY/MM/DD)
        "%d/%m/%y",  # 15/08/24 (international)
        "%d-%m-%y",  # 15-08-24
        "%m/%d/%y",  # 08/15/24 (US)
    ]
    
    for cand in candidates:
        c = cand.strip().strip(",;|")
        for fmt in fmts:
            try:
                parsed = datetime.strptime(c, fmt).date()
                if 1990 <= parsed.year <= datetime.now().year + 1:
                    return parsed
            except Exception:
                pass

    # ISO-ish fallback (YYYY-MM-DDTHH:MM:SS)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except Exception:
        return None


def _parse_pdf_creation_datetime_best_effort(value):
    """
    Parse PDF metadata creation/modification datetime into `datetime`.

    Handles PDF format: D:YYYYMMDDHHMMSS(+TZ)
    Returns:
      - datetime on success
      - None on failure
    """
    if not value:
        return None

    # Already datetime-like
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        return value

    s = str(value).strip()

    # PDF date format e.g. D:20251130082231+00'00'
    if s.startswith("D:") and len(s) >= 10:
        core = s
        if "+" in core:
            core = core.split("+")[0]
        if "-" in core[2:]:
            core = core.split("-")[0]

        for fmt in ["D:%Y%m%d%H%M%S", "D:%Y%m%d"]:
            try:
                return datetime.strptime(core, fmt)
            except Exception:
                pass

    for fmt in [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y%m%d%H%M%S",
        "%Y/%m/%d",
        "%Y/%m/%d %H:%M:%S",
    ]:
        try:
            return datetime.strptime(s.split()[0], fmt)
        except Exception:
            pass

    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

def _push_reason(reasons: List[str], msg: str, severity: str = "INFO") -> None:
    """Append a reason with a consistent severity tag for the ensemble layer.

    Downstream (ensemble) can scan these tags without parsing emojis/prose.

    Supported severities:
      - HARD_FAIL: should strongly bias to fake unless overridden by policy
      - CRITICAL: strong indicator; if conflicting with other engines, prefer review
      - INFO: normal explanatory reason
    """
    sev = (severity or "INFO").upper().strip()
    reasons.append(f"[{sev}] {msg}")


def _is_hard_fail_reason(reason: str) -> bool:
    return (reason or "").lstrip().startswith("[HARD_FAIL]")


def _is_critical_reason(reason: str) -> bool:
    return (reason or "").lstrip().startswith("[CRITICAL]")


# ---------------------------------------------------------------------------
# Learned Rules Mini-Engine
# ---------------------------------------------------------------------------

def _learned_rule_dedupe_key(raw: str, parsed: Optional[Dict[str, Any]] = None) -> str:
    """Stable dedupe key for learned rule triggers.
    
    Uses semantic key (pattern + missing list) for better deduplication.
    Falls back to normalized raw string if parsing unavailable.
    """
    if parsed:
        pattern = parsed.get("pattern", "unknown")
        missing = parsed.get("missing", [])
        if missing:
            # Semantic key: pattern + sorted missing list
            missing_key = tuple(sorted(missing)) if isinstance(missing, list) else ()
            return f"{pattern}:{missing_key}"
        return pattern
    
    # Fallback: normalized raw string
    s = (raw or "").strip().lower()
    s = re.sub(r"\s+", " ", s)  # collapse whitespace
    return s


def _parse_learned_rule(raw: str) -> Dict[str, Any]:
    """Parse a learned rule string into structured fields."""
    out: Dict[str, Any] = {
        "raw": raw or "",
        "pattern": "unknown",
        "times_seen": None,
        "confidence_adjustment": 0.0,
        "missing": [],
    }

    m = re.search(r"pattern detected:\s*([a-zA-Z0-9_\-]+)", raw or "", flags=re.IGNORECASE)
    if m:
        out["pattern"] = (m.group(1) or "unknown").strip()

    m2 = re.search(r"identified by users\s+(\d+)\s+time", raw or "", flags=re.IGNORECASE)
    if m2:
        try:
            out["times_seen"] = int(m2.group(1))
        except Exception:
            out["times_seen"] = None

    m3 = re.search(r"Confidence adjustment:\s*([+\-]?[0-9]*\.?[0-9]+)", raw or "", flags=re.IGNORECASE)
    if m3:
        try:
            out["confidence_adjustment"] = float(m3.group(1))
        except Exception:
            out["confidence_adjustment"] = 0.0
    
    # Parse missing elements list for better deduplication
    if "missing critical elements:" in (raw or "").lower():
        # Extract comma-separated list after "Missing critical elements:"
        m4 = re.search(r"Missing critical elements:\s*([^.]+)", raw or "", flags=re.IGNORECASE)
        if m4:
            missing_str = m4.group(1).strip()
            out["missing"] = [x.strip() for x in missing_str.split(",") if x.strip()]

    return out


def _apply_learned_rules(
    *,
    triggered_rules: List[Any],
    events: List["RuleEvent"],
    reasons: List[str],
    tf: Dict[str, Any],
    doc_profile: Dict[str, Any],
    missing_fields_enabled: bool,
    dp_conf: float,
    optional_subtype: bool,
) -> float:
    """Apply learned-rule adjustments safely with doc-profile gating.

    Guarantees:
    - Dedupe duplicate triggers (semantic-first; raw fallback).
    - Suppress `missing_elements` when missing-field gate is OFF.
    - Gate learned patterns via DocumentProfile.disabled_rules (like R7/R16).
    - Cap total learned contribution via DocumentProfile.max_learned_contribution.
    - Only non-suppressed adjustments affect score.
    - Soft-gating factors are applied exactly once.
    - Adjustment is clamped to a sane range to avoid runaway scores.
    
    Pattern to Rule ID Mapping:
    - spacing_anomaly → LR_SPACING_ANOMALY
    - missing_elements → LR_MISSING_ELEMENTS
    - invalid_address → LR_INVALID_ADDRESS
    """

    def _safe_float(v: Any, default: float = 0.0) -> float:
        try:
            if v is None:
                return float(default)
            f = float(v)
            if f != f:  # NaN
                return float(default)
            if f == float("inf") or f == float("-inf"):
                return float(default)
            return f
        except Exception:
            return float(default)

    def _semantic_key(parsed: Dict[str, Any], raw: str) -> str:
        """Prefer a semantic dedupe key; fall back to a normalized raw string."""
        try:
            pat = str(parsed.get("pattern") or "").strip().lower()
            missing = parsed.get("missing") or parsed.get("missing_fields") or []
            if isinstance(missing, str):
                missing = [missing]
            if isinstance(missing, list):
                missing_norm = tuple(sorted({str(x).strip().lower() for x in missing if str(x).strip()}))
            else:
                missing_norm = tuple()
            if pat or missing_norm:
                return f"{pat}|{missing_norm}"
        except Exception:
            pass
        # Raw fallback (collapse whitespace)
        r = " ".join(str(raw or "").strip().lower().split())
        return r

    # Pattern to Rule ID mapping for doc-profile gating
    PATTERN_TO_RULE_ID = {
        "spacing_anomaly": "LR_SPACING_ANOMALY",
        "missing_elements": "LR_MISSING_ELEMENTS",
        "invalid_address": "LR_INVALID_ADDRESS",
    }
    
    # FUTURE ENHANCEMENT: Corroboration logic
    # For higher confidence, require multiple signals:
    # - spacing_anomaly only counts if 2+ learned patterns fire
    # - OR if metadata anomaly (R1_SUSPICIOUS_SOFTWARE) + layout anomaly both exist
    # This prevents single noisy learned patterns from dominating the verdict.
    # Implementation: Track pattern_count, check for corroborating rules in events list.
    
    # Get DocumentProfile object for gating
    from app.pipelines.doc_profiles import get_profile_for_doc_class, should_apply_rule
    doc_class = tf.get("doc_class", "UNKNOWN")
    profile_obj = get_profile_for_doc_class(doc_class)
    
    # Track total learned contribution for capping
    non_suppressed_adjustment = 0.0
    total_learned_contribution = 0.0

    seen: set = set()
    for rule in (triggered_rules or []):
        raw = str(rule or "")

        # Parse once; never let parsing break the main engine.
        try:
            parsed = _parse_learned_rule(raw)
            if not isinstance(parsed, dict):
                parsed = {}
        except Exception:
            parsed = {}

        pattern = parsed.get("pattern") or "unknown"
        conf_adj = _safe_float(parsed.get("confidence_adjustment"), default=0.0)

        # Dedupe: semantic-first
        key = _semantic_key(parsed, raw)
        if not key or key in seen:
            continue
        seen.add(key)

        # Identify missing-fields-dependent learned rules
        raw_l = str(raw).lower()
        pat_l = str(pattern).strip().lower()

        is_missing_fields_dependent = (
            ("missing_elements" in raw_l) or (pat_l == "missing_elements")
            or ("invalid_address" in raw_l) or (pat_l == "invalid_address")
        )

        # DOC-PROFILE GATING: Check if this learned pattern is disabled for this doc type
        learned_rule_id = PATTERN_TO_RULE_ID.get(pat_l)
        profile_gated = False
        if learned_rule_id and not should_apply_rule(profile_obj, learned_rule_id):
            profile_gated = True
            logger.info(f"Learned pattern '{pat_l}' suppressed by doc-profile gating for {doc_class}")
        
        # Suppress when missing-field gate is OFF (audit-only)
        suppressed = bool(is_missing_fields_dependent and (not missing_fields_enabled)) or profile_gated
        
        # POS-SPECIFIC SUPPRESSION: Don't penalize missing optional fields
        # If POS receipt has core fields (total/merchant/currency), suppress missing_elements
        if not suppressed and pat_l == "missing_elements":
            doc_subtype = doc_profile.get("subtype") if isinstance(doc_profile, dict) else None
            is_pos = doc_subtype and str(doc_subtype).upper().startswith("POS_")
            
            if is_pos:
                # Check if core POS fields present
                has_total = bool(tf.get("total_amount"))
                has_merchant = bool(tf.get("merchant_candidate"))
                has_currency = bool(tf.get("currency_symbols") or tf.get("has_currency"))
                has_line_items = bool(tf.get("has_line_items"))
                
                # Suppress if core transaction evidence exists
                core_fields_present = (has_total or has_line_items) and has_merchant and has_currency
                if core_fields_present:
                    suppressed = True

        # POS-SPECIFIC SUPPRESSION: Don't penalize invalid_address for POS receipts
        if not suppressed and pat_l == "invalid_address":
            doc_subtype = doc_profile.get("subtype", "").upper()
            is_pos = doc_subtype.startswith("POS_")
            
            if is_pos:
                # For POS, address is optional per domain pack
                # Suppress if core fields present (merchant + currency)
                has_merchant = bool(tf.get("merchant_candidate"))
                has_currency = bool(tf.get("currency_symbols") or tf.get("has_currency"))
                
                if has_merchant and has_currency:
                    suppressed = True
        
        # GATE SUPPRESSION: Don't penalize spacing_anomaly when missing-field gate is disabled
        # or doc confidence is low (likely OCR quality issue, not fraud)
        if not suppressed and pat_l == "spacing_anomaly":
            doc_profile_confidence = doc_profile.get("confidence", 0.0)
            
            # Suppress if missing-field gate is disabled (low doc confidence)
            if not missing_fields_enabled:
                suppressed = True
            # Suppress if doc confidence is low (< 0.6)
            elif doc_profile_confidence < 0.6:
                suppressed = True
            else:
                # POS-SPECIFIC SUPPRESSION: Don't penalize for high uppercase POS receipts
                doc_subtype = doc_profile.get("subtype", "").upper()
                is_pos = doc_subtype.startswith("POS_")
                
                # Check if receipt has high uppercase ratio (common for thermal POS)
                if is_pos and tf.get("full_text"):
                    lines = [l.strip() for l in tf["full_text"].split('\n') if l.strip()]
                    if lines:
                        uppercase_lines = sum(1 for line in lines if len(line) > 3 and line.isupper())
                        uppercase_ratio = uppercase_lines / len(lines)
                        
                        # If >50% lines are uppercase, suppress spacing_anomaly
                        if uppercase_ratio > 0.5:
                            suppressed = True

        # Clamp per-rule adjustment to avoid runaway behavior from noisy feedback.
        # (You can widen this later, but this is safe for early production.)
        conf_adj = max(-0.50, min(0.50, float(conf_adj)))

        if not suppressed:
            # Track contribution for profile cap
            total_learned_contribution += float(conf_adj)
            non_suppressed_adjustment += float(conf_adj)

        # User-facing reasons: mark suppressed explicitly
        if suppressed:
            reasons.append(f"ℹ️ [INFO] Learned Rule (suppressed): {raw}")
        else:
            reasons.append(f"[INFO] 🎓 Learned Rule: {raw}")

        gating = {
            "doc_family": doc_profile.get("family") if isinstance(doc_profile, dict) else None,
            "doc_subtype": doc_profile.get("subtype") if isinstance(doc_profile, dict) else None,
            "doc_profile_confidence": _safe_float(dp_conf, default=0.0),
            "optional_subtype": bool(optional_subtype),
            "missing_fields_enabled": bool(missing_fields_enabled),
            "suppressed": bool(suppressed),
            "profile_gated": bool(profile_gated),
            "learned_rule_id": learned_rule_id,
        }

        # Audit-only event (never contributes to score directly)
        _emit_event(
            events=events,
            reasons=None,
            rule_id="LR_LEARNED_PATTERN",
            severity="INFO",
            weight=0.0,
            message=(
                "Learned rule triggered (suppressed by missing-field gate)"
                if suppressed
                else "Learned rule triggered"
            ),
            evidence={
                "pattern": pattern,
                "times_seen": parsed.get("times_seen"),
                "missing": parsed.get("missing") or parsed.get("missing_fields"),
                "raw": raw,
                "confidence_adjustment": conf_adj,
                "suppressed": suppressed,
                "applied_to_score": (not suppressed),
                "gating": gating,
            },
            confidence_factor=1.0,
        )

    # ---- Final soft gating (apply ONCE) ----
    dp_conf_f = _safe_float(dp_conf, default=0.0)
    if dp_conf_f < 0.55:
        # Learned rules are noisy when doc type is uncertain
        non_suppressed_adjustment *= 0.25

        # Hard cap: learned rules must never dominate the verdict
        non_suppressed_adjustment = max(
            min(non_suppressed_adjustment, 0.05), -0.05
        )

    if optional_subtype:
        non_suppressed_adjustment *= 0.60

    # Apply profile-based cap on total learned contribution
    max_cap = profile_obj.max_learned_contribution
    if max_cap is not None and total_learned_contribution > max_cap:
        capped_adjustment = max_cap
        logger.info(
            f"Learned contribution capped: {total_learned_contribution:.3f} → {max_cap:.3f} "
            f"(profile={doc_class}, cap={max_cap})"
        )
        
        # Emit INFO audit event for explainability
        _emit_event(
            events=events,
            reasons=None,
            rule_id="LR_CAP_APPLIED",
            severity="INFO",
            weight=0.0,
            message=f"Learned rule contribution capped for {doc_class}",
            evidence={
                "cap": max_cap,
                "original": round(total_learned_contribution, 3),
                "capped_to": round(capped_adjustment, 3),
                "profile": doc_class,
                "reduction": round(total_learned_contribution - max_cap, 3),
            },
            reason_text=None,
            confidence_factor=1.0,
        )
    else:
        capped_adjustment = total_learned_contribution
    
    # Clamp total adjustment to avoid runaway scores
    out = max(-1.0, min(1.0, float(capped_adjustment)))
    return out


def _score_and_explain(
    features: ReceiptFeatures,
    apply_learned: bool = True,
    vision_assessment: Optional[Dict[str, Any]] = None,
) -> ReceiptDecision:
    score = 0.0
    reasons: List[str] = []
    minor_notes: List[str] = []
    events: List[RuleEvent] = []

    ff = features.file_features
    tf = features.text_features
    lf = features.layout_features
    fr = features.forensic_features

    conf_factor = _confidence_factor_from_features(ff, tf, lf, fr)
    
    # ============================================================================
    # ARCHITECTURE FLIP: Profile-Based Rule Gating
    # Load document profile and gate rules based on document type
    # ============================================================================
    from app.pipelines.doc_profiles import (
        get_profile_for_doc_class,
        should_apply_rule,
        get_rule_severity,
    )
    
    doc_class = tf.get("doc_class", "UNKNOWN")
    doc_profile_obj = get_profile_for_doc_class(doc_class)
    
    logger.info(f"Applying rules for doc_class={doc_class}, profile={doc_profile_obj.doc_class}, risk={doc_profile_obj.fraud_surface}")

    def emit_event(*, events, reasons, rule_id, severity, weight, message, evidence=None, reason_text=None):
        # Apply profile-based severity override
        severity = get_rule_severity(doc_profile_obj, rule_id, severity)
        
        return _emit_event(
            events=events,
            reasons=reasons,
            rule_id=rule_id,
            severity=severity,
            weight=weight,
            message=message,
            evidence=evidence,
            reason_text=reason_text,
            confidence_factor=conf_factor,
        )

    # ---------------------------------------------------------------------------
    # Vision veto (veto-only): if vision detects tampering, mark HARD_FAIL.
    # Vision can never *increase* trust; it only provides a downgrade/veto signal.
    # ---------------------------------------------------------------------------
    try:
        va = vision_assessment or {}
        vi = str(va.get("visual_integrity") or "").strip().lower()
        vconf = va.get("confidence")
        try:
            vconf_f = float(vconf) if vconf is not None else 0.0
        except Exception:
            vconf_f = 0.0

        # Accept alternate key names for backward compatibility
        if not vi and isinstance(va.get("raw"), dict):
            vi = str(va["raw"].get("visual_integrity") or "").strip().lower()

        if vi == "tampered":
            emit_event(
                events=events,
                reasons=reasons,
                rule_id="V1_VISION_TAMPERED",
                severity="HARD_FAIL",
                weight=0.50,  # weight irrelevant for label; HARD_FAIL drives label=fake
                message="Vision detected clear tampering",
                evidence={
                    "visual_integrity": "tampered",
                    "confidence": vconf_f,
                    "observable_reasons": va.get("observable_reasons")
                    or va.get("claims")
                    or (va.get("raw") or {}).get("observable_reasons")
                    or [],
                },
                reason_text="🚨 Vision detected clear tampering (veto)",
            )
    except Exception as e:
        logger.warning(f"Vision veto evaluation failed: {e}")

    source_type = ff.get("source_type")

    blob_text = _join_text(tf, lf)
    doc_type_hint = _detect_document_type(blob_text)

    # ---------------------------------------------------------------------------
    # GeoRuleMatrix wiring (geo/currency/tax consistency)
    # Must never throw; must never return early.
    # ---------------------------------------------------------------------------
    merchant_hint = (
        tf.get("merchant")
        or tf.get("merchant_name")
        or tf.get("vendor")
        or tf.get("merchant_extracted")
    )
    try:
        score += _geo_currency_tax_consistency(
            text=blob_text,
            merchant=merchant_hint,
            reasons=reasons,
            minor_notes=minor_notes,
            events=events,
            features=tf,
        )
    except Exception:
        minor_notes.append("Geo consistency checks skipped due to an internal error.")

    # ---------------------------------------------------------------------------
    # RULE GROUP 1: Producer / metadata anomalies
    # ---------------------------------------------------------------------------
    producer = ff.get("producer", "")
    creator = ff.get("creator", "")
    # Split tools into high-risk (HARD_FAIL) vs medium-risk (WARNING)
    high_risk_tools = [
        "canva", "photoshop", "illustrator", "sketch", "figma",
        "affinity", "gimp", "inkscape", "coreldraw", "pixlr",
        "fotor", "befunky", "snappa", "crello", "desygner",
    ]
    
    # PDF utilities are common for legitimate workflows (merge, compress, convert)
    # Only WARNING unless combined with other fraud signals
    medium_risk_tools = [
        "wps", "ilovepdf", "smallpdf", "pdfcandy", "sejda",
    ]
    
    producer_lower = (producer or "").lower()
    creator_lower = (creator or "").lower()
    
    # Check high-risk tools first (HARD_FAIL)
    if any(tool in producer_lower or tool in creator_lower for tool in high_risk_tools):
        tool_found = next((t for t in high_risk_tools if t in producer_lower or t in creator_lower), "editing software")
        score += emit_event(
            events=events,
            reasons=reasons,
            rule_id="R1_SUSPICIOUS_SOFTWARE",
            severity="HARD_FAIL",
            weight=0.50,
            message=f"Suspicious editing software detected: {tool_found}",
            evidence={"producer": producer, "creator": creator, "tool": tool_found, "risk_level": "high"},
            reason_text=f"🚨 Suspicious Software Detected: '{tool_found}' - This software is commonly used to create fake receipts.",
        )
    # Check medium-risk tools (WARNING only)
    elif any(tool in producer_lower or tool in creator_lower for tool in medium_risk_tools):
        tool_found = next((t for t in medium_risk_tools if t in producer_lower or t in creator_lower), "pdf utility")
        score += emit_event(
            events=events,
            reasons=reasons,
            rule_id="R1_SUSPICIOUS_SOFTWARE",
            severity="WARNING",
            weight=0.10,
            message=f"PDF utility detected: {tool_found}",
            evidence={"producer": producer, "creator": creator, "tool": tool_found, "risk_level": "medium"},
            reason_text=f"⚠️ PDF Utility Detected: '{tool_found}' - Document has been processed by PDF utility software.",
        )

    if not ff.get("creation_date"):
        minor_notes.append("Document is missing a creation date in its metadata.")
    
    if not ff.get("mod_date"):
        minor_notes.append("Document is missing a modification date in its metadata.")
    
    if source_type == "image" and not ff.get("exif_present"):
        minor_notes.append("Image has no EXIF data (could be a screenshot or exported image).")

    # R1B_METADATA_TIMESTAMP_ANOMALY: creation vs modification date gap
    # Expert insight: If a PDF was created months ago but modified very recently,
    # someone likely edited it (changed amounts, dates, merchant name).
    # Legitimate workflows (scan → store) don't produce large creation-to-mod gaps.
    try:
        _cd_raw = ff.get("creation_date")
        _md_raw = ff.get("mod_date")
        if _cd_raw and _md_raw:
            _cd_dt = _parse_pdf_creation_datetime_best_effort(_cd_raw)
            _md_dt = _parse_pdf_creation_datetime_best_effort(_md_raw)
            if _cd_dt and _md_dt:
                _meta_gap = abs((_md_dt - _cd_dt).total_seconds())
                _meta_gap_hours = _meta_gap / 3600.0
                _meta_gap_days = _meta_gap / 86400.0

                # Small gaps (< 1 hour) are normal — tool processing, save/export.
                # Medium gaps (1-30 days) — could be legitimate re-export.
                # Large gaps (> 30 days) — very suspicious, document was revisited.
                if _meta_gap_days > 30:
                    score += emit_event(
                        events=events,
                        reasons=reasons,
                        rule_id="R1B_METADATA_TIMESTAMP_ANOMALY",
                        severity="CRITICAL",
                        weight=0.25,
                        message=f"Document modified {int(_meta_gap_days)} days after creation",
                        evidence={
                            "creation_date": str(_cd_dt),
                            "mod_date": str(_md_dt),
                            "gap_days": round(_meta_gap_days, 1),
                            "gap_hours": round(_meta_gap_hours, 1),
                        },
                        reason_text=(
                            f"📄⚠️ Metadata Anomaly: Document was modified {int(_meta_gap_days)} days "
                            f"after it was created. This indicates the document was reopened "
                            f"and edited, which is uncommon for genuine receipts."
                        ),
                    )
                elif _meta_gap_hours > 24:
                    # 1-30 day gap: mild warning
                    score += emit_event(
                        events=events,
                        reasons=reasons,
                        rule_id="R1B_METADATA_TIMESTAMP_ANOMALY",
                        severity="WARNING",
                        weight=0.08,
                        message=f"Document modified {round(_meta_gap_hours, 1)} hours after creation",
                        evidence={
                            "creation_date": str(_cd_dt),
                            "mod_date": str(_md_dt),
                            "gap_days": round(_meta_gap_days, 1),
                            "gap_hours": round(_meta_gap_hours, 1),
                        },
                        reason_text=(
                            f"📄 Metadata Note: Document was modified {round(_meta_gap_days, 1)} days "
                            f"after creation. Could indicate re-processing or editing."
                        ),
                    )
    except Exception as e:
        logger.warning(f"R1B_METADATA_TIMESTAMP_ANOMALY check failed: {e}")

    # ---------------------------------------------------------------------------
    # RULE GROUP 2: Text-based checks (amounts, merchant, dates)
    # ---------------------------------------------------------------------------
    has_any_amount = tf.get("has_any_amount", False)
    total_line_present = tf.get("total_line_present", False)
    has_total_value = _has_total_value(tf)
    total_mismatch = tf.get("total_mismatch", False)
    has_date = tf.get("has_date", False)
    merchant_candidate = tf.get("merchant_candidate") or tf.get("merchant")

    # Emit merchant extraction debug event (huge for debugging)
    emit_event(
        events=events,
        reasons=None,
        rule_id="MERCHANT_DEBUG",
        severity="INFO",
        weight=0.0,
        message="Merchant extraction debug",
        evidence={
            "merchant_candidate": tf.get("merchant_candidate"),
            "merchant_final": tf.get("merchant"),
            "merchant_candidate_debug": tf.get("merchant_candidate_debug"),
        },
    )

    # Doc-aware expectations (prevents false-positives on logistics docs etc.)
    # Use legacy_doc_profile to avoid collision with DocumentProfile object (profile_obj)
    legacy_doc_profile = _get_doc_profile(tf, doc_type_hint=doc_type_hint)
    expects_amounts = _expects_amounts(tf, legacy_doc_profile)
    expects_total_line = _expects_total_line(tf, legacy_doc_profile)
    expects_date = _expects_date(tf, legacy_doc_profile)
    
    # Emit doc profiling debug event for diagnostics
    emit_event(
        events=events,
        reasons=None,
        rule_id="DOC_PROFILE_DEBUG",
        severity="INFO",
        weight=0.0,
        message="Document profiling diagnostics",
        evidence={
            "doc_subtype_guess": legacy_doc_profile.get("subtype"),
            "doc_family_guess": legacy_doc_profile.get("family"),
            "doc_profile_confidence": legacy_doc_profile.get("confidence"),
            "doc_profile_evidence": legacy_doc_profile.get("evidence"),
            "document_intent": tf.get("document_intent"),
        },
    )

    emit_event(
        events=events,
        reasons=None,
        rule_id="DOMAIN_PACK_VALIDATION",
        severity="INFO",
        weight=0.0,
        message="Domain pack validation diagnostics",
        evidence={
            "domain_validation": tf.get("domain_validation"),
        },
    )
    missing_fields_enabled = _missing_field_penalties_enabled(tf, doc_profile=legacy_doc_profile)
    
    # Debug logging (not printed to console in production)
    logger.debug("\n🔍 GATE CHECK:")
    logger.debug(f"   geo_country: {tf.get('geo_country_guess')} (conf: {tf.get('geo_confidence')})")
    logger.debug(f"   doc_subtype: {tf.get('doc_subtype_guess')} (conf: {tf.get('doc_profile_confidence')})")
    logger.debug(f"   document_intent: {tf.get('document_intent')}")
    logger.debug(f"   missing_fields_enabled: {missing_fields_enabled}")
    logger.debug(f"   Total events before gate: {len(events)}")
    
    # Always emit gate decision for transparency (audit event)
    if missing_fields_enabled:
        gate_message = "Missing-field penalties ENABLED"
    else:
        # Determine specific reason for disabling
        doc_subtype_opt = legacy_doc_profile.get("subtype")
        dp_conf = legacy_doc_profile.get("confidence", 0.0)
        if doc_subtype_opt == "UNKNOWN" or not doc_subtype_opt:
            disable_reason = f"doc subtype is UNKNOWN (confidence={dp_conf:.2f})"
        elif dp_conf < 0.4:
            disable_reason = f"doc profile confidence too low ({dp_conf:.2f} < 0.4)"
        else:
            disable_reason = f"doc profile confidence below threshold ({dp_conf:.2f}, subtype={doc_subtype_opt})"
        gate_message = f"Missing-field penalties DISABLED: {disable_reason}"
    
    _emit_event(
        events=events,
        reasons=None,
        rule_id="GATE_MISSING_FIELDS",
        severity="INFO",
        weight=0.0,
        message=gate_message,
        evidence=_missing_field_gate_evidence(tf, legacy_doc_profile),
        confidence_factor=1.0,
    )
    
    logger.debug(f"   Total events after gate emission: {len(events)}")

    # If upstream extractors (LayoutLM / DONUT / ensemble) already provided a total,
    # do NOT flag "No Total Line" purely based on missing TOTAL keyword/line.
    extracted_total_raw = (
        tf.get("total_amount")
        or tf.get("normalized_total")
        or tf.get("total")
        or tf.get("grand_total")
    )

    def _to_float_amount(v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            try:
                return float(v)
            except Exception:
                return None
        s = str(v)
        s = s.replace(",", "").replace("$", "").replace("₹", "").strip()
        # remove common currency codes if present inline
        s = re.sub(r"\b(usd|inr|cad|aud|eur|gbp)\b", "", s, flags=re.IGNORECASE).strip()
        try:
            return float(s)
        except Exception:
            return None

    extracted_total_val = _to_float_amount(extracted_total_raw)
    has_extracted_total = extracted_total_val is not None and extracted_total_val > 0

    if not has_any_amount:
        if expects_amounts:
            # Only penalize if missing-field gate is enabled
            if missing_fields_enabled:
                score += emit_event(
                    events=events,
                    reasons=reasons,
                    rule_id="R5_NO_AMOUNTS",
                    severity="CRITICAL",
                    weight=0.40,
                    message="No currency amounts detected in document",
                    evidence={
                        "has_any_amount": False,
                        "doc_family": legacy_doc_profile.get("family"),
                        "doc_subtype": legacy_doc_profile.get("subtype"),
                        "doc_profile_confidence": legacy_doc_profile.get("confidence"),
                        "missing_fields_enabled": missing_fields_enabled,
                        "missing_field_gate": _missing_field_gate_evidence(tf, legacy_doc_profile),
                    },
                    reason_text="💰 No Amounts Detected: The document contains no recognizable currency amounts.",
                )
        else:
            minor_notes.append(
                "Amounts were not detected, but this document type often does not contain totals/amounts."
            )
            emit_event(
                events=events,
                reasons=None,
                rule_id="R5_NO_AMOUNTS_OPTIONAL_FOR_DOC",
                severity="INFO",
                weight=0.0,
                message="No amounts detected but amounts are optional for this doc subtype",
                evidence={
                    "has_any_amount": False,
                    "doc_family": legacy_doc_profile.get("family"),
                    "doc_subtype": legacy_doc_profile.get("subtype"),
                    "doc_profile_confidence": legacy_doc_profile.get("confidence"),
                },
            )

    if has_any_amount and not total_line_present:
        # If we can still extract a usable total value, do not penalize as "No Total Line".
        has_usable_total_value = bool(_has_total_value(tf) or has_extracted_total)

        if expects_total_line and not has_usable_total_value:
            # Only penalize if missing-field gate is enabled
            if missing_fields_enabled:
                score += emit_event(
                    events=events,
                    reasons=reasons,
                    rule_id="R6_NO_TOTAL_LINE",
                    severity="CRITICAL",
                    weight=0.15,
                    message="Amounts present but no total line found",
                    evidence={
                        "has_any_amount": True,
                        "total_line_present": False,
                        "has_usable_total_value": has_usable_total_value,
                        "doc_family": legacy_doc_profile.get("family"),
                        "doc_subtype": legacy_doc_profile.get("subtype"),
                        "doc_profile_confidence": legacy_doc_profile.get("confidence"),
                        "missing_fields_enabled": missing_fields_enabled,
                        "missing_field_gate": _missing_field_gate_evidence(tf, legacy_doc_profile),
                    },
                    reason_text="🧾 No Total Line: Document has amounts but no clear total/grand total line.",
                )
        else:
            minor_notes.append(
                "Total line keyword was not detected, but this document type may not use a TOTAL label (or a total value was extracted)."
            )
            emit_event(
                events=events,
                reasons=None,
                rule_id="R6_NO_TOTAL_LINE_OPTIONAL_FOR_DOC",
                severity="INFO",
                weight=0.0,
                message="No TOTAL line keyword, but optional for doc subtype or total value exists",
                evidence={
                    "has_any_amount": True,
                    "total_line_present": False,
                    "has_usable_total_value": has_usable_total_value,
                    "doc_family": legacy_doc_profile.get("family"),
                    "doc_subtype": legacy_doc_profile.get("subtype"),
                    "doc_profile_confidence": legacy_doc_profile.get("confidence"),
                },
            )

    # ---------------------------------------------------------------------------
    # R7: Total Mismatch (POS line items don't sum to total)
    # ---------------------------------------------------------------------------
    """
    RULE_ID: R7_TOTAL_MISMATCH
    SCOPE: doc_family=TRANSACTIONAL (POS_RECEIPT, POS_RESTAURANT, etc.)
    INTENT: reimbursement, expense_tracking
    ALLOWED_DOC_FAMILIES: ["POS_RECEIPT", "POS_RESTAURANT", "POS_RETAIL"]
    
    FAILURE_MODE_ADDRESSED: Edited POS receipt totals (line items don't sum to total)
    REAL_WORLD_EXAMPLE: Restaurant receipt with 3 items ($12, $15, $8) but total 
                         shows $50 instead of $35. Manual edit or OCR error.
    WHY_NEW_RULE: Core fraud detection for POS receipts. Line items are the source
                  of truth for transactional receipts.
    
    CONFIDENCE_GATE:
      - should_apply_rule(doc_profile_obj, "R7_TOTAL_MISMATCH") == True
      - Gated OFF for COMMERCIAL_INVOICE (complex line items with shipping/duties)
    FAILURE_MODE: soft_degrade
    SEVERITY_RANGE: INFO → WARNING
    GOLDEN_TEST: tests/golden/pos_receipt.json
    VERSION: 1.0
    """
    # Enforce Rule × Family Matrix
    doc_family = legacy_doc_profile.get("family", "UNKNOWN").upper()
    execution_mode = get_execution_mode("R7_TOTAL_MISMATCH", doc_family)
    
    if execution_mode == ExecutionMode.FORBIDDEN:
        logger.debug(f"R7_TOTAL_MISMATCH skipped: {doc_family} not in allow-list")
        total_mismatch = False
    # GATED by profile: Skip for commercial invoices (complex line items with shipping, duties, etc.)
    elif should_apply_rule(doc_profile_obj, "R7_TOTAL_MISMATCH"):
        total_mismatch = bool(tf.get("total_mismatch", False))
    else:
        # RELAXATION: Even when profile gates it off, check for OBVIOUS mismatches
        # (>20% discrepancy is too large to ignore regardless of doc type)
        total_mismatch = False
        _fallback_total = _normalize_amount_str(tf.get("total_amount"))
        _fallback_sum = _normalize_amount_str(tf.get("line_items_sum"))
        if (_fallback_total and _fallback_total > 0 and _fallback_sum is not None
                and abs(_fallback_total - _fallback_sum) / _fallback_total > 0.20):
            total_mismatch = True
            logger.info(f"R7_TOTAL_MISMATCH: profile gated OFF for {doc_class} but >20% mismatch detected — applying as WARNING")
        else:
            logger.info(f"R7_TOTAL_MISMATCH skipped for {doc_class} (profile: apply_total_reconciliation=False)")
    
    if total_mismatch:
        # POS-SPECIFIC TOLERANCE: Allow small mismatch due to OCR errors on thermal prints
        doc_subtype = str(legacy_doc_profile.get("subtype") or tf.get("doc_subtype_guess") or "").upper()
        is_pos = doc_subtype.startswith("POS_")

        ocr_confidence = tf.get("ocr_confidence", None)
        # low_ocr_quality: None when unknown, True/False when known
        if ocr_confidence is None:
            low_ocr_quality = None  # Unknown quality
        else:
            try:
                low_ocr_quality = float(ocr_confidence) < 0.5
            except Exception:
                low_ocr_quality = None

        # Calculate actual mismatch ratio (0-1) if available
        total_amount = tf.get("total_amount")
        items_sum = tf.get("line_items_sum")

        # Keep raw values for debugging/audit (before normalization)
        total_amount_raw = total_amount
        items_sum_raw = items_sum

        # Normalize amounts defensively
        total_amount_n = _normalize_amount_str(total_amount)
        items_sum_n = _normalize_amount_str(items_sum)

        mismatch_ratio = 0.0
        has_total_amount = total_amount_n is not None and total_amount_n > 0
        has_line_items_sum = items_sum_n is not None
        if has_total_amount and has_line_items_sum:
            mismatch_ratio = abs(total_amount_n - items_sum_n) / float(total_amount_n)

        # For POS receipts with low OCR quality, allow ±5% tolerance
        tolerance_applied = bool(is_pos and (low_ocr_quality is True) and mismatch_ratio > 0 and mismatch_ratio <= 0.05)

        if tolerance_applied:
            # Small mismatch, likely OCR error - downgrade to WARNING
            severity = "WARNING"
            weight = 0.15
            message = "Minor total mismatch (likely OCR error on thermal print)"
        else:
            # Significant mismatch or high OCR quality - keep CRITICAL
            severity = "CRITICAL"
            weight = 0.40
            message = "Line items do not sum to printed total"

        score += emit_event(
            events=events,
            reasons=reasons,
            rule_id="R7_TOTAL_MISMATCH",
            severity=severity,
            weight=weight,
            message=message,
            evidence={
                "total_amount_raw": total_amount_raw,
                "line_items_sum_raw": items_sum_raw,
                "total_amount": total_amount_n,
                "line_items_sum": items_sum_n,
                "has_total_amount": has_total_amount,
                "has_line_items_sum": has_line_items_sum,
                "mismatch_ratio": mismatch_ratio,
                "mismatch_percentage": round(mismatch_ratio * 100, 2),
                "is_pos": is_pos,
                "ocr_confidence": ocr_confidence,
                "low_ocr_quality": low_ocr_quality,
                "tolerance_applied": tolerance_applied,
                "semantic_verification_invoked": tf.get("semantic_verification_invoked", False),
                "semantic_verification_applied": tf.get("semantic_verification_applied", False),
                "semantic_amounts": tf.get("semantic_amounts"),
            },
            reason_text="💰 Total Mismatch: Line items don't add up to the printed total.",
        )

    # ---------------------------------------------------------------------------
    # R7C: Credit Note Reconciliation (SIGN-AWARE VARIANT OF R7B)
    # ---------------------------------------------------------------------------
    """
    RULE_ID: R7C_CREDIT_NOTE_RECONCILIATION
    SCOPE: doc_family=INVOICE AND is_credit_note=True
    INTENT: billing, refund_verification
    ALLOWED_DOC_FAMILIES: ["CREDIT_NOTE"]
    
    FAILURE_MODE_ADDRESSED: Credit notes with negative totals fail standard reconciliation
    REAL_WORLD_EXAMPLE: Refund invoice with total=-$118 (subtotal=-$100, tax=-$18)
                         triggers false positive in R7B due to sign mismatch.
    WHY_NEW_RULE: R7B uses standard reconciliation math. Credit notes need sign-aware
                  logic (abs() for ratio calculation) and softer severity (messy IRL).
    
    CONFIDENCE_GATE:
      - doc_profile_confidence >= 0.75
      - fields_present >= 2
      - is_credit_note == True
    FAILURE_MODE: soft_degrade
    SEVERITY_RANGE: INFO → WARNING (never CRITICAL)
    GOLDEN_TEST: tests/golden/credit_note.json
    VERSION: 1.0
    NOTES: Credit notes can have negative totals - uses abs() for ratio calculation
    """
    # Credit notes can have negative totals - same math as R7B but sign-aware
    # Lower severity than R7B (credit notes are messy IRL)
    # RUNS BEFORE R7B because credit notes are a semantic specialization
    
    # Only apply to invoice-type documents (not POS receipts)
    doc_family = legacy_doc_profile.get("family", "").upper()
    doc_subtype = legacy_doc_profile.get("subtype", "").upper()
    
    # Determine if this is an invoice-type document
    is_credit_note_family = doc_family == "CREDIT_NOTE" or tf.get("is_credit_note", False)
    is_invoice_type = (
        doc_family == "INVOICE" 
        or "INVOICE" in doc_subtype 
        or doc_subtype in ("TAX_INVOICE", "VAT_INVOICE", "COMMERCIAL_INVOICE", "SERVICE_INVOICE")
        or is_credit_note_family
    )
    is_credit_note = tf.get("is_credit_note", False)
    
    # Enforce Rule × Family Matrix
    execution_mode = get_execution_mode("R7C_CREDIT_NOTE_RECONCILIATION", doc_family)
    
    if execution_mode == ExecutionMode.FORBIDDEN:
        logger.debug(f"R7C_CREDIT_NOTE_RECONCILIATION skipped: {doc_family} forbidden")
        # Skip silently - forbidden
    elif not is_credit_note_family and execution_mode != ExecutionMode.SOFT:
        logger.debug(f"R7C_CREDIT_NOTE_RECONCILIATION skipped: not a credit note")
        # Skip silently - not a credit note (unless SOFT mode allows it)
    
    # STRICT GATING: All must pass (only if not forbidden)
    if execution_mode != ExecutionMode.FORBIDDEN and is_invoice_type and is_credit_note:
        # Get doc_profile_confidence for gating
        dp_conf_val = tf.get("doc_profile_confidence") or legacy_doc_profile.get("confidence") or 0.0
        try:
            dp_conf_val = float(dp_conf_val)
        except Exception:
            dp_conf_val = 0.0
        
        # Gate: Only apply if confidence >= 0.75
        if dp_conf_val >= 0.75:
            # Extract invoice components
            subtotal = tf.get("subtotal")
            tax_amount = tf.get("tax_amount")
            shipping_amount = tf.get("shipping_amount")
            discount_amount = tf.get("discount_amount")
            total_amount = tf.get("total_amount")
            
            # Normalize amounts
            subtotal_n = _normalize_amount_str(subtotal)
            tax_n = _normalize_amount_str(tax_amount)
            shipping_n = _normalize_amount_str(shipping_amount)
            discount_n = _normalize_amount_str(discount_amount)
            total_n = _normalize_amount_str(total_amount)
            
            # Count available fields for "enough fields present" gate
            fields_present = sum([
                subtotal_n is not None,
                tax_n is not None,
                total_n is not None and total_n > 0,
            ])
            
            # Gate: Need at least 2 fields (e.g., subtotal + total, or tax + total)
            if fields_present >= 2 and total_n is not None and total_n > 0:
                # Calculate expected total
                # expected_total = subtotal + tax + shipping - discount
                expected_total = 0.0
                components_used = []
                
                if subtotal_n is not None:
                    expected_total += subtotal_n
                    components_used.append(f"subtotal={subtotal_n}")
                
                if tax_n is not None:
                    expected_total += tax_n
                    components_used.append(f"tax={tax_n}")
                
                # Opportunistically add shipping and discount if available
                if shipping_n is not None:
                    expected_total += shipping_n
                    components_used.append(f"shipping={shipping_n}")
                
                if discount_n is not None:
                    expected_total -= discount_n
                    components_used.append(f"discount=-{discount_n}")
                
                # If we only have tax but no subtotal, we can't reconcile
                # (need at least subtotal to make sense)
                if subtotal_n is None and tax_n is not None:
                    # Can't reconcile - skip
                    pass
                elif expected_total > 0:
                    # Calculate mismatch
                    mismatch = abs(expected_total - total_n)
                    mismatch_ratio = mismatch / total_n if total_n > 0 else 0.0
                    
                    # Determine tolerance based on OCR confidence and currency
                    ocr_confidence = tf.get("ocr_confidence")
                    if ocr_confidence is None or ocr_confidence >= 0.7:
                        # High OCR confidence - stricter tolerance (2%)
                        tolerance = 0.02
                    elif ocr_confidence >= 0.5:
                        # Medium OCR confidence - moderate tolerance (5%)
                        tolerance = 0.05
                    else:
                        # Low OCR confidence - looser tolerance (10%)
                        tolerance = 0.10
                    
                    # TAX_INVOICE: Apply stricter tolerance (regulated documents)
                    # Tax invoices should reconcile more tightly to catch edited GST/VAT invoices
                    if doc_subtype == "TAX_INVOICE":
                        tolerance *= 0.5  # 1-5% instead of 2-10%
                        logger.debug(f"TAX_INVOICE detected: applying stricter tolerance ({tolerance*100:.1f}%)")
                    
                    # MINIMUM ABSOLUTE DELTA FLOOR: Avoid penny-level noise
                    # Very small totals can create noisy ratios (e.g., $5 total with $0.20 error = 4%)
                    # Treat mismatches < $1.00 as within tolerance
                    treat_as_within_tolerance = abs(mismatch) < 1.00
                    
                    # MULTI-CURRENCY DETECTION: Skip reconciliation if FX conversion detected
                    # Invoices with currency conversions almost never reconcile cleanly
                    multi_currency_detected = tf.get("multi_currency_detected", False)
                    
                    # Check if mismatch exceeds tolerance
                    if mismatch_ratio > tolerance and not treat_as_within_tolerance and not multi_currency_detected:
                        # Check if line items look incomplete/dirty
                        has_line_items = bool(tf.get("has_line_items"))
                        line_items_sum = tf.get("line_items_sum")
                        line_items_dirty = (
                            has_line_items 
                            and line_items_sum is not None 
                            and abs(line_items_sum - total_n) / total_n > 0.20  # >20% off
                        )
                        
                        if line_items_dirty:
                            # Line items incomplete - downgrade to INFO
                            severity = "INFO"
                            weight = 0.0
                            message = "Invoice components don't reconcile (line items incomplete)"
                        elif mismatch_ratio > tolerance * 2:
                            # Significant mismatch - WARNING
                            severity = "WARNING"
                            weight = 0.08
                            message = f"Invoice total reconciliation mismatch ({mismatch_ratio*100:.1f}%)"
                        else:
                            # Minor mismatch - INFO
                            severity = "INFO"
                            weight = 0.0
                            message = f"Minor invoice reconciliation variance ({mismatch_ratio*100:.1f}%)"
                        
                        score += emit_event(
                            events=events,
                            reasons=reasons if weight > 0 else None,
                            rule_id="R7B_INVOICE_TOTAL_RECONCILIATION",
                            severity=severity,
                            weight=weight,
                            message=message,
                            evidence={
                                "subtotal": subtotal_n,
                                "tax_amount": tax_n,
                                "total_amount": total_n,
                                "expected_total": round(expected_total, 2),
                                "mismatch": round(mismatch, 2),
                                "mismatch_ratio": round(mismatch_ratio, 4),
                                "mismatch_percentage": round(mismatch_ratio * 100, 2),
                                "tolerance": tolerance,
                                "tolerance_percentage": round(tolerance * 100, 2),
                                "components_used": components_used,
                                "ocr_confidence": ocr_confidence,
                                "line_items_dirty": line_items_dirty if 'line_items_dirty' in locals() else False,
                                "doc_profile_confidence": dp_conf_val,
                                "is_tax_invoice": doc_subtype == "TAX_INVOICE",
                                "treat_as_within_tolerance": treat_as_within_tolerance,
                                "multi_currency_detected": multi_currency_detected,
                            },
                            reason_text=(
                                f"🧾 Invoice Reconciliation: Components don't add up to total "
                                f"(expected {expected_total:.2f}, got {total_n:.2f})"
                            ) if weight > 0 else None,
                        )
    
    # ---------------------------------------------------------------------------
    # R7B: Invoice Total Reconciliation (for COMMERCIAL_INVOICE, TAX_INVOICE, etc.)
    # ---------------------------------------------------------------------------
    """
    RULE_ID: R7B_INVOICE_TOTAL_RECONCILIATION
    SCOPE: doc_family=INVOICE AND is_credit_note=False
    INTENT: billing, compliance_verification
    ALLOWED_DOC_FAMILIES: ["COMMERCIAL_INVOICE", "TAX_INVOICE"]
    
    FAILURE_MODE_ADDRESSED: Edited invoice totals (subtotal+tax+shipping-discount != total)
    REAL_WORLD_EXAMPLE: Vendor invoice with subtotal=$1000, tax=$180, shipping=$20
                         but total shows $1500 instead of $1200. Manual inflation.
    WHY_NEW_RULE: R7 only applies to POS receipts with line items. Commercial invoices
                  use component reconciliation (subtotal+tax+shipping-discount) not
                  line-item sums. Different document structure requires different math.
    
    CONFIDENCE_GATE:
      - doc_profile_confidence >= 0.75
      - fields_present >= 2
      - NOT is_credit_note (R7C handles those)
    FAILURE_MODE: soft_degrade
    SEVERITY_RANGE: INFO → WARNING
    GOLDEN_TEST: tests/golden/invoice.json
    VERSION: 1.0
    ENHANCEMENTS:
      - TAX_INVOICE: 0.5x stricter tolerance (1-5% vs 2-10%)
      - Minimum delta floor: $1.00 (prevents penny-level noise)
      - Multi-currency skip: FX conversions never reconcile cleanly
      - Opportunistic shipping/discount extraction
    """
    # More sophisticated reconciliation using subtotal, tax, shipping, discount
    # Gated by doc_profile_confidence and field availability
    # Uses looser tolerance (2-10%) based on OCR confidence and currency complexity
    # RUNS AFTER R7C - skips credit notes (R7C handles those)
    
    # Enforce Rule × Family Matrix
    execution_mode = get_execution_mode("R7B_INVOICE_TOTAL_RECONCILIATION", doc_family)
    
    if execution_mode == ExecutionMode.FORBIDDEN:
        logger.debug(f"R7B_INVOICE_TOTAL_RECONCILIATION skipped: {doc_family} forbidden")
    # Guard: Skip credit notes (let R7C handle them)
    elif is_invoice_type and not is_credit_note:
        # Get doc_profile_confidence for gating
        dp_conf_val = tf.get("doc_profile_confidence") or legacy_doc_profile.get("confidence") or 0.0
        try:
            dp_conf_val = float(dp_conf_val)
        except Exception:
            dp_conf_val = 0.0
        
        # Gate: Only apply if confidence >= 0.75
        if dp_conf_val >= 0.75:
            # Extract invoice components (same as R7B)
            subtotal = tf.get("subtotal")
            tax_amount = tf.get("tax_amount")
            shipping_amount = tf.get("shipping_amount")
            discount_amount = tf.get("discount_amount")
            total_amount = tf.get("total_amount")
            
            # Normalize amounts
            subtotal_n = _normalize_amount_str(subtotal)
            tax_n = _normalize_amount_str(tax_amount)
            shipping_n = _normalize_amount_str(shipping_amount)
            discount_n = _normalize_amount_str(discount_amount)
            total_n = _normalize_amount_str(total_amount)
            
            # Count available fields for "enough fields present" gate
            fields_present = sum([
                subtotal_n is not None,
                tax_n is not None,
                total_n is not None,
            ])
            
            # Gate: Need at least 2 fields and total must exist
            if fields_present >= 2 and total_n is not None:
                # Calculate expected total (same formula as R7B)
                expected_total = 0.0
                components_used = []
                
                if subtotal_n is not None:
                    expected_total += subtotal_n
                    components_used.append(f"subtotal={subtotal_n}")
                
                if tax_n is not None:
                    expected_total += tax_n
                    components_used.append(f"tax={tax_n}")
                
                # Opportunistically add shipping and discount if available
                if shipping_n is not None:
                    expected_total += shipping_n
                    components_used.append(f"shipping={shipping_n}")
                
                if discount_n is not None:
                    expected_total -= discount_n
                    components_used.append(f"discount=-{discount_n}")
                
                # If we only have tax but no subtotal, we can't reconcile
                if subtotal_n is None and tax_n is not None:
                    # Can't reconcile - skip
                    pass
                else:
                    # SIGN-AWARE: Credit notes can be negative
                    # Use abs() for ratio calculation to handle negative totals
                    mismatch = abs(expected_total - total_n)
                    mismatch_ratio = mismatch / abs(total_n) if total_n != 0 else 0.0
                    
                    # Reuse R7B tolerance logic
                    ocr_confidence = tf.get("ocr_confidence")
                    if ocr_confidence is None or ocr_confidence >= 0.7:
                        tolerance = 0.02  # High OCR confidence - 2%
                    elif ocr_confidence >= 0.5:
                        tolerance = 0.05  # Medium OCR confidence - 5%
                    else:
                        tolerance = 0.10  # Low OCR confidence - 10%
                    
                    # TAX_INVOICE credit notes: Apply stricter tolerance
                    if doc_subtype == "TAX_INVOICE":
                        tolerance *= 0.5  # 1-5% instead of 2-10%
                    
                    # MINIMUM ABSOLUTE DELTA FLOOR (same as R7B)
                    treat_as_within_tolerance = abs(mismatch) < 1.00
                    
                    # MULTI-CURRENCY DETECTION (same as R7B)
                    multi_currency_detected = tf.get("multi_currency_detected", False)
                    
                    # Check if mismatch exceeds tolerance
                    if mismatch_ratio > tolerance and not treat_as_within_tolerance and not multi_currency_detected:
                        # Check if line items look incomplete/dirty
                        has_line_items = bool(tf.get("has_line_items"))
                        line_items_sum = tf.get("line_items_sum")
                        line_items_dirty = (
                            has_line_items 
                            and line_items_sum is not None 
                            and abs(total_n) > 0
                            and abs(line_items_sum - total_n) / abs(total_n) > 0.20  # >20% off
                        )
                        
                        # SOFT SEVERITY MODEL (credit notes are messy IRL)
                        if line_items_dirty:
                            # Line items incomplete - INFO only
                            severity = "INFO"
                            weight = 0.0
                            message = "Credit note components don't reconcile (line items incomplete)"
                        elif mismatch_ratio > tolerance * 2:
                            # Significant mismatch - WARNING (softer than R7B)
                            severity = "WARNING"
                            weight = 0.05  # Lower than R7B's 0.08
                            message = f"Credit note reconciliation mismatch ({mismatch_ratio*100:.1f}%)"
                        else:
                            # Minor mismatch - INFO only
                            severity = "INFO"
                            weight = 0.0
                            message = f"Minor credit note reconciliation variance ({mismatch_ratio*100:.1f}%)"
                        
                        score += emit_event(
                            events=events,
                            reasons=reasons if weight > 0 else None,
                            rule_id="R7C_CREDIT_NOTE_RECONCILIATION",
                            severity=severity,
                            weight=weight,
                            message=message,
                            evidence={
                                "is_credit_note": True,
                                "subtotal": subtotal_n,
                                "tax_amount": tax_n,
                                "total_amount": total_n,
                                "expected_total": round(expected_total, 2),
                                "mismatch": round(mismatch, 2),
                                "mismatch_ratio": round(mismatch_ratio, 4),
                                "mismatch_percentage": round(mismatch_ratio * 100, 2),
                                "tolerance": tolerance,
                                "tolerance_percentage": round(tolerance * 100, 2),
                                "components_used": components_used,
                                "ocr_confidence": ocr_confidence,
                                "line_items_dirty": line_items_dirty if 'line_items_dirty' in locals() else False,
                                "doc_profile_confidence": dp_conf_val,
                                "is_tax_invoice": doc_subtype == "TAX_INVOICE",
                                "treat_as_within_tolerance": treat_as_within_tolerance,
                                "multi_currency_detected": multi_currency_detected,
                            },
                            reason_text=(
                                f"🧾 Credit Note Reconciliation: Components don't add up to total "
                                f"(expected {expected_total:.2f}, got {total_n:.2f})"
                            ) if weight > 0 else None,
                        )

    # R8: No date
    if not has_date:
        if expects_date:
            # Only penalize if missing-field gate is enabled
            if missing_fields_enabled:
                # NUANCE: Downgrade severity if time OR receipt_number present
                # Many Indian POS receipts have time but OCR misses date
                has_time = bool(tf.get("receipt_time"))
                has_receipt_num = bool(tf.get("receipt_number"))
                has_alternative_identifier = has_time or has_receipt_num
                
                # OCR CONFIDENCE ADJUSTMENT: Reduce penalty if OCR quality is poor
                ocr_confidence = tf.get("ocr_confidence", None)
                # low_ocr_quality: None when unknown, True/False when known
                if ocr_confidence is None:
                    low_ocr_quality = None  # Unknown quality
                else:
                    low_ocr_quality = ocr_confidence < 0.4
                
                if has_alternative_identifier:
                    # Downgrade to WARNING with reduced weight
                    severity = "WARNING"
                    weight = 0.10  # Half of original 0.20
                    message = "No date found, but time or receipt number present"
                elif low_ocr_quality:
                    # Reduce penalty for poor OCR quality
                    severity = "WARNING"
                    weight = 0.12  # 60% of original 0.20
                    message = "No date found (low OCR quality)"
                else:
                    # Full penalty
                    severity = "CRITICAL"
                    weight = 0.20
                    message = "No date found in document"
                
                score += emit_event(
                    events=events,
                    reasons=reasons,
                    rule_id="R8_NO_DATE",
                    severity=severity,
                    weight=weight,
                    message=message,
                    evidence={
                        "has_date": False,
                        "has_time": has_time,
                        "has_receipt_number": has_receipt_num,
                        "has_alternative_identifier": has_alternative_identifier,
                        "ocr_confidence": ocr_confidence,
                        "low_ocr_quality": low_ocr_quality,
                        "doc_family": legacy_doc_profile.get("family"),
                        "doc_subtype": legacy_doc_profile.get("subtype"),
                        "doc_profile_confidence": legacy_doc_profile.get("confidence"),
                        "missing_fields_enabled": missing_fields_enabled,
                        "missing_field_gate": _missing_field_gate_evidence(tf, legacy_doc_profile),
                        "severity_downgraded": has_alternative_identifier or low_ocr_quality,
                    },
                    reason_text="📅 No Date Found: Receipt/invoice is missing a transaction date.",
                )
        else:
            minor_notes.append(
                "Date was not detected, but this document subtype often omits dates (or date is not central)."
            )
            emit_event(
                events=events,
                reasons=None,
                rule_id="R8_NO_DATE_OPTIONAL_FOR_DOC",
                severity="INFO",
                weight=0.0,
                message="No date detected but optional for this doc subtype",
                evidence={
                    "has_date": False,
                    "doc_family": legacy_doc_profile.get("family"),
                    "doc_subtype": legacy_doc_profile.get("subtype"),
                    "doc_profile_confidence": legacy_doc_profile.get("confidence"),
                },
            )

    if not merchant_candidate:
        if missing_fields_enabled:
            score += emit_event(
                events=events,
                reasons=reasons,
                rule_id="R9_NO_MERCHANT",
                severity="CRITICAL",
                weight=0.15,
                message="No merchant name could be identified",
                evidence={
                    "merchant_candidate": None,
                    "missing_fields_enabled": missing_fields_enabled,
                    "missing_field_gate": _missing_field_gate_evidence(tf, legacy_doc_profile),
                },
                reason_text="🏪 No Merchant: Could not identify a merchant/vendor name.",
            )
        else:
            # ENHANCEMENT: Still flag missing merchant as WARNING even when gate is off
            # Missing merchant is always suspicious — just reduce severity when uncertain
            score += emit_event(
                events=events,
                reasons=reasons,
                rule_id="R9_NO_MERCHANT",
                severity="WARNING",
                weight=0.08,
                message="No merchant name could be identified (reduced penalty — doc type uncertain)",
                evidence={
                    "merchant_candidate": None,
                    "missing_fields_enabled": missing_fields_enabled,
                    "gated_reduction": True,
                    "missing_field_gate": _missing_field_gate_evidence(tf, legacy_doc_profile),
                },
                reason_text="🏪 No Merchant: Could not identify a merchant/vendor name (doc type uncertain — reduced penalty).",
            )

    # R8B: Date conflict - multiple distant dates in same receipt (HIGH VALUE FRAUD SIGNAL)
    all_dates = tf.get("all_dates", [])
    if len(all_dates) >= 2:
        from datetime import datetime
        try:
            # Parse all dates and find max difference
            parsed_dates = []
            for date_str in all_dates:
                try:
                    parsed = datetime.strptime(date_str, "%Y-%m-%d")
                    parsed_dates.append(parsed)
                except:
                    pass
            
            if len(parsed_dates) >= 2:
                parsed_dates.sort()
                date_diff_days = (parsed_dates[-1] - parsed_dates[0]).days
                
                # If dates differ by > 30 days, this is highly suspicious
                if date_diff_days > 30:
                    # For POS receipts, this is especially suspicious (likely merged/tampered)
                    doc_subtype = legacy_doc_profile.get("subtype", "").upper()
                    is_pos = doc_subtype.startswith("POS_")
                    
                    severity = "CRITICAL"
                    weight = 0.35 if is_pos else 0.25
                    
                    score += emit_event(
                        events=events,
                        reasons=reasons,
                        rule_id="R_DATE_CONFLICT",
                        severity=severity,
                        weight=weight,
                        message=f"Multiple dates found with {date_diff_days} days difference",
                        evidence={
                            "all_dates": all_dates,
                            "date_diff_days": date_diff_days,
                            "is_pos": is_pos,
                            "num_dates": len(all_dates),
                        },
                        reason_text=f"📅⚠️ Date Conflict: Receipt contains multiple dates spanning {date_diff_days} days. This suggests tampering or merged receipts.",
                    )
        except Exception as e:
            logger.warning(f"Date conflict check failed: {e}")

    # Merchant plausibility checks
    if merchant_candidate:
        issues = _merchant_plausibility_issues(merchant_candidate)
        if issues:
            reason_msg = _format_merchant_issue_reason(merchant_candidate, issues)

            # Gate merchant plausibility penalties when missing-field gate is OFF
            if missing_fields_enabled:
                # One score contribution (avoid double-penalizing for multiple issue flags)
                weight = 0.12
                if any(it in issues for it in ("looks_like_label", "looks_like_identifier")):
                    weight = 0.18

                score += emit_event(
                    events=events,
                    reasons=reasons,
                    rule_id="MERCHANT_IMPLAUSIBLE",
                    severity="CRITICAL",
                    weight=weight,
                    message="Merchant name appears implausible",
                    evidence={"merchant": merchant_candidate, "issues": issues},
                    reason_text=reason_msg,
                )
            else:
                # Emit INFO event only (no score penalty)
                emit_event(
                    events=events,
                    reasons=None,
                    rule_id="MERCHANT_IMPLAUSIBLE_GATED",
                    severity="INFO",
                    weight=0.0,
                    message="Merchant name appears implausible (gated - no penalty applied)",
                    evidence={
                        "merchant": merchant_candidate,
                        "issues": issues,
                        "missing_fields_enabled": missing_fields_enabled,
                        "gated": True,
                    },
                )

    # ---------------------------------------------------------------------------
    # R9B: Document Type Unknown or Mixed (SOFT DEGRADE)
    # ---------------------------------------------------------------------------
    """
    RULE_ID: R9B_DOC_TYPE_UNKNOWN_OR_MIXED
    SCOPE: doc_family=TRANSACTIONAL (POS_RECEIPT, POS_RESTAURANT, etc.)
    INTENT: reimbursement, expense_tracking
    ALLOWED_DOC_FAMILIES: ["POS_RECEIPT", "POS_RESTAURANT", "POS_RETAIL"]
    
    CONFIDENCE_GATE:
      - doc_profile_confidence < 0.6
      - Mixed invoice/receipt language detected
    FAILURE_MODE: soft_degrade
    SEVERITY_RANGE: INFO → WARNING
    VERSION: 1.0
    """
    # Document type checks
    # _detect_document_type returns "unknown" when invoice+receipt language is mixed
    if doc_type_hint in ("ambiguous", "unknown"):
        # Get doc profile confidence and subtype
        dp_conf_val = tf.get("doc_profile_confidence") or legacy_doc_profile.get("confidence") or 0.0
        try:
            dp_conf_val = float(dp_conf_val)
        except Exception:
            dp_conf_val = 0.0
        
        doc_family = legacy_doc_profile.get("family", "").upper()
        doc_subtype = legacy_doc_profile.get("subtype", "").upper()
        
        # Enforce Rule × Family Matrix
        execution_mode = get_execution_mode("R9B_DOC_TYPE_UNKNOWN_OR_MIXED", doc_family)
        
        if execution_mode == ExecutionMode.FORBIDDEN:
            logger.debug(f"R9B_DOC_TYPE_UNKNOWN_OR_MIXED skipped: {doc_family} forbidden")
        # GATE: Suppress R9B for high-confidence POS receipts
        # POS receipts are structurally noisy by nature - ambiguity ≠ fraud
        elif dp_conf_val >= 0.8 and doc_subtype.startswith("POS_"):
            emit_event(
                events=events,
                reasons=None,
                rule_id="R9B_DOC_TYPE_UNKNOWN_GATED",
                severity="INFO",
                weight=0.0,
                message="Document type ambiguity suppressed for high-confidence POS receipt",
                evidence={
                    "doc_type": doc_type_hint,
                    "doc_subtype": doc_subtype,
                    "doc_profile_confidence": dp_conf_val,
                    "gated": True,
                    "reason": "POS receipts are structurally noisy - ambiguity is normal",
                },
            )
        else:
            # Check if merchant/currency/table present (structural validity signals)
            merchant_present = bool(tf.get("merchant_candidate"))
            currency_present = bool(tf.get("has_currency") or tf.get("currency_symbols"))
            table_present = bool(tf.get("has_line_items"))
            structural_signals = sum([merchant_present, currency_present, table_present])
            
            # Downgrade if transactional doc with low confidence
            if doc_family == "TRANSACTIONAL" and dp_conf_val < 0.4:
                severity = "WARNING"
                weight = 0.08
            # Downgrade if merchant + currency + table present (likely valid POS receipt)
            elif structural_signals >= 3:
                severity = "WARNING"
                weight = 0.08
            # Reduce weight by 50% if at least 2 structural signals present
            elif structural_signals >= 2:
                severity = "CRITICAL"
                weight = 0.075  # 50% of 0.15
            else:
                severity = "CRITICAL"
                weight = 0.15
            
            score += emit_event(
                events=events,
                reasons=reasons,
                rule_id="R9B_DOC_TYPE_UNKNOWN_OR_MIXED",
                severity=severity,
                weight=weight,
                message="Document type unclear or mixed (invoice/receipt language)",
                evidence={
                    "doc_type": doc_type_hint,
                    "doc_family": doc_family,
                    "doc_profile_confidence": dp_conf_val,
                    "structural_signals": structural_signals,
                    "severity_downgraded": (severity == "WARNING"),
                },
                reason_text="📄 Document Type Ambiguity: Contains mixed/unclear invoice/receipt language.",
            )

    # ---------------------------------------------------------------------------
    # RULE GROUP 3: Layout anomalies
    # ---------------------------------------------------------------------------
    num_lines = lf.get("num_lines", 0)
    numeric_line_ratio = lf.get("numeric_line_ratio", 0.0)

    if num_lines < 5:
        score += emit_event(
            events=events,
            reasons=reasons,
            rule_id="R10_TOO_FEW_LINES",
            severity="INFO",
            weight=0.15,
            message=f"Very few lines detected ({num_lines})",
            evidence={"num_lines": num_lines},
            reason_text=f"📏 Too Few Lines: Only {num_lines} lines detected (typical receipts have more).",
        )

    if num_lines > 120:
        score += emit_event(
            events=events,
            reasons=reasons,
            rule_id="R11_TOO_MANY_LINES",
            severity="INFO",
            weight=0.10,
            message=f"Unusually many lines ({num_lines})",
            evidence={"num_lines": num_lines},
            reason_text=f"📏 Too Many Lines: {num_lines} lines (could be noisy OCR or filler text).",
        )

    if numeric_line_ratio > 0.8 and num_lines > 10:
        score += emit_event(
            events=events,
            reasons=reasons,
            rule_id="R12_HIGH_NUMERIC_RATIO",
            severity="INFO",
            weight=0.10,
            message="Very high numeric line ratio",
            evidence={"numeric_line_ratio": numeric_line_ratio, "num_lines": num_lines},
            reason_text=f"🔢 High Numeric Ratio: {numeric_line_ratio:.0%} of lines are purely numeric.",
        )

    # ---------------------------------------------------------------------------
    # RULE GROUP 4: Forensic cues
    # ---------------------------------------------------------------------------
    
    # R_TAMPER_WATERMARK: Detect fake receipt generators and watermarks (HIGH VALUE)
    full_text = "\n".join(raw.ocr_text_per_page) if hasattr(features, 'raw') and hasattr(features.raw, 'ocr_text_per_page') else ""
    if not full_text:
        # Reconstruct from lines if available
        lines = lf.get("lines", [])
        full_text = "\n".join(lines) if lines else ""
    
    tamper_keywords = [
        "receiptfaker", "receipt faker", "fake receipt", "receipt generator",
        "invoice generator", "fake invoice", "sample receipt", "demo receipt",
        "test receipt", "template", "example receipt", "specimen",
        "not valid", "void", "copy only", "for display only",
    ]
    
    detected_tamper_keywords = []
    for keyword in tamper_keywords:
        if keyword.lower() in full_text.lower():
            detected_tamper_keywords.append(keyword)
    
    if detected_tamper_keywords:
        # This is a near hard-fail - fake receipt generator detected
        score += emit_event(
            events=events,
            reasons=reasons,
            rule_id="R_TAMPER_WATERMARK",
            severity="CRITICAL",
            weight=0.50,  # Very high weight - this is almost certainly fake
            message=f"Tamper/watermark keywords detected: {', '.join(detected_tamper_keywords)}",
            evidence={
                "detected_keywords": detected_tamper_keywords,
                "num_keywords": len(detected_tamper_keywords),
            },
            reason_text=f"🚨 WATERMARK DETECTED: Receipt contains tamper keywords: {', '.join(detected_tamper_keywords)}. This indicates a fake receipt generator or template.",
        )
    
    uppercase_ratio = fr.get("uppercase_ratio", 0.0)
    unique_char_count = fr.get("unique_char_count", 0)

    if uppercase_ratio > 0.8 and num_lines > 5:
        score += emit_event(
            events=events,
            reasons=reasons,
            rule_id="R13_HIGH_UPPERCASE",
            severity="INFO",
            weight=0.10,
            message="High uppercase character ratio",
            evidence={"uppercase_ratio": uppercase_ratio},
            reason_text=f"🔠 High Uppercase: {uppercase_ratio:.0%} uppercase (template-like).",
        )

    if unique_char_count < 15 and num_lines > 5:
        score += emit_event(
            events=events,
            reasons=reasons,
            rule_id="R14_LOW_CHAR_VARIETY",
            severity="INFO",
            weight=0.15,
            message="Low character variety",
            evidence={"unique_char_count": unique_char_count},
            reason_text=f"🔤 Low Character Variety: Only {unique_char_count} unique characters.",
        )

    # ---------------------------------------------------------------------------
    # RULE GROUP 4B: Pixel-level image forensics
    # ---------------------------------------------------------------------------
    # Consumes forensic_features["image_forensics"] produced by image_forensics.py
    img_forensics = fr.get("image_forensics") or {}
    if img_forensics.get("forensics_available"):
        _if_suspicious = img_forensics.get("overall_suspicious", False)
        _if_signal_count = img_forensics.get("signal_count", 0)
        _if_confidence = float(img_forensics.get("overall_confidence", 0) or 0)
        _if_evidence_list = img_forensics.get("overall_evidence", [])

        # Only emit if 2+ independent forensic signals are suspicious
        # (single signal is too noisy — ELA alone fires on low-quality JPEGs)
        if _if_suspicious and _if_signal_count >= 2 and _if_confidence >= 0.3:
            severity = "CRITICAL" if _if_signal_count >= 3 else "WARNING"
            weight = 0.25 if severity == "CRITICAL" else 0.12
            score += emit_event(
                events=events,
                reasons=reasons,
                rule_id="R_IMAGE_FORENSICS_TAMPERING",
                severity=severity,
                weight=weight,
                message=f"Image forensics: {_if_signal_count} suspicious signals detected",
                evidence={
                    "signal_count": _if_signal_count,
                    "confidence": _if_confidence,
                    "evidence": _if_evidence_list[:5],
                    "ela_suspicious": img_forensics.get("ela", {}).get("ela_suspicious"),
                    "noise_suspicious": img_forensics.get("noise", {}).get("noise_suspicious"),
                    "dpi_suspicious": img_forensics.get("dpi", {}).get("dpi_suspicious"),
                    "histogram_suspicious": img_forensics.get("histogram", {}).get("histogram_suspicious"),
                },
                reason_text=(
                    f"🔬 Image Forensics: {_if_signal_count} independent pixel-level "
                    f"signals suggest possible image manipulation. "
                    + "; ".join(_if_evidence_list[:3])
                ),
            )

        # Individual high-confidence signals that are worth emitting on their own

        # ELA with very high zone variance = strong splicing indicator
        _ela = img_forensics.get("ela", {})
        if _ela.get("ela_zone_variance", 0) > 25.0:
            score += emit_event(
                events=events,
                reasons=reasons,
                rule_id="R_IMAGE_ELA_SPLICE",
                severity="CRITICAL",
                weight=0.20,
                message="ELA detects likely image splicing",
                evidence={
                    "ela_zone_variance": _ela.get("ela_zone_variance"),
                    "ela_hotspot_ratio": _ela.get("ela_hotspot_ratio"),
                    "ela_mean": _ela.get("ela_mean"),
                    "ela_max": _ela.get("ela_max"),
                },
                reason_text=(
                    f"🔬 ELA Splice Detection: Zone variance "
                    f"{_ela.get('ela_zone_variance', 0):.1f} indicates different "
                    f"parts of the image were saved at different JPEG quality levels. "
                    f"This is a strong indicator of copy-paste editing."
                ),
            )

        # Very low noise = digitally generated (not a photograph/scan)
        _noise = img_forensics.get("noise", {})
        if _noise.get("noise_mean", 99) < 1.0:
            score += emit_event(
                events=events,
                reasons=reasons,
                rule_id="R_IMAGE_DIGITAL_ORIGIN",
                severity="WARNING",
                weight=0.08,
                message="Image appears digitally generated (no sensor noise)",
                evidence={
                    "noise_mean": _noise.get("noise_mean"),
                    "noise_std": _noise.get("noise_std"),
                },
                reason_text=(
                    f"🔬 Digital Origin: Image noise level "
                    f"({_noise.get('noise_mean', 0):.2f}) is near zero, suggesting "
                    f"the image was digitally created rather than photographed/scanned."
                ),
            )

        # Very low resolution = suspicious
        _dpi = img_forensics.get("dpi", {})
        if _dpi.get("is_very_low_res"):
            score += emit_event(
                events=events,
                reasons=reasons,
                rule_id="R_IMAGE_LOW_RES",
                severity="WARNING",
                weight=0.08,
                message=f"Very low resolution image ({_dpi.get('width')}×{_dpi.get('height')})",
                evidence={
                    "width": _dpi.get("width"),
                    "height": _dpi.get("height"),
                    "is_screenshot_size": _dpi.get("is_screenshot_size"),
                },
                reason_text=(
                    f"🔬 Low Resolution: Image is only "
                    f"{_dpi.get('width')}×{_dpi.get('height')} pixels — "
                    f"too small for a legitimate receipt scan or photo."
                ),
            )

    # ---------------------------------------------------------------------------
    # RULE GROUP 5: Date validation (impossible dates, suspicious gaps)
    # ---------------------------------------------------------------------------
    receipt_date_str = tf.get("date_extracted") or tf.get("receipt_date")
    creation_date_str = ff.get("creation_date")
    
    # Parse receipt date if present (regardless of creation date)
    receipt_date = _parse_date_best_effort(receipt_date_str) if receipt_date_str else None

    # R_FUTURE_DATE: Receipt date is in the future
    # Expert insight: A receipt dated tomorrow or next week is obviously fabricated.
    # Allow 1-day tolerance for timezone differences.
    if receipt_date is not None:
        try:
            _today = date.today()
            _days_ahead = (receipt_date - _today).days
            if _days_ahead > 1:
                # More than 1 day in the future → definite fabrication
                severity = "HARD_FAIL" if _days_ahead > 7 else "CRITICAL"
                weight = 0.45 if severity == "HARD_FAIL" else 0.30
                score += emit_event(
                    events=events,
                    reasons=reasons,
                    rule_id="R_FUTURE_DATE",
                    severity=severity,
                    weight=weight,
                    message=f"Receipt date is {_days_ahead} days in the future",
                    evidence={
                        "receipt_date": str(receipt_date),
                        "today": str(_today),
                        "days_ahead": _days_ahead,
                    },
                    reason_text=(
                        f"📅🚨 Future Date: Receipt is dated {receipt_date_str} "
                        f"which is {_days_ahead} days in the future. "
                        f"A receipt cannot be dated before the transaction occurs."
                    ),
                )
        except Exception as e:
            logger.warning(f"R_FUTURE_DATE check failed: {e}")

    if receipt_date_str and creation_date_str:
        # Parse creation date for comparison
        creation_datetime = _parse_pdf_creation_datetime_best_effort(creation_date_str)

        if receipt_date and creation_datetime:
            creation_date = creation_datetime.date()

            if receipt_date > creation_date:
                score += emit_event(
                    events=events,
                    reasons=reasons,
                    rule_id="R15_IMPOSSIBLE_DATE_SEQUENCE",
                    severity="HARD_FAIL",
                    weight=0.40,
                    message="Receipt date is AFTER file creation date (impossible)",
                    evidence={
                        "receipt_date": receipt_date_str,
                        "creation_date": creation_date_str,
                        "receipt_date_parsed": str(receipt_date),
                        "creation_date_parsed": str(creation_date),
                    },
                    reason_text="📅⚠️ Impossible Date: Receipt date is after file creation date.",
                )
            else:
                # Suspicious date gap: file created significantly after receipt date
                # GATED by profile: Skip for commercial invoices (created later for accounting)
                gap_days = (creation_date - receipt_date).days
                
                # Use the DocumentProfile object loaded from doc_class
                from app.pipelines.doc_profiles import get_profile_for_doc_class
                doc_class = tf.get("doc_class", "UNKNOWN")
                profile_obj = get_profile_for_doc_class(doc_class)
                
                profile_threshold = profile_obj.date_gap_threshold_days
                should_check_gap = should_apply_rule(profile_obj, "R16_SUSPICIOUS_DATE_GAP")
                
                if not should_check_gap:
                    logger.info(f"R16_SUSPICIOUS_DATE_GAP skipped for {doc_class} (profile: apply_date_gap_rules=False)")
                elif profile_threshold is None:
                    logger.info(f"R16_SUSPICIOUS_DATE_GAP skipped for {doc_class} (profile: no threshold)")
                elif gap_days > profile_threshold:
                    # Get doc profile confidence for severity adjustment
                    dp_conf_val = 0.0
                    try:
                        dp_conf_val = float(legacy_doc_profile.get("confidence") or 0.0)
                    except Exception:
                        dp_conf_val = 0.0
                    
                    # Downgrade severity for low-confidence docs with moderate gaps
                    if dp_conf_val < 0.4 and gap_days < 540:
                        severity = "WARNING"
                        raw_weight = 0.10
                    else:
                        severity = "CRITICAL"
                        raw_weight = 0.35
                    
                    score += emit_event(
                        events=events,
                        reasons=reasons,
                        rule_id="R16_SUSPICIOUS_DATE_GAP",
                        severity=severity,
                        weight=raw_weight,
                        message=f"File created {gap_days} days after receipt date",
                        evidence={
                            "receipt_date": receipt_date_str,
                            "creation_date": creation_date_str,
                            "gap_days": gap_days,
                            "doc_profile_confidence": dp_conf_val,
                            "severity_downgraded": (severity == "WARNING"),
                            "profile_threshold": profile_threshold,
                            "profile_gated": True,
                        },
                        reason_text=(
                            f"📅⚠️ Suspicious Date Gap: File created {gap_days} days "
                            f"after receipt date (backdating pattern)."
                        ),
                    )
    elif receipt_date_str and not receipt_date:
        score += emit_event(
            events=events,
            reasons=reasons,
            rule_id="R17_UNPARSABLE_DATE",
            severity="CRITICAL",
            weight=0.25,
            message="Receipt date present but unparsable",
            evidence={"receipt_date_str": receipt_date_str},
            reason_text=f"📅❓ Unparsable Date: '{receipt_date_str}' cannot be parsed into known format.",
        )

    # ---------------------------------------------------------------------------
    # RULE GROUP 5B: Plausibility checks (expert-style analysis)
    # ---------------------------------------------------------------------------

    # R_ROUND_TOTAL: Suspiciously round total amounts
    # Expert insight: Real receipts almost never have perfectly round totals
    # (e.g., $500.00, $1000.00) because tax makes them uneven.
    # Common in fabricated receipts where the fraudster picks a round number.
    try:
        _rt_val = _normalize_amount_str(tf.get("total_amount"))
        if _rt_val is not None and _rt_val >= 50.0:
            # Check if total is a "round" number (no cents, divisible by 50 or 100)
            is_round = (_rt_val == int(_rt_val)) and (int(_rt_val) % 50 == 0)
            # Don't flag small round amounts (coffee shops often have $5, $10 totals)
            # Don't flag if tax was extracted (tax presence makes round totals less suspicious)
            has_tax = bool(tf.get("tax_amount"))
            if is_round and not has_tax and _rt_val >= 100.0:
                score += emit_event(
                    events=events,
                    reasons=reasons,
                    rule_id="R_ROUND_TOTAL",
                    severity="WARNING",
                    weight=0.08,
                    message=f"Suspiciously round total amount (${_rt_val:.2f})",
                    evidence={
                        "total_amount": _rt_val,
                        "is_round": True,
                        "has_tax": has_tax,
                    },
                    reason_text=f"💰 Round Total: Total of ${_rt_val:.2f} is suspiciously round — real receipts rarely have perfectly round totals after tax.",
                )
    except Exception as e:
        logger.warning(f"R_ROUND_TOTAL check failed: {e}")

    # R_TAX_RATE_ANOMALY: Tax rate doesn't match country norms
    # Expert insight: Each country has specific tax rates. A US receipt with 25% tax
    # or an Indian receipt with 3% GST is suspicious.
    try:
        _tax_val = _normalize_amount_str(tf.get("tax_amount"))
        _subtotal_val = _normalize_amount_str(tf.get("subtotal"))
        _total_val = _normalize_amount_str(tf.get("total_amount"))
        geo_country = tf.get("geo_country_guess", "").upper()
        geo_conf = float(tf.get("geo_confidence", 0) or 0)

        # Only check if we have tax, a base amount, and confident geo
        if _tax_val is not None and _tax_val > 0 and geo_conf >= 0.6:
            # Determine base amount (prefer subtotal, fall back to total - tax)
            base = _subtotal_val
            if base is None and _total_val is not None:
                base = _total_val - _tax_val
            if base is not None and base > 0:
                tax_rate = (_tax_val / base) * 100  # as percentage

                # Country-specific expected tax ranges
                TAX_RANGES = {
                    "US": (0.0, 12.0),   # US sales tax: 0-11.45%
                    "IN": (4.5, 30.0),   # India GST: 5%, 12%, 18%, 28%
                    "GB": (0.0, 22.0),   # UK VAT: 0%, 5%, 20%
                    "CA": (4.5, 16.0),   # Canada GST+PST: 5-15%
                    "AU": (9.0, 11.0),   # Australia GST: 10%
                    "AE": (4.5, 6.0),    # UAE VAT: 5%
                    "SA": (14.0, 16.0),  # Saudi VAT: 15%
                    "DE": (0.0, 21.0),   # Germany VAT: 7%, 19%
                    "FR": (0.0, 22.0),   # France VAT: 5.5%, 10%, 20%
                }
                expected_range = TAX_RANGES.get(geo_country)

                if expected_range:
                    low, high = expected_range
                    if tax_rate < low - 1.0 or tax_rate > high + 2.0:
                        # Tax rate is outside expected range (with tolerance)
                        score += emit_event(
                            events=events,
                            reasons=reasons,
                            rule_id="R_TAX_RATE_ANOMALY",
                            severity="WARNING",
                            weight=0.10,
                            message=f"Tax rate {tax_rate:.1f}% unusual for {geo_country} (expected {low:.0f}-{high:.0f}%)",
                            evidence={
                                "tax_amount": _tax_val,
                                "base_amount": base,
                                "tax_rate_pct": round(tax_rate, 2),
                                "geo_country": geo_country,
                                "geo_confidence": geo_conf,
                                "expected_range_pct": list(expected_range),
                            },
                            reason_text=f"💰 Tax Rate Anomaly: {tax_rate:.1f}% tax is unusual for {geo_country} (expected {low:.0f}-{high:.0f}%). May indicate amount manipulation.",
                        )
    except Exception as e:
        logger.warning(f"R_TAX_RATE_ANOMALY check failed: {e}")

    # R_AMOUNT_PLAUSIBILITY: Total amount implausible for merchant type
    # Expert insight: A $5,000 coffee shop receipt or a $50,000 gas station receipt
    # is highly suspicious. Real-world merchants have typical transaction ranges.
    try:
        _ap_total = _normalize_amount_str(tf.get("total_amount"))
        _ap_merchant = (
            tf.get("merchant_candidate") or tf.get("merchant") or ""
        ).lower()
        _ap_subtype = str(
            legacy_doc_profile.get("subtype") or tf.get("doc_subtype_guess") or ""
        ).upper()

        if _ap_total is not None and _ap_total > 0 and (_ap_merchant or _ap_subtype):
            # Merchant-type → (typical_max, label) mapping
            # These are deliberately generous ceilings; only truly absurd values fire.
            _MERCHANT_RANGES = {
                "coffee":    (200,   "coffee shop"),
                "cafe":      (200,   "cafe"),
                "starbucks": (200,   "coffee shop"),
                "dunkin":    (200,   "coffee shop"),
                "bakery":    (300,   "bakery"),
                "fast food": (300,   "fast food"),
                "mcdonald":  (300,   "fast food"),
                "burger":    (300,   "fast food"),
                "kfc":       (300,   "fast food"),
                "subway":    (200,   "fast food"),
                "pizza":     (500,   "pizza"),
                "restaurant":(2000,  "restaurant"),
                "diner":     (500,   "diner"),
                "bar":       (1000,  "bar"),
                "pub":       (1000,  "pub"),
                "gas station":(500,  "gas station"),
                "fuel":      (500,   "fuel station"),
                "petrol":    (500,   "fuel station"),
                "parking":   (200,   "parking"),
                "taxi":      (500,   "taxi/ride"),
                "uber":      (500,   "taxi/ride"),
                "lyft":      (500,   "taxi/ride"),
                "ola":       (500,   "taxi/ride"),
                "grocery":   (1000,  "grocery store"),
                "supermarket":(2000, "supermarket"),
                "pharmacy":  (1000,  "pharmacy"),
                "convenience":(500,  "convenience store"),
            }

            # Also infer from doc_subtype
            _SUBTYPE_RANGES = {
                "POS_RESTAURANT": (3000,  "restaurant receipt"),
                "FUEL":           (500,   "fuel receipt"),
                "PARKING":        (200,   "parking receipt"),
                "TRANSPORT":      (1000,  "transport receipt"),
            }

            matched_label = None
            matched_max = None

            # Check merchant name first (more specific)
            for keyword, (max_amt, label) in _MERCHANT_RANGES.items():
                if keyword in _ap_merchant:
                    matched_label = label
                    matched_max = max_amt
                    break

            # Fall back to subtype range
            if matched_max is None and _ap_subtype in _SUBTYPE_RANGES:
                matched_max, matched_label = _SUBTYPE_RANGES[_ap_subtype]

            if matched_max is not None and _ap_total > matched_max * 2:
                # Total is > 2× the generous ceiling — very suspicious
                severity = "CRITICAL" if _ap_total > matched_max * 5 else "WARNING"
                weight = 0.20 if severity == "CRITICAL" else 0.10
                score += emit_event(
                    events=events,
                    reasons=reasons,
                    rule_id="R_AMOUNT_PLAUSIBILITY",
                    severity=severity,
                    weight=weight,
                    message=f"Total ${_ap_total:.2f} implausible for {matched_label} (typical max ~${matched_max})",
                    evidence={
                        "total_amount": _ap_total,
                        "merchant_candidate": _ap_merchant,
                        "doc_subtype": _ap_subtype,
                        "matched_label": matched_label,
                        "typical_max": matched_max,
                        "ratio": round(_ap_total / matched_max, 1),
                    },
                    reason_text=(
                        f"💰 Implausible Amount: ${_ap_total:.2f} at a {matched_label} "
                        f"is unusually high (typical max ~${matched_max}). "
                        f"May indicate amount inflation."
                    ),
                )
    except Exception as e:
        logger.warning(f"R_AMOUNT_PLAUSIBILITY check failed: {e}")

    # ---------------------------------------------------------------------------
    # RULE GROUP 5C: Address Validation (consumes features.py address signals)
    # ---------------------------------------------------------------------------
    # address_profile and merchant_address_consistency are extracted in features.py
    # but were never consumed by the scoring engine — this is the bridge.
    try:
        address_profile = tf.get("address_profile") or {}
        addr_classification = address_profile.get("address_classification", "")
        merchant_addr_consistency = tf.get("merchant_address_consistency") or {}

        # R_ADDRESS_FAKE: Detect known fake/placeholder address patterns
        addr_evidence_list = address_profile.get("address_evidence", [])
        if any("fake" in str(e).lower() or "placeholder" in str(e).lower() for e in addr_evidence_list):
            score += emit_event(
                events=events,
                reasons=reasons,
                rule_id="R_ADDRESS_FAKE",
                severity="CRITICAL",
                weight=0.30,
                message="Address appears to be a fake/placeholder",
                evidence={
                    "address_classification": addr_classification,
                    "address_evidence": addr_evidence_list,
                },
                reason_text="📍 Fake Address: Document contains a known fake/placeholder address pattern.",
            )

        # R_ADDRESS_MISSING: No address on document types that require one
        # (invoices, commercial docs — but NOT POS receipts which often lack addresses)
        doc_family_addr = legacy_doc_profile.get("family", "").upper()
        doc_subtype_addr = legacy_doc_profile.get("subtype", "").upper()
        expects_address = doc_family_addr in ("INVOICE", "COMMERCIAL") or "INVOICE" in doc_subtype_addr
        is_pos_receipt = doc_subtype_addr.startswith("POS_")

        if expects_address and addr_classification in ("NOT_AN_ADDRESS", ""):
            dp_conf_addr = float(legacy_doc_profile.get("confidence", 0) or 0)
            if dp_conf_addr >= 0.6:
                score += emit_event(
                    events=events,
                    reasons=reasons,
                    rule_id="R_ADDRESS_MISSING",
                    severity="WARNING",
                    weight=0.10,
                    message="Invoice/commercial document has no detectable address",
                    evidence={
                        "address_classification": addr_classification,
                        "doc_family": doc_family_addr,
                        "doc_subtype": doc_subtype_addr,
                        "doc_profile_confidence": dp_conf_addr,
                    },
                    reason_text="📍 No Address: Invoice/commercial document is missing an address — unusual for legitimate business documents.",
                )

        # R_ADDRESS_IMPLAUSIBLE: Weak address structure (not fake, but not convincing)
        if addr_classification == "WEAK_ADDRESS" and not is_pos_receipt:
            addr_score = address_profile.get("address_score", 0)
            if addr_score <= 2:
                score += emit_event(
                    events=events,
                    reasons=reasons,
                    rule_id="R_ADDRESS_IMPLAUSIBLE",
                    severity="WARNING",
                    weight=0.08,
                    message="Address structure is implausible (very weak evidence)",
                    evidence={
                        "address_classification": addr_classification,
                        "address_score": addr_score,
                        "address_evidence": addr_evidence_list,
                    },
                    reason_text="📍 Weak Address: Document address has very weak structural evidence — may be fabricated.",
                )

        # R_ADDRESS_MERCHANT_MISMATCH: Merchant name inconsistent with address
        mac_verdict = merchant_addr_consistency.get("verdict", "")
        if mac_verdict in ("INCONSISTENT", "SUSPICIOUS"):
            mac_confidence = float(merchant_addr_consistency.get("confidence", 0) or 0)
            if mac_confidence >= 0.6:
                severity = "CRITICAL" if mac_verdict == "INCONSISTENT" else "WARNING"
                weight = 0.15 if mac_verdict == "INCONSISTENT" else 0.08
                score += emit_event(
                    events=events,
                    reasons=reasons,
                    rule_id="R_ADDRESS_MERCHANT_MISMATCH",
                    severity=severity,
                    weight=weight,
                    message=f"Merchant name inconsistent with address ({mac_verdict})",
                    evidence={
                        "verdict": mac_verdict,
                        "confidence": mac_confidence,
                        "merchant_address_consistency": merchant_addr_consistency,
                    },
                    reason_text=f"📍🏪 Merchant-Address Mismatch: The merchant name doesn't match the address on the document ({mac_verdict}).",
                )
    except Exception as e:
        logger.warning(f"Address validation rules failed: {e}")

    # ---------------------------------------------------------------------------
    # RULE GROUP 6: Apply learned rules from feedback
    # ---------------------------------------------------------------------------

    if apply_learned:
        # ------------------------------------------------------------------
        # Safety: learned rules expect a legacy-style doc_profile dict.
        # Create backward-compat alias in this scope to avoid NameError.
        # ------------------------------------------------------------------
        doc_profile = legacy_doc_profile  # Alias for older learned-rule code paths
        
        try:
            from app.pipelines.learning import apply_learned_rules

            learned_adjustment, triggered_rules = apply_learned_rules(features.__dict__)

            # Compute doc profile confidence and optional subtype once
            dp_conf = 0.0
            try:
                dp_conf = float(legacy_doc_profile.get("confidence") or 0.0)
            except Exception:
                dp_conf = 0.0

            st = (legacy_doc_profile.get("subtype") or "").upper() if isinstance(legacy_doc_profile, dict) else ""
            optional_subtype = (
                st in _DOC_SUBTYPES_TOTAL_OPTIONAL
                or st in _DOC_SUBTYPES_AMOUNTS_OPTIONAL
                or st in _DOC_SUBTYPES_DATE_OPTIONAL
            )

            # Apply learned rules using refactored mini-engine
            delta = _apply_learned_rules(
                triggered_rules=list(triggered_rules or []),
                events=events,
                reasons=reasons,
                tf=tf,
                doc_profile=legacy_doc_profile,
                missing_fields_enabled=missing_fields_enabled,
                dp_conf=dp_conf,
                optional_subtype=optional_subtype,
            )

            if delta != 0.0:
                score += float(delta)
                score = max(0.0, min(1.0, float(score)))

        except Exception as e:
            logger.warning(f"Failed to apply learned rules: {e}")
            
            # Emit INFO event for learned rule failure with doc-profile context
            emit_event(
                events=events,
                reasons=None,
                rule_id="LEARNED_RULES_FAILURE",
                severity="INFO",
                weight=0.0,
                message=f"Failed to apply learned rules: {str(e)}",
                evidence={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "doc_subtype_guess": tf.get("doc_subtype_guess"),
                    "doc_profile_confidence": tf.get("doc_profile_confidence"),
                },
            )
            
            # Reduce confidence factor due to system error
            conf_factor = max(0.5, conf_factor * 0.8)

    # ---------------------------------------------------------------------------
    # R10: Template Quality Cluster (TQC)
    # ---------------------------------------------------------------------------
    """
    CLUSTER_ID: TQC_TEMPLATE_QUALITY
    RULE_ID: R10_TEMPLATE_QUALITY
    
    ALLOWED_DOC_FAMILIES:
      - POS_RECEIPT
      - COMMERCIAL_INVOICE
      - TAX_INVOICE
    
    INTENT: template_integrity_soft_signal
    
    FAILURE_MODE: soft_signal_only
    SEVERITY_RANGE: INFO → WARNING
    MAX_WEIGHT: 0.05
    
    GATES:
      - doc_profile_confidence >= 0.75
      - keyword_checks require lang_confidence >= 0.60
      - date_checks require geo_confidence >= 0.70
    
    LANGUAGE_SUPPORT:
      - keyword checks: language-specific (opt-in)
      - spacing checks: language-agnostic
    
    SAFETY:
      - MUST NOT flip REAL → FAKE alone
      - MUST NOT fire on UNKNOWN family
    
    VERSION: 1.0
    """
    # Hard gates
    doc_family = legacy_doc_profile.get("family", "").upper()
    execution_mode = get_execution_mode("R10_TEMPLATE_QUALITY", doc_family)
    
    if execution_mode == ExecutionMode.FORBIDDEN:
        logger.debug(f"R10_TEMPLATE_QUALITY skipped: {doc_family} forbidden")
    else:
        dp_conf_val = tf.get("doc_profile_confidence") or legacy_doc_profile.get("confidence") or 0.0
        try:
            dp_conf_val = float(dp_conf_val)
        except Exception:
            dp_conf_val = 0.0
        
        if dp_conf_val >= 0.75:
            tqc_score = 0.0
            evidence = {}
            
            # Canonicalize full_text for signal detectors
            # Many pipelines don't populate full_text, so we use _join_text()
            # which prefers tf["raw_text"]/tf["text"], else falls back to lf["lines"]
            tf_for_tqc = dict(tf)
            if not tf_for_tqc.get("full_text"):
                tf_for_tqc["full_text"] = _join_text(tf, lf)
            
            # ---------- S1: Keyword typo detector (language-gated) ----------
            lang = tf.get("lang_guess")
            lang_conf = float(tf.get("lang_confidence") or 0.0)
            
            # Gate: lang_conf >= 0.60 AND lang != "mixed"
            # Mixed-language receipts should not trigger spelling checks
            if lang_conf >= 0.60 and lang != "mixed":
                delta, ev = detect_keyword_typos(tf_for_tqc, lang)
                tqc_score += delta
                if ev:
                    evidence["keyword_typos"] = ev
            
            # ---------- S2: Spacing anomaly (always allowed) ----------
            delta, ev = detect_spacing_anomaly(tf_for_tqc)
            tqc_score += delta
            if ev:
                evidence["spacing_anomaly"] = ev
            
            # ---------- S3: Date format mismatch (geo-gated, weak) ----------
            geo_conf = float(tf.get("geo_confidence") or 0.0)
            if geo_conf >= 0.70:
                delta, ev = detect_date_format_anomaly(tf_for_tqc)
                tqc_score += delta
                if ev:
                    evidence["date_format"] = ev
            
            # ---------- Language Confidence Weighting ----------
            # Adjust signal weight based on language detection confidence
            # High confidence (>0.8) → full weight
            # Medium confidence (0.6-0.8) → 70% weight
            # Low confidence (<0.6) → already gated out by S1
            
            lang_conf_factor = 1.0
            if lang_conf < 0.80:
                # Medium confidence: reduce weight to avoid false positives
                lang_conf_factor = 0.70
            
            # Apply language confidence factor to TQC score
            tqc_score_adjusted = tqc_score * lang_conf_factor
            
            # ---------- Cap & emit ----------
            MAX_WEIGHT = 0.05
            applied = min(MAX_WEIGHT, tqc_score_adjusted * MAX_WEIGHT)
            
            if applied > 0:
                severity = "INFO" if applied < 0.03 else "WARNING"
                
                score += emit_event(
                    events=events,
                    reasons=reasons,
                    rule_id="R10_TEMPLATE_QUALITY",
                    severity=severity,
                    weight=applied,
                    message="Template quality anomalies detected",
                    evidence=evidence,
                    reason_text="📝 Template Quality: Document contains formatting or spelling anomalies.",
                )

    # ---------------------------------------------------------------------------
    # Final label determination (single source of truth)
    # ---------------------------------------------------------------------------
    score = max(0.0, min(1.0, float(score)))
    has_hard_fail = any(e.severity == "HARD_FAIL" for e in events)
    critical_count = sum(1 for e in events if e.severity == "CRITICAL")
    
    if has_hard_fail:
        label = "fake"
    elif critical_count >= 2:
        label = "fake"
    elif score >= 0.70:
        label = "fake"
    elif score >= 0.35:
        label = "suspicious"
    else:
        label = "real"
    
    # Extract full geo profile for ensemble audit trail
    geo_profile_debug = {
        "family": legacy_doc_profile.get("family"),
        "subtype": legacy_doc_profile.get("subtype"),
        "confidence": legacy_doc_profile.get("confidence"),
        "evidence": legacy_doc_profile.get("evidence"),
        # Add geo-aware fields if available
        "lang_guess": tf.get("lang_guess"),
        "lang_confidence": tf.get("lang_confidence"),
        "geo_country_guess": tf.get("geo_country_guess"),
        "geo_confidence": tf.get("geo_confidence"),
        "geo_evidence": tf.get("geo_evidence"),
    }
    
    return ReceiptDecision(
        score=score,
        label=label,
        reasons=reasons,
        minor_notes=minor_notes,
        events=[asdict(e) for e in events],
        rule_version=RULE_VERSION,
        policy_version=POLICY_VERSION,
        engine_version=ENGINE_VERSION,
        debug={
            "doc_profile": geo_profile_debug,
            "vision_assessment": vision_assessment or {},
        },
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_receipt(
    file_path: str,
    extracted_total: str = None,
    extracted_merchant: str = None,
    extracted_date: str = None,
    apply_learned: bool = True,
    vision_assessment: Optional[Dict[str, Any]] = None,
) -> ReceiptDecision:
    """
    Main entry point for receipt analysis.
    
    Args:
        file_path: Path to receipt file (PDF or image)
        extracted_total: Optional pre-extracted total from other engines
        extracted_merchant: Optional pre-extracted merchant from other engines
        extracted_date: Optional pre-extracted date from other engines
        apply_learned: Whether to apply learned rules from feedback
        vision_assessment: Optional vision veto payload from vision_llm (e.g., {"visual_integrity": "clean|suspicious|tampered", "confidence": 0..1, "observable_reasons": [...]})
        
    Returns:
        ReceiptDecision with label, score, reasons, and audit events
    """
    # 1. Create ReceiptInput from file path
    from app.schemas.receipt import ReceiptInput
    receipt_input = ReceiptInput(file_path=file_path)
    
    # 2. Ingest the receipt file and run OCR with preprocessing
    raw = ingest_and_ocr(receipt_input, preprocess=True)
    
    # 3. Build features from the raw receipt data
    features = build_features(raw)
    
    # 3. If we have extracted data from other engines, enhance the features
    if extracted_total:
        features.text_features["total_amount"] = extracted_total
    if extracted_merchant:
        features.text_features["merchant_candidate"] = extracted_merchant
    if extracted_date:
        features.text_features["date_extracted"] = extracted_date
    
    # 4. Run rule-based analysis
    return _score_and_explain(features, apply_learned=apply_learned, vision_assessment=vision_assessment)
    