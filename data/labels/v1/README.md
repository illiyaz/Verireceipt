# VeriReceipt Labels V1

**Status:** Active  
**Version:** 1.0  
**Format:** JSONL (one document per line)

---

## Purpose

Human-annotated labels for ML model training and evaluation.

Each document has:
- **doc_id**: Unique hash identifier
- **annotator_judgments**: Human assessments (fraud outcome, evidence, etc.)
- **adjudication**: Final resolution when annotators disagree
- **metadata**: Provenance and tooling information

---

## File Structure

```
data/labels/v1/
├── labels.jsonl          # Main dataset (one JSON per line)
├── README.md              # This file
└── schema/               # Schema documentation
    └── label_v1.json     # JSON schema for validation
```

---

## Labeling Workflow

### Phase 1: Fast & Simple

1. **Two reviewers** assess each document
2. **Primary judgment**: `doc_outcome`, `fraud_types`, `decision_reasons`, `evidence_strength`
3. **Disagreement handling**: If outcomes differ → adjudication required

### Phase 2: Detailed (when scaling)

1. **Field-level labels**: merchant_name, total_amount, invoice_date, merchant_address
2. **Signal reviews**: Agreement/disagreement with emitted signals
3. **Evidence notes**: Detailed reasoning for decisions

---

## Label Schema

### Core Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `doc_outcome` | enum | ✅ | GENUINE, FRAUDULENT, INCONCLUSIVE |
| `fraud_types` | array | ✅* | Fraud type codes (required for FRAUDULENT) |
| `decision_reasons` | array | ✅* | Reason codes (≥2 for FRAUDULENT) |
| `evidence_strength` | enum | ✅ | NONE, WEAK, MODERATE, STRONG |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `field_labels` | object | Field-level validation (merchant, amount, date) |
| `signal_reviews` | object | Per-signal agreement reviews |
| `notes` | string | Optional annotator notes |

---

## Validation Rules

### Hard Constraints

1. **GENUINE documents**:
   - `fraud_types` must be empty
   - `evidence_strength` ∈ {NONE, WEAK}

2. **FRAUDULENT documents**:
   - `fraud_types` must be non-empty
   - `decision_reasons` must have ≥2 items
   - `evidence_strength` ∈ {MODERATE, STRONG}

3. **INCONCLUSIVE documents**:
   - `evidence_strength` ≠ NONE
   - `fraud_types` optional (allowed)

4. **Signal reviews**:
   - All signal names must be in SignalRegistry
   - Only review signals that actually emitted

### Consistency Checks

- `label_version` must be "v1"
- `doc_id` must be stable (hash-based)
- `created_at` must be valid ISO datetime
- `annotator_judgments` must have ≥1 entry

---

## Taxonomies

### Fraud Types

```python
FRAUD_TYPES = [
    "FAKE_MERCHANT",      # Non-existent business
    "AMOUNT_MANIPULATION", # Total amount altered
    "DUPLICATE_INVOICE",   # Same invoice submitted multiple times
    "TEMPLATE_FORGERY",    # Fake template/manipulated PDF
    "MULTIPLE_ADDRESS",    # Suspicious multiple addresses
    "FUTURE_DATING",       # Future dates on historical docs
    "LANGUAGE_MISMATCH",   # Language inconsistencies
    "OCR_MANIPULATION",   # Text extraction tampering
    "OTHER",              # Catch-all for other types
]
```

### Decision Reasons

```python
DECISION_REASONS = [
    "MULTIPLE_ADDRESSES_DETECTED",
    "MERCHANT_ADDRESS_MISMATCH", 
    "AMOUNT_TOTAL_MISMATCH",
    "AMOUNT_MISSING",
    "FUTURE_DATE_DETECTED",
    "TEMPLATE_QUALITY_POOR",
    "PDF_PRODUCER_SUSPICIOUS",
    "OCR_CONFIDENCE_LOW",
    "LANGUAGE_INCONSISTENT",
    "MERCHANT_EXTRACTION_WEAK",
    "EVIDENCE_INSUFFICIENT",
    "DOCUMENT_AMBIGUOUS",
    "OTHER",
]
```

---

## Example JSONL Entry

```json
{
  "label_version": "v1",
  "doc_id": "sha256:abc123...",
  "source_batch": "batch_2024_01_15",
  "created_at": "2024-01-16T10:30:00Z",
  "tool_version": "labelpack_v1.0",
  "annotator_judgments": [
    {
      "doc_outcome": "FRAUDULENT",
      "fraud_types": ["MULTIPLE_ADDRESS", "FAKE_MERCHANT"],
      "decision_reasons": [
        "MULTIPLE_ADDRESSES_DETECTED",
        "MERCHANT_ADDRESS_MISMATCH"
      ],
      "evidence_strength": "STRONG",
      "signal_reviews": {
        "addr.multi_address": {"agree": true, "comment": "Clear multiple addresses"},
        "addr.merchant_consistency": {"agree": true, "comment": "Merchant name doesn't match address"}
      },
      "notes": "Document shows clear signs of fake merchant with multiple addresses"
    },
    {
      "doc_outcome": "FRAUDULENT", 
      "fraud_types": ["MULTIPLE_ADDRESS"],
      "decision_reasons": [
        "MULTIPLE_ADDRESSES_DETECTED",
        "EVIDENCE_INSUFFICIENT"
      ],
      "evidence_strength": "MODERATE",
      "notes": "Multiple addresses but merchant could be legitimate"
    }
  ],
  "adjudication": {
    "finalized_by": "senior_reviewer",
    "final_outcome": "FRAUDULENT",
    "final_fraud_types": ["MULTIPLE_ADDRESS", "FAKE_MERCHANT"],
    "final_decision_reasons": [
      "MULTIPLE_ADDRESSES_DETECTED",
      "MERCHANT_ADDRESS_MISMATCH"
    ],
    "final_evidence_strength": "STRONG",
    "final_notes": "Confirmed fake merchant with multiple addresses"
  }
}
```

---

## Quality Guidelines

### Annotator Instructions

1. **Review signals first** - Understand what the system detected
2. **Check extracted fields** - Verify merchant, amount, date accuracy
3. **Assess evidence strength** - How confident are you in your judgment?
4. **Provide specific reasons** - Use the provided taxonomy
5. **Add notes when unclear** - Help future annotators understand edge cases

### Common Pitfalls

- **Don't ignore signals** - They provide valuable context
- **Don't use "OTHER" unless necessary** - Be specific
- **Don't skip evidence strength** - Critical for ML confidence
- **Don't forget fraud types** for fraudulent documents

---

## Tools & Scripts

### Label Pack Generator
```bash
python scripts/labelpack.py --input-folder data/pdfs/ --output labelpacks/
```

### Validation
```bash
python scripts/validate_labels.py --labels data/labels/v1/labels.jsonl
```

### Dataset Builder
```bash
python app/ml/dataset_builder.py --labels data/labels/v1/labels.jsonl --features features.jsonl
```

---

## Versioning

- **v1.0**: Initial schema with core fields
- **Future versions**: Add field-level labels, signal reviews, etc.

Backward compatibility maintained through `label_version` field.

---

## Contact

Questions about labeling? Contact the ML team.

---

**Last Updated:** 2024-01-16  
**Version:** 1.0  
**Status:** Active
