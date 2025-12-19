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
    # Common time patterns
    time_patterns = [
        r'\b([0-2]?\d):([0-5]\d)\s*(?:AM|PM|am|pm)\b',  # 12:30 PM
        r'\b([0-2]?\d):([0-5]\d):([0-5]\d)\b',  # 14:30:45
        r'\b([0-2]?\d):([0-5]\d)\b',  # 14:30
    ]
    
    for pattern in time_patterns:
        match = re.search(pattern, text)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            
            # Convert to 24-hour format if AM/PM present
            if 'PM' in match.group(0).upper() or 'pm' in match.group(0):
                if hour != 12:
                    hour += 12
            elif 'AM' in match.group(0).upper() or 'am' in match.group(0):
                if hour == 12:
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

    # Tax and subtotal extraction
    subtotal = _find_subtotal(lines)
    tax_amount, tax_rate = _find_tax_amount(lines)
    tax_breakdown = _detect_tax_breakdown(lines)

    # Receipt number extraction
    receipt_number = _extract_receipt_number(lines)

    # Date and time extraction
    has_date = _has_any_date(full_text)
    receipt_date = _extract_receipt_date(full_text)
    receipt_time = _extract_receipt_time(full_text)
    
    # Currency extraction
    currency_symbols = _extract_currency_symbols(full_text)

    # Merchant candidate
    merchant_candidate = _guess_merchant_line(lines)
    
    # NEW: Extract merchant details for validation
    merchant_address = _extract_merchant_address(full_text)
    merchant_phone = _extract_merchant_phone(full_text)
    city, pin_code = _extract_city_and_pin(full_text)

    # Get raw OCR text before normalization for spacing analysis
    raw_ocr_text = "\n".join(raw.ocr_text_per_page) if raw.ocr_text_per_page else ""
    text_stats = _compute_text_stats(lines, raw_text=raw_ocr_text)

    text_features: Dict[str, Any] = {
        "has_any_amount": bool(all_amounts),
        "num_amount_candidates": len(all_amounts),
        "total_line_present": total_line is not None,
        "total_amount": total_amount,
        "has_line_items": has_line_items,
        "line_items_sum": items_sum if has_line_items else None,
        "total_mismatch": total_mismatch,
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "tax_rate": tax_rate,
        "receipt_number": receipt_number,
        "has_date": has_date,
        "receipt_date": receipt_date,  # Actual extracted date
        "receipt_time": receipt_time,  # Actual extracted time
        "currency_symbols": currency_symbols,  # List of currencies found
        "merchant_candidate": merchant_candidate,
        # NEW: Merchant validation fields
        "merchant_name": merchant_candidate,  # Alias for validation
        "merchant_address": merchant_address,
        "merchant_phone": merchant_phone,
        "city": city,
        "pin_code": pin_code,
    }
    # Add tax breakdown info
    text_features.update(tax_breakdown)
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