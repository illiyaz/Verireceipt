# VeriReceipt Web Demo Guide

## Overview

Beautiful, modern web interface for VeriReceipt with **drag-and-drop** receipt upload and **real-time 3-engine analysis**.

![VeriReceipt Web Demo](https://img.shields.io/badge/Status-Ready-brightgreen)

---

## Features

### ✨ **Modern UI**
- 🎨 Beautiful gradient design with Tailwind CSS
- 📱 Fully responsive (mobile, tablet, desktop)
- 🖱️ Drag-and-drop file upload
- ⚡ Real-time analysis with loading states
- 🎭 Smooth animations and transitions

### 🤖 **3-Engine Analysis**
- **Rule-Based Engine** - Fast OCR + metadata analysis
- **DONUT Transformer** - Document understanding
- **Vision LLM** - Visual fraud detection

### 📊 **Comprehensive Results**
- Hybrid verdict with confidence score
- Individual engine breakdowns
- Fraud indicators and reasoning
- Recommended actions (Approve/Reject/Review)
- Processing time for each engine

---

## Quick Start

### **Option 1: One-Command Launch** (Recommended)

```bash
python run_web_demo.py
```

This will:
1. ✅ Start FastAPI backend (port 8000)
2. ✅ Start Web UI server (port 3000)
3. ✅ Open browser automatically

**That's it!** 🎉

---

### **Option 2: Manual Launch**

**Terminal 1 - Start API:**
```bash
python -m uvicorn app.api.main:app --reload --port 8000
```

**Terminal 2 - Start Web UI:**
```bash
cd web
python -m http.server 3000
```

**Open browser:**
```
http://localhost:3000
```

---

## Usage

### **Step 1: Upload Receipt**

Drag and drop a receipt image or PDF, or click to browse:

```
Supported formats:
- JPG/JPEG
- PNG
- PDF
```

### **Step 2: Analyze**

Click **"Analyze Receipt"** button. The system will:

1. Run all 3 engines in parallel (~10-15 seconds)
2. Show real-time progress
3. Display comprehensive results

### **Step 3: Review Results**

**Hybrid Verdict:**
- Final classification (Real/Fake/Suspicious)
- Confidence percentage
- Recommended action
- Reasoning from all engines

**Individual Engine Results:**
- Rule-Based: Label, score, key findings
- DONUT: Merchant, total, data quality
- Vision LLM: Verdict, confidence, fraud indicators

### **Step 4: Take Action**

Based on the hybrid verdict:
- ✅ **Real** → Approve receipt
- ❌ **Fake** → Reject receipt
- ⚠️ **Suspicious** → Send for human review

---

## Architecture

```
┌─────────────────────────────────────────────┐
│         Web UI (React + Tailwind)          │
│         http://localhost:3000               │
└─────────────────┬───────────────────────────┘
                  │ HTTP POST /analyze/hybrid
                  ↓
┌─────────────────────────────────────────────┐
│       FastAPI Backend (Python)              │
│       http://localhost:8000                 │
└─────────────────┬───────────────────────────┘
                  │
        ┌─────────┴─────────┐
        ↓         ↓         ↓
   ┌────────┐ ┌──────┐ ┌────────┐
   │ Rule-  │ │DONUT │ │Vision  │
   │ Based  │ │      │ │  LLM   │
   └────────┘ └──────┘ └────────┘
   (Parallel Processing)
```

---

## API Endpoint

### **POST /analyze/hybrid**

Analyzes receipt with all 3 engines in parallel.

**Request:**
```bash
curl -X POST "http://localhost:8000/analyze/hybrid" \
  -F "file=@receipt.jpg"
```

**Response:**
```json
{
  "rule_based": {
    "label": "real",
    "score": 0.0,
    "reasons": ["No strong anomalies detected"],
    "time_seconds": 2.34
  },
  "donut": {
    "merchant": "Shell Gas Station",
    "total": 45.67,
    "line_items_count": 3,
    "data_quality": "good",
    "time_seconds": 8.45
  },
  "vision_llm": {
    "verdict": "real",
    "confidence": 0.90,
    "authenticity_score": 0.89,
    "fraud_indicators": [],
    "time_seconds": 12.45
  },
  "hybrid_verdict": {
    "final_label": "real",
    "confidence": 0.95,
    "recommended_action": "approve",
    "reasoning": [
      "Both engines strongly indicate authentic receipt"
    ]
  },
  "timing": {
    "parallel_total_seconds": 12.67
  },
  "engines_used": ["rule-based", "donut", "vision-llm"]
}
```

---

## Screenshots

### **Upload Screen**
```
┌─────────────────────────────────────────────┐
│  VeriReceipt - AI Receipt Fraud Detection  │
├─────────────────────────────────────────────┤
│                                             │
│   ┌───────────────────────────────────┐   │
│   │   📤                              │   │
│   │   Drag & drop your receipt here   │   │
│   │   or click to browse              │   │
│   │                                   │   │
│   │   Supports: JPG, PNG, PDF         │   │
│   └───────────────────────────────────┘   │
│                                             │
│   [Analyze Receipt]  [Clear]               │
│                                             │
└─────────────────────────────────────────────┘
```

### **Results Screen**
```
┌─────────────────────────────────────────────┐
│  Analysis Results                           │
├─────────────────────────────────────────────┤
│                                             │
│  Hybrid Verdict:                            │
│  ┌─────────────────────────────────────┐   │
│  │  REAL                               │   │
│  │  Confidence: 95.0%                  │   │
│  │  Action: Approve                    │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ Rule-    │ │ DONUT    │ │ Vision   │   │
│  │ Based    │ │          │ │ LLM      │   │
│  │          │ │          │ │          │   │
│  │ Label:   │ │ Merchant:│ │ Verdict: │   │
│  │ real     │ │ Shell    │ │ real     │   │
│  │ Score:   │ │ Total:   │ │ Conf:    │   │
│  │ 0.000    │ │ $45.67   │ │ 90%      │   │
│  └──────────┘ └──────────┘ └──────────┘   │
│                                             │
└─────────────────────────────────────────────┘
```

---

## Customization

### **Change API URL**

Edit `web/index.html`:

```javascript
const API_BASE_URL = 'http://your-server:8000';
```

### **Change Colors**

The UI uses Tailwind CSS. Modify classes in `web/index.html`:

```html
<!-- Change gradient -->
<div class="gradient-bg">  <!-- Edit this class in <style> -->

<!-- Change badge colors -->
<div class="badge-real">   <!-- Green gradient -->
<div class="badge-fake">   <!-- Red gradient -->
```

### **Add More Engines**

1. Add engine to backend (`app/api/main.py`)
2. Update `HybridAnalyzeResponse` model
3. Add engine card to `ResultsView` component

---

## Troubleshooting

### **"Failed to analyze receipt"**

**Problem:** API server not running

**Solution:**
```bash
# Check if API is running
curl http://localhost:8000/health

# If not, start it
python -m uvicorn app.api.main:app --port 8000
```

### **"DONUT not available"**

**Problem:** DONUT dependencies not installed

**Solution:**
```bash
pip install transformers torch pillow sentencepiece
```

### **"Vision LLM not available"**

**Problem:** Ollama not running or model not downloaded

**Solution:**
```bash
# Start Ollama
ollama serve

# Pull vision model
ollama pull llama3.2-vision:latest
```

### **CORS Errors**

**Problem:** Browser blocking requests

**Solution:** API already has CORS enabled. If still issues:

```python
# In app/api/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Specify exact origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Performance

### **Analysis Speed**

| Scenario | Time | Engines Used |
|----------|------|--------------|
| Fast path (clearly real) | 2-5s | Rule-based only |
| Suspicious case | 10-15s | All 3 (parallel) |
| High-stakes | 10-15s | All 3 (parallel) |

**Average:** ~12 seconds for complete 3-engine analysis

### **Optimization Tips**

1. **Use parallel processing** (already enabled)
2. **Cache DONUT model** (loads once, reuses)
3. **Warm up Ollama** (first query is slower)
4. **Use smaller vision models** for faster results

---

## Deployment

### **Production Deployment**

1. **Build static assets** (optional - already using CDN)
2. **Deploy FastAPI** with Gunicorn:
   ```bash
   gunicorn app.api.main:app -w 4 -k uvicorn.workers.UvicornWorker
   ```
3. **Serve web UI** with Nginx or Caddy
4. **Use HTTPS** for security
5. **Set proper CORS origins**

### **Docker Deployment**

```dockerfile
FROM python:3.11

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt
RUN pip install transformers torch pillow sentencepiece

EXPOSE 8000 3000

CMD ["python", "run_web_demo.py"]
```

---

## Next Steps

### **Enhancements**

1. **User Authentication** - Add login/signup
2. **History** - Store analysis results
3. **Batch Upload** - Analyze multiple receipts
4. **Export Results** - Download as PDF/CSV
5. **Feedback Loop** - Allow users to correct verdicts
6. **Dashboard** - Analytics and statistics
7. **Mobile App** - Native iOS/Android apps

### **Advanced Features**

1. **Real-time Analysis** - WebSocket streaming
2. **Confidence Threshold** - Adjust sensitivity
3. **Custom Rules** - Add domain-specific rules
4. **Model Selection** - Choose which engines to use
5. **A/B Testing** - Compare different models

---

## Summary

✅ **You now have:**
- Beautiful drag-and-drop web UI
- 3-engine parallel analysis
- Real-time results with explanations
- One-command launch script
- Production-ready architecture

✅ **Run it now:**
```bash
python run_web_demo.py
```

✅ **Then:**
1. Drag and drop a receipt
2. Click "Analyze Receipt"
3. See all 3 engines work together!

**Your complete fraud detection system is ready! 🚀**
