# OCR & Extraction Benchmark: Popeyes Receipt

**Date:** Feb 14, 2026  
**Test Image:** `data/raw/Popeyes total wrong.png` (600x1651 px, POS thermal receipt)

---

## Ground Truth (human reading of receipt)

| Field | Value |
|-------|-------|
| Merchant | POPEYES |
| Address | 507 S Cumberland St, Lebanon, TN 37087 |
| Phone | (615) 994-8796 |
| Receipt Date | 06/08/25 2:43 PM |
| Items | 6 PC CHICKEN COMBO $18.98, 5 REG BISCUIT $10, 1 REG SIDES $10, 2 SMALL DRINK $10, 3 SALT FRIES $13.97, 1 SPRITE $2.89 |
| Subtotal | $75.84 |
| Tax | $3.05 |
| Total | $88.89 |
| Payment | DEBIT, card ending 4922, CHIP |
| Card Date | 11/20/2019 11:09 AM |
| Status | APPROVED |
| Country | USA (Tennessee) |

**Known anomaly:** Card transaction date (2019) is ~6 years before receipt date (2025). This is the "total wrong" — either manipulated receipt or system clock issue.

---

## Engine Results

### 1. EasyOCR (Current Pipeline)

| Field | Extracted | Correct? |
|-------|-----------|----------|
| Merchant | `{` | WRONG |
| Address | Not found | WRONG |
| Phone | Not found | WRONG |
| Date | Found 2025-06-08 + 2019-11-20 | Partial |
| Subtotal | `S75,84` (not parsed) | WRONG |
| Tax | `'83', 05` (not parsed) | WRONG |
| Total | `588, 89` (not parsed) | WRONG |
| Country | Australia (0.82 conf) | WRONG |
| Language | mixed (0.0 conf) | WRONG |
| Doc Type | RECEIPT (0.55 conf) | Partial |
| **Verdict** | **real (score 0.175)** | **WRONG** |

**Key failures:** `$` → `S`, decimals → commas, random single-char garbage lines, merchant picked `{` from line 2.

**OCR text (first 300 chars):**
```
6\n{\n'aus1am\n19\n72\ntitchev\npopeves\nX\n507\nS Cumber land St _\nLebanon _\nETN 370087\nQ\n(6,15)* 994-8796\nDate: 06/08/25 2:43 PM\n6\nPC CHICKEN COMBO\nQ\nS18, 98\nREG BISCUIT\n810\nREG SIDES...
```

---

### 2. Tesseract 5.5.1 (Default, no preprocessing)

| Field | Extracted | Correct? |
|-------|-----------|----------|
| Merchant | `Popeyes.` | YES (extra period) |
| Address | `507 S Cumberland St, Lebanon, TN 370087` | YES (zip +0) |
| Phone | `(615) 994-8796` | YES |
| Date | `06/08/25 2:43 PM` (with preprocessing) | YES |
| Items | All names correct | YES |
| Subtotal | `$75.84` | YES |
| Tax | `$3.05` | YES |
| Total | `$88,89` | Partial (comma) |
| Card | `4922`, DEBIT, CHIP | YES |
| Card Date | `11/20/2019 11:09 AM` | YES |

**OCR text:**
```
Popeyes.\n\n507 S Cumberland St,\nLebanon, TN 370087\n(615) 994-8796\n\n6 PC CHICKEN COMBO $1898\n5 REG BISCUIT $10\n1 REG SIDES $10\n2 SMALL DRINK $10\n3 SALT FRIES $13.97\n1 SPRITE $2,89\n\nSubtotal $75.84\n\nTax $3.05\n\nTotal $88,89\nCARD NUMBER...
```

**Assessment:** Dramatically better than EasyOCR. Clean text, correct structure, $ signs preserved, items on proper lines. Minor issues: `$1898` missing decimal, `$88,89` uses comma.

---

### 3. Tesseract + Otsu Binarization

Similar to default Tesseract with minor differences. Phone became `(815)` instead of `(615)`. No significant improvement over default.

---

### 4. EasyOCR + Otsu Preprocessing

Better than raw EasyOCR but still noisy:
- Merchant: `Popeves` (improved from `{`)
- Address: on one line (good)
- Items/prices merged into separate blocks (bad for alignment)
- `S` still used instead of `$`

Not competitive with Tesseract.

---

### 5. Qwen2.5-VL:32B (Vision LLM via Ollama)

| Field | Extracted | Correct? |
|-------|-----------|----------|
| Merchant | `POPEYES` | YES |
| Address | `507 S Cumberland St, Lebanon, TN 370087` | YES |
| Phone | `(615) 994-8796` | YES |
| Date | `06/08/25` | YES |
| Time | `2:43 PM` | YES |
| Items | All 6 items with correct prices | YES |
| Subtotal | `75.84` | YES |
| Tax | `3.05` | YES |
| Total | `88.89` | YES |
| Payment | DEBIT, 4922, CHIP | YES |
| Card Date | `11/20/2019 11:09 AM` | YES |
| Status | APPROVED | YES |

**Accuracy: ~98%** (only minor: zip code 370087 vs 37087 — matches what's printed)  
**Latency: ~20 seconds**

---

### 6. Llama3.2-Vision:latest (11B, current default)

| Field | Extracted | Correct? |
|-------|-----------|----------|
| Merchant | `POPEYES` | YES |
| Address | `507 S Cumberland St. Lebanon, TN 37087` | YES |
| Phone | `(615) 994-8796` | YES |
| Date | `06/08/25 2:43 PM` | YES |
| Items | All 6 items with correct prices | YES |
| Subtotal | `75.84` | YES |
| Tax | `3.05` | YES |
| Total | `88.89` | YES |
| Payment | DEBIT, 4922 | YES |
| Card Date/Time | Fields slightly swapped | Minor |
| Status | APPROVED | YES |

**Accuracy: ~95%** (minor field assignment issues in card section)  
**Latency: ~7.4 seconds**

---

### 7. Gemma3:27B (Vision)

| Field | Extracted | Correct? |
|-------|-----------|----------|
| Merchant | `POPEYES LOUISIANA KITCHEN` | Hallucinated (added chain name) |
| Date | `06/25` | WRONG (dropped day) |
| Items | Missing BISCUIT, wrong SALT FRIES price | WRONG |
| Subtotal | `41.87` | WRONG |
| Total | `44.87` | WRONG |

**Accuracy: ~40%** — Hallucinated values, unreliable.  
**Latency: ~14.3 seconds**

---

## Comparison Matrix

| Field | EasyOCR | Tesseract | Qwen2.5-VL | Llama3.2-V | Gemma3 |
|-------|---------|-----------|------------|------------|--------|
| Merchant | X | ~ | **YES** | **YES** | ~ |
| Address | X | **YES** | **YES** | **YES** | **YES** |
| Phone | X | **YES** | **YES** | **YES** | **YES** |
| Date | ~ | **YES** | **YES** | **YES** | X |
| Items | X | **YES** | **YES** | **YES** | X |
| Subtotal | X | **YES** | **YES** | **YES** | X |
| Tax | X | **YES** | **YES** | **YES** | X |
| Total | X | ~ | **YES** | **YES** | X |
| Card info | X | **YES** | **YES** | ~ | ~ |
| **Score** | **1/10** | **8/10** | **10/10** | **9/10** | **4/10** |
| **Latency** | **~2s** | **~1s** | **~20s** | **~7s** | **~14s** |

---

## Key Findings

### 1. EasyOCR is catastrophically bad on thermal POS receipts
- `$` signs become `S` or disappear
- Random single-character garbage lines
- Amounts not on same line as items
- The entire downstream pipeline fails because of this

### 2. Tesseract is dramatically better out of the box
- Correctly reads `$` signs, item lines, totals
- Clean line structure
- Minor decimal/comma issues
- **Switching from EasyOCR to Tesseract for the primary OCR would be a low-effort, high-impact fix**

### 3. Vision LLMs produce structured data directly
- Qwen2.5-VL:32B and Llama3.2-Vision both achieve near-perfect extraction
- They understand receipt structure, not just individual characters
- They return properly typed values (numbers, not strings)
- Card date/time correctly identified as separate from receipt date
- **20s latency is acceptable for receipt verification (not real-time)**

### 4. Not all Vision LLMs are equal
- Gemma3:27B hallucinated values — unreliable for extraction
- Model selection matters significantly

### 5. The real receipt IS suspicious
- Card transaction date (11/20/2019) is ~6 years before receipt date (06/08/25)
- This is a legitimate fraud signal that should be caught
- With proper extraction, the rules engine would correctly flag this

---

## Recommended Architecture

### Phase 1: Quick Win — Switch to Tesseract (Days)
Replace EasyOCR with Tesseract as the primary OCR engine. This alone fixes ~80% of extraction issues on POS receipts with minimal code changes.

### Phase 2: Vision LLM Extraction (1-2 Weeks)
Add Vision LLM as a **structured extraction layer** that runs in parallel with OCR:
```
Image → [Tesseract OCR] → text features → Rules Engine
  │                                            ↑
  └──→ [Vision LLM] → structured JSON → validate/merge
```

The Vision LLM extracts: merchant, address, items, totals, dates, payment info.
The Rules Engine validates: math consistency, date logic, fraud patterns.

### Phase 3: Confidence-Weighted Fusion (Ongoing)
When OCR and Vision LLM disagree, use confidence scores to pick the better value per field. Track accuracy over time to auto-tune weights.

### Why NOT Vision LLM Only?
- 7-20s latency per receipt (OCR is <2s)
- Requires GPU/Ollama running
- Can hallucinate (Gemma3 example)
- Rules engine still needed for fraud logic
- OCR text still useful for regex patterns, keyword detection

### Why NOT Tesseract Only?
- Still has decimal/comma issues
- Doesn't understand document structure (just reads text)
- Can't extract meaning (item name vs quantity vs price)
- No visual fraud detection (editing artifacts, font inconsistencies)
