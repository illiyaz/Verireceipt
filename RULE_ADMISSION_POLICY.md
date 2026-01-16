# Rule Admission Policy (RAP) v1.0

**The Constitution of VeriReceipt's Rules Engine**

Any rule that violates this policy **MUST NOT** be merged.

---

## 🧱 Core Principles

A rule MAY be added **ONLY IF ALL** conditions are met:

---

### RAP-0: A Rule Must Explain Why It Exists

**Every rule must document:**
1. The failure mode it addresses
2. A real-world example that triggered it
3. Why existing rules were insufficient

**Example:**
```python
"""
RULE_ID: R7B_INVOICE_TOTAL_RECONCILIATION
FAILURE_MODE_ADDRESSED: Edited invoice totals (e.g., $1000 → $10000)
REAL_WORLD_EXAMPLE: Vendor inflated total from $1,234 to $12,340 while keeping 
                     line items unchanged. R7 (POS) doesn't apply to invoices.
WHY_NEW_RULE: R7 only applies to POS receipts with line items. Invoices use 
              subtotal+tax reconciliation, not line-item sums.
"""
```

**Why this matters:**
- Prevents duplicate rules
- Prevents "because we saw it once" rules  
- Forces justification beyond cleverness
- **Critical 6-12 months from now** when context is lost

**❌ NOT ALLOWED:**
- "Catches anomalies"
- "Improves accuracy"
- "Handles edge cases"

**✅ ALLOWED:**
- Specific failure mode with concrete example
- Clear gap in existing coverage

---

### RAP-1: Bounded Document Scope

Every rule must declare **exactly one** of:
- `doc_family` OR
- `doc_subtype` OR  
- `document_intent`

**❌ NOT ALLOWED:**
- "Applies to all receipts"
- "Generic anomaly detection"
- "Fallback rule"

**✅ ALLOWED:**
- `doc_subtype == COMMERCIAL_INVOICE`
- `doc_family == TRANSACTIONAL`
- `intent == reimbursement`

**Why:** Prevents silent rule bleed across document types.

---

### RAP-2: Explicit Confidence Gate

Every rule must include **at least one** hard gating condition:

**Examples:**
```python
doc_profile_confidence >= 0.75
extraction_confidence_score >= 0.65
line_item_confidence >= 0.6
```

**❌ NOT ALLOWED:**
- Ungated pattern checks
- "Best effort" heuristics

**Why:** Low-confidence docs must never accumulate penalties.

---

### RAP-3: Safe Degradation

A rule must answer **YES** to:

> "If this rule misfires, will the decision still be reasonable?"

**Concrete Requirements:**
- ✅ No rule may force `fake`
- ✅ No rule may emit `HARD_FAIL` unless:
  - Legally impossible (e.g., invalid GSTIN checksum)
  - Cryptographically impossible
- ✅ Default severity: `WARNING`

---

### RAP-4: No Structure Invention

Rules **consume** extracted fields — they do **NOT** infer new ones.

**❌ NOT ALLOWED:**
- Guessing missing totals
- Reconstructing invoices
- "If tax missing, assume X%"

**✅ ALLOWED:**
- Opportunistic extraction (shipping, discount)
- Only if already present in text

---

### RAP-5: Golden Test Requirement

**No exceptions. No test → no rule.**

Golden test must prove:
1. ✅ One true positive
2. ✅ One false positive prevention
3. ✅ One gating scenario

---

### RAP-6: Append-Only Rules

**No existing rule behavior may change without:**
- Version bump (e.g., R7B → R7B.v2)
- Golden test update
- Explicit approval

**Old rules are deprecated, not mutated.**

---

### RAP-7: Document Family Cap

**Document families are capped at 7 (+ UNKNOWN). New families require policy change.**

**The 7 Core Families:**
1. POS_RECEIPT
2. COMMERCIAL_INVOICE
3. TAX_INVOICE (subtype of COMMERCIAL_INVOICE)
4. CREDIT_NOTE
5. LOGISTICS / SHIPPING_DOC
6. SUBSCRIPTION / SERVICE_STATEMENT
7. REIMBURSEMENT_SUPPORTING_DOC

**+ UNKNOWN / MISC (safety state, not a family)**

**Why this matters:**
- Prevents infinite taxonomy sprawl
- Keeps golden test matrix manageable
- Forces architectural review for new families
- 7 families cover 95-98% of real documents

**See:** `DOCUMENT_FAMILY_MODEL.md` for full taxonomy.

---

### RAP-8: Subtype Qualification Test

**A document may be introduced as a subtype ONLY if it passes the 5-question test.**

**The 5 Questions (ALL must be YES):**
1. Same economic intent?
2. Same core structure?
3. Same reconciliation math (maybe with constraints)?
4. Same failure modes?
5. Same severity ceiling?

**If ANY = NO → New Family (requires RAP-7 review)**

**Examples:**
- TAX_INVOICE → ✅ Subtype (all 5 YES)
- CREDIT_NOTE → ❌ New Family (sign-aware math, different intent)

**See:** `DOCUMENT_FAMILY_MODEL.md` for decision test details.

---

## 📜 Mandatory Rule Header Template

Every rule **MUST** start with this block:

```python
"""
RULE_ID: R7C_CREDIT_NOTE_RECONCILIATION
SCOPE: doc_subtype=COMMERCIAL_INVOICE AND is_credit_note=True
INTENT: billing, refund_verification

FAILURE_MODE_ADDRESSED: Credit notes with negative totals fail standard reconciliation
REAL_WORLD_EXAMPLE: Refund invoice with total=-$118 (subtotal=-$100, tax=-$18)
                     triggers false positive in R7B due to sign mismatch
WHY_NEW_RULE: R7B uses standard reconciliation math. Credit notes need sign-aware
              logic (abs() for ratio calculation) and softer severity.

CONFIDENCE_GATE:
  - doc_profile_confidence >= 0.75
  - fields_present >= 2
  - is_credit_note == True
FAILURE_MODE: soft_degrade
SEVERITY_RANGE: INFO → WARNING (never CRITICAL)
GOLDEN_TEST: tests/golden/credit_note.json
VERSION: 1.0
"""
```

**If this header is missing → reject PR.**

---

## 🚨 CI Enforcement

A PR is **BLOCKED** if:

1. ✅ A new rule ID is introduced without:
   - Header block
   - Golden test reference
2. ✅ Any golden test score changes without explicit approval
3. ✅ Any rule fires in `golden_misc_safe.json`

---

## 📊 Current Rules Compliance

| Rule ID | Scope | Gate | Test | Status |
|---------|-------|------|------|--------|
| R7_TOTAL_MISMATCH | POS_RECEIPT | profile_gating | ✅ | COMPLIANT |
| R7B_INVOICE_TOTAL_RECONCILIATION | INVOICE | dp_conf >= 0.75 | ✅ | COMPLIANT |
| R7C_CREDIT_NOTE_RECONCILIATION | CREDIT_NOTE | dp_conf >= 0.75 | ✅ | COMPLIANT |

---

## 🎯 Golden Test Matrix

| Document Family | Golden Test | Status |
|----------------|-------------|--------|
| POS_RECEIPT | `tests/golden/pos_receipt.json` | REQUIRED |
| COMMERCIAL_INVOICE | `tests/golden/invoice.json` | REQUIRED |
| CREDIT_NOTE | `tests/golden/credit_note.json` | REQUIRED |
| TAX_INVOICE (India) | `tests/golden/tax_invoice_india.json` | REQUIRED |
| TRANSPORT/LOGISTICS | `tests/golden/logistics.json` | REQUIRED |
| UNKNOWN/MISC | `tests/golden/misc_safe.json` | **CRITICAL** |

**The `misc_safe.json` test prevents 90% of future false positives.**

---

## 🔒 Lock-In Point

**This is the constitution. Treat it as immutable.**

With RAP + Golden Tests + CI Gating, VeriReceipt is future-proofed against unchecked cleverness.
