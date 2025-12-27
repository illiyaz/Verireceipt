# 📋 How to View Document Tags

When you upload a document for analysis, VeriReceipt automatically classifies it into **31 document subtypes** across **3 families** (TRANSACTIONAL, LOGISTICS, PAYMENT).

## 🎯 Quick Answer

**After uploading a document, document tags are available in:**

### **1. CSV Audit Log** (Recommended - Persistent)
```bash
python view_audit_records.py
```

Look for the **ENS_DOC_PROFILE_TAGS** event in the audit trail.

### **2. API Response** (If you need real-time access)
Currently, document tags are used internally but not directly returned in the API response. However, you can:
- Check the **ensemble reconciliation events** (see below)
- Access them from the **CSV log** after analysis

---

## 📊 Detailed Guide

### **Method 1: View from CSV Audit Log** ✅ EASIEST

After analyzing a document, run:

```bash
# View latest analysis
python view_audit_records.py

# View specific decision
python view_audit_records.py --decision-id <uuid>

# View last 5 analyses
python view_audit_records.py --last 5
```

**What you'll see:**

```
🔍 **Audit Events** (4 events)

   [1] ENS_DOC_PROFILE_TAGS (INFO)
       Source:  ensemble
       Type:    reconciliation
       Message: Derived document profile tags for audit and downstream reconciliation.
       Evidence:
         • doc_family: TRANSACTIONAL
         • doc_subtype: TAX_INVOICE
         • doc_profile_confidence: 0.85
```

---

### **Method 2: Access from API Response** (Requires modification)

Currently, the API doesn't return document tags in the response. To add them, you have two options:

#### **Option A: Return in API Response** (Modify API)

Edit `app/api/main.py` to include doc_profile in the response:

```python
# In the /analyze/hybrid endpoint, after getting rule_based results:
rule_based_result = analyze_receipt(str(temp_path))

# Extract doc_profile from features
doc_profile = {
    "doc_family": rule_based_result.features.text_features.get("doc_family_guess"),
    "doc_subtype": rule_based_result.features.text_features.get("doc_subtype_guess"),
    "doc_profile_confidence": rule_based_result.features.text_features.get("doc_profile_confidence"),
    "doc_profile_evidence": rule_based_result.features.text_features.get("doc_profile_evidence"),
}

# Add to response
results["doc_profile"] = doc_profile
```

Then access it:
```python
response = requests.post('http://localhost:8000/analyze/hybrid', files={'file': f})
result = response.json()

doc_profile = result['doc_profile']
print(f"Family: {doc_profile['doc_family']}")
print(f"Subtype: {doc_profile['doc_subtype']}")
print(f"Confidence: {doc_profile['doc_profile_confidence']}")
```

#### **Option B: Extract from Ensemble Events** (Already available)

Document tags are included in the ensemble reconciliation events:

```python
response = requests.post('http://localhost:8000/analyze/hybrid', files={'file': f})
result = response.json()

# Find ENS_DOC_PROFILE_TAGS event
for event in result['ensemble_verdict']['reconciliation_events']:
    if event['code'] == 'ENS_DOC_PROFILE_TAGS':
        evidence = event['evidence']
        print(f"Family: {evidence['doc_family']}")
        print(f"Subtype: {evidence['doc_subtype']}")
        print(f"Confidence: {evidence['doc_profile_confidence']}")
        break
```

---

### **Method 3: Query CSV Directly**

```python
import csv
import json

with open('data/logs/decisions.csv', 'r') as f:
    reader = csv.DictReader(f)
    rows = list(reader)
    
    # Get latest decision
    latest = rows[-1]
    
    # Parse audit_events JSON
    audit_events = json.loads(latest['audit_events'])
    
    # Find ENS_DOC_PROFILE_TAGS
    for event in audit_events:
        if event['code'] == 'ENS_DOC_PROFILE_TAGS':
            evidence = event['evidence']
            print(f"Family: {evidence['doc_family']}")
            print(f"Subtype: {evidence['doc_subtype']}")
            print(f"Confidence: {evidence['doc_profile_confidence']}")
```

---

## 🏷️ Document Tag Structure

**Document Family** (3 options):
- `TRANSACTIONAL` - Receipts, invoices, bills
- `LOGISTICS` - Shipping documents, waybills
- `PAYMENT` - Payment confirmations, bank slips

**Document Subtype** (31 options):
- TRANSACTIONAL: `POS_RESTAURANT`, `POS_RETAIL`, `ECOMMERCE`, `TAX_INVOICE`, `VAT_INVOICE`, `COMMERCIAL_INVOICE`, `SERVICE_INVOICE`, `SHIPPING_INVOICE`, `PROFORMA`, `CREDIT_NOTE`, `DEBIT_NOTE`, `UTILITY`, `TELECOM`, `SUBSCRIPTION`, `RENT`, `INSURANCE`, `HOTEL_FOLIO`, `FUEL`, `PARKING`, `TRANSPORT`, `MISC`
- LOGISTICS: `SHIPPING_BILL`, `BILL_OF_LADING`, `AIR_WAYBILL`, `DELIVERY_NOTE`
- PAYMENT: `PAYMENT_RECEIPT`, `BANK_SLIP`, `CARD_CHARGE_SLIP`, `REFUND_RECEIPT`

**Confidence Score**: 0.0 - 1.0
- `> 0.75` - High confidence
- `0.55 - 0.75` - Medium confidence
- `< 0.55` - Low confidence (document-aware rules are soft-gated)

**Evidence**: List of matched keywords that led to the classification

---

## 💡 Why Document Tags Matter

Document tags are used for:

1. **Document-Aware Rule Validation**
   - R5 (No amounts) - Skipped for LOGISTICS docs
   - R6 (No total line) - Skipped for docs without total requirements
   - R8 (No date) - Skipped for LOGISTICS docs

2. **Learned Rule Gating**
   - Low doc_profile_confidence (< 0.55) → Reduce learned rule adjustments by 35%
   - Optional subtypes (LOGISTICS, PAYMENT) → Reduce learned rule adjustments by 40%

3. **Audit Trail**
   - Every decision includes doc_family, doc_subtype, doc_profile_confidence
   - Evidence tracking for compliance

4. **Analytics**
   - Track which document types are most commonly flagged
   - Identify false positive patterns by document type

---

## 🚀 Recommended Workflow

**For Development/Testing:**
```bash
# 1. Analyze a document
python test_audit_trail.py

# 2. View the audit trail
python view_audit_records.py
```

**For Production:**
```python
import requests

# Upload document
with open('receipt.pdf', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/analyze/hybrid',
        files={'file': ('receipt.pdf', f, 'application/pdf')}
    )

result = response.json()

# Get decision ID
decision_id = result.get('receipt_id')  # or extract from response

# Later, query audit log by decision_id
# Or extract from ensemble reconciliation events
for event in result.get('ensemble_verdict', {}).get('reconciliation_events', []):
    if event['code'] == 'ENS_DOC_PROFILE_TAGS':
        doc_tags = event['evidence']
        print(f"Document Type: {doc_tags['doc_family']} / {doc_tags['doc_subtype']}")
        print(f"Confidence: {doc_tags['doc_profile_confidence']}")
```

---

## 📝 Summary

| Method | Availability | Ease of Use | Best For |
|--------|-------------|-------------|----------|
| **CSV Audit Log** | ✅ Always | ⭐⭐⭐⭐⭐ | Post-analysis review, compliance |
| **Ensemble Events** | ✅ Always | ⭐⭐⭐⭐ | Real-time access, programmatic use |
| **API Response** | ❌ Not yet | ⭐⭐⭐ | Real-time access (requires modification) |

**Recommended:** Use `python view_audit_records.py` for quick viewing, or extract from ensemble reconciliation events for programmatic access.
