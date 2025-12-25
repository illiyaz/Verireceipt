# VeriReceipt API Documentation

## Base URL
```
http://localhost:8000
```

## Interactive API Docs
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## Endpoints

### 1. Health Check

#### `GET /health`

Check if the API server is running.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

---

### 2. Simple Analysis

#### `POST /analyze`

Analyze a single receipt using the rule-based engine.

**Request:**
- **Content-Type**: `multipart/form-data`
- **Body**: 
  - `file`: Receipt image or PDF (JPEG, PNG, PDF)

**Response:**
```json
{
  "label": "fake",
  "score": 0.75,
  "reasons": [
    "[HARD_FAIL] 🚨 Suspicious Software Detected: 'Canva' - This software is commonly used to create fake receipts.",
    "[CRITICAL] 💵🌍 Currency–Geography Consistency Issue: The document's currency does not match the implied region."
  ],
  "minor_notes": [
    "Document is missing a creation date in its metadata.",
    "Rule severity summary: hard_fail=True, critical=True"
  ],
  "processing_time_ms": 1234.56,
  "receipt_ref": null,
  "analysis_ref": "analysis_20241225_123456"
}
```

**Status Codes:**
- `200 OK`: Analysis successful
- `400 Bad Request`: Invalid file type
- `500 Internal Server Error`: Processing error

---

### 3. Batch Analysis

#### `POST /analyze/batch`

Analyze multiple receipts in parallel.

**Request:**
- **Content-Type**: `multipart/form-data`
- **Body**: 
  - `files`: Multiple receipt files (up to 10)

**Response:**
```json
{
  "results": [
    {
      "filename": "receipt1.jpg",
      "label": "real",
      "score": 0.15,
      "reasons": ["No strong anomalies detected based on current rule set."],
      "processing_time_ms": 987.65
    },
    {
      "filename": "receipt2.pdf",
      "label": "fake",
      "score": 0.85,
      "reasons": ["[CRITICAL] Currency mismatch detected"],
      "processing_time_ms": 1543.21
    }
  ],
  "total_processing_time_ms": 2530.86,
  "successful": 2,
  "failed": 0
}
```

---

### 4. Hybrid Multi-Engine Analysis

#### `POST /analyze/hybrid`

Analyze receipt using all available engines (Rule-Based, Vision LLM, DONUT, LayoutLM) and return ensemble verdict.

**Request:**
- **Content-Type**: `multipart/form-data`
- **Body**: 
  - `file`: Receipt image or PDF
- **Query Parameters** (optional):
  - `vision_model`: Vision model to use (default: `gpt-4o-mini`)
    - Options: `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`

**Response:**
```json
{
  "ensemble_verdict": {
    "final_label": "fake",
    "confidence": 0.93,
    "recommended_action": "reject",
    "reasoning": [
      "🚨 HARD FAIL: Structural inconsistencies detected",
      "   • [HARD_FAIL] Currency mismatch: USD with lakhs",
      "ℹ️ Note: Visual realism cannot override structural inconsistencies."
    ],
    "agreement_score": 0.67
  },
  "individual_results": {
    "rule_based": {
      "label": "fake",
      "score": 0.85,
      "reasons": ["[CRITICAL] Currency–Geography Consistency Issue"],
      "timing_ms": 1234.56
    },
    "vision_llm": {
      "verdict": "real",
      "confidence": 0.75,
      "reasoning": "Receipt appears visually authentic with proper formatting",
      "timing_ms": 3456.78
    },
    "donut": {
      "merchant": "Walmart",
      "total": "45.67",
      "date": "2024-08-15",
      "confidence": 0.89,
      "timing_ms": 2345.67
    },
    "layoutlm": {
      "merchant": "Walmart Supercenter",
      "total": "45.67",
      "date": "2024-08-15",
      "timing_ms": 1987.65
    }
  },
  "converged_data": {
    "merchant": "Walmart Supercenter",
    "total": "45.67",
    "date": "2024-08-15",
    "items": []
  },
  "total_processing_time_ms": 9024.66
}
```

---

### 5. Streaming Analysis (Server-Sent Events)

#### `POST /analyze/stream`

Analyze receipt with real-time progress updates via Server-Sent Events.

**Request:**
- **Content-Type**: `multipart/form-data`
- **Body**: 
  - `file`: Receipt image or PDF

**Response Stream (SSE):**
```
event: progress
data: {"event": "start", "message": "Analysis started"}

event: progress
data: {"event": "engine_start", "engine": "rule-based"}

event: progress
data: {"event": "engine_complete", "engine": "rule-based", "result": {...}}

event: progress
data: {"event": "engine_start", "engine": "vision-llm"}

event: progress
data: {"event": "engine_complete", "engine": "vision-llm", "result": {...}}

event: result
data: {"ensemble_verdict": {...}, "individual_results": {...}}

event: complete
data: {"message": "Analysis complete"}
```

**Client Example (JavaScript):**
```javascript
const eventSource = new EventSource('/analyze/stream');

eventSource.addEventListener('progress', (e) => {
  const data = JSON.parse(e.data);
  console.log('Progress:', data);
});

eventSource.addEventListener('result', (e) => {
  const data = JSON.parse(e.data);
  console.log('Final Result:', data);
});

eventSource.addEventListener('complete', (e) => {
  eventSource.close();
});
```

---

## Feedback Endpoints

### 6. Submit Feedback

#### `POST /feedback/submit`

Submit detailed feedback for a receipt analysis to improve the learning engine.

**Request:**
```json
{
  "receipt_id": "receipt_20241225_123456",
  "user_label": "real",
  "confidence": 5,
  "indicator_reviews": [
    {
      "indicator": "Suspicious Software Detected",
      "user_verdict": "incorrect",
      "explanation": "This is a legitimate receipt from a business that uses Canva for branding"
    },
    {
      "indicator": "Currency mismatch",
      "user_verdict": "correct",
      "explanation": "This is indeed suspicious"
    }
  ],
  "missed_indicators": [
    {
      "indicator_type": "duplicate_line_items",
      "description": "Line item 'Coffee' appears twice with same price",
      "severity": "medium"
    }
  ],
  "data_corrections": {
    "merchant": "Starbucks Coffee",
    "total": "15.67",
    "date": "2024-08-15"
  },
  "comments": "The software detection rule needs refinement for legitimate businesses"
}
```

**Response:**
```json
{
  "status": "success",
  "feedback_id": "fb_20241225_123456",
  "message": "Feedback recorded successfully",
  "learning_triggered": true
}
```

---

### 7. Feedback Statistics

#### `GET /feedback/stats`

Get feedback statistics and learning engine status.

**Response:**
```json
{
  "total_feedback": 150,
  "by_label": {
    "real": 80,
    "fake": 60,
    "suspicious": 10
  },
  "avg_confidence": 4.2,
  "learned_rules_count": 12,
  "last_training": "2024-12-25T10:30:00Z",
  "false_positive_rate": 0.15,
  "false_negative_rate": 0.08
}
```

---

### 8. Trigger Retraining

#### `POST /feedback/retrain`

Manually trigger the learning engine to update rules based on feedback.

**Response:**
```json
{
  "status": "success",
  "rules_updated": 5,
  "rules_added": 2,
  "rules_removed": 1,
  "training_time_ms": 3456.78
}
```

---

## Data Models

### ReceiptDecision

```python
{
  "label": str,              # "real", "fake", "suspicious"
  "score": float,            # 0.0 - 1.0
  "reasons": List[str],      # Tagged reasons: [SEVERITY] message
  "features": Optional[ReceiptFeatures],
  "minor_notes": Optional[List[str]],
  "rule_version": str,       # Ruleset version (e.g., "1.0.0")
  "engine_version": str,     # App version (e.g., "0.3.0")
  "debug": Optional[Dict]    # Geo/currency/tax metadata
}
```

### Severity Tags

Reasons are tagged with severity levels:

- **[HARD_FAIL]**: Structural inconsistencies that strongly indicate fraud
  - Example: Impossible date sequence, currency mismatch
  - Ensemble behavior: Forces "fake" verdict (0.93 confidence)

- **[CRITICAL]**: Strong fraud indicators requiring review
  - Example: Suspicious software, tax regime mismatch
  - Ensemble behavior: High weight in decision (0.85 confidence)

- **[INFO]**: Normal explanatory reasons
  - Example: Missing creation date, low text quality
  - Ensemble behavior: Informational only

---

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Unsupported file type: .txt. Allowed: .jpg, .jpeg, .png, .pdf"
}
```

### 500 Internal Server Error
```json
{
  "detail": "OCR processing failed: <error details>"
}
```

---

## Rate Limits

Currently no rate limits enforced. For production deployment, consider:
- 100 requests/minute per IP
- 1000 requests/hour per API key

---

## Authentication

Currently no authentication required. For production:
- Implement API key authentication
- Use JWT tokens for user sessions
- Add role-based access control (RBAC)

---

## Best Practices

### 1. File Upload
- **Max file size**: 10 MB
- **Supported formats**: JPEG, PNG, PDF
- **Recommended resolution**: 1200+ pixels for best OCR accuracy

### 2. Batch Processing
- **Max files per batch**: 10
- **Timeout**: 60 seconds per file
- Use `/analyze/stream` for real-time progress

### 3. Feedback Loop
- Submit feedback for all decisions (especially incorrect ones)
- Provide detailed explanations for indicator reviews
- Include data corrections when extraction is wrong
- Use confidence ratings honestly (1-5 scale)

### 4. Error Handling
```javascript
try {
  const response = await fetch('/analyze', {
    method: 'POST',
    body: formData
  });
  
  if (!response.ok) {
    const error = await response.json();
    console.error('Analysis failed:', error.detail);
  }
  
  const result = await response.json();
  // Process result
} catch (error) {
  console.error('Network error:', error);
}
```

---

## WebSocket Support (Future)

Planned for v2.0:
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/analyze');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Real-time update:', data);
};

ws.send(JSON.stringify({
  action: 'analyze',
  file_base64: '...'
}));
```

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and updates.

---

## Support

- **GitHub Issues**: https://github.com/illiyaz/Verireceipt/issues
- **Documentation**: https://github.com/illiyaz/Verireceipt/wiki
- **Email**: support@verireceipt.com (if available)

---

**Last Updated:** December 25, 2024  
**API Version:** 1.0.0  
**Engine Version:** 0.3.0+geo
