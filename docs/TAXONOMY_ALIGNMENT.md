# Taxonomy Alignment Guide

## Overview

This document ensures consistency across all classification components in VeriReceipt. Any changes to document subtypes, families, or intents must be reflected across all modules.

## Document Families (5 total)

```python
VALID_DOC_FAMILIES = [
    "TRANSACTIONAL",  # Receipts, invoices, bills
    "LOGISTICS",      # Shipping, delivery, transport
    "STATEMENT",      # Bank/card statements
    "PAYMENT",        # Payment receipts, proof of payment
    "UNKNOWN"         # Fallback
]
```

## Document Subtypes (50+)

All subtypes must be present in:
1. `llm_classifier.py` → `VALID_DOC_SUBTYPES`
2. `document_intent.py` → `SUBTYPE_TO_INTENT`
3. `geo_detection.py` → `GEO_SUBTYPE_KEYWORDS` (if geo-specific)

### TRANSACTIONAL Family
- POS_RESTAURANT, POS_RETAIL, POS_FUEL
- HOSPITALITY, ECOMMERCE, HOTEL_FOLIO, FUEL, PARKING, TRANSPORT
- TAX_INVOICE, VAT_INVOICE, COMMERCIAL_INVOICE, SALES_INVOICE, SERVICE_INVOICE, SHIPPING_INVOICE
- PROFORMA, INVOICE (generic)
- CREDIT_NOTE, DEBIT_NOTE
- UTILITY, UTILITY_BILL, TELECOM, TELECOM_BILL, ELECTRICITY_BILL, WATER_BILL
- SUBSCRIPTION, RENT, INSURANCE

### LOGISTICS Family
- SHIPPING_BILL, BILL_OF_LADING, AIR_WAYBILL
- DELIVERY_NOTE, PACKING_LIST
- TRAVEL (generic travel docs)

### PAYMENT Family
- PAYMENT_RECEIPT, BANK_RECEIPT, BANK_SLIP
- CARD_CHARGE_SLIP, REFUND_RECEIPT
- RECEIPT (generic)

### STATEMENT Family
- STATEMENT (generic), BANK_STATEMENT, CARD_STATEMENT

### CLAIMS Family
- CLAIM (generic), MEDICAL_CLAIM, INSURANCE_CLAIM, WARRANTY_CLAIM
- EXPENSE_CLAIM, EXPENSE_REPORT

## Document Intents (9 total)

```python
DocumentIntent:
    PURCHASE          # POS receipts, retail, ecommerce
    BILLING           # Invoices, tax invoices
    SUBSCRIPTION      # Utility bills, telecom, insurance premiums
    TRANSPORT         # Logistics, shipping, travel
    PROOF_OF_PAYMENT  # Payment receipts, bank slips
    STATEMENT         # Bank/card statements
    CLAIM             # Insurance/medical claims
    REIMBURSEMENT     # Expense claims, refunds
    UNKNOWN           # Fallback
```

## Subtype → Intent Mapping

**Critical:** Every subtype in `VALID_DOC_SUBTYPES` must have a mapping in `SUBTYPE_TO_INTENT`.

### PURCHASE Intent
- POS_RESTAURANT, POS_RETAIL, POS_FUEL
- HOSPITALITY, ECOMMERCE, HOTEL_FOLIO, FUEL, PARKING
- MISC, MISC_RECEIPT, EXPENSE_RECEIPT, CARD_SLIP
- RECEIPT (generic)

### BILLING Intent
- All *_INVOICE subtypes (TAX_INVOICE, VAT_INVOICE, etc.)
- INVOICE (generic)
- DEBIT_NOTE

### SUBSCRIPTION Intent
- UTILITY, UTILITY_BILL, TELECOM, TELECOM_BILL
- ELECTRICITY_BILL, WATER_BILL
- SUBSCRIPTION, RENT, INSURANCE

### TRANSPORT Intent
- SHIPPING_BILL, BILL_OF_LADING, AIR_WAYBILL
- DELIVERY_NOTE, PACKING_LIST
- TRAVEL, TRANSPORT

### PROOF_OF_PAYMENT Intent
- PAYMENT_RECEIPT, BANK_RECEIPT, BANK_SLIP
- CARD_CHARGE_SLIP

### STATEMENT Intent
- STATEMENT, BANK_STATEMENT, CARD_STATEMENT

### CLAIM Intent
- CLAIM, MEDICAL_CLAIM, INSURANCE_CLAIM, WARRANTY_CLAIM

### REIMBURSEMENT Intent
- EXPENSE_CLAIM, EXPENSE_REPORT
- CREDIT_NOTE, REFUND_RECEIPT

## Domain → Intent Fallback

When subtype confidence < 0.5, domain provides fallback intent:

```python
DOMAIN_DEFAULT_INTENT = {
    "telecom": SUBSCRIPTION,
    "logistics": TRANSPORT,
    "transport": TRANSPORT,
    "insurance": SUBSCRIPTION,  # Premium/policy billing, not claim
    "healthcare": PURCHASE,     # Medical services/supplies
    "medical": PURCHASE,        # Medical services/supplies
    "ecommerce": PURCHASE,
    "utility": SUBSCRIPTION,
    "banking": STATEMENT,
    "hr_expense": REIMBURSEMENT,
    "expense": REIMBURSEMENT,
}
```

**Note on healthcare/medical:**
- Domain default is PURCHASE (medical services, supplies, pharmacy)
- Subtype MEDICAL_CLAIM maps to CLAIM intent
- This allows proper routing for both medical purchases and insurance claims

## Checklist for Adding New Subtype

When adding a new document subtype:

- [ ] Add to `llm_classifier.py` → `VALID_DOC_SUBTYPES`
- [ ] Add to `document_intent.py` → `SUBTYPE_TO_INTENT`
- [ ] Add to LLM prompt grouping in `_build_classification_prompt()`
- [ ] If geo-specific, add to `geo_detection.py` → `GEO_SUBTYPE_KEYWORDS`
- [ ] Update README.md subtype count if needed
- [ ] Update this document
- [ ] Test with sample documents

## Checklist for Adding New Domain

When adding a new domain:

- [ ] Create YAML domain pack in `resources/domainpacks/`
- [ ] Add to `llm_classifier.py` → `VALID_DOMAINS`
- [ ] Add to `document_intent.py` → `DOMAIN_DEFAULT_INTENT`
- [ ] Update README.md domain list
- [ ] Test with sample documents

## Common Pitfalls

### ❌ Subtype in LLM but not in intent mapping
**Problem:** LLM returns valid subtype, but intent resolver falls back to UNKNOWN.
**Solution:** Add mapping to `SUBTYPE_TO_INTENT`.

### ❌ Domain intent conflicts with subtype intent
**Problem:** Healthcare domain defaults to PURCHASE, but MEDICAL_CLAIM should be CLAIM.
**Solution:** Subtype mapping takes precedence over domain default. Ensure specific subtypes are mapped correctly.

### ❌ Inconsistent family counts in README
**Problem:** README says "3 families" but code has 5.
**Solution:** Keep README in sync with `VALID_DOC_FAMILIES`.

### ❌ Partial taxonomy in LLM prompt
**Problem:** LLM prompt shows only first 20 subtypes, causing hallucinations.
**Solution:** Show full taxonomy grouped by family in prompt.

## Validation Script

Run this to check taxonomy alignment:

```bash
python scripts/validate_taxonomy.py
```

This will check:
- All subtypes in `VALID_DOC_SUBTYPES` have intent mappings
- All domains in `VALID_DOMAINS` have default intents
- Family counts match across modules
- No orphaned subtypes in geo_detection
