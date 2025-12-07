# Production Deployment Guide

## Overview
VeriReceipt can be deployed in multiple configurations depending on your requirements.

## Deployment Options

### Option 1: Cloud Deployment (Recommended for MVP)
**Best for:** Quick deployment, testing, scalability

**Requirements:**
- Server with 4GB+ RAM
- Internet access
- OpenAI API key

**Pros:**
- ✅ Easy setup
- ✅ Best accuracy (5 engines)
- ✅ No GPU needed
- ✅ Auto-scaling possible

**Cons:**
- ❌ Requires internet
- ❌ API costs (~$0.01-0.03/receipt)
- ❌ Not air-gapped

**Setup:**
```bash
# 1. Set environment variables
export OPENAI_API_KEY="your-key-here"

# 2. Install dependencies
pip install -r requirements.txt

# 3. Pre-download models (one-time, with internet)
python scripts/download_models.py

# 4. Run server
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

---

### Option 2: Air-Gapped Deployment
**Best for:** Security-critical environments, compliance

**Requirements:**
- Server with 8GB+ RAM
- GPU recommended (for local vision model)
- No internet after initial setup

**Pros:**
- ✅ Fully offline
- ✅ No API costs
- ✅ Compliant with air-gap requirements
- ✅ Data never leaves premises

**Cons:**
- ❌ More complex setup
- ❌ Requires GPU for best results
- ❌ Manual model updates

**Setup:**

**Step 1: Prepare Models (On Internet-Connected Machine)**
```bash
# Download all models
python scripts/download_models.py

# Package model cache
tar -czf verireceipt-models.tar.gz ~/.cache/huggingface/
```

**Step 2: Transfer to Air-Gapped Server**
```bash
# Copy models
scp verireceipt-models.tar.gz server:/tmp/

# On server
tar -xzf /tmp/verireceipt-models.tar.gz -C ~/
```

**Step 3: Configure for Offline Mode**
```bash
# Disable Vision LLM (or use local model)
export VISION_LLM_ENABLED=false

# Or use local vision model
export VISION_LLM_TYPE=local
export VISION_LLM_MODEL=llava-v1.6-vicuna-7b
```

**Step 4: Run**
```bash
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

---

### Option 3: Hybrid Deployment
**Best for:** Flexibility, gradual migration

**Configuration:**
- 4 engines always offline
- Vision LLM optional/fallback
- System works with or without internet

**Setup:**
```bash
# Vision LLM auto-disabled if no API key
# System continues with 4 engines
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

---

## Model Pre-Download Script

Create `scripts/download_models.py`:
```python
#!/usr/bin/env python3
"""
Pre-download all AI models for offline deployment.
Run once with internet access.
"""

print("Downloading VeriReceipt AI models...")
print("This may take 10-15 minutes and requires ~5GB storage.\n")

# 1. DONUT
print("1/4 Downloading DONUT model...")
from app.pipelines.donut_extractor import get_donut_extractor
get_donut_extractor()
print("✅ DONUT downloaded\n")

# 2. Donut-Receipt
print("2/4 Downloading Donut-Receipt model...")
from app.models.donut_receipt import DonutReceiptExtractor
DonutReceiptExtractor()
print("✅ Donut-Receipt downloaded\n")

# 3. LayoutLM
print("3/4 Downloading LayoutLM model...")
from app.models.layoutlm import LayoutLMExtractor
LayoutLMExtractor()
print("✅ LayoutLM downloaded\n")

# 4. Vision LLM (optional)
print("4/4 Checking Vision LLM...")
try:
    from app.pipelines.vision_llm import analyze_receipt_with_vision
    print("✅ Vision LLM configured (requires API key at runtime)\n")
except:
    print("⚠️  Vision LLM not available (optional)\n")

print("=" * 60)
print("✅ All models downloaded successfully!")
print(f"Models cached in: ~/.cache/huggingface/hub/")
print("=" * 60)
```

---

## Environment Variables

### Required
```bash
# None - system works with defaults
```

### Optional
```bash
# OpenAI API Key (for Vision LLM)
OPENAI_API_KEY=sk-...

# Disable Vision LLM
VISION_LLM_ENABLED=false

# Upload directory
UPLOAD_DIR=/tmp/verireceipt_uploads

# Model cache directory
HF_HOME=~/.cache/huggingface
```

---

## Docker Deployment

### Dockerfile
```dockerfile
FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Pre-download models (optional - can be done at runtime)
# RUN python scripts/download_models.py

# Expose port
EXPOSE 8000

# Run server
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose
```yaml
version: '3.8'

services:
  verireceipt:
    build: .
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./data:/app/data
      - model-cache:/root/.cache/huggingface
    restart: unless-stopped

volumes:
  model-cache:
```

---

## Security Considerations

### API Key Management
```bash
# Never commit API keys to git
# Use environment variables or secrets manager

# Development
export OPENAI_API_KEY="sk-..."

# Production (AWS)
aws secretsmanager get-secret-value --secret-id verireceipt/openai-key

# Production (K8s)
kubectl create secret generic verireceipt-secrets \
  --from-literal=openai-api-key=sk-...
```

### File Upload Security
- Validate file types
- Scan for malware
- Limit file sizes
- Isolate upload directory
- Clean up old files

---

## Performance Tuning

### CPU-Only Server
```bash
# Disable GPU (if no GPU available)
export CUDA_VISIBLE_DEVICES=""

# Expected performance:
# - Rule-Based: ~1-2s
# - DONUT: ~5-10s
# - Donut-Receipt: ~3-5s
# - LayoutLM: ~1-2s
# - Vision LLM: ~10-15s (API)
# Total: ~20-35s per receipt
```

### GPU Server
```bash
# Use GPU for faster inference
export CUDA_VISIBLE_DEVICES=0

# Expected performance:
# - Rule-Based: ~1s
# - DONUT: ~2-3s
# - Donut-Receipt: ~1-2s
# - LayoutLM: ~0.5s
# - Vision LLM: ~10-15s (API)
# Total: ~15-20s per receipt
```

---

## Monitoring

### Health Check Endpoint
```bash
curl http://localhost:8000/health
```

### Metrics to Monitor
- Request latency
- Engine success rates
- API costs (Vision LLM)
- Disk usage (uploads)
- Memory usage
- Model load times

---

## Testing Before Production

### 1. Functional Testing
```bash
# Test all engines
python -m pytest tests/

# Test with sample receipts
python scripts/test_receipts.py
```

### 2. Load Testing
```bash
# Install locust
pip install locust

# Run load test
locust -f tests/load_test.py
```

### 3. Accuracy Testing
- Test with 20-50 real receipts
- Mix of real and fake receipts
- Collect feedback
- Measure accuracy

---

## Deployment Checklist

### Pre-Deployment
- [ ] All models downloaded
- [ ] Environment variables configured
- [ ] API keys secured
- [ ] Upload directory configured
- [ ] Tests passing
- [ ] Load testing completed

### Deployment
- [ ] Server provisioned
- [ ] Models transferred (if air-gapped)
- [ ] Application deployed
- [ ] Health check passing
- [ ] Monitoring configured

### Post-Deployment
- [ ] Test with real receipts
- [ ] Monitor performance
- [ ] Collect user feedback
- [ ] Review API costs
- [ ] Plan for scaling

---

## Recommended Timeline

### Week 1: Testing Phase
- Test with 10-20 receipts
- Validate accuracy
- Collect feedback
- Identify issues

### Week 2: Planning Phase
- Decide on deployment option
- Plan infrastructure
- Set up monitoring
- Prepare documentation

### Week 3: Deployment Phase
- Deploy to staging
- Run load tests
- Deploy to production
- Monitor closely

### Week 4+: Optimization Phase
- Tune performance
- Reduce costs
- Improve accuracy
- Scale as needed

---

## Cost Estimates

### Cloud Deployment (with Vision LLM)
- Server: $50-100/month (4GB RAM)
- OpenAI API: $0.01-0.03/receipt
- Storage: $5-10/month
- **Total: $55-110/month + per-receipt costs**

### Air-Gapped Deployment
- Server: $100-200/month (8GB RAM, GPU)
- Storage: $10-20/month
- **Total: $110-220/month (no per-receipt costs)**

### Hybrid Deployment
- Server: $50-100/month
- OpenAI API: Optional
- **Total: $50-100/month**

---

## Support

For deployment assistance:
1. Review this guide
2. Test in development
3. Contact team for production support
