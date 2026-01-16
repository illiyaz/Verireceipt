# Rule × Document Family Allow-List Matrix

**Principle:** A rule may ONLY execute if it is explicitly allowed for that document family. Absence from the matrix = forbidden.

**This prevents:**
- "Rule bleed"
- Accidental reuse
- Clever refactors breaking safety

---

## 📊 Canonical Rule × Family Matrix (v1.0)

| Rule ID | POS_RECEIPT | COMMERCIAL_INVOICE | TAX_INVOICE* | CREDIT_NOTE | LOGISTICS | SUBSCRIPTION | REIMBURSEMENT | UNKNOWN |
|---------|-------------|-------------------|--------------|-------------|-----------|--------------|---------------|---------|
| **R7_TOTAL_MISMATCH** | 🔴 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **R7B_INVOICE_TOTAL_RECONCILIATION** | ❌ | 🔴 | 🔴 | ❌ | ❌ | 🟡 | ❌ | ❌ |
| **R7C_CREDIT_NOTE_RECONCILIATION** | ❌ | ❌ | 🟡 | 🔴 | ❌ | ❌ | ❌ | ❌ |
| **LR_SPACING_ANOMALY** | 🔴 | 🟡 | 🟡 | 🟡 | ❌ | 🟡 | ❌ | ❌ |
| **VISION_HARD_FAIL_VETO** | 🔴 | 🔴 | 🔴 | 🔴 | 🔴 | 🔴 | 🟡 | 🟡 |
| **DATE_SANITY** | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | ❌ |
| **CURRENCY_CONSISTENCY** | 🟡 | 🔴 | 🔴 | 🟡 | ❌ | 🟡 | ❌ | ❌ |

**Legend (Explicit Execution Modes):**
- 🔴 **BLOCK** = Full enforcement (rule fires, contributes to score, can block decision)
- 🟡 **SOFT** = Soft enforcement (rule fires, logs warning, minimal score contribution)
- 🔵 **AUDIT** = Audit only (rule fires, logs for analysis, zero score contribution)
- ❌ **FORBIDDEN** = Silent skip (rule does not execute)

**\* TAX_INVOICE is a subtype of COMMERCIAL_INVOICE (inherits + tightens rules)**

---

## 🔒 Enforcement in Code

Every rule **MUST** declare:

```python
"""
RULE_ID: R7B_INVOICE_TOTAL_RECONCILIATION
ALLOWED_DOC_FAMILIES: ["COMMERCIAL_INVOICE", "TAX_INVOICE"]
"""
```

The engine enforces with **explicit execution modes**:

```python
from app.pipelines.rule_family_matrix import get_execution_mode, ExecutionMode

execution_mode = get_execution_mode("R7B_INVOICE_TOTAL_RECONCILIATION", doc_family)

if execution_mode == ExecutionMode.FORBIDDEN:
    return  # silent skip

# Handle SOFT mode (minimal score contribution)
if execution_mode == ExecutionMode.SOFT:
    severity_cap = "WARNING"  # never CRITICAL
    score_multiplier = 0.3  # reduced impact

# Handle AUDIT mode (zero score contribution)
if execution_mode == ExecutionMode.AUDIT:
    score_multiplier = 0.0  # log only, no score
```

**No conditionals, no clever overrides. Execution mode is machine-enforceable.**

---

## 🧠 Why This Matters

**Two-layer safety:**
1. ✅ Golden tests validate behavior per family
2. ✅ Allow-list prevents execution outside scope

**Benefits:**
- You can add rules safely without re-reading the whole system
- A new rule cannot "accidentally" affect POS or UNKNOWN docs
- Clear audit trail of what runs where

---

## 📝 Current Rule Compliance

### R7_TOTAL_MISMATCH
```python
ALLOWED_DOC_FAMILIES = ["POS_RECEIPT", "POS_RESTAURANT", "POS_RETAIL"]
```
**Status:** ✅ Compliant

### R7B_INVOICE_TOTAL_RECONCILIATION
```python
ALLOWED_DOC_FAMILIES = ["COMMERCIAL_INVOICE", "TAX_INVOICE"]
```
**Status:** ✅ Compliant

### R7C_CREDIT_NOTE_RECONCILIATION
```python
ALLOWED_DOC_FAMILIES = ["CREDIT_NOTE"]
```
**Status:** ✅ Compliant

---

## 🚨 Adding a New Rule

When adding a new rule:

1. **Declare allowed families in header:**
   ```python
   """
   RULE_ID: R8_NEW_RULE
   ALLOWED_DOC_FAMILIES: ["COMMERCIAL_INVOICE"]
   """
   ```

2. **Add to matrix above**

3. **Enforce in code:**
   ```python
   ALLOWED_DOC_FAMILIES = {"COMMERCIAL_INVOICE"}
   
   if doc_family not in ALLOWED_DOC_FAMILIES:
       return  # silent skip
   ```

4. **Update golden tests** for each allowed family

---

## 🔐 CI Enforcement

The CI will block PRs that:
1. Add a rule without `ALLOWED_DOC_FAMILIES` declaration
2. Execute a rule outside its allow-list
3. Modify the matrix without explicit approval

See: `.github/workflows/rule_pr_gate.yml`

---

## 📊 Matrix Evolution

**Version History:**

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-12 | Initial matrix with R7, R7B, R7C |

**To update the matrix:**
1. Increment version
2. Document changes
3. Update all affected golden tests
4. Get explicit approval

**The matrix is append-only. Old versions are archived, not mutated.**
