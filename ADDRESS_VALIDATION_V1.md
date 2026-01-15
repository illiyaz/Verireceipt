# Address Validation V1 - Geo-Agnostic Structure Validation

**Date:** 2026-01-15  
**Status:** 🟢 COMPLETE

---

## 🎯 Design Principles

### ✅ What We DO
- **Validate structure, not correctness** - Check if text looks like an address
- **Country-agnostic by default** - Universal patterns that work globally
- **Use patterns that generalize** - Street, unit, locality, postal tokens
- **Gate strict logic on confidence** - Only apply when doc_profile_confidence >= 0.55

### ❌ What We DON'T Do (V1)
- ❌ No India-only assumptions
- ❌ No postal DB lookups
- ❌ No "this address exists" checks
- ❌ No heavy regex per country

**This keeps false positives extremely low.**

---

## 📊 Address Validation Rubric

### **Signal Types & Weights**

| Component | Examples | Weight |
|-----------|----------|--------|
| **Street indicator** | street, st, road, rd, ave, blvd, lane, ln | +2 |
| **Building/unit** | apt, suite, unit, floor, fl, # | +1 |
| **City/locality tokens** | Alphabetic words >3 chars | +1 to +2 |
| **Postal-like token** | Alphanumeric 4-8 chars | +1 |
| **Country/state word** | Explicit location mention | +2 |

⚠️ **Postal code is weak, never decisive.**

---

### **Confidence Gates**

| Score | Classification |
|-------|---------------|
| < 3 | `NOT_AN_ADDRESS` |
| 3 | `WEAK_ADDRESS` |
| 4-5 | `PLAUSIBLE_ADDRESS` |
| ≥ 6 | `STRONG_ADDRESS` |

---

## 🧪 Example Outcomes

| Input | Result |
|-------|--------|
| `"123 Main St"` | `WEAK_ADDRESS` (score: 3) |
| `"123 Main St, Springfield"` | `PLAUSIBLE_ADDRESS` (score: 4) |
| `"Suite 402, 221B Baker Street, London"` | `STRONG_ADDRESS` (score: 6) |
| `"Total: $45.00"` | `NOT_AN_ADDRESS` (score: 0) |
| `"560001"` | `NOT_AN_ADDRESS` (score: 0) |

---

## 🧩 Pipeline Integration

### **Placement**
```
OCR → text_features
     → address_validation   ← NEW
     → geo_detection
     → rules
```

### **Output**
```python
text_features["address_profile"] = {
    "address_score": 4,
    "address_classification": "PLAUSIBLE_ADDRESS",
    "address_evidence": ["street_keyword:st", "locality_tokens", "postal_like_token"]
}

doc_profile["has_address"] = (
    address_profile["address_classification"] in {"PLAUSIBLE_ADDRESS", "STRONG_ADDRESS"}
    if doc_profile_confidence >= 0.55 else None
)
```

---

## 📁 Files Created

### **1. `app/address/validate.py`**
Core validation logic with universal patterns:
- `validate_address(text)` - Main entry point
- `_classify(score)` - Score to classification mapping
- `_empty_result()` - Empty result for invalid input

### **2. `app/address/__init__.py`**
Module exports

### **3. `tests/test_address_validation.py`**
Comprehensive golden tests:
- ✅ 19 tests covering all classifications
- ✅ International addresses (US, UK, India)
- ✅ Edge cases (empty, short, postal-only)
- ✅ Real-world scenarios (receipts, invoices)

### **4. `app/pipelines/features.py`** (Modified)
Integration points:
- Call `validate_address(full_text)` after merchant extraction
- Add `address_profile` to `text_features`
- Add `has_address` to `doc_profile` (gated by confidence >= 0.55)

---

## 🛡️ Safety Guarantees

1. ✅ **Not India-centric** - Works globally
2. ✅ **No geo guessing** - Pure structure validation
3. ✅ **No postal assumptions** - Postal codes are weak signals
4. ✅ **Extremely low false positives** - Conservative scoring
5. ✅ **Confidence gating** - Only affects rules when doc_profile_confidence >= 0.55

---

## 📊 Test Results

```bash
python -m pytest tests/test_address_validation.py -v
```

**Result:** ✅ **19/19 tests passing**

### **Test Coverage**
- ✅ NOT_AN_ADDRESS: Total amounts, short text, postal-only
- ✅ WEAK_ADDRESS: Street with number only
- ✅ PLAUSIBLE_ADDRESS: Street + city, street + unit
- ✅ STRONG_ADDRESS: Complete addresses with all components
- ✅ International: UK, India, US addresses
- ✅ Edge cases: Empty, None, PO Box

---

## 🚀 Next Steps (V2)

Once V1 lands cleanly:
1. **Address vs Merchant mismatch** - Detect when address doesn't match merchant
2. **Multiple address detection** - Flag receipts with multiple addresses
3. **Address missing gating** - Only penalize missing address for invoices
4. **Country-aware enrichment** - Optional geo-specific validation (gated)

---

## 🧠 Key Insights

### **Why Structure Over Correctness?**
- ✅ Structure is universal (street, city, postal)
- ✅ Correctness requires external DBs (expensive, error-prone)
- ✅ False positives are worse than false negatives for fraud detection

### **Why Conservative Scoring?**
- ✅ Better to miss an address than flag valid receipts
- ✅ Confidence gating prevents over-penalization
- ✅ Can always add more signals later without breaking existing logic

### **Why Geo-Agnostic?**
- ✅ Avoids India-specific bias
- ✅ Works for all countries immediately
- ✅ Can add country-specific enrichment later (gated)

---

**Address validation V1 complete. Ready for integration into rules engine.** 🎯
