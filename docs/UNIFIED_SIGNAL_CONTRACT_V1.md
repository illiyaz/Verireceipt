# Unified Signal Contract (V1)

**Status:** Production  
**Version:** 1.0  
**Last Updated:** 2024-01-16

---

## Table of Contents

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

## 🔒 SignalRegistry & Contract Enforcement

### Purpose

The `SignalRegistry` is a static registry of all allowed signal names in the Unified Signal Contract (V1). It provides:

- **Contract enforcement** - Prevents typos like `addr.multiAddr` or `date.future_2`
- **Safer refactors** - Know exactly what signals exist across the codebase
- **ML-feature stability** - Consistent signal names for learned rules and telemetry
- **Clean telemetry joins** - No orphaned or misspelled signal names

### Registry Definition

Located in `app/schemas/receipt.py`:

```python
@dataclass(frozen=True)
class SignalSpec:
    """Formal specification for a signal (immutable)."""
    name: str
    domain: str
    version: str
    severity: str  # "weak" | "medium" | "strong"
    gated_by: List[str]  # Conditions that gate this signal
    privacy: str  # "safe" | "derived"
    description: str


class SignalRegistry:
    SIGNALS: Dict[str, SignalSpec] = {
        "addr.structure": SignalSpec(
            name="addr.structure",
            domain="address",
            version="v1",
            severity="weak",
            gated_by=["doc_profile_confidence"],
            privacy="safe",
            description="Address structure validation",
        ),
        # ... 18 more signals
    }
    
    @classmethod
    def is_allowed(cls, name: str) -> bool:
        return name in cls.SIGNALS
    
    @classmethod
    def get_spec(cls, name: str) -> Optional[SignalSpec]:
        return cls.SIGNALS.get(name)
    
    @classmethod
    def get_by_domain(cls, domain: str) -> List[SignalSpec]:
        return [s for s in cls.SIGNALS.values() if s.domain == domain]
```

**Key features:**
- **Immutable specs** (frozen dataclass) - no runtime modification
- **Rich metadata** - domain, version, severity, gating, privacy
- **Machine-checkable** - CI enforces all invariants

### Enforcement

Registry enforcement happens in `app/pipelines/features.py` after signal emission:

```python
from app.schemas.receipt import SignalRegistry

for name in unified_signals.keys():
    if not SignalRegistry.is_allowed(name):
        raise ValueError(f"Unregistered signal emitted: '{name}'")
```

**Why hard fail?** This is a schema violation - CI must fail to prevent corrupted telemetry and broken ML joins.

### Adding New Signals

1. Create signal wrapper in `app/signals/`
2. Add to `SignalRegistry.ALLOWED_SIGNALS`
3. Update tests in `tests/test_signal_registry.py`
4. Update count in `test_signal_registry_count()`
5. Document in this file

---

## 🤖 Learned Rules & Signal Consumption

### Design Principles

**Hard Invariant:** A learned rule must **never** fire on a single signal alone.

**Minimum requirements:**
- ≥2 signals OR
- 1 signal + external evidence (user history, risk profile)

### Canonical Input

Learned rules only see:
```python
{"signal_name": "addr.multi_address", "status": "TRIGGERED", "confidence": 0.82}
```

**Nothing else.** No raw evidence, no interpretation, no PII.

### Pattern 1: Boolean Embedding

For logistic regression, LightGBM, small neural nets:

```python
features = {
    "addr_multi_triggered": signal.status == "TRIGGERED",
    "addr_multi_conf": signal.confidence,
    "addr_multi_gated": signal.status == "GATED",
}
```

### Pattern 2: Signal Interaction Features

Explicit, auditable combinations:

```python
addr_multi_and_mismatch = (
    signals["addr.multi_address"].status == "TRIGGERED" and
    signals["addr.merchant_consistency"].status == "TRIGGERED"
)
```

### Pattern 3: Confidence-Weighted Signals

For scoring models:

```python
score = weight * signal.confidence if signal.status == "TRIGGERED" else 0
# GATED signals contribute zero, not negative
```

### Example Learned Rule

```python
def learned_rule_addr_anomaly_cluster(signals: Dict[str, SignalV1]) -> Dict[str, Any]:
    sig_multi = signals.get("addr.multi_address")
    sig_cons = signals.get("addr.merchant_consistency")
    
    if not sig_multi or sig_multi.status == "GATED":
        return {"status": "GATED", "reason": "addr.multi_address gated"}
    if not sig_cons or sig_cons.status == "GATED":
        return {"status": "GATED", "reason": "addr.merchant_consistency gated"}
    
    if sig_multi.status == "TRIGGERED" and sig_cons.status == "TRIGGERED":
        combined_confidence = min(sig_multi.confidence, sig_cons.confidence)
        return {
            "status": "TRIGGERED",
            "rule_id": "LEARNED_ADDR_ANOMALY_CLUSTER",
            "confidence": combined_confidence,
            "evidence": {
                "signals_used": ["addr.multi_address", "addr.merchant_consistency"],
            },
        }
    
    return {"status": "NOT_TRIGGERED"}
```

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
