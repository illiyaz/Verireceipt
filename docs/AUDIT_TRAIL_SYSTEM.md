# Audit Trail System Documentation

## Overview

VeriReceipt implements a comprehensive audit trail system that tracks every decision, rule evaluation, and extraction with full provenance and confidence awareness.

## Core Components

### 1. AuditEvent Schema

Every decision step is recorded as an `AuditEvent`:

```python
@dataclass
class AuditEvent:
    # Identity & Ordering
    event_id: str              # UUID for deduplication
    ts: str                    # ISO-8601 UTC timestamp
    
    # Classification
    source: str                # rule_engine / ensemble / vision_llm / layoutlm / donut
    type: str                  # rule_triggered / model_vote / override / normalization
    severity: Optional[str]    # HARD_FAIL / CRITICAL / WARNING / INFO
    code: Optional[str]        # Stable rule ID (e.g., R16_SUSPICIOUS_DATE_GAP)
    
    # Content
    message: str               # Human-readable summary
    evidence: Dict[str, Any]   # Machine-readable structured data
```

**Key Features:**
- Auto-generates `event_id` and `ts` via `finalize_defaults()`
- Serializes to JSON via `to_dict()` for persistence
- Immutable once created (append-only audit log)

### 2. ReceiptDecision Schema

Enhanced decision object with full audit context:

```python
@dataclass
class ReceiptDecision:
    # Core verdict
    label: str                 # real / fake / suspicious
    score: float               # 0.0 - 1.0
    
    # Version tracking
    rule_version: str
    policy_version: str
    policy_name: str           # "default" / "strict" / "lenient"
    engine_version: str
    
    # Decision identity
    decision_id: str           # UUID
    created_at: str            # ISO-8601 timestamp
    finalized: bool            # True = final, False = draft
    
    # Extraction confidence (NEW)
    extraction_confidence_score: Optional[float]   # 0.0 - 1.0
    extraction_confidence_level: Optional[str]     # "low" / "medium" / "high"
    
    # Monetary extraction (NEW)
    normalized_total: Optional[float]
    currency: Optional[str]                        # ISO code (USD, EUR, INR)
    parsed_totals: Optional[List[Dict]]            # All candidate totals
    
    # Audit trail
    audit_events: List[AuditEvent]                 # Primary audit log
    events: Optional[List[Dict]]                   # Legacy rule events
    
    # Human-readable explanations
    reasons: List[str]
    minor_notes: Optional[List[str]]
```

**Key Methods:**
- `finalize_defaults()` - Auto-populate IDs, timestamps, and nested events
- `add_audit_event(event)` - Append event with auto-finalization
- `to_dict()` - JSON-serializable export for persistence

## Confidence-Aware Rule Weighting

### Problem Statement

OCR quality varies significantly across receipts. Low-quality OCR can trigger false positives in rule-based fraud detection.

### Solution: Confidence Scaling

Rules are now weighted based on extraction confidence:

```python
def _confidence_factor_from_features(ff, tf, lf, fr) -> float:
    """
    Returns multiplicative factor in [0.6, 1.0] to scale soft rule weights.
    HARD_FAIL rules are NEVER scaled.
    """
    # Extract confidence from text features
    conf = tf.get("confidence")  # From ensemble
    
    # Map to factor
    if conf >= 0.85:
        factor = 1.0      # High confidence - full weight
    elif conf >= 0.65:
        factor = 0.85     # Medium confidence - slight reduction
    else:
        factor = 0.70     # Low confidence - more reduction
    
    # Additional softening for low-quality images
    if source_type == "image" and not exif_present:
        factor = min(factor, 0.80)
    
    return max(0.60, min(1.00, factor))
```

### RuleEvent Tracking

Each rule now tracks both raw and applied weights:

```python
@dataclass
class RuleEvent:
    rule_id: str
    severity: str              # HARD_FAIL | CRITICAL | WARNING | INFO
    weight: float              # Applied weight (after confidence scaling)
    raw_weight: float          # Original rule weight
    message: str
    evidence: Dict[str, Any]   # Includes confidence_factor, raw_weight, applied_weight
```

### Emission Logic

```python
def _emit_event(..., confidence_factor: float = 1.0) -> float:
    """
    Emit rule event with confidence-aware weighting.
    """
    raw_w = float(weight or 0.0)
    cf = float(confidence_factor or 1.0)
    
    # HARD_FAIL rules always use full weight
    if severity == "HARD_FAIL":
        applied_w = raw_w
        cf_used = 1.0
    else:
        # Soft rules scaled by confidence
        cf_used = max(0.60, min(1.00, cf))
        applied_w = raw_w * cf_used
    
    # Store both weights in evidence
    ev.evidence["confidence_factor"] = cf_used
    ev.evidence["raw_weight"] = raw_w
    ev.evidence["applied_weight"] = applied_w
    
    return applied_w  # Return applied weight for score accumulation
```

## Extraction Confidence System

### Unified Representation

Ensemble now provides consistent confidence metrics:

```python
converged_data = {
    "merchant": "Starbucks",
    "total": 12.50,
    "date": "2024-01-15",
    
    # Per-field confidence
    "confidence": {
        "merchant": 0.90,
        "total": 0.95,
        "date": 0.85,
        "overall": 0.90
    },
    
    # Normalized overall confidence (NEW)
    "confidence_score": 0.90,      # float in [0, 1]
    "confidence_level": "high"     # "low" | "medium" | "high"
}
```

### Confidence Level Mapping

```python
def _confidence_level(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.65:
        return "medium"
    return "low"
```

### Weighted Average Calculation

```python
weights = {"merchant": 0.40, "total": 0.40, "date": 0.20}

overall = sum(w * confidence[field] for field, w in weights.items()) / sum(weights.values())
```

## Enhanced Merchant Validation

### Problem: OCR Label Confusion

OCR engines frequently extract field labels as merchant names:
- "MERCHANT", "INVOICE", "RECEIPT", "TOTAL"
- "Merchant:", "Vendor:", "Bill To:"

### Solution: Blacklist + Heuristics

```python
_MERCHANT_LABEL_BLACKLIST = {
    "invoice", "receipt", "tax invoice", "bill", "statement",
    "total", "subtotal", "amount", "date", "customer", "vendor"
}

def _looks_like_label_merchant(merchant: str) -> bool:
    """Detect if extracted 'merchant' is actually a field label."""
    s = normalize(merchant)
    
    # Exact blacklist match
    if s in _MERCHANT_LABEL_BLACKLIST:
        return True
    
    # Very short generic tokens
    if len(s) <= 3 and s.isalpha():
        return True
    
    # Starts with common label patterns
    if re.match(r"^(invoice|receipt|tax invoice|bill|statement)\b", s):
        return True
    
    # Key-value label pattern
    if re.match(r"^(merchant|vendor|customer|date|total)\s*[:\-]", s):
        return True
    
    return False
```

### Smart Candidate Selection

```python
def _select_best_merchant_candidate(candidates: List[Tuple[str, Any, float]]):
    """Choose best merchant, preferring non-label-like values."""
    # Filter out label-like candidates
    good = [c for c in candidates if not _looks_like_label_merchant(c[1])]
    
    if good:
        return max(good, key=lambda x: x[2])  # Highest weight
    
    # All look like labels - use highest weight with reduced confidence
    return max(candidates, key=lambda x: x[2])
```

## Vision/Rules Reconciliation

### Decision Precedence

```
1. HARD_FAIL (rules) → Always reject
2. Strong rule evidence → Reject (even if vision says real)
3. Vision fake + rules not clean → Reject
4. Vision high-conf real + rules moderate → Human review (NEW)
5. Both align on real → Approve
6. Low-confidence vision → Defer to rules + agreement
7. Remaining conflicts → Human review
```

### Thresholds

```python
STRONG_RULE_REJECT_SCORE = 0.85    # Auto-reject threshold
MODERATE_RULE_SCORE = 0.70         # Conflict zone threshold
```

### Conflict Resolution Example

```python
# Vision very confident REAL, but rules moderately suspicious
if (vision_verdict == "real" and vision_confidence >= 0.90 
    and rule_label == "fake" 
    and MODERATE_RULE_SCORE <= rule_score < STRONG_RULE_REJECT_SCORE
    and critical_count <= 1):
    
    verdict["final_label"] = "suspicious"
    verdict["recommended_action"] = "human_review"
    verdict["reasoning"] = [
        "⚠️ Vision/Rules conflict",
        f"✅ Vision: real (conf={vision_confidence:.2f})",
        f"❌ Rules: fake (score={rule_score:.2f})",
        "→ Escalating to human review"
    ]
```

## Persistence

### CSV Logging

All new fields automatically logged to `data/logs/decisions.csv`:

```csv
filename,label,score,decision_id,created_at,policy_name,
extraction_confidence_score,extraction_confidence_level,
normalized_total,currency,audit_events,events,...
```

### Database Storage

SQLite `Analysis` table includes all new fields:

```python
analysis = Analysis(
    decision_id=decision.decision_id,
    created_at=decision.created_at,
    policy_name=decision.policy_name,
    extraction_confidence_score=decision.extraction_confidence_score,
    extraction_confidence_level=decision.extraction_confidence_level,
    normalized_total=decision.normalized_total,
    currency=decision.currency,
    audit_events=json.dumps([e.to_dict() for e in decision.audit_events]),
    ...
)
```

## Usage Examples

### 1. Creating a Decision with Audit Trail

```python
from app.pipelines.rules import analyze_receipt

decision = analyze_receipt(
    file_path="/path/to/receipt.pdf",
    extracted_total="$45.67",
    extracted_merchant="Starbucks",
    apply_learned=True
)

# Auto-finalize before persistence
decision.finalize_defaults()

# Audit events are automatically populated
for event in decision.audit_events:
    print(f"{event.ts} [{event.severity}] {event.code}: {event.message}")
```

### 2. Adding Custom Audit Events

```python
from app.schemas.receipt import AuditEvent

event = AuditEvent(
    source="manual_review",
    type="override",
    severity="INFO",
    code="HUMAN_OVERRIDE",
    message="Approved by compliance officer",
    evidence={"reviewer_id": "CO-123", "notes": "Verified with merchant"}
)

decision.add_audit_event(event)  # Auto-finalizes event
```

### 3. Querying Audit Trail

```python
# Find all HARD_FAIL events
hard_fails = [e for e in decision.audit_events if e.severity == "HARD_FAIL"]

# Find rule-triggered events
rule_events = [e for e in decision.audit_events if e.type == "rule_triggered"]

# Export to JSON
audit_json = [e.to_dict() for e in decision.audit_events]
```

## Benefits

### 1. Reduced False Positives
- Low OCR confidence → Reduced rule weights → Fewer false rejections
- Noisy receipts no longer auto-rejected

### 2. Better Merchant Extraction
- Filters common OCR label confusion
- Prefers real business names over generic labels

### 3. Richer Audit Trail
- Every decision fully traceable
- Confidence factors preserved in evidence
- Supports compliance and debugging

### 4. Improved Conflict Resolution
- Nuanced Vision/Rules reconciliation
- Human review for ambiguous cases
- Reduced auto-reject rate

### 5. Enhanced Analytics
- Track confidence trends over time
- Identify low-quality OCR patterns
- Optimize rule weights based on confidence distribution

## Migration Notes

### Breaking Changes
None - all changes are backward compatible.

### New Fields
All new fields have sensible defaults:
- `extraction_confidence_score`: defaults to 0.70
- `extraction_confidence_level`: defaults to "medium"
- `policy_name`: defaults to "default"
- `finalized`: defaults to True

### Legacy Support
- Old `events` field still populated for backward compatibility
- Existing CSV logs continue to work (new columns added dynamically)

## Future Enhancements

1. **Adaptive Thresholds**: Learn optimal confidence thresholds from feedback
2. **Confidence Calibration**: Calibrate ensemble confidence scores
3. **Rule Learning**: Auto-adjust rule weights based on false positive rates
4. **Audit Analytics Dashboard**: Visualize audit trails and confidence distributions
