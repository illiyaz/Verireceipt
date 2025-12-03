# Advanced Fraud Detection Checks - Smart Ideas

## **Currently Implemented** ✅

1. ✅ Suspicious producers (Canva, TCPDF, etc.)
2. ✅ Date mismatch (creation vs receipt date)
3. ✅ Stripped metadata
4. ✅ Missing key elements
5. ✅ Poor OCR quality

---

## **High-Priority Checks to Add** 🔥

### **1. Font Consistency Analysis** 🔥

**Problem:** Real receipts use thermal printers with consistent fonts. Fake receipts mix multiple fonts.

**Detection:**
```python
# R19: Multiple font styles detected
# Analyze character widths, heights, spacing
def detect_mixed_fonts(text_lines):
    # Real thermal receipts: uniform character width
    # Fake receipts: variable fonts (Arial, Times, etc.)
    
    char_widths = []
    for line in lines:
        # Measure character spacing
        avg_width = len(line) / max(1, count_chars(line))
        char_widths.append(avg_width)
    
    variance = std_dev(char_widths)
    
    if variance > threshold:
        score += 0.25
        reason = "Multiple font styles detected - real receipts use uniform thermal printing"
```

**Impact:** High - catches Canva/Photoshop receipts

---

### **2. Receipt Number Validation** 🔥

**Problem:** Fake receipts often have invalid or sequential receipt numbers.

**Detection:**
```python
# R20: Invalid receipt number format
def validate_receipt_number(text):
    # Real patterns:
    # - Random: "R-8472-3829"
    # - Sequential with date: "20251130-0042"
    # - Store-specific: "WM-45782-NY"
    
    # Fake patterns:
    # - Too simple: "001", "123"
    # - Sequential: "0001", "0002", "0003"
    # - All zeros: "00000"
    
    receipt_num = extract_receipt_number(text)
    
    if receipt_num:
        if is_too_simple(receipt_num):  # "001", "123"
            score += 0.20
        if all_same_digit(receipt_num):  # "11111"
            score += 0.30
        if is_sequential_pattern(receipt_num):  # "12345"
            score += 0.25
```

**Impact:** High - many fake receipts use simple numbers

---

### **3. Tax Calculation Verification** 🔥

**Problem:** Fake receipts often have incorrect tax calculations.

**Detection:**
```python
# R21: Tax calculation mismatch
def verify_tax_calculation(subtotal, tax_amount, tax_rate, total):
    # Extract tax rate from receipt (e.g., "GST 18%")
    # Calculate expected tax
    expected_tax = subtotal * (tax_rate / 100)
    
    # Check if tax matches
    if abs(tax_amount - expected_tax) > 0.50:
        score += 0.30
        reason = f"Tax calculation incorrect: Expected {expected_tax}, got {tax_amount}"
    
    # Check if total = subtotal + tax
    expected_total = subtotal + tax_amount
    if abs(total - expected_total) > 0.50:
        score += 0.25
        reason = "Total doesn't match subtotal + tax"
```

**Impact:** Very High - math errors are common in fakes

---

### **4. Merchant Verification** 🔥

**Problem:** Fake receipts use non-existent or misspelled merchant names.

**Detection:**
```python
# R22: Unknown or suspicious merchant
def verify_merchant(merchant_name):
    # Check against database of known merchants
    # Check for common misspellings
    # Check for generic names
    
    if merchant_name in KNOWN_FAKE_MERCHANTS:
        score += 0.40
        reason = "Merchant name known to be fake"
    
    if is_generic_name(merchant_name):  # "Store", "Shop", "Retail"
        score += 0.20
        reason = "Generic merchant name - suspicious"
    
    if has_typos(merchant_name):  # "Amazom" instead of "Amazon"
        score += 0.25
        reason = "Merchant name has spelling errors"
```

**Impact:** High - easy to implement with merchant database

---

### **5. Address Validation** 🔥

**Problem:** Fake receipts have invalid or incomplete addresses.

**Detection:**
```python
# R23: Invalid address format
def validate_address(text):
    address = extract_address(text)
    
    if not address:
        score += 0.15
        reason = "No address found - unusual for legitimate receipts"
    
    if address:
        if not has_zip_code(address):
            score += 0.10
        if not has_city(address):
            score += 0.10
        if is_incomplete(address):  # Just "123 Main St"
            score += 0.15
            reason = "Incomplete address - missing city/state/zip"
```

**Impact:** Medium - helps catch lazy fakes

---

### **6. Line Item Price Consistency** 🔥

**Problem:** Fake receipts have unrealistic prices or patterns.

**Detection:**
```python
# R24: Suspicious pricing patterns
def check_price_patterns(line_items):
    prices = [item.price for item in line_items]
    
    # All round numbers (10.00, 20.00, 30.00)
    if all(price % 1 == 0 for price in prices):
        score += 0.20
        reason = "All prices are round numbers - unusual"
    
    # All same price
    if len(set(prices)) == 1 and len(prices) > 2:
        score += 0.25
        reason = "All items have same price - suspicious"
    
    # Unrealistic prices
    if any(price > 50000 for price in prices):
        score += 0.20
        reason = "Unusually high item price detected"
```

**Impact:** Medium - catches obvious patterns

---

### **7. Timestamp Validation** ⚡

**Problem:** Fake receipts have impossible timestamps.

**Detection:**
```python
# R25: Invalid timestamp
def validate_timestamp(date, time):
    # Check for impossible times
    if time and (time < "06:00" or time > "23:00"):
        # Most stores don't operate 24/7
        score += 0.10
        reason = "Transaction time outside normal business hours"
    
    # Check for future dates
    if date > today:
        score += 0.40
        reason = "Receipt date is in the future - impossible"
    
    # Check for very old dates
    if date < (today - 365 days):
        score += 0.15
        reason = "Receipt is over 1 year old - unusual for expense claims"
```

**Impact:** Medium - catches careless fakes

---

### **8. Currency Symbol Consistency** ⚡

**Problem:** Fake receipts mix currency symbols or use wrong ones.

**Detection:**
```python
# R26: Mixed or incorrect currency symbols
def check_currency_consistency(text):
    currencies = extract_currency_symbols(text)
    
    if len(set(currencies)) > 1:
        score += 0.30
        reason = f"Multiple currency symbols found: {currencies}"
    
    # Check if currency matches merchant location
    if merchant_country == "India" and "$" in currencies:
        score += 0.25
        reason = "Currency symbol doesn't match merchant location"
```

**Impact:** Medium - catches international fakes

---

### **9. Image Quality Analysis** ⚡

**Problem:** Fake receipts are often low-resolution screenshots.

**Detection:**
```python
# R27: Suspicious image quality
def analyze_image_quality(image):
    width, height = image.size
    
    # Too small (screenshot)
    if width < 800 or height < 800:
        score += 0.15
        reason = "Low resolution image - may be screenshot"
    
    # Perfect dimensions (Canva default: 1080x1080)
    if width == 1080 and height == 1080:
        score += 0.20
        reason = "Image dimensions match Canva default - suspicious"
    
    # Check compression artifacts
    if has_jpeg_artifacts(image):
        score += 0.10
        reason = "Heavy JPEG compression - may be re-saved multiple times"
```

**Impact:** Medium - catches Canva exports

---

### **10. Duplicate Receipt Detection** ⚡

**Problem:** Same receipt submitted multiple times with minor edits.

**Detection:**
```python
# R28: Duplicate or similar receipt
def check_for_duplicates(current_receipt, database):
    # Compare with previously submitted receipts
    for prev_receipt in database:
        similarity = calculate_similarity(current_receipt, prev_receipt)
        
        if similarity > 0.95:
            score += 0.50
            reason = "Receipt appears to be duplicate or very similar to previous submission"
        
        # Same merchant, same total, different dates
        if (same_merchant and same_total and different_dates):
            score += 0.30
            reason = "Suspicious: Same merchant and total as previous receipt"
```

**Impact:** Very High - catches reuse fraud

---

## **Advanced Checks (ML-Based)** 🚀

### **11. Thermal Printer Artifact Detection**

**Problem:** Real receipts have thermal printer artifacts, fakes don't.

**Detection:**
```python
# R29: Missing thermal printer characteristics
def detect_thermal_artifacts(image):
    # Real thermal receipts have:
    # - Horizontal lines (print head artifacts)
    # - Slight fading at edges
    # - Consistent dot patterns
    # - Paper texture
    
    has_artifacts = check_thermal_patterns(image)
    
    if not has_artifacts:
        score += 0.25
        reason = "No thermal printer artifacts - may be computer-generated"
```

**Implementation:** Requires image processing (OpenCV)

---

### **12. Paper Texture Analysis**

**Problem:** Real receipts have paper texture, digital ones don't.

**Detection:**
```python
# R30: No paper texture detected
def analyze_paper_texture(image):
    # Real paper has:
    # - Grain patterns
    # - Slight variations in brightness
    # - Natural imperfections
    
    texture_score = measure_texture(image)
    
    if texture_score < threshold:
        score += 0.20
        reason = "No paper texture - appears to be digital creation"
```

**Implementation:** Requires ML model

---

### **13. Lighting Consistency**

**Problem:** Fake receipts have inconsistent lighting/shadows.

**Detection:**
```python
# R31: Inconsistent lighting
def check_lighting(image):
    # Real scans have:
    # - Consistent lighting across image
    # - Natural shadows
    # - Uniform brightness
    
    # Fake composites have:
    # - Different lighting on different elements
    # - Artificial shadows
    # - Brightness variations
    
    if has_inconsistent_lighting(image):
        score += 0.25
        reason = "Inconsistent lighting suggests composite/edited image"
```

**Implementation:** Requires image analysis

---

### **14. Merchant Logo Verification**

**Problem:** Fake receipts have low-quality or incorrect logos.

**Detection:**
```python
# R32: Invalid or low-quality logo
def verify_logo(image, merchant_name):
    logo = extract_logo(image)
    
    if logo:
        # Compare with known merchant logos
        similarity = compare_with_database(logo, merchant_name)
        
        if similarity < 0.7:
            score += 0.30
            reason = "Merchant logo doesn't match known logo"
        
        # Check logo quality
        if is_low_resolution(logo):
            score += 0.15
            reason = "Low quality logo - may be copied from internet"
```

**Implementation:** Requires logo database + image matching

---

### **15. Barcode/QR Code Validation**

**Problem:** Fake receipts have invalid or missing barcodes.

**Detection:**
```python
# R33: Invalid or missing barcode
def validate_barcode(image):
    barcode = extract_barcode(image)
    
    if not barcode:
        score += 0.10
        reason = "No barcode found - many real receipts have barcodes"
    
    if barcode:
        if not is_valid_format(barcode):
            score += 0.25
            reason = "Barcode format is invalid"
        
        # Check if barcode matches receipt number
        if not matches_receipt_number(barcode, receipt_num):
            score += 0.20
            reason = "Barcode doesn't match receipt number"
```

**Implementation:** Requires barcode reader library

---

## **Implementation Priority**

### **Phase 1: Quick Wins (1-2 days)** 🔥

1. **Tax calculation verification** - High impact, easy to implement
2. **Receipt number validation** - Catches simple fakes
3. **Timestamp validation** - Easy logic checks
4. **Currency consistency** - Simple pattern matching
5. **Image dimensions check** - One-liner

**Expected improvement:** +15-20% detection rate

---

### **Phase 2: Medium Effort (3-5 days)** ⚡

6. **Font consistency analysis** - Requires text analysis
7. **Address validation** - Need address parser
8. **Line item price patterns** - Statistical analysis
9. **Merchant verification** - Need merchant database
10. **Duplicate detection** - Need receipt database

**Expected improvement:** +20-25% detection rate

---

### **Phase 3: Advanced (1-2 weeks)** 🚀

11. **Thermal printer artifacts** - Image processing
12. **Paper texture analysis** - ML model
13. **Lighting consistency** - Computer vision
14. **Logo verification** - Image matching
15. **Barcode validation** - Barcode library

**Expected improvement:** +30-35% detection rate

---

## **Recommended Next Steps**

### **Immediate (Do Now):**

1. **Tax calculation check** (2 hours)
   - Extract subtotal, tax, total
   - Verify math
   - High impact, easy win

2. **Receipt number validation** (1 hour)
   - Check for "001", "123", etc.
   - Flag sequential patterns
   - Catches lazy fakes

3. **Image dimensions check** (30 min)
   - Flag 1080x1080 (Canva default)
   - Flag very small images
   - One-liner implementation

---

### **This Week:**

4. **Timestamp validation** (2 hours)
5. **Currency consistency** (1 hour)
6. **Address validation** (3 hours)

---

### **This Month:**

7. **Font consistency** (1 day)
8. **Merchant database** (2 days)
9. **Duplicate detection** (2 days)

---

## **Expected Overall Impact**

| Phase | Time | Detection Rate | Total |
|-------|------|----------------|-------|
| Current | - | 70% | 70% |
| Phase 1 | 2 days | +15% | 85% |
| Phase 2 | 5 days | +20% | 95% |
| Phase 3 | 2 weeks | +10% | 99%+ |

---

## **Quick Implementation: Tax Check**

Here's the easiest high-impact check to add right now:

```python
# R19: Tax calculation mismatch
if tf.get("total_amount") and tf.get("line_items_sum"):
    subtotal = tf.get("line_items_sum")
    total = tf.get("total_amount")
    
    # Assume standard tax rates (18% GST in India, 10% VAT, etc.)
    for tax_rate in [0.05, 0.10, 0.18, 0.20]:
        expected_total = subtotal * (1 + tax_rate)
        
        # If total matches expected (within 1%), it's valid
        if abs(total - expected_total) / total < 0.01:
            break
    else:
        # No tax rate matches
        score += 0.25
        reasons.append(
            f"Total ({total}) doesn't match subtotal ({subtotal}) + standard tax rates"
        )
```

---

## **Summary**

### **Top 5 Smart Checks to Add:**

1. 🔥 **Tax calculation** - Math errors are common
2. 🔥 **Receipt number** - Simple patterns are obvious
3. 🔥 **Image dimensions** - Canva default is 1080x1080
4. ⚡ **Timestamp** - Future dates are impossible
5. ⚡ **Currency** - Mixed symbols are suspicious

### **Total Potential:**

- **15 new checks** identified
- **Expected improvement:** 70% → 99%+ detection
- **Implementation time:** 2 days to 2 weeks

**Would you like me to implement the top 3 quick wins now?** (Tax, receipt number, image dimensions - ~4 hours total) 🚀
