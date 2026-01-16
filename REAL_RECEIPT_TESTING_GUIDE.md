# Real Receipt Testing Guide - Vision Veto System Validation

## ✅ Golden Tests Complete (3/3 Passing)

The vision veto system has passed all golden tests:
- ✅ **CLEAN** vision → rules decide (no interference)
- ✅ **SUSPICIOUS** vision → rules decide (audit-only)
- ✅ **TAMPERED** vision → HARD_FAIL (veto triggers)

Now we need to validate with **10-15 real receipts** to ensure the system works correctly in production.

---

## 📋 Testing Plan

### **Phase 1: Known Good Receipts (5 receipts)**
Test receipts you know are authentic and legitimate.

**Expected Behavior:**
- Vision returns `visual_integrity: "clean"` or `"suspicious"`
- No `V1_VISION_TAMPERED` event
- Decision based on rules (likely `label: "real"` with low score)
- No vision interference in reasoning

**What to Check:**
1. Final decision label and score
2. No "vision said real" language in reasons
3. Vision assessment in debug (for audit)
4. Rules reasoning unchanged

---

### **Phase 2: Obvious Fake Receipts (5 receipts)**
Test receipts you know are fake or heavily edited.

**Expected Behavior:**
- Vision may return `visual_integrity: "tampered"` if editing is visible
- If tampered: `V1_VISION_TAMPERED` HARD_FAIL → `label: "fake"`
- If not tampered: Rules catch it anyway → `label: "fake"`
- Observable reasons captured in evidence

**What to Check:**
1. Rules catch fakes even without vision veto
2. Vision veto only triggers for visually tampered receipts
3. Observable reasons are meaningful and specific
4. No false positives from vision

---

### **Phase 3: Borderline Receipts (5 receipts)**
Test receipts that are ambiguous or have quality issues.

**Expected Behavior:**
- Vision may return `"suspicious"` (audit-only, no veto)
- Decision based entirely on rules
- Suspicious assessment stored in debug
- Observable reasons help with investigation

**What to Check:**
1. Vision does NOT force decision
2. Rules make the final call
3. Suspicious reasons are helpful for audit
4. No vision upgrade language

---

## 🧪 How to Test

### **Option 1: Web UI Testing**

1. Start the server:
   ```bash
   cd /Users/LENOVO/Documents/Projects/VeriReceipt
   uvicorn app.api.main:app --reload --port 8000
   ```

2. Open browser: `http://localhost:8000`

3. Upload receipt and inspect:
   - Final verdict (real/fake/suspicious)
   - Audit report (check for vision events)
   - Reasoning (check for "vision said real")
   - Debug info (vision_assessment)

### **Option 2: API Testing**

```bash
# Test a receipt via API
curl -X POST "http://localhost:8000/api/v1/receipts/analyze-hybrid" \
  -F "file=@/path/to/receipt.jpg"
```

Inspect the JSON response:
```json
{
  "decision": {
    "label": "fake",
    "score": 0.85,
    "reasons": [
      "[HARD_FAIL] 🚨 Vision detected clear tampering (veto)",
      "..."
    ]
  },
  "audit_report": "...",
  "debug": {
    "vision_assessment": {
      "visual_integrity": "tampered",
      "confidence": 0.92,
      "observable_reasons": [...]
    }
  }
}
```

### **Option 3: Python Script Testing**

Create a test script:

```python
from app.pipelines.rules import analyze_receipt
from app.pipelines.vision_llm import build_vision_assessment

# Test a receipt
receipt_path = "/path/to/receipt.jpg"

# Get vision assessment
vision_assessment = build_vision_assessment(receipt_path)
print(f"Vision: {vision_assessment['visual_integrity']}")

# Analyze with rules
decision = analyze_receipt(
    receipt_path,
    vision_assessment=vision_assessment
)

print(f"Decision: {decision.label} (score: {decision.score:.2f})")
print(f"Reasons: {decision.reasons[:5]}")

# Check for vision veto
vision_events = [e for e in decision.events if e.get("rule_id") == "V1_VISION_TAMPERED"]
if vision_events:
    print(f"⚠️  Vision veto triggered!")
else:
    print(f"✅ No vision veto (rules decided)")
```

---

## 🔍 Audit Trail Inspection Checklist

For each receipt, verify:

### **1. Vision Evidence is Readable**
- [ ] `visual_integrity` is one of: `clean`, `suspicious`, `tampered`
- [ ] `confidence` is between 0.0-1.0
- [ ] `observable_reasons` are specific and verifiable
- [ ] Evidence stored in `debug.vision_assessment`

### **2. Rule Reasoning is Unchanged**
- [ ] Reasons mention specific rule violations
- [ ] No generic "vision said X" language
- [ ] Rule-based scoring is primary
- [ ] HARD_FAIL events are from rules, not vision (except V1_VISION_TAMPERED)

### **3. No "Vision Said Real" Language**
Search for these phrases (should NOT appear):
- ❌ "Vision LLM confirms authenticity"
- ❌ "Vision model says real"
- ❌ "Vision indicates authentic"
- ❌ "Both engines agree: real"

Acceptable phrases:
- ✅ "Vision detected clear tampering (veto)"
- ✅ "Vision assessment: suspicious (audit-only)"
- ✅ "Vision evidence stored for audit"

### **4. Vision Veto Behavior**
- [ ] `clean` → no veto, rules decide
- [ ] `suspicious` → no veto, rules decide (audit-only)
- [ ] `tampered` → HARD_FAIL veto, label=fake

---

## 📊 Expected Results Summary

| Scenario | Vision | V1_VISION_TAMPERED | Final Label | Decision By |
|----------|--------|-------------------|-------------|-------------|
| Good receipt, clean scan | clean | ❌ No | real | Rules |
| Good receipt, poor quality | suspicious | ❌ No | real | Rules |
| Fake receipt, no editing | clean/suspicious | ❌ No | fake | Rules |
| Fake receipt, edited | **tampered** | ✅ **Yes** | **fake** | **Vision Veto** |
| Borderline, suspicious | suspicious | ❌ No | suspicious | Rules |

---

## 🚨 Red Flags to Watch For

### **Critical Issues:**
1. **Vision upgrading trust**: "Vision said real" language in reasons
2. **Vision overriding rules**: Clean receipt marked fake due to vision
3. **Suspicious triggering veto**: `suspicious` causing HARD_FAIL
4. **Missing veto**: Clear tampering not triggering V1_VISION_TAMPERED

### **Minor Issues:**
1. **Vague observable reasons**: "Looks suspicious" instead of specific artifacts
2. **Low confidence on clear tampering**: Should be >0.7 for HARD_FAIL
3. **Missing debug info**: vision_assessment not in debug

---

## 📝 Testing Log Template

Use this template to document each test:

```markdown
### Receipt #1: [Description]
- **Category**: Good / Fake / Borderline
- **File**: receipt_001.jpg
- **Vision Result**: clean / suspicious / tampered (confidence: 0.XX)
- **Observable Reasons**: [list]
- **V1_VISION_TAMPERED**: Yes / No
- **Final Label**: real / fake / suspicious (score: 0.XX)
- **Decision By**: Rules / Vision Veto
- **Issues Found**: None / [describe]
- **Notes**: [any observations]
```

---

## ✅ Success Criteria

The vision veto system is working correctly if:

1. **No false positives from vision**
   - Clean receipts are not vetoed
   - Vision doesn't force "fake" on good receipts

2. **Rules stay primary**
   - Most decisions made by rules
   - Vision only vetoes clear tampering

3. **Audit trails are clear**
   - Observable reasons are specific
   - No "vision said real" language
   - Evidence captured for investigation

4. **Veto triggers correctly**
   - Tampered receipts trigger V1_VISION_TAMPERED
   - HARD_FAIL drives label to "fake"
   - Observable reasons explain why

---

## 🚀 Ready to Test!

1. Gather 10-15 real receipts (5 good, 5 fake, 5 borderline)
2. Test each receipt using one of the methods above
3. Document results using the testing log template
4. Review audit trails for red flags
5. Report any issues found

**Server is running at:** `http://127.0.0.1:8000`

**Golden tests passed:** 3/3 ✅

**System status:** Ready for production validation 🎯
