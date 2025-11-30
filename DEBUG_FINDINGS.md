# Debug Findings - Why Fake Receipts Not Detected

## **File 1: Apple Macbook mouse monitor.pdf**

### **Issue 1: Date Extraction Failed** ❌

**OCR Text Contains:**
```
Receipt date: Nov 14, 2025
```

**But Extracted:**
```
has_date: False
receipt_date: None
```

**Why?** The date regex doesn't match "Nov 14, 2025" format!

**Current regex patterns don't include:**
- "Nov 14, 2025" (Month abbreviation + day + year)
- "14 Nov 2025" (Day + month abbreviation + year)

**Fix Needed:** Add more date patterns to `_DATE_REGEXES`

---

### **Issue 2: TCPDF Not in Suspicious List** ❌

**Metadata Shows:**
```
Producer: TCPDF 6.10.1 (http://www.tcpdf.org)
Creator: TCPDF
Title: Conta.com - Invoice
```

**TCPDF** is a PHP library for generating PDFs - commonly used for fake invoices!

**Current suspicious list:**
```python
SUSPICIOUS_PRODUCERS = {
    "canva", "photoshop", "wps", "fotor",
    "ilovepdf", "sejda", "smallpdf", ...
}
```

**Missing:** TCPDF, Conta.com, and other invoice generators

**Fix Needed:** Add TCPDF and invoice generators to suspicious list

---

### **Issue 3: Date Mismatch Not Detected** ❌

**Actual Dates:**
- Creation Date: Nov 30, 2025 (08:22:31)
- Receipt Date: Nov 14, 2025

**Difference:** 16 days!

**Why Not Detected:**
1. Receipt date not extracted (regex issue)
2. Even if extracted, creation date format not parsed correctly

**Creation date format:** `D:20251130082231+00'00'` (PDF date format)

**Fix Needed:** Parse PDF date format properly

---

## **File 2: C Test2.jpg (Canva)**

### **Issue 1: No Metadata at All** ❌

**Extracted:**
```
Producer: None
Creator: None
Software: None
EXIF Present: True (but only 6 keys)
```

**Why?** Canva exports strip metadata!

When you export from Canva as JPG, it removes:
- Software field
- Creator field
- All identifying information

**Fix Needed:** Visual analysis (can't rely on metadata)

---

### **Issue 2: OCR Quality Poor** ❌

**OCR Output:**
```
Dats) cc59019
Cit09. te 5518
Stone Ravert PlC.12
```

**Should be:**
```
Date: 05/09/19
City: ...
Store Name: ...
```

**Why?** Low quality image or poor OCR

**Fix Needed:** Better OCR or image preprocessing

---

## **Root Causes Summary**

| Issue | File 1 (PDF) | File 2 (JPG) | Fix Priority |
|-------|--------------|--------------|--------------|
| Date regex incomplete | ❌ | ❌ | 🔥 HIGH |
| TCPDF not suspicious | ❌ | N/A | 🔥 HIGH |
| PDF date format | ❌ | N/A | 🔥 HIGH |
| Metadata stripped | N/A | ❌ | ⚡ MEDIUM |
| OCR quality | ✅ | ❌ | ⚡ MEDIUM |

---

## **Fixes Needed**

### **Fix 1: Add More Date Patterns** 🔥

```python
# In app/pipelines/features.py

_DATE_REGEXES = [
    # Existing patterns...
    
    # ADD THESE:
    re.compile(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b', re.I),
    # Matches: Nov 14, 2025 or Nov 14 2025
    
    re.compile(r'\b\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b', re.I),
    # Matches: 14 Nov 2025
    
    re.compile(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b', re.I),
    # Matches: November 14, 2025
]
```

---

### **Fix 2: Add TCPDF and Invoice Generators** 🔥

```python
# In app/pipelines/features.py

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
    
    # ADD THESE:
    "tcpdf",           # PHP PDF generator
    "fpdf",            # Another PHP PDF library
    "conta.com",       # Invoice generator
    "invoice",         # Generic invoice tools
    "receipt maker",   # Receipt generators
    "fake receipt",    # Obviously fake
    "dompdf",          # PHP HTML to PDF
    "wkhtmltopdf",     # HTML to PDF converter
}
```

---

### **Fix 3: Parse PDF Date Format** 🔥

```python
# In app/pipelines/rules.py, R15 date mismatch rule

# ADD THIS PARSER:
def parse_pdf_date(date_str):
    """Parse PDF date format: D:20251130082231+00'00'"""
    if date_str.startswith('D:'):
        # Remove D: prefix and timezone
        date_part = date_str[2:10]  # YYYYMMDD
        return datetime.strptime(date_part, '%Y%m%d')
    return None

# Then in R15:
if isinstance(creation_date_raw, str):
    if creation_date_raw.startswith('D:'):
        creation_date = parse_pdf_date(creation_date_raw)
    else:
        # Try other formats...
```

---

### **Fix 4: Visual Analysis for Canva** ⚡

Since metadata is stripped, use visual cues:

```python
# New rules to add:

# R16: Perfect alignment (computer-generated)
if text_perfectly_aligned():
    score += 0.2
    reasons.append("Text is perfectly aligned - likely computer-generated")

# R17: Uniform font rendering
if all_fonts_identical():
    score += 0.2
    reasons.append("All text has identical rendering - not scanned")

# R18: Missing printer artifacts
if no_printer_artifacts():
    score += 0.15
    reasons.append("No printer imperfections - likely digital creation")
```

---

## **Expected Results After Fixes**

### **File 1: Apple Macbook PDF**

**Before:**
```
Label: REAL
Score: 0.200
Reasons: No valid date found
```

**After:**
```
Label: FAKE
Score: 0.55+
Reasons:
  • TCPDF producer detected - commonly used for fake invoices
  • File created 16 days after receipt date (Nov 14) - likely backdated
  • Conta.com invoice generator detected
```

---

### **File 2: C Test2.jpg (Canva)**

**Before:**
```
Label: SUSPICIOUS
Score: 0.350
Reasons: No total line, no date
```

**After:**
```
Label: FAKE
Score: 0.70+
Reasons:
  • No metadata present - likely stripped by editing software
  • Text perfectly aligned - computer-generated
  • No printer artifacts - not a real scan
  • Poor OCR quality - low resolution digital image
```

---

## **Implementation Order**

### **Phase 1: Critical (Do Now)** 🔥

1. **Add date patterns** (15 min)
   - Fix "Nov 14, 2025" format
   - Test with your PDF

2. **Add TCPDF to suspicious list** (5 min)
   - Add invoice generators
   - Test with your PDF

3. **Fix PDF date parsing** (15 min)
   - Parse D:YYYYMMDD format
   - Test date mismatch detection

**Total: 35 minutes, HIGH IMPACT**

---

### **Phase 2: Important (Next)** ⚡

4. **Add visual quality rules** (1-2 hours)
   - Perfect alignment detection
   - Uniform font check
   - Printer artifact check

5. **Improve OCR preprocessing** (1 hour)
   - Image enhancement
   - Better tesseract config

---

## **Quick Test After Fixes**

```bash
# Test File 1
python debug_receipt.py "data/raw/Apple Macbook  mouse monitor.pdf"

# Should show:
# ✅ Date extracted: 2025-11-14
# ✅ TCPDF flagged as suspicious
# ✅ Date mismatch: 16 days
# ✅ Final verdict: FAKE

# Test File 2
python debug_receipt.py "data/raw/C Test2.jpg"

# Should show:
# ✅ No metadata (suspicious)
# ✅ Visual quality issues detected
# ✅ Final verdict: FAKE
```

---

## **Summary**

### **Why Detection Failed:**

1. **Date regex incomplete** - Doesn't match "Nov 14, 2025"
2. **TCPDF not flagged** - Common fake invoice generator
3. **PDF date format** - Not parsed correctly
4. **Metadata stripped** - Canva exports remove all traces
5. **No visual analysis** - Can't detect computer-generated look

### **Quick Wins:**

- ✅ Add 3 date patterns (15 min)
- ✅ Add TCPDF to list (5 min)
- ✅ Fix PDF date parser (15 min)

**Total: 35 minutes to catch both your test cases!**

---

**Would you like me to implement these fixes now?** 🚀
