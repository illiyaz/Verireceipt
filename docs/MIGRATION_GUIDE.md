# Migration Guide: Vision Verdict → Visual Integrity

## Overview

This guide helps developers migrate from the old `vision_verdict` system to the new **veto-only** `visual_integrity` design.

---

## Why the Change?

### Problems with Old Design

1. **Trust Upgrading:** Vision could say "real" and override rule-based rejections
2. **Probabilistic Blending:** Vision scores were weighted with rule scores
3. **Inconsistent Decisions:** Different code paths had different vision logic
4. **False Positives:** Vision models are better at detecting tampering than confirming authenticity

### New Design Benefits

1. **Veto-Only:** Vision can only reject (detect tampering), never approve
2. **Consistent:** Single entry point, single contract
3. **Auditable:** Clear evidence trail for vision decisions
4. **Safe:** No false positives leading to approval

---

## Breaking Changes

### 1. Field Name Changes

| Old Field | New Field | Type Change |
|-----------|-----------|-------------|
| `vision_verdict` | `visual_integrity` | "real"/"fake" → "clean"/"suspicious"/"tampered" |
| `vision_reasoning` | N/A (removed) | Use `observable_reasons` in audit |
| `vision_confidence` | `vision_confidence` | No change (0.0-1.0) |

### 2. Function Changes

| Old Function | New Function | Status |
|--------------|--------------|--------|
| `analyze_receipt_with_vision()` | `build_vision_assessment()` | ✅ Use new |
| `get_hybrid_verdict()` | N/A | ❌ Removed |
| `run_vision_authenticity()` | N/A | ❌ Deprecated |

### 3. Response Structure Changes

**Before:**
```json
{
  "vision_verdict": "real",
  "vision_confidence": 0.90,
  "vision_reasoning": "Receipt appears authentic",
  "authenticity_assessment": {
    "verdict": "real",
    "confidence": 0.90,
    "authenticity_score": 0.85
  }
}
```

**After:**
```json
{
  "visual_integrity": "clean",
  "vision_confidence": 0.90
}
```

---

## Migration Steps

### Step 1: Update Imports

**Before:**
```python
from app.pipelines.vision_llm import analyze_receipt_with_vision
```

**After:**
```python
from app.pipelines.vision_llm import build_vision_assessment
```

### Step 2: Update Function Calls

**Before:**
```python
vision_results = analyze_receipt_with_vision(image_path)
auth = vision_results.get("authenticity_assessment", {})
verdict = auth.get("verdict")
confidence = auth.get("confidence")
reasoning = auth.get("reasoning")
```

**After:**
```python
vision_assessment = build_vision_assessment(image_path)
visual_integrity = vision_assessment.get("visual_integrity")
confidence = vision_assessment.get("confidence")
observable_reasons = vision_assessment.get("observable_reasons", [])
```

### Step 3: Update Decision Logic

**Before (WRONG - allowed trust upgrading):**
```python
if vision_verdict == "real" and vision_confidence > 0.7:
    final_label = "real"
    final_confidence = 0.95
elif vision_verdict == "fake" and vision_confidence > 0.7:
    final_label = "fake"
    final_confidence = 0.90
```

**After (CORRECT - veto-only):**
```python
# Vision veto already applied in rule-based engine
# Only check for tampering in audit trail
if visual_integrity == "tampered":
    # This should already be handled by V1_VISION_TAMPERED event
    # Just log for transparency
    logger.info("Vision veto triggered: tampering detected")

# Rules decide for all other cases
final_label = rule_label
final_confidence = rule_score
```

### Step 4: Update Response Handling

**Before:**
```python
response = {
    "label": final_label,
    "score": final_score,
    "vision_verdict": vision_verdict,
    "vision_confidence": vision_confidence,
    "vision_reasoning": vision_reasoning
}
```

**After:**
```python
response = {
    "label": final_label,
    "score": final_score,
    "visual_integrity": visual_integrity,
    "vision_confidence": vision_confidence
    # observable_reasons stored in debug/audit only
}
```

### Step 5: Remove Corroboration Logic

**Before (WRONG - vision influenced corroboration):**
```python
if vision_verdict == "real" and rule_label == "fake":
    corroboration_flags.append("VISION_REAL_RULES_FAKE")
    corroboration_score -= 0.25

if vision_verdict == "real" and layoutlm_missing_total:
    corroboration_flags.append("VISION_REAL_LAYOUT_MISSING_TOTAL")
```

**After (CORRECT - vision-free corroboration):**
```python
# Vision is NOT part of corroboration
# Only rules + extraction quality
if critical_count > 0:
    corroboration_score -= 0.25

if layoutlm_extracted and layoutlm_extracted.get("total"):
    corroboration_score += 0.25
```

---

## Code Examples

### Example 1: Basic Vision Check

**Before:**
```python
def check_receipt(image_path):
    vision_results = analyze_receipt_with_vision(image_path)
    auth = vision_results.get("authenticity_assessment", {})
    
    if auth.get("verdict") == "real":
        return "approved"
    elif auth.get("verdict") == "fake":
        return "rejected"
    else:
        return "review"
```

**After:**
```python
def check_receipt(image_path):
    # Vision is veto-only - use rules for primary decision
    rule_decision = run_rule_based_analysis(image_path)
    vision_assessment = build_vision_assessment(image_path)
    
    # Only veto if tampering detected
    if vision_assessment.get("visual_integrity") == "tampered":
        return "rejected"  # Vision veto
    
    # Otherwise, rules decide
    if rule_decision["label"] == "real":
        return "approved"
    elif rule_decision["label"] == "fake":
        return "rejected"
    else:
        return "review"
```

### Example 2: Hybrid Decision

**Before:**
```python
def hybrid_decision(rule_result, vision_result):
    rule_score = rule_result["score"]
    vision_verdict = vision_result["authenticity_assessment"]["verdict"]
    vision_confidence = vision_result["authenticity_assessment"]["confidence"]
    
    # Blending logic (WRONG)
    if rule_score < 0.3 and vision_verdict == "real":
        return {"label": "real", "confidence": 0.85}
    elif rule_score > 0.7 and vision_verdict == "fake":
        return {"label": "fake", "confidence": 0.90}
    else:
        # Average scores (WRONG)
        final_score = (rule_score + vision_confidence) / 2
        return {"label": "suspicious", "confidence": final_score}
```

**After:**
```python
def hybrid_decision(rule_result, vision_assessment):
    # Vision veto already applied in rule_result
    # No blending - rules decide
    
    rule_label = rule_result["label"]
    rule_score = rule_result["score"]
    visual_integrity = vision_assessment.get("visual_integrity")
    
    # Vision assessment stored for audit only
    # (tampering already handled by V1_VISION_TAMPERED in rules)
    
    return {
        "label": rule_label,
        "confidence": rule_score,
        "visual_integrity": visual_integrity  # Audit only
    }
```

### Example 3: Streaming Endpoint

**Before:**
```python
def run_vision():
    vision_results = analyze_receipt_with_vision(image_path)
    auth = vision_results.get("authenticity_assessment", {})
    
    return {
        "verdict": auth.get("verdict"),
        "confidence": auth.get("confidence"),
        "reasoning": auth.get("reasoning")
    }
```

**After:**
```python
def run_vision():
    vision_assessment = build_vision_assessment(image_path)
    
    return {
        "visual_integrity": vision_assessment.get("visual_integrity"),
        "confidence": vision_assessment.get("confidence"),
        "observable_reasons": vision_assessment.get("observable_reasons", [])
    }
```

---

## Schema Migration

### ReceiptDecision Dataclass

**Before:**
```python
@dataclass
class ReceiptDecision:
    label: str
    score: float
    vision_verdict: Optional[str] = None
    vision_confidence: Optional[float] = None
    vision_reasoning: Optional[str] = None
```

**After:**
```python
@dataclass
class ReceiptDecision:
    label: str
    score: float
    visual_integrity: Optional[str] = None
    vision_confidence: Optional[float] = None
    # vision_reasoning removed - use debug/audit
```

### Database Schema

If you store decisions in a database:

**Migration SQL:**
```sql
-- Add new column
ALTER TABLE receipt_decisions 
ADD COLUMN visual_integrity VARCHAR(20);

-- Migrate data
UPDATE receipt_decisions 
SET visual_integrity = CASE 
    WHEN vision_verdict = 'real' THEN 'clean'
    WHEN vision_verdict = 'fake' THEN 'tampered'
    ELSE 'suspicious'
END;

-- Drop old columns
ALTER TABLE receipt_decisions 
DROP COLUMN vision_verdict,
DROP COLUMN vision_reasoning;
```

---

## Testing Your Migration

### 1. Run Enforcement Tests

```bash
# Check for violations
python tests/test_veto_enforcement.py

# Should pass all 5 checks:
# ✅ No vision_verdict
# ✅ No authenticity_assessment
# ✅ No vision corroboration flags
# ✅ No vision upgrade language
# ✅ Schema fields veto-safe
```

### 2. Run Golden Tests

```bash
# Validate veto-only behavior
python tests/test_vision_veto_golden.py

# Should pass all 3 scenarios:
# ✅ CLEAN → rules decide
# ✅ SUSPICIOUS → rules decide (audit-only)
# ✅ TAMPERED → HARD_FAIL
```

### 3. Manual Testing

```python
# Test clean vision
assessment = build_vision_assessment("clean_receipt.jpg")
assert assessment["visual_integrity"] == "clean"
# Decision should be based on rules only

# Test tampered vision
assessment = build_vision_assessment("tampered_receipt.jpg")
assert assessment["visual_integrity"] == "tampered"
# Decision should be "fake" regardless of rules
```

---

## Common Migration Errors

### Error 1: Still Using vision_verdict

**Symptom:**
```python
AttributeError: 'dict' object has no attribute 'vision_verdict'
```

**Fix:**
```python
# Before
verdict = result.vision_verdict

# After
visual_integrity = result.visual_integrity
```

### Error 2: Expecting "real" or "fake"

**Symptom:**
```python
if visual_integrity == "real":  # This will never be true!
    approve()
```

**Fix:**
```python
# Vision can only say "clean", "suspicious", or "tampered"
if visual_integrity == "clean":
    # This means no tampering detected, but rules still decide
    pass
```

### Error 3: Blending Scores

**Symptom:**
```python
final_score = 0.5 * rule_score + 0.5 * vision_confidence
```

**Fix:**
```python
# Don't blend - rules decide
final_score = rule_score
# Vision confidence is for audit only
```

### Error 4: Vision in Corroboration

**Symptom:**
```python
if visual_integrity == "clean" and rule_label == "fake":
    corroboration_score -= 0.25
```

**Fix:**
```python
# Vision is NOT part of corroboration
# Remove all vision-based corroboration logic
```

---

## Rollback Plan

If you need to rollback temporarily:

1. **Keep old functions** (marked as deprecated)
2. **Feature flag** to switch between old/new
3. **Parallel testing** with both systems

**Example:**
```python
USE_VETO_ONLY = os.getenv("USE_VETO_ONLY", "true") == "true"

if USE_VETO_ONLY:
    vision_assessment = build_vision_assessment(image_path)
    visual_integrity = vision_assessment["visual_integrity"]
else:
    # Old system (deprecated)
    vision_results = analyze_receipt_with_vision(image_path)
    vision_verdict = vision_results["authenticity_assessment"]["verdict"]
```

---

## FAQ

**Q: Can I still access the old `authenticity_assessment` structure?**

A: Yes, it's available in `vision_assessment["raw"]["authenticity_assessment"]` for debugging, but should not be used for decisions.

**Q: What if my code relies on vision saying "real"?**

A: This is a design violation. Vision should never approve receipts. Refactor to use rule-based decisions with vision veto for tampering only.

**Q: How do I handle "suspicious" assessments?**

A: Suspicious is audit-only. Store it in debug/audit trails but don't change the decision. Rules still decide.

**Q: Will this break my existing API clients?**

A: Yes, if they expect `vision_verdict`. Update clients to use `visual_integrity` and handle the new values ("clean"/"suspicious"/"tampered").

**Q: Can I gradually migrate?**

A: Yes, use feature flags and parallel testing. But ensure enforcement tests pass before full deployment.

---

## Checklist

- [ ] Updated all imports to use `build_vision_assessment()`
- [ ] Replaced `vision_verdict` with `visual_integrity`
- [ ] Removed `vision_reasoning` usage
- [ ] Updated decision logic to be veto-only
- [ ] Removed vision from corroboration
- [ ] Updated response schemas
- [ ] Updated database schemas (if applicable)
- [ ] Updated API documentation
- [ ] Updated client code
- [ ] Ran enforcement tests (all passing)
- [ ] Ran golden tests (all passing)
- [ ] Tested with real receipts
- [ ] Updated monitoring/alerts

---

## Support

If you encounter issues during migration:

1. **Check enforcement tests:** `python tests/test_veto_enforcement.py`
2. **Review design doc:** `docs/VISION_VETO_DESIGN.md`
3. **Check API docs:** `docs/API_DOCUMENTATION.md`
4. **Run golden tests:** `python tests/test_vision_veto_golden.py`

---

**Last Updated:** January 1, 2026  
**Migration Status:** Required for all production deployments
