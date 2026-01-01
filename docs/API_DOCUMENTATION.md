# VeriReceipt API Documentation

## Overview

VeriReceipt provides REST API endpoints for receipt verification using a multi-engine approach with vision veto-only design.

---

## Base URL

```
http://localhost:8000
```

---

## Endpoints

### 1. Analyze Receipt (Hybrid)

**Endpoint:** `POST /analyze/hybrid`

**Description:** Analyzes a receipt using all available engines (Rule-Based, DONUT, Donut-Receipt, LayoutLM, Vision LLM) and returns a comprehensive verdict.

**Request:**
```http
POST /analyze/hybrid
Content-Type: multipart/form-data

file: <receipt_image_or_pdf>
```

**Supported Formats:**
- Images: JPG, JPEG, PNG, WEBP, BMP
- Documents: PDF (auto-converted to images)

**Response:**
```json
{
  "label": "real" | "fake" | "suspicious",
  "score": 0.85,
  "reasons": [
    "[INFO] Missing-field penalties disabled: geo/doc profile confidence too low",
    "[CRITICAL] Document Type Ambiguity: Contains mixed/unclear invoice/receipt language"
  ],
  "minor_notes": [],
  "rule_version": "0.0.1",
  "policy_version": "0.0.1",
  "engine_version": "ensemble-v0.0.1",
  "policy_name": "ensemble",
  
  "visual_integrity": "clean" | "suspicious" | "tampered",
  "vision_confidence": 0.90,
  
  "layoutlm_status": "good" | "bad" | "error" | "unknown",
  "layoutlm_confidence": "low" | "medium" | "high",
  "layoutlm_extracted": {
    "merchant": "Acme Store",
    "total": "45.99",
    "date": "2024-01-15"
  },
  
  "corroboration_score": 0.75,
  "corroboration_signals": {
    "agreement_score": 0.8,
    "critical_count": 0,
    "visual_integrity": "clean",
    "rule_label": "real",
    "rule_score": 0.85,
    "layoutlm_has_total": true
  },
  "corroboration_flags": [],
  
  "extraction_confidence_score": 0.82,
  "extraction_confidence_level": "high",
  
  "audit_events": [
    {
      "source": "rules",
      "type": "rule_trigger",
      "code": "V1_VISION_TAMPERED",
      "severity": "HARD_FAIL",
      "message": "Vision detected clear tampering",
      "evidence": {
        "visual_integrity": "tampered",
        "confidence": 0.92,
        "observable_reasons": [
          "Clear editing artifacts around total amount"
        ]
      }
    }
  ],
  
  "debug": {
    "visual_integrity": "clean",
    "confidence": 0.90,
    "observable_reasons": []
  }
}
```

---

### 2. Analyze Receipt (Streaming)

**Endpoint:** `POST /analyze/hybrid/stream`

**Description:** Same as `/analyze/hybrid` but streams results as each engine completes using Server-Sent Events (SSE).

**Request:**
```http
POST /analyze/hybrid/stream
Content-Type: multipart/form-data

file: <receipt_image_or_pdf>
```

**Response:** Server-Sent Events (text/event-stream)

**Event Types:**

1. **analysis_start**
```
event: analysis_start
data: {"message": "Starting 5-engine analysis"}
```

2. **engine_start**
```
event: engine_start
data: {"event": "engine_start", "engine": "rule-based"}
```

3. **engine_complete**
```
event: engine_complete
data: {
  "event": "engine_complete",
  "engine": "vision-llm",
  "data": {
    "visual_integrity": "clean",
    "confidence": 0.90,
    "observable_reasons": [],
    "time_seconds": 2.34
  }
}
```

4. **analysis_complete**
```
event: analysis_complete
data: {
  "rule_based": {...},
  "donut": {...},
  "donut_receipt": {...},
  "layoutlm": {...},
  "vision_llm": {
    "visual_integrity": "clean",
    "confidence": 0.90,
    "observable_reasons": []
  },
  "hybrid_verdict": {
    "final_label": "real",
    "confidence": 0.85,
    "recommended_action": "approve",
    "reasoning": ["Rule-based engine indicates authentic receipt"]
  },
  "timing": {
    "parallel_total_seconds": 3.45
  },
  "engines_used": ["rule-based", "donut", "layoutlm", "vision-llm"]
}
```

---

## Response Fields

### Core Decision Fields

| Field | Type | Description |
|-------|------|-------------|
| `label` | string | Final decision: "real", "fake", or "suspicious" |
| `score` | float | Confidence score (0.0-1.0) |
| `reasons` | array | List of reasons for the decision |
| `minor_notes` | array | Non-critical observations |

### Vision Fields (Veto-Only)

| Field | Type | Description |
|-------|------|-------------|
| `visual_integrity` | string | "clean", "suspicious", or "tampered" |
| `vision_confidence` | float | Vision model confidence (0.0-1.0) |

**Important:** Vision is veto-only:
- `"clean"` → No effect on decision
- `"suspicious"` → Audit only, no effect on decision
- `"tampered"` → HARD_FAIL, receipt rejected

### Layout Extraction Fields

| Field | Type | Description |
|-------|------|-------------|
| `layoutlm_status` | string | "good", "bad", "error", or "unknown" |
| `layoutlm_confidence` | string | "low", "medium", or "high" |
| `layoutlm_extracted` | object | Extracted fields (merchant, total, date) |

### Corroboration Fields

| Field | Type | Description |
|-------|------|-------------|
| `corroboration_score` | float | Cross-engine agreement (0.0-1.0) |
| `corroboration_signals` | object | Evidence for corroboration score |
| `corroboration_flags` | array | Specific corroboration issues |

**Note:** Vision is NOT part of corroboration. Only rules + extraction quality.

### Audit Fields

| Field | Type | Description |
|-------|------|-------------|
| `audit_events` | array | Structured audit trail |
| `debug` | object | Debug information including vision evidence |

---

## Vision Veto-Only Design

### Key Principles

1. **Vision cannot approve receipts**
   - Vision cannot say "real" or "fake"
   - Vision can only say "clean", "suspicious", or "tampered"

2. **Vision can only veto (reject)**
   - Only `visual_integrity: "tampered"` affects decisions
   - Triggers `V1_VISION_TAMPERED` HARD_FAIL event
   - Receipt is rejected regardless of rule-based score

3. **Vision does not participate in blending**
   - No weighted averaging with rule-based scores
   - No corroboration influence
   - Audit-only for "clean" and "suspicious"

### Vision Response Interpretation

```python
# Clean - No effect
{
  "visual_integrity": "clean",
  "vision_confidence": 0.90
}
# → Rules decide normally

# Suspicious - Audit only
{
  "visual_integrity": "suspicious",
  "vision_confidence": 0.65
}
# → Rules decide normally, stored for investigation

# Tampered - HARD_FAIL veto
{
  "visual_integrity": "tampered",
  "vision_confidence": 0.92
}
# → Receipt rejected (label: "fake")
# → V1_VISION_TAMPERED event in audit_events
```

---

## Error Responses

### 400 Bad Request
```json
{
  "detail": "No file uploaded"
}
```

### 415 Unsupported Media Type
```json
{
  "detail": "Unsupported file type. Supported: jpg, jpeg, png, pdf, webp, bmp"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Analysis failed: <error_message>"
}
```

---

## Example Usage

### Python

```python
import requests

# Analyze receipt
with open("receipt.jpg", "rb") as f:
    response = requests.post(
        "http://localhost:8000/analyze/hybrid",
        files={"file": f}
    )

result = response.json()
print(f"Label: {result['label']}")
print(f"Score: {result['score']}")
print(f"Visual Integrity: {result['visual_integrity']}")

# Check for vision veto
if result['visual_integrity'] == 'tampered':
    print("⚠️ Vision detected tampering - receipt rejected")
```

### cURL

```bash
curl -X POST "http://localhost:8000/analyze/hybrid" \
  -F "file=@receipt.jpg"
```

### JavaScript (Streaming)

```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);

const eventSource = new EventSource('/analyze/hybrid/stream');

eventSource.addEventListener('engine_complete', (event) => {
  const data = JSON.parse(event.data);
  console.log(`${data.engine} completed:`, data.data);
});

eventSource.addEventListener('analysis_complete', (event) => {
  const results = JSON.parse(event.data);
  console.log('Final verdict:', results.hybrid_verdict);
  eventSource.close();
});

fetch('/analyze/hybrid/stream', {
  method: 'POST',
  body: formData
});
```

---

## Audit Trail

### Vision Tampering Event

When vision detects tampering, a structured event is emitted:

```json
{
  "source": "rules",
  "type": "rule_trigger",
  "code": "V1_VISION_TAMPERED",
  "severity": "HARD_FAIL",
  "message": "Vision detected clear tampering",
  "evidence": {
    "visual_integrity": "tampered",
    "confidence": 0.92,
    "observable_reasons": [
      "Clear editing artifacts around total amount",
      "Font inconsistency between merchant name and total",
      "Digital manipulation signatures detected"
    ]
  }
}
```

### Debug Information

Vision assessment is always stored in debug for audit:

```json
{
  "debug": {
    "visual_integrity": "suspicious",
    "confidence": 0.65,
    "observable_reasons": [
      "Unusual spacing patterns",
      "Low-resolution merchant logo"
    ]
  }
}
```

---

## Migration from Old API

### Deprecated Fields (Removed)

| Old Field | New Field | Notes |
|-----------|-----------|-------|
| `vision_verdict` | `visual_integrity` | Changed from "real"/"fake" to "clean"/"suspicious"/"tampered" |
| `vision_reasoning` | N/A | Not exposed in response (use audit trail) |
| `authenticity_assessment` | N/A | Internal structure only |
| `authenticity_score` | N/A | No blending weights |

### Breaking Changes

1. **`vision_verdict` removed**
   - Replace with `visual_integrity`
   - Update logic to handle "clean"/"suspicious"/"tampered"

2. **`vision_reasoning` removed**
   - Use `debug.observable_reasons` for investigation
   - Check `audit_events` for structured evidence

3. **Vision no longer in corroboration**
   - `corroboration_signals` no longer includes vision fields
   - `corroboration_flags` no longer has VISION_* flags

---

## Rate Limiting

Currently no rate limiting implemented. Recommended limits:
- 100 requests per minute per IP
- 1000 requests per hour per IP

---

## Performance

Typical response times (parallel execution):
- Rule-Based: ~0.5-1.0s
- DONUT: ~1.0-2.0s
- Donut-Receipt: ~1.0-2.0s
- LayoutLM: ~1.5-3.0s
- Vision LLM: ~2.0-4.0s

**Total (parallel):** ~3-5 seconds

---

## References

- **Design Document:** `docs/VISION_VETO_DESIGN.md`
- **Testing Guide:** `REAL_RECEIPT_TESTING_GUIDE.md`
- **Schema Definition:** `app/schemas/receipt.py`

---

**Last Updated:** January 1, 2026  
**API Version:** v1.0
