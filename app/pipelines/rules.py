# app/pipelines/rules.py

from typing import List

from app.schemas.receipt import (
    ReceiptFeatures,
    ReceiptDecision,
    ReceiptInput,
)
from app.pipelines.ingest import ingest_and_ocr
from app.pipelines.features import build_features


def _score_and_explain(feats: ReceiptFeatures) -> ReceiptDecision:
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

    ff = feats.file_features
    tf = feats.text_features
    lf = feats.layout_features
    fr = feats.forensic_features

    source_type = ff.get("source_type")  # "pdf" or "image" (set by metadata pipelines)

    # ---------------------------------------------------------------------------
    # RULE GROUP 1: Producer / metadata anomalies
    #
    # These checks inspect PDF/image metadata (producer, creator, creation date,
    # modification date, EXIF data). Individually these are weak–medium signals,
    # but in combination they strongly indicate manual editing or template usage.
    # ---------------------------------------------------------------------------

    # R1: Suspicious PDF producer/creator (e.g. Canva/Photoshop/WPS/etc.)
    # High severity because many fake receipts originate from these tools.
    if ff.get("suspicious_producer"):
        score += 0.3
        reasons.append(
            f"PDF producer/creator ('{ff.get('producer') or ff.get('creator')}') "
            "is commonly associated with edited or template-based documents."
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
                            f"CRITICAL: Receipt date ({receipt_date_str}) is {abs(days_diff)} days AFTER "
                            f"file creation date - this is impossible and indicates fabrication."
                        )
                    
                    # File created more than 2 days after receipt date (suspicious)
                    elif days_diff > 2:
                        score += 0.35
                        reasons.append(
                            f"Suspicious: File created {days_diff} days after receipt date ({receipt_date_str}) - "
                            f"likely backdated or fabricated."
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
                "Image metadata appears stripped or minimal - common with edited/generated receipts."
            )
    
    # R17: Extremely low OCR confidence / garbled text
    # Computer-generated images often have poor OCR due to low resolution or compression
    # Real scans usually have better OCR quality
    avg_line_length = sum(len(line) for line in lf.get("lines", [])) / max(1, num_lines)
    if avg_line_length < 10 and num_lines > 5:
        score += 0.15
        reasons.append(
            "Very short average line length - may indicate low quality or synthetic image."
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
            f"Missing multiple key elements ({', '.join(missing_elements)}) - "
            f"unusual for legitimate receipts."
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
                f"Math error: Subtotal ({subtotal:.2f}) + Tax ({tax_amount:.2f}) "
                f"≠ Total ({total_amount:.2f}). Difference: {total_diff:.2f}"
            )
        
        # If tax rate is given, verify tax calculation
        if tax_rate:
            expected_tax = subtotal * (tax_rate / 100)
            tax_diff = abs(tax_amount - expected_tax)
            
            if tax_diff > 1.0:
                score += 0.25
                reasons.append(
                    f"Tax calculation error: {tax_rate}% of {subtotal:.2f} "
                    f"should be {expected_tax:.2f}, but got {tax_amount:.2f}"
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
                f"Total ({total_amount:.2f}) doesn't match line items ({items_sum:.2f}) "
                f"plus any standard tax rate - suspicious calculation"
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
                    f"Receipt number '{receipt_number}' is suspiciously simple (< 100) - "
                    f"real receipts typically have larger numbers"
                )
        
        # Check for all same digit (1111, 0000, etc.)
        if len(set(receipt_num_clean)) == 1 and len(receipt_num_clean) >= 3:
            score += 0.30
            reasons.append(
                f"Receipt number '{receipt_number}' has all same digits - highly suspicious"
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
                    f"Receipt number '{receipt_number}' is sequential - suspicious pattern"
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
                "Image dimensions (1080x1080) match Canva default - likely computer-generated"
            )
        
        # Very small images (likely screenshots)
        elif image_width < 800 or image_height < 800:
            score += 0.15
            reasons.append(
                f"Low resolution image ({image_width}x{image_height}) - may be screenshot or low-quality fake"
            )
        
        # Perfect square (unusual for receipts)
        elif image_width == image_height and image_width >= 1000:
            score += 0.20
            reasons.append(
                f"Perfect square dimensions ({image_width}x{image_height}) - unusual for real receipts"
            )

    # --- 10. Normalize and classify ------------------------------------------

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

    return ReceiptDecision(
        label=label,
        score=score,
        reasons=reasons,
        features=feats,
        minor_notes=minor_notes or None,
    )


def analyze_receipt(file_path: str) -> ReceiptDecision:
    """
    High-level orchestrator:
    file_path -> ingest+OCR -> features -> rule-based decision.
    This is the function described in the README.
    """
    inp = ReceiptInput(file_path=file_path)
    raw = ingest_and_ocr(inp)
    feats = build_features(raw)
    decision = _score_and_explain(feats)
    return decision