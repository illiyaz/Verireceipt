# Reference Rules: Address Validation Features

**Status:** ⚠️ DESIGN PROOF, NOT ENFORCEMENT ⚠️

**Purpose:** Demonstrate safe consumption of address validation features (V1, V2.1, V2.2)

---

## 🎯 Overview

This document provides **illustrative examples** of how to consume address validation features in fraud detection rules. These are **NOT operational rules** but design patterns for:

- Future learned rules
- ML feature engineering
- Human review tooling
- Fraud pattern documentation

---

## 🛡️ Guardrails (Non-Negotiable)

### ❌ What NOT to Do

1. **No Scoring** - Rules emit flags, not scores
2. **No Hard Fail** - Rules never mark documents as fraud alone
3. **No Single Signal** - Rules must combine ≥2 signals
4. **No Unguarded Rules** - Rules must gate on confidence

### ✅ What TO Do

1. **Combine Signals** - Use ≥2 features per rule
2. **Gate on Confidence** - Check `doc_profile_confidence` and `merchant_confidence`
3. **Emit Structured Evidence** - Return interpretable results
4. **Document Risk Hypothesis** - Explain legitimate vs suspicious patterns

---

## 📋 Reference Rules

### Rule 1: Multi-Address + Mismatch (Invoice)

**ID:** `RULE_ADDR_MULTI_AND_MISMATCH`

**Signal Combination:**
- Document is INVOICE with high confidence (≥0.8)
- Multiple distinct addresses detected
- Merchant name doesn't match any address

**Risk Hypothesis:**
- **Legitimate:** B2B invoices often have bill-to, ship-to addresses
- **Suspicious:** When combined with PDF editing, template anomalies

**Usage:**
```python
if (doc_subtype == "INVOICE" 
    and doc_profile_confidence >= 0.8
    and multi_address_profile["status"] == "MULTIPLE"
    and merchant_address_consistency["status"] in {"WEAK_MISMATCH", "MISMATCH"}):
    emit_flag("address_anomaly_cluster")
```

**Next Steps:**
- Check PDF metadata for suspicious producers
- Review template quality signals
- Verify merchant legitimacy

---

### Rule 2: Multi-Address in High-Confidence Invoice

**ID:** `RULE_ADDR_MULTI_IN_INVOICE_HIGHCONF`

**Signal Combination:**
- Document is INVOICE with high confidence (≥0.8)
- Multiple distinct addresses detected
- At least one address is PLAUSIBLE or STRONG

**Risk Hypothesis:**
- **Legitimate:** B2B invoices (most common)
- **Informational:** Track document complexity

**Usage:**
```python
if (doc_subtype == "INVOICE"
    and doc_profile_confidence >= 0.8
    and multi_address_profile["status"] == "MULTIPLE"
    and address_profile["address_classification"] in {"PLAUSIBLE_ADDRESS", "STRONG_ADDRESS"}):
    emit_flag("complex_invoice_structure")
```

**Telemetry:**
- Track frequency to understand invoice complexity distribution
- Useful for tuning multi-address detection sensitivity

---

### Rule 3: PO Box + Corporate Merchant

**ID:** `RULE_ADDR_POBOX_CORPORATE_MISMATCH`

**Signal Combination:**
- Merchant name suggests corporate entity (Ltd, LLC, Corp)
- Merchant confidence ≥0.7
- Address is PO Box type
- Document confidence ≥0.7

**Risk Hypothesis:**
- **Legitimate:** Small businesses, remote operations
- **Suspicious:** Large corporations typically have physical addresses

**Usage:**
```python
if (merchant_confidence >= 0.7
    and doc_profile_confidence >= 0.7
    and "ltd" in merchant_name.lower() or "corp" in merchant_name.lower()
    and address_profile["address_type"] == "PO_BOX"):
    emit_flag("address_type_anomaly")
```

**Next Steps:**
- Verify merchant registration
- Check if merchant is known/established
- Review other documents from same merchant

---

### Rule 4: Low Confidence Suppression

**ID:** `RULE_ADDR_SUPPRESSION_LOW_CONFIDENCE`

**Signal Combination:**
- Document profile confidence <0.55
- Address features are gated (return UNKNOWN)

**Risk Hypothesis:**
- Low confidence = unreliable OCR or unclear document type
- Address signals are not trustworthy

**Usage:**
```python
if doc_profile_confidence < 0.55:
    suppress_address_rules()
    emit_flag("address_features_unreliable")
```

**Telemetry:**
- Track % of docs suppressed
- Tune confidence threshold based on false positive rate

---

### Rule 5: Weak Merchant Suppression

**ID:** `RULE_ADDR_SUPPRESSION_WEAK_MERCHANT`

**Signal Combination:**
- Merchant confidence <0.6
- Merchant-address consistency is gated (returns UNKNOWN)

**Risk Hypothesis:**
- Low merchant confidence = uncertain merchant extraction
- Consistency check is not trustworthy

**Usage:**
```python
if merchant_confidence < 0.6:
    suppress_merchant_consistency_rules()
    emit_flag("merchant_consistency_unreliable")
```

**Telemetry:**
- Track % of docs suppressed
- Improve merchant extraction heuristics

---

### Rule 6: Template Editing Suspicion

**ID:** `RULE_ADDR_TEMPLATE_EDITING_SUSPICION`

**Signal Combination:**
- PDF producer is suspicious (online editors)
- Multiple addresses detected
- At least one address is PLAUSIBLE or STRONG
- Document confidence ≥0.7

**Risk Hypothesis:**
- **Legitimate:** Users editing legitimate invoices
- **Suspicious:** Fraudsters creating fake invoices with editing tools

**Usage:**
```python
if (suspicious_pdf_producer
    and doc_profile_confidence >= 0.7
    and multi_address_profile["status"] == "MULTIPLE"
    and address_profile["address_classification"] in {"PLAUSIBLE_ADDRESS", "STRONG_ADDRESS"}):
    emit_flag("template_editing_suspicion")
```

**Next Steps:**
- Check PDF metadata for editing timestamps
- Review template quality signals
- Compare with known legitimate templates

---

## 🔄 Rule Evaluation Pattern

### Recommended Flow

```python
# 1. Extract features from pipeline
address_profile = text_features["address_profile"]
merchant_address_consistency = text_features["merchant_address_consistency"]
multi_address_profile = text_features["multi_address_profile"]

# 2. Check confidence gates FIRST
if doc_profile_confidence < 0.55:
    return {"suppressed": True, "reason": "low_doc_confidence"}

if merchant_confidence < 0.6:
    # Skip merchant-dependent rules
    pass

# 3. Evaluate rules (combine ≥2 signals)
triggered_rules = []

if (condition_1 and condition_2 and condition_3):
    triggered_rules.append({
        "rule_id": "RULE_XYZ",
        "risk_hint": "...",
        "evidence": {...},
    })

# 4. Emit structured evidence (no scoring)
return {
    "triggered_rules": triggered_rules,
    "interpretation": "...",
    "next_steps": [...],
}
```

---

## 📊 Feature Availability Matrix

| Feature | Confidence Gate | Returns UNKNOWN When |
|---------|----------------|---------------------|
| `address_profile` | None | Never (always returns classification) |
| `merchant_address_consistency` | doc_profile_confidence ≥0.55 AND merchant_confidence ≥0.6 | Either confidence below threshold |
| `multi_address_profile` | doc_profile_confidence ≥0.55 | Confidence below threshold |

---

## 🎓 Design Principles

### 1. Signal Substrate, Not Fraud Detector

Address features are **signals**, not verdicts. They must be combined with:
- PDF metadata (producer, creation date)
- Template quality signals
- Merchant legitimacy checks
- Amount/date anomalies
- Historical patterns

### 2. Confidence-Aware Architecture

Every rule must respect confidence gates:
- **High confidence (≥0.8):** Trust signals, use for risk amplification
- **Medium confidence (0.55-0.79):** Use cautiously, require corroboration
- **Low confidence (<0.55):** Suppress, signals unreliable

### 3. Explainable by Design

Every triggered rule must provide:
- **Rule ID:** Unique identifier
- **Evidence:** Structured data (no free text)
- **Interpretation:** Human-readable explanation
- **Next Steps:** Actionable recommendations

### 4. Regression-Protected

Golden tests (15 cases, 65 tests) lock behavior:
- Prevents silent regressions
- Enables confident heuristic evolution
- Provides system truth

---

## 🚀 ML Readiness

### When ML Makes Sense

✅ **Use ML when:**
- You have ≥10,000 labeled examples
- False positive cost is high
- Patterns are complex/non-linear
- You need to combine 5+ signals

❌ **Don't use ML when:**
- You have <1,000 labeled examples
- Rules are simple (2-3 signals)
- Explainability is critical
- You can't maintain the model

### Feature Engineering

Address features are **ML-ready**:
```python
# Example feature vector
features = [
    address_profile["address_score"],  # Numeric
    1 if address_profile["address_type"] == "PO_BOX" else 0,  # Binary
    multi_address_profile["count"],  # Numeric
    merchant_address_consistency["score"],  # Numeric [0.0-1.0]
    doc_profile_confidence,  # Numeric [0.0-1.0]
    merchant_confidence,  # Numeric [0.0-1.0]
]
```

---

## 📈 Telemetry Recommendations

### Key Metrics to Track

1. **Feature Distribution:**
   - % docs with PLAUSIBLE/STRONG address
   - % docs with MULTIPLE addresses
   - % docs with PO_BOX addresses

2. **Consistency Patterns:**
   - % docs with CONSISTENT merchant-address
   - % docs with WEAK_MISMATCH
   - % docs with MISMATCH

3. **Gating Rates:**
   - % docs gated due to low doc_profile_confidence
   - % docs gated due to low merchant_confidence

4. **Rule Triggers:**
   - Frequency of each reference rule
   - Overlap between rules (e.g., multi-address ∧ mismatch)

5. **False Positive Tracking:**
   - % of triggered rules that are false positives
   - Which rules have highest FP rate

---

## 🔍 Human Review Tooling

### Recommended UI Elements

**Address Profile Card:**
```
┌─────────────────────────────────────┐
│ Address Validation                  │
├─────────────────────────────────────┤
│ Classification: STRONG_ADDRESS      │
│ Score: 7/10                         │
│ Type: STANDARD                      │
│ Raw Text: "123 Main St, City..."   │
└─────────────────────────────────────┘
```

**Multi-Address Detection Card:**
```
┌─────────────────────────────────────┐
│ Multi-Address Detection             │
├─────────────────────────────────────┤
│ Status: MULTIPLE                    │
│ Count: 3 distinct addresses         │
│ Types: [STANDARD, STANDARD, PO_BOX]│
│ Evidence: distinct_postal_tokens    │
└─────────────────────────────────────┘
```

**Merchant Consistency Card:**
```
┌─────────────────────────────────────┐
│ Merchant-Address Consistency        │
├─────────────────────────────────────┤
│ Status: WEAK_MISMATCH               │
│ Score: 0.4/1.0                      │
│ Merchant: "Acme Corp"               │
│ Confidence: 0.85                    │
└─────────────────────────────────────┘
```

---

## ⚠️ Important Warnings

### DO NOT:

1. ❌ Use any single rule to mark fraud
2. ❌ Operationalize without extensive testing
3. ❌ Ignore confidence gates
4. ❌ Score or penalize based on address signals alone
5. ❌ Assume address correctness (we don't validate existence)

### DO:

1. ✅ Combine ≥2 signals per rule
2. ✅ Gate on confidence thresholds
3. ✅ Emit structured evidence
4. ✅ Track telemetry for tuning
5. ✅ Test extensively before production

---

## 📚 Related Documentation

- `ADDRESS_VALIDATION_V1.md` - V1 design and scoring rubric
- `ADDRESS_VALIDATION_V1.md` (V2.1 section) - Merchant-address consistency
- `ADDRESS_VALIDATION_V1.md` (V2.2 section) - Multi-address detection
- `ADDRESS_VALIDATION_V1.md` (V3 section) - Learned rule patterns
- `tests/golden/address_cases.json` - Golden test cases
- `tests/test_address_golden.py` - Golden test runner

---

## 🎯 Summary

**What We Built:**
- Signal substrate (not fraud detector)
- Composable features
- Confidence-aware architecture
- Explainable by design
- Regression-protected
- ML-ready (but not ML-dependent)

**What's Next:**
- Add telemetry hooks (Step 4)
- Upgrade V2.2 schema for debugging (Step 5)
- Design human labeling loop
- Determine when ML makes sense

**Key Insight:**
> "Very few teams get this right. You've built a signal substrate that scales."

---

**Last Updated:** 2024-01-16  
**Version:** 1.0  
**Status:** Design Proof (Not Operational)
