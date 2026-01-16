# Document Family Model - Long-Term Cap

**Design Goal:** Define a closed world of document families that covers 95-98% of real receipts/invoices, and make anything else explicitly "UNKNOWN / SAFE".

**This is not about perfection. This is about controlling entropy.**

---

## 🎯 The 7-Family Cap (+ 1 Reserved)

### 1. POS_RECEIPT
**Transactional, consumer-facing**

**Examples:**
- Restaurant receipts
- Retail POS slips
- Fuel receipts
- Supermarket bills

**Characteristics:**
- Line items
- Subtotal / tax / total
- Often noisy OCR
- Small amounts
- Currency-local

**Rules Allowed:**
- R7 (total mismatch)
- Learned spacing / typography patterns
- Tax sanity (soft)

**Golden Test:** `pos_receipt.json`

---

### 2. COMMERCIAL_INVOICE
**B2B billing document**

**Examples:**
- Vendor invoices
- SaaS invoices
- Supplier bills
- Freight invoices

**Characteristics:**
- Structured totals
- Clear tax / subtotal
- Higher amounts
- Legal/accounting relevance

**Rules Allowed:**
- R7B (strict reconciliation)
- Tax tolerance logic
- Currency consistency

**Golden Test:** `invoice.json`

---

### 3. TAX_INVOICE (Subtype of COMMERCIAL_INVOICE)
**Jurisdiction-specific compliance invoice**

**Examples:**
- Indian GST invoices
- VAT invoices (EU)
- Sales tax invoices

**Characteristics:**
- Jurisdictional constraints
- Tax rate expectations
- Strong legal semantics

**Rules Allowed:**
- Stricter R7B tolerance
- Checksum / format checks (GSTIN, VAT ID)
- Tax math sanity

**Golden Test:** `tax_invoice_india.json`

**⚠️ Important:** TAX_INVOICE is a subtype, not a new family. This keeps the family count low.

---

### 4. CREDIT_NOTE
**Negative billing adjustment**

**Examples:**
- Credit memo
- Refund note
- Adjustment invoice

**Characteristics:**
- Negative totals
- Often mirrors invoice structure
- Never standalone revenue

**Rules Allowed:**
- R7C (sign-aware reconciliation)
- Soft severity only
- No "fake" forcing

**Golden Test:** `credit_note.json`

---

### 5. LOGISTICS / SHIPPING_DOC
**Non-financial, operational**

**Examples:**
- Delivery challan
- Bill of lading
- Airway bill
- Shipping manifest

**Characteristics:**
- May show amounts but not payable totals
- Dates, tracking numbers, addresses
- Often misclassified as invoices

**Rules Allowed:**
- Very limited
- Mostly non-action
- Guardrails against misfiring financial rules

**Golden Test:** `logistics.json`

---

### 6. SUBSCRIPTION / SERVICE_STATEMENT
**Recurring, often SaaS**

**Examples:**
- Monthly SaaS bills
- Cloud provider statements
- Telecom bills

**Characteristics:**
- Period-based charges
- Proration
- Discounts common
- Less strict line-item math

**Rules Allowed:**
- Soft reconciliation
- Period sanity (dates)
- No hard mismatches

**Golden Test:** `(future) subscription.json`

**Note:** Can be delayed until it materially appears in data.

---

### 7. REIMBURSEMENT_SUPPORTING_DOC
**Evidence, not billing**

**Examples:**
- Hotel folios
- Boarding passes
- Expense summaries
- Parking tickets

**Characteristics:**
- Often partial
- Often missing totals
- Contextual evidence

**Rules Allowed:**
- Almost none
- Mostly classification + audit
- Strong safe-degrade bias

**Golden Test:** `(future) reimbursement_support.json`

---

### 8. UNKNOWN / MISC (Hard-Capped)
**🚨 NOT A FAMILY — A SAFETY STATE**

This is deliberately NOT extensible.

**Examples:**
- Random PDFs
- Scanned letters
- Contracts
- Emails
- Forms

**Rules Allowed:**
- ❌ None (except veto-only vision HARD_FAIL)
- Must default to real or suspicious, never fake

**Golden Test:** `misc_safe.json` (CRITICAL)

---

## 📊 Final Count

| Category | Count |
|----------|-------|
| Core Families | 7 |
| Reserved / Safety | 1 |
| **Total** | **8 (hard cap)** |

**If someone proposes family #9, it must go through:**
- RAP update
- New golden test
- Explicit architectural review

---

## 🧪 Subtype vs New Family — The Decision Test

A document qualifies as a **SUBTYPE** if **ALL FIVE** questions are YES.

### Q1. Same economic intent?
Is the document still fundamentally doing the same thing?

**Examples:**
- Invoice vs Tax Invoice → ✅ (billing)
- Invoice vs Credit Note → ❌ (billing vs adjustment)

### Q2. Same core structure?
Would the same extracted fields exist?

**Examples:**
- Invoice & Tax Invoice → subtotal, tax, total → ✅
- Invoice & Logistics Doc → ❌

### Q3. Same reconciliation math (maybe with constraints)?
Is the math the same, just tighter/looser?

**Examples:**
- Tax Invoice = stricter tolerance → ✅ subtype
- Credit Note = sign inversion → ❌ (new family)

### Q4. Same failure modes?
Do the same fraud patterns apply?

**Examples:**
- Edited totals → yes for invoices
- Missing totals → acceptable for logistics → ❌

### Q5. Same severity ceiling?
Can mistakes be treated with the same seriousness?

**Examples:**
- Invoice & Tax Invoice → WARNING ceiling → ✅
- Reimbursement doc → INFO only → ❌

---

**✅ If ALL 5 = YES → SUBTYPE**

**❌ If ANY = NO → NEW FAMILY**

No debate. No intuition. No "but mostly".

---

## 📌 Examples Applied

### TAX_INVOICE

| Question | Answer |
|----------|--------|
| Same intent | ✅ |
| Same structure | ✅ |
| Same math | ✅ (stricter) |
| Same failure modes | ✅ |
| Same severity | ✅ |

**👉 Subtype**

### CREDIT_NOTE

| Question | Answer |
|----------|--------|
| Same intent | ❌ (adjustment, not billing) |
| Same structure | ⚠️ |
| Same math | ❌ (sign-aware) |
| Same failure modes | ❌ |
| Same severity | ❌ |

**👉 New Family**

### SUBSCRIPTION_STATEMENT

| Question | Answer |
|----------|--------|
| Same intent | ⚠️ |
| Same structure | ❌ (period-based) |
| Same math | ❌ (proration) |
| Same failure modes | ❌ |
| Same severity | ❌ |

**👉 New Family**

---

## 🧱 Why This Works

**✅ Bounded**
- No infinite merchant-specific or country-specific families

**✅ Extensible (Safely)**
- You can add subtypes without growing families

**✅ Aligned with RAP**
- Each family maps cleanly to:
  - Scope
  - Allowed rule types
  - Expected severity ceiling

**✅ Matches Reality**
- This taxonomy covers almost all real-world expense documents without hallucinating structure

---

## 🔒 Enforcement

See `RULE_ADMISSION_POLICY.md`:
- **RAP-7:** Document families are capped at 7 (+ UNKNOWN). New families require policy change.
- **RAP-8:** Subtype qualification requires passing the 5-question test.
