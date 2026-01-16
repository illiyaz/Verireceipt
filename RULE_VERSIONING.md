# Rule Versioning Strategy

**Rules are append-only. Old rules are deprecated, not mutated.**

---

## 🎯 Core Principle

**No existing rule behavior may change without:**
1. Version bump
2. Golden test update
3. Explicit approval

---

## 📦 Versioning Scheme

Rules use semantic versioning: `MAJOR.MINOR`

### Version Format

```
R7B_INVOICE_TOTAL_RECONCILIATION.v1.0
R7B_INVOICE_TOTAL_RECONCILIATION.v1.1  (minor enhancement)
R7B_INVOICE_TOTAL_RECONCILIATION.v2.0  (breaking change)
```

### When to Bump Version

| Change Type | Version Bump | Example |
|-------------|--------------|---------|
| Bug fix (no behavior change) | None | Fix typo in evidence field |
| Enhancement (backward compatible) | MINOR | Add new optional field to evidence |
| Tolerance change | MINOR | Adjust tolerance from 2% to 2.5% |
| Gating change | MAJOR | Change confidence gate from 0.75 to 0.80 |
| Severity change | MAJOR | Change WARNING to CRITICAL |
| Scope change | MAJOR | Apply to new document types |

---

## 🔄 Migration Process

### Step 1: Create New Version

```python
# OLD (keep running)
"""
RULE_ID: R7B_INVOICE_TOTAL_RECONCILIATION
VERSION: 1.0
...
"""
if is_invoice_type and not is_credit_note:
    # ... existing logic ...

# NEW (run in parallel)
"""
RULE_ID: R7B_INVOICE_TOTAL_RECONCILIATION
VERSION: 2.0
CHANGES:
  - Stricter tolerance for TAX_INVOICE (1% vs 2%)
  - Added multi-currency skip logic
MIGRATION_PLAN: Run both v1.0 and v2.0 for 30 days, compare results
DEPRECATION_DATE: 2026-03-01
"""
if is_invoice_type and not is_credit_note:
    # ... new logic ...
```

### Step 2: Run Both Versions in Parallel

```python
# Emit events from both versions with version tag
result_v1 = run_r7b_v1(features)
result_v2 = run_r7b_v2(features)

# Log comparison for analysis
if result_v1.score != result_v2.score:
    logger.info(f"R7B version mismatch: v1={result_v1.score}, v2={result_v2.score}")

# Use v1 for decision (safe), log v2 for monitoring
return result_v1
```

### Step 3: Analyze Results

Monitor for 30 days:
- Compare v1 vs v2 scores
- Check for unexpected v2 behavior
- Validate v2 doesn't increase false positives

### Step 4: Cutover

Once v2 is validated:
```python
# Use v2 for decision
return result_v2

# Mark v1 as deprecated
"""
RULE_ID: R7B_INVOICE_TOTAL_RECONCILIATION
VERSION: 1.0
STATUS: DEPRECATED (use v2.0)
DEPRECATED_DATE: 2026-03-01
"""
```

### Step 5: Remove Old Version

After 90 days of v2 stability:
- Remove v1 code
- Archive v1 golden tests
- Update documentation

---

## 🧪 Golden Test Updates

When versioning a rule:

1. **Keep old golden test:**
   ```
   tests/golden/invoice.v1.json  (archived)
   ```

2. **Create new golden test:**
   ```
   tests/golden/invoice.v2.json  (active)
   ```

3. **Update test runner:**
   ```python
   # Run both versions during migration
   run_test("invoice.v1.json", rule_version="1.0")
   run_test("invoice.v2.json", rule_version="2.0")
   ```

---

## 📊 Version History

### Current Active Versions

| Rule ID | Version | Status | Golden Test |
|---------|---------|--------|-------------|
| R7_TOTAL_MISMATCH | 1.0 | ACTIVE | pos_receipt.json |
| R7B_INVOICE_TOTAL_RECONCILIATION | 1.0 | ACTIVE | invoice.json |
| R7C_CREDIT_NOTE_RECONCILIATION | 1.0 | ACTIVE | credit_note.json |

### Deprecated Versions

| Rule ID | Version | Deprecated Date | Reason |
|---------|---------|-----------------|--------|
| _(none yet)_ | - | - | - |

---

## 🚫 Anti-Patterns

**DO NOT:**
- ❌ Modify existing rule logic without version bump
- ❌ Change tolerance values "just to see what happens"
- ❌ Remove gating conditions to "fix" edge cases
- ❌ Delete old golden tests before 90-day stability period

**DO:**
- ✅ Create new version for any behavior change
- ✅ Run old and new versions in parallel
- ✅ Monitor metrics before cutover
- ✅ Keep audit trail of all changes

---

## 🔒 Enforcement

CI will block PRs that:
1. Modify rule logic without version bump
2. Change golden test expectations without version bump
3. Remove deprecated rules before 90-day period

---

## 📝 Example: R7B Enhancement

**Scenario:** Want to add shipping/discount extraction to R7B

**Wrong Approach:**
```python
# ❌ Modifying existing rule
if is_invoice_type:
    # Add shipping/discount logic here
```

**Correct Approach:**
```python
# ✅ Create R7B v1.1 (backward compatible enhancement)
"""
RULE_ID: R7B_INVOICE_TOTAL_RECONCILIATION
VERSION: 1.1
CHANGES:
  - Added opportunistic shipping/discount extraction
  - Backward compatible: if shipping/discount not found, behaves like v1.0
GOLDEN_TEST: tests/golden/invoice.v1.1.json
"""
```

Since this is backward compatible (doesn't change behavior for existing invoices), it's a MINOR bump (1.0 → 1.1).

---

## 🎯 Summary

**Rules are immutable once deployed.**

To change a rule:
1. Bump version
2. Update golden test
3. Run in parallel
4. Monitor metrics
5. Cutover when safe
6. Deprecate old version
7. Remove after 90 days

This prevents regressions and maintains audit trail.
