# app/pipelines/rules.py

# app/pipelines/rules.py

import logging
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from app.pipelines.features import build_features
from app.pipelines.ingest import ingest_and_ocr
from app.schemas.receipt import ReceiptDecision, ReceiptFeatures, ReceiptInput


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

    ev = RuleEvent(
        rule_id=rule_id,
        severity=sev,
        weight=applied_w,
        raw_weight=raw_w,
        message=str(message or ""),
        evidence=evidence or {},
    )

    # copy evidence and attach audit fields
    ev.evidence = dict(ev.evidence or {})
    ev.evidence.setdefault("confidence_factor", cf_used)
    ev.evidence.setdefault("raw_weight", raw_w)
    ev.evidence.setdefault("applied_weight", applied_w)
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
    """
    c = tf.get("confidence")

    conf: Optional[float] = None
    if isinstance(c, (int, float)):
        try:
            conf = float(c)
        except Exception:
            conf = None
    elif isinstance(c, str):
        cl = c.strip().lower()
        if cl in ("high", "h"):
            conf = 0.90
        elif cl in ("medium", "med", "m"):
            conf = 0.70
        elif cl in ("low", "l"):
            conf = 0.45

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
    if subtype == "UNKNOWN" and doc_type_hint:
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
    }


def _expects_total_line(doc_profile: Dict[str, Any]) -> bool:
    subtype = (doc_profile.get("subtype") or "UNKNOWN").upper()
    # If we are not confident about the subtype, do not be strict
    if float(doc_profile.get("confidence") or 0.0) < 0.55:
        return False
    return subtype not in _DOC_SUBTYPES_TOTAL_OPTIONAL


def _expects_amounts(doc_profile: Dict[str, Any]) -> bool:
    subtype = (doc_profile.get("subtype") or "UNKNOWN").upper()
    if float(doc_profile.get("confidence") or 0.0) < 0.55:
        return False
    return subtype not in _DOC_SUBTYPES_AMOUNTS_OPTIONAL


def _expects_date(doc_profile: Dict[str, Any]) -> bool:
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
    import re

    t = (text or "").upper()
    return bool(re.search(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b", t))


def _looks_like_pan(text: str) -> bool:
    """Indian PAN: 10 chars: 5 letters + 4 digits + 1 letter."""
    import re

    t = (text or "").upper()
    return bool(re.search(r"\b[A-Z]{5}\d{4}[A-Z]\b", t))


def _looks_like_ein(text: str) -> bool:
    """US EIN: 2 digits hyphen 7 digits (e.g., 12-3456789)."""
    import re

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
    """Lightweight India signal: state names, PIN (6 digits), +91, INR."""
    import re

    t = (text or "").lower()
    if "+91" in t or "india" in t or " inr" in t or "₹" in t:
        return True
    if re.search(r"\b\d{6}\b", t):  # PIN
        return True
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
        "odisha",
        "punjab",
        "haryana",
        "delhi",
        "assam",
        "goa",
    ]
    return any(s in t for s in states)
# -----------------------------------------------------------------------------
# Canada geography detection helper
# -----------------------------------------------------------------------------
def _detect_canada_hint(text: str) -> bool:
    """
    Lightweight Canada signal: looks for province names, cities, tax terms, +1 with Canadian context,
    or Canadian postal codes (e.g., M5V 2T6).
    """
    import re
    t = (text or "").lower()
    # Province/city/region hints
    canada_hints = [
        "canada",
        "ontario",
        "toronto",
        "vancouver",
        "british columbia",
        "bc",
        "on",
        "qc",
        "gst",
        "hst",
        "pst",
        "cra",
        # "+1" (Canadian context only - require another Canada hint to be present)
    ]
    if any(h in t for h in canada_hints):
        return True
    # "+1" as phone code, but only if another Canada hint is present
    if "+1" in t:
        # Look for Canada context in a window of 50 chars around "+1"
        idx = t.find("+1")
        window = t[max(0, idx - 50): idx + 50]
        if any(h in window for h in ["canada", "ontario", "toronto", "vancouver", "bc", "qc"]):
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
    """Lightweight UK signal: UK country/city terms, VAT, UK postcodes, +44."""
    import re
    t = (text or "").lower()
    if "+44" in t or "united kingdom" in t or "uk" in t or "london" in t or "england" in t or "scotland" in t:
        return True
    # UK postcode (very loose) e.g., SW1A 1AA, EC1A 1BB
    if re.search(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b", t, re.I):
        return True
    if "vat" in t:
        return True
    return False


def _detect_eu_hint(text: str) -> bool:
    """Lightweight EU signal: EUR, VAT, common EU country/city names, EU VAT ID-like patterns."""
    import re
    t = (text or "").lower()
    eu_hints = [
        "europe", "eu ", "germany", "berlin", "france", "paris", "spain", "madrid", "italy", "rome",
        "netherlands", "amsterdam", "ireland", "dublin", "belgium", "brussels", "austria", "vienna",
        "sweden", "stockholm", "denmark", "copenhagen", "finland", "helsinki", "poland", "warsaw",
    ]
    if any(h in t for h in eu_hints):
        return True
    if "eur" in t or "€" in t:
        return True
    if "vat" in t:
        return True
    # EU VAT ID-ish (very rough): country code + 8-12 alnum
    if re.search(r"\b[A-Z]{2}[A-Z0-9]{8,12}\b", (text or "").upper()):
        return True
    return False


def _detect_sg_hint(text: str) -> bool:
    """Lightweight Singapore signal: SG/ Singapore, +65, GST (SG), postal codes (6 digits)."""
    import re
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
    import re
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
        "vat",
    ]):
        return True
    return False

def _detect_saudi_hint(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in [
        "saudi", "saudi arabia", "kingdom of saudi arabia", "ksa",
        "riyadh", "jeddah", "dammam",
        "+966", "sar", "riyal", "vat",
        "السعودية",
    ])

def _detect_oman_hint(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in [
        "oman", "sultanate of oman", "muscat",
        "+968", "omr", "rial", "vat",
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
    return any(k in t for k in ["bahrain", "manama", "+973", "bhd", "dinar", "vat"])

def _detect_jordan_hint(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in [
        "jordan", "amman", "hashemite kingdom",
        "+962", "jod", "dinar",
        "الأردن",
    ])
    

def _detect_nz_hint(text: str) -> bool:
    """Lightweight New Zealand signal: New Zealand, NZ, +64, GST (NZ), IRD, cities."""
    import re
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
    import re
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

def _detect_sea_hint(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in [
        "singapore", "malaysia", "thailand", "indonesia", "philippines",
        "kuala lumpur", "bangkok", "jakarta", "manila",
        "+65", "+60", "+66", "+62", "+63"
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
    if _has_token("hkd") or "hk$" in tl:
        return "HKD"
    if _has_token("twd") or "nt$" in tl:
        return "TWD"

    # --- Southeast Asia ---
    if _has_token("sgd") or "s$" in t or "singapore dollar" in tl:
        return "SGD"
    if _has_token("myr") or "ringgit" in tl or ("rm" in tl and not _has_token("arm")):
        return "MYR"
    if _has_token("thb") or "฿" in t or "baht" in tl:
        return "THB"
    if _has_token("idr") or "rupiah" in tl or ("rp" in tl and not _has_token("grp")):
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

    # Fall back to v1 hinting
    return _currency_hint(text)


def _geo_currency_tax_consistency(
    text: str,
    merchant: Optional[str],
    reasons: List[str],
    minor_notes: List[str],
    events: List[RuleEvent],
) -> float:
    """Apply GeoRuleMatrix consistency checks.

    Returns incremental score to add.
    """
    score_delta = 0.0

    blob = text or ""
    currency = _currency_hint_extended(blob)
    tax = _tax_regime_hint(blob)
    geos = _detect_geo_candidates(blob)

    # If multiple geos detected, treat as cross-border (no penalty)
    if len(geos) >= 2:
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
        return score_delta

    # No geo detected → can't validate; keep as a minor note (no penalty)
    if len(geos) == 0:
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
        return score_delta

    region = geos[0]
    cfg = GEO_RULE_MATRIX.get(region, {})
    tier = cfg.get("tier", "RELAXED")

    expected_currencies = cfg.get("currencies", set())
    expected_taxes = cfg.get("tax_regimes", set())

    # -------------------- Currency mismatch --------------------
    currency_mismatch = bool(currency and expected_currencies and (currency not in expected_currencies))
    if currency_mismatch:
        score_delta += _emit_event(
            events=events,
            reasons=reasons,
            rule_id="GEO_CURRENCY_MISMATCH",
            severity="CRITICAL",
            weight=0.30,
            message="Currency does not match implied region",
            evidence={
                "region": region,
                "currency_detected": currency,
                "expected_currencies": sorted(list(expected_currencies)),
                "geo_candidates": geos,
                "tier": tier,
            },
            reason_text=(
                "💵🌍 Currency–Geography Consistency Issue:\n"
                f"   • Implied region: {region}\n"
                f"   • Detected currency: {currency}\n"
                f"   • Expected currencies: {sorted(list(expected_currencies))}\n"
                "Mismatches like this are common in fabricated or edited receipts."
            ),
        )

    # -------------------- Tax mismatch --------------------
    if tax and expected_taxes and (tax not in expected_taxes):
        score_delta += _emit_event(
            events=events,
            reasons=reasons,
            rule_id="GEO_TAX_MISMATCH",
            severity="CRITICAL",
            weight=0.18,
            message="Tax regime terminology does not match implied region",
            evidence={
                "region": region,
                "tax_detected": tax,
                "expected_taxes": sorted(list(expected_taxes)),
                "tier": tier,
            },
        )

    # STRICT tier softening for travel/hospitality cross-border receipts
    if tier == "STRICT" and currency_mismatch and _is_travel_or_hospitality(blob):
        minor_notes.append(
            "✈️ Travel/hospitality context detected. Currency–geo mismatch may be legitimate (cross-border). "
            "Downgrading severity to REVIEW and reducing penalty."
        )
        _emit_event(
            events=events,
            reasons=None,
            rule_id="GEO_TRAVEL_SOFTENER",
            severity="INFO",
            weight=0.0,
            message="Travel/hospitality context detected; reduced geo/currency mismatch penalty",
            evidence={"region": region, "currency_detected": currency, "tier": tier},
        )
        score_delta = max(0.0, score_delta - 0.15)

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
def _currency_hint(text: str) -> Optional[str]:
    """Return best-effort currency hint based on symbols/keywords.

    IMPORTANT:
    - `$` is ambiguous (USD, CAD, AUD, SGD, etc.) and MUST be handled last.
    - Prefer explicit currency codes/symbols first.
    """
    t = (text or "")
    tl = t.lower()

    def _has_token(s: str) -> bool:
        return f" {s} " in f" {tl} "

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
    if _has_token("myr") or "ringgit" in tl:
        return "MYR"
    if _has_token("thb") or "฿" in t or "baht" in tl:
        return "THB"
    if _has_token("idr") or "rupiah" in tl or ("rp" in tl and not _has_token("grp")):
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
      - unknown

    Notes:
    - Many fakes mix labels (e.g., "INVOICE" in header but styled like a receipt).
    - We only use this as a *consistency* signal; it's not a sole hard-fail.
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
    """Best-effort tax regime hint: GST/HST/PST/VAT/SALES_TAX/None based on keywords."""
    t = (text or "").lower()

    # GST family (India/SG/AU + sometimes CA)
    if "cgst" in t or "sgst" in t or "igst" in t:
        return "GST"
    if "gst" in t or "goods and services tax" in t:
        return "GST"

    # Canada-specific
    if "qst" in t or "quebec sales tax" in t:
        return "PST"
    if "pst" in t or "provincial sales tax" in t:
        return "PST"
    if "hst" in t or "harmonized sales tax" in t:
        return "HST"

    # VAT regions (UK/EU/Middle East etc.)
    if "vat" in t or "value added tax" in t:
        return "VAT"

    # US-style
    if any(k in t for k in ["sales tax", "state tax", "county tax", "city tax", "local tax"]):
        return "SALES_TAX"

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

def _parse_date_best_effort(date_str: Optional[str]):
    """
    Parse a date string from OCR/LLM into `datetime.date`.

    Receipt dates come in many formats (YYYY-MM-DD, DD/MM/YY, YYYY/MM/DD, etc.).
    If we can't parse a date that *looks present*, that's suspicious.
    Returns:
      - datetime.date on success
      - None on failure
    """
    if not date_str:
        return None

    s = str(date_str).strip()

    fmts = [
        "%Y-%m-%d",  # 2024-08-15
        "%Y/%m/%d",  # 2024/08/15
        "%d/%m/%Y",  # 15/08/2024
        "%d-%m-%Y",  # 15-08-2024
        "%m/%d/%Y",  # 08/15/2024
        "%m-%d-%Y",  # 08-15-2024
        "%y/%m/%d",  # 24/08/15 (YY/MM/DD)
        "%d/%m/%y",  # 15/08/24
        "%d-%m-%y",  # 15-08-24
        "%m/%d/%y",  # 08/15/24
    ]

    # Try full string, first token, last token (handles "Date: 2024/08/15 10:22")
    candidates = [s]
    parts = s.split()
    if parts:
        candidates.append(parts[0])
        candidates.append(parts[-1])

    for cand in candidates:
        c = cand.strip().strip(",;|")
        for fmt in fmts:
            try:
                return datetime.strptime(c, fmt).date()
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

def _score_and_explain(features: ReceiptFeatures, apply_learned: bool = True) -> ReceiptDecision:
    score = 0.0
    reasons: List[str] = []
    minor_notes: List[str] = []
    events: List[RuleEvent] = []

    ff = features.file_features
    tf = features.text_features
    lf = features.layout_features
    fr = features.forensic_features

    conf_factor = _confidence_factor_from_features(ff, tf, lf, fr)

    def emit_event(*, events, reasons, rule_id, severity, weight, message, evidence=None, reason_text=None):
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
        )
    except Exception:
        minor_notes.append("Geo consistency checks skipped due to an internal error.")

    # ---------------------------------------------------------------------------
    # RULE GROUP 1: Producer / metadata anomalies
    # ---------------------------------------------------------------------------
    producer = ff.get("producer", "")
    creator = ff.get("creator", "")
    suspicious_tools = [
        "canva", "photoshop", "illustrator", "sketch", "figma",
        "affinity", "gimp", "inkscape", "coreldraw", "pixlr",
        "fotor", "befunky", "snappa", "crello", "desygner",
        "wps", "ilovepdf", "smallpdf", "pdfcandy", "sejda",
    ]
    
    producer_lower = (producer or "").lower()
    creator_lower = (creator or "").lower()
    
    if any(tool in producer_lower or tool in creator_lower for tool in suspicious_tools):
        tool_found = next((t for t in suspicious_tools if t in producer_lower or t in creator_lower), "editing software")
        score += emit_event(
            events=events,
            reasons=reasons,
            rule_id="R1_SUSPICIOUS_SOFTWARE",
            severity="HARD_FAIL",
            weight=0.50,
            message=f"Suspicious software detected: {tool_found}",
            evidence={"producer": producer, "creator": creator, "tool": tool_found},
            reason_text=f"🚨 Suspicious Software Detected: '{tool_found}' - This software is commonly used to create fake receipts.",
        )

    if not ff.get("creation_date"):
        minor_notes.append("Document is missing a creation date in its metadata.")
    
    if not ff.get("mod_date"):
        minor_notes.append("Document is missing a modification date in its metadata.")
    
    if source_type == "image" and not ff.get("exif_present"):
        minor_notes.append("Image has no EXIF data (could be a screenshot or exported image).")

    # ---------------------------------------------------------------------------
    # RULE GROUP 2: Text-based checks (amounts, merchant, dates)
    # ---------------------------------------------------------------------------
    has_any_amount = tf.get("has_any_amount", False)
    total_line_present = tf.get("total_line_present", False)
    has_total_value = _has_total_value(tf)
    total_mismatch = tf.get("total_mismatch", False)
    has_date = tf.get("has_date", False)
    merchant_candidate = tf.get("merchant_candidate") or tf.get("merchant")

    # Doc-aware expectations (prevents false-positives on logistics docs etc.)
    doc_profile = _get_doc_profile(tf, doc_type_hint=doc_type_hint)
    expects_amounts = _expects_amounts(doc_profile)
    expects_total_line = _expects_total_line(doc_profile)
    expects_date = _expects_date(doc_profile)

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
            score += emit_event(
                events=events,
                reasons=reasons,
                rule_id="R5_NO_AMOUNTS",
                severity="CRITICAL",
                weight=0.40,
                message="No currency amounts detected in document",
                evidence={
                    "has_any_amount": False,
                    "doc_family": doc_profile.get("family"),
                    "doc_subtype": doc_profile.get("subtype"),
                    "doc_profile_confidence": doc_profile.get("confidence"),
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
                    "doc_family": doc_profile.get("family"),
                    "doc_subtype": doc_profile.get("subtype"),
                    "doc_profile_confidence": doc_profile.get("confidence"),
                },
            )

    if has_any_amount and not total_line_present:
        # If we can still extract a usable total value, do not penalize as "No Total Line".
        has_usable_total_value = bool(_has_total_value(tf) or has_extracted_total)

        if expects_total_line and not has_usable_total_value:
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
                    "doc_family": doc_profile.get("family"),
                    "doc_subtype": doc_profile.get("subtype"),
                    "doc_profile_confidence": doc_profile.get("confidence"),
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
                    "doc_family": doc_profile.get("family"),
                    "doc_subtype": doc_profile.get("subtype"),
                    "doc_profile_confidence": doc_profile.get("confidence"),
                },
            )

    if total_mismatch:
        score += emit_event(
            events=events,
            reasons=reasons,
            rule_id="R7_TOTAL_MISMATCH",
            severity="CRITICAL",
            weight=0.40,
            message="Line items do not sum to printed total",
            evidence={"total_mismatch": True},
            reason_text="⚠️ Total Mismatch: Sum of line items does not match the printed total.",
        )

    if not has_date:
        if expects_date:
            score += emit_event(
                events=events,
                reasons=reasons,
                rule_id="R8_NO_DATE",
                severity="CRITICAL",
                weight=0.20,
                message="No date found in document",
                evidence={
                    "has_date": False,
                    "doc_family": doc_profile.get("family"),
                    "doc_subtype": doc_profile.get("subtype"),
                    "doc_profile_confidence": doc_profile.get("confidence"),
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
                    "doc_family": doc_profile.get("family"),
                    "doc_subtype": doc_profile.get("subtype"),
                    "doc_profile_confidence": doc_profile.get("confidence"),
                },
            )

    if not merchant_candidate:
        score += emit_event(
            events=events,
            reasons=reasons,
            rule_id="R9_NO_MERCHANT",
            severity="CRITICAL",
            weight=0.15,
            message="No merchant name could be identified",
            evidence={"merchant_candidate": None},
            reason_text="🏪 No Merchant: Could not identify a merchant/vendor name.",
        )

    # Merchant plausibility checks
    if merchant_candidate:
        issues = _merchant_plausibility_issues(merchant_candidate)
        if issues:
            reason_msg = _format_merchant_issue_reason(merchant_candidate, issues)

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

    # Document type checks
    # _detect_document_type returns "unknown" when invoice+receipt language is mixed
    if doc_type_hint in ("ambiguous", "unknown"):
        score += emit_event(
            events=events,
            reasons=reasons,
            rule_id="R9B_DOC_TYPE_UNKNOWN_OR_MIXED",
            severity="CRITICAL",
            weight=0.15,
            message="Document type unclear or mixed (invoice/receipt language)",
            evidence={"doc_type": doc_type_hint},
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
    # RULE GROUP 5: Date validation (impossible dates, suspicious gaps)
    # ---------------------------------------------------------------------------
    receipt_date_str = tf.get("date_extracted") or tf.get("receipt_date")
    creation_date_str = ff.get("creation_date")

    if receipt_date_str and creation_date_str:
        receipt_date = _parse_date_best_effort(receipt_date_str)
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
                    reason_text=(
                        f"📅🚨 Impossible Date Sequence: Receipt dated {receipt_date} "
                        f"but file created {creation_date}."
                    ),
                )
            else:
                gap_days = (creation_date - receipt_date).days
                if gap_days > 2:
                    score += emit_event(
                        events=events,
                        reasons=reasons,
                        rule_id="R16_SUSPICIOUS_DATE_GAP",
                        severity="CRITICAL",
                        weight=0.35,
                        message=f"File created {gap_days} days after receipt date",
                        evidence={
                            "receipt_date": receipt_date_str,
                            "creation_date": creation_date_str,
                            "gap_days": gap_days,
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
    # RULE GROUP 6: Apply learned rules from feedback
    # ---------------------------------------------------------------------------     

    if apply_learned:
        try:
            from app.pipelines.learning import apply_learned_rules
            learned_adjustment, triggered_rules = apply_learned_rules(features.__dict__)
            # If doc profile confidence is low, learned rules are less reliable for missing-field claims.
            # Soft-gate the adjustment instead of fully skipping.
            
            if float(doc_profile.get("confidence") or 0.0) < 0.55:
                learned_adjustment *= 0.65

            # If this doc subtype often omits amounts/totals/dates, reduce learned penalties further.
            st = (doc_profile.get("subtype") or "").upper()
            if st in _DOC_SUBTYPES_TOTAL_OPTIONAL or st in _DOC_SUBTYPES_AMOUNTS_OPTIONAL or st in _DOC_SUBTYPES_DATE_OPTIONAL:
                learned_adjustment *= 0.60
            if learned_adjustment != 0.0:
                score += learned_adjustment
                score = max(0.0, min(1.0, score))
                for rule in triggered_rules:
                    reasons.append(f"[INFO] 🎓 Learned Rule: {rule}")
        except Exception as e:
            logger.warning(f"Failed to apply learned rules: {e}")

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
    
    return ReceiptDecision(
        score=score,
        label=label,
        reasons=reasons,
        minor_notes=minor_notes,
        events=[asdict(e) for e in events],
        rule_version=RULE_VERSION,
        policy_version=POLICY_VERSION,
        engine_version=ENGINE_VERSION,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_receipt(
    file_path: str,
    extracted_total: str = None,
    extracted_merchant: str = None,
    extracted_date: str = None,
    apply_learned: bool = True
) -> ReceiptDecision:
    """
    Main entry point for receipt analysis.
    
    Args:
        file_path: Path to receipt file (PDF or image)
        extracted_total: Optional pre-extracted total from other engines
        extracted_merchant: Optional pre-extracted merchant from other engines
        extracted_date: Optional pre-extracted date from other engines
        apply_learned: Whether to apply learned rules from feedback
        
    Returns:
        ReceiptDecision with label, score, reasons, and audit events
    """
    # 1. Create ReceiptInput from file path
    from app.schemas.receipt import ReceiptInput
    receipt_input = ReceiptInput(file_path=file_path)
    
    # 2. Ingest the receipt file and run OCR
    raw = ingest_and_ocr(receipt_input)
    
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
    return _score_and_explain(features, apply_learned=apply_learned)
    