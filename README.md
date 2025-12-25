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
      features.py         # Feature engineering (14+ signals)
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
- ✅ Rule-based fraud engine (14+ rules)
- ✅ Vision LLM integration (fraud detection + authenticity)
- ✅ LayoutLM integration (data extraction)
- ✅ Ensemble verdict system
- ✅ **Comprehensive Feedback System** 🆕
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

| ID  | Rule                                    | Condition (Trigger)                                                                                 | Weight | Severity       |
|-----|-----------------------------------------|------------------------------------------------------------------------------------------------------|--------|----------------|
| R1  | Suspicious producer/creator             | PDF `producer`/`creator` contains known editing/template tools (Canva, Photoshop, WPS, etc.)        | +0.30  | High           |
| R2  | Missing creation date                   | No `creation_date` metadata                                                                        | +0.05  | Low            |
| R3  | Missing modification date               | No `mod_date` metadata                                                                             | +0.05  | Low            |
| R4  | No EXIF data (images)                   | `exif_present = False` for image receipts                                                          | +0.05  | Low            |
| R5  | No detected amounts                     | No currency/amount tokens detected in OCR text                                                     | +0.40  | High           |
| R6  | Amounts but no total line               | `has_any_amount = True` and `total_line_present = False`                                           | +0.15  | Medium         |
| R7  | Line-item vs total mismatch             | `total_mismatch = True` (sum of line items ≠ printed total)                                        | +0.40  | High           |
| R8  | No date found                           | `has_date = False`                                                                                 | +0.20  | Medium–High    |
| R9  | No merchant candidate                   | `merchant_candidate` could not be confidently inferred                                             | +0.15  | Medium         |
| R10 | Too few lines                           | `num_lines < 5`                                                                                  | +0.15  | Medium         |
| R11 | Too many lines                          | `num_lines > 120`                                                                                | +0.10  | Low–Medium     |
| R12 | Very high numeric line ratio            | `numeric_line_ratio > 0.8` and `num_lines > 10`                                              | +0.10  | Low–Medium     |
| R13 | High uppercase ratio                    | `uppercase_ratio > 0.8` and `num_lines > 5`                                                  | +0.10  | Low–Medium     |
| R14 | Low character variety                   | `unique_char_count < 15` and `num_lines > 5`                                                 | +0.15  | Medium         |

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

**R5 – No detected amounts**  
- **What:** OCR text contains no recognizable currency/amount pattern.  
- **Why:** A receipt without any numeric amount is almost never valid. Often indicates OCR failure or synthetic text.  
- **Weight:** +0.40 (high).

**R6 – Amounts but no total line**  
- **What:** Amounts exist but no line with "Total/Grand Total/Amount Payable/etc." found.  
- **Why:** Most receipts clearly mark the total; absence suggests an incomplete or template-style artifact.  
- **Weight:** +0.15 (medium).

**R7 – Line-item vs total mismatch**  
- **What:** Sum of detected line-item amounts does not match the printed total (above a small tolerance).  
- **Why:** Strong signal of manual tampering with the total or error in fabrication.  
- **Weight:** +0.40 (high).

**R8 – No date found**  
- **What:** No date-like pattern detected in OCR text.  
- **Why:** Valid receipts almost always include a date; missing date is a compliance red flag.  
- **Weight:** +0.20 (medium–high).

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

---

**Developer Notes:**  
- All weights and thresholds live in `app/pipelines/rules.py`.  
- They are intentionally simple constants to make experimentation easy.  
- When adjusting weights, keep the **relative severity** in mind rather than absolute values.  
- In the future, these rules can be moved to a config file (YAML/JSON) to make the engine data-driven.

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
- [x] **Comprehensive Feedback System** 🆕
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