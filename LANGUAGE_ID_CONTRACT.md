# Language Identification Contract

**MODULE:** `app/pipelines/language_id.py`  
**VERSION:** 1.0  
**STATUS:** 🔒 FOUNDATION

---

## 🎯 Purpose

Provide **deterministic, confidence-aware language identification** for OCR text that:
- Works on short OCR text
- Handles mixed-language receipts
- Never pollutes downstream rules with false confidence
- Treats "mixed" as a first-class state

---

## 🚫 What This Is NOT

❌ **NOT an LLM-based language guesser**  
❌ **NOT a translation service**  
❌ **NOT a script detector** (though it could be extended)

✅ **IS a deterministic, confidence-gated language classifier**

---

## 🔧 Technology Choice

**Tool:** fastText `lid.176.bin`

**Why fastText?**
- ✅ Fast (milliseconds)
- ✅ Offline (no API calls)
- ✅ Robust on short text
- ✅ Deterministic (same input → same output)
- ✅ Supports 176 languages
- ✅ Well-tested in production

**Installation:**
```bash
pip install fasttext
```

**Model Download:**
```bash
wget https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin
mv lid.176.bin resources/models/
```

---

## 📊 Decision Logic

### **Step 1: Text Preprocessing**

```python
def extract_language_text(text_lines):
    clean = []
    for line in text_lines:
        if len(line) < 4:
            continue
        alpha_ratio = sum(c.isalpha() for c in line) / max(len(line), 1)
        if alpha_ratio < 0.30:
            continue
        clean.append(line)
    return " ".join(clean)[:2000]
```

**Filters out:**
- Numeric-only lines (prices, totals)
- Very short lines (< 4 chars)
- Lines with low alphabetic ratio (< 30%)

**Keeps:**
- Headers, labels, descriptions
- Merchant names
- Product descriptions

---

### **Step 2: Language Detection**

```python
if text_len < 200:
    lang = "mixed"
    conf = 0.0
elif top_lang_conf < 0.40:
    lang = "mixed"
    conf = detected_conf
else:
    lang = detected_lang
    conf = detected_conf
```

**Key Thresholds:**
- **Minimum text length:** 200 chars
- **Minimum confidence:** 0.40

**Result:**
- `lang`: ISO 639-1 code (e.g., "en", "es", "zh") or "mixed"
- `lang_confidence`: 0.0 - 1.0
- `lang_source`: "fasttext"

---

## 📋 Output Schema

```python
{
  "lang": "en" | "es" | "zh" | "mixed",
  "lang_confidence": 0.0 - 1.0,
  "lang_source": "fasttext",
  "text_length": int,
  "lines_used": int
}
```

**Persisted in `doc_profile`:**
```json
{
  "lang": "en",
  "lang_confidence": 0.95,
  "lang_source": "fasttext"
}
```

---

## 🔒 Integration with R10 (Template Quality)

### **Updated S1 Gate**

**Before:**
```python
if lang_conf >= 0.60:
    delta, ev = detect_keyword_typos(tf, lang)
```

**After:**
```python
if lang_conf >= 0.60 and lang != "mixed":
    delta, ev = detect_keyword_typos(tf, lang)
```

**Why:** Mixed-language receipts should NOT trigger spelling checks.

---

### **Gate Summary**

| Signal | Gate |
|--------|------|
| **S1 (Keyword Typos)** | `lang_conf >= 0.60` AND `lang != "mixed"` |
| **S2 (Spacing Anomaly)** | Always allowed (language-agnostic) |
| **S3 (Date Format)** | `geo_conf >= 0.70` |

---

## 🧪 Golden Tests (MANDATORY)

### **Test 1: invoice_english_typo.json**
- **lang:** "en"
- **lang_confidence:** 0.95
- **Contains:** "maximun" typo
- **Expects:** R10 fires

### **Test 2: invoice_mixed_language.json**
- **lang:** "mixed"
- **lang_confidence:** 0.0
- **Contains:** English + Arabic text
- **Expects:** R10 does NOT fire

### **Test 3: invoice_short_text.json**
- **lang:** "mixed"
- **lang_confidence:** 0.0
- **Text length:** < 150 chars
- **Expects:** No language-based rules fire

### **Test 4: invoice_chinese_clean.json**
- **lang:** "zh"
- **lang_confidence:** 0.98
- **Contains:** Clean Chinese text
- **Expects:** R10 does NOT fire (no English spelling expected)

**CI BLOCKS if these fail.**

---

## 🛡️ Safety Guarantees

1. **Never lie about language**
   - If uncertain → "mixed"
   - If short text → "mixed"
   - If low confidence → "mixed"

2. **"mixed" is first-class**
   - Not an error state
   - Not a fallback
   - A legitimate classification

3. **Confidence gates everything**
   - Low confidence → downstream rules skip
   - High confidence → downstream rules proceed
   - No confidence → safe default

4. **Deterministic**
   - Same input → same output
   - No randomness
   - No API calls

---

## 📁 File Structure

```
app/pipelines/
├── language_id.py              # Language ID module
├── rules.py                    # R10 uses lang gates
└── template_quality_signals.py # S1 respects lang

resources/models/
└── lid.176.bin                 # fastText model (176 languages)

tests/golden/
├── invoice_english_typo.json
├── invoice_mixed_language.json
├── invoice_short_text.json
└── invoice_chinese_clean.json
```

---

## 🚀 Integration Guide

### **Step 1: Add to Document Profiling**

```python
from app.pipelines.language_id import get_language_from_features

# In document profiling pipeline
lang_result = get_language_from_features(tf, lf)

doc_profile.update({
    "lang": lang_result["lang"],
    "lang_confidence": lang_result["lang_confidence"],
    "lang_source": lang_result["lang_source"],
})
```

### **Step 2: Use in Rules**

```python
# In rule logic
lang = tf.get("lang_guess") or doc_profile.get("lang")
lang_conf = float(tf.get("lang_confidence") or doc_profile.get("lang_confidence") or 0.0)

if lang_conf >= 0.60 and lang != "mixed":
    # Safe to use language-specific logic
    pass
```

---

## 📈 Supported Languages (Top 20)

| Code | Language | Notes |
|------|----------|-------|
| en | English | Primary |
| es | Spanish | Primary |
| fr | French | Primary |
| de | German | Primary |
| zh | Chinese | Primary |
| ar | Arabic | Primary |
| ja | Japanese | Supported |
| ko | Korean | Supported |
| pt | Portuguese | Supported |
| ru | Russian | Supported |
| it | Italian | Supported |
| nl | Dutch | Supported |
| pl | Polish | Supported |
| tr | Turkish | Supported |
| vi | Vietnamese | Supported |
| th | Thai | Supported |
| id | Indonesian | Supported |
| ms | Malay | Supported |
| hi | Hindi | Supported |
| bn | Bengali | Supported |

**Total:** 176 languages supported by fastText

---

## 🔄 Upgrade Path

**Current:** fastText `lid.176.bin`  
**Future Options:**
- Add script detection (Latin, Arabic, CJK, etc.)
- Add language-specific confidence tuning
- Add multilingual keyword expansion

**Downgrade Criteria:**
- False positive rate > 5% on mixed-language docs
- Performance issues (> 100ms per doc)

---

## ✅ Checklist for Language-Based Rules

Before adding a language-based rule:
- [ ] Check `lang != "mixed"`
- [ ] Check `lang_confidence >= threshold`
- [ ] Add golden test for target language
- [ ] Add golden test for mixed-language case
- [ ] Document language support in rule header
- [ ] Update this contract if new languages added

---

**Last Updated:** 2026-01-13  
**Owner:** VeriReceipt Core Team  
**Status:** 🔒 FOUNDATION
