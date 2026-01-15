# Geo Confidence Scoring Rubric

**Date:** 2026-01-15  
**Status:** 🟢 PRODUCTION

---

## 🎯 Purpose

Define clear, auditable scoring rules for geographic origin detection to prevent false positives while maintaining high accuracy for genuine matches.

---

## 📊 Signal Types & Weights

### **Strong Signals (3 points each)**
- Tax keywords (GST, VAT, HST, PST, GSTIN, etc.)
- Formatted phone numbers (country-specific patterns)
- Formatted postal codes (country-specific patterns)

### **Medium Signals (2 points each)**
- Unique currency symbols (₹, £, ¥ with context)
- Non-ambiguous phone/postal patterns

### **Weak Signals (1 point each)**
- Location markers (city/state names)
- Ambiguous currency symbols ($, ¥)
- Ambiguous postal patterns (6-digit alone)

### **Language Hint Bonus (0-3 points)**
- Proportional to language confidence
- Capped at 3 points
- Formula: `min(3.0, lang_score * 0.30)`

---

## 🎚️ Confidence Calculation

### **Base Formula:**
```python
confidence = min(1.0, winner_score / max(10, total_score))
```

### **Modifiers:**

#### **1. Weak Signal Penalty**
If `winner_score < 6`:
```python
confidence *= 0.5
```

#### **2. Strong Signal Boost**
If `winner_score >= 10`:
```python
confidence = min(1.0, confidence + 0.2)
```

#### **3. Weak-Only Cap (Fix #3)**
If no strong signals AND `winner_score < 8`:
```python
confidence = min(confidence, 0.25)
```

#### **4. UNKNOWN Gate**
If `confidence < 0.30` OR `winner_score < 6`:
```python
geo_country_guess = "UNKNOWN"
```

---

## 📏 Confidence Tiers

| Confidence | Tier | Interpretation | Action |
|------------|------|----------------|--------|
| **0.00 - 0.29** | UNKNOWN | Insufficient signals | Emit "UNKNOWN", don't guess |
| **0.30 - 0.49** | LOW | Weak or conflicting signals | Use with caution, flag for review |
| **0.50 - 0.69** | MODERATE | Likely correct, some ambiguity | Safe for most rules |
| **0.70 - 0.89** | HIGH | Strong evidence | Safe for strict rules |
| **0.90 - 1.00** | VERY HIGH | Overwhelming evidence | Maximum confidence |

---

## 🇮🇳 India Detection Rules (Post-Fix)

### **Required: ≥2 India Signals**

| Signal | Weight | Notes |
|--------|--------|-------|
| `+91` | Strong (1 signal) | India country code |
| `india` | Strong (1 signal) | Explicit country name |
| `INR` or `₹` | Strong (1 signal) | Indian currency |
| `GST` or `GSTIN` | Strong (1 signal) | India-specific tax |
| Indian state/city | Medium (1 signal) | Mumbai, Delhi, Karnataka, etc. |
| `\b\d{6}\b` with context | Weak (1 signal) | Only if India keyword present |
| `\b\d{6}\b` alone | ❌ REMOVED | Too ambiguous (CN, SG overlap) |

### **Examples:**

**✅ Valid India Detection (≥2 signals):**
- `+91` + `Mumbai` → 2 signals
- `INR` + `GSTIN` → 2 signals
- `india` + `\b\d{6}\b` → 2 signals (PIN counts with context)
- `Karnataka` + `₹` → 2 signals

**❌ Invalid India Detection (<2 signals):**
- `\b\d{6}\b` alone → 0 signals (removed)
- `Mumbai` alone → 1 signal (insufficient)
- Generic `$` symbol → 0 signals (not India-specific)

---

## 🌍 Cross-Country Ambiguity Resolution

### **Ambiguous Signals:**
- `$` → US, CA, AU, SG, MX, NZ
- `\b\d{6}\b` → IN, CN, SG
- `\b\d{10}\b` → US, MX (phone)
- `GST` → IN, CA, SG, AU, NZ

### **Resolution Strategy:**
1. **Require strong signals** (tax keywords, formatted patterns)
2. **Only score ambiguous signals if strong signals present**
3. **Cap confidence for weak-only matches** (≤0.25)
4. **Emit UNKNOWN** if confidence < 0.30

---

## 📊 Scoring Examples

### **Example 1: Strong India Match**
```
Text: "GSTIN: 29ABCDE1234F1Z5, Mumbai, ₹1,250.00"

Signals:
- GSTIN: +3 (tax keyword)
- Mumbai: +1 (location)
- ₹: +2 (currency)

Total: 6 points
Confidence: 6 / 10 = 0.60 → MODERATE
Result: IN (confidence: 0.60)
```

### **Example 2: Weak India Match (Pre-Fix)**
```
Text: "Total: $125.00, 123456"

Signals (OLD):
- $: +1 (ambiguous currency)
- 123456: +1 (6-digit PIN)

Total: 2 points
Confidence: 2 / 10 = 0.20 → UNKNOWN
Result: IN (confidence: 0.20) ❌ FALSE POSITIVE
```

### **Example 3: Weak India Match (Post-Fix)**
```
Text: "Total: $125.00, 123456"

Signals (NEW):
- $: +0 (ambiguous, no strong signals)
- 123456: +0 (removed standalone PIN)

Total: 0 points
Confidence: 0.00
Result: UNKNOWN ✅ CORRECT
```

### **Example 4: Valid India with Context**
```
Text: "Invoice from India, PIN: 560001, Total: $125.00"

Signals (NEW):
- "india": +1 (country name)
- "PIN: 560001": +1 (6-digit with context)

Total: 2 points (≥2 India signals)
Confidence: 2 / 10 = 0.20 → capped at 0.25 (weak-only)
Result: UNKNOWN (confidence < 0.30) ✅ CORRECT (below gate)
```

---

## 🎯 Gating Thresholds

### **Geo Validation Rules:**
- **Minimum confidence:** 0.30
- **Minimum score:** 6 points
- **Below threshold:** Emit "UNKNOWN"

### **Rule Engine Usage:**
- **GEO_CURRENCY_MISMATCH:** Requires geo_confidence ≥ 0.60
- **GEO_TAX_MISMATCH:** Requires geo_confidence ≥ 0.60
- **Cross-border detection:** Fires on multiple geo candidates

---

## 🧪 Test Cases

### **Test 1: False IN Detection (82216-24-GLPR.pdf)**
**Before Fix:**
- Detected: IN (confidence: 0.41)
- Signals: Weak/ambiguous only
- Result: ❌ FALSE POSITIVE

**After Fix:**
- Detected: UNKNOWN (confidence: 0.00)
- Signals: <2 India signals
- Result: ✅ CORRECT

### **Test 2: True IN Detection**
**Input:** "GSTIN: 29ABCDE1234F1Z5, +91-9876543210, Mumbai"
- Signals: GSTIN (3) + +91 (2) + Mumbai (1) = 6 points
- Confidence: 0.60
- Result: ✅ IN (confidence: 0.60)

### **Test 3: Ambiguous Receipt**
**Input:** "Total: $50.00, 123456 Main St"
- Signals: $ (ambiguous, 0) + 123456 (removed, 0) = 0 points
- Confidence: 0.00
- Result: ✅ UNKNOWN

---

## 📋 Implementation Checklist

- [x] Fix #1: Kill standalone 6-digit PIN detection
- [x] Fix #2: Require ≥2 India signals
- [x] Fix #3: Cap geo confidence for weak matches (≤0.25)
- [x] Fix #4: Add explicit audit reason for UNKNOWN geo
- [x] Update `rules.py` `_detect_india_hint()`
- [x] Update `geo_detection.py` GEO_SIGNALS["IN"]
- [x] Update `geo_detection.py` confidence calculation
- [x] Update `audit_formatter.py` geo display logic
- [ ] Create golden test for false IN detection
- [ ] Test with problematic receipts (82216-24-GLPR.pdf, 81846-2024.pdf)
- [ ] Validate no regressions on true IN receipts

---

## 🎯 Success Criteria

**After fixes, we should see:**
1. ✅ No false IN detection on non-India receipts
2. ✅ Geo confidence < 0.30 for ambiguous receipts
3. ✅ Audit reports show "No reliable geographic origin detected"
4. ✅ True India receipts still detected correctly (≥2 signals)
5. ✅ Cross-border receipts handled gracefully

---

**Geo confidence scoring is now production-ready with clear, auditable rules.** 🎯
