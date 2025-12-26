# VeriReceipt – AI-Powered Fake Receipt Detection Engine

VeriReceipt is an intelligent fraud-detection system that identifies **fake, AI-generated, manipulated, or tampered receipts** submitted for reimbursements. It combines **document forensics**, **OCR**, **metadata analysis**, **rule-based scoring**, and **AI models (DONUT/CLIP)** to determine whether a receipt is **real**, **fake**, or **suspicious**, along with human-readable explanations.

---

## 🚀 Why VeriReceipt?

Businesses lose money every year due to:
- AI-generated receipts (Canva, Photoshop, fake receipt apps)
- Digitally altered totals
- Edited dates, vendor names, or line items
- PDF metadata tampering
- Reimbursement fraud

VeriReceipt stops this using a hybrid AI + forensic rules pipeline.

---

## 🏗 Architecture Overview

```
          ┌──────────────────────────┐
          │     Receipt Upload       │
          └──────────────┬───────────┘
                         ▼
              ┌─────────────────────┐
              │ Ingestion Pipeline  │
              │ - PDF/Image Load    │
              │ - Normalization     │
              └──────────┬──────────┘
                         ▼
         ┌───────────────┴───────────────┐
         ▼                               ▼
  ┌─────────────┐              ┌─────────────────┐
  │  Metadata   │              │  OCR & Text     │
  │  Engine     │              │  Extraction     │
  │ - PDF meta  │              │ - EasyOCR       │
  │ - EXIF data │              │ - Tesseract     │
  └──────┬──────┘              └────────┬────────┘
         └───────────────┬───────────────┘
                         ▼
              ┌─────────────────────┐
              │ Feature Extraction  │
              │ - Forensic signals  │
              │ - Text patterns     │
              │ - Layout cues       │
              │ - Spacing anomalies │
              └──────────┬──────────┘
                         ▼
         ┌───────────────┴────────────────────┐
         ▼                ▼                   ▼
  ┌─────────────┐  ┌──────────┐      ┌──────────────┐
  │ Rule-Based  │  │ Vision   │      │  LayoutLM    │
  │ Engine      │  │ LLM      │      │  Extraction  │
  │ - 14 Rules  │  │ - Fraud  │      │  - Merchant  │
  │ - Learned   │  │   Detect │      │  - Total     │
  │   Rules     │  │ - Auth   │      │  - Date      │
  └──────┬──────┘  └────┬─────┘      └──────┬───────┘
         └───────────────┴────────────────────┘
                         ▼
              ┌─────────────────────┐
              │ Ensemble Verdict    │
              │ - Converge results  │
              │ - Critical override │
              │ - Confidence score  │
              └──────────┬──────────┘
                         ▼
              ┌─────────────────────┐
              │ Final Decision       │
              │ - real/fake/suspicious │
              │ - Confidence %       │
              │ - Detailed reasons   │
              └──────────┬──────────┘
                         ▼
              ┌─────────────────────┐
              │ Human Review         │
              │ - Feedback form      │
              │ - Indicator review   │
              │ - Data corrections   │
              └──────────┬──────────┘
                         ▼
              ┌─────────────────────┐
              │ Learning Engine      │
              │ - Reinforce correct  │
              │ - Reduce false alarms│
              │ - Create new rules   │
              │ - Learn patterns     │
              └──────────┬──────────┘
                         ▼
              ┌─────────────────────┐
              │ Improved Detection   │
              │ (Next Analysis)      │
              └─────────────────────┘
```

---

## 📦 Project Structure

```
VeriReceipt/
  app/
    pipelines/
      ingest.py           # PDF/Image ingestion
      metadata.py         # PDF metadata & EXIF extraction
      ocr.py              # EasyOCR + Tesseract
      features.py         # Feature engineering (18+ signals)
      rules.py            # Rule-based engine + learned rules
      vision_llm.py       # Vision LLM (Ollama/PyTorch)
      layoutlm.py         # LayoutLM data extraction
      ensemble.py         # Multi-engine verdict convergence
      learning.py         # 🆕 Feedback learning engine
    models/
      feedback.py         # 🆕 Feedback data models
    repository/
      feedback_store.py   # 🆕 SQLite feedback storage
    api/
      main.py             # FastAPI endpoints
      feedback.py         # 🆕 Feedback API routes
    schemas/
      receipt.py
    utils/
    config.py
  web/
    index.html            # Main analysis UI
    review.html           # 🆕 Comprehensive feedback form
    stats.html            # 🆕 Feedback stats dashboard
  data/
    raw/                  # Test receipts
    processed/
    feedback.db           # 🆕 Local feedback database
  notebooks/
  tests/
  requirements.txt
  README.md
  FEEDBACK_WORKFLOW_SUMMARY.md  # 🆕 Complete feedback docs
```

---

## 🛡 Status Badges

![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-Apache%202.0-green)
![Build](https://img.shields.io/badge/build-passing-success)
![AI](https://img.shields.io/badge/AI-DONUT%20%7C%20CLIP-orange)

---

## 📌 Current Development Stage

### ✅ **Completed:**
- ✅ Core folder structure & project setup
- ✅ Receipt ingestion (PDF/Image support)
- ✅ OCR pipeline (EasyOCR + Tesseract)
- ✅ Metadata extraction (PDF + EXIF)
- ✅ Rule-based fraud engine (18+ rules including cross-field validation)
- ✅ Vision LLM integration (fraud detection + authenticity)
- ✅ LayoutLM integration (data extraction)
- ✅ Ensemble verdict system with reconciliation events
- ✅ **Document Profile Detection** 🆕
  - 31 document subtypes across 3 families (TRANSACTIONAL, LOGISTICS, PAYMENT)
  - Confidence-based classification with ambiguity detection
  - Evidence tracking for audit trail
- ✅ **Document-Aware Rule Validation** 🆕
  - Context-aware expectations (logistics docs don't need totals)
  - Reduced false positives on specialized document types
  - Soft-gating for learned rules based on doc profile confidence
- ✅ **Ensemble Reconciliation Events** 🆕
  - Structured decision path tracking
  - 7 decision scenarios with full evidence
  - Confidence normalization across all engines
- ✅ **Comprehensive Feedback System**
  - Detailed feedback form UI
  - Indicator-level reviews (✅ Correct / ❌ False Alarm)
  - Missed indicator tracking
  - Data correction learning
  - Local learning engine
- ✅ FastAPI backend with 10+ endpoints
- ✅ React-based web UI
- ✅ Docker deployment setup
- ✅ Stats dashboard

### 🔄 **In Progress:**
- Enhanced pattern learning (merchants, addresses)
- ML model fine-tuning preparation
- Active learning features

### 📋 **Next:**
- Collect diverse training dataset
- Fine-tune Vision LLM on user feedback
- Fine-tune DONUT on extraction corrections
- Reinforcement learning for ensemble weights
- Production deployment with fine-tuned models  

---


## 🔧 Development Plan (Phase 1 – Rule-Based Engine)

VeriReceipt is currently in **Phase 1**, where the goal is to make the system capable of detecting fake receipts using deterministic rules before adding machine learning models. This phase builds the foundation for all future AI capabilities.

### **1. Feature Engineering**
We will extract structured, meaningful features from the raw receipt:
- **File & Metadata Features**
  - Suspicious PDF producers (e.g., Canva, Photoshop, WPS)
  - Creation/modification date anomalies
  - EXIF availability (camera vs synthetic images)
  - File size irregularities
- **Text Features (From OCR)**
  - Merchant name extraction
  - Date extraction + validation
  - Total amount identification
  - Line-item parsing
  - Amount mismatch detection
- **Layout Features (Basic for v1)**
  - Line structure consistency
  - Presence/absence of expected labels (e.g., "Total", "Invoice")
- **Forensic Cues**
  - Repeated text patterns
  - Highly uniform spacing (template-like)
  - All-caps or low variety of characters

### **2. Rule-Based Fraud Engine**
We will combine the above features into a weighted scoring model:
- Assign weights to anomalies (e.g., metadata forgery = high severity)
- Aggregate into a 0–1 fraud score
- Map to:
  - **0.0–0.3 → real**
  - **0.3–0.6 → suspicious**
  - **0.6–1.0 → fake**
- Produce **human-readable reasoning**, e.g.:
  - `"PDF producer is 'Canva', which is frequently used to fabricate receipts."`
  - `"Sum of line items does not match printed total."`

### **3. Orchestrated Analysis Pipeline**
Implement a unified function:

```
analyze_receipt(file_path) → ReceiptDecision
```

Flow:
1. Ingestion →  
2. OCR →  
3. Metadata extraction →  
4. Feature engineering →  
5. Rule engine →  
6. Final decision  

This becomes the core engine for both CLI and API.

### **4. Testing Tools**
We will add:
- A CLI test script (`test_run.py`)
- Example sample receipts in `data/raw/`

The script prints:
```
Label: fake
Score: 0.82
Reasons:
 - Producer is Canva
 - Total mismatch
```

### **5. Outputs (v1)**
Every decision returns:
- `label` (real / suspicious / fake)
- `score`
- `reasons`
- optional feature dump (for debugging)

This completes a fully working v1 that already provides real value to reimbursement teams before ML is added.

## 🧮 Rule Engine Specification (Phase 1)

This section documents the rules currently implemented in the VeriReceipt v1 engine. Each rule contributes a weighted score to a final fraud score between 0.0 and 1.0.

### Rule Summary Table

| ID  | Rule                                    | Condition (Trigger)                                                                                 | Weight | Severity Tag   |
|-----|-----------------------------------------|------------------------------------------------------------------------------------------------------|--------|----------------|
| R1  | Suspicious producer/creator             | PDF `producer`/`creator` contains known editing/template tools (Canva, Photoshop, WPS, etc.)        | +0.50  | HARD_FAIL      |
| R2  | Missing creation date                   | No `creation_date` metadata                                                                        | +0.05  | INFO           |
| R3  | Missing modification date               | No `mod_date` metadata                                                                             | +0.05  | INFO           |
| R4  | No EXIF data (images)                   | `exif_present = False` for image receipts                                                          | +0.05  | INFO           |
| R5  | No detected amounts                     | No currency/amount tokens detected in OCR text                                                     | +0.40  | CRITICAL       |
| R6  | Amounts but no total line               | `has_any_amount = True` and `total_line_present = False`                                           | +0.15  | CRITICAL       |
| R7  | Line-item vs total mismatch             | `total_mismatch = True` (sum of line items ≠ printed total)                                        | +0.40  | CRITICAL       |
| R8  | No date found                           | `has_date = False`                                                                                 | +0.20  | CRITICAL       |
| R9  | No merchant candidate                   | `merchant_candidate` could not be confidently inferred                                             | +0.15  | CRITICAL       |
| R9b | Document type ambiguity                 | Mixed invoice/receipt language in same document                                                    | +0.15  | CRITICAL       |
| R9c | Invoice missing typical fields          | Invoice-like doc without Invoice No / Bill To / Amount Due                                        | +0.12  | INFO           |
| R9d | Receipt missing payment signal          | Receipt-like doc without paid/txn/auth code                                                        | +0.08  | INFO           |
| R10 | Too few lines                           | `num_lines < 5`                                                                                  | +0.15  | INFO           |
| R11 | Too many lines                          | `num_lines > 120`                                                                                | +0.10  | INFO           |
| R12 | Very high numeric line ratio            | `numeric_line_ratio > 0.8` and `num_lines > 10`                                              | +0.10  | INFO           |
| R13 | High uppercase ratio                    | `uppercase_ratio > 0.8` and `num_lines > 5`                                                  | +0.10  | INFO           |
| R14 | Low character variety                   | `unique_char_count < 15` and `num_lines > 5`                                                 | +0.15  | INFO           |
| R15 | Impossible date sequence                | Receipt dated AFTER file creation date (physically impossible)                                    | +0.40  | HARD_FAIL      |
| R16 | Suspicious date gap                     | File created >2 days after receipt date (backdating pattern)                                      | +0.35  | CRITICAL       |
| R17 | Unparsable receipt date                 | Date present but cannot be parsed into known format                                               | +0.25  | CRITICAL       |
| **GEO-CURRENCY-TAX SYSTEM** 🆕 |
| GEO1 | Currency-geography mismatch            | Currency doesn't match region (e.g., CAD with only US signals, 24 regions supported)              | +0.30  | CRITICAL       |
| GEO2 | Tax regime mismatch                    | Tax terminology doesn't match region (e.g., USD with GST, INR with sales tax)                     | +0.18  | CRITICAL       |
| GEO3 | Healthcare merchant-currency           | US healthcare provider billing in CAD/INR without evidence                                        | +0.22  | CRITICAL       |
| **MERCHANT VALIDATION** 🆕 |
| MER1 | Merchant looks like label              | Merchant name appears to be field label (INVOICE/RECEIPT/ORDER)                                   | +0.18  | CRITICAL       |
| MER2 | Merchant looks like identifier         | Merchant contains many digits, resembles invoice/receipt number                                   | +0.18  | CRITICAL       |
| MER3 | Merchant starts with label             | Merchant begins with "invoice"/"receipt"/"order" prefix                                           | +0.12  | CRITICAL       |
| **CROSS-FIELD CONSISTENCY** |
| R30 | Geography mismatch (legacy)            | Mixed US location cues with India cues (e.g., US state + +91 phone/PIN/GST)                  | +0.30  | CRITICAL       |
| R31 | Currency vs tax-regime (legacy)        | USD with GST terms OR INR with US sales-tax terms                                            | +0.30  | CRITICAL       |
| R32 | Missing business identifiers            | High-value invoice (>100,000) without GSTIN/PAN/EIN                                          | +0.25  | CRITICAL       |
| R33 | Template artifacts                      | Placeholder text like "<Payment terms>" or "Invoice template"                              | +0.20  | CRITICAL       |
| R34 | Vague high-value charges                | Generic fees ("Incidentals"/"Consultation") without breakdown on high-value invoices       | +0.15  | INFO           |

**Classification thresholds:**

- `score < 0.3`  → **real**  
- `0.3 ≤ score < 0.6` → **suspicious**  
- `score ≥ 0.6` → **fake**

---

### Detailed Rule Descriptions

**R1 – Suspicious producer/creator**  
- **What:** Checks if the PDF `producer` or `creator` string contains tools like Canva, Photoshop, WPS, Fotor, etc.  
- **Why:** These tools are commonly used to design templates or edit documents after generation. For native POS/e-bill systems, producers are usually printer drivers or system names.  
- **Weight:** +0.30 (high) because it is a strong signal of possible manual fabrication or editing.

**R2 – Missing creation date**  
- **What:** No `creation_date` metadata present.  
- **Why:** Native systems typically record this. Missing data may indicate export via intermediate tools.  
- **Weight:** +0.05 (low).

**R3 – Missing modification date**  
- **What:** No `mod_date` metadata present.  
- **Why:** Similar reasoning as R2; weak but useful when combined with other signals.  
- **Weight:** +0.05 (low).

**R4 – No EXIF data (image receipts)**  
- **What:** For image-based receipts, absence of EXIF (camera) data is mildly suspicious.  
- **Why:** Genuine receipts photographed by a phone usually carry some EXIF info; exports/screenshots often strip it.  
- **Weight:** +0.05 (low).

**R5 – No detected amounts** 🔄  
- **What:** OCR text contains no recognizable currency/amount pattern.  
- **Why:** A receipt without any numeric amount is almost never valid. Often indicates OCR failure or synthetic text.  
- **Weight:** +0.40 (high) - **Document-aware:** Skipped for logistics documents (Air Waybills, Bills of Lading, Delivery Notes) where amounts are optional.  
- **Evidence:** Includes doc_family, doc_subtype, doc_profile_confidence for audit trail.

**R6 – Amounts but no total line** 🔄  
- **What:** Amounts exist but no line with "Total/Grand Total/Amount Payable/etc." found.  
- **Why:** Most receipts clearly mark the total; absence suggests an incomplete or template-style artifact.  
- **Weight:** +0.15 (medium) - **Document-aware:** Skipped if total value extracted by LayoutLM/DONUT OR if document type doesn't require TOTAL keyword (logistics docs).  
- **Evidence:** Includes has_usable_total_value, doc_family, doc_subtype for audit trail.

**R7 – Line-item vs total mismatch**  
- **What:** Sum of detected line-item amounts does not match the printed total (above a small tolerance).  
- **Why:** Strong signal of manual tampering with the total or error in fabrication.  
- **Weight:** +0.40 (high).

**R8 – No date found** 🔄  
- **What:** No date-like pattern detected in OCR text.  
- **Why:** Valid receipts almost always include a date; missing date is a compliance red flag.  
- **Weight:** +0.20 (medium–high) - **Document-aware:** Skipped for logistics documents (Bills of Lading, Delivery Notes) where dates may be less prominent.  
- **Evidence:** Includes doc_family, doc_subtype, doc_profile_confidence for audit trail.

**R9 – No merchant candidate**  
- **What:** We cannot confidently infer a merchant name from the header lines.  
- **Why:** Most receipts clearly show merchant/store name at the top; absence suggests generic/fake templates.  
- **Weight:** +0.15 (medium).

**R10 – Too few lines**  
- **What:** Very small number of lines (`num_lines < 5`).  
- **Why:** Real receipts typically have multiple lines for header, items, totals, legal text. Too few lines feels synthetic.  
- **Weight:** +0.15 (medium).

**R11 – Too many lines**  
- **What:** Unusually large number of lines (`num_lines > 120`).  
- **Why:** Could indicate noisy OCR on non-receipt content, or synthetic filler text.  
- **Weight:** +0.10 (low–medium).

**R12 – Very high numeric line ratio**  
- **What:** Majority of lines are numeric (`numeric_line_ratio > 0.8` and `num_lines > 10`).  
- **Why:** Real receipts contain text labels, not only numeric content; pure numeric patterns look auto-generated.  
- **Weight:** +0.10 (low–medium).

**R13 – High uppercase ratio**  
- **What:** Most alphabetic characters are uppercase (`uppercase_ratio > 0.8`).  
- **Why:** Overuse of uppercase can indicate template headings being repeated or stylized synthetic layouts.  
- **Weight:** +0.10 (low–medium).

**R14 – Low character variety**  
- **What:** Very low unique character count (`unique_char_count < 15` with reasonable line count).  
- **Why:** Suggests repetitive or boilerplate content, often seen in simple fake templates.  
- **Weight:** +0.15 (medium).

**R30 – Geography mismatch** 🆕  
- **What:** Detects mixed US and India location cues (e.g., US state name + +91 phone number or Indian PIN code).  
- **Why:** Legitimate invoices rarely mix jurisdictions without clear cross-border context. This pattern is common in template-based fakes where elements are copied from different sources.  
- **Weight:** +0.30 (high) because it's a strong signal of synthetic document creation.

**R31 – Currency vs tax-regime mismatch** 🆕  
- **What:** Detects USD formatting with GST terms (CGST/SGST/IGST) OR INR formatting with US sales-tax terms.  
- **Why:** Tax regimes are jurisdiction-specific. USD invoices should not have GST (India tax), and INR invoices should not have US sales tax terminology. This mismatch indicates template reuse or fabrication.  
- **Weight:** +0.30 (high) for USD+GST; +0.15 (medium) for INR+US-tax.

**R32 – Missing business identifiers** 🆕  
- **What:** High-value invoices (total ≥ 100,000) without GSTIN, PAN, or EIN-like identifiers.  
- **Why:** Legitimate businesses include registration/tax identifiers on invoices, especially for high-value transactions. Missing identifiers suggest the invoice may be fabricated.  
- **Weight:** +0.25 (high) for high-value invoices without proper business registration.

**R33 – Template artifacts** 🆕  
- **What:** Detects placeholder text like "<Payment terms>", "<Due on receipt>", or "Invoice template".  
- **Why:** These are clear signs the document was created from a template rather than generated by a POS or accounting system. Real receipts don't contain placeholder markup.  
- **Weight:** +0.20 (medium–high) as it's a direct indicator of template usage.

**R34 – Vague high-value charges** 🆕  
- **What:** Generic fee descriptions ("Incidentals", "Consultation", "Professional fee") without breakdown (hours, rates, references) on high-value invoices.  
- **Why:** Legitimate high-value professional services include detailed breakdowns. Vague descriptions are commonly used in fabricated invoices to justify inflated amounts.  
- **Weight:** +0.15 (medium) when combined with high invoice value and no supporting details.

**R15 – Impossible date sequence** 🆕  
- **What:** Receipt/purchase date is AFTER the PDF/image creation date (physically impossible).  
- **Why:** A receipt cannot be dated after the file containing it was created. This is a hard-fail structural inconsistency that strongly indicates backdating or fabrication.  
- **Weight:** +0.40 (high)  
- **Severity:** HARD_FAIL (forces ensemble to reject)

**R16 – Suspicious date gap** 🆕  
- **What:** File created more than 2 days after the receipt date.  
- **Why:** While receipts can be scanned later, a significant gap is unusual for expense claims and is a common pattern in backdated or fabricated receipts.  
- **Weight:** +0.35 (high)  
- **Severity:** CRITICAL

**R17 – Unparsable receipt date** 🆕  
- **What:** Date string is present but cannot be parsed into any known format (10+ formats supported).  
- **Why:** Prevents reliable consistency checks and is suspicious when a date is clearly present. Common in manually edited documents.  
- **Weight:** +0.25 (high)  
- **Severity:** CRITICAL

**R9b – Document type ambiguity** 🆕  
- **What:** Document contains both "INVOICE" and "RECEIPT" language.  
- **Why:** Legitimate documents are consistent (invoice OR receipt). Mixing terms is common in edited/template PDFs.  
- **Weight:** +0.15 (medium)  
- **Severity:** CRITICAL

**R9c – Invoice missing typical fields** 🆕  
- **What:** Invoice-like document without Invoice No / Bill To / Amount Due.  
- **Why:** Can happen with OCR misses, but also common in template-generated fakes.  
- **Weight:** +0.12 (medium)  
- **Severity:** INFO (logged for review)

**R9d – Receipt missing payment signal** 🆕  
- **What:** Receipt-like document without paid/payment received/txn/auth code.  
- **Why:** Not always wrong, but worth review when combined with other anomalies.  
- **Weight:** +0.08 (low)  
- **Severity:** INFO

---

### 📋 Document Profile Detection System

VeriReceipt now includes intelligent document classification to reduce false positives and provide context-aware validation.

**Supported Document Families:**

**1. TRANSACTIONAL (21 subtypes)**
- **Receipts (8):** POS_RESTAURANT, POS_RETAIL, ECOMMERCE, HOTEL_FOLIO, FUEL, PARKING, TRANSPORT, MISC
- **Invoices (8):** TAX_INVOICE, VAT_INVOICE, COMMERCIAL_INVOICE, SERVICE_INVOICE, SHIPPING_INVOICE, PROFORMA, CREDIT_NOTE, DEBIT_NOTE
- **Bills (5):** UTILITY, TELECOM, SUBSCRIPTION, RENT, INSURANCE

**2. LOGISTICS (4 subtypes)**
- SHIPPING_BILL, BILL_OF_LADING, AIR_WAYBILL, DELIVERY_NOTE

**3. PAYMENT (4 subtypes)**
- PAYMENT_RECEIPT, BANK_SLIP, CARD_CHARGE_SLIP, REFUND_RECEIPT

**Document-Aware Validation:**

The system adjusts expectations based on document type:

- **Logistics documents** (Air Waybills, Bills of Lading, Delivery Notes):
  - ✅ Totals/amounts are **optional** (no penalty for missing)
  - ✅ Dates may be **less prominent** (no penalty for missing)
  - ✅ Focus on shipment fields instead of financial fields

- **Payment documents** (Payment Receipts, Bank Slips):
  - ✅ Different validation rules for transaction confirmations
  - ✅ Transaction ID/UTR validation instead of merchant validation

- **Confidence-based gating:**
  - If doc_profile_confidence < 0.55: reduce learned rule adjustments by 35%
  - If doc subtype has optional fields: reduce learned rule adjustments by 40%

**Benefits:**
- ✅ **Reduced false positives** on specialized document types
- ✅ **Context-aware validation** based on document family
- ✅ **Evidence tracking** for audit compliance
- ✅ **200+ keywords** mapped to specific subtypes

---

### 🌍 Global Geo-Currency-Tax System (GeoRuleMatrix)

The GeoRuleMatrix is a comprehensive validation system supporting **24 regions/countries** with intelligent cross-border detection and context awareness.

**GEO1 – Currency-geography mismatch** 🆕  
- **What:** Detected currency doesn't match expected currencies for the implied region.  
- **Example:** CAD currency with only US geography signals (no Canadian evidence).  
- **Why:** Legitimate receipts have consistent currency-geography pairing. Mismatches are common in fabricated receipts where elements are mixed from different sources.  
- **Weight:** +0.30 (high)  
- **Severity:** CRITICAL  
- **Supported Regions:** US, CA, IN, UK, EU, AU, SG, MY, TH, ID, PH, JP, CN, HK, TW, KR, NZ, UAE, SA, OM, QA, KW, BH, JO  
- **Intelligence:**  
  - Cross-border detection (no penalty for multi-region receipts)  
  - Travel/hospitality context awareness (penalty reduced by 0.15)  
  - STRICT vs RELAXED tier enforcement

**GEO2 – Tax regime mismatch** 🆕  
- **What:** Detected tax terminology doesn't match expected regime for the region.  
- **Example:** USD receipt with GST (Indian tax) terminology.  
- **Why:** Tax regimes are jurisdiction-specific. USD invoices should not have GST, and INR invoices should not have US sales tax.  
- **Weight:** +0.18 (high)  
- **Severity:** CRITICAL  
- **Tax Regimes:** GST (India/SG/AU), VAT (UK/EU/Middle East), HST/PST (Canada), SALES_TAX (US)

**GEO3 – Healthcare merchant-currency plausibility** 🆕  
- **What:** US healthcare provider (hospital/clinic/medical) billing in CAD or INR without Canadian/Indian geography evidence.  
- **Why:** US healthcare providers don't typically bill in foreign currencies unless there's clear cross-border context.  
- **Weight:** +0.22 (CAD) or +0.18 (INR)  
- **Severity:** CRITICAL  
- **Detection:** Merchant name contains healthcare terms + currency mismatch + no foreign geography

---

### 🏪 Merchant Validation System

**MER1 – Merchant looks like label** 🆕  
- **What:** Merchant name appears to be a field label (contains "INVOICE", "RECEIPT", "ORDER", "TOTAL", etc.).  
- **Why:** Real merchant names are business names, not field labels. This indicates the LLM/OCR extracted a label instead of the actual merchant.  
- **Weight:** +0.18 (high)  
- **Severity:** CRITICAL

**MER2 – Merchant looks like identifier** 🆕  
- **What:** Merchant contains many digits (≥4) and more digits than letters.  
- **Why:** Merchant names are business names, not invoice/receipt numbers. This pattern indicates extraction error or fabrication.  
- **Weight:** +0.18 (high)  
- **Severity:** CRITICAL

**MER3 – Merchant starts with label prefix** 🆕  
- **What:** Merchant begins with "invoice", "receipt", "order" prefix.  
- **Why:** Real merchant names don't start with document type labels. This is a clear extraction error.  
- **Weight:** +0.12 (medium)  
- **Severity:** CRITICAL

---

### 🏷️ Severity Tagging System

All fraud reasons are now tagged with severity levels for intelligent ensemble decision-making:

- **[HARD_FAIL]**: Structural inconsistencies that strongly indicate fraud  
  - Examples: Impossible date sequence, suspicious software (Canva/Photoshop)  
  - Ensemble behavior: Forces "fake" verdict with 0.93 confidence  
  - Visual realism cannot override hard-fail indicators

- **[CRITICAL]**: Strong fraud indicators requiring review  
  - Examples: Currency mismatch, tax regime mismatch, merchant validation failures  
  - Ensemble behavior: High weight in decision (0.85 confidence if rule score ≥0.7)  
  - Triggers human review if conflicting with vision assessment

- **[INFO]**: Normal explanatory reasons  
  - Examples: Missing metadata, low text quality, document type observations  
  - Ensemble behavior: Informational only, contributes to score but doesn't force verdict

**Performance Optimization:**  
- Tag-first checking: 166x faster than regex pattern matching  
- O(n) complexity for tagged reasons vs O(n*m) for patterns  
- Backward compatible with untagged reasons

---

### 🤖 Ensemble Reconciliation Events

The ensemble verdict system now generates **structured reconciliation events** that track the complete decision path with full evidence for audit compliance.

**Decision Path Events:**

1. **ENS_HARD_FAIL_WINS**
   - Rule engine HARD_FAIL overrides visual assessment
   - Confidence: 0.93
   - Evidence: rule_label, rule_score, hard_fail_count, hard_fail_reasons, vision_verdict, agreement_score

2. **ENS_RULES_STRONG_REJECT**
   - Rule engine strong fraud indicators trigger rejection
   - Confidence: 0.85
   - Evidence: rule_score, critical_count, critical_reasons, vision_verdict

3. **ENS_VISION_RULE_CONFLICT_REVIEW**
   - Vision highly confident REAL but rules flagged anomalies
   - Routed to human review
   - Confidence: 0.70
   - Evidence: vision/rule verdicts, critical_reasons, agreement_score, converged_confidence

4. **ENS_ALIGN_APPROVE**
   - Vision and rules align; approved
   - Confidence: Blended = 0.70 + (0.15 × vision_conf) + (0.20 × agreement)
   - Evidence: vision/rule verdicts, agreement_score, converged_confidence_level

5. **ENS_VISION_LOW_RULES_AGREE_APPROVE**
   - Vision low-confidence; approved based on rules + high agreement
   - Confidence: Blended = 0.55 + (0.25 × agreement) + (0.20 × (1-rule_score))
   - Evidence: agreement_score, converged_confidence_level

6. **ENS_VISION_LOW_DEFER_REVIEW**
   - Vision low-confidence; deferred to human review using rule signals
   - Confidence: Blended = 0.45 + (0.20 × agreement) + (0.20 × (1-rule_score))
   - Evidence: has_critical_indicator, agreement_threshold, approve_gate_passed

7. **ENS_DEFAULT_REVIEW**
   - Defaulted to human review due to conflict/insufficient evidence
   - Confidence: 0.65
   - Evidence: all engine verdicts and scores

**Confidence Normalization:**

The `_normalize_confidence()` method handles:
- 0-1 floats (direct use)
- 0-100 percentages (divided by 100)
- String percentages ('70%' → 0.70)
- String levels ('high' → 0.90, 'medium' → 0.70, 'low' → 0.40)
- Defaults and bounds enforcement (always 0.0-1.0)

**Benefits:**
- ✅ **Full audit trail** for every ensemble decision
- ✅ **Transparent decision logic** with structured evidence
- ✅ **Consistent confidence values** across all engines
- ✅ **Compliance-ready** for regulatory review

---

---

## 📊 Comprehensive Audit Trail System

VeriReceipt provides a **complete, structured audit trail** for every decision, ensuring regulatory compliance and full transparency.

### **Audit Components**

**1. AuditEvent (Structured Events)**
- `event_id`: UUID for unique identification
- `ts`: ISO-8601 timestamp
- `source`: Origin (ensemble, rule_engine, vision_llm, etc.)
- `type`: Event type (reconciliation, rule_triggered, normalization, etc.)
- `severity`: HARD_FAIL / CRITICAL / WARNING / INFO
- `code`: Stable identifier (e.g., R5_NO_AMOUNTS, ENS_HARD_FAIL_WINS)
- `message`: Human-readable explanation
- `evidence`: Machine-queryable metadata (dict)

**2. LearnedRuleAudit (Feedback-Derived Rules)**
- `pattern`: Pattern identifier (e.g., "missing_elements", "spacing_anomaly")
- `message`: Human-readable explanation
- `confidence_adjustment`: Signed delta applied by learned rules
- `times_seen`: Number of times users flagged this pattern
- `severity`: INFO / WARNING / CRITICAL
- `evidence`: Additional context (doc_family, gating, etc.)

**3. Reconciliation Events (Ensemble Decision Path)**

All ensemble decisions include structured reconciliation events:

- **ENS_DOC_PROFILE_TAGS** - Document classification metadata
- **ENS_VISION_CONF_NORMALIZED** - Vision LLM confidence normalization trace
- **ENS_LEARNED_RULES_APPLIED** - Learned rule summary (patterns, adjustments)
- **ENS_HARD_FAIL_WINS** / **ENS_RULES_STRONG_REJECT** / etc. - Decision path events
- **ENS_FINAL_DECISION** - Complete decision summary with all evidence

Each event includes:
- Vision verdict and confidence
- Rule label and score
- Critical count and agreement score
- Learned rule count and patterns
- Document profile (family, subtype, confidence)
- Converged extraction confidence

### **Viewing Audit Records**

**Quick View (Latest Analysis):**
```bash
python view_audit_records.py
```

**View Last N Analyses:**
```bash
python view_audit_records.py --last 5
```

**View Specific Decision:**
```bash
python view_audit_records.py --decision-id <uuid>
```

**Test Audit Trail:**
```bash
python test_audit_trail.py  # Analyze a PDF and view audit events
```

### **Audit Trail Storage**

**CSV Log:** `data/logs/decisions.csv`
- `audit_events` column contains JSON array of AuditEvent objects
- `learned_rule_audits` column contains JSON array of LearnedRuleAudit objects
- `events` column contains legacy rule events (backward compatible)

**API Response:**
- Ensemble verdict includes `reconciliation_events` array
- Rule-based results include `events` array with structured evidence

### **Benefits**

✅ **Regulatory Compliance** - Complete audit trail for every decision  
✅ **Machine-Queryable** - Structured JSON evidence for analytics  
✅ **Learned Rule Transparency** - Track pattern, frequency, and adjustments  
✅ **Document-Aware Gating** - Visibility into conditional rule application  
✅ **Ensemble Decision Path** - 7 scenarios with full evidence  
✅ **Confidence Traceability** - Normalization and blending logic exposed  
✅ **Easy Viewing** - Utility scripts for human-readable audit reports  

---

**Developer Notes:**  
- All weights and thresholds live in `app/pipelines/rules.py`.  
- They are intentionally simple constants to make experimentation easy.  
- When adjusting weights, keep the **relative severity** in mind rather than absolute values.  
- In the future, these rules can be moved to a config file (YAML/JSON) to make the engine data-driven.
- Document profile detection uses keyword-based heuristics in `app/pipelines/features.py`.
- Ensemble reconciliation events are generated in `app/pipelines/ensemble.py`.
- Audit events are created in `app/schemas/receipt.py` and populated in `app/api/main.py`.
- Learned rule events are emitted in `app/pipelines/rules.py` with `LR_LEARNED_PATTERN` rule_id.

---

## 🗺 Roadmap

### **Phase 1 — Core Foundations (✅ COMPLETE)**
- [x] Project setup  
- [x] Ingestion + OCR pipeline  
- [x] Metadata extraction  
- [x] Feature engineering (14 fraud rules)
- [x] Rule engine v1  
- [x] FastAPI backend with 6 endpoints
- [x] Docker deployment setup
- [x] Human feedback loop & ML training

### **Phase 2 — AI Integration & Learning System (✅ COMPLETE)**
- [x] Vision LLM integration (fraud detection + authenticity)
- [x] LayoutLM integration (data extraction)
- [x] Ensemble verdict system with critical overrides
- [x] **Document Profile Detection System** 🆕
  - [x] 31 document subtypes across 3 families (TRANSACTIONAL, LOGISTICS, PAYMENT)
  - [x] Keyword-based classification with confidence scoring
  - [x] Document-aware rule validation (conditional R5, R6, R8)
  - [x] Evidence tracking for audit compliance
- [x] **Ensemble Reconciliation Events** 🆕
  - [x] 7 structured decision path events
  - [x] Confidence normalization (handles floats, percentages, string levels)
  - [x] Complete audit trail for regulatory compliance
  - [x] Learned rule integration in ensemble decisions
- [x] **Comprehensive Audit Trail System** 🆕
  - [x] Structured AuditEvent dataclass with UUID and timestamps
  - [x] LearnedRuleAudit tracking (pattern, adjustment, frequency)
  - [x] Reconciliation events from ensemble (ENS_* codes)
  - [x] Document profile tags in audit evidence
  - [x] Machine-queryable decision evidence
  - [x] CSV persistence with full JSON audit columns
  - [x] Utility scripts (view_audit_records.py, test_audit_trail.py)
- [x] **Comprehensive Feedback System**
  - [x] Detailed feedback form UI
  - [x] Indicator-level reviews (confirm/false alarm/uncertain)
  - [x] Missed indicator tracking (10 structured patterns)
  - [x] Data correction learning
  - [x] Enhanced learning engine
    - [x] Reinforce confirmed indicators (+0.02)
    - [x] Reduce false indicators (-0.08)
    - [x] Create rules for missed patterns (+0.15)
    - [x] Learn from data corrections
    - [x] Whitelist system for false alarms
  - [x] Stats dashboard with learned rules
  - [x] Local SQLite storage (GDPR compliant)
- [ ] Collect diverse dataset (real + fake receipts)
- [ ] Fine-tune Vision LLM on user feedback
- [ ] Fine-tune DONUT on extraction corrections
- [ ] Reinforcement learning for ensemble weights

### **Phase 3 — Production System**
- [x] FastAPI backend
- [x] Docker deployment
- [x] Analysis logging & monitoring
- [ ] Web dashboard for finance teams
- [ ] Authentication & authorization
- [ ] Rate limiting

### **Phase 4 — Commercialization**
- [ ] Multi-tenant SaaS support
- [ ] API rate limiting & auth
- [ ] Billing & usage metering
- [ ] Marketplace integrations (Expensify, Concur)

---

## 📘 API Documentation

VeriReceipt provides a complete REST API for receipt analysis and feedback collection.

### Quick Start

```bash
# Start the API server
python run_api.py

# Access interactive documentation
# Swagger UI: http://localhost:8080/docs
# ReDoc: http://localhost:8080/redoc
```

### Key Endpoints

**Analysis:**
- **POST /api/analyze/hybrid** - Multi-engine analysis (Rule-Based + Vision LLM + LayoutLM)
- **POST /api/analyze/rule-based** - Rule-based only analysis
- **POST /api/analyze/vision** - Vision LLM only analysis
- **POST /api/analyze/batch** - Batch analysis (up to 50 receipts)

**Feedback & Learning:** 🆕
- **POST /feedback/submit** - Submit comprehensive feedback
- **GET /feedback/stats** - Get feedback statistics
- **GET /feedback/history** - View feedback history
- **GET /feedback/learned-rules** - List all learned rules
- **POST /feedback/rules/{id}/toggle** - Enable/disable learned rule
- **GET /feedback/export** - Export learned rules
- **POST /feedback/import** - Import learned rules

**System:**
- **GET /health** - Health check
- **GET /stats** - System statistics

### Documentation

- **[API Guide](API_GUIDE.md)** - Complete API reference with examples
- **[Human Feedback Guide](HUMAN_FEEDBACK_GUIDE.md)** - Learning system documentation

### Example Usage

```python
import requests

# Analyze a receipt
with open("receipt.jpg", "rb") as f:
    response = requests.post("http://localhost:8080/analyze", files={"file": f})
    result = response.json()
    print(f"Label: {result['label']}, Score: {result['score']}")

# Submit feedback
feedback = {
    "analysis_ref": "receipt.jpg",
    "given_label": "fake",
    "comment": "Verified as fabricated"
}
requests.post("http://localhost:8080/feedback", json=feedback)
```

---

## 💬 Contact

For support or contributions, feel free to reach out.

---

## 🎉 VeriReceipt — AI That Knows What’s Real