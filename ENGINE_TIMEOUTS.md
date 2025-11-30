# Engine Timeouts - Prevent Hanging Analysis

## Overview

The hybrid analysis system now has **timeouts** to prevent engines from hanging indefinitely.

---

## Problem Solved

### **Before: No Timeouts**
```
❌ If engine hangs → entire API hangs forever
❌ User waits indefinitely with "Analyzing..." spinner
❌ No way to recover without killing the server
❌ Bad user experience
```

### **After: With Timeouts**
```
✅ Each engine has a maximum time limit
✅ Timed-out engines marked as failed
✅ Other engines still return results
✅ User gets response within predictable time
✅ Tiered logic still works (critical vs optional)
```

---

## Timeout Configuration

### **Per-Engine Timeouts**

```python
RULE_BASED_TIMEOUT = 30   # 30 seconds (fast engine)
DONUT_TIMEOUT = 60        # 60 seconds (medium speed)
LAYOUTLM_TIMEOUT = 60     # 60 seconds (medium speed)
VISION_TIMEOUT = 90       # 90 seconds (slowest - Ollama)
```

### **Why These Values?**

| Engine | Normal Time | Timeout | Reason |
|--------|-------------|---------|--------|
| Rule-Based | 2-5s | 30s | Very fast, 30s is generous |
| DONUT | 5-15s | 60s | Medium speed, handles slow cases |
| LayoutLM | 3-8s | 60s | Medium speed, OCR can be slow |
| Vision LLM | 10-30s | 90s | Ollama can be slow, needs more time |

---

## How It Works

### **1. Submit All Engines in Parallel**

```python
with ThreadPoolExecutor(max_workers=4) as executor:
    rule_future = executor.submit(run_rule_based)
    donut_future = executor.submit(run_donut)
    layoutlm_future = executor.submit(run_layoutlm)
    vision_future = executor.submit(run_vision)
```

All 4 engines start at the same time.

---

### **2. Wait with Timeout**

```python
try:
    results["rule_based"] = rule_future.result(timeout=30)
except FuturesTimeoutError:
    results["rule_based"] = {
        "error": "Timeout after 30s - engine took too long",
        "time_seconds": 30
    }
```

If engine doesn't complete in 30s → mark as failed.

---

### **3. Continue with Other Engines**

Even if one times out, others still complete:

```python
# Rule-Based times out after 30s
results["rule_based"] = {"error": "Timeout after 30s"}

# But other engines still work
results["donut"] = {"merchant": "...", "total": 123.45}
results["layoutlm"] = {"merchant": "...", "total": 123.45}
results["vision_llm"] = {"verdict": "real", "confidence": 0.9}
```

---

### **4. Tiered Logic Handles Timeouts**

```python
# Critical engines
if rule_based OK and vision_llm OK:
    # Generate verdict (even if optional engines timed out)
    verdict = "real"
    confidence = 0.85
else:
    # Critical engine timed out
    verdict = "incomplete"
    action = "retry_or_review"
```

---

## Example Scenarios

### **Scenario 1: All Engines Complete (Normal)**

```json
{
  "rule_based": {"label": "real", "time_seconds": 2.3},
  "donut": {"merchant": "Store", "time_seconds": 8.1},
  "layoutlm": {"merchant": "Store", "time_seconds": 4.2},
  "vision_llm": {"verdict": "real", "time_seconds": 13.5},
  "hybrid_verdict": {
    "final_label": "real",
    "confidence": 0.95
  }
}
```

**Total time:** ~14 seconds (slowest engine)

---

### **Scenario 2: Optional Engine Timeouts**

```json
{
  "rule_based": {"label": "real", "time_seconds": 2.3},
  "donut": {"error": "Timeout after 60s", "time_seconds": 60},
  "layoutlm": {"merchant": "Store", "time_seconds": 4.2},
  "vision_llm": {"verdict": "real", "time_seconds": 13.5},
  "hybrid_verdict": {
    "final_label": "real",
    "confidence": 0.90,
    "engines_status": {
      "critical_complete": true,
      "optional_complete": 1,
      "failed_engines": ["DONUT: Timeout after 60s"]
    },
    "reasoning": [
      "✅ 3/4 engines indicate authentic receipt",
      "✅ Critical engines agree: REAL",
      "✅ LayoutLM validated structure",
      "ℹ️ DONUT unavailable (confidence slightly lower)"
    ]
  }
}
```

**Total time:** ~60 seconds (DONUT timeout)
**Result:** Still got verdict! DONUT timed out but it's optional.

---

### **Scenario 3: Critical Engine Timeouts**

```json
{
  "rule_based": {"label": "real", "time_seconds": 2.3},
  "donut": {"merchant": "Store", "time_seconds": 8.1},
  "layoutlm": {"merchant": "Store", "time_seconds": 4.2},
  "vision_llm": {"error": "Timeout after 90s", "time_seconds": 90},
  "hybrid_verdict": {
    "final_label": "incomplete",
    "confidence": 0.0,
    "recommended_action": "retry_or_review",
    "engines_status": {
      "critical_complete": false,
      "failed_engines": ["Vision LLM: Timeout after 90s"]
    },
    "reasoning": [
      "⚠️ Critical engines failed",
      "❌ Vision LLM: Timeout after 90s"
    ]
  }
}
```

**Total time:** ~90 seconds (Vision LLM timeout)
**Result:** Cannot generate verdict - critical engine failed.

---

### **Scenario 4: Multiple Timeouts**

```json
{
  "rule_based": {"label": "real", "time_seconds": 2.3},
  "donut": {"error": "Timeout after 60s", "time_seconds": 60},
  "layoutlm": {"error": "Timeout after 60s", "time_seconds": 60},
  "vision_llm": {"verdict": "real", "time_seconds": 13.5},
  "hybrid_verdict": {
    "final_label": "real",
    "confidence": 0.85,
    "engines_status": {
      "critical_complete": true,
      "optional_complete": 0,
      "failed_engines": [
        "DONUT: Timeout after 60s",
        "LayoutLM: Timeout after 60s"
      ]
    },
    "reasoning": [
      "✅ 2/4 engines indicate authentic receipt",
      "✅ Critical engines agree: REAL",
      "ℹ️ DONUT unavailable (confidence slightly lower)",
      "ℹ️ LayoutLM unavailable (confidence slightly lower)"
    ]
  }
}
```

**Total time:** ~60 seconds (both optional engines timeout)
**Result:** Still got verdict with lower confidence.

---

## Maximum Wait Times

### **Best Case (All Fast)**
- All engines complete quickly
- **Total time:** ~15 seconds

### **Worst Case (All Timeout)**
- All engines hit their timeout
- **Total time:** ~90 seconds (longest timeout)

### **Typical Case**
- Critical engines complete: ~15 seconds
- Optional engines may timeout: ~60 seconds
- **Total time:** 15-60 seconds

---

## Benefits

### **1. No Infinite Hanging**
```
Before: Engine hangs → wait forever
After:  Engine hangs → timeout after 90s max
```

### **2. Predictable Response Time**
```
Before: Unknown (could be hours)
After:  Maximum 90 seconds
```

### **3. Graceful Degradation**
```
Before: One engine hangs → no verdict
After:  Optional engine times out → still get verdict
```

### **4. Better UX**
```
Before: "Analyzing..." forever
After:  "Analysis complete! (DONUT timed out)"
```

### **5. Production Ready**
```
✅ Handles slow networks
✅ Handles unresponsive services
✅ Handles heavy load
✅ Always returns within 90s
```

---

## Adjusting Timeouts

### **Make Timeouts Longer**

If engines legitimately need more time:

```python
# In app/api/main.py
RULE_BASED_TIMEOUT = 60   # Was 30s
DONUT_TIMEOUT = 120       # Was 60s
LAYOUTLM_TIMEOUT = 120    # Was 60s
VISION_TIMEOUT = 180      # Was 90s
```

### **Make Timeouts Shorter**

For faster failure detection:

```python
RULE_BASED_TIMEOUT = 15   # Was 30s
DONUT_TIMEOUT = 30        # Was 60s
LAYOUTLM_TIMEOUT = 30     # Was 60s
VISION_TIMEOUT = 45       # Was 90s
```

### **Per-Environment Configuration**

```python
import os

# Development: Longer timeouts
if os.getenv("ENV") == "development":
    VISION_TIMEOUT = 180
# Production: Shorter timeouts
else:
    VISION_TIMEOUT = 60
```

---

## Monitoring Timeouts

### **Log Timeout Events**

```python
except FuturesTimeoutError:
    logger.warning(f"Vision LLM timed out after {VISION_TIMEOUT}s")
    results["vision_llm"] = {"error": "Timeout"}
```

### **Track Timeout Metrics**

```python
# Count timeouts per engine
timeout_counts = {
    "rule_based": 0,
    "donut": 5,      # DONUT times out frequently
    "layoutlm": 2,
    "vision_llm": 10  # Vision LLM times out most
}
```

### **Alert on High Timeout Rate**

```python
if timeout_rate > 0.5:  # 50% of requests timing out
    send_alert("High timeout rate - check Ollama service")
```

---

## Troubleshooting

### **Engine Always Times Out**

**Symptoms:**
- Same engine times out on every request
- Other engines complete normally

**Possible Causes:**
1. Service not running (e.g., Ollama stopped)
2. Service overloaded
3. Network issues
4. Model not loaded

**Solutions:**
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Restart Ollama
ollama serve

# Check system resources
top  # Look for high CPU/memory
```

---

### **All Engines Timeout**

**Symptoms:**
- All 4 engines timeout
- Every request fails

**Possible Causes:**
1. Server overloaded
2. Disk I/O issues
3. Memory exhaustion

**Solutions:**
```bash
# Check system resources
df -h   # Disk space
free -h # Memory
top     # CPU

# Restart services
systemctl restart verireceipt
```

---

### **Timeouts Too Aggressive**

**Symptoms:**
- Engines timeout but would complete if given more time
- Legitimate slow receipts fail

**Solutions:**
```python
# Increase timeouts
VISION_TIMEOUT = 180  # 3 minutes instead of 90s
```

---

## Summary

### **What Changed**

✅ **Added timeouts** to all 4 engines
✅ **Prevent infinite hanging** - max 90s wait
✅ **Graceful degradation** - optional engines can timeout
✅ **Better error messages** - "Timeout after 60s"
✅ **Production ready** - predictable response times

### **Timeout Values**

- **Rule-Based:** 30 seconds
- **DONUT:** 60 seconds
- **LayoutLM:** 60 seconds
- **Vision LLM:** 90 seconds

### **Maximum Wait Time**

**90 seconds** (Vision LLM timeout)

### **Key Principle**

**"Always return a response within predictable time, even if some engines fail"**

**Your fraud detection system is now robust against hanging engines! 🎉**
