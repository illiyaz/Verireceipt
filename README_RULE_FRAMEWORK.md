# VeriReceipt Rule Framework - Lock-In Complete ✅

**The system works. The architecture is clean. The instincts are correct.**

This is the lock-in point to prevent future entropy.

---

## 🎯 What We Built

### 1. Rule Admission Policy (RAP) v1.0
**Location:** `RULE_ADMISSION_POLICY.md`

The constitution of the rules engine. Any rule that violates RAP **MUST NOT** be merged.

**6 Core Principles:**
- RAP-1: Bounded document scope
- RAP-2: Explicit confidence gate
- RAP-3: Safe degradation
- RAP-4: No structure invention
- RAP-5: Golden test requirement
- RAP-6: Append-only rules

### 2. Golden Test Framework
**Location:** `tests/golden_test_runner.py`

Canonical tests that lock in behavior per document family.

**6 Golden Tests:**
- `pos_receipt.json` - POS receipts
- `invoice.json` - Commercial invoices
- `credit_note.json` - Credit notes (sign-aware)
- `tax_invoice_india.json` - Indian GST invoices
- `logistics.json` - Shipping/delivery docs
- **`misc_safe.json`** - **CRITICAL** safety net

### 3. CI Enforcement
**Location:** `.github/workflows/rule_pr_gate.yml`

Automated PR gate that blocks:
- New rules without headers
- Golden test changes without approval
- Any rule firing in `misc_safe.json`

### 4. Rule Versioning Strategy
**Location:** `RULE_VERSIONING.md`

Rules are append-only. Old rules deprecated, not mutated.

---

## 🚀 Quick Start

### Run Golden Tests
```bash
# Run all tests
python tests/golden_test_runner.py

# Run specific test
python tests/golden_test_runner.py --test invoice

# Strict mode (fail on warnings)
python tests/golden_test_runner.py --strict

# Check critical safety net
python tests/golden_test_runner.py --check-misc
```

### Validate Rule Headers
```bash
python scripts/validate_rule_headers.py /tmp/new_rules.txt
```

---

## 📊 Current Rules Status

| Rule | Version | Scope | Gate | Test | Status |
|------|---------|-------|------|------|--------|
| R7 | 1.0 | POS_RECEIPT | profile | pos_receipt.json | ✅ |
| R7C | 1.0 | CREDIT_NOTE | dp_conf >= 0.75 | credit_note.json | ✅ |
| R7B | 1.0 | INVOICE | dp_conf >= 0.75 | invoice.json | ✅ |

---

## 🔒 The Lock-In

With RAP + Golden Tests + CI Gating, VeriReceipt is future-proofed.

**The only thing that can ruin this now is unchecked cleverness.**

---

## 📝 Adding a New Rule

1. Write rule with mandatory header
2. Create golden test
3. Run `python tests/golden_test_runner.py`
4. Ensure `misc_safe.json` still passes
5. Submit PR (CI will enforce RAP)

---

**This is the right lock-in point. Treat it as immutable.**
