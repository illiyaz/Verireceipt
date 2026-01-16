# R10_TEMPLATE_QUALITY Contract

**CLUSTER_ID:** `TQC_TEMPLATE_QUALITY`  
**RULE_ID:** `R10_TEMPLATE_QUALITY`  
**VERSION:** 1.0  
**STATUS:** 🔒 LOCKED

---

## 🎯 Purpose

Detect template quality anomalies in receipts and invoices without relying on LLMs or inference. This is a **soft signal only** - it contributes minimally to the fraud score and cannot flip a document from REAL → FAKE alone.

---

## 📋 Scope

### **Allowed Document Families**

| Family | Execution Mode | Rationale |
|--------|----------------|-----------|
| `POS_RECEIPT` | 🟡 SOFT | Template quality is a soft heuristic |
| `POS_RESTAURANT` | 🟡 SOFT | Template quality is a soft heuristic |
| `POS_RETAIL` | 🟡 SOFT | Template quality is a soft heuristic |
| `COMMERCIAL_INVOICE` | 🟡 SOFT | Template quality is a soft heuristic |
| `TAX_INVOICE` | 🟡 SOFT | Template quality is a soft heuristic |
| `CREDIT_NOTE` | ❌ FORBIDDEN | Credit notes are messy by nature |
| `LOGISTICS` | ❌ FORBIDDEN | Logistics docs have varied formats |
| `SUBSCRIPTION` | ❌ FORBIDDEN | Subscription invoices are messy |
| `UNKNOWN` | ❌ FORBIDDEN | Safety: never fire on unknown |

### **Intent**
- `template_integrity_soft_signal`

---

## 🚦 Gates

### **Hard Gates (Must Pass)**
1. **Document Family:** Must be in allowed list (see above)
2. **Document Profile Confidence:** `>= 0.75`

### **Signal-Specific Gates**
- **S1 (Keyword Typos):** `lang_confidence >= 0.60`
- **S2 (Spacing Anomaly):** Always allowed (language-agnostic)
- **S3 (Date Format):** `geo_confidence >= 0.70`

---

## 🔍 Signal Detectors

### **S1: Keyword Typo Detector**

**What it does:**
- Checks for typos in semantic keywords (e.g., "maximun" → "maximum")
- Uses Levenshtein distance (edit distance 1-2)
- Language-specific keyword dictionaries

**Supported Languages:**
- English (en): `invoice`, `total`, `subtotal`, `tax`, `amount`, `due`, `maximum`, `minimum`, `quantity`, `price`, `discount`, `balance`, `payment`, `receipt`, `date`
- Spanish (es): `factura`, `total`, `subtotal`, `impuesto`, `iva`, `importe`, `vencimiento`, `máximo`, `mínimo`, `cantidad`, `precio`, `descuento`, `saldo`, `pago`, `recibo`, `fecha`
- French (fr): `facture`, `total`, `sous-total`, `taxe`, `tva`, `montant`, `dû`, `maximum`, `minimum`, `quantité`, `prix`, `remise`, `solde`, `paiement`, `reçu`, `date`
- German (de): `rechnung`, `gesamt`, `zwischensumme`, `steuer`, `mwst`, `betrag`, `fällig`, `maximum`, `minimum`, `menge`, `preis`, `rabatt`, `saldo`, `zahlung`, `quittung`, `datum`

**OCR Safety:**
- Uses accent normalization (e.g., "máximo" → "maximo")
- Handles OCR accent stripping gracefully
- Deterministic across languages

**Score Contribution:** 0.0 - 0.4

**NO LLM. NO INFERENCE.**

---

### **S2: Spacing Anomaly Detector**

**What it does:**
- Detects unusual spacing patterns (multiple spaces, tabs)
- Flags misaligned columns
- Language-agnostic (works for Arabic, Chinese, English, etc.)

**Triggers:**
- Multiple consecutive spaces (`  `)
- Tab characters in text
- At least 2 suspicious lines required

**Score Contribution:** 0.0 - 0.4

**LANGUAGE-AGNOSTIC.**

---

### **S3: Date Format Mismatch Detector**

**What it does:**
- Detects ambiguous or mismatched date formats
- Only fires when unambiguous (day > 12)
- Very weak signal

**Score Contribution:** 0.0 - 0.2

**VERY WEAK. GEO-GATED.**

---

## 📊 Scoring

### **Maximum Weight**
- `MAX_WEIGHT = 0.05` (5% of total score)

### **Severity Levels**
- `INFO`: `applied < 0.03`
- `WARNING`: `applied >= 0.03`

### **Aggregation**
```python
tqc_score = S1_delta + S2_delta + S3_delta
applied = min(MAX_WEIGHT, tqc_score * MAX_WEIGHT)
```

---

## 🛡️ Safety Guarantees

1. **MUST NOT flip REAL → FAKE alone**
   - Max weight is only 0.05 (5%)
   - Other rules must also fire for FAKE label

2. **MUST NOT fire on UNKNOWN family**
   - Execution mode is FORBIDDEN for UNKNOWN

3. **Language Safety**
   - S1 only fires if language is supported
   - S2 is language-agnostic (safe for all languages)
   - S3 is geo-gated (only fires with high geo confidence)

4. **No False Positives on Clean Docs**
   - Spanish invoice with no English typos → R10 does NOT fire
   - Chinese invoice with proper spacing → R10 does NOT fire

---

## 🧪 Golden Tests (MANDATORY)

### **Test 1: invoice_template_typo_maximun.json**
- **Contains:** "maximun" instead of "maximum"
- **Expects:** R10 fired
- **Score:** ≤ 0.05 (MAX_WEIGHT cap)
- **Evidence:** `keyword_typos` with `{"expected": "maximum", "found": "maximun"}`

### **Test 2: invoice_spacing_anomaly.json**
- **Contains:** Misaligned columns (multiple spaces)
- **Language:** Unknown
- **Expects:** R10 fired
- **Score:** ≤ 0.05 (MAX_WEIGHT cap)
- **Evidence:** `spacing_anomaly` with suspicious lines

### **Test 3: invoice_clean_spanish.json**
- **Language:** Spanish
- **Contains:** Clean Spanish invoice (no English typos)
- **Expects:** R10 does NOT fire

### **Test 4: invoice_clean_chinese_no_penalty.json**
- **Language:** Chinese
- **Contains:** Clean Chinese invoice with proper spacing
- **Expects:** R10 does NOT fire

**If any future rule breaks these → CI blocks merge.**

---

## 📁 File Structure

```
app/pipelines/
├── template_quality_signals.py    # Signal detectors (S1, S2, S3)
├── rules.py                        # R10 orchestrator
└── rule_family_matrix.py           # R10 matrix entry

tests/golden/
├── invoice_template_typo_maximun.json
├── invoice_spacing_anomaly.json
├── invoice_clean_spanish.json
└── invoice_clean_chinese_no_penalty.json
```

---

## 🔒 Naming Lock

**From this point forward:**
- **CLUSTER_ID** = `TQC_TEMPLATE_QUALITY`
- **RULE_ID** = `R10_TEMPLATE_QUALITY`
- We never refer to R8 for this purpose again
- R10 is permanently "Template Quality"

---

## 🚀 Extension Points

### **Adding New Languages**
1. Add keyword set to `SEMANTIC_KEYWORDS_BY_LANG` in `template_quality_signals.py`
2. Add golden test for new language
3. Update this document

### **Adding New Signals**
1. Implement signal detector in `template_quality_signals.py`
2. Return `(score_delta, evidence)` tuple
3. Add to R10 orchestrator in `rules.py`
4. Update golden tests
5. Update this document

### **Signal Requirements**
- **MUST** return `(float, Optional[Any])` tuple
- **MUST NOT** emit events directly
- **MUST** be isolated and testable
- **SHOULD** be language-agnostic when possible
- **SHOULD** have clear gates

---

## 📈 Upgrade Path

**Current:** SOFT (soft heuristic)  
**Future Options:**
- AUDIT (logging only) - for testing new signals before promotion
- BLOCK (full enforcement) - NOT RECOMMENDED (violates soft signal contract)

**Downgrade Criteria:**
- False positive rate > 5%
- User complaints about legitimate docs flagged

---

## ✅ Checklist for New Signals

- [ ] Implement detector in `template_quality_signals.py`
- [ ] Add to R10 orchestrator
- [ ] Add language support (if applicable)
- [ ] Create golden test
- [ ] Update this contract
- [ ] Run CI validation
- [ ] Monitor false positive rate

---

**Last Updated:** 2026-01-13  
**Owner:** VeriReceipt Core Team  
**Status:** 🔒 LOCKED
