# Hardening Round 4 - Zaffran False Positive Fix

## Overview

Fixed Zaffran false positive (0.555 → 0.218, -60.7%) by addressing **extraction artifacts** that were being misinterpreted as fraud signals.

---

## Problem Analysis

### Zaffran Receipt - Before Fixes

```
🎯 DECISION: fake (score: 0.5550)

Contributing factors:
1. GEO_CURRENCY_MISMATCH: 0.30 (CRITICAL) ❌
   - country: "EU"
   - currency_detected: "GBP"
   - expected: ["EUR"]
   - Reality: Mumbai, India receipt with INR amounts

2. R9B_DOC_TYPE_UNKNOWN: 0.105 (CRITICAL) ❌
   - Doc confidence: 0.55
   - Structural signals: 1
   - Reality: OCR quality issue, not fraud

3. spacing_anomaly (learned rule): +0.15 ❌
   - applied_to_score: true
   - Reality: Thermal POS receipt with normal spacing
```

**Root cause:** Bad OCR extraction → wrong geo/currency signals → cascading penalties for extraction artifacts, not genuine fraud.

---

## Fixes Implemented

### Fix #1: Gate GEO_CURRENCY_MISMATCH ✅

**Problem:** Rule fired CRITICAL penalty even when geo confidence was 0.0 (unknown).

**Solution:** Only apply CRITICAL penalty when `geo_confidence >= 0.6`

**File:** `app/pipelines/rules.py:1257-1290, 1360-1385`

```python
# Get geo confidence from text_features (if available)
geo_confidence = tf.get("geo_confidence", 0.0) if tf else 0.0

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
        evidence={
            "country": country,
            "currency_detected": currency,
            "expected_currencies": sorted(list(expected_currencies)),
            "geo_confidence": geo_confidence,
            "gated": geo_confidence < 0.6,  # Shows if penalty was suppressed
        }
    )
```

**Impact:**
- Zaffran: geo_confidence = 0.0 → GEO_CURRENCY_MISMATCH downgraded to INFO (0.00 weight)
- Cross-border receipts: Multiple geo candidates detected → no penalty
- Legitimate receipts with poor OCR: No false geo penalties

---

### Fix #2: Suppress spacing_anomaly When Doc Confidence Low ✅

**Problem:** `spacing_anomaly` learned rule applied +0.15 penalty even when:
- Missing-field gate was disabled (low doc confidence)
- Doc confidence < 0.6 (likely OCR issue)

**Solution:** Suppress `spacing_anomaly` when extraction quality is poor

**File:** `app/pipelines/rules.py:2111-2136`

```python
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
```

**Logic:**
1. If `missing_fields_enabled == False` → suppress (low doc confidence)
2. If `doc_profile_confidence < 0.6` → suppress (uncertain extraction)
3. If POS receipt with >50% uppercase lines → suppress (normal for thermal prints)

**Impact:**
- Zaffran: spacing_anomaly suppressed (doc confidence 0.55 < 0.6)
- Poor OCR receipts: No false spacing penalties
- Thermal POS receipts: Normal uppercase formatting not penalized

---

### Fix #3: Vision LLM Import Fixed ✅

**Problem:** Vision fallback never ran because import failed:
```
Vision LLM not available for OCR fallback: cannot import name 'extract_receipt_data'
```

**Root cause:** Function name mismatch
- `vision_llm.py` exports: `extract_receipt_data_with_vision`
- `ocr_fallback.py` tried to import: `extract_receipt_data`

**Solution:** Fix import to use correct function names

**File:** `app/pipelines/ocr_fallback.py:16-31`

```python
# Import vision LLM if available
try:
    from app.pipelines.vision_llm import (
        query_vision_model,
        extract_receipt_data_with_vision,  # ✅ Correct name
        detect_fraud_indicators_with_vision,
        build_vision_assessment
    )
    HAS_VISION_LLM = True
    logger.info("✅ Vision LLM successfully imported and available")
except ImportError as e:
    HAS_VISION_LLM = False
    logger.warning(f"Vision LLM not available for OCR fallback: {e}")
    logger.debug(f"ImportError details: {type(e).__name__}: {str(e)}")
except Exception as e:
    HAS_VISION_LLM = False
    logger.error(f"Unexpected error importing vision_llm: {type(e).__name__}: {str(e)}")
```

**Verification:**
```bash
python -c "from app.pipelines.ocr_fallback import HAS_VISION_LLM; print(f'HAS_VISION_LLM: {HAS_VISION_LLM}')"
# Output: HAS_VISION_LLM: True ✅
```

**Impact:**
- Vision LLM now successfully imports
- Fallback available for low OCR confidence receipts
- Better logging shows exact import errors

---

## Test Results - Zaffran Receipt

### Before Fixes
```
🎯 DECISION: fake (score: 0.5550)

Events:
- GEO_CURRENCY_MISMATCH [CRITICAL]: 0.30
  - country: "EU"
  - currency: "GBP"
  - geo_confidence: 0.0 (unknown)
  
- R9B_DOC_TYPE_UNKNOWN [CRITICAL]: 0.105
  - doc_confidence: 0.55
  
- spacing_anomaly [learned rule]: +0.15
  - applied_to_score: true
```

### After Fixes
```
🎯 DECISION: real (score: 0.2180)

Events:
- GEO_CROSS_BORDER_HINTS [INFO]: 0.00 ✅
  - geo_candidates: ["CA", "IN", "EU", "AU", "SG"]
  - Multiple regions detected → cross-border mode
  
- R9B_DOC_TYPE_UNKNOWN [WARNING]: 0.068 ✅
  - Downgraded from CRITICAL
  - Structural signals present
  
- spacing_anomaly [learned rule]: 0.00 ✅
  - suppressed: true
  - doc_confidence: 0.55 < 0.6
```

### Score Breakdown

| Component | Before | After | Change |
|-----------|--------|-------|--------|
| **GEO_CURRENCY_MISMATCH** | 0.300 | 0.000 | -100% ✅ |
| **spacing_anomaly** | 0.150 | 0.000 | -100% ✅ |
| **R9B_DOC_TYPE_UNKNOWN** | 0.105 | 0.068 | -35% ✅ |
| **Total Score** | 0.555 | 0.218 | **-60.7%** ✅ |
| **Decision** | fake | real | ✅ Fixed |

---

## Key Insights

### 1. Extraction Artifacts vs Fraud Signals

**Problem:** Poor OCR creates cascading false positives
- Bad merchant extraction → low doc confidence
- Bad currency detection → geo mismatch penalty
- Bad spacing extraction → spacing anomaly penalty

**Solution:** Gate penalties based on extraction confidence
- If geo_confidence < 0.6 → don't penalize geo/currency mismatch
- If doc_confidence < 0.6 → don't penalize spacing anomalies
- If multiple geo candidates → cross-border mode (no penalty)

### 2. Confidence-Aware Penalty Policy

**Old policy:** Apply penalties regardless of extraction quality
**New policy:** Only apply penalties when confident in extraction

```python
# Pattern:
if signal_detected and confidence_in_detection >= threshold:
    apply_penalty()
else:
    downgrade_to_info()  # Audit only, no score impact
```

### 3. Cross-Border Detection

When multiple geo regions detected, treat as legitimate cross-border receipt:
- No geo/currency mismatch penalties
- No tax regime penalties
- INFO event for audit trail

---

## Files Modified

### 1. `app/pipelines/rules.py`
**Lines 1257-1290:** Gate legacy GEO_CURRENCY_MISMATCH
- Add geo_confidence extraction
- Only CRITICAL if geo_confidence >= 0.6
- Add gated flag to evidence

**Lines 1360-1385:** Gate DB-backed GEO_CURRENCY_MISMATCH
- Same gating logic for DB-backed path
- Add geo_confidence to evidence

**Lines 2111-2136:** Suppress spacing_anomaly when doc confidence low
- Check missing_fields_enabled
- Check doc_profile_confidence < 0.6
- POS-specific uppercase ratio check

### 2. `app/pipelines/ocr_fallback.py`
**Lines 16-31:** Fix vision_llm import
- Import correct function names
- Add detailed error logging
- Verify HAS_VISION_LLM flag

---

## Impact Summary

### Zaffran Receipt (Primary Test Case)
- **Score:** 0.555 → 0.218 (-60.7%)
- **Decision:** fake → real ✅
- **False positive eliminated**

### General Improvements
1. **Geo/currency penalties** now confidence-aware
2. **Spacing anomalies** suppressed for poor OCR
3. **Vision fallback** properly wired and available
4. **Cross-border receipts** handled correctly

### No Regressions
- Popeyes fake receipt still detected (date conflict, watermark)
- Shell receipts still pass (legitimate POS)
- All previous hardening fixes still active

---

## Testing Commands

```bash
# Test Zaffran (was false positive)
python scripts/show_evidence.py data/raw/Zaffran.jpg

# Test Popeyes (should still be fake)
python scripts/show_evidence.py data/raw/Popeyes-download.png

# Test Shell receipts (should still be real)
python scripts/show_evidence.py "data/raw/Shell Auto.jpg"
python scripts/show_evidence.py "data/raw/Shell Auto1.jpg"

# Verify vision LLM import
python -c "from app.pipelines.ocr_fallback import HAS_VISION_LLM; print(f'HAS_VISION_LLM: {HAS_VISION_LLM}')"
```

---

## Summary

**3 fixes implemented:**
1. ✅ GEO_CURRENCY_MISMATCH gating (geo_confidence >= 0.6)
2. ✅ spacing_anomaly suppression (doc_confidence < 0.6)
3. ✅ Vision LLM import fixed

**Result:** Zaffran false positive eliminated (0.555 → 0.218, -60.7%)

**Philosophy:** Don't penalize extraction artifacts. Only penalize high-confidence fraud signals.

**Total hardening rounds:** 4
**Total fixes:** 19 ✅
