# app/pipelines/features.py

import re
from dataclasses import asdict
from typing import Dict, Any, List, Tuple, Optional

from app.schemas.receipt import ReceiptRaw, ReceiptFeatures


# --- Helper: Suspicious PDF producers / tools -------------------------------

SUSPICIOUS_PRODUCERS = {
    "canva",
    "photoshop",
    "adobe photoshop",
    "wps",
    "fotor",
    "ilovepdf",
    "sejda",
    "smallpdf",
    "pdfescape",
    "dochub",
    "foxit",
    # PDF generators (commonly used for fake invoices)
    "tcpdf",           # PHP PDF library
    "fpdf",            # Another PHP PDF library
    "dompdf",          # PHP HTML to PDF
    "wkhtmltopdf",     # HTML to PDF converter
    # Invoice/receipt generators
    "conta.com",       # Invoice generator
    "invoice generator",
    "receipt maker",
    "fake receipt",
    "invoice maker",
}


# --- Helper: Basic text normalization ---------------------------------------

def _normalize_text(text: str) -> str:
    # Collapse multiple spaces, lowercase, strip
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def _get_all_text_pages(raw: ReceiptRaw) -> Tuple[str, List[str]]:
    page_texts = [_normalize_text(t or "") for t in raw.ocr_text_per_page]
    full_text = "\n".join(page_texts)
    return full_text, page_texts


# --- Helper: Amount extraction ----------------------------------------------

_AMOUNT_REGEX = re.compile(
    r"(?<!\w)(?:₹|rs\.?|inr)?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)


def _parse_amount(s: str) -> Optional[float]:
    try:
        # remove commas and currency symbols
        s_clean = s.replace(",", "")
        s_clean = re.sub(r"[^\d.]", "", s_clean)
        if not s_clean:
            return None
        return float(s_clean)
    except ValueError:
        return None


def _extract_candidate_amounts(lines: List[str]) -> List[float]:
    amounts: List[float] = []
    for line in lines:
        for match in _AMOUNT_REGEX.finditer(line):
            amt = _parse_amount(match.group(1))
            if amt is not None:
                amounts.append(amt)
    return amounts


def _find_total_line(lines: List[str]) -> Tuple[Optional[str], Optional[float]]:
    """
    Try to find a line that looks like the 'Total' line and extract its amount.
    We look for keywords and then pick the last such line.
    """
    total_keywords = [
        "total",
        "grand total",
        "amount payable",
        "amount due",
        "net total",
        "balance due",
    ]

    candidate_lines: List[Tuple[int, str]] = []
    for idx, line in enumerate(lines):
        lower = line.lower()
        if any(k in lower for k in total_keywords):
            candidate_lines.append((idx, line))

    if not candidate_lines:
        return None, None

    # Pick the last occurrence (usually the actual payable total)
    _, total_line = candidate_lines[-1]

    # Find amount on that line
    match = _AMOUNT_REGEX.search(total_line)
    if match:
        amt = _parse_amount(match.group(1))
        return total_line, amt

    return total_line, None


def _extract_line_item_amounts(lines: List[str]) -> List[float]:
    """
    Very naive v1 line-item detector:
    - line contains some text and ends with an amount
    - we simply pick numbers at the end of a line
    """
    line_item_amounts: List[float] = []
    for line in lines:
        # Skip empty / very short
        if len(line.strip()) < 3:
            continue

        # Try to match amount near the end of the line
        match = re.search(r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)\s*$", line)
        if match:
            amt = _parse_amount(match.group(1))
            if amt is not None:
                line_item_amounts.append(amt)

    return line_item_amounts


# --- Helper: Date extraction (simple) ---------------------------------------

_DATE_REGEXES = [
    # 12/11/2025, 12-11-2025
    re.compile(r"\b([0-3]?\d)[/-]([0-1]?\d)[/-]((?:20)?\d{2})\b"),
    # 2025-11-12
    re.compile(r"\b(20\d{2})[-/]([0-1]?\d)[-/]([0-3]?\d)\b"),
    # Nov 14, 2025 or Nov 14 2025
    re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+([0-3]?\d),?\s+(20\d{2})\b", re.I),
    # 14 Nov 2025
    re.compile(r"\b([0-3]?\d)\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(20\d{2})\b", re.I),
    # November 14, 2025
    re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+([0-3]?\d),?\s+(20\d{2})\b", re.I),
]


def _has_any_date(text: str) -> bool:
    for rx in _DATE_REGEXES:
        if rx.search(text):
            return True
    return False


def _extract_receipt_date(text: str) -> Optional[str]:
    """
    Extract the first date found in the receipt text.
    Returns date string in a normalized format or None.
    """
    from datetime import datetime
    
    for rx in _DATE_REGEXES:
        match = rx.search(text)
        if match:
            date_str = match.group(0)
            # Try to parse and normalize the date
            try:
                # Try various date formats
                formats = [
                    "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y",
                    "%d %b %Y", "%d %B %Y",  # 14 Nov 2025, 14 November 2025
                    "%b %d, %Y", "%b %d %Y",  # Nov 14, 2025, Nov 14 2025
                    "%B %d, %Y", "%B %d %Y",  # November 14, 2025
                ]
                for fmt in formats:
                    try:
                        parsed = datetime.strptime(date_str, fmt)
                        return parsed.strftime("%Y-%m-%d")  # Normalize to YYYY-MM-DD
                    except:
                        continue
                # If parsing fails, return the original string
                return date_str
            except:
                return date_str
    return None


# --- Helper: Merchant candidate line ----------------------------------------

def _guess_merchant_line(lines: List[str]) -> Optional[str]:
    """
    Heuristic:
    - First non-empty line
    - That is not mostly numbers
    - That is not just 'tax invoice' or purely generic text
    """
    generic_words = {"tax invoice", "invoice", "receipt", "bill", "cash memo"}

    for line in lines[:8]:  # look only at top few lines
        l = line.strip()
        if not l:
            continue
        lower = l.lower()
        if any(g == lower for g in generic_words):
            continue
        # skip if too numeric
        digits = sum(c.isdigit() for c in l)
        if digits > 0 and digits / max(1, len(l)) > 0.5:
            continue
        return l

    return None


# --- Helper: basic layout + forensic stats ----------------------------------

def _compute_text_stats(lines: List[str]) -> Dict[str, Any]:
    num_lines = len(lines)
    num_chars = sum(len(l) for l in lines)
    num_numeric_lines = 0
    all_text = "\n".join(lines)

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        digit_count = sum(c.isdigit() for c in stripped)
        if digit_count >= len(stripped) * 0.5:
            num_numeric_lines += 1

    numeric_ratio = num_numeric_lines / max(1, num_lines)
    unique_chars = set(all_text)
    uppercase_chars = sum(1 for c in all_text if c.isupper())
    alpha_chars = sum(1 for c in all_text if c.isalpha())

    uppercase_ratio = uppercase_chars / max(1, alpha_chars)

    return {
        "num_lines": num_lines,
        "num_chars": num_chars,
        "num_numeric_lines": num_numeric_lines,
        "numeric_line_ratio": numeric_ratio,
        "unique_char_count": len(unique_chars),
        "uppercase_ratio": uppercase_ratio,
    }


# --- Main feature builder ----------------------------------------------------

def build_features(raw: ReceiptRaw) -> ReceiptFeatures:
    """
    Build structured features from a ReceiptRaw.
    This is the core bridge between low-level extraction and the rule engine.
    """

    full_text, page_texts = _get_all_text_pages(raw)
    lines = full_text.split("\n") if full_text else []

    # --- File & metadata features -------------------------------------------
    meta = raw.pdf_metadata or {}
    producer = (meta.get("producer") or meta.get("creator") or "") or ""
    producer_lower = str(producer).lower()

    suspicious_producer = any(p in producer_lower for p in SUSPICIOUS_PRODUCERS)

    file_features: Dict[str, Any] = {
        "file_size_bytes": raw.file_size_bytes,
        "num_pages": raw.num_pages,
        "source_type": meta.get("source_type"),  # "pdf" or "image"
        "producer": producer,
        "creator": meta.get("creator"),
        "suspicious_producer": suspicious_producer,
        "has_creation_date": bool(meta.get("creation_date")),
        "creation_date": meta.get("creation_date"),  # Actual date value
        "has_mod_date": bool(meta.get("mod_date")),
        "mod_date": meta.get("mod_date"),  # Actual date value
        "exif_present": meta.get("exif_present"),  # for images
        "exif_keys_count": meta.get("exif_keys_count"),
    }

    # --- Text features -------------------------------------------------------
    # Total & line items
    all_amounts = _extract_candidate_amounts(lines)
    total_line, total_amount = _find_total_line(lines)
    line_item_amounts = _extract_line_item_amounts(lines)

    # Compute simple mismatch feature
    items_sum = sum(line_item_amounts) if line_item_amounts else 0.0
    has_line_items = bool(line_item_amounts)
    total_mismatch = (
        bool(total_amount is not None and has_line_items and abs(items_sum - total_amount) > 0.5)
    )

    # Date presence and extraction
    has_date = _has_any_date(full_text)
    receipt_date = _extract_receipt_date(full_text)

    # Merchant candidate
    merchant_candidate = _guess_merchant_line(lines)

    text_stats = _compute_text_stats(lines)

    text_features: Dict[str, Any] = {
        "has_any_amount": bool(all_amounts),
        "num_amount_candidates": len(all_amounts),
        "total_line_present": total_line is not None,
        "total_amount": total_amount,
        "has_line_items": has_line_items,
        "line_items_sum": items_sum if has_line_items else None,
        "total_mismatch": total_mismatch,
        "has_date": has_date,
        "receipt_date": receipt_date,  # Actual extracted date
        "merchant_candidate": merchant_candidate,
    }
    text_features.update(text_stats)

    # --- Layout features (basic for now) ------------------------------------
    layout_features: Dict[str, Any] = {
        # For v1, layout is essentially captured by text_stats.
        # Later we can add positional / block-based metrics.
        "num_lines": text_stats["num_lines"],
        "numeric_line_ratio": text_stats["numeric_line_ratio"],
        "lines": lines,  # Store lines for visual quality checks
    }

    # --- Forensic-ish features ----------------------------------------------
    # Simple heuristics - more advanced stuff can be added later
    forensic_features: Dict[str, Any] = {
        "uppercase_ratio": text_stats["uppercase_ratio"],
        "unique_char_count": text_stats["unique_char_count"],
        # Room for future: compression artifacts, noise levels, etc.
    }

    return ReceiptFeatures(
        file_features=file_features,
        text_features=text_features,
        layout_features=layout_features,
        forensic_features=forensic_features,
    )