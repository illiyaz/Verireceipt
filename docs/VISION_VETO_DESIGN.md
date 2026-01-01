# Vision Veto-Only Design

## Overview

VeriReceipt implements a **strict veto-only design** for vision LLM integration. Vision can only detect tampering and trigger rejection—it cannot upgrade trust, confirm authenticity, or override rule-based decisions.

**Mental Model:**
```
Vision is a sensor, not a judge.
It can pull the emergency brake, but never press the accelerator.
```

---

## Design Principles

### 1. Vision is Veto-Only

| Vision Output | Effect | Decision Authority |
|---------------|--------|-------------------|
| `clean` | ❌ No effect | Rules decide |
| `suspicious` | ℹ️ Audit only | Rules decide |
| `tampered` | 🚨 HARD_FAIL → fake | Vision veto |

**Key Constraints:**
- Vision **cannot** say "real" or "fake"
- Vision **cannot** upgrade trust scores
- Vision **cannot** override rule-based decisions
- Vision **cannot** participate in decision blending

### 2. Canonical Vision Assessment Contract

Vision LLM outputs a standardized assessment:

```python
{
    "visual_integrity": "clean" | "suspicious" | "tampered",
    "confidence": 0.0-1.0,  # float
    "observable_reasons": [
        "Clear editing artifacts around total amount",
        "Font inconsistency between merchant name and total",
        "Digital manipulation signatures detected"
    ]
}
```

**Forbidden Fields:**
- ❌ `vision_verdict` (allowed trust upgrading)
- ❌ `vision_reasoning` (probabilistic influence)
- ❌ `authenticity_assessment` (old structure)
- ❌ `authenticity_score` (blending weight)

### 3. Single Entry Point

**Only one function should be called:**
```python
from app.pipelines.vision_llm import build_vision_assessment

assessment = build_vision_assessment(image_path)
# Returns: {visual_integrity, confidence, observable_reasons}
```

**Deprecated functions (do not use):**
- ❌ `analyze_receipt_with_vision()` - returns old verdict structure
- ❌ `get_hybrid_verdict()` - allows vision to override rules
- ❌ `run_vision_authenticity()` - probabilistic blending

---

## Implementation Details

### Vision Veto Flow

```
1. Vision Assessment (upstream)
   ↓
   build_vision_assessment(image_path)
   ↓
   {visual_integrity: "tampered", confidence: 0.92, observable_reasons: [...]}

2. Rules Engine (primary decision)
   ↓
   If visual_integrity == "tampered":
      Emit V1_VISION_TAMPERED event (severity: HARD_FAIL)
      label = "fake"
      Add observable_reasons to audit trail
   Else:
      Rules decide normally (vision has no effect)
   
3. Ensemble (packaging only)
   ↓
   Package rule decision + audit metadata
   Store vision assessment for audit transparency
   NO vision decisioning or blending

4. Final Output
   ↓
   label: from rules (or vision veto if tampered)
   visual_integrity: for audit
   observable_reasons: for investigation
```

### Code Locations

**Core Implementation:**
- `app/pipelines/vision_llm.py` - `build_vision_assessment()` (lines 493-595)
- `app/pipelines/rules.py` - Vision veto integration in `_score_and_explain()`
- `app/pipelines/ensemble.py` - Audit-only vision capture (lines 480-498)

**API Endpoints:**
- `app/api/main.py` - `/analyze/hybrid` (non-streaming)
- `app/api/main.py` - `/analyze/hybrid/stream` (streaming)

**Schema:**
- `app/schemas/receipt.py` - `ReceiptDecision` dataclass (lines 138-142)

---

## API Changes

### Response Schema (Before vs After)

**Before (violated veto-only):**
```json
{
  "label": "real",
  "score": 0.85,
  "vision_verdict": "real",
  "vision_confidence": 0.90,
  "vision_reasoning": "Receipt appears authentic"
}
```

**After (veto-safe):**
```json
{
  "label": "real",
  "score": 0.85,
  "visual_integrity": "clean",
  "vision_confidence": 0.90
}
```

### Field Mapping

| Old Field (Forbidden) | New Field (Veto-Safe) | Notes |
|----------------------|----------------------|-------|
| `vision_verdict` | `visual_integrity` | "clean"\|"suspicious"\|"tampered" |
| `vision_reasoning` | N/A | Not exposed in response |
| `authenticity_assessment` | N/A | Internal only |
| `authenticity_score` | N/A | No blending weights |

**Observable reasons** are available in audit trails and debug info, but not in the main response payload.

---

## Corroboration Changes

### Before (Vision Influenced Decisions)

```python
# FORBIDDEN: Vision-based corroboration flags
if vision_verdict == "real" and rule_label == "fake":
    corroboration_flags.append("VISION_REAL_RULES_FAKE")
    corroboration_score -= 0.25

if vision_verdict == "real" and layoutlm_missing_total:
    corroboration_flags.append("VISION_REAL_LAYOUT_MISSING_TOTAL")
```

### After (Vision-Free Corroboration)

```python
# Vision is NOT part of corroboration
# Only rules + extraction quality matter
if critical_count > 0:
    corroboration_score -= 0.25

if layoutlm_extracted and layoutlm_extracted.get("total"):
    corroboration_score += 0.25
```

**Removed Flags:**
- ❌ `VISION_REAL_RULES_CRITICAL`
- ❌ `VISION_REAL_LAYOUT_MISSING_TOTAL`
- ❌ `VISION_REAL_RULES_FAKE`
- ❌ `VISION_FAKE_RULES_REAL`

---

## Streaming Endpoint Changes

### Before (Broken)

```python
# Old streaming endpoint used deprecated functions
vision_results = analyze_receipt_with_vision(image_path)
auth = vision_results.get("authenticity_assessment", {})

# Hybrid logic allowed vision to decide
if vision_verdict == "real" and vision_confidence > 0.7:
    hybrid["final_label"] = "real"
```

### After (Veto-Safe)

```python
# Use canonical veto-safe function
vision_assessment = build_vision_assessment(image_path)

result = {
    "visual_integrity": vision_assessment.get("visual_integrity"),
    "confidence": vision_assessment.get("confidence"),
    "observable_reasons": vision_assessment.get("observable_reasons")
}

# Hybrid uses rules only (vision veto already applied)
hybrid["final_label"] = rule_label
hybrid["confidence"] = rule_score
```

---

## Testing Strategy

### 1. Golden Tests (`tests/test_vision_veto_golden.py`)

Three critical scenarios:

**Test 1: CLEAN Vision**
```python
# Vision says "clean" → rules decide
visual_integrity = "clean"
# Expected: No V1_VISION_TAMPERED event
# Expected: Decision based purely on rules
```

**Test 2: SUSPICIOUS Vision**
```python
# Vision says "suspicious" → audit only
visual_integrity = "suspicious"
# Expected: No V1_VISION_TAMPERED event
# Expected: Decision based purely on rules
# Expected: Suspicious assessment in debug/audit
```

**Test 3: TAMPERED Vision**
```python
# Vision says "tampered" → HARD_FAIL
visual_integrity = "tampered"
# Expected: V1_VISION_TAMPERED event (severity: HARD_FAIL)
# Expected: label = "fake"
# Expected: Observable reasons in audit trail
```

### 2. Comprehensive Enforcement (`tests/test_veto_enforcement.py`)

Scans **all 91 Python files** in repository:

**Check 1: No vision_verdict**
- Fails if `vision_verdict` appears anywhere
- Ensures old field is completely removed

**Check 2: No authenticity_assessment**
- Fails if old vision output structure used
- Ensures canonical function is used

**Check 3: No vision corroboration flags**
- Fails if `VISION_REAL_*` or `VISION_FAKE_*` found
- Ensures vision doesn't influence corroboration

**Check 4: No vision upgrade language**
- Fails if phrases like "vision says real" found
- Ensures no trust upgrading language

**Check 5: Schema field safety**
- Fails if schema has `vision_verdict` or `vision_reasoning`
- Ensures response payload is veto-safe

### 3. Running Tests

```bash
# Golden tests (functional validation)
python tests/test_vision_veto_golden.py

# Comprehensive enforcement (code scanning)
python tests/test_veto_enforcement.py

# Or with pytest
pytest tests/test_vision_veto_golden.py -v
pytest tests/test_veto_enforcement.py -v
```

---

## Enforcement Mechanisms

### 1. Automated Code Scanning

The enforcement test scans all Python files and fails CI/CD if violations found:

```python
# Scans entire repository
python_files = project_root.rglob('*.py')
# Excludes: venv, build, __pycache__, etc.

# No broad skips - only pure comments
if stripped.startswith('#'):
    continue
```

### 2. Schema Validation

`ReceiptDecision` dataclass enforces veto-safe fields:

```python
@dataclass
class ReceiptDecision:
    # ✅ Allowed
    visual_integrity: Optional[str] = None
    vision_confidence: Optional[float] = None
    
    # ❌ Forbidden (removed)
    # vision_verdict: ...
    # vision_reasoning: ...
```

### 3. Import Restrictions

Only canonical function should be imported:

```python
# ✅ Correct
from app.pipelines.vision_llm import build_vision_assessment

# ❌ Forbidden
from app.pipelines.vision_llm import analyze_receipt_with_vision
from app.pipelines.vision_llm import get_hybrid_verdict
```

---

## Migration Guide

### For Developers

**If you see `vision_verdict` in code:**
1. Replace with `visual_integrity`
2. Update logic to handle "clean"|"suspicious"|"tampered"
3. Remove any trust upgrading logic

**If you see `authenticity_assessment`:**
1. Replace with `build_vision_assessment()`
2. Use new contract: `{visual_integrity, confidence, observable_reasons}`

**If you see vision-based corroboration:**
1. Remove vision from corroboration logic
2. Use only rules + extraction quality

### For API Consumers

**Response field changes:**
- `vision_verdict` → `visual_integrity`
- `vision_reasoning` → Not exposed (use audit trails)

**Interpretation:**
- `visual_integrity: "clean"` → Vision found no issues
- `visual_integrity: "suspicious"` → Vision found anomalies (audit only)
- `visual_integrity: "tampered"` → Vision detected tampering (receipt rejected)

---

## Audit Trail

### Vision Evidence in Audit Events

When vision detects tampering:

```python
{
    "code": "V1_VISION_TAMPERED",
    "severity": "HARD_FAIL",
    "message": "Vision detected clear tampering",
    "evidence": {
        "visual_integrity": "tampered",
        "confidence": 0.92,
        "observable_reasons": [
            "Clear editing artifacts around total amount",
            "Font inconsistency between merchant name and total"
        ]
    }
}
```

### Debug Info

Vision assessment always stored for audit:

```python
decision.debug = {
    "visual_integrity": "suspicious",
    "confidence": 0.65,
    "observable_reasons": [
        "Unusual spacing patterns",
        "Low-resolution merchant logo"
    ]
}
```

---

## Common Pitfalls

### ❌ DON'T: Use vision to upgrade trust

```python
# FORBIDDEN
if visual_integrity == "clean" and vision_confidence > 0.8:
    label = "real"  # Vision cannot approve!
```

### ❌ DON'T: Blend vision scores

```python
# FORBIDDEN
final_score = 0.5 * rule_score + 0.5 * vision_confidence
```

### ❌ DON'T: Use vision in corroboration

```python
# FORBIDDEN
if visual_integrity == "clean" and rule_label == "fake":
    corroboration_flags.append("VISION_CLEAN_RULES_FAKE")
```

### ✅ DO: Only veto on tampering

```python
# CORRECT
if visual_integrity == "tampered":
    emit_event("V1_VISION_TAMPERED", severity="HARD_FAIL")
    label = "fake"
```

### ✅ DO: Store for audit

```python
# CORRECT
decision.visual_integrity = visual_integrity
decision.vision_confidence = vision_confidence
decision.debug["observable_reasons"] = observable_reasons
```

---

## FAQ

**Q: Why can't vision say "real"?**

A: Vision models are prone to false positives. Allowing vision to approve receipts would create a bypass for sophisticated fakes. Vision is better at detecting obvious tampering than confirming authenticity.

**Q: What if vision says "suspicious"?**

A: Suspicious assessments are audit-only. They don't affect the decision but are stored for investigation. Rules still decide the outcome.

**Q: Can vision override a rule-based "real" decision?**

A: Only if vision detects tampering (`visual_integrity: "tampered"`). This triggers a HARD_FAIL veto. Vision cannot upgrade a "fake" to "real".

**Q: What happens if vision and rules disagree?**

A: Rules always decide, except for tampering veto. If rules say "fake" and vision says "clean", the receipt is still rejected. If rules say "real" and vision says "tampered", the receipt is rejected (veto).

**Q: How do I debug vision decisions?**

A: Check the audit trail for `V1_VISION_TAMPERED` events and inspect `decision.debug["observable_reasons"]` for specific evidence.

---

## References

- **Implementation:** `app/pipelines/vision_llm.py` (lines 493-595)
- **Golden Tests:** `tests/test_vision_veto_golden.py`
- **Enforcement:** `tests/test_veto_enforcement.py`
- **Schema:** `app/schemas/receipt.py` (lines 138-142)
- **Real Receipt Testing:** `REAL_RECEIPT_TESTING_GUIDE.md`

---

## Version History

- **v1.0 (2025-12-31):** Initial veto-only implementation
  - Created `build_vision_assessment()` canonical function
  - Removed `vision_verdict` and `authenticity_assessment`
  - Implemented V1_VISION_TAMPERED HARD_FAIL event
  - Added comprehensive enforcement tests
  - Fixed schema fields and corroboration logic
  - Updated streaming endpoint to be veto-safe

---

**Last Updated:** January 1, 2026  
**Status:** Production-Ready ✅
