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

---

## 🔁 V2.1: Merchant ↔ Address Consistency (Feature-only)

**Date:** 2026-01-15  
**Status:** 🟢 COMPLETE

V2.1 introduces **semantic consistency checks** between extracted merchant identity and detected address.

### **Key Properties**
- ✅ **Geo-agnostic** - No country-specific assumptions
- ✅ **Confidence-gated** - Only runs when signals are strong enough
- ✅ **Non-verifying** - No "address exists" checks
- ✅ **Soft signals only** - Feature emission, no scoring impact

### **Output Format**

```json
"merchant_address_consistency": {
  "status": "CONSISTENT | WEAK_MISMATCH | MISMATCH | UNKNOWN",
  "score": 0.0 - 0.2,
  "evidence": ["merchant_token_overlap:acme", "address_type_mismatch:po_box_vs_corporate"]
}
```

### **Gating Conditions**

The consistency check returns `UNKNOWN` if any of these conditions are met:
- Merchant name is missing
- Merchant confidence < 0.6
- Address classification is not `PLAUSIBLE_ADDRESS` or `STRONG_ADDRESS`
- Doc profile confidence < 0.55

### **Consistency Signals**

#### **1. Token Overlap (Weak Signal, +0.1)**
- Extracts meaningful tokens from merchant name (excludes: ltd, llp, inc, corp, company, co, pvt, private, limited)
- Checks if any merchant tokens appear in address text
- Example: "Acme Logistics" + "123 Acme Street" → overlap detected

#### **2. Address Type Mismatch (Soft Signal, +0.2)**
- Detects if merchant is corporate (contains: ltd, llp, inc, corp, company, logistics, services, solutions, industries)
- Flags if corporate merchant has PO Box address
- Example: "Acme Logistics Ltd" + "P.O. Box 1234" → mismatch

### **Classification**

| Score | Status |
|-------|--------|
| 0.0 | `CONSISTENT` |
| ≤ 0.1 | `WEAK_MISMATCH` |
| > 0.1 | `MISMATCH` |

### **Usage in Pipeline**

```python
merchant_address_consistency = assess_merchant_address_consistency(
    merchant_name=merchant_candidate,
    merchant_confidence=0.8,
    address_profile=address_profile,
    doc_profile_confidence=doc_profile.get("confidence", 0.0),
)

text_features["merchant_address_consistency"] = merchant_address_consistency
```

### **Design Rationale**

**Why Feature-Only?**
- ✅ Allows learned rules to discover patterns organically
- ✅ Avoids premature penalization
- ✅ Can be tuned based on real-world data
- ✅ Safe to deploy without risk of false positives

**Why Confidence-Gated?**
- ✅ Only runs when we have strong signals
- ✅ Prevents noise from weak extractions
- ✅ Returns `UNKNOWN` instead of guessing

**Why Geo-Agnostic?**
- ✅ Works globally without country-specific rules
- ✅ Avoids bias toward any region
- ✅ Can add country-specific enrichment later (gated)

### **New Fields in V2.1**

#### **`address_profile` Extensions**
- `address_raw_text`: Original input text
- `address_type`: `STANDARD`, `PO_BOX`, or `UNKNOWN`

#### **`text_features` Addition**
- `merchant_address_consistency`: Full consistency assessment result

---

**This signal is designed to support learned rules and should not independently mark fraud.**

---

## 🧾 V2.2: Multi-Address Detection (Feature-only)

**Date:** 2026-01-16  
**Status:** 🟢 COMPLETE

V2.2 detects whether a document contains **multiple distinct address-like blocks**.

### **Key Properties**
- ✅ **Geo-agnostic** - Works globally without country-specific assumptions
- ✅ **Structure-only** - Detects address-like blocks, not correctness
- ✅ **Confidence-gated** - Returns `UNKNOWN` when doc profile confidence is low
- ✅ **Feature-only** - Emits signals for downstream learned rules (no scoring impact)

### **Gating Conditions**
Returns `UNKNOWN` if:
- `doc_profile_confidence < 0.55` 
- Text is too short / insufficient
- No plausible address candidates found

### **How It Works**
1. Builds candidate blocks from:
   - Paragraphs (split by blank lines)
   - Sliding windows of 2–4 lines
2. Runs `validate_address(block)` on each block
3. Keeps only `PLAUSIBLE_ADDRESS` / `STRONG_ADDRESS` candidates
4. Groups candidates using conservative distinctness heuristics:
   - Different postal-like tokens
   - Different address types (`PO_BOX` vs `STANDARD`)
   - Low locality token overlap

### **Output Format**
```json
"multi_address_profile": {
  "status": "SINGLE | MULTIPLE | UNKNOWN",
  "count": 0,
  "address_types": ["STANDARD", "PO_BOX"],
  "evidence": ["distinct_postal_tokens"]
}
```

### **Safety Guarantees**
- ❌ No fraud scoring impact
- ❌ No geo correctness claims
- ✅ Conservative to avoid false positives

---

## 🧠 V3: Learned Rule Consumption Examples

**Date:** 2026-01-16  
**Status:** 📖 DOCUMENTATION ONLY

V3 documents how learned rules should consume address-related signals safely.

### **Principle**

**No single address signal should independently mark a document as fraudulent.** Address signals are amplifiers, not decisive verdicts.

### **Example Patterns**

#### **Pattern A: Invoice Risk Amplifier (high-confidence docs only)**
Trigger when multiple weak indicators co-occur:
- `doc_subtype == INVOICE`
- `doc_profile_confidence >= 0.8`
- `multi_address_profile.status == MULTIPLE`
- `merchant_address_consistency.status in {WEAK_MISMATCH, MISMATCH}`

#### **Pattern B: Template / Editing Suspicion (tooling + structure)**
- `suspicious_pdf_producer == true`
- `multi_address_profile.status == MULTIPLE`
- `address_profile.address_classification in {PLAUSIBLE_ADDRESS, STRONG_ADDRESS}`

#### **Pattern C: Suppression for Low-Confidence Docs**
- If `doc_profile_confidence < 0.55`, address-derived learned rules should be suppressed or downgraded.

### **Design Rationale**

**Why Feature-Only?**
- ✅ Allows learned rules to discover patterns organically
- ✅ Avoids premature penalization
- ✅ Can be tuned based on real-world data

**Why Multiple Signals?**
- ✅ Single signals are too weak to be decisive
- ✅ Combination of signals creates stronger evidence
- ✅ Reduces false positive rate

**Why Confidence Gating?**
- ✅ Only applies to high-confidence documents
- ✅ Prevents noise from uncertain classifications
- ✅ Maintains precision over recall

---
