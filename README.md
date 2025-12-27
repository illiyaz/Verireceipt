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

### 🤖 **5-Engine Hybrid Analysis**
- **Rule-Based Engine** - 34+ fraud detection rules with geo-awareness
- **Vision LLM** (Ollama/PyTorch) - Visual authenticity assessment
- **LayoutLM** - Multimodal document understanding and field extraction
- **DONUT** - Document understanding transformer
- **Donut-Receipt** - Specialized receipt parsing

### 🌍 **Global Geo-Aware Validation**
- **24 regions/countries** supported (US, CA, IN, UK, EU, AU, SG, MY, TH, ID, PH, JP, CN, HK, TW, KR, NZ, UAE, SA, OM, QA, KW, BH, JO)
- Currency-geography consistency checking
- Tax regime validation (GST, VAT, HST, PST, Sales Tax)
- Cross-border transaction detection
- Healthcare merchant-currency plausibility

### 📋 **Intelligent Document Classification**
- **31 document subtypes** across 3 families:
  - **TRANSACTIONAL** (21): Receipts, Invoices, Bills
  - **LOGISTICS** (4): Shipping Bills, Bills of Lading, Air Waybills, Delivery Notes
  - **PAYMENT** (4): Payment Receipts, Bank Slips, Card Charge Slips, Refund Receipts
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

### 🔄 **Learning & Feedback System**
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
│   │   └── feedback.py            # Feedback API routes
│   ├── schemas/
│   │   └── receipt.py             # Pydantic schemas
│   └── utils/
│       └── audit_formatter.py     # 📊 Audit report formatter
├── web/
│   ├── index.html                 # 🎨 Main analysis UI (tabbed interface)
│   ├── review.html                # Human feedback form
│   ├── stats.html                 # Feedback stats dashboard
│   └── audit_report.html          # Standalone audit viewer
├── data/
│   ├── raw/                       # Test receipts
│   ├── processed/
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

### Severity Levels

- **[HARD_FAIL]** - Structural inconsistencies (forces rejection)
  - R1: Suspicious software (Canva, Photoshop)
  - R15: Impossible date sequence

- **[CRITICAL]** - Strong fraud indicators
  - R5-R9: Missing fields (amounts, totals, dates, merchant)
  - GEO1-GEO3: Geo-currency-tax mismatches
  - MER1-MER3: Merchant validation failures

- **[INFO]** - Explanatory reasons
  - R2-R4: Missing metadata
  - R10-R14: Text quality issues

### Document-Aware Validation

Rules automatically adjust based on document type:

- **Logistics documents** (Air Waybills, Bills of Lading):
  - ✅ No penalty for missing totals/amounts
  - ✅ No penalty for missing dates
  
- **Payment documents** (Bank Slips, Payment Receipts):
  - ✅ Different validation for transaction confirmations

- **Confidence-based gating:**
  - Low doc_profile_confidence: reduce learned rule adjustments by 35%
  - Optional field documents: reduce adjustments by 40%

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

- **[GEO_AWARE_CLASSIFICATION.md](docs/GEO_AWARE_CLASSIFICATION.md)** - Geo-aware system details
- **[FEEDBACK_WORKFLOW_SUMMARY.md](docs/FEEDBACK_WORKFLOW_SUMMARY.md)** - Feedback system guide
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

### 🔄 In Progress
- Enhanced pattern learning
- ML model fine-tuning preparation
- Active learning features

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
