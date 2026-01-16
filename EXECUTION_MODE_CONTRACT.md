# Execution Mode Contract

**Explicit, machine-enforceable execution modes for the Rule × Family Matrix.**

---

## 🎯 The Problem

Without explicit execution modes, "soft" enforcement is ambiguous:
- Does "soft" mean lower score?
- Does it mean log-only?
- Can it still block decisions?
- How do we enforce it in code?

**Solution:** Formalize execution modes as an enum.

---

## 🔴 🟡 🔵 ❌ The Four Modes

### 🔴 BLOCK (Full Enforcement)
**Rule fires, contributes to score, can block decision**

**When to use:**
- Core fraud detection rules
- High-confidence document families
- Rules that should prevent approval

**Example:**
- R7 on POS_RECEIPT
- R7B on COMMERCIAL_INVOICE

**Code behavior:**
```python
execution_mode = ExecutionMode.BLOCK

# Rule fires normally
score_contribution = calculate_score()  # Full weight
severity = determine_severity()  # Can be CRITICAL
decision_impact = True  # Can block approval
```

---

### 🟡 SOFT (Soft Enforcement)
**Rule fires, logs warning, minimal score contribution**

**When to use:**
- Document families where rule is relevant but noisy
- Experimental rules being validated
- Rules that should warn but not block

**Example:**
- R7B on SUBSCRIPTION (invoices are messy, proration common)
- R7C on TAX_INVOICE (credit notes can be tax invoices, but rare)

**Code behavior:**
```python
execution_mode = ExecutionMode.SOFT

# Rule fires with reduced impact
score_contribution = calculate_score() * 0.3  # 30% weight
severity = min(severity, "WARNING")  # Never CRITICAL
decision_impact = False  # Cannot block approval
logger.warning(f"[SOFT] {rule_id} fired on {doc_family}")
```

---

### 🔵 AUDIT (Audit Only)
**Rule fires, logs for analysis, zero score contribution**

**When to use:**
- Rules being tested before promotion to SOFT/BLOCK
- Data collection for future rule development
- Monitoring without decision impact

**Example:**
- New experimental rules
- Rules for analytics/reporting only

**Code behavior:**
```python
execution_mode = ExecutionMode.AUDIT

# Rule fires but has zero impact
score_contribution = 0.0  # No score impact
severity = "INFO"  # Always INFO
decision_impact = False  # Cannot block approval
logger.info(f"[AUDIT] {rule_id} fired on {doc_family}")
audit_log.append({"rule": rule_id, "family": doc_family, "result": result})
```

---

### ❌ FORBIDDEN (Silent Skip)
**Rule does not execute**

**When to use:**
- Document families where rule is not applicable
- Prevents rule bleed
- Default for unknown families

**Example:**
- R7 (POS) on COMMERCIAL_INVOICE
- R7B (Invoice) on POS_RECEIPT

**Code behavior:**
```python
execution_mode = ExecutionMode.FORBIDDEN

# Rule does not execute
return  # Silent skip
logger.debug(f"{rule_id} skipped: {doc_family} forbidden")
```

---

## 📊 Current Matrix (v1.0)

| Rule | POS | INVOICE | TAX_INV | CREDIT | SUBSCRIPTION |
|------|-----|---------|---------|--------|--------------|
| **R7** | 🔴 | ❌ | ❌ | ❌ | ❌ |
| **R7B** | ❌ | 🔴 | 🔴 | ❌ | 🟡 |
| **R7C** | ❌ | ❌ | 🟡 | 🔴 | ❌ |

**Rationale:**
- R7B on SUBSCRIPTION: 🟡 SOFT because subscription invoices have proration, discounts, complex line items
- R7C on TAX_INVOICE: 🟡 SOFT because credit notes can be tax invoices, but it's rare and messy

---

## 🔒 Enforcement in Code

### Declaration
```python
"""
RULE_ID: R7B_INVOICE_TOTAL_RECONCILIATION
ALLOWED_DOC_FAMILIES: ["COMMERCIAL_INVOICE", "TAX_INVOICE"]
"""
```

### Execution
```python
from app.pipelines.rule_family_matrix import get_execution_mode, ExecutionMode

execution_mode = get_execution_mode("R7B_INVOICE_TOTAL_RECONCILIATION", doc_family)

if execution_mode == ExecutionMode.FORBIDDEN:
    return  # Silent skip

# Apply mode-specific behavior
if execution_mode == ExecutionMode.BLOCK:
    score_multiplier = 1.0
    severity_cap = None  # No cap
elif execution_mode == ExecutionMode.SOFT:
    score_multiplier = 0.3
    severity_cap = "WARNING"
elif execution_mode == ExecutionMode.AUDIT:
    score_multiplier = 0.0
    severity_cap = "INFO"

# Calculate score with mode-specific multiplier
score_contribution = base_score * score_multiplier
```

---

## 🧪 Mode Transitions

**Rules can transition between modes as they mature:**

```
AUDIT → SOFT → BLOCK
  ↓       ↓       ↓
(test)  (warn)  (enforce)
```

**Example lifecycle:**
1. **New rule:** Start in AUDIT mode on target family
2. **Validation:** Collect data, tune thresholds
3. **Promotion:** Move to SOFT mode (warn but don't block)
4. **Maturity:** Move to BLOCK mode (full enforcement)

**Requires:**
- Matrix version bump
- Golden test update
- Explicit approval

---

## 🚨 Critical Invariants

1. ✅ **Execution mode is machine-enforceable**
   - No ambiguity around "soft"
   - Code enforces mode-specific behavior
   - CI validates mode declarations

2. ✅ **SOFT mode never blocks decisions**
   - Severity capped at WARNING
   - Score contribution reduced (30%)
   - Cannot force "fake" decision

3. ✅ **AUDIT mode has zero score impact**
   - Always INFO severity
   - Score contribution = 0.0
   - Logs only, no decision impact

4. ✅ **Mode changes require version bump**
   - Matrix is versioned
   - Changes need approval
   - Golden tests updated

---

## 📝 Why This Works

**Prevents ambiguity:**
- "Soft" is now explicit: 30% score, WARNING cap
- "Audit" is now explicit: 0% score, INFO only
- No more "allowed but don't score" confusion

**Machine-enforceable:**
- Enum-based, not string-based
- Type-safe in Python
- CI can validate

**Future-proof:**
- Easy to add new modes (e.g., EXPERIMENTAL)
- Clear upgrade path (AUDIT → SOFT → BLOCK)
- Versioned and auditable

---

## 🔐 The Contract

**Every rule × family combination has ONE execution mode:**
- 🔴 BLOCK
- 🟡 SOFT
- 🔵 AUDIT
- ❌ FORBIDDEN

**No exceptions. No clever overrides. Machine-enforceable.**

**This is the final piece of the entropy lock.** 🚀
