# Spacing Anomaly Detection - Analysis & Solutions

## Problem Statement

User identified **visual spacing anomalies** in PDF receipts:
```
Example text in PDF:
"DESCRIPTION          TOTAL(AUD)
 300,000
 Digital Campaign Annual Fee"
```

Excessive spaces between words are visible to human eye but not detected by the system.

---

## Root Cause Analysis

### Why Spacing Detection Failed

1. **OCR Normalization**
   - Tesseract/EasyOCR **normalize whitespace** during text extraction
   - Multiple spaces → Single space
   - Example: `"TOTAL     300,000"` becomes `"TOTAL 300,000"`
   - Our R14b spacing detection rule can't see original spacing

2. **PDF Text Extraction Normalization**
   - PyPDF2 also normalizes spacing in text content
   - PDF stores text as positioned elements, not sequential text
   - Text extraction reorders and normalizes spacing

3. **Visual vs. Content Spacing**
   - The spacing is a **rendering artifact** in the PDF
   - Text content: `"TOTAL 300,000"` (normal)
   - Visual rendering: `"TOTAL          300,000"` (excessive gaps)
   - Created by manual text positioning in PDF editors

4. **Vision LLM Limitations**
   - llama3.2-vision tends to be "helpful" and overlook subtle issues
   - Trained to say receipts look "real" unless obvious artifacts
   - Not sensitive enough to spacing anomalies
   - May need more explicit prompting or different model

---

## Solutions Implemented

### ✅ Solution 1: OCR-Based Spacing Detection (R14b)
**File:** `app/pipelines/features.py`, `app/pipelines/rules.py`

**Implementation:**
- `_detect_spacing_anomalies()` function analyzes raw OCR text
- Detects consecutive spaces (3+)
- Calculates spacing variance
- Flags excessive/inconsistent spacing

**Limitation:** Only works if OCR preserves spacing (rare)

**Status:** Implemented but ineffective for this PDF type

---

### ✅ Solution 2: Vision LLM Enhancement
**File:** `app/pipelines/vision_llm.py`

**Implementation:**
- Enhanced fraud detection prompt
- Prioritized spacing anomalies as #1 detection target
- Added explicit instructions to look for spacing issues
- Added `spacing_issues` field to JSON response

**Limitation:** Vision LLM still not detecting spacing in this case

**Status:** Implemented but needs more aggressive prompting or different model

---

### ✅ Solution 3: Text Layout Anomaly Detection (R14c)
**File:** `app/pipelines/rules.py`

**Implementation:**
- Detects text fragmentation patterns
- Checks average line length
- Short lines (<15 chars) with many lines → manual text placement
- Indicates PDF editor usage

**Detection:**
```python
avg_line_length = sum(len(line) for line in lines) / num_lines
if avg_line_length < 15 and num_lines > 10:
    # Text was manually placed in PDF editor
    score += 0.15
```

**Status:** Implemented, may catch some cases

---

## Current Detection Stack

### Layer 1: Rule-Based (iLovePDF Detection)
✅ **Working** - Detects suspicious software
- Score: +0.30 for iLovePDF
- This is the PRIMARY indicator currently working

### Layer 2: OCR Spacing Analysis (R14b)
❌ **Not Working** - OCR normalizes spacing
- Would add +0.20 if spacing detected
- Requires raw OCR text with preserved spacing

### Layer 3: Vision LLM Spacing Detection
❌ **Not Working** - Model not sensitive enough
- Would flag in fraud_indicators
- Needs more aggressive prompting or different model

### Layer 4: Text Layout Analysis (R14c)
⚠️ **Partially Working** - Detects fragmentation
- Adds +0.15 for short average line length
- Secondary indicator

---

## Why Current Verdict is "Real" (80%)

**Current Scores:**
- Rule-Based: 45% suspicious (iLovePDF detected)
- Vision LLM: 100% real (no spacing detected)
- LayoutLM: Extracted data successfully
- Ensemble: Weighted average → 80% real

**The Problem:**
- Only 1 engine (Rule-Based) detects fraud
- Vision LLM strongly says "real" (100% confidence)
- Ensemble trusts Vision LLM heavily
- Result: Overall verdict is "real" despite iLovePDF detection

---

## Recommended Solutions

### Option 1: Increase Rule-Based Weight in Ensemble ✅ **EASIEST**
**Change:** Increase iLovePDF detection score
```python
# Current
if suspicious_producer:
    score += 0.30  # 30%

# Proposed
if suspicious_producer:
    score += 0.50  # 50% - makes it "fake" threshold
```

**Impact:** Rule-Based verdict becomes "fake" instead of "suspicious"
**Ensemble:** Will weight "fake" verdict more heavily

---

### Option 2: Add PDF Structure Analysis 🔧 **MEDIUM**
**Approach:** Analyze PDF internal structure
- Check for text positioning commands
- Detect manual text placement
- Analyze font changes and positioning

**Tools:** PyPDF2, pdfplumber
**Complexity:** Medium - requires PDF parsing expertise

---

### Option 3: Use Different Vision Model 🤖 **HARD**
**Options:**
- GPT-4 Vision (paid API)
- Claude 3 Vision (paid API)
- Qwen2-VL (local, larger model)

**Benefit:** Better spacing detection
**Cost:** API costs or larger model requirements

---

### Option 4: Hybrid Approach - PDF Rendering Analysis 🎨 **ADVANCED**
**Approach:**
1. Render PDF to high-res image
2. Analyze pixel-level spacing between text
3. Compare with expected spacing for font size
4. Flag abnormal gaps

**Tools:** pdf2image + OpenCV
**Complexity:** High - requires computer vision expertise

---

## Immediate Action Items

### ✅ Completed
1. PDF-to-image conversion for LayoutLM/Vision
2. OCR-based spacing detection (R14b)
3. Vision LLM prompt enhancement
4. Text layout anomaly detection (R14c)

### 🎯 Recommended Next Steps

**Quick Win (5 minutes):**
1. Increase iLovePDF detection score from 0.30 → 0.50
2. This will make Rule-Based verdict "fake" instead of "suspicious"
3. Ensemble will then likely return "fake" verdict

**Medium Term (1-2 hours):**
1. Add PDF structure analysis
2. Detect text positioning commands
3. Flag manual text placement patterns

**Long Term (1-2 days):**
1. Implement pixel-level spacing analysis
2. Or integrate better Vision model (GPT-4V/Claude)
3. Build comprehensive PDF forensics

---

## Test Results Summary

**PDF Tested:** BrandPulse Marketing invoice (iLovePDF generated)

**Detections:**
- ✅ iLovePDF software detected (Rule-Based)
- ✅ Invalid phone number (Rule-Based)
- ✅ LayoutLM extracted data successfully
- ❌ Spacing anomalies NOT detected (OCR normalized)
- ❌ Vision LLM said "real" (not sensitive to spacing)

**Current Verdict:** Real (80%) - **INCORRECT**
**Expected Verdict:** Fake (70-90%) - based on iLovePDF + spacing

**Gap:** Vision LLM confidence (100% real) overrides Rule-Based detection

---

## Conclusion

The spacing detection challenge is **fundamentally difficult** because:
1. OCR normalizes whitespace
2. PDF text extraction normalizes spacing
3. Spacing is a visual rendering artifact
4. Vision LLMs aren't trained to detect subtle spacing issues

**Best Current Solution:**
- Increase Rule-Based scoring for iLovePDF detection
- This makes the verdict "fake" based on software detection alone
- Spacing detection remains a secondary/future enhancement

**The iLovePDF detection is actually the STRONGEST signal** - it directly indicates the receipt was created in a PDF editor, which is highly suspicious for receipts.
