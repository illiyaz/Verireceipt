# LLM Document Classifier Setup

The document classifier uses LLM as a **gated fallback** when heuristics are uncertain (low confidence, unknown subtype, etc.).

## Quick Start with Ollama (Local)

### 1. Install Ollama

```bash
# macOS/Linux
curl -fsSL https://ollama.com/install.sh | sh

# Or download from https://ollama.com/download
```

### 2. Pull a Model

```bash
# Recommended: Fast 3B model for classification
ollama pull llama3.2:3b

# Alternative: Larger model for better accuracy
ollama pull llama3.1:8b
```

### 3. Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit .env (defaults are fine for local Ollama)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
```

### 4. Install Python Package

```bash
pip install ollama
```

### 5. Test

```bash
# Ollama should auto-start, or run manually:
ollama serve

# Test classification
python scripts/show_evidence.py data/raw/your_document.pdf
# Look for "llm_classification" field in output
```

## Alternative: OpenAI (Cloud)

### 1. Get API Key

Sign up at https://platform.openai.com/api-keys

### 2. Configure

```bash
# Edit .env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o-mini
```

### 3. Install Package

```bash
pip install openai
```

## When LLM is Called

The classifier only runs when heuristics are uncertain:

- ✅ Document profile confidence < 0.6
- ✅ Domain confidence < 0.6
- ✅ Document subtype = "unknown"
- ✅ Language confidence < 0.5
- ✅ Non-English with confidence < 0.8

**Typical trigger rate:** 15-25% of documents

## Disable LLM

```bash
# Edit .env
LLM_PROVIDER=none
```

## Model Recommendations

### Ollama (Local)

| Model | Size | Speed | Accuracy | Use Case |
|-------|------|-------|----------|----------|
| `llama3.2:3b` | 2GB | Fast | Good | **Recommended** for most cases |
| `llama3.1:8b` | 4.7GB | Medium | Better | Higher accuracy needed |
| `mistral:7b` | 4.1GB | Medium | Good | Alternative option |

### OpenAI (Cloud)

| Model | Cost/1K tokens | Speed | Accuracy |
|-------|----------------|-------|----------|
| `gpt-4o-mini` | $0.00015 | Fast | Excellent |
| `gpt-4o` | $0.0025 | Medium | Best |

## Troubleshooting

### Ollama not connecting

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama manually
ollama serve

# Check logs
tail -f ~/.ollama/logs/server.log
```

### Model not found

```bash
# List installed models
ollama list

# Pull missing model
ollama pull llama3.2:3b
```

### Slow classification

- Use smaller model (`llama3.2:3b` instead of `8b`)
- Reduce `LLM_MAX_TOKENS` in `.env`
- Check CPU/GPU usage during inference

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Document Processing                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Heuristic Classification                        │
│  • Geo-aware profiling (geo_detection.py)                   │
│  • Domain inference (domain_validation.py)                   │
│  • Keyword matching, pattern detection                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Gate Check:    │
                    │  Confidence OK? │
                    └─────────────────┘
                         │         │
                    YES  │         │  NO
                         │         │
                         │         ▼
                         │  ┌──────────────────────┐
                         │  │  LLM Classifier      │
                         │  │  (llm_classifier.py) │
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
┌─────────────────────────────────────────────────────────────┐
│              Document Intent Resolution                      │
│  • Map subtype → intent                                      │
│  • Apply domain bias if needed                               │
│  • Return final classification                               │
└─────────────────────────────────────────────────────────────┘
```

## Cost Estimation

### Ollama (Local)
- **Cost:** $0 (free, runs on your hardware)
- **Latency:** 1-3 seconds per document (3B model)
- **Privacy:** All data stays local

### OpenAI (Cloud)
- **Cost:** ~$0.0003 per document (2000 chars)
- **Latency:** 0.5-1.5 seconds per document
- **Privacy:** Data sent to OpenAI

**Example monthly cost (OpenAI):**
- 10,000 documents/month
- 25% trigger rate = 2,500 LLM calls
- 2,500 × $0.0003 = **$0.75/month**
