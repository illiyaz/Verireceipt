# app/pipelines/rules.py

from typing import List, Optional
import logging

from app.schemas.receipt import (
    ReceiptFeatures,
    ReceiptDecision,
    ReceiptInput,
)
from app.pipelines.ingest import ingest_and_ocr
from app.pipelines.features import build_features


logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Helper utilities (keep rule logic self-contained)
# -----------------------------------------------------------------------------

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


def _currency_hint(text: str) -> Optional[str]:
    """Return best-effort currency hint (USD/INR/None) based on symbols/keywords."""
    t = (text or "")
    tl = t.lower()
    if "$" in t or " usd" in tl:
        return "USD"
    if "₹" in t or " inr" in tl or "rupees" in tl or "rs." in tl or "rs " in tl:
        return "INR"
    return None


def _score_and_explain(features: ReceiptFeatures, apply_learned: bool = True) -> ReceiptDecision:
    """
    Convert ReceiptFeatures into a fraud score, label, and reasons.
    v1 is fully rule-based, with transparent reasoning.
    """

    # ---------------------------------------------------------------------------
    # The rule engine builds a fraud score in [0.0, 1.0] by adding weighted points
    # for each triggered anomaly. See README "Rule Engine Specification" for the
    # full documentation of all rules, weights, and reasoning.
    # ---------------------------------------------------------------------------

    score = 0.0
    reasons: List[str] = []       # main/critical reasons
    minor_notes: List[str] = []   # low-severity metadata observations

    ff = features.file_features
    tf = features.text_features
    lf = features.layout_features
    fr = features.forensic_features

    source_type = ff.get("source_type")  # "pdf" or "image" (set by metadata pipelines)

    blob_text = _join_text(tf, lf)

    # ---------------------------------------------------------------------------
    # RULE GROUP 1: Producer / metadata anomalies
    #
    # These checks inspect PDF/image metadata (producer, creator, creation date,
    # modification date, EXIF data). Individually these are weak–medium signals,
    # but in combination they strongly indicate manual editing or template usage.
    # ---------------------------------------------------------------------------

    # R1: Suspicious PDF producer/creator (e.g. Canva/Photoshop/WPS/etc.)
    # CRITICAL: High severity because many fake receipts originate from these tools.
    # Increased from 0.3 to 0.5 to ensure "fake" verdict for PDF editor-generated receipts.
    if ff.get("suspicious_producer"):
        score += 0.5
        producer_name = ff.get('producer') or ff.get('creator')
        reasons.append(
            f"🚨 Suspicious Software Detected: '{producer_name}' - "
            f"This software is commonly used to create fake receipts. "
            f"Real receipts are typically generated by point-of-sale systems or accounting software, "
            f"not design tools like Canva, Photoshop, or PDF generators like TCPDF."
        )

    # For PDFs: missing creation/modification dates are weak signals and logged as minor notes.
    if source_type == "pdf":
        if not ff.get("has_creation_date"):
            score += 0.05
            minor_notes.append("Document is missing a creation date in its metadata.")

        if not ff.get("has_mod_date"):
            score += 0.05
            minor_notes.append("Document is missing a modification date in its metadata.")

    # EXIF: for images, absence of EXIF is *slightly* suspicious for 'photos' of bills.
    # Treated as a low-severity observation.
    if source_type == "image":
        exif_present = ff.get("exif_present")
        if exif_present is False:
            score += 0.05
            minor_notes.append(
                "Image has no EXIF data, which may indicate it was exported or edited rather than captured."
            )

    # ---------------------------------------------------------------------------
    # RULE GROUP 2: Text-based anomalies
    #
    # These are the strongest and most important checks. They analyze OCR text
    # for totals, amounts, line items, dates, and merchant names. Errors in these
    # areas often indicate tampering or synthetically generated receipts.
    # ---------------------------------------------------------------------------

    # R5: No detected currency/amount tokens — a strong indicator of invalid or
    # template-generated receipts. Real receipts almost always contain amounts.
    if not tf.get("has_any_amount"):
        score += 0.4
        reasons.append("No currency or numeric amount could be reliably detected in the receipt text.")

    # No total line but there are amounts
    if tf.get("has_any_amount") and not tf.get("total_line_present"):
        score += 0.15
        reasons.append("Amounts detected but no clear 'Total' line found on the receipt.")

    # R7: Sum of line-item amounts does not match printed total — high severity.
    # Often indicates manual tampering or altered totals.
    if tf.get("total_mismatch"):
        score += 0.4
        reasons.append(
            "Sum of detected line-item amounts does not match the printed total amount."
        )

    # R8: No date detected — most real receipts include a transaction date.
    if not tf.get("has_date"):
        score += 0.2
        reasons.append("No valid date found on the receipt.")

    # R9: Could not infer merchant/store name from header region.
    # Real receipts nearly always show merchant identity clearly.
    if not tf.get("merchant_candidate"):
        score += 0.15
        reasons.append("Could not confidently identify a merchant name in the header.")

    # ---------------------------------------------------------------------------
    # RULE GROUP 3: Layout / structure anomalies
    #
    # These checks use high-level structural cues such as number of lines and the
    # proportion of numeric lines. Useful for detecting receipts that are too short,
    # too long, or unnaturally dominated by numeric values.
    # ---------------------------------------------------------------------------

    num_lines = lf.get("num_lines", 0)
    numeric_ratio = lf.get("numeric_line_ratio", 0.0)

    # R10: Very few lines — real receipts typically contain header, items, totals.
    if num_lines < 5:
        score += 0.15
        reasons.append(
            f"Very few text lines detected in the receipt ({num_lines}), which is atypical for real receipts."
        )

    # R11: Excessively high line count — may indicate noisy OCR or non-receipt pages.
    if num_lines > 120:
        score += 0.1
        reasons.append(
            f"Unusually high number of text lines detected in the receipt ({num_lines}), "
            "which may indicate noisy or synthetic text."
        )

    # R12: Most lines are numeric — may indicate auto-generated tabular data.
    if numeric_ratio > 0.8 and num_lines > 10:
        score += 0.1
        reasons.append(
            "A very high proportion of lines consist mostly of numbers, which may indicate auto-generated content."
        )

    # ---------------------------------------------------------------------------
    # RULE GROUP 4: Forensic-ish cues
    #
    # These are weaker but additive indicators. They highlight repetitive, stylized,
    # or template-like textual patterns (uppercase dominance, low character variety).
    # ---------------------------------------------------------------------------

    uppercase_ratio = fr.get("uppercase_ratio", 0.0)
    unique_char_count = fr.get("unique_char_count", 0)

    # R13: Very high uppercase ratio — template-like headings repeated excessively.
    if uppercase_ratio > 0.8 and num_lines > 5:
        score += 0.1
        reasons.append(
            "A large portion of alphabetic characters are uppercase, giving the text a template-like appearance."
        )

    # R14: Very low character variety — highly repetitive/synthetic content.
    if unique_char_count < 15 and num_lines > 5:
        score += 0.15
        reasons.append(
            "Low variety of characters detected in the text, which may indicate repetitive or template-generated content."
        )
    
    # R14b: Abnormal spacing patterns — excessive or inconsistent spacing
    has_excessive_spacing = fr.get("has_excessive_spacing", False)
    has_inconsistent_spacing = fr.get("has_inconsistent_spacing", False)
    max_consecutive_spaces = fr.get("max_consecutive_spaces", 0)
    
    if has_excessive_spacing or max_consecutive_spaces >= 5:
        score += 0.20
        reasons.append(
            f"📏 Abnormal Text Spacing Detected: Found {max_consecutive_spaces} consecutive spaces between words. "
            f"This is unusual for legitimate receipts and may indicate text manipulation or PDF generation artifacts."
        )
    elif has_inconsistent_spacing:
        score += 0.10
        minor_notes.append(
            f"Inconsistent spacing detected between words (variance: {fr.get('spacing_variance', 0):.1f}). "
            f"May indicate manual text placement or PDF editing."
        )
    
    # R14c: Check for jumbled/disordered text (indicates manual PDF text placement)
    # If text extraction shows words in wrong order, it means text was manually positioned
    avg_line_length = sum(len(line) for line in lf.get("lines", [])) / max(1, num_lines)
    if avg_line_length < 15 and num_lines > 10:
        # Very short average line length with many lines suggests text fragmentation
        score += 0.15
        minor_notes.append(
            f"📝 Text Layout Anomaly: Average line length is only {avg_line_length:.1f} characters. "
            f"This may indicate text was manually placed in a PDF editor rather than naturally generated."
        )

    # ---------------------------------------------------------------------------
    # RULE GROUP 5: Date mismatch (creation date vs receipt date)
    #
    # CRITICAL: If PDF/image was created AFTER the receipt date, it's likely fake.
    # This catches cases where someone creates a fake receipt with a backdated date.
    # ---------------------------------------------------------------------------

    # R15: Creation date vs receipt date mismatch
    if ff.get("has_creation_date") and tf.get("receipt_date"):
        try:
            from datetime import datetime
            
            creation_date_raw = ff.get("creation_date")
            receipt_date_str = tf.get("receipt_date")
            
            if creation_date_raw and receipt_date_str:
                # Parse creation date (from PDF metadata - usually datetime object or string)
                if isinstance(creation_date_raw, str):
                    # Try to parse string date
                    creation_date = None
                    
                    # Handle PDF date format: D:20251130082231+00'00'
                    if creation_date_raw.startswith('D:'):
                        try:
                            # Extract YYYYMMDD from D:YYYYMMDDHHMMSS...
                            date_part = creation_date_raw[2:10]  # Get YYYYMMDD
                            creation_date = datetime.strptime(date_part, '%Y%m%d')
                        except:
                            pass
                    
                    # Try standard formats if not PDF format or if parsing failed
                    if not creation_date:
                        for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M%S"]:
                            try:
                                creation_date = datetime.strptime(creation_date_raw.split()[0], fmt)
                                break
                            except:
                                continue
                    
                    # If still None, try ISO format
                    if not creation_date:
                        try:
                            creation_date = datetime.fromisoformat(creation_date_raw.replace('Z', '+00:00'))
                        except:
                            pass
                else:
                    # Assume it's already a datetime object
                    creation_date = creation_date_raw
                
                # Parse receipt date (from OCR text - normalized to YYYY-MM-DD)
                receipt_date = datetime.strptime(receipt_date_str, "%Y-%m-%d")
                
                if creation_date and receipt_date:
                    # Calculate difference in days
                    days_diff = (creation_date.date() - receipt_date.date()).days
                    
                    # Receipt date is in the future relative to creation (impossible!)
                    if days_diff < -1:
                        score += 0.4
                        reasons.append(
                            f"⚠️ Impossible Date Sequence Detected:\n"
                            f"   • Receipt/Purchase Date: {receipt_date_str}\n"
                            f"   • PDF Creation Date: {creation_date.date()}\n"
                            f"   • Time Difference: Receipt is {abs(days_diff)} days AFTER file creation\n"
                            f"   • Problem: This is physically impossible - a receipt cannot be dated after the file containing it was created. "
                            f"This strongly indicates the receipt was backdated or fabricated."
                        )
                    
                    # File created more than 2 days after receipt date (suspicious)
                    elif days_diff > 2:
                        score += 0.35
                        reasons.append(
                            f"⏰ Suspicious Date Gap Detected:\n"
                            f"   • Receipt/Purchase Date: {receipt_date_str}\n"
                            f"   • PDF Creation Date: {creation_date.date()}\n"
                            f"   • Time Difference: File created {days_diff} days AFTER the receipt date\n"
                            f"   • Analysis: While receipts can be scanned later, a {days_diff}-day gap is unusual for expense claims. "
                            f"This pattern is common in backdated or fabricated receipts created to match past dates."
                        )
                    
                    # Same day or next day (normal - receipt scanned same/next day)
                    elif days_diff >= -1 and days_diff <= 2:
                        minor_notes.append(
                            f"Receipt scanned within {days_diff} day(s) of transaction - normal timing."
                        )
        except Exception as e:
            # Date parsing failed - log but don't penalize
            minor_notes.append(f"Could not compare creation date vs receipt date: {str(e)}")

    # ---------------------------------------------------------------------------
    # RULE GROUP 6: Visual quality indicators (computer-generated detection)
    #
    # These checks detect receipts that look too perfect to be real scans.
    # Real scanned receipts have imperfections, while computer-generated ones
    # (Canva, Photoshop, etc.) are too clean and uniform.
    # ---------------------------------------------------------------------------

    # R16: No metadata present (likely stripped by editing software)
    # When images have EXIF but no useful metadata, it's suspicious
    if source_type == "image":
        exif_present = ff.get("exif_present", False)
        exif_keys = ff.get("exif_keys_count", 0)
        has_creator = bool(ff.get("creator") or ff.get("producer"))
        
        # Has EXIF but no creator/software info = metadata stripped
        if exif_present and exif_keys > 0 and not has_creator:
            score += 0.25
            reasons.append(
                f"🔍 Metadata Stripped: This image has EXIF data ({exif_keys} fields) but no creator or software information. "
                f"This is a common technique used by editing software (like Canva) to hide the source. "
                f"Real scanned receipts typically preserve camera or scanner metadata."
            )
    
    # R17: Extremely low OCR confidence / garbled text
    # Computer-generated images often have poor OCR due to low resolution or compression
    # Real scans usually have better OCR quality
    avg_line_length = sum(len(line) for line in lf.get("lines", [])) / max(1, num_lines)
    if avg_line_length < 10 and num_lines > 5:
        score += 0.15
        reasons.append(
            f"📝 Poor Text Quality: Average line length is only {avg_line_length:.1f} characters. "
            f"This suggests either very low image quality or garbled OCR, which is common in "
            f"low-resolution computer-generated images or screenshots."
        )
    
    # R18: No clear structure (missing merchant, total, date)
    # Real receipts have clear structure, fake ones often miss key elements
    missing_elements = []
    if not tf.get("merchant_candidate"):
        missing_elements.append("merchant")
    if not tf.get("total_amount"):
        missing_elements.append("total")
    if not tf.get("has_date"):
        missing_elements.append("date")
    
    if len(missing_elements) >= 2:
        score += 0.20
        reasons.append(
            f"❌ Incomplete Receipt Structure: Missing critical elements: {', '.join(missing_elements)}. "
            f"Legitimate receipts from real businesses always include merchant name, total amount, and date. "
            f"The absence of {len(missing_elements)} key elements suggests this may be a poorly constructed fake."
        )

    # ---------------------------------------------------------------------------
    # RULE GROUP 7: Tax and calculation checks
    #
    # Verify mathematical accuracy of tax calculations and totals.
    # Fake receipts often have incorrect math.
    # ---------------------------------------------------------------------------

    # R19: Tax calculation mismatch
    subtotal = tf.get("subtotal")
    tax_amount = tf.get("tax_amount")
    tax_rate = tf.get("tax_rate")
    total_amount = tf.get("total_amount")
    
    if subtotal and tax_amount and total_amount:
        # Check if subtotal + tax = total
        expected_total = subtotal + tax_amount
        total_diff = abs(total_amount - expected_total)
        
        if total_diff > 1.0:  # Allow 1 rupee/dollar rounding
            score += 0.30
            reasons.append(
                f"🧮 Math Error Detected:\n"
                f"   • Subtotal: {subtotal:.2f}\n"
                f"   • Tax: {tax_amount:.2f}\n"
                f"   • Expected Total: {expected_total:.2f}\n"
                f"   • Actual Total on Receipt: {total_amount:.2f}\n"
                f"   • Difference: {total_diff:.2f}\n"
                f"   • Problem: Real receipts from legitimate businesses have accurate calculations. "
                f"Math errors like this are a strong indicator of manually created fake receipts."
            )
        
        # If tax rate is given, verify tax calculation
        if tax_rate:
            expected_tax = subtotal * (tax_rate / 100)
            tax_diff = abs(tax_amount - expected_tax)
            
            if tax_diff > 1.0:
                score += 0.25
                reasons.append(
                    f"💰 Tax Calculation Error:\n"
                    f"   • Subtotal: {subtotal:.2f}\n"
                    f"   • Tax Rate Claimed: {tax_rate}%\n"
                    f"   • Expected Tax ({tax_rate}% of {subtotal:.2f}): {expected_tax:.2f}\n"
                    f"   • Actual Tax on Receipt: {tax_amount:.2f}\n"
                    f"   • Difference: {tax_diff:.2f}\n"
                    f"   • Problem: Incorrect tax calculations are common in manually created fake receipts."
                )
    
    # R20: Total doesn't match standard tax rates (if no explicit tax line)
    elif total_amount and tf.get("line_items_sum") and not tax_amount:
        items_sum = tf.get("line_items_sum")
        # Common tax rates: 5%, 10%, 12%, 18%, 20%
        common_rates = [0.05, 0.10, 0.12, 0.18, 0.20]
        
        matches_any_rate = False
        for rate in common_rates:
            expected_total = items_sum * (1 + rate)
            if abs(total_amount - expected_total) / total_amount < 0.02:  # Within 2%
                matches_any_rate = True
                break
        
        # Also check if total equals items_sum (no tax)
        if abs(total_amount - items_sum) < 1.0:
            matches_any_rate = True
        
        if not matches_any_rate and items_sum > 0:
            score += 0.20
            reasons.append(
                f"❓ Unusual Total Amount:\n"
                f"   • Line Items Sum: {items_sum:.2f}\n"
                f"   • Total on Receipt: {total_amount:.2f}\n"
                f"   • Difference: {abs(total_amount - items_sum):.2f}\n"
                f"   • Analysis: This doesn't match any standard tax rate (5%, 10%, 12%, 18%, 20%) or a no-tax scenario. "
                f"Real receipts follow predictable tax patterns. This mismatch suggests manual fabrication."
            )
    
    # R20b: Indian GST validation (CGST + SGST should equal total tax, or IGST for interstate)
    is_indian = tf.get("is_indian_receipt", False)
    if is_indian:
        has_cgst = tf.get("has_cgst", False)
        has_sgst = tf.get("has_sgst", False)
        has_igst = tf.get("has_igst", False)
        cgst_amount = tf.get("cgst_amount")
        sgst_amount = tf.get("sgst_amount")
        igst_amount = tf.get("igst_amount")
        
        # Indian GST rule: Either (CGST + SGST) for intrastate OR IGST for interstate
        # Having both is incorrect
        if has_cgst and has_sgst and has_igst:
            score += 0.30
            reasons.append(
                f"🇮🇳 Indian GST Error: Receipt shows both CGST+SGST (intrastate) AND IGST (interstate). "
                f"This is impossible - Indian receipts use either CGST+SGST for same-state transactions "
                f"or IGST for interstate transactions, never both."
            )
        
        # Validate CGST + SGST = total tax (they should be equal amounts)
        elif has_cgst and has_sgst and cgst_amount and sgst_amount:
            # CGST and SGST should be equal
            if abs(cgst_amount - sgst_amount) > 0.5:
                score += 0.25
                reasons.append(
                    f"🇮🇳 Indian GST Error:\n"
                    f"   • CGST: {cgst_amount:.2f}\n"
                    f"   • SGST: {sgst_amount:.2f}\n"
                    f"   • Problem: In Indian GST system, CGST and SGST must be equal amounts (each is half of the total GST rate). "
                    f"This mismatch indicates an incorrect or fabricated receipt."
                )
            
            # Check if CGST + SGST matches the total tax
            if tax_amount:
                expected_tax = cgst_amount + sgst_amount
                if abs(tax_amount - expected_tax) > 1.0:
                    score += 0.20
                    reasons.append(
                        f"🇮🇳 Indian GST Calculation Error:\n"
                        f"   • CGST: {cgst_amount:.2f}\n"
                        f"   • SGST: {sgst_amount:.2f}\n"
                        f"   • CGST + SGST: {expected_tax:.2f}\n"
                        f"   • Total Tax Shown: {tax_amount:.2f}\n"
                        f"   • Difference: {abs(tax_amount - expected_tax):.2f}\n"
                        f"   • Problem: Total tax should equal CGST + SGST in Indian receipts."
                    )

    # ---------------------------------------------------------------------------
    # RULE GROUP 8: Receipt number validation
    #
    # Check for suspicious receipt number patterns that are common in fakes.
    # ---------------------------------------------------------------------------

    # R21: Suspicious receipt number patterns
    receipt_number = tf.get("receipt_number")
    
    if receipt_number:
        receipt_num_clean = receipt_number.replace('-', '').replace('_', '').upper()
        
        # Check for very simple numbers (001, 123, etc.)
        if receipt_num_clean.isdigit() and len(receipt_num_clean) <= 4:
            num_value = int(receipt_num_clean)
            if num_value < 100:
                score += 0.25
                reasons.append(
                    f"🔢 Suspiciously Simple Receipt Number: '{receipt_number}' (value: {num_value}) is extremely low. "
                    f"Real businesses process hundreds or thousands of transactions and use larger receipt numbers. "
                    f"Simple numbers like this are commonly used in hastily created fake receipts."
                )
        
        # Check for all same digit (1111, 0000, etc.)
        if len(set(receipt_num_clean)) == 1 and len(receipt_num_clean) >= 3:
            score += 0.30
            reasons.append(
                f"🚫 Repetitive Receipt Number: '{receipt_number}' consists of all identical digits. "
                f"Real receipt numbering systems never use patterns like '1111' or '0000'. "
                f"This is a clear sign of a fabricated receipt where someone didn't bother creating a realistic number."
            )
        
        # Check for sequential patterns (12345, 123456, etc.)
        if receipt_num_clean.isdigit() and len(receipt_num_clean) >= 4:
            is_sequential = True
            for i in range(len(receipt_num_clean) - 1):
                if int(receipt_num_clean[i+1]) != (int(receipt_num_clean[i]) + 1) % 10:
                    is_sequential = False
                    break
            
            if is_sequential:
                score += 0.25
                reasons.append(
                    f"🔢 Sequential Receipt Number: '{receipt_number}' follows a sequential pattern (like 12345). "
                    f"Real receipt numbers are typically random or use complex formats with dates/store codes. "
                    f"Sequential patterns like this are a hallmark of fake receipts."
                )

    # ---------------------------------------------------------------------------
    # RULE GROUP 9: Image quality and dimensions
    #
    # Check for suspicious image dimensions that indicate computer-generated receipts.
    # ---------------------------------------------------------------------------

    # R22: Suspicious image dimensions
    image_width = ff.get("image_width")
    image_height = ff.get("image_height")
    
    if image_width and image_height:
        # Canva default dimensions (1080x1080)
        if image_width == 1080 and image_height == 1080:
            score += 0.25
            reasons.append(
                f"🎨 Canva Signature Detected: Image dimensions are exactly 1080x1080 pixels, which is Canva's default canvas size. "
                f"Real receipt scans have irregular dimensions based on paper size and scanner settings. "
                f"This perfect square format is a strong indicator the receipt was created in Canva, not scanned from a real document."
            )
        
        # Very small images (likely screenshots)
        elif image_width < 800 or image_height < 800:
            score += 0.15
            reasons.append(
                f"📱 Low Resolution Image: Dimensions are only {image_width}x{image_height} pixels. "
                f"Real receipt scans are typically 1200+ pixels to capture fine print clearly. "
                f"This low resolution suggests a screenshot or a low-quality image downloaded from the internet."
            )
        
        # Perfect square (unusual for receipts)
        elif image_width == image_height and image_width >= 1000:
            score += 0.20
            reasons.append(
                f"🔳 Unusual Square Format: Image is a perfect square ({image_width}x{image_height}). "
                f"Real receipts are rectangular (portrait orientation) due to paper dimensions. "
                f"Square images are typical of design software templates, not real scanned documents."
            )

    # ---------------------------------------------------------------------------
    # RULE GROUP 10: Timestamp validation
    #
    # Check for suspicious transaction times and future dates.
    # ---------------------------------------------------------------------------

    # R23: Timestamp validation
    receipt_date_str = tf.get("receipt_date")
    receipt_time = tf.get("receipt_time")
    
    if receipt_date_str:
        try:
            from datetime import datetime, date
            receipt_date = datetime.strptime(receipt_date_str, "%Y-%m-%d").date()
            today = date.today()
            
            # Future date (impossible)
            if receipt_date > today:
                days_future = (receipt_date - today).days
                score += 0.40
                reasons.append(
                    f"⏰ Future Date Detected:\n"
                    f"   • Receipt Date: {receipt_date_str}\n"
                    f"   • Today's Date: {today}\n"
                    f"   • Difference: {days_future} days in the FUTURE\n"
                    f"   • Problem: Receipt cannot be dated in the future. This is impossible and indicates fabrication."
                )
            
            # Very old receipt (over 1 year - unusual for expense claims)
            elif (today - receipt_date).days > 365:
                days_old = (today - receipt_date).days
                score += 0.10
                minor_notes.append(
                    f"Receipt is {days_old} days old (over 1 year) - unusual for expense claims."
                )
        except:
            pass
    
    # Check transaction time
    if receipt_time:
        try:
            hour = int(receipt_time.split(':')[0])
            minute = int(receipt_time.split(':')[1])
            
            # Very early morning (12 AM - 5 AM) - unusual for most businesses
            if hour >= 0 and hour < 5:
                score += 0.15
                reasons.append(
                    f"🌙 Unusual Transaction Time:\n"
                    f"   • Time: {receipt_time}\n"
                    f"   • Analysis: Transaction at {hour}:{minute:02d} is very early morning. "
                    f"Most retail businesses are closed during these hours. "
                    f"This timing is suspicious for a regular purchase."
                )
            
            # Very late night (11 PM - 12 AM) - less common
            elif hour == 23:
                score += 0.10
                minor_notes.append(
                    f"Transaction at {receipt_time} (late night) - less common for retail purchases."
                )
        except:
            pass

    # ---------------------------------------------------------------------------
    # RULE GROUP 11: Currency consistency
    #
    # Check for mixed currency symbols (indicates fabrication).
    # ---------------------------------------------------------------------------

    # R24: Multiple currency symbols
    currency_symbols = tf.get("currency_symbols", [])
    
    if len(currency_symbols) > 1:
        score += 0.30
        reasons.append(
            f"💱 Mixed Currency Symbols Detected:\n"
            f"   • Currencies Found: {', '.join(currency_symbols)}\n"
            f"   • Problem: Real receipts use a single currency. Multiple currency symbols "
            f"({len(currency_symbols)} different currencies) indicate the receipt was manually created "
            f"by combining elements from different sources or templates."
        )

    # ---------------------------------------------------------------------------
    # RULE GROUP 12: Cross-field consistency rules (strong fraud signals)
    #
    # These rules catch synthetic / template invoices that look visually valid
    # but fail basic real-world consistency checks (geo, tax regime, identifiers).
    # ---------------------------------------------------------------------------

    # R30: Geography mismatch (US-style address cues + India cues like +91/PIN/GST)
    addr_text = " ".join(
        [
            str(tf.get("merchant_address") or ""),
            str(tf.get("city") or ""),
            str(tf.get("state") or ""),
            str(tf.get("pin_code") or ""),
            str(tf.get("country") or ""),
        ]
    )
    phone_text = str(tf.get("merchant_phone") or "")

    us_hint = _detect_us_state_hint(addr_text) or _detect_us_state_hint(blob_text)
    india_hint = _detect_india_hint(addr_text) or _detect_india_hint(blob_text)
    phone_india = "+91" in phone_text or "+91" in blob_text

    if us_hint and (india_hint or phone_india):
        score += 0.30
        reasons.append(
            "🌍 Geography Mismatch: The document mixes US location cues with India cues "
            "(e.g., +91 phone/PIN/state references). Legitimate invoices rarely mix jurisdictions "
            "like this without clear cross-border context."
        )

    # R31: Currency vs tax-regime mismatch (USD with GST terms; INR with US sales-tax terms)
    currency_from_features = None
    if isinstance(tf.get("currency_symbols"), list) and tf.get("currency_symbols"):
        syms = tf.get("currency_symbols")
        if "$" in syms:
            currency_from_features = "USD"
        if "₹" in syms and currency_from_features is None:
            currency_from_features = "INR"

    currency_hint = currency_from_features or _currency_hint(blob_text)

    has_gst_terms = (
        _has_any_pattern(blob_text, ["gst", "cgst", "sgst", "igst"])
        or bool(tf.get("has_cgst") or tf.get("has_sgst") or tf.get("has_igst"))
    )
    has_us_tax_terms = _has_any_pattern(blob_text, ["sales tax", "state tax", "county tax"])

    if currency_hint == "USD" and has_gst_terms:
        score += 0.30
        reasons.append(
            "💱 Tax/Currency Inconsistency: USD formatting combined with GST terms "
            "(GST/CGST/SGST/IGST) is highly unusual and commonly seen in fabricated invoices."
        )
    elif currency_hint == "INR" and has_us_tax_terms and not has_gst_terms:
        score += 0.15
        reasons.append(
            "💱 Tax/Currency Inconsistency: The document looks India/INR-oriented but uses US sales-tax "
            "terminology without GST breakdown. This mismatch is suspicious for reimbursement receipts."
        )

    # R32: Missing mandatory identifiers for high-value invoices
    total_amount = tf.get("total_amount")
    high_value_threshold = 100000  # conservative INR-like threshold

    if isinstance(total_amount, (int, float)) and total_amount >= high_value_threshold:
        has_gstin = bool(tf.get("gstin")) or _looks_like_gstin(blob_text)
        has_pan = bool(tf.get("pan")) or _looks_like_pan(blob_text)
        has_ein = bool(tf.get("ein")) or _looks_like_ein(blob_text)

        if not (has_gstin or has_pan or has_ein):
            score += 0.25
            reasons.append(
                f"🪪 Missing Business Identifiers: High-value invoice (total={total_amount:.2f}) but no "
                "GSTIN/PAN/EIN-like identifier was found. Legitimate businesses usually include legal/"
                "registration identifiers on invoices."
            )

    # R33: Template / placeholder artifacts
    if _has_any_pattern(
        blob_text,
        [
            "<payment terms",
            "<payment term",
            "<due on receipt",
            "invoice template",
        ],
    ):
        score += 0.20
        reasons.append(
            "📄 Template Artifact Detected: Placeholder-like text (e.g., '<Payment terms...>') suggests "
            "the invoice was created from a template rather than generated by a POS/accounting system."
        )

    # R34: Vague, high-value line item descriptions without breakdown
    if _has_any_pattern(
        blob_text,
        [
            "incidentals",
            "incidental",
            "consultation",
            "professional fee",
            "service fee",
        ],
    ):
        has_breakdown_terms = _has_any_pattern(
            blob_text,
            [
                "hour",
                "hrs",
                "hourly",
                "rate",
                "/hr",
                "per hour",
                "ref:",
                "case id",
            ],
        )
        if not has_breakdown_terms and isinstance(total_amount, (int, float)) and total_amount >= high_value_threshold:
            score += 0.15
            reasons.append(
                "🧾 Vague High-Value Charges: Generic fee terms (e.g., 'Incidentals'/'Consultation') but no "
                "basic breakdown (hours/rates/reference). This pattern is common in fabricated invoices."
            )
    # --- R25: Address Validation ---------------------------------------------
    merchant_address = tf.get("merchant_address")
    if merchant_address:
        try:
            from app.validation.address_validator import validate_address_complete
            
            address_validation = validate_address_complete(
                merchant_address,
                merchant_name=tf.get("merchant_name")
            )
            
            if not address_validation["valid"]:
                score += 0.15
                address_issues = address_validation["issues"][:2]  # Top 2 issues
                reasons.append(
                    f"📍 R25: Invalid Address Format:\n"
                    f"   • Address: {merchant_address[:50]}...\n"
                    f"   • Issues: {', '.join(address_issues)}\n"
                    f"   • Confidence: {address_validation['confidence']:.0%}\n"
                    f"   • Problem: Address format or geography doesn't match real-world data."
                )
        except Exception as e:
            minor_notes.append(f"Address validation error: {str(e)}")
    
    # --- R26: Merchant Verification ------------------------------------------
    merchant_name = tf.get("merchant_name")
    if merchant_name:
        try:
            from app.validation.merchant_validator import validate_merchant_complete
            
            merchant_validation = validate_merchant_complete(
                merchant_name,
                city=tf.get("city"),
                pin_code=tf.get("pin_code"),
                items=tf.get("items")
            )
            
            # Known merchant but location mismatch
            if merchant_validation.get("known_merchant") and not merchant_validation["verified"]:
                score += 0.20
                reasons.append(
                    f"🏪 R26: Merchant Location Mismatch:\n"
                    f"   • Merchant: {merchant_name}\n"
                    f"   • Issues: {', '.join(merchant_validation['issues'][:2])}\n"
                    f"   • Problem: Known merchant but location doesn't match database."
                )
            
            # Suspicious merchant name patterns
            elif not merchant_validation["valid"] and merchant_validation["confidence"] < 0.5:
                score += 0.15
                reasons.append(
                    f"⚠️ R26: Suspicious Merchant Name:\n"
                    f"   • Merchant: {merchant_name}\n"
                    f"   • Issues: {', '.join(merchant_validation['issues'][:2])}\n"
                    f"   • Problem: Merchant name has suspicious patterns."
                )
        except Exception as e:
            minor_notes.append(f"Merchant validation error: {str(e)}")
    
    # --- R27: Phone Number Validation ----------------------------------------
    merchant_phone = tf.get("merchant_phone")
    if merchant_phone:
        try:
            from app.validation.phone_validator import validate_phone_number
            
            phone_validation = validate_phone_number(merchant_phone, country="IN")
            
            if not phone_validation["valid"]:
                score += 0.10
                reasons.append(
                    f"📞 R27: Invalid Phone Number:\n"
                    f"   • Phone: {merchant_phone}\n"
                    f"   • Issues: {', '.join(phone_validation['issues'][:2])}\n"
                    f"   • Problem: Phone number format is invalid or appears fake."
                )
        except Exception as e:
            minor_notes.append(f"Phone validation error: {str(e)}")
    
    # --- R28: Business Hours Validation --------------------------------------
    receipt_time = tf.get("receipt_time")
    if receipt_time and merchant_name:
        try:
            from app.validation.business_hours_validator import validate_business_hours
            
            hours_validation = validate_business_hours(
                merchant_name,
                receipt_time,
                receipt_date=tf.get("receipt_date")
            )
            
            if not hours_validation["valid"]:
                score += 0.10
                reasons.append(
                    f"🕐 R28: Unusual Transaction Time:\n"
                    f"   • Time: {receipt_time} ({hours_validation.get('transaction_hour', 'N/A')}:00)\n"
                    f"   • Business Hours: {hours_validation.get('business_hours', 'N/A')}\n"
                    f"   • Issues: {', '.join(hours_validation['issues'][:2])}\n"
                    f"   • Problem: Transaction outside typical business hours."
                )
        except Exception as e:
            minor_notes.append(f"Business hours validation error: {str(e)}")

    # --- 12. Normalize and classify ------------------------------------------

    # Clamp score to [0, 1]
    score = max(0.0, min(1.0, score))

    if score < 0.3:
        label = "real"
    elif score < 0.6:
        label = "suspicious"
    else:
        label = "fake"

    # If there are no reasons but score is low, add a generic explanation
    if not reasons and label == "real":
        reasons.append("No strong anomalies detected based on current rule set.")
    
    # Apply learned rules from feedback (if enabled)
    if apply_learned:
        try:
            from app.pipelines.learning import apply_learned_rules
            
            learned_adjustment, triggered_rules = apply_learned_rules(features.__dict__)
            
            if learned_adjustment != 0.0:
                score += learned_adjustment
                score = max(0.0, min(1.0, score))  # Clamp to [0, 1]
                
                # Re-evaluate label with adjusted score
                if score < 0.3:
                    label = "real"
                elif score < 0.6:
                    label = "suspicious"
                else:
                    label = "fake"
                
                # Add learned rules to reasoning
                for rule in triggered_rules:
                    reasons.append(f"📚 Learned Rule: {rule}")
                
                logger.info(f"Applied {len(triggered_rules)} learned rules, adjustment: {learned_adjustment:+.2f}")
        except Exception as e:
            logger.warning(f"Failed to apply learned rules: {e}")

    return ReceiptDecision(
        label=label,
        score=score,
        reasons=reasons,
        features=features,
        minor_notes=minor_notes or None,
    )


def analyze_receipt(
    file_path: str,
    extracted_total: Optional[str] = None,
    extracted_merchant: Optional[str] = None,
    extracted_date: Optional[str] = None
) -> ReceiptDecision:
    """
    High-level orchestrator:
    file_path -> ingest+OCR -> features -> rule-based decision.
    
    Args:
        file_path: Path to receipt image/PDF
        extracted_total: Pre-extracted total from advanced models (DONUT/LayoutLM)
        extracted_merchant: Pre-extracted merchant from advanced models
        extracted_date: Pre-extracted date from advanced models
    
    If extracted data is provided, it will be used to enhance OCR results.
    This allows advanced vision models to help Rule-Based engine.
    """
    inp = ReceiptInput(file_path=file_path)
    raw = ingest_and_ocr(inp)
    feats = build_features(raw)
    
    # Enhance features with pre-extracted data if available
    if extracted_total and not feats.text_features.get("total"):
        logger.info(f"✨ Using pre-extracted total: {extracted_total}")
        feats.text_features["total"] = extracted_total
        feats.text_features["total_line_present"] = True  # Mark that total exists
    
    if extracted_merchant and not feats.text_features.get("merchant"):
        logger.info(f"✨ Using pre-extracted merchant: {extracted_merchant}")
        feats.text_features["merchant"] = extracted_merchant
    
    if extracted_date and not feats.text_features.get("date"):
        logger.info(f"✨ Using pre-extracted date: {extracted_date}")
        feats.text_features["date"] = extracted_date
    
    decision = _score_and_explain(feats)
    return decision