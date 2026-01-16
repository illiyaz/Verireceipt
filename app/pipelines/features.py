# app/pipelines/features.py

import re
import logging
from dataclasses import asdict
from typing import Dict, Any, List, Tuple, Optional
from app.pipelines.language_id import identify_language
from app.schemas.receipt import ReceiptRaw, ReceiptFeatures, SignalV1
from app.pipelines.geo_detection import detect_geo_and_profile
from app.pipelines.lang import LangPackLoader, ScriptDetector, LangPackRouter, TextNormalizer
from app.pipelines.document_intent import resolve_document_intent, IntentSource
from app.pipelines.domain_validation import infer_domain_from_domainpacks, validate_domain_pack
from app.address import (
    validate_address,
    assess_merchant_address_consistency,
    detect_multi_address_profile,
)
from app.signals import (
    signal_addr_structure,
    signal_addr_merchant_consistency,
    signal_addr_multi_address,
    signal_amount_total_mismatch,
    signal_amount_missing,
    signal_amount_semantic_override,
    signal_pdf_producer_suspicious,
    signal_template_quality_low,
    signal_merchant_extraction_weak,
    signal_merchant_confidence_low,
)
from app.telemetry.address_metrics import record_address_features
logger = logging.getLogger(__name__)


# NOTE:
# doc_subtype_guess is a hypothesis, not a fact.
# Rules should gate on confidence and source.

# --- Language Pack System Initialization -----------------------------------

# Initialize language pack system (lazy loading to avoid import issues)
_lang_loader = None
_script_detector = None
_lang_router = None
_text_normalizer = None

def _get_lang_system():
    """Get initialized language system components."""
    global _lang_loader, _script_detector, _lang_router, _text_normalizer
    
    if _lang_loader is None:
        _lang_loader = LangPackLoader(strict=True)
        _lang_loader.load_all()
        _script_detector = ScriptDetector()
        _lang_router = LangPackRouter(_lang_loader, _script_detector)
        _text_normalizer = TextNormalizer()
    
    return {
        'loader': _lang_loader,
        'detector': _script_detector,
        'router': _lang_router,
        'normalizer': _text_normalizer
    }


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


def _detect_spacing_anomalies(raw_text: str) -> Dict[str, Any]:
    """
    Detect abnormal spacing patterns in OCR text that may indicate manipulation.
    
    Suspicious patterns:
    - Excessive spaces between words (e.g., "TOTAL    300,000")
    - Inconsistent spacing (some words close, others far apart)
    - Multiple consecutive spaces that survived OCR
    - Abnormal line breaks in the middle of words
    
    Returns dict with anomaly flags and metrics.
    """
    anomalies = {
        "has_excessive_spacing": False,
        "has_inconsistent_spacing": False,
        "excessive_space_count": 0,
        "max_consecutive_spaces": 0,
        "avg_word_spacing": 0.0,
        "spacing_variance": 0.0,
    }
    
    if not raw_text or len(raw_text) < 10:
        return anomalies
    
    lines = raw_text.split('\n')
    
    # Track spacing between words across all lines
    word_spacings = []
    excessive_space_lines = []
    
    for line_idx, line in enumerate(lines):
        if len(line.strip()) < 3:
            continue
        
        # Count consecutive spaces in this line
        consecutive_spaces = re.findall(r' {2,}', line)
        if consecutive_spaces:
            max_spaces = max(len(s) for s in consecutive_spaces)
            anomalies["max_consecutive_spaces"] = max(
                anomalies["max_consecutive_spaces"], 
                max_spaces
            )
            
            # If we have 3+ consecutive spaces, it's suspicious
            if max_spaces >= 3:
                anomalies["excessive_space_count"] += len([s for s in consecutive_spaces if len(s) >= 3])
                excessive_space_lines.append(line_idx)
        
        # Analyze word spacing patterns
        words = line.split()
        if len(words) >= 2:
            # Measure spacing by looking at original line
            for i in range(len(words) - 1):
                # Find position of word in original line
                word_pos = line.find(words[i])
                next_word_pos = line.find(words[i + 1], word_pos + len(words[i]))
                if next_word_pos > 0:
                    spacing = next_word_pos - (word_pos + len(words[i]))
                    word_spacings.append(spacing)
    
    # Calculate spacing statistics
    if word_spacings:
        avg_spacing = sum(word_spacings) / len(word_spacings)
        anomalies["avg_word_spacing"] = round(avg_spacing, 2)
        
        # Calculate variance
        variance = sum((s - avg_spacing) ** 2 for s in word_spacings) / len(word_spacings)
        anomalies["spacing_variance"] = round(variance, 2)
        
        # Flag excessive spacing if we have 3+ spaces between words
        if anomalies["max_consecutive_spaces"] >= 3:
            anomalies["has_excessive_spacing"] = True
        
        # Flag inconsistent spacing if variance is high
        # High variance means some words are very close, others very far
        if variance > 10 and avg_spacing > 2:
            anomalies["has_inconsistent_spacing"] = True
    
    return anomalies


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


def _find_subtotal(lines: List[str]) -> Optional[float]:
    """
    Try to find the subtotal (before tax) on the receipt.
    """
    subtotal_keywords = ["subtotal", "sub total", "sub-total", "amount before tax"]
    
    for line in lines:
        lower = line.lower()
        if any(k in lower for k in subtotal_keywords):
            match = _AMOUNT_REGEX.search(line)
            if match:
                return _parse_amount(match.group(1))
    return None


def _find_shipping_amount(lines: List[str]) -> Optional[float]:
    """
    Try to find shipping/freight/delivery amount.
    Simple keyword-based extraction - opportunistic only.
    """
    SHIPPING_KEYWORDS = ["shipping", "freight", "delivery", "handling", "postage"]
    
    for line in lines:
        lower = line.lower()
        if any(k in lower for k in SHIPPING_KEYWORDS):
            match = _AMOUNT_REGEX.search(line)
            if match:
                amount = _parse_amount(match.group(1))
                # Sanity check: shipping shouldn't be > $10,000
                if amount and 0 < amount < 10000:
                    return amount
    return None


def _find_discount_amount(lines: List[str]) -> Optional[float]:
    """
    Try to find discount/promo/coupon amount.
    Simple keyword-based extraction - opportunistic only.
    """
    DISCOUNT_KEYWORDS = ["discount", "promo", "coupon", "rebate", "savings", "off"]
    
    for line in lines:
        lower = line.lower()
        if any(k in lower for k in DISCOUNT_KEYWORDS):
            match = _AMOUNT_REGEX.search(line)
            if match:
                amount = _parse_amount(match.group(1))
                # Sanity check: discount shouldn't be > $50,000
                if amount and 0 < amount < 50000:
                    return amount
    return None


def _find_tax_amount(lines: List[str]) -> Tuple[Optional[float], Optional[float]]:
    """
    Try to find tax amount and tax rate on the receipt.
    Handles multiple tax systems:
    - India: GST, CGST, SGST, IGST, CESS
    - International: VAT, Sales Tax, Service Tax
    
    Returns (total_tax_amount, tax_rate_percent)
    """
    # Indian tax components
    indian_tax_keywords = [
        "gst", "cgst", "sgst", "igst", "cess",  # Indian GST system
        "central gst", "state gst", "integrated gst"
    ]
    
    # International tax keywords
    international_tax_keywords = [
        "tax", "vat", "sales tax", "service tax", "excise"
    ]
    
    all_tax_keywords = indian_tax_keywords + international_tax_keywords
    
    # Collect all tax amounts (for Indian receipts with multiple components)
    tax_amounts = []
    tax_rate = None
    
    for line in lines:
        lower = line.lower()
        
        # Check if line contains any tax keyword
        if any(k in lower for k in all_tax_keywords):
            # Try to extract tax amount - look for amount after colon or at end of line
            # This handles formats like "CGST @ 9%: 90.00" or "Tax: 90.00"
            if ':' in line:
                # Get the part after the colon
                after_colon = line.split(':')[-1]
                match = _AMOUNT_REGEX.search(after_colon)
            else:
                # No colon, search the whole line
                match = _AMOUNT_REGEX.search(line)
            
            if match:
                amount = _parse_amount(match.group(1))
                if amount:
                    tax_amounts.append(amount)
            
            # Try to extract tax rate (e.g., "18%", "10%", "2.5%")
            rate_match = re.search(r'(\d+(?:\.\d+)?)\s*%', line)
            if rate_match and not tax_rate:  # Take first rate found
                tax_rate = float(rate_match.group(1))
    
    # Sum all tax components (important for Indian receipts with CGST+SGST)
    total_tax = sum(tax_amounts) if tax_amounts else None
    
    return total_tax, tax_rate


def _detect_tax_breakdown(lines: List[str]) -> Dict[str, Any]:
    """
    Detect and extract individual tax components (especially for Indian receipts).
    Returns a dictionary with tax breakdown information.
    """
    tax_breakdown = {
        "has_cgst": False,
        "has_sgst": False,
        "has_igst": False,
        "has_cess": False,
        "cgst_amount": None,
        "sgst_amount": None,
        "igst_amount": None,
        "cess_amount": None,
        "is_indian_receipt": False,
    }
    
    for line in lines:
        lower = line.lower()
        
        # Check for CGST (Central GST)
        if "cgst" in lower or "central gst" in lower:
            tax_breakdown["has_cgst"] = True
            tax_breakdown["is_indian_receipt"] = True
            # Look for amount after colon
            if ':' in line:
                after_colon = line.split(':')[-1]
                match = _AMOUNT_REGEX.search(after_colon)
            else:
                match = _AMOUNT_REGEX.search(line)
            if match:
                tax_breakdown["cgst_amount"] = _parse_amount(match.group(1))
        
        # Check for SGST (State GST)
        if "sgst" in lower or "state gst" in lower:
            tax_breakdown["has_sgst"] = True
            tax_breakdown["is_indian_receipt"] = True
            # Look for amount after colon
            if ':' in line:
                after_colon = line.split(':')[-1]
                match = _AMOUNT_REGEX.search(after_colon)
            else:
                match = _AMOUNT_REGEX.search(line)
            if match:
                tax_breakdown["sgst_amount"] = _parse_amount(match.group(1))
        
        # Check for IGST (Integrated GST - interstate)
        if "igst" in lower or "integrated gst" in lower:
            tax_breakdown["has_igst"] = True
            tax_breakdown["is_indian_receipt"] = True
            # Look for amount after colon
            if ':' in line:
                after_colon = line.split(':')[-1]
                match = _AMOUNT_REGEX.search(after_colon)
            else:
                match = _AMOUNT_REGEX.search(line)
            if match:
                tax_breakdown["igst_amount"] = _parse_amount(match.group(1))
        
        # Check for CESS
        if "cess" in lower:
            tax_breakdown["has_cess"] = True
            tax_breakdown["is_indian_receipt"] = True
            # Look for amount after colon
            if ':' in line:
                after_colon = line.split(':')[-1]
                match = _AMOUNT_REGEX.search(after_colon)
            else:
                match = _AMOUNT_REGEX.search(line)
            if match:
                tax_breakdown["cess_amount"] = _parse_amount(match.group(1))
    
    return tax_breakdown


def _extract_receipt_number(lines: List[str]) -> Optional[str]:
    """
    Try to extract receipt/invoice number from the receipt.
    """
    receipt_keywords = [
        "receipt", "invoice", "bill", "order", "transaction",
        "ref", "reference", "#", "no", "number"
    ]
    
    for line in lines:
        lower = line.lower()
        # Check if line contains receipt number keywords
        if any(k in lower for k in receipt_keywords):
            # Try to extract alphanumeric receipt number
            # Patterns: R-1234, INV-001, #12345, 0001, etc.
            match = re.search(r'[:#\s]([A-Z0-9\-]{3,20})\b', line, re.I)
            if match:
                receipt_num = match.group(1).strip()
                # Filter out common false positives
                if receipt_num.lower() not in ['number', 'no', 'ref']:
                    return receipt_num
    
    return None


def _extract_line_item_amounts(lines: List[str]) -> tuple[List[float], float]:
    """
    Extract line item amounts with confidence tracking.
    
    Returns:
        (amounts, confidence) where confidence is 0.0-1.0
        
    Strategy:
    - Only count lines that look like item descriptions (text + amount)
    - Skip lines that are likely metadata (short, all caps, labels)
    - Skip lines with suspicious patterns (addresses, IDs, phone numbers)
    - Return low confidence if extraction is ambiguous
    """
    line_item_amounts: List[float] = []
    suspicious_patterns = [
        r'\b\d{5,}\b',  # Long numbers (IDs, phone, ZIP)
        r'\b[A-Z]{2}\s+\d{5}',  # State + ZIP
        r'^[A-Z\s]{3,}$',  # All caps short lines (labels)
        r'(?i)\b(total|subtotal|tax|discount|balance|amount|due|paid)\b',  # Structural keywords
        r'(?i)\b(invoice|receipt|bill|order)\s*#?\s*\d+',  # Document IDs
        r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',  # Dates
        r'\b\d{1,2}:\d{2}',  # Times
        r'(?i)\b(po number|purchase order)\b',  # Purchase order
        r'(?i)\b(quote|quotation)\b',  # Quote
        r'(?i)\b(proforma|commercial invoice)\b',  # Proforma invoice
    ]
    
    for line in lines:
        stripped = line.strip()
        
        # Skip empty or very short lines
        if len(stripped) < 5:
            continue
        
        # Skip lines that match suspicious patterns
        if any(re.search(pat, stripped) for pat in suspicious_patterns):
            continue
        
        # Must have some descriptive text (not just numbers/symbols)
        text_chars = sum(1 for c in stripped if c.isalpha())
        if text_chars < 3:
            continue
        
        # Try to match amount near the end of the line
        # Amount should be preceded by at least some text
        match = re.search(r'^(.{5,})\s+([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)\s*$', stripped)
        if match:
            description = match.group(1).strip()
            amount_str = match.group(2)
            
            # Verify description looks like an item (not a label)
            if len(description) >= 3 and not description.isupper():
                amt = _parse_amount(amount_str)
                if amt is not None and amt > 0:
                    line_item_amounts.append(amt)
    
    # Compute confidence based on extraction quality
    if not line_item_amounts:
        confidence = 0.0
    elif len(line_item_amounts) == 1:
        confidence = 0.3  # Single item - low confidence
    elif len(line_item_amounts) <= 3:
        confidence = 0.6  # Few items - medium confidence
    else:
        confidence = 0.8  # Multiple items - high confidence
    
    return line_item_amounts, confidence


# --- Helper: Date extraction (simple) ---------------------------------------

_DATE_REGEXES = [
    # 12/11/2025, 12-11-2025
    re.compile(r"\b([0-3]?\d)[/-]([0-1]?\d)[/-]((?:20)?\d{2})\b"),
    # 2025-11-12
    re.compile(r"\b(20\d{2})[-/]([0-1]?\d)[-/]([0-3]?\d)\b"),
    # MM/DD/YY HH:MM AM/PM (with optional spaces for OCR artifacts)
    re.compile(r'\b\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}\s+\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)\b'),
    # MM/DD/YY HH:MM (24-hour)
    re.compile(r'\b\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}\s+\d{1,2}:\d{2}\b'),
    # MM/DD/YYYY or DD-MM-YY (basic)
    re.compile(r'\b\d{1,2}\s*[/-]\s*\d{1,2}\s*[/-]\s*\d{2,4}\b'),
    # YYYY-MM-DD (ISO format)
    re.compile(r'\b\d{4}\s*[/-]\s*\d{1,2}\s*[/-]\s*\d{1,2}\b'),
    # DD Month YYYY (e.g., 15 January 2024)
    re.compile(r'\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4}\b', re.IGNORECASE),
    # Month DD, YYYY (e.g., January 15, 2024)
    re.compile(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}\b', re.IGNORECASE),
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


def _extract_currency_symbols(text: str) -> List[str]:
    """
    Extract all currency symbols found in the text.
    Returns list of unique currency symbols.
    """
    currency_symbols = []
    currency_patterns = [
        (r'₹', 'INR'),  # Indian Rupee
        (r'\$', 'USD'),  # US Dollar
        (r'€', 'EUR'),  # Euro
        (r'£', 'GBP'),  # British Pound
        (r'¥', 'JPY'),  # Japanese Yen
        (r'Rs\.?', 'INR'),  # Rupees (text)
        (r'USD', 'USD'),
        (r'EUR', 'EUR'),
        (r'GBP', 'GBP'),
    ]
    
    for pattern, symbol in currency_patterns:
        if re.search(pattern, text):
            if symbol not in currency_symbols:
                currency_symbols.append(symbol)
    
    return currency_symbols


def _extract_receipt_time(text: str) -> Optional[str]:
    """
    Extract time from receipt text.
    Returns time string in HH:MM format or None.
    """
    # Time patterns: HH:MM AM/PM or HH:MM (24-hour)
    time_patterns = [
        r'\b(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)\b',  # 12-hour with AM/PM
        r'\b(\d{1,2}):(\d{2})\b',  # 24-hour or ambiguous
    ]
    
    for pattern in time_patterns:
        match = re.search(pattern, text)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            
            # Handle AM/PM conversion if present
            if len(match.groups()) >= 3 and match.group(3):
                period = match.group(3).upper()
                if period == 'PM' and hour != 12:
                    hour += 12
                elif period == 'AM' and hour == 12:
                    hour = 0
            
            return f"{hour:02d}:{minute:02d}"
    
    return None


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


def _extract_all_dates(text: str) -> List[str]:
    """
    Extract ALL dates found in the receipt text.
    Returns list of date strings for conflict detection.
    """
    from datetime import datetime
    
    dates = []
    for rx in _DATE_REGEXES:
        for match in rx.finditer(text):
            date_str = match.group(0).strip()
            # Try to parse and normalize
            try:
                formats = [
                    "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%d/%m/%y",
                    "%Y-%m-%d", "%d-%m-%Y",
                    "%m/%d/%Y %I:%M %p", "%m/%d/%y %I:%M %p",  # With time
                    "%d %b %Y", "%d %B %Y",
                    "%b %d, %Y", "%b %d %Y",
                    "%B %d, %Y", "%B %d %Y",
                ]
                for fmt in formats:
                    try:
                        parsed = datetime.strptime(date_str.split()[0] if ' ' in date_str else date_str, fmt)
                        normalized = parsed.strftime("%Y-%m-%d")
                        if normalized not in dates:
                            dates.append(normalized)
                        break
                    except:
                        continue
            except:
                pass
    
    return dates


# --- Helper: Merchant candidate line ----------------------------------------

def _extract_merchant_address(text: str) -> Optional[str]:
    """
    Extract merchant address from receipt text.
    Looks for multi-line address patterns.
    """
    lines = text.split('\n')
    
    # Look for address indicators
    address_keywords = ['address', 'addr', 'location', 'store', 'branch']
    
    for i, line in enumerate(lines):
        line_lower = line.lower()
        
        # Check if line contains address keyword
        if any(kw in line_lower for kw in address_keywords):
            # Extract next 2-3 lines as address
            address_lines = []
            for j in range(i, min(i+4, len(lines))):
                addr_line = lines[j].strip()
                if addr_line and len(addr_line) > 5:
                    address_lines.append(addr_line)
            
            if address_lines:
                return ' '.join(address_lines)
    
    # Fallback: Look for PIN code and extract surrounding lines
    pin_pattern = r'\b\d{6}\b'
    for i, line in enumerate(lines):
        if re.search(pin_pattern, line):
            # Get this line and previous 2 lines
            start = max(0, i-2)
            address_lines = [lines[j].strip() for j in range(start, i+1) if lines[j].strip()]
            if address_lines:
                return ' '.join(address_lines)
    
    return None


def _extract_merchant_phone(text: str) -> Optional[str]:
    """
    Extract phone number from receipt text.
    """
    # Phone patterns
    patterns = [
        r'\+91[-\s]?\d{5}[-\s]?\d{5}',  # +91-XXXXX-XXXXX
        r'\b\d{10}\b',                    # 10 digits
        r'\b0\d{2,3}[-\s]?\d{7,8}\b',    # Landline with STD
        r'(?:phone|tel|mobile|contact)[\s:]+([+\d\s\-()]+)',  # After keywords
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            phone = match.group(1) if match.lastindex else match.group(0)
            # Clean up
            phone = re.sub(r'[^\d+]', '', phone)
            if len(phone) >= 10:
                return phone
    
    return None


def _extract_city_and_pin(text: str) -> tuple:
    """
    Extract city name and PIN code from text.
    Returns (city, pin_code) tuple.
    """
    city = None
    pin_code = None
    
    # Extract PIN code
    pin_match = re.search(r'\b(\d{6})\b', text)
    if pin_match:
        pin_code = pin_match.group(1)
    
    # Extract city - look for common Indian cities
    cities = [
        'hyderabad', 'bangalore', 'bengaluru', 'mumbai', 'delhi', 'new delhi',
        'chennai', 'kolkata', 'pune', 'ahmedabad', 'jaipur', 'surat',
        'lucknow', 'kanpur', 'nagpur', 'indore', 'thane', 'bhopal',
        'visakhapatnam', 'patna', 'vadodara', 'ghaziabad', 'ludhiana',
        'agra', 'nashik', 'faridabad', 'meerut', 'rajkot', 'varanasi'
    ]
    
    text_lower = text.lower()
    for city_name in cities:
        if city_name in text_lower:
            city = city_name.title()
            break
    
    return (city, pin_code)


def _compute_merchant_confidence(merchant_name: str, lines: List[str], full_text: str) -> float:
    """
    Compute confidence score for extracted merchant name.
    
    Heuristic scoring:
    - Strong (0.8-1.0): In header/top 10 lines + has business suffix + tax context nearby
    - Medium (0.6-0.79): Appears once in top 10 lines OR has business suffix
    - Low (0.0-0.59): Scattered, footer-only, or weak signals
    
    Returns:
        float: Confidence score 0.0-1.0
    """
    if not merchant_name or not merchant_name.strip():
        return 0.0
    
    merchant_norm = merchant_name.strip().lower()
    score = 0.4  # Base score (conservative)
    
    # 1. Position scoring (top 10 lines = header)
    found_in_header = False
    line_positions = []
    for i, line in enumerate(lines[:10]):
        if merchant_norm in (line or "").lower():
            found_in_header = True
            line_positions.append(i)
            break
    
    if found_in_header:
        score += 0.15
        # Bonus for very top (lines 0-2)
        if line_positions and line_positions[0] <= 2:
            score += 0.1
    
    # 2. Business suffix detection
    business_suffixes = [
        "inc", "llc", "ltd", "corp", "corporation", "company", "co",
        "pvt", "private", "limited", "gmbh", "sa", "srl", "pty",
        "llp", "logistics", "services", "solutions", "industries"
    ]
    has_business_suffix = any(suffix in merchant_norm for suffix in business_suffixes)
    if has_business_suffix:
        score += 0.2
    
    # 3. Tax context nearby (GST/VAT/TIN within 5 lines)
    tax_indicators = ["gst", "gstin", "vat", "tin", "tax id", "tax no", "pan"]
    has_tax_context = False
    if line_positions:
        start_idx = max(0, line_positions[0] - 2)
        end_idx = min(len(lines), line_positions[0] + 5)
        nearby_text = " ".join(lines[start_idx:end_idx]).lower()
        has_tax_context = any(ind in nearby_text for ind in tax_indicators)
    
    if has_tax_context:
        score += 0.2
    
    # 4. Penalty for scattered appearances (appears in multiple distant locations)
    all_positions = []
    for i, line in enumerate(lines):
        if merchant_norm in (line or "").lower():
            all_positions.append(i)
    
    if len(all_positions) > 1:
        # Check if scattered (gap > 10 lines)
        max_gap = max(all_positions) - min(all_positions)
        if max_gap > 10:
            score -= 0.3
    
    # 5. Penalty for footer-only (appears only after line 30)
    if all_positions and min(all_positions) > 30:
        score -= 0.4
    
    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, score))


def _looks_like_company_name(line: str, packs=None) -> bool:
    """Check if a line looks like a plausible company name."""
    if not line or len(line.strip()) < 3:
        return False
    
    s = line.strip()
    
    # Too short or too long
    if len(s) < 3 or len(s) > 100:
        return False
    
    # Too many digits (likely an invoice number or date)
    digit_ratio = sum(c.isdigit() for c in s) / max(len(s), 1)
    if digit_ratio > 0.5:
        return False
    
    # Has at least some letters
    if not any(c.isalpha() for c in s):
        return False
    
    # Use language pack company suffixes if available
    if packs:
        lang_system = _get_lang_system()
        normalizer = lang_system['normalizer']
        
        # Combine company suffixes from all packs
        company_indicators = set()
        for pack in packs:
            script = pack.scripts[0]
            # Add suffixes
            company_indicators.update([
                normalizer.normalize_text(suffix, script).lower()
                for suffix in pack.company.suffixes
            ])
            # Add prefixes
            company_indicators.update([
                normalizer.normalize_text(prefix, script).lower()
                for prefix in pack.company.prefixes
            ])
        
        lower = s.lower()
        if any(ind in lower for ind in company_indicators):
            return True
    else:
        # Fallback to hardcoded indicators
        company_indicators = [
            "inc", "llc", "ltd", "corp", "corporation", "company", "co",
            "pvt", "private", "limited", "gmbh", "sa", "srl", "pty"
        ]
        lower = s.lower()
        if any(ind in lower for ind in company_indicators):
            return True
    
    # Looks like a proper name (mixed case or all caps, reasonable length)
    if len(s) >= 5 and (s[0].isupper() or s.isupper()):
        return True
    
    return False


def _guess_merchant_line(lines: List[str]) -> Optional[str]:
    """
    Heuristic:
    - First non-empty line
    - That is not mostly numbers
    - That is not just 'tax invoice' or purely generic text
    - Hardened to reject document titles like "COMMERCIAL INVOICE"
    - Never treats structural labels as merchants
    - Uses language packs for multilingual support
    - Multi-line merge: If top N lines are uppercase and near each other, concatenate
    """
    # Get language pack system
    lang_system = _get_lang_system()
    router = lang_system['router']
    normalizer = lang_system['normalizer']
    
    # Join lines for language detection
    text_for_routing = "\n".join(lines[:10]) if lines else ""
    
    # Route to appropriate language pack(s)
    routing_result = router.route_document(text_for_routing, allow_multi_pack=True)
    
    # Get primary pack and fallbacks
    packs = routing_result.all_packs
    
    # Combine keywords from all available packs
    title_blacklist = set()
    structural_labels = set()
    next_line_preference_labels = set()
    
    for pack in packs:
        # Document titles (blacklist)
        title_blacklist.update([
            normalizer.normalize_text(title, pack.scripts[0]).lower()
            for title in pack.keywords.doc_titles
        ])
        
        # Structural labels
        structural_labels.update([
            normalizer.normalize_text(label, pack.scripts[0]).lower()
            for label in pack.labels.structural
        ])
        
        # Next-line preference labels
        next_line_preference_labels.update([
            normalizer.normalize_text(label, pack.scripts[0]).lower()
            for label in pack.labels.next_line_preference
        ])
    
    # Multi-line merge: Check if top lines are uppercase and should be concatenated
    # Common pattern: "JOINT AL MANDI" split across 2-3 lines
    uppercase_lines = []
    for i, line in enumerate(lines[:5]):  # Check first 5 lines
        s = (line or "").strip()
        if not s:
            continue
        
        # Check if line is mostly uppercase (>70% uppercase letters)
        alpha_chars = [c for c in s if c.isalpha()]
        if alpha_chars:
            uppercase_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
            if uppercase_ratio > 0.7 and len(s) > 2:
                # Check it's not a document title or structural label
                norm = normalizer.normalize_text(s, routing_result.script).lower().strip()
                norm = re.sub(r"[^\w\s/]", "", norm).strip()
                
                if norm not in title_blacklist and not any(k in norm for k in structural_labels):
                    uppercase_lines.append((i, s))
        
        # Stop if we hit a non-uppercase line (merchant name ended)
        if len(uppercase_lines) > 0 and uppercase_ratio <= 0.7:
            break
    
    # If we found 2-3 consecutive uppercase lines at the top, merge them
    if len(uppercase_lines) >= 2:
        indices = [idx for idx, _ in uppercase_lines]
        # Check they're consecutive or nearly consecutive (allow 1 empty line gap)
        if max(indices) - min(indices) <= len(uppercase_lines):
            merged = " ".join([text for _, text in uppercase_lines])
            # Verify merged result looks like a company name
            if _looks_like_company_name(merged, packs):
                return merged

    for i, line in enumerate(lines[:8]):
        s = (line or "").strip()
        if not s:
            continue

        # Normalize using language pack normalizer
        norm = normalizer.normalize_text(s, routing_result.script).lower().strip()
        
        # Additional normalization for matching (remove punctuation)
        norm = re.sub(r"[^\w\s/]", "", norm)  # Remove . : , - etc, keep / for "ship to/consignee"
        norm = norm.strip()

        # 0️⃣ Treat common structural labels (even when OCR squashes punctuation like "EXPORTER/SHIPPER" -> "EXPORTERISHIPPER")
        # If we see a label, prefer the next line as the company name.
        if any(tok in norm for tok in next_line_preference_labels):
            if i + 1 < len(lines):
                next_line = (lines[i + 1] or "").strip()
                if _looks_like_company_name(next_line, packs):
                    return next_line
            # If label present but next line isn't a company, do not treat the label as merchant.
            continue

        # 1️⃣ Hard reject document titles (using language pack blacklist)
        if norm in title_blacklist:
            continue

        # 2️⃣ Reject mostly-numeric or label-like lines
        digit_ratio = sum(c.isdigit() for c in norm) / max(len(norm), 1)
        if digit_ratio > 0.4:
            continue

        # Check for label-like patterns using language pack structural labels
        if any(k in norm for k in structural_labels):
            continue

        # 3️⃣ Reject structural labels
        if norm in structural_labels:
            # Special case: if this is a label that should trigger next-line preference
            if norm in next_line_preference_labels and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if _looks_like_company_name(next_line, packs):
                    return next_line
            continue

        # 4️⃣ Looks plausible
        return s

    return None


# --- Helper: Document profile / type inference -----------------------------

def _detect_document_profile(full_text: str, lines: List[str]) -> Dict[str, Any]:
    """Infer a coarse document family/subtype from text.

    This is intentionally heuristic (no LLM) and should be stable/offline.

    Supported taxonomy (doc_family_guess / doc_subtype_guess):
      - TRANSACTIONAL:
          POS_RESTAURANT, POS_RETAIL, ECOMMERCE, HOTEL_FOLIO, FUEL, PARKING, TRANSPORT, MISC,
          TAX_INVOICE, VAT_INVOICE, COMMERCIAL_INVOICE, SERVICE_INVOICE, SHIPPING_INVOICE,
          PROFORMA, CREDIT_NOTE, DEBIT_NOTE,
          UTILITY, TELECOM, SUBSCRIPTION, RENT, INSURANCE
      - LOGISTICS:
          SHIPPING_BILL, BILL_OF_LADING, AIR_WAYBILL, DELIVERY_NOTE
      - PAYMENT:
          PAYMENT_RECEIPT, BANK_SLIP, CARD_CHARGE_SLIP, REFUND_RECEIPT

    Returns:
      {
        "doc_family_guess": "TRANSACTIONAL"|"LOGISTICS"|"PAYMENT"|"UNKNOWN",
        "doc_subtype_guess": str,
        "doc_profile_confidence": float (0..1),
        "doc_profile_evidence": [str, ...]
      }
    """

    text = (full_text or "").lower()
    top = "\n".join((lines or [])[:30]).lower()
    
    # Normalize punctuation for better keyword matching
    text_norm = re.sub(r"[^\w\s/]", " ", text)  # Replace punctuation with space
    text_norm = re.sub(r"\s+", " ", text_norm).strip()
    top_norm = re.sub(r"[^\w\s/]", " ", top)
    top_norm = re.sub(r"\s+", " ", top_norm).strip()

    # Keyword buckets. Keep interpretable and stable.
    # We score *subtypes* first, then derive the family from the winning subtype.
    subtype_keywords: Dict[str, List[str]] = {
        # --- TRANSACTIONAL / RECEIPT --------------------------------------
        "POS_RESTAURANT": [
            "table", "server", "gratuity", "tip", "covers", "dine in", "dine-in",
            "restaurant", "cafe", "bar", "food", "beverage", "gst on food",
        ],
        "POS_RETAIL": [
            "pos", "terminal", "till", "cashier", "thank you", "change due",
            "qty", "sku", "barcode", "item", "discount", "store", "receipt",
        ],
        "ECOMMERCE": [
            "order id", "order #", "order number", "shipment", "delivered", "tracking",
            "invoice for your order", "sold by", "fulfilled", "marketplace", "platform fee",
        ],
        "HOTEL_FOLIO": [
            "folio", "room", "room no", "check-in", "check out", "check-out",
            "nightly rate", "stay", "guest", "front desk", "hotel", "resort",
        ],
        "FUEL": [
            "fuel", "petrol", "diesel", "litre", "liter", "pump", "nozzle",
            "price/l", "price per litre", "total litres", "odometer",
        ],
        "PARKING": [
            "parking", "park", "slot", "entry time", "exit time", "duration",
            "vehicle", "license plate", "parking fee",
        ],
        "TRANSPORT": [
            "taxi", "uber", "ola", "ride", "trip", "km", "fare", "driver",
            "boarding", "ticket", "bus", "train", "metro",
        ],
        "MISC": [
            "receipt", "cash memo", "cashmemo", "invoice cum receipt", "bill",
        ],

        # --- TRANSACTIONAL / INVOICE --------------------------------------
        "TAX_INVOICE": [
            "tax invoice", "gstin", "gst", "hsn", "sac", "place of supply",
            "cgst", "sgst", "igst",
        ],
        "VAT_INVOICE": [
            "vat invoice", "vat no", "vat number", "vat registration", "vat%", "vat amount",
        ],
        "COMMERCIAL_INVOICE": [
            "commercial invoice", "incoterms", "hs code", "hsn", "hsn code", "h.s. code",
            "country of origin", "consignee", "shipper", "exporter", "export", "import",
            "country of export", "country of ultimate destination",
            "date of export", "invoice value", "fob", "cif",
            "inv no", "inv. no", "invoice no", "invoice number",
            "port of loading", "port of discharge",
        ],
        "SERVICE_INVOICE": [
            "service invoice", "service period", "hours", "rate", "professional fee",
            "consulting", "maintenance", "support fee",
        ],
        "SHIPPING_INVOICE": [
            "shipping invoice", "freight", "freight charges", "carrier", "awb",
            "tracking", "shipment", "port", "vessel",
        ],
        "PROFORMA": [
            "proforma", "pro forma", "proforma invoice", "quotation", "quote",
        ],
        "CREDIT_NOTE": [
            "credit note", "credit memo", "cn no", "credit amount", "credited",
        ],
        "DEBIT_NOTE": [
            "debit note", "debit memo", "dn no", "debit amount", "debited",
        ],

        # --- TRANSACTIONAL / BILL -----------------------------------------
        "UTILITY": [
            "electricity", "power bill", "electricity bill",
            "water bill", "gas bill",
            "meter", "kwh", "units consumed", "billing period",
            "consumer no", "service no", "account no",
        ],
        "TELECOM": [
            "telecom", "mobile bill", "postpaid", "prepaid", "data usage", "minutes used",
            "roaming", "imei",
        ],
        "SUBSCRIPTION": [
            "subscription", "plan", "renewal", "monthly", "annual", "billing cycle",
            "auto-renew", "recurring",
        ],
        "RENT": [
            "rent", "lease", "tenant", "landlord", "rental period", "security deposit",
        ],
        "INSURANCE": [
            "insurance", "policy", "premium", "coverage", "insured", "claim",
            "policy number",
        ],

        # --- LOGISTICS ------------------------------------------------------
        "SHIPPING_BILL": [
            "shipping bill", "sb no", "let export order", "leo", "customs",
            "exporter", "ad code", "country of export", "country of ultimate destination",
            "hsn", "hsn code", "export value", "port of loading", "port of discharge",
        ],
        "BILL_OF_LADING": [
            "bill of lading", "b/l", "bl no", "vessel", "port of loading",
            "port of discharge", "container", "seal", "shipper", "consignee",
        ],
        "AIR_WAYBILL": [
            "airway bill", "air waybill", "awb", "awb no", "awb#", "air cargo", "iata",
            "consignee", "shipper", "exporter", "country of export",
            "country of ultimate destination", "flight no", "airport of departure",
            "port of loading", "port of discharge",
        ],
        "DELIVERY_NOTE": [
            "delivery note", "delivery challan", "challan", "pod", "proof of delivery",
            "delivered to", "received by",
        ],

        # --- PAYMENT --------------------------------------------------------
        "PAYMENT_RECEIPT": [
            "payment receipt", "paid", "payment successful", "payment reference",
            "transaction id", "txn id", "utr", "rrn", "auth code",
        ],
        "BANK_SLIP": [
            "deposit slip", "bank slip", "pay-in slip", "cheque", "cheque no",
            "account no", "branch", "ifsc", "swift",
        ],
        "CARD_CHARGE_SLIP": [
            "charge slip", "card slip", "merchant copy", "customer copy",
            "terminal id", "tid", "mid", "approval code", "card number",
        ],
        "REFUND_RECEIPT": [
            "refund", "refunded", "refund receipt", "refund id", "refunded to",
            "return", "reversal",
        ],
    }

    # Base weights: strong, document-specific phrases should dominate.
    subtype_weight: Dict[str, float] = {
        # Transactional receipts
        "POS_RESTAURANT": 1.0,
        "POS_RETAIL": 0.9,
        "ECOMMERCE": 0.95,
        "HOTEL_FOLIO": 1.0,
        "FUEL": 1.0,
        "PARKING": 0.9,
        "TRANSPORT": 0.85,
        "MISC": 0.6,
        # Transactional invoices
        "TAX_INVOICE": 1.0,
        "VAT_INVOICE": 1.0,
        "COMMERCIAL_INVOICE": 1.0,
        "SERVICE_INVOICE": 0.9,
        "SHIPPING_INVOICE": 0.95,
        "PROFORMA": 0.9,
        "CREDIT_NOTE": 1.0,
        "DEBIT_NOTE": 1.0,
        # Transactional bills
        "UTILITY": 0.95,
        "TELECOM": 0.9,
        "SUBSCRIPTION": 0.85,
        "RENT": 0.85,
        "INSURANCE": 0.9,
        # Logistics
        "SHIPPING_BILL": 1.0,
        "BILL_OF_LADING": 1.0,
        "AIR_WAYBILL": 1.0,
        "DELIVERY_NOTE": 0.9,
        # Payment
        "PAYMENT_RECEIPT": 0.95,
        "BANK_SLIP": 0.95,
        "CARD_CHARGE_SLIP": 0.95,
        "REFUND_RECEIPT": 0.95,
    }

    def _hit(hay: str, kw: str) -> bool:
        return kw in hay

    subtype_scores: Dict[str, float] = {k: 0.0 for k in subtype_keywords}
    subtype_evidence: Dict[str, List[str]] = {k: [] for k in subtype_keywords}

    # Score using both whole text + top region (use normalized versions for matching)
    for subtype, kws in subtype_keywords.items():
        w = float(subtype_weight.get(subtype, 1.0))
        for kw in kws:
            # Check both original and normalized text for better punctuation handling
            if _hit(text, kw) or _hit(top, kw) or _hit(text_norm, kw) or _hit(top_norm, kw):
                subtype_scores[subtype] += w
                if kw not in subtype_evidence[subtype]:
                    subtype_evidence[subtype].append(kw)

    # If we see strong logistics/customs headers, boost logistics/international invoice subtypes.
    logistics_markers = [
        "exporter", "shipper", "consignee",
        "hs code", "hsn", "customs",
        "awb", "airway bill", "bill of lading",
        "shipping bill", "port of loading", "port of discharge",
        "country of export", "country of ultimate destination",
    ]
    logistics_hits = sum(1 for m in logistics_markers if (m in text_norm) or (m in top_norm))
    if logistics_hits >= 2:
        # Prefer logistics classification over generic transactional/bill-like matches.
        for st in ["SHIPPING_BILL", "BILL_OF_LADING", "AIR_WAYBILL", "COMMERCIAL_INVOICE", "SHIPPING_INVOICE"]:
            if st in subtype_scores:
                subtype_scores[st] += 1.5

    # Pick best subtype
    best_subtype = max(subtype_scores, key=lambda k: subtype_scores[k]) if subtype_scores else "UNKNOWN"
    best_score = subtype_scores.get(best_subtype, 0.0)

    if best_score <= 0.0:
        return {
            "doc_family_guess": "UNKNOWN",
            "doc_subtype_guess": "UNKNOWN",
            "doc_profile_confidence": 0.0,
            "doc_profile_evidence": [],
        }

    # Derive family from subtype
    transactional_receipts = {
        "POS_RESTAURANT", "POS_RETAIL", "ECOMMERCE", "HOTEL_FOLIO", "FUEL", "PARKING", "TRANSPORT", "MISC"
    }
    transactional_invoices = {
        "TAX_INVOICE", "VAT_INVOICE", "COMMERCIAL_INVOICE", "SERVICE_INVOICE", "SHIPPING_INVOICE",
        "PROFORMA", "CREDIT_NOTE", "DEBIT_NOTE"
    }
    transactional_bills = {"UTILITY", "TELECOM", "SUBSCRIPTION", "RENT", "INSURANCE"}
    logistics = {"SHIPPING_BILL", "BILL_OF_LADING", "AIR_WAYBILL", "DELIVERY_NOTE"}
    payment = {"PAYMENT_RECEIPT", "BANK_SLIP", "CARD_CHARGE_SLIP", "REFUND_RECEIPT"}

    if best_subtype in logistics:
        family = "LOGISTICS"
    elif best_subtype in payment:
        family = "PAYMENT"
    else:
        family = "TRANSACTIONAL"

    # Confidence: simple + bounded.
    #  - higher when more unique keywords matched for the winner
    #  - penalize ambiguity when runner-up is close
    uniq_hits = len(subtype_evidence.get(best_subtype, []))
    second_best = 0.0
    for st, sc in subtype_scores.items():
        if st != best_subtype:
            second_best = max(second_best, sc)

    raw_conf = min(1.0, 0.25 + 0.16 * uniq_hits)
    if second_best > 0.0:
        # Stronger penalty for ambiguity - when multiple document types detected
        ambiguity_ratio = second_best / max(0.01, best_score)
        penalty = min(0.65, 0.55 * ambiguity_ratio)
        raw_conf = max(0.0, raw_conf - penalty)

    # If we only matched very generic tokens (e.g., just "receipt"), cap confidence.
    if best_subtype == "MISC" and uniq_hits <= 2:
        raw_conf = min(raw_conf, 0.45)

    # Avoid classifying as UTILITY on weak/ambiguous evidence (common in customs/logistics PDFs that contain the word "bill").
    if best_subtype == "UTILITY" and uniq_hits <= 2:
        raw_conf = min(raw_conf, 0.35)

    # Logistics-like override: if 2+ strong keywords appear for logistics/customs documents,
    # set minimum confidence floor to improve classification and extraction routing.
    # NOTE: This does NOT automatically enable missing-field penalties - those are still
    # gated separately based on document expectations (receipt fields vs logistics fields).
    logistics_like = logistics | {"COMMERCIAL_INVOICE", "SHIPPING_INVOICE"}
    if uniq_hits >= 2 and best_subtype in logistics_like:
        raw_conf = max(raw_conf, 0.55)

    # Get top 3 subtype scores for debugging
    sorted_scores = sorted(subtype_scores.items(), key=lambda x: x[1], reverse=True)[:3]
    top_3_scores = {st: round(sc, 2) for st, sc in sorted_scores}
    
    # Check which logistics markers were found
    logistics_markers_found = [m for m in logistics_markers if (m in text_norm) or (m in top_norm)]

    result = {
        "doc_family_guess": family,
        "doc_subtype_guess": best_subtype,
        "doc_profile_confidence": round(float(raw_conf), 3),
        "doc_profile_evidence": sorted(subtype_evidence.get(best_subtype, [])),
        # Debug info (not returned but can be logged)
        "_debug": {
            "uniq_hits": uniq_hits,
            "top_3_scores": top_3_scores,
            "best_score": round(best_score, 2),
            "logistics_hits": logistics_hits,
            "logistics_markers_found": logistics_markers_found,
        }
    }
    
    return result


# --- Helper: basic layout + forensic stats ----------------------------------

def _compute_text_stats(lines: List[str], raw_text: str = None) -> Dict[str, Any]:
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
    
    # Add spacing anomaly detection
    spacing_anomalies = {}
    if raw_text:
        spacing_anomalies = _detect_spacing_anomalies(raw_text)

    result = {
        "num_lines": num_lines,
        "num_chars": num_chars,
        "num_numeric_lines": num_numeric_lines,
        "numeric_line_ratio": numeric_ratio,
        "unique_char_count": len(unique_chars),
        "uppercase_ratio": uppercase_ratio,
    }
    
    # Merge spacing anomalies into result
    result.update(spacing_anomalies)
    
    return result


# --- Main feature builder ----------------------------------------------------

def build_features(raw: ReceiptRaw) -> ReceiptFeatures:
    """
    Build structured features from a ReceiptRaw.
    This is the core bridge between low-level extraction and the rule engine.
    """

    full_text, page_texts = _get_all_text_pages(raw)
    lines = full_text.split("\n") if full_text else []
    
    # ============================================================================
    # ARCHITECTURE FLIP: Document Classification & Profile Selection
    # Use heuristic classification to select appropriate validation profile
    # ============================================================================
    
    # NEW: Geo-aware document classification (Steps 1-4)
    geo_profile = detect_geo_and_profile(full_text, lines)
    
    # Map heuristic classification to document profiles
    doc_subtype_guess_raw = geo_profile.get("doc_subtype_guess", "UNKNOWN")
    doc_class = doc_subtype_guess_raw  # Use heuristic as doc_class
    doc_class_confidence = geo_profile.get("doc_profile_confidence", 0.0)  # Use doc_profile_confidence, not doc_subtype_confidence
    doc_class_evidence = geo_profile.get("doc_subtype_evidence", [])
    llm_classification_attempted = False
    
    # Detect invoice patterns for better classification
    text_lower = full_text.lower()
    if any(keyword in text_lower for keyword in ["invoice number", "invoice no", "inv no", "bill to", "ship to", "terms:", "payment terms"]):
        if "tax invoice" in text_lower or "vat invoice" in text_lower:
            doc_class = "TAX_INVOICE"
            doc_class_confidence = 0.85
        else:
            doc_class = "COMMERCIAL_INVOICE"
            doc_class_confidence = 0.85
        logger.info(f"Detected invoice pattern, classified as {doc_class}")
    
    # Load document profile based on classification
    from app.pipelines.doc_profiles import get_profile_for_doc_class
    doc_profile_obj = get_profile_for_doc_class(doc_class)
    if doc_profile_obj is None:
        doc_profile_obj = get_profile_for_doc_class("UNKNOWN")
    logger.info(f"Selected profile: {doc_profile_obj.doc_class} (risk: {doc_profile_obj.fraud_surface}, model: {doc_profile_obj.risk_model})")

    # ============================================================================
    # BACKWARD COMPATIBILITY BRIDGE
    # Unify new doc_class system with old doc_profile fields
    # ============================================================================
    # Normalize confidence
    try:
        dcc = float(doc_class_confidence or 0.0)
    except Exception:
        dcc = 0.0
    
    # If we have confident classification (>= 0.75), override geo_profile fields
    # This ensures old gates (_missing_field_penalties_enabled, _expects_*) follow new classification
    if doc_profile_obj is not None and dcc >= 0.75:
        # Map doc_class to doc_family
        if doc_class in ["COMMERCIAL_INVOICE", "TAX_INVOICE"]:
            doc_family_guess = "INVOICE"
        elif doc_class.startswith("POS_"):
            doc_family_guess = "TRANSACTIONAL"
        elif doc_class in ["BANK_STATEMENT", "UTILITY_BILL"]:
            doc_family_guess = "STATEMENT"
        elif doc_class == "TRADE_DOCUMENT":
            doc_family_guess = "TRADE"
        else:
            doc_family_guess = "UNKNOWN"
        
        # Override geo_profile fields with new classification
        doc_subtype_guess_raw = doc_class
        doc_subtype_guess = doc_class
        doc_subtype_confidence = doc_class_confidence
        doc_subtype_source = "heuristic_invoice_detection"
        doc_subtype_evidence = doc_class_evidence
        requires_corroboration = False
        
        logger.info(f"BRIDGE: Overriding geo_profile with doc_class={doc_class} (confidence={doc_class_confidence:.2f})")
    else:
        # Use geo_profile heuristics as fallback
        doc_subtype_guess_raw = geo_profile.get("doc_subtype_guess")
        doc_subtype_guess = doc_subtype_guess_raw
        doc_subtype_confidence = geo_profile.get("doc_subtype_confidence")
        doc_subtype_source = geo_profile.get("doc_subtype_source")
        doc_subtype_evidence = geo_profile.get("doc_subtype_evidence")
        requires_corroboration = geo_profile.get("requires_corroboration")
        doc_family_guess = geo_profile.get("doc_family_guess")

    # --- Extract basic features needed for early decisions ---
    # Total & line items
    all_amounts = _extract_candidate_amounts(lines)
    total_line, total_amount = _find_total_line(lines)
    line_item_amounts, line_items_confidence = _extract_line_item_amounts(lines)

    # Compute simple mismatch feature
    items_sum = sum(line_item_amounts) if line_item_amounts else 0.0
    has_line_items = bool(line_item_amounts)
    
    # Compute initial mismatch ratio for semantic verification decision
    initial_mismatch_ratio = None
    if total_amount and items_sum and total_amount > 0:
        initial_mismatch_ratio = abs(total_amount - items_sum) / total_amount
    
    # Currency extraction
    currency_symbols = _extract_currency_symbols(full_text)
    has_currency = bool(currency_symbols)

    # Merchant candidate (needed for bias calculation)
    merchant_candidate = _guess_merchant_line(lines)
    
    # Compute merchant confidence (heuristic scoring)
    merchant_confidence = _compute_merchant_confidence(merchant_candidate or "", lines, full_text)
    
    # Emit merchant signals
    try:
        signals["merchant.extraction_weak"] = signal_merchant_extraction_weak(
            merchant_candidate, merchant_confidence, conf
        ).dict()
        signals["merchant.confidence_low"] = signal_merchant_confidence_low(
            merchant_confidence
        ).dict()
    except Exception as e:
        logger.warning(f"Failed to emit merchant signals: {e}")
    
    # Safety clamp: never treat low-confidence subtype as truth
    try:
        conf = float(doc_subtype_confidence) if doc_subtype_confidence is not None else 0.0
    except (TypeError, ValueError):
        conf = 0.0
    
    # NOTE: conf must be computed before any address-derived features
    # (V2.1 consistency + V2.2 multi-address both require doc_profile_confidence)
    
    # Initialize unified signals dict
    signals = {}
    
    # Address validation (geo-agnostic, structure-based)
    address_profile = validate_address(full_text)
    
    # V2.1: Merchant-address consistency assessment (feature-only, no scoring impact)
    merchant_address_consistency = assess_merchant_address_consistency(
        merchant_name=merchant_candidate,
        merchant_confidence=merchant_confidence,
        address_profile=address_profile,
        doc_profile_confidence=conf,
    )
    
    # V2.2: Multi-address detection (feature-only)
    multi_address_profile = detect_multi_address_profile(
        text=full_text,
        doc_profile_confidence=conf,
    )
    text_features["multi_address_profile"] = multi_address_profile
    
    # Emit unified signals (V1 contract)
    try:
        signals["addr.structure"] = signal_addr_structure(address_profile).dict()
        signals["addr.merchant_consistency"] = signal_addr_merchant_consistency(merchant_address_consistency).dict()
        signals["addr.multi_address"] = signal_addr_multi_address(multi_address_profile).dict()
    except Exception as e:
        logger.warning(f"Failed to emit address signals: {e}")
    
    # Optional: Record address telemetry (controlled by ENABLE_ADDRESS_TELEMETRY env var)
    import os
    if os.environ.get("ENABLE_ADDRESS_TELEMETRY", "false").lower() == "true":
        try:
            record_address_features(
                address_profile=address_profile,
                merchant_address_consistency=merchant_address_consistency,
                multi_address_profile=multi_address_profile,
                merchant_confidence=merchant_confidence,
                doc_profile_confidence=conf,
                doc_subtype=doc_profile.get("subtype", "UNKNOWN"),
            )
        except Exception as e:
            # Never fail feature extraction due to telemetry
            logger.warning(f"Address telemetry failed: {e}")
    
    # MERCHANT-PRESENT BIAS: Add small positive prior toward TRANSACTIONAL
    # If merchant + currency + table exist, boost confidence slightly
    merchant_present_bias = 0.0
    if merchant_candidate and has_currency and has_line_items:
        merchant_present_bias = 0.08
        conf = min(1.0, conf + merchant_present_bias)

    # EXCEPTION: POS_RESTAURANT is valid even at lower confidence to prevent fallback override
    if conf < 0.5 and doc_subtype_guess_raw != "POS_RESTAURANT":
        doc_subtype_guess = "unknown"

    # Legacy doc_profile for backward compatibility
    # Now unified with new doc_class system via bridge above
    doc_profile = {
        "doc_class": doc_class,
        "doc_subtype_guess": doc_subtype_guess,
        "doc_subtype_confidence": doc_subtype_confidence,
        "doc_subtype_source": doc_subtype_source,
        "doc_subtype_evidence": doc_subtype_evidence,
        "requires_corroboration": requires_corroboration,
        "family": doc_family_guess,
        "confidence": doc_subtype_confidence,
        "llm_classification_attempted": llm_classification_attempted,
        # Language fields will be populated after language ID runs
        "lang": None,
        "lang_confidence": 0.0,
        "lang_source": None,
        # Defensive fix: Add final geo data from detect_geo_and_profile
        "geo_country": geo_profile.get("geo_country_guess"),
        "geo_confidence": geo_profile.get("geo_confidence"),
        # Address validation (gated by doc_profile_confidence)
        "has_address": (
            address_profile["address_classification"] in {"PLAUSIBLE_ADDRESS", "STRONG_ADDRESS"}
            if conf >= 0.55 else None
        ),
    }

    # --- File & metadata features -------------------------------------------
    meta = raw.pdf_metadata or {}
    producer = (meta.get("producer") or meta.get("creator") or "") or ""
    producer_lower = str(producer).lower()

    suspicious_producer = any(p in producer_lower for p in SUSPICIOUS_PRODUCERS)
    # Get image dimensions from first page
    image_width = None
    image_height = None
    if raw.images and len(raw.images) > 0:
        image_width = raw.images[0].width
        image_height = raw.images[0].height

    suspicious_producer = _check_suspicious_producer(meta)
    
    # Emit PDF/template signals (early, before conf is computed)
    try:
        signals["template.pdf_producer_suspicious"] = signal_pdf_producer_suspicious(
            meta, suspicious_producer
        ).dict()
    except Exception as e:
        logger.warning(f"Failed to emit PDF producer signal: {e}")
    
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
        "image_width": image_width,
        "image_height": image_height,
    }

    # --- Text features (continued) -------------------------------------------
    # NOTE: total_mismatch is an *initial* estimate. If semantic verification overrides
    # totals/line-items, we will recompute total_mismatch after SVL.
    total_mismatch = bool(
        total_amount is not None and has_line_items and abs(items_sum - float(total_amount)) > 0.5
    )

    # Tax and subtotal extraction
    subtotal = _find_subtotal(lines)
    tax_amount, tax_rate = _find_tax_amount(lines)
    tax_breakdown = _detect_tax_breakdown(lines)
    
    # Shipping and discount extraction (opportunistic)
    shipping_amount = _find_shipping_amount(lines)
    discount_amount = _find_discount_amount(lines)
    
    # Credit note detection (simple keyword-based)
    CREDIT_NOTE_KEYWORDS = [
        "credit note",
        "credit memo",
        "credit advice",
        "refund note",
        "credit voucher",
    ]
    text_lower = full_text.lower()
    is_credit_note = any(k in text_lower for k in CREDIT_NOTE_KEYWORDS)

    # Receipt number extraction
    receipt_number = _extract_receipt_number(lines)

    # Date and time extraction
    has_date = _has_any_date(full_text)
    receipt_date = _extract_receipt_date(full_text)
    receipt_time = _extract_receipt_time(full_text)
    
    # NEW: Language pack routing information
    lang_system = _get_lang_system()
    router = lang_system['router']
    text_for_routing = "\n".join(lines[:10]) if lines else ""
    routing_result = router.route_document(text_for_routing, allow_multi_pack=True)
    
    lang_pack_info = {
        "primary_lang_pack": routing_result.primary_pack.id,
        "primary_lang_pack_version": routing_result.primary_pack.version,
        "primary_lang_pack_name": routing_result.primary_pack.name,
        "detected_script": routing_result.script,
        "routing_confidence": routing_result.confidence,
        "fallback_packs": [pack.id for pack in routing_result.fallback_packs],
        "is_mixed_script": routing_result.reasoning and any("mixed" in reason.lower() for reason in routing_result.reasoning),
        "routing_reasoning": routing_result.reasoning,
    }
    
    # NEW: Extract merchant details for validation
    merchant_address = _extract_merchant_address(full_text)
    merchant_phone = _extract_merchant_phone(full_text)
    city, pin_code = _extract_city_and_pin(full_text)

    # Get raw OCR text before normalization for spacing analysis
    raw_ocr_text = "\n".join(raw.ocr_text_per_page) if raw.ocr_text_per_page else ""
    text_stats = _compute_text_stats(lines, raw_text=raw_ocr_text)

    # Extract OCR metadata
    ocr_metadata = raw.pdf_metadata.get("ocr_metadata", {}) if raw.pdf_metadata else {}
    # Use None for unknown confidence (not 1.0 or 0.0)
    ocr_confidence = ocr_metadata.get("avg_confidence", None)
    
    # --- Semantic Verification Layer (SVL) ---
    # Use LLM to verify amounts when extraction confidence is low or mismatch is large
    semantic_amounts = None
    semantic_verification_invoked = False  # Was LLM called?
    semantic_verification_applied = False  # Were LLM results used?
    
    try:
        from app.pipelines.llm_semantic_amounts import (
            llm_verify_amounts,
            should_use_semantic_verification
        )
        
        # Decide if semantic verification is needed
        if should_use_semantic_verification(
            ocr_confidence=ocr_confidence,
            line_items_confidence=line_items_confidence,
            total_mismatch_ratio=initial_mismatch_ratio
        ):
            logger.info("Triggering semantic verification (low confidence or large mismatch)")
            semantic_verification_invoked = True
            
            semantic_amounts = llm_verify_amounts(
                text=full_text,
                extracted_amounts=all_amounts,
                ocr_confidence=ocr_confidence,
                doc_subtype=doc_subtype_guess
            )
            
            if semantic_amounts and semantic_amounts.confidence >= 0.85:
                # Use semantic amounts instead of regex extraction
                logger.info(f"Using semantic amounts (confidence: {semantic_amounts.confidence})")
                line_item_amounts = semantic_amounts.line_item_amounts
                items_sum = sum(line_item_amounts) if line_item_amounts else 0.0
                has_line_items = bool(line_item_amounts)
                line_items_confidence = semantic_amounts.confidence
                semantic_verification_applied = True
                
                # Override total if semantic extraction is more confident
                if semantic_amounts.total_amount is not None:
                    total_amount = semantic_amounts.total_amount
            else:
                if semantic_amounts:
                    logger.info(f"Semantic amounts returned but confidence too low ({semantic_amounts.confidence:.2f} < 0.85)")
                else:
                    logger.info("Semantic verification invoked but returned no results (LLM unavailable?)")
    except ImportError:
        logger.debug("Semantic verification not available (llm_semantic_amounts not imported)")
    except Exception as e:
        logger.warning(f"Semantic verification failed: {e}")

    # Recompute mismatch after SVL overrides (important: SVL may change totals/line-items)
    try:
        total_mismatch = bool(
            total_amount is not None
            and has_line_items
            and abs((items_sum or 0.0) - float(total_amount)) > 0.5
        )
    except Exception:
        total_mismatch = False
    
    # Emit amount signals
    try:
        signals["amount.total_mismatch"] = signal_amount_total_mismatch(
            total_amount, items_sum, has_line_items, total_mismatch, conf
        ).dict()
        signals["amount.missing"] = signal_amount_missing(
            total_amount, has_currency, doc_subtype_guess_raw, conf
        ).dict()
        # Semantic override signal (if semantic amounts were used)
        if 'semantic_amounts' in locals() and semantic_amounts:
            signals["amount.semantic_override"] = signal_amount_semantic_override(
                semantic_amounts, 
                text_features.get("total_amount"),  # Original before override
                semantic_amounts.total_amount
            ).dict()
    except Exception as e:
        logger.warning(f"Failed to emit amount signals: {e}")

    # Extract all dates for conflict detection
    all_dates = _extract_all_dates(full_text)
    
    text_features: Dict[str, Any] = {
        # Document classification (early LLM)
        "doc_class": doc_class,
        "doc_class_confidence": doc_class_confidence,
        "doc_class_evidence": doc_class_evidence,
        "doc_profile": doc_profile_obj.to_dict(),
        "llm_classification_attempted": llm_classification_attempted,
        
        # Amounts
        "has_any_amount": bool(all_amounts),
        "num_amount_candidates": len(all_amounts),
        "total_line_present": total_line is not None,
        "total_amount": total_amount,
        "has_line_items": has_line_items,
        "line_items_sum": items_sum if has_line_items else None,
        "line_items_confidence": line_items_confidence,
        "semantic_verification_invoked": semantic_verification_invoked,
        "semantic_verification_applied": semantic_verification_applied,
        "semantic_amounts": semantic_amounts.to_dict() if semantic_amounts else None,
        "total_mismatch": total_mismatch,
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "tax_rate": tax_rate,
        "shipping_amount": shipping_amount,
        "discount_amount": discount_amount,
        "is_credit_note": is_credit_note,
        "receipt_number": receipt_number,
        "has_date": has_date,
        "receipt_date": receipt_date,  # Actual extracted date
        "receipt_time": receipt_time,  # Actual extracted time
        "all_dates": all_dates,  # All dates found (for conflict detection)
        "currency_symbols": currency_symbols,  # List of currencies found
        "merchant_candidate": merchant_candidate,
        # NEW: Merchant validation fields
        "merchant_name": merchant_candidate,  # Alias for validation
        "merchant_address": merchant_address,
        "merchant_phone": merchant_phone,
        "city": city,
        "pin_code": pin_code,
        # OCR quality metadata
        "ocr_confidence": ocr_confidence,
        "ocr_engine": ocr_metadata.get("engine", "unknown"),
        # NEW: Document profile (heuristic)
        "doc_family_guess": doc_profile.get("doc_family_guess"),
        "doc_subtype_guess": doc_profile.get("doc_subtype_guess"),
        "doc_subtype_confidence": doc_profile.get("doc_subtype_confidence"),
        "doc_subtype_source": doc_profile.get("doc_subtype_source"),
        "doc_subtype_evidence": doc_profile.get("doc_subtype_evidence"),
        "requires_corroboration": doc_profile.get("requires_corroboration"),
        # document_intent/domain_hint/domain_validation are attached later (after we have full features).
        "doc_profile_confidence": doc_profile.get("doc_profile_confidence"),
        "doc_profile_evidence": doc_profile.get("doc_profile_evidence"),
        # NEW: Geo-aware classification results
        "lang_guess": geo_profile.get("lang_guess"),
        "lang_confidence": geo_profile.get("lang_confidence"),
        "geo_country_guess": geo_profile.get("geo_country_guess"),
        "geo_confidence": geo_profile.get("geo_confidence"),
        "geo_evidence": geo_profile.get("geo_evidence"),
        # NEW: Address validation (geo-agnostic, structure-based)
        "address_profile": address_profile,
        # V2.1: Merchant-address consistency (feature-only)
        "merchant_address_consistency": merchant_address_consistency,
        # V2.2: Multi-address detection (feature-only)
        "multi_address_profile": multi_address_profile,
        # NEW: Language pack routing information
        **lang_pack_info,
    }
    # Add tax breakdown info
    text_features.update(tax_breakdown)
    text_features.update(text_stats)
    # Add geo-specific features (MX RFC, US ZIP, IN GSTIN, etc.)
    text_features.update(geo_profile.get("geo_specific_features", {}))
    
    # Vision LLM fallback for failed OCR extractions
    try:
        from app.pipelines.ocr_fallback import integrate_vision_fallback
        import os
        # Get original image path if available
        image_path = raw.pdf_metadata.get("file_path") if raw.pdf_metadata else None
        if image_path and os.path.exists(image_path):
            text_features = integrate_vision_fallback(
                text_features=text_features,
                ocr_metadata=ocr_metadata,
                image_path=image_path,
                doc_subtype=doc_subtype_guess
            )
            
            # Re-evaluate doc profile confidence after vision fallback
            if text_features.get("vision_fallback_used"):
                # Vision LLM filled critical fields - boost confidence
                # Check what was fixed
                vision_fixed_merchant = text_features.get("merchant_source") == "vision_llm"
                vision_fixed_date = text_features.get("receipt_date_source") == "vision_llm"
                vision_fixed_total = text_features.get("total_amount_source") == "vision_llm"
                
                # Apply confidence boost based on what was fixed
                confidence_boost = 0.0
                if vision_fixed_merchant:
                    confidence_boost += 0.05
                if vision_fixed_date or text_features.get("receipt_time_source") == "vision_llm":
                    confidence_boost += 0.03
                if vision_fixed_total:
                    confidence_boost += 0.05
                
                if confidence_boost > 0:
                    doc_subtype_confidence = min(doc_subtype_confidence + confidence_boost, 0.95)
                    text_features["doc_subtype_confidence"] = doc_subtype_confidence
                    text_features["vision_confidence_boost"] = confidence_boost
    except Exception as e:
        logger.warning(f"Vision LLM fallback skipped: {e}")

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

    domain_hint = infer_domain_from_domainpacks(
        text_features=text_features,
        lang_features=lang_pack_info,
        layout_features=layout_features,
    )

    # LLM CLASSIFIER GATE: Only call when heuristics are uncertain
    # This is a fallback for low-confidence cases
    llm_classification = None
    try:
        from app.pipelines.llm_classifier import (
            should_call_llm_classifier,
            classify_document_with_llm,
            integrate_llm_classification,
        )
        from app.config.llm_config import LLMConfig, get_llm_client
        
        # Defensive float conversions - handle None values
        domain_conf = float(domain_hint.get("confidence") or 0.0) if domain_hint else 0.0
        lang_conf = float(geo_profile.get("lang_confidence") or 0.0)
        lang_guess = geo_profile.get("lang_guess")
        
        if should_call_llm_classifier(
            doc_profile_confidence=float(doc_profile.get("doc_profile_confidence") or 0.0),
            domain_confidence=domain_conf,
            doc_subtype=str(doc_profile.get("doc_subtype_guess") or doc_subtype_guess or "unknown"),
            lang_confidence=lang_conf,
            lang_guess=lang_guess,
            merchant_candidate=merchant_candidate,
        ):
            # Initialize LLM client from config
            llm_config = LLMConfig.from_env()
            llm_client = get_llm_client(llm_config)
            
            llm_result = classify_document_with_llm(
                text=full_text,
                llm_client=llm_client,
                provider=llm_config.provider,
                model=llm_config.ollama_model if llm_config.provider == "ollama" else llm_config.openai_model,
                max_chars=2000,
                max_tokens=llm_config.max_tokens,
            )
            
            # Merge LLM results with existing heuristics
            # Pass source_text for evidence grounding
            merged = integrate_llm_classification(
                llm_result=llm_result,
                existing_domain_hint=domain_hint,
                existing_doc_profile=doc_profile,
                source_text=full_text[:2000],  # Trimmed for grounding
            )
            
            # Update domain_hint and doc_profile if LLM was more confident
            if merged.get("domain_hint_updated"):
                domain_hint = merged["domain_hint"]
            if merged.get("doc_profile_updated"):
                doc_profile = merged["doc_profile"]
                # Keep locals aligned with the updated profile
                doc_subtype_guess_raw = doc_profile.get("doc_subtype_guess")
                doc_subtype_guess = doc_profile.get("doc_subtype_guess") or doc_subtype_guess
                try:
                    conf = float(doc_profile.get("doc_profile_confidence") or conf)
                except (TypeError, ValueError):
                    pass
            
            llm_classification = merged.get("llm_classification")
    
    except ImportError:
        # LLM classifier not available, continue with heuristics only
        pass
    except Exception as e:
        # Log error but don't fail the entire pipeline
        llm_classification = {"error": str(e)[:100]}

    intent_result = resolve_document_intent(
        doc_subtype=doc_subtype_guess_raw,
        doc_subtype_confidence=conf,
        domain_hint=domain_hint,
        source=IntentSource.HEURISTIC,
    )
    document_intent = intent_result.to_dict()

    domain_validation = validate_domain_pack(
        intent_result=intent_result,
        domain_hint=domain_hint,
    )

    text_features["domain_hint"] = domain_hint
    text_features["document_intent"] = document_intent
    text_features["domain_validation"] = domain_validation
    if llm_classification:
        text_features["llm_classification"] = llm_classification

    # ============================================================================
    # PHASE 2: Deterministic Language Identification
    # ============================================================================
    # Run language ID on text lines for deterministic, confidence-aware detection
    # This replaces fragile LLM-based language guessing
    try:
        lang_result = identify_language(lines)
        
        # Add to text_features (will be used by R10 and other language-aware rules)
        text_features["lang_guess"] = lang_result["lang"]
        text_features["lang_confidence"] = lang_result["lang_confidence"]
        text_features["lang_source"] = lang_result["lang_source"]
        
        # Update doc_profile with language fields (for persistence)
        doc_profile["lang"] = lang_result["lang"]
        doc_profile["lang_confidence"] = lang_result["lang_confidence"]
        doc_profile["lang_source"] = lang_result["lang_source"]
        
        logger.info(f"Language detected: {lang_result['lang']} (confidence: {lang_result['lang_confidence']:.2f}, source: {lang_result['lang_source']})")
    except Exception as e:
        logger.warning(f"Language identification failed: {e}")
        # Fallback to "mixed" state
        text_features["lang_guess"] = "mixed"
        text_features["lang_confidence"] = 0.0
        text_features["lang_source"] = "fallback"
        
        # Update doc_profile with fallback
        doc_profile["lang"] = "mixed"
        doc_profile["lang_confidence"] = 0.0
        doc_profile["lang_source"] = "fallback"

    return ReceiptFeatures(
        file_features=file_features,
        text_features=text_features,
        layout_features=layout_features,
        forensic_features=forensic_features,
        document_intent=document_intent,
        signals=signals,
    )