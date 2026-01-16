# Unified Signal Contract (V1)

**Status:** ✅ Production Ready  
**Version:** 1.0  
**Date:** 2024-01-16

---

## 🎯 Purpose

Create a **privacy-safe, confidence-aware, composable signal substrate** for fraud detection.

**Problem:** Features return heterogeneous dicts with:
- Raw text (PII leakage risk)
- Inconsistent confidence semantics
- No clear triggered/not-triggered states
- Hard to compose in rules

**Solution:** Unified `SignalV1` contract that:
- ✅ No raw text or PII
- ✅ Confidence-gated (signals suppressed if confidence too low)
- ✅ Structured evidence (machine-readable)
- ✅ Human-readable interpretation
- ✅ Composable in rules

---

## 📊 SignalV1 Schema

```python
class SignalV1(BaseModel):
    """
    Unified Signal Contract (v1)
    
    Privacy-safe, confidence-aware signal for fraud detection.
    """
    status: str  # "TRIGGERED" | "NOT_TRIGGERED" | "GATED" | "UNKNOWN"
    confidence: float  # [0.0-1.0]
    evidence: Dict[str, Any]  # Structured, privacy-safe evidence (no PII)
    interpretation: Optional[str]  # Human-readable explanation
    gating_reason: Optional[str]  # Why signal was gated (if status=GATED)
```

### **Status Values**

- **`TRIGGERED`**: Signal condition met (e.g., mismatch detected, multiple addresses found)
- **`NOT_TRIGGERED`**: Signal condition not met (normal/expected state)
- **`GATED`**: Signal suppressed due to low confidence (unreliable)
- **`UNKNOWN`**: Signal evaluation failed or indeterminate

### **Confidence Semantics**

- **High (0.8-1.0)**: Trust signal, use for risk amplification
- **Medium (0.5-0.79)**: Use cautiously, require corroboration
- **Low (<0.5)**: Weak signal, needs strong corroboration
- **Zero (0.0)**: Gated or failed

---

## 🔌 Emitted Signals

### **Address Signals** (3 signals)

#### 1. `addr.structure`
**Purpose:** Indicates presence and quality of address structure

**Triggers:**
- `TRIGGERED`: PLAUSIBLE_ADDRESS or STRONG_ADDRESS detected
- `NOT_TRIGGERED`: WEAK_ADDRESS or NOT_AN_ADDRESS

**Evidence:**
```python
{
  "classification": "STRONG_ADDRESS",
  "score": 7,
  "address_type": "STANDARD",
  "signals_found": ["street_indicator", "postal_token", "locality"]
}
```

#### 2. `addr.merchant_consistency`
**Purpose:** Indicates merchant-address alignment

**Triggers:**
- `TRIGGERED`: WEAK_MISMATCH or MISMATCH detected
- `NOT_TRIGGERED`: CONSISTENT
- `GATED`: Low doc or merchant confidence

**Evidence:**
```python
{
  "consistency_status": "WEAK_MISMATCH",
  "score": 0.1,
  "mismatch_type": "WEAK_MISMATCH"
}
```

#### 3. `addr.multi_address`
**Purpose:** Indicates presence of multiple distinct addresses

**Triggers:**
- `TRIGGERED`: MULTIPLE addresses detected
- `NOT_TRIGGERED`: SINGLE address
- `GATED`: Low doc confidence or insufficient text

**Evidence:**
```python
{
  "count": 3,
  "address_types": ["STANDARD", "STANDARD", "PO_BOX"],
  "distinctness_basis": ["postal_tokens", "address_type"],
  "evidence": ["distinct_postal_tokens", "distinct_address_types"]
}
```

---

### **Amount Signals** (3 signals)

#### 4. `amount.total_mismatch`
**Purpose:** Indicates line items sum doesn't match total

**Triggers:**
- `TRIGGERED`: Mismatch > $0.50
- `NOT_TRIGGERED`: Match within tolerance
- `GATED`: Low doc confidence or missing data

**Evidence:**
```python
{
  "total_amount": 100.00,
  "items_sum": 95.00,
  "mismatch_amount": 5.00,
  "mismatch_percentage": 5.0
}
```

#### 5. `amount.missing`
**Purpose:** Indicates expected amount is missing

**Triggers:**
- `TRIGGERED`: Missing total in transactional doc (INVOICE, POS_RECEIPT)
- `NOT_TRIGGERED`: Total present or not required

**Evidence:**
```python
{
  "doc_subtype": "INVOICE",
  "has_currency": true,
  "doc_profile_confidence": 0.85
}
```

#### 6. `amount.semantic_override`
**Purpose:** Indicates LLM corrected amount extraction

**Triggers:**
- `TRIGGERED`: Semantic LLM changed total amount
- `NOT_TRIGGERED`: LLM confirmed original or not invoked

**Evidence:**
```python
{
  "original_total": 100.00,
  "semantic_total": 105.00,
  "difference": 5.00,
  "semantic_confidence": 0.92
}
```

---

### **Template/PDF Signals** (2 signals)

#### 7. `template.pdf_producer_suspicious`
**Purpose:** Indicates PDF created by suspicious tool

**Triggers:**
- `TRIGGERED`: Producer flagged (online converter, editor)
- `NOT_TRIGGERED`: Legitimate producer

**Evidence:**
```python
{
  "producer_flagged": true,
  "producer_hint": "iLovePDF...",  # Truncated
  "creator_hint": "Microsoft Word..."
}
```

#### 8. `template.quality_low`
**Purpose:** Indicates poor template quality (OCR noise, layout issues)

**Triggers:**
- `TRIGGERED`: Quality score < 0.6
- `NOT_TRIGGERED`: Quality acceptable
- `GATED`: Low doc confidence

**Evidence:**
```python
{
  "quality_score": 0.45,
  "issues": ["high_ocr_noise", "layout_fragmented"],
  "issue_count": 2
}
```

---

### **Merchant Signals** (2 signals)

#### 9. `merchant.extraction_weak`
**Purpose:** Indicates merchant name extraction is uncertain

**Triggers:**
- `TRIGGERED`: No merchant or confidence < 0.6
- `NOT_TRIGGERED`: Strong extraction (confidence ≥ 0.6)
- `GATED`: Low doc confidence

**Evidence:**
```python
{
  "merchant_present": true,
  "merchant_confidence": 0.45,
  "merchant_length": 15
}
```

#### 10. `merchant.confidence_low`
**Purpose:** Indicates merchant confidence below threshold

**Triggers:**
- `TRIGGERED`: Confidence < 0.6 (default threshold)
- `NOT_TRIGGERED`: Confidence ≥ 0.6

**Evidence:**
```python
{
  "merchant_confidence": 0.55,
  "threshold": 0.6,
  "below_threshold": true
}
```

---

## 🔄 Signal Flow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Feature Extraction (features.py)                        │
│    - validate_address() → address_profile                  │
│    - assess_merchant_address_consistency() → consistency   │
│    - detect_multi_address_profile() → multi_address        │
│    - Extract amounts, merchant, PDF metadata               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Signal Wrappers (app/signals/)                          │
│    - signal_addr_structure(address_profile) → SignalV1     │
│    - signal_addr_merchant_consistency(consistency) → ...   │
│    - signal_addr_multi_address(multi_address) → ...        │
│    - signal_amount_total_mismatch(...) → ...               │
│    - signal_pdf_producer_suspicious(...) → ...             │
│    - signal_merchant_extraction_weak(...) → ...            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Emit to ReceiptFeatures.signals                         │
│    signals = {                                              │
│      "addr.structure": {...},                              │
│      "addr.merchant_consistency": {...},                   │
│      "addr.multi_address": {...},                          │
│      "amount.total_mismatch": {...},                       │
│      "amount.missing": {...},                              │
│      ...                                                    │
│    }                                                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Rule Consumption (app/rules/reference/)                 │
│    - Prefer unified signals if available                    │
│    - Fall back to legacy features for backward compat      │
│    - Combine ≥2 signals per rule                           │
│    - Always gate on confidence                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎨 Usage Examples

### **Example 1: Consuming Signals in Rules**

```python
def rule_multi_address_and_mismatch(
    signals: Dict[str, Any],
    doc_profile: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Rule: Multiple addresses + merchant mismatch in high-confidence invoice.
    """
    # Gate on document confidence
    if doc_profile.get("confidence", 0.0) < 0.8:
        return {"status": "GATED"}
    
    # Extract signals
    sig_multi = signals.get("addr.multi_address", {})
    sig_cons = signals.get("addr.merchant_consistency", {})
    
    # Check conditions using signals
    is_invoice = doc_profile.get("subtype") in {"INVOICE", "TAX_INVOICE"}
    has_multiple = sig_multi.get("status") == "TRIGGERED"
    has_mismatch = sig_cons.get("status") == "TRIGGERED"
    
    if is_invoice and has_multiple and has_mismatch:
        return {
            "status": "TRIGGERED",
            "rule_id": "MULTI_ADDR_MISMATCH",
            "evidence": {
                "multi_address_count": sig_multi.get("evidence", {}).get("count"),
                "consistency_status": sig_cons.get("evidence", {}).get("consistency_status"),
            },
            "interpretation": "Multiple addresses with merchant mismatch detected",
        }
    
    return {"status": "NOT_TRIGGERED"}
```

### **Example 2: Signal Inspection**

```python
# Get all triggered signals
triggered = [
    (name, sig)
    for name, sig in features.signals.items()
    if sig.get("status") == "TRIGGERED"
]

# Get high-confidence signals
high_conf = [
    (name, sig)
    for name, sig in features.signals.items()
    if sig.get("confidence", 0.0) >= 0.8
]

# Get gated signals (suppressed due to low confidence)
gated = [
    (name, sig)
    for name, sig in features.signals.items()
    if sig.get("status") == "GATED"
]
```

### **Example 3: Backward Compatibility**

```python
def evaluate_rules(features: ReceiptFeatures):
    """
    Evaluate rules with backward compatibility.
    """
    # Prefer signals if available
    if features.signals:
        return evaluate_with_signals(features.signals, features.text_features)
    else:
        # Fall back to legacy features
        return evaluate_with_legacy_features(features.text_features)
```

---

## 🔒 Privacy & Security

### **What's Safe**

✅ **Structured evidence** - No raw text, only aggregates/counts  
✅ **Truncated hints** - PDF producer truncated to 50 chars  
✅ **No merchant names** - Only confidence scores  
✅ **No addresses** - Only types and counts  
✅ **No amounts** - Only differences and percentages (rounded)

### **What to Avoid**

❌ **Don't log full signals** to external systems without review  
❌ **Don't expose in public APIs** without sanitization  
❌ **Don't use for analytics** without aggregation  

### **Recommendation**

Treat signals as **internal-only** data. Use for:
- Internal fraud rules
- Human review tooling (internal)
- Debugging (development/staging)

---

## 🎯 Design Principles

### **1. Privacy-First**
- No raw text or PII in evidence
- Truncate hints to prevent leakage
- Only structured, aggregate data

### **2. Confidence-Aware**
- Every signal has confidence score
- Signals gated when confidence too low
- Rules must respect confidence thresholds

### **3. Composable**
- Signals are atomic units
- Rules combine ≥2 signals
- Clear triggered/not-triggered states

### **4. Explainable**
- Human-readable interpretations
- Structured evidence for debugging
- Gating reasons when suppressed

### **5. Backward Compatible**
- Legacy features still available
- Rules can fall back gracefully
- Additive, not breaking

---

## 📊 Signal Coverage Matrix

| Feature Domain | Signals | Coverage |
|---|---|---|
| **Address** | 3 | Structure, consistency, multi-address |
| **Amount** | 3 | Mismatch, missing, semantic override |
| **Template/PDF** | 2 | Suspicious producer, quality |
| **Merchant** | 2 | Extraction weak, confidence low |
| **Total** | **10** | **Core fraud signals** |

---

## 🚀 Future Extensions

### **Planned Signals (V2)**

- `date.conflict` - Conflicting dates detected
- `date.future` - Future date in historical doc
- `geo.mismatch` - Geographic inconsistency
- `language.mixed` - Suspicious language mixing
- `ocr.low_confidence` - Poor OCR quality
- `template.editing_detected` - Template manipulation

### **ML-Ready Signals (V3)**

- `ml.fraud_score` - Learned fraud probability
- `ml.anomaly_score` - Anomaly detection score
- `ml.cluster_id` - Document cluster assignment

---

## 📚 Related Documentation

- `app/schemas/receipt.py` - SignalV1 schema definition
- `app/signals/` - Signal wrapper implementations
- `docs/REFERENCE_RULES_ADDRESS.md` - Rule patterns using signals
- `docs/TELEMETRY_ADDRESS.md` - Metrics and observability
- `ADDRESS_VALIDATION_V1.md` - Address feature documentation

---

## ✅ Implementation Checklist

- [x] Define SignalV1 schema in `app/schemas/receipt.py`
- [x] Add `signals` field to `ReceiptFeatures`
- [x] Create signal wrappers in `app/signals/`
  - [x] Address signals (3)
  - [x] Amount signals (3)
  - [x] Template signals (2)
  - [x] Merchant signals (2)
- [x] Wire signals in `app/pipelines/features.py`
- [x] Update reference rules to consume signals
- [x] Test signal wrappers
- [x] Document unified signal contract

---

## 🎓 Key Insights

**What We Learned:**
- Unified contracts enable composability
- Privacy-safe evidence prevents PII leakage
- Confidence gating prevents false positives
- Backward compatibility eases migration

**What's Next:**
- Monitor signal distribution in production
- Add more signals (date, geo, OCR, template)
- Build learned rules using signal combinations
- Create human review UI consuming signals

---

**Last Updated:** 2024-01-16  
**Version:** 1.0  
**Status:** Production Ready
