# VeriReceipt API Guide

## Quick Start

### 1. Start the API Server

```bash
# Option 1: Using the startup script
python run_api.py

# Option 2: Using uvicorn directly
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 9000
```

The API will be available at: `http://localhost:9000`

### 2. Access Interactive Documentation

- **Swagger UI**: http://localhost:9000/docs
- **ReDoc**: http://localhost:9000/redoc

---

## API Endpoints

### Health Check

**GET** `/health`

Check if the API is running.

**Response:**
```json
{
  "status": "ok",
  "service": "VeriReceipt",
  "version": "0.1.0",
  "timestamp": "2025-11-30T10:00:00.000000"
}
```

---

### Analyze Single Receipt

**POST** `/analyze`

Upload and analyze a single receipt.

**Request:**
- **Content-Type**: `multipart/form-data`
- **Body**: `file` (PDF, JPG, JPEG, or PNG)

**cURL Example:**
```bash
curl -X POST "http://localhost:9000/analyze" \
  -F "file=@data/raw/Gas_bill.jpeg"
```

**Python Example:**
```python
import requests

with open("receipt.jpg", "rb") as f:
    files = {"file": ("receipt.jpg", f, "image/jpeg")}
    response = requests.post("http://localhost:9000/analyze", files=files)
    result = response.json()
    print(f"Label: {result['label']}, Score: {result['score']}")
```

**Response:**
```json
{
  "label": "real",
  "score": 0.15,
  "reasons": [
    "Amounts detected but no clear 'Total' line found on the receipt."
  ],
  "minor_notes": [],
  "processing_time_ms": 1234.56,
  "receipt_ref": null,
  "analysis_ref": "Gas_bill.jpeg"
}
```

**Response Fields:**
- `label`: Classification result (`real`, `suspicious`, or `fake`)
- `score`: Fraud probability (0.0 = definitely real, 1.0 = definitely fake)
- `reasons`: Main reasons for the classification
- `minor_notes`: Low-severity observations
- `processing_time_ms`: Analysis duration in milliseconds

**Score Thresholds:**
- `0.0 - 0.3`: **real** - No significant fraud indicators
- `0.3 - 0.6`: **suspicious** - Some anomalies detected, manual review recommended
- `0.6 - 1.0`: **fake** - Strong fraud indicators, likely fabricated

---

### Batch Analysis

**POST** `/analyze/batch`

Analyze multiple receipts in a single request (max 50 files).

**Request:**
- **Content-Type**: `multipart/form-data`
- **Body**: Multiple `files` fields

**cURL Example:**
```bash
curl -X POST "http://localhost:9000/analyze/batch" \
  -F "files=@receipt1.jpg" \
  -F "files=@receipt2.pdf" \
  -F "files=@receipt3.png"
```

**Python Example:**
```python
import requests

files = [
    ("files", ("receipt1.jpg", open("receipt1.jpg", "rb"), "image/jpeg")),
    ("files", ("receipt2.pdf", open("receipt2.pdf", "rb"), "application/pdf")),
]

response = requests.post("http://localhost:9000/analyze/batch", files=files)
result = response.json()
print(f"Processed: {result['total_processed']} receipts in {result['total_time_ms']} ms")
```

**Response:**
```json
{
  "results": [
    {
      "label": "real",
      "score": 0.0,
      "reasons": ["No strong anomalies detected based on current rule set."],
      "minor_notes": [],
      "processing_time_ms": 1234.56,
      "receipt_ref": null,
      "analysis_ref": "receipt1.jpg"
    },
    {
      "label": "fake",
      "score": 0.85,
      "reasons": [
        "PDF producer/creator ('Canva') is commonly associated with edited documents.",
        "Sum of detected line-item amounts does not match the printed total amount."
      ],
      "minor_notes": [],
      "processing_time_ms": 1456.78,
      "receipt_ref": null,
      "analysis_ref": "receipt2.pdf"
    }
  ],
  "total_processed": 2,
  "total_time_ms": 2691.34
}
```

---

### Get Statistics

**GET** `/stats`

Get aggregate statistics about all analyzed receipts.

**cURL Example:**
```bash
curl -X GET "http://localhost:9000/stats"
```

**Response:**
```json
{
  "total_analyses": 150,
  "real_count": 120,
  "suspicious_count": 20,
  "fake_count": 10,
  "avg_score": 0.18,
  "last_updated": "2025-11-30T10:30:00.000000"
}
```

---

### Submit Feedback

**POST** `/feedback`

Submit human feedback/override for a specific analysis.

**Request Body:**
```json
{
  "receipt_ref": null,
  "analysis_ref": "receipt.jpg",
  "given_label": "fake",
  "reviewer_id": "john.doe@company.com",
  "comment": "Clearly fabricated - merchant doesn't exist",
  "reason_code": "FAKE_MERCHANT"
}
```

**Response:**
```json
{
  "feedback_ref": "feedback_123",
  "message": "Feedback recorded successfully."
}
```

**Note:** Feedback is only supported with database backend. CSV backend will return 501 Not Implemented.

---

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Unsupported file type: .txt. Allowed: .pdf, .jpg, .jpeg, .png"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Analysis failed: OCR extraction error"
}
```

### 501 Not Implemented
```json
{
  "detail": "Feedback not implemented for this backend (CSV). Switch to DB backend."
}
```

---

## Configuration

### Environment Variables

```bash
# Storage backend: "csv" (default) or "db"
export VERIRECEIPT_STORE_BACKEND=csv

# Database URL (only if using DB backend)
export VERIRECEIPT_DATABASE_URL=postgresql://user:pass@localhost:5432/verireceipt

# Upload directory (default: /tmp/verireceipt_uploads)
export VERIRECEIPT_UPLOAD_DIR=/tmp/verireceipt_uploads
```

### Using CSV Backend (Default)

```bash
# No configuration needed
python run_api.py
```

Results are logged to: `data/logs/decisions.csv`

### Using Database Backend

```bash
export VERIRECEIPT_STORE_BACKEND=db
export VERIRECEIPT_DATABASE_URL=postgresql://verireceipt:verireceipt@localhost:5432/verireceipt

# Run migrations (if using DB)
# alembic upgrade head

python run_api.py
```

---

## Testing the API

### Using the Test Client

```bash
# Make sure API is running first
python run_api.py

# In another terminal
python test_api_client.py
```

### Using cURL

```bash
# Health check
curl http://localhost:9000/health

# Analyze receipt
curl -X POST http://localhost:9000/analyze \
  -F "file=@data/raw/Gas_bill.jpeg"

# Get stats
curl http://localhost:9000/stats
```

### Using Postman

1. Import the API from: http://localhost:9000/docs
2. Or manually create requests:
   - **POST** `/analyze` with form-data file upload
   - **GET** `/health`
   - **GET** `/stats`

---

## Integration Examples

### JavaScript/Node.js

```javascript
const FormData = require('form-data');
const fs = require('fs');
const axios = require('axios');

async function analyzeReceipt(filePath) {
  const form = new FormData();
  form.append('file', fs.createReadStream(filePath));
  
  const response = await axios.post('http://localhost:9000/analyze', form, {
    headers: form.getHeaders()
  });
  
  console.log('Label:', response.data.label);
  console.log('Score:', response.data.score);
  return response.data;
}

analyzeReceipt('receipt.jpg');
```

### Python

```python
import requests

def analyze_receipt(file_path):
    with open(file_path, 'rb') as f:
        files = {'file': f}
        response = requests.post('http://localhost:9000/analyze', files=files)
        return response.json()

result = analyze_receipt('receipt.jpg')
print(f"Label: {result['label']}, Score: {result['score']}")
```

### cURL

```bash
curl -X POST "http://localhost:9000/analyze" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@receipt.jpg"
```

---

## Performance

### Typical Response Times

- **Single receipt analysis**: 1-3 seconds
  - PDF conversion: ~500ms
  - OCR processing: ~1000ms
  - Feature extraction + rules: ~200ms

- **Batch analysis (10 receipts)**: 10-30 seconds
  - Processes sequentially
  - Future: Add parallel processing

### Optimization Tips

1. **Use batch endpoint** for multiple receipts
2. **Preprocess images**: Resize large images before upload
3. **Use DB backend** for better statistics performance
4. **Enable caching**: Redis integration (coming soon)

---

## Deployment

### Docker

```bash
# Build and run with Docker Compose
docker-compose up --build

# API will be available at http://localhost:9001
```

### Production Considerations

1. **CORS**: Update `allow_origins` in `app/api/main.py` to specific domains
2. **Authentication**: Add API key middleware (not yet implemented)
3. **Rate Limiting**: Add rate limiting middleware (not yet implemented)
4. **Monitoring**: Integrate with logging/monitoring services
5. **Scaling**: Use multiple workers with Gunicorn

```bash
# Production deployment with Gunicorn
gunicorn app.api.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:9000
```

---

## Next Steps

1. **Build a web UI** to visualize results
2. **Add authentication** (API keys, OAuth)
3. **Implement rate limiting**
4. **Add webhook support** for async processing
5. **Create SDKs** for popular languages

---

## Support

For issues or questions:
- Check the main README.md
- Review API docs at `/docs`
- Check logs in `data/logs/`
