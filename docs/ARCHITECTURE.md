# VeriReceipt Architecture

## Overview

VeriReceipt uses a **multi-layered classification and validation pipeline** that combines heuristic profiling, domain inference, intent resolution, and LLM-based fallbacks to accurately classify and validate documents while minimizing false positives.

## Document Classification Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                    1. OCR & Text Extraction                      │
│                    (Tesseract, EasyOCR)                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              2. Geo-Aware Document Profiling                     │
│              (geo_detection.py)                                  │
│                                                                  │
│  • Language detection (fasttext)                                │
│  • Country/region inference (enriched geo database)             │
│  • Document subtype classification (keyword-based)              │
│  • Confidence scoring with MIN_SUBTYPE_SCORE gating             │
│                                                                  │
│  Output: doc_family, doc_subtype, confidence, evidence          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              3. Domain Hint Inference                            │
│              (domain_validation.py)                              │
│                                                                  │
│  • Load domain packs (YAML configs)                             │
│  • Score against expectations:                                  │
│    - required_any: OR across groups                             │
│    - required_all: AND across groups (HARD GATE)                │
│    - forbidden: Negative keywords (slam to 0.0)                 │
│  • Select best matching domain                                  │
│                                                                  │
│  Output: domain, confidence, evidence, intent_bias              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   Gate Check:   │
                    │   Confidence    │
                    │   Acceptable?   │
                    └─────────────────┘
                         │         │
                    YES  │         │  NO
                         │         │
                         │         ▼
                         │  ┌──────────────────────┐
                         │  │  4. LLM Classifier   │
                         │  │  (llm_classifier.py) │
                         │  │                      │
                         │  │  GATED FALLBACK:     │
                         │  │  • doc_conf < 0.6    │
                         │  │  • domain_conf < 0.6 │
                         │  │  • subtype unknown   │
                         │  │  • lang_conf < 0.5   │
                         │  │                      │
                         │  │  Returns:            │
                         │  │  • doc_family        │
                         │  │  • doc_subtype       │
                         │  │  • domain            │
                         │  │  • confidence        │
                         │  │  • evidence          │
                         │  └──────────────────────┘
                         │         │
                         │         ▼
                         │  ┌──────────────────────┐
                         │  │  Merge Results       │
                         │  │  (confidence-based)  │
                         │  └──────────────────────┘
                         │         │
                         └─────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              5. Document Intent Resolution                       │
│              (document_intent.py)                                │
│                                                                  │
│  • Map doc_subtype → DocumentIntent                             │
│  • Apply domain bias if subtype confidence low                  │
│  • Gate domain attachment (only if domain_conf >= 0.6)          │
│  • Add evidence for unmapped subtypes                           │
│                                                                  │
│  Output: intent, confidence, source, domain, evidence           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              6. Domain Pack Validation                           │
│              (domain_validation.py)                              │
│                                                                  │
│  • Check intent-domain consistency                              │
│  • Enforce validation rules (if confidence >= 0.6)              │
│  • Generate audit trail                                         │
│                                                                  │
│  Output: validation result, checks, evidence                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              7. Rule Engine                                      │
│              (rules.py)                                          │
│                                                                  │
│  • 34+ fraud detection rules                                    │
│  • Confidence-based gating                                      │
│  • Doc-aware expectations                                       │
│  • Learned rule application                                     │
│                                                                  │
│  Output: fraud_score, events, reasons                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              8. Visual Fraud Detection (Optional)                │
│              (vision_llm.py)                                     │
│                                                                  │
│  • Spacing anomaly detection                                    │
│  • Font inconsistency detection                                 │
│  • Editing artifact detection                                   │
│  • VETO-ONLY: Can only downgrade trust                          │
│                                                                  │
│  Output: visual_integrity, confidence, observable_reasons       │
└─────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. Geo-Aware Document Profiling

**File:** `app/pipelines/geo_detection.py`

**Purpose:** Classify documents using geo-specific keyword matching and language detection.

**Key Features:**
- Language detection using fasttext
- Country/region inference with enriched geo database
- Geo-specific keyword dictionaries (24+ regions)
- Confidence-based subtype selection with MIN_SUBTYPE_SCORE gating
- Special handling for POS_RESTAURANT (0.55 base confidence for "restaurant" keyword)

**Output:**
```python
{
    "doc_family_guess": "TRANSACTIONAL",
    "doc_subtype_guess": "POS_RESTAURANT",
    "doc_subtype_confidence": 0.55,
    "doc_subtype_evidence": ["restaurant"],
    "geo_country_guess": "IN",
    "geo_confidence": 0.29,
    "lang_guess": "en",
    "lang_confidence": 0.3
}
```

### 2. Domain Pack System

**Files:** 
- `app/pipelines/domain_validation.py`
- `resources/domainpacks/*.yaml`

**Purpose:** Infer document domain (telecom, logistics, insurance, etc.) using declarative YAML configs.

**Domain Pack Structure:**
```yaml
id: telecom
name: Telecom / Mobile Services
description: Mobile bills, telecom invoices, data plans

expectations:
  required_any:  # OR across groups
    - ["customer_id", "account_id", "subscriber_id"]
    - ["phone_number", "msisdn", "sim_number", "imei"]
    - ["billing_period_start", "billing_period_end"]
  
  required_all:  # AND across groups (HARD GATE)
    - ["issue_date", "due_date", "service_date"]
    - ["merchant_name", "provider_name"]
  
  forbidden:  # Negative keywords (slam confidence to 0.0)
    - "restaurant"
    - "buffet"
    - "food"

intent_bias:
  default_intent: subscription
  confidence_multiplier: 0.8
```

**Scoring Logic:**
1. **required_any:** Score +1 for each matching group (OR logic)
2. **required_all:** HARD GATE - if any group fails, confidence = 0.0
3. **forbidden:** If any keyword present, confidence = 0.0
4. Final confidence = score / max_score (if not hard-gated)

**Key Improvements:**
- Hard-gating on `required_all` failures eliminates false positives
- Negative keywords prevent domain misclassification
- Telecom domain hardened with specific signals (reduced false positives by ~80%)

### 3. LLM Document Classifier

**Files:**
- `app/pipelines/llm_classifier.py`
- `app/config/llm_config.py`

**Purpose:** Gated fallback for low-confidence document classification using local or cloud LLMs.

**Gating Conditions (only runs when):**
- `doc_profile_confidence < 0.6` OR
- `domain_confidence < 0.6` OR
- `doc_subtype == "unknown"` OR
- `lang_confidence < 0.5` OR
- Non-English with `lang_confidence < 0.8`

**Typical trigger rate:** 15-25% of documents

**Supported Providers:**
- **Ollama (local):** `llama3.2:3b`, `llama3.1:8b`, `mistral:7b`
- **OpenAI (cloud):** `gpt-4o-mini`, `gpt-4o`

**Configuration:**
```bash
# .env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
```

**Output:**
```python
{
    "doc_family": "TRANSACTIONAL",
    "doc_subtype": "POS_RESTAURANT",
    "domain": "hospitality",
    "confidence": 0.75,
    "evidence": ["restaurant keyword", "pos format", "food items"]
}
```

**Merge Strategy:**
- If LLM confidence > existing confidence → use LLM result
- Otherwise → keep heuristic result
- Both preserved in audit trail

### 4. Document Intent Resolution

**File:** `app/pipelines/document_intent.py`

**Purpose:** Map document subtype to high-level intent (purchase, billing, transport, etc.).

**Intent Taxonomy:**
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

**Mapping Examples:**
```python
SUBTYPE_TO_INTENT = {
    "POS_RESTAURANT": DocumentIntent.PURCHASE,
    "TAX_INVOICE": DocumentIntent.BILLING,
    "INVOICE": DocumentIntent.BILLING,  # Generic fallback
    "RECEIPT": DocumentIntent.PURCHASE,  # Generic fallback
    "TELECOM": DocumentIntent.SUBSCRIPTION,
    "SHIPPING_BILL": DocumentIntent.TRANSPORT,
    "INSURANCE_CLAIM": DocumentIntent.CLAIM,
}
```

**Domain Bias (fallback when subtype confidence < 0.5):**
```python
DOMAIN_DEFAULT_INTENT = {
    "telecom": DocumentIntent.SUBSCRIPTION,
    "logistics": DocumentIntent.TRANSPORT,
    "insurance": DocumentIntent.SUBSCRIPTION,  # Premium/policy, not claim
    "healthcare": DocumentIntent.PURCHASE,
    "ecommerce": DocumentIntent.PURCHASE,
}
```

**Key Features:**
- Generic INVOICE/RECEIPT mappings reduce "unknown intent" noise
- Domain bias provides stable fallback for low-confidence subtypes
- Domain only attached when `domain_conf >= 0.6`
- Evidence includes `unmapped_subtype:<SUBTYPE>` for debugging

### 5. Visual Fraud Detection

**Files:**
- `app/pipelines/vision_llm.py` (Ollama)
- `app/pipelines/vision_llm_pytorch.py` (PyTorch)

**Purpose:** Detect visual tampering using vision models (VETO-ONLY).

**Detection Categories:**
- Spacing anomalies (excessive gaps, inconsistent spacing)
- Font inconsistencies (different fonts/sizes)
- Editing artifacts (pixelation, blurring, halos)
- Layout anomalies (misalignment, overlapping text)
- Quality issues (compression artifacts)

**Veto-Only Design:**
```
Vision is a sensor, not a judge.
It can pull the emergency brake, but never press the accelerator.
```

- ✅ `tampered` → HARD_FAIL (triggers veto in rules.py)
- ✅ `suspicious` → audit only (no veto)
- ✅ `clean` → no effect

**Models:**
- Development: `llama3.2-vision:latest` (Ollama)
- Production: `llava-1.5-7b-hf` (PyTorch)

## Configuration

### Environment Variables

```bash
# LLM Classifier
LLM_PROVIDER=ollama|openai|none
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Vision LLM
USE_OLLAMA=true|false
```

### Domain Packs

Domain packs are YAML configs in `resources/domainpacks/`:

```
domainpacks/
├── telecom.yaml
├── logistics.yaml
├── insurance.yaml
├── healthcare.yaml
└── ecommerce.yaml
```

### Language Packs

Language packs are YAML configs in `resources/langpacks/`:

```
langpacks/
├── common.yaml
├── en.yaml
├── es.yaml
├── fr.yaml
├── de.yaml
├── ja.yaml
├── ko.yaml
├── zh.yaml
└── ar.yaml
```

## Performance Characteristics

### Accuracy
- **Heuristic profiling:** 75-85% accuracy
- **With LLM fallback:** 85-95% accuracy
- **With vision veto:** 90-98% accuracy (fraud detection)

### Latency
- **Heuristic only:** 50-200ms
- **With LLM (Ollama):** 1-3 seconds (15-25% of docs)
- **With vision:** +2-5 seconds (optional)

### Cost
- **Ollama (local):** $0 (free, runs on hardware)
- **OpenAI:** ~$0.75/month for 10K documents (25% trigger rate)

## Audit Trail

Every document produces comprehensive audit events:

```json
{
  "DOC_PROFILE_DEBUG": {
    "doc_subtype_guess": "POS_RESTAURANT",
    "doc_profile_confidence": 0.55,
    "doc_profile_evidence": ["restaurant"],
    "document_intent": {
      "intent": "purchase",
      "confidence": 0.775,
      "source": "heuristic",
      "domain": null
    }
  },
  "DOMAIN_PACK_VALIDATION": {
    "domain_hint": {
      "domain": null,
      "confidence": 0.0,
      "evidence": []
    },
    "intent": {
      "intent": "purchase",
      "confidence": 0.775
    },
    "enforced": false,
    "passed": true
  },
  "llm_classification": {
    "doc_subtype": "POS_RESTAURANT",
    "confidence": 0.75,
    "evidence": ["llm_override"]
  }
}
```

## Key Design Principles

1. **Confidence-Based Gating:** Never trust low-confidence signals
2. **Veto-Only Vision:** Vision can only reject, never approve
3. **Declarative Domain Packs:** Domain logic in YAML, not code
4. **LLM as Fallback:** Only call LLM when heuristics uncertain
5. **Comprehensive Audit:** Every decision is traceable
6. **Hard-Gating:** Failed required_all → confidence = 0.0
7. **Negative Keywords:** Explicit exclusion prevents misclassification
8. **Generic Fallbacks:** INVOICE/RECEIPT mappings reduce unknown noise

## Recent Improvements (Jan 2026)

### Domain Pack Robustness
- ✅ Hard-gating on `required_all` failures
- ✅ Negative keyword enforcement (`forbidden` list)
- ✅ Telecom domain hardened (80% reduction in false positives)
- ✅ Domain only attached when confidence >= 0.6

### Restaurant Classification
- ✅ "restaurant" keyword alone reaches 0.55 confidence
- ✅ Prevents fallback override to generic INVOICE
- ✅ POS_RESTAURANT → purchase intent mapping

### Intent Resolution
- ✅ Generic INVOICE/RECEIPT mappings added
- ✅ Insurance domain default changed to SUBSCRIPTION
- ✅ Unmapped subtype evidence for debugging
- ✅ Domain bias provides stable fallback

### LLM Classifier
- ✅ Gated fallback for low-confidence cases
- ✅ Ollama local support (llama3.2:3b)
- ✅ OpenAI cloud support (gpt-4o-mini)
- ✅ Config-based provider selection
- ✅ Confidence-based merge strategy
