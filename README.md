# VeriReceipt – AI-Powered Receipt Fraud Detection System

VeriReceipt is an intelligent fraud-detection system that identifies **fake, AI-generated, manipulated, or tampered receipts** using a hybrid approach combining **5 AI engines**, **geo-aware rules**, **document forensics**, and **comprehensive audit trails**.

[![Status](https://img.shields.io/badge/status-production--ready-brightgreen)](https://github.com)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB)](https://react.dev/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)

---

## 🚀 Why VeriReceipt?

Businesses lose millions annually due to:
- 🎨 AI-generated receipts (Canva, Photoshop, fake receipt apps)
- 💰 Digitally altered totals and line items
- 📅 Edited dates, vendor names, or payment details
- 📄 PDF metadata tampering
- 🌍 Cross-border currency/tax inconsistencies
- 🏪 Fake merchant information

**VeriReceipt stops this using a 5-engine hybrid AI pipeline with comprehensive audit trails.**

---

## ✨ Key Features

### 🤖 **5-Engine Hybrid Architecture** (3 engines active by default)
- **Rule-Based Engine** - 34+ fraud detection rules with forensic decision logic (PRIMARY DECISION) ✅ Active
  - Confidence-based gating (prevents over-penalization of uncertain documents)
  - Hardened merchant extraction (eliminates 60-70% of false positives)
  - Conditional severity (date gaps, doc-type ambiguity)
  - Learned rule impact capping
- **Vision LLM** (Ollama/PyTorch) - **Veto-only tampering detection** (can only reject, never approve) ✅ Active
- **LLM Classifier** (Ollama/OpenAI) - Gated fallback for ambiguous document classification ✅ Active
- **LayoutLM** - Multimodal document understanding and field extraction ⚠️ Optional
- **DONUT** - Document understanding transformer ⚠️ Optional

**Vision Veto-Only Design:**
```
Vision is a sensor, not a judge.
It can pull the emergency brake, but never press the accelerator.
```
- ✅ `tampered` → HARD_FAIL (receipt rejected)
- ✅ `suspicious` → audit only (rules decide)
- ✅ `clean` → no effect (rules decide)

### 🌍 **Global Geo-Aware Validation** ✅ **Recently Enhanced**
- **24 regions/countries** supported (US, CA, IN, UK, EU, AU, SG, MY, TH, ID, PH, JP, CN, HK, TW, KR, NZ, UAE, SA, OM, QA, KW, BH, JO)
- **Hardened geo detection** with false positive elimination:
  - Removed ambiguous 6-digit postal patterns (eliminated India false positives)
  - Multi-signal requirement (≥2 signals for India detection)
  - Confidence-based UNKNOWN gating (confidence < 0.30 → UNKNOWN)
  - Canonical data sourcing (all gates use final geo output)
- Currency-geography consistency checking
- Tax regime validation (GST, VAT, HST, PST, Sales Tax)
- Cross-border transaction detection
- Healthcare merchant-currency plausibility

### 📋 **Intelligent Document Classification**
- **50+ document subtypes** across 5 families:
  - **TRANSACTIONAL**: POS receipts, invoices, bills, subscriptions
  - **LOGISTICS**: Shipping bills, bills of lading, air waybills, delivery notes
  - **STATEMENT**: Bank statements, card statements
  - **PAYMENT**: Payment receipts, bank slips, card charge slips, refunds
  - **CLAIMS**: Insurance claims, medical claims, expense claims
- **Domain Pack System** - Declarative YAML-based domain inference
  - Hard-gating on required fields (80% reduction in false positives)
  - Negative keyword enforcement (prevents misclassification)
  - Telecom, logistics, insurance, healthcare, ecommerce domains
- **LLM Classifier Fallback** - Gated AI classification for ambiguous documents
  - Local Ollama support (llama3.2:3b) - zero infrastructure cost
  - OpenAI support (gpt-4o-mini) - low-cost gated calls (pricing varies by usage)
  - Only triggers on low-confidence cases (15-25% of documents)
- Context-aware validation (logistics docs don't need totals)
- Confidence-based rule gating

### 📊 **Comprehensive Audit System**
- **Formatted audit reports** for human review
- Executive summary with fraud risk score
- Geo-aware classification context
- Missing field analysis with gate reasoning
- Critical events breakdown
- Auditor recommendations
- Copy-to-clipboard functionality

### 🎯 **Modern Web UI**
- **Tabbed interface** with 3 views:
  - **Verdict Tab** - Hybrid verdict with all engine results
  - **Audit Report Tab** - Full formatted audit report
  - **Analysis Log Tab** - Real-time processing timeline
- Real-time progress tracking
- Engine status transparency
- Human review workflow
- Feedback collection system

### � **Warranty Claims Fraud Detection** ✅ **New Module**
- **PDF Warranty Claim Analysis** — Upload warranty claim PDFs for automated fraud detection
  - AI-powered extraction of VIN, customer, vehicle, issue, and amount data
  - Risk scoring (0–100%) with triage classification (AUTO_APPROVE / REVIEW / INVESTIGATE)
  - Fraud signal detection (suspicious amounts, date anomalies, duplicate submissions)
- **Duplicate Detection Engine** — Multi-layer duplicate identification:
  - **Image-level:** Exact file hash matching + perceptual hash (pHash) similarity
  - **Claim-level:** Same VIN + similar issue description + date proximity
  - Dynamic template filtering (banners/logos excluded via aspect ratio + frequency analysis)
  - Grouped duplicate audit view showing all linked claims with match reasons
- **Interactive Dashboard** with 6 KPI cards (all clickable with drill-down):
  - Total Claims, Auto Approved, Review, Investigate, Suspicious, Duplicates
  - Claims by Root Cause (horizontal bar chart, filterable by brand/model/issue)
  - Claims by Vehicle Brand (doughnut chart)
  - Claims Over Time (trend line)
  - Claims by Dealer (bar chart)
  - Fraud Signals Distribution (radar chart)
  - Duplicate Statistics (dedicated panel)
- **PDF Viewing** — View original warranty claim PDFs for both analyzed and linked duplicate claims
- **Advanced Filtering** — Filter root cause chart by:
  - Vehicle brand (e.g., Chevrolet, Honda)
  - Vehicle model (e.g., Chevrolet Malibu)
  - Issue type / root cause (e.g., Engine overheating, Alternator malfunction)
- **Claim Detail Modal** — Click any claim ID to view full details with inline PDF viewer

### � **Learning & Feedback System**
- Indicator-level feedback (✅ Correct / ❌ False Alarm)
- Missed indicator tracking
- Data correction learning
- Pattern learning (merchants, addresses)
- Local learning engine with SQLite storage
- Stats dashboard

---

## 🏗 System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Receipt Upload (PDF/Image)                │
└────────────────────────────┬────────────────────────────────┘
                             ▼
                  ┌──────────────────────┐
                  │  Ingestion Pipeline  │
                  │  - PDF/Image Load    │
                  │  - Normalization     │
                  │  - PDF→Image Convert │
                  └──────────┬───────────┘
                             ▼
        ┌────────────────────┴────────────────────┐
        ▼                                         ▼
┌───────────────┐                        ┌────────────────┐
│   Metadata    │                        │  OCR & Text    │
│   Extraction  │                        │  Extraction    │
│ - PDF meta    │                        │ - EasyOCR      │
│ - EXIF data   │                        │ - Tesseract    │
│ - Timestamps  │                        │ - Text parsing │
└───────┬───────┘                        └────────┬───────┘
        └────────────────────┬────────────────────┘
                             ▼
                  ┌──────────────────────┐
                  │ Feature Extraction   │
                  │ - Forensic signals   │
                  │ - Text patterns      │
                  │ - Layout analysis    │
                  │ - Geo detection      │
                  └──────────┬───────────┘
                             ▼
        ┌────────────────────┴────────────────────┐
        │         5-Engine Parallel Analysis       │
        └────────────────────┬────────────────────┘
                             ▼
    ┌────────┬────────┬────────┬────────┬────────┐
    ▼        ▼        ▼        ▼        ▼        ▼
┌────────┐ ┌────┐ ┌────────┐ ┌─────┐ ┌──────────┐
│ Rule-  │ │Vision│ │LayoutLM│ │DONUT│ │ Donut-   │
│ Based  │ │ LLM │ │        │ │     │ │ Receipt  │
│ Engine │ │     │ │        │ │     │ │          │
└───┬────┘ └──┬─┘ └────┬───┘ └──┬──┘ └────┬─────┘
    └─────────┴────────┴────────┴─────────┘
                       ▼
            ┌──────────────────────┐
            │  Ensemble Verdict    │
            │  - Reconciliation    │
            │  - Confidence blend  │
            │  - Critical override │
            └──────────┬───────────┘
                       ▼
            ┌──────────────────────┐
            │   Audit Formatter    │
            │   - Executive summary│
            │   - Geo context      │
            │   - Event breakdown  │
            │   - Recommendations  │
            └──────────┬───────────┘
                       ▼
            ┌──────────────────────┐
            │  Final Decision      │
            │  - Label + Score     │
            │  - Reasoning         │
            │  - Audit Report      │
            └──────────┬───────────┘
                       ▼
            ┌──────────────────────┐
            │   Human Review       │
            │   - Feedback form    │
            │   - Corrections      │
            │   - Learning loop    │
            └──────────────────────┘
```

---

## 📦 Project Structure

```
VeriReceipt/
├── app/
│   ├── pipelines/
│   │   ├── ingest.py              # PDF/Image ingestion
│   │   ├── metadata.py            # PDF metadata & EXIF extraction
│   │   ├── ocr.py                 # EasyOCR + Tesseract
│   │   ├── features.py            # Feature engineering (18+ signals)
│   │   ├── geo_detection.py       # 🌍 Geo-aware classification (24 regions)
│   │   ├── rules.py               # Rule-based engine (34+ rules)
│   │   ├── vision_llm.py          # Vision LLM (Ollama/PyTorch)
│   │   ├── layoutlm_extractor.py  # LayoutLM data extraction
│   │   ├── donut_extractor.py     # DONUT document understanding
│   │   ├── ensemble.py            # Multi-engine verdict convergence
│   │   └── learning.py            # Feedback learning engine
│   ├── models/
│   │   └── feedback.py            # Feedback data models
│   ├── repository/
│   │   ├── receipt_store.py       # Receipt storage
│   │   └── feedback_store.py      # SQLite feedback storage
│   ├── api/
│   │   ├── main.py                # FastAPI endpoints
│   │   ├── feedback.py            # Feedback API routes
│   │   └── warranty_routes.py     # 🔧 Warranty claims API (analyze, dashboard, duplicates)
│   ├── warranty/                   # 🔧 Warranty claims module
│   │   ├── __init__.py
│   │   ├── models.py              # Warranty data models (WarrantyClaim, ClaimAnalysisResult)
│   │   ├── extractor.py           # PDF extraction (text, images, hashes)
│   │   ├── pipeline.py            # Analysis pipeline (extract → hash → duplicates → signals)
│   │   ├── duplicates.py          # Duplicate detection (image hash, VIN, issue similarity)
│   │   ├── signals.py             # Fraud signal detection (amounts, dates, patterns)
│   │   ├── db.py                  # Database operations (SQLite/PostgreSQL dual-mode)
│   │   └── bootstrap.py           # Schema creation and seed data
│   ├── schemas/
│   │   └── receipt.py             # Pydantic schemas
│   └── utils/
│       └── audit_formatter.py     # 📊 Audit report formatter
├── web/
│   ├── index.html                 # 🎨 Main receipt analysis UI (tabbed interface)
│   ├── warranty.html              # 🔧 Warranty claims UI (analyze + dashboard)
│   ├── review.html                # Human feedback form
│   ├── stats.html                 # Feedback stats dashboard
│   └── audit_report.html          # Standalone audit viewer
├── data/
│   ├── raw/                       # Test receipts
│   ├── processed/
│   ├── warranty_pdfs/             # 🔧 Stored warranty claim PDFs
│   └── feedback.db                # Local feedback database
├── docs/
│   ├── GEO_AWARE_CLASSIFICATION.md   # Geo-aware system docs
│   └── FEEDBACK_WORKFLOW_SUMMARY.md  # Feedback system docs
├── requirements.txt
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Ollama (for Vision LLM)
- Tesseract OCR

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/VeriReceipt.git
cd VeriReceipt

# Install Python dependencies
pip install -r requirements.txt

# Install Tesseract (macOS)
brew install tesseract

# Install Ollama and pull vision model
brew install ollama
ollama pull llama3.2-vision:latest
```

### Start the Server

```bash
# Start FastAPI backend
uvicorn app.api.main:app --reload --port 8000

# Access web UI
open http://localhost:8000/web/index.html
```

---

## 🎯 Usage

### Web UI (Recommended)

1. **Navigate to** `http://localhost:8000/web/index.html`
2. **Upload** a PDF or image receipt
3. **Click "Analyze Receipt"** (wait 3-5 minutes for all engines)
4. **View results** in tabbed interface:
   - **Verdict Tab** - See all 5 engine results and hybrid verdict
   - **Audit Report Tab** - View comprehensive formatted audit report
   - **Analysis Log Tab** - Review processing timeline
5. **Click "Review Receipt"** to provide feedback

### API Endpoints

#### 1. Fast Analysis (Rule-Based Only)
```bash
curl -X POST "http://localhost:8000/analyze" \
  -F "file=@receipt.pdf"
```

**Response:**
```json
{
  "label": "SUSPICIOUS",
  "score": 0.65,
  "reasons": [
    "[HARD_FAIL] Suspicious Software Detected: ilovepdf",
    "[CRITICAL] Currency-Geography Mismatch: CAD with only US signals"
  ],
  "audit_report": "╔═══════════════════════════════════╗\n║  VERIRECEIPT AUDIT REPORT  ║\n╚═══════════════════════════════════╝\n..."
}
```

#### 2. Hybrid Analysis (All 5 Engines)
```bash
curl -X POST "http://localhost:8000/analyze/hybrid" \
  -F "file=@receipt.pdf"
```

**Response:**
```json
{
  "receipt_id": "abc123",
  "rule_based": {
    "label": "SUSPICIOUS",
    "score": 0.65,
    "audit_report": "..."
  },
  "vision_llm": {
    "verdict": "REAL",
    "confidence": 0.85
  },
  "layoutlm": {
    "merchant": "Acme Corp",
    "total": 1234.56,
    "date": "2024-01-15"
  },
  "donut": { ... },
  "donut_receipt": { ... },
  "hybrid_verdict": {
    "final_label": "HUMAN_REVIEW",
    "confidence": 0.70,
    "reasoning": [...]
  }
}
```

#### 3. Submit Feedback
```bash
curl -X POST "http://localhost:8000/feedback" \
  -H "Content-Type: application/json" \
  -d '{
    "receipt_id": "abc123",
    "user_verdict": "real",
    "indicator_reviews": [
      {"indicator": "R1_SUSPICIOUS_SOFTWARE", "is_correct": false}
    ]
  }'
```

#### 4. Warranty Claim Analysis
```bash
# Analyze a warranty claim PDF
curl -X POST "http://localhost:8000/warranty/analyze" \
  -F "file=@warranty_claim.pdf" \
  -F "dealer_id=DLR001"
```

**Response:**
```json
{
  "claim_id": "LGLZWO",
  "risk_score": 0.80,
  "triage_class": "INVESTIGATE",
  "duplicates_found": [
    {"matched_claim_id": "SQG05A", "match_type": "IMAGE_EXACT", "similarity_score": 1.0}
  ],
  "fraud_signals": [
    {"signal_type": "DUPLICATE_IMAGE_EXACT", "severity": "HIGH", "description": "Exact duplicate image found"}
  ]
}
```

#### 5. Warranty Dashboard & Drill-Down
```bash
# Dashboard overview (KPI counts)
curl "http://localhost:8000/warranty/dashboard/overview"

# Root causes filtered by brand and issue
curl "http://localhost:8000/warranty/dashboard/root-causes?brand=Chevrolet&issue=Engine+overheating"

# Drill-down: claims with duplicates
curl "http://localhost:8000/warranty/dashboard/claims?duplicates_only=true"

# Duplicate audit for a specific claim
curl "http://localhost:8000/warranty/duplicates/LGLZWO"

# View stored PDF for a claim
curl "http://localhost:8000/warranty/claim/LGLZWO/pdf"
```

#### 6. Warranty Web UI
```
http://localhost:8000/web/warranty.html
```
- **Analyze tab** — Upload warranty claim PDFs, view risk score, fraud signals, and duplicate audit
- **Dashboard tab** — Interactive charts with KPI cards, root cause analysis, brand/model/issue filters

---

## 📊 Audit Report Features

The audit report provides a comprehensive, human-readable analysis:

### Executive Summary
- Final verdict (LEGITIMATE/SUSPICIOUS/HUMAN_REVIEW)
- Fraud risk score (0.00 - 1.00)
- Key concerns with severity tags

### Geo-Aware Classification Context
- Language detection (confidence score)
- Geographic origin (24 regions supported)
- Document family & subtype
- Geo evidence breakdown

### Missing Field Analysis
- Fields checked vs fields found
- Gate reasoning (why penalties were skipped)
- Document-aware expectations

### Critical Events
- Severity-tagged fraud indicators
- Evidence for each event
- Source attribution

### Auditor Recommendations
- Context-aware next steps
- Verification checklist
- Risk mitigation strategies

**Example:**
```
╔═══════════════════════════════════════════════════════════════════════════╗
║                     VERIRECEIPT AUDIT REPORT                              ║
╚═══════════════════════════════════════════════════════════════════════════╝

Decision ID:     abc123-2024-12-28
Timestamp:       2024-12-28T00:30:00
Final Verdict:   SUSPICIOUS (Score: 0.65)
Policy:          default v0.0.0
Rule Version:    0.0.0

═══════════════════════════════════════════════════════════════════════════
EXECUTIVE SUMMARY
═══════════════════════════════════════════════════════════════════════════

⚠️  Document flagged as SUSPICIOUS - requires human review

Fraud Risk Score: 0.65 / 1.00

Key Concerns:
  1. [HARD_FAIL] Suspicious Software Detected: ilovepdf
  2. [CRITICAL] Currency-Geography Mismatch: CAD with only US signals
  3. [CRITICAL] Tax Regime Mismatch: USD with GST terminology

═══════════════════════════════════════════════════════════════════════════
GEO-AWARE CLASSIFICATION CONTEXT
═══════════════════════════════════════════════════════════════════════════

Language Detection:
  • Detected Language: EN (confidence: 0.85)
  • Interpretation: High confidence English detection

Geographic Origin:
  • Detected Country: US (confidence: 0.45)
  • Interpretation: Low confidence - UNKNOWN geo state

Document Classification:
  • Family: TRANSACTIONAL
  • Subtype: MISC (confidence: 0.20)
  • Interpretation: Low confidence classification - requires corroboration

...
```

---

## 🌍 Geo-Aware Features

### Supported Regions (24)
- **North America:** US, CA
- **Europe:** UK, EU (multi-country)
- **Asia Pacific:** IN, SG, MY, TH, ID, PH, JP, CN, HK, TW, KR, AU, NZ
- **Middle East:** UAE, SA, OM, QA, KW, BH, JO

### Currency Validation
- Detects 20+ currencies (USD, CAD, INR, GBP, EUR, AUD, SGD, etc.)
- Cross-references with geography signals
- Identifies cross-border transactions
- Travel/hospitality context awareness

### Tax Regime Validation
- **GST** (India, Singapore, Australia)
- **VAT** (UK, EU, Middle East)
- **HST/PST** (Canada)
- **Sales Tax** (US)

### Intelligence Features
- Cross-border detection (no false positives on multi-region receipts)
- STRICT vs RELAXED enforcement tiers
- Healthcare merchant-currency plausibility
- Penalty reduction for travel/hospitality contexts

---

## 🔧 Rule Engine (34+ Rules)

### Forensic Decision Logic

VeriReceipt uses **evidence-based scoring** rather than heuristic stacking:
- Each fraud indicator contributes a weighted score
- Confidence-based gating prevents over-penalization
- Conditional severity for uncertain documents
- Full audit trail for transparency

### Severity Levels

- **[HARD_FAIL]** - Structural inconsistencies (forces rejection)
  - R1: Suspicious software (Canva, Photoshop)
  - R15: Impossible date sequence

- **[CRITICAL]** - Strong fraud indicators (conditional severity)
  - R5-R9: Missing fields (gated by confidence >= 0.55)
  - R16: Date gap (WARNING if dp_conf < 0.4 and gap < 540 days)
  - R9B: Doc-type ambiguity (WARNING for low-confidence transactional docs)
  - GEO1-GEO3: Geo-currency-tax mismatches
  - MER1-MER3: Merchant validation (gated when confidence low)

- **[INFO]** - Explanatory reasons
  - R2-R4: Missing metadata
  - R10-R14: Text quality issues
  - Gate decisions (GATE_MISSING_FIELDS, MERCHANT_IMPLAUSIBLE_GATED)

### Merchant Extraction Hardening

**Eliminates 60-70% of false positives:**
- ✅ Rejects structural labels: "BILL TO", "SHIP TO", "INVOICE", "DATE", etc.
- ✅ Rejects document titles: "COMMERCIAL INVOICE", "PROFORMA INVOICE", etc.
- ✅ Smart next-line preference: "BILL TO" → "Acme Corp Inc" (company name)
- ✅ Company name detection with indicator matching

### Document-Aware Validation

Rules automatically adjust based on document type and confidence:

- **Logistics documents** (Air Waybills, Bills of Lading):
  - ✅ No penalty for missing totals/amounts
  - ✅ No penalty for missing dates
  
- **Payment documents** (Bank Slips, Payment Receipts):
  - ✅ Different validation for transaction confirmations

- **Confidence-based gating:**
  - `dp_conf < 0.55`: Missing-field penalties **disabled**
  - `dp_conf < 0.55`: Learned rule impact **capped at ±0.05**
  - `dp_conf < 0.4` + `gap < 540 days`: Date gap **downgraded to WARNING**
  - `dp_conf < 0.4` + `TRANSACTIONAL`: Doc-type ambiguity **downgraded to WARNING**

---

## 🤖 AI Models

### 1. Rule-Based Engine
- **34+ fraud detection rules**
- Geo-aware validation (24 regions)
- Document-aware expectations
- Severity-tagged reasoning
- **Speed:** ~2-5 seconds

### 2. Vision LLM (Ollama)
- **Model:** llama3.2-vision:latest (10.7B parameters)
- Visual authenticity assessment
- Fraud pattern detection
- **Speed:** ~2-5 minutes (configurable timeout: 300s)

### 3. LayoutLM
- **Model:** microsoft/layoutlmv3-base
- Multimodal document understanding
- Field extraction (merchant, total, date)
- **Speed:** ~5-10 seconds

### 4. DONUT
- **Model:** naver-clova-ix/donut-base
- Document understanding transformer
- Specialized for receipts
- **Status:** Temporarily disabled (model loading issues)

### 5. Donut-Receipt
- **Model:** Custom receipt parser
- Structured extraction
- **Status:** Temporarily disabled (model loading issues)

---

## 📈 Performance

### Speed
- **Fast mode** (/analyze): ~2-5 seconds (rule-based only)
- **Hybrid mode** (/analyze/hybrid): ~3-5 minutes (all engines)

### Accuracy
- **Rule-based:** High precision on structural fraud
- **Vision LLM:** High accuracy on visual authenticity
- **Ensemble:** Balanced approach with reconciliation

### Scalability
- Parallel engine execution
- Async API endpoints
- Configurable timeouts
- Docker deployment ready

---

## 🔄 Learning & Feedback

### Feedback Collection
- ✅ Correct / ❌ False Alarm indicator reviews
- Missed indicator tracking
- Data corrections (merchant, total, date)
- Free-form notes

### Learning Engine
- Pattern learning (merchants, addresses)
- Rule weight adjustments
- False positive reduction
- SQLite local storage

### Stats Dashboard
- Feedback metrics
- Accuracy trends
- Most corrected indicators
- User engagement stats

---

## 🐳 Docker Deployment

```bash
# Build image
docker build -t verireceipt:latest .

# Run container
docker run -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -e USE_OLLAMA=true \
  verireceipt:latest

# Access UI
open http://localhost:8000/web/index.html
```

---

## 🧪 Testing

```bash
# Run unit tests
pytest tests/

# Test single receipt
python test_run.py data/raw/sample_receipt.pdf

# Test API endpoint
curl -X POST "http://localhost:8000/analyze" \
  -F "file=@data/raw/sample_receipt.pdf"
```

---

## 📚 Documentation

- **[FORENSIC_DECISION_LOGIC.md](docs/FORENSIC_DECISION_LOGIC.md)** - Forensic decision logic & recent improvements
- **[GEO_AWARE_CLASSIFICATION.md](docs/GEO_AWARE_CLASSIFICATION.md)** - Geo-aware system details
- **[FEEDBACK_WORKFLOW_SUMMARY.md](docs/FEEDBACK_WORKFLOW_SUMMARY.md)** - Feedback system guide
- **[CHANGELOG.md](CHANGELOG.md)** - Version history and recent changes
- **API Documentation:** `http://localhost:8000/docs` (Swagger UI)

---

## 🛣 Roadmap

### ✅ Completed
- Core fraud detection engine
- 5-engine hybrid analysis
- Geo-aware validation (24 regions)
- Document classification (31 subtypes)
- Comprehensive audit reports
- Tabbed web UI
- Feedback & learning system
- **Forensic decision logic** (Jan 2026)
  - Merchant extraction hardening (60-70% false positive reduction)
  - Confidence-based gating (prevents over-penalization)
  - Conditional severity (date gaps, doc-type ambiguity)
  - Learned rule impact capping
- **Warranty Claims Fraud Detection** (Feb 2026)
  - PDF claim analysis with AI-powered data extraction
  - Multi-layer duplicate detection (image hash + perceptual hash + VIN matching)
  - Interactive dashboard with 6 KPI cards and 7 chart panels
  - Root cause filtering by brand, model, and issue type
  - PDF storage and viewing for analyzed and linked duplicate claims
  - Claim detail modal with inline PDF viewer
  - PostgreSQL + SQLite dual-mode database support

### 🔄 In Progress
- Enhanced pattern learning
- ML model fine-tuning preparation
- Active learning features
- Production deployment optimization

### 📋 Planned
- Fine-tune Vision LLM on user feedback
- Fine-tune DONUT on extraction corrections
- Reinforcement learning for ensemble weights
- Production deployment with fine-tuned models
- Mobile app integration
- Blockchain audit trail

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **FastAPI** - Modern web framework
- **React** - UI framework
- **Ollama** - Local LLM inference
- **Microsoft LayoutLM** - Document understanding
- **Naver DONUT** - Receipt parsing
- **EasyOCR** - Text extraction
- **Tesseract** - OCR engine

---

## 📞 Support

- **Issues:** [GitHub Issues](https://github.com/yourusername/VeriReceipt/issues)
- **Discussions:** [GitHub Discussions](https://github.com/yourusername/VeriReceipt/discussions)
- **Email:** support@verireceipt.com

---

## 🌟 Star History

If you find VeriReceipt useful, please consider giving it a star ⭐

---

**Built with ❤️ for fraud prevention and financial integrity**
