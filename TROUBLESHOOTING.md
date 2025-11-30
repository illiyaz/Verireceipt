# VeriReceipt Troubleshooting Guide

## **Common Issues & Solutions**

---

## **Issue 1: Old Server Still Running (Code Changes Not Applied)**

### **Symptoms:**
- Made code changes but they don't work
- Errors persist after installing dependencies
- LayoutLM always pending
- PDF processing still fails

### **Cause:**
Multiple old server processes still running from previous sessions.

### **Solution:**

```bash
# Kill ALL old processes
pkill -9 -f "uvicorn.*app.api.main"
pkill -9 -f "run_web_demo"

# Or use the restart script
./restart_server.sh

# Verify no processes running
ps aux | grep -E "uvicorn|run_web_demo" | grep -v grep

# Should show nothing!
```

### **Then start fresh:**
```bash
python run_web_demo.py
```

---

## **Issue 2: PDF Processing Fails**

### **Symptoms:**
```
❌ Rule-Based failed: Unable to get page count
❌ DONUT failed: cannot identify image file
```

### **Causes:**
1. Old server running (see Issue 1)
2. Missing dependencies
3. Corrupted PDF file

### **Solutions:**

#### **Step 1: Kill old processes**
```bash
pkill -9 -f "uvicorn.*app.api.main"
```

#### **Step 2: Verify dependencies**
```bash
# Check PyMuPDF
python -c "import fitz; print('PyMuPDF:', fitz.version)"

# Check pdf2image
python -c "from pdf2image import convert_from_path; print('pdf2image: OK')"
```

#### **Step 3: Test PDF loading**
```bash
python -c "
from app.pipelines.ingest import _load_images_from_pdf
imgs = _load_images_from_pdf('your_receipt.pdf')
print(f'Loaded {len(imgs)} pages')
"
```

#### **Step 4: Restart server**
```bash
python run_web_demo.py
```

---

## **Issue 3: LayoutLM Always Pending**

### **Symptoms:**
- LayoutLM never shows in logs
- Always stays in "pending" state
- No success or error message

### **Causes:**
1. Old server running (most common!)
2. LayoutLM not available
3. Timeout issue

### **Solutions:**

#### **Step 1: Kill old server**
```bash
pkill -9 -f "uvicorn.*app.api.main"
```

#### **Step 2: Check LayoutLM availability**
```bash
python -c "
from app.pipelines.layoutlm_extractor import LAYOUTLM_AVAILABLE
print(f'LayoutLM Available: {LAYOUTLM_AVAILABLE}')
"
```

If False, install dependencies:
```bash
pip install transformers torch pillow pytesseract
brew install tesseract
```

#### **Step 3: Restart server**
```bash
python run_web_demo.py
```

---

## **Issue 4: Port Already in Use**

### **Symptoms:**
```
OSError: [Errno 48] Address already in use
```

### **Solution:**
```bash
# Kill processes on port 8000 and 3000
lsof -ti:8000 | xargs kill -9
lsof -ti:3000 | xargs kill -9

# Then restart
python run_web_demo.py
```

---

## **Issue 5: Date Mismatch Not Detected**

### **Symptoms:**
- PDF created days after receipt date
- Still marked as REAL
- No date mismatch warning

### **Causes:**
1. Rule-Based engine failed (see Issue 2)
2. Date extraction failed
3. Old server running

### **Solutions:**

#### **Step 1: Ensure Rule-Based works**
```bash
# Test directly
python -c "
from app.pipelines.rules import analyze_receipt
result = analyze_receipt('your_receipt.pdf')
print(f'Label: {result.label}')
print(f'Reasons: {result.reasons}')
"
```

#### **Step 2: Check date extraction**
```bash
python -c "
from app.pipelines.features import _extract_receipt_date
date = _extract_receipt_date('Receipt date: 20/11/2025')
print(f'Extracted date: {date}')
"
```

#### **Step 3: Kill old server and restart**
```bash
pkill -9 -f "uvicorn.*app.api.main"
python run_web_demo.py
```

---

## **Issue 6: All Engines Timeout**

### **Symptoms:**
```
❌ Rule-Based failed: Timeout after 30s
❌ DONUT failed: Timeout after 60s
```

### **Causes:**
1. System overloaded
2. Large PDF file
3. Slow OCR processing

### **Solutions:**

#### **Increase timeouts:**
Edit `app/api/main.py`:
```python
# Line ~457
RULE_BASED_TIMEOUT = 60   # Was 30s
DONUT_TIMEOUT = 120       # Was 60s
LAYOUTLM_TIMEOUT = 120    # Was 60s
VISION_TIMEOUT = 180      # Was 90s
```

#### **Reduce PDF size:**
```bash
# Reduce DPI in app/pipelines/ingest.py
# Line ~18: dpi=300 → dpi=150
```

---

## **Issue 7: Canva Receipt Not Detected**

### **Symptoms:**
- Fake receipt created in Canva
- Marked as REAL
- No suspicious producer warning

### **Causes:**
1. JPG export loses metadata
2. Need visual analysis
3. Vision LLM not detecting

### **Solutions:**

#### **Check if metadata preserved:**
```bash
python -c "
from app.pipelines.metadata import extract_image_metadata
meta = extract_image_metadata('canva_receipt.jpg')
print(f'Creator: {meta.get(\"creator\")}')
print(f'Software: {meta.get(\"Software\")}')
"
```

#### **Enhance Vision LLM prompt:**
See `FRAUD_DETECTION_IMPROVEMENTS.md` for enhanced prompts.

---

## **Quick Diagnostic Script**

Save as `diagnose.py`:

```python
#!/usr/bin/env python3
import subprocess
import sys

print("🔍 VeriReceipt Diagnostic Tool\n")

# Check dependencies
print("1. Checking dependencies...")
try:
    import fitz
    print("   ✅ PyMuPDF installed")
except:
    print("   ❌ PyMuPDF missing: pip install pymupdf")

try:
    from pdf2image import convert_from_path
    print("   ✅ pdf2image installed")
except:
    print("   ❌ pdf2image missing: pip install pdf2image")

try:
    from app.pipelines.layoutlm_extractor import LAYOUTLM_AVAILABLE
    print(f"   {'✅' if LAYOUTLM_AVAILABLE else '❌'} LayoutLM available: {LAYOUTLM_AVAILABLE}")
except:
    print("   ❌ LayoutLM import failed")

# Check running processes
print("\n2. Checking running processes...")
result = subprocess.run(
    "ps aux | grep -E 'uvicorn.*app.api.main' | grep -v grep",
    shell=True, capture_output=True, text=True
)
if result.stdout:
    print("   ⚠️  Old server processes found:")
    print(result.stdout)
    print("   Run: pkill -9 -f 'uvicorn.*app.api.main'")
else:
    print("   ✅ No old processes running")

# Check ports
print("\n3. Checking ports...")
for port in [8000, 3000]:
    result = subprocess.run(
        f"lsof -ti:{port}",
        shell=True, capture_output=True, text=True
    )
    if result.stdout:
        print(f"   ⚠️  Port {port} in use by PID: {result.stdout.strip()}")
    else:
        print(f"   ✅ Port {port} available")

print("\n✅ Diagnostic complete!")
print("\nRecommended action:")
print("1. Kill old processes: pkill -9 -f 'uvicorn.*app.api.main'")
print("2. Restart server: python run_web_demo.py")
```

Run it:
```bash
python diagnose.py
```

---

## **Best Practices**

### **Always Do This Before Testing:**

```bash
# 1. Kill old processes
pkill -9 -f "uvicorn.*app.api.main"
pkill -9 -f "run_web_demo"

# 2. Verify ports are free
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:3000 | xargs kill -9 2>/dev/null

# 3. Start fresh
python run_web_demo.py
```

### **After Code Changes:**

```bash
# Always restart the server!
# Ctrl+C to stop
# Then: python run_web_demo.py
```

### **After Installing Dependencies:**

```bash
# Restart the server to load new packages
pkill -9 -f "uvicorn.*app.api.main"
python run_web_demo.py
```

---

## **Summary**

### **Most Common Issue: Old Server Running** 🔥

**90% of problems are caused by old server processes!**

**Always do this first:**
```bash
pkill -9 -f "uvicorn.*app.api.main"
python run_web_demo.py
```

### **Quick Fix Checklist:**

- [ ] Kill old processes
- [ ] Check dependencies installed
- [ ] Verify ports are free
- [ ] Restart server
- [ ] Test again

**If still not working, run `python diagnose.py` for detailed diagnostics.**
