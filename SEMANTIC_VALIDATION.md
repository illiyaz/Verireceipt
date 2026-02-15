# 🔍 Semantic Validation System

## Overview

VeriReceipt's **Semantic Validation System** provides multi-layered fraud detection beyond basic math verification. It uses a 7-stage hybrid pipeline that combines Vision LLM extraction with rule-based validation across three priority tiers:

| Tier | Features | Complexity |
|------|----------|------------|
| **P1** | Price Plausibility, Cross-Field Semantics | Low effort |
| **P2** | Merchant Context DB, Temporal Validation | Medium effort |
| **P3** | Receipt Template Fingerprinting | Medium effort |

---

## 🏗️ Architecture

### Hybrid Pipeline Stages

```
┌─────────────────────────────────────────────────────────────────┐
│                    hybrid_extract_and_verify()                   │
├─────────────────────────────────────────────────────────────────┤
│  Stage 1: Vision LLM Extraction (qwen2.5vl / llama3.2-vision)   │
│  Stage 2: Math Verification (subtotal + tax = total)            │
│  Stage 3: Price Plausibility (P1) - item/total range checks     │
│  Stage 4: Cross-Field Semantics (P1) - tax/currency consistency │
│  Stage 5: Merchant Context (P2) - DB-backed business rules      │
│  Stage 6: Temporal Validation (P2) - date/time plausibility     │
│  Stage 7: Template Fingerprinting (P3) - structural matching    │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

```python
result = hybrid_extract_and_verify("receipt.png")

# Returns:
{
    "success": True,
    "extracted": {...},           # Vision LLM output
    "verification": {...},        # Math check results
    "price_plausibility": {...},  # P1: price range checks
    "semantic_validation": {...}, # P1: cross-field checks
    "merchant_context": {...},    # P2: DB-backed rules
    "temporal_validation": {...}, # P2: date/time checks
    "template_validation": {...}, # P3: template fingerprint
    "fraud_signals": [...],       # All errors (HIGH severity)
    "warnings": [...],            # All warnings (MEDIUM/LOW)
    "is_suspicious": bool,
    "suspicion_reasons": {...},
}
```

---

## 📊 P1: Price Plausibility & Cross-Field Semantics

### Price Plausibility Checks

**Location:** `app/pipelines/vision_llm.py:validate_price_plausibility()`

**What it checks:**
- Individual item prices within merchant-type thresholds
- Total amount within expected range
- Currency normalization to USD for comparison

**Thresholds by Merchant Type:**

| Type | Min Item | Max Item | Max Total |
|------|----------|----------|-----------|
| restaurant | $0.50 | $200 | $1,000 |
| fast_food | $0.50 | $50 | $200 |
| grocery | $0.01 | $500 | $2,000 |
| fuel | $1.00 | $300 | $500 |
| retail | $0.50 | $5,000 | $10,000 |

**Currency Conversion:**
```python
CURRENCY_TO_USD = {
    "USD": 1.0, "INR": 0.012, "EUR": 1.08,
    "GBP": 1.27, "CAD": 0.74, "AED": 0.27, ...
}
```

**Output:**
```json
{
    "is_plausible": true,
    "errors": [],
    "warnings": [
        {"type": "SUSPICIOUSLY_HIGH_PRICE", "item": "...", "price_usd": 1548}
    ]
}
```

### Cross-Field Semantic Validation

**Location:** `app/pipelines/vision_llm.py:validate_cross_field_semantics()`

**What it checks:**
- Tax type matches country (e.g., CGST/SGST only in India)
- Currency matches country (e.g., INR only in India)
- Merchant type matches items (e.g., fuel station shouldn't sell electronics)

**Tax-Country Mapping:**
```python
TAX_COUNTRY_MAP = {
    "CGST": "IN", "SGST": "IN", "IGST": "IN", "GST": "IN",
    "VAT": ["UK", "DE", "AE", "EU"], 
    "Sales Tax": "US",
    "HST": "CA", "PST": "CA", "QST": "CA",
}
```

**Output:**
```json
{
    "is_consistent": true,
    "warnings": [
        {"type": "TAX_COUNTRY_MISMATCH", "tax": "CGST", "expected_country": "IN"}
    ]
}
```

---

## 🏪 P2: Merchant Context Database

### Database Schema

**Table:** `merchant_context` in `app/data/geo.sqlite`

```sql
CREATE TABLE merchant_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_name_norm TEXT NOT NULL,
    merchant_aliases TEXT,
    merchant_type TEXT NOT NULL,
    country_code TEXT,
    expected_items TEXT,
    forbidden_items TEXT,
    min_total REAL,
    max_total REAL,
    typical_hours_open INTEGER DEFAULT 6,
    typical_hours_close INTEGER DEFAULT 23,
    is_24h BOOLEAN DEFAULT FALSE,
    expected_currencies TEXT,
    expected_tax_types TEXT,
    notes TEXT,
    effective_from TEXT,
    effective_to TEXT
)
```

### Seed Data (23 merchants)

| Merchant | Type | Country | Hours | Expected Currency |
|----------|------|---------|-------|-------------------|
| popeyes | fast_food | US | 6-23 | USD |
| mcdonald | fast_food | Global | 6-24 | USD,EUR,GBP,INR |
| starbucks | fast_food | Global | 5-22 | USD,EUR,GBP |
| zaffran | restaurant | IN | 11-23 | INR |
| pizza hut | restaurant | IN | 11-23 | INR,USD |
| walmart | retail | US | 6-23 | USD |
| shell | fuel | Global | 24h | USD,GBP |
| ... | ... | ... | ... | ... |

### Query Functions

**Location:** `app/geo/db.py`

```python
# Look up merchant by name (fuzzy match)
context = query_merchant_context("Popeyes Louisiana Kitchen")

# Get all merchants by type
restaurants = query_merchants_by_type("restaurant")
```

### Merchant Context Validation

**Location:** `app/pipelines/vision_llm.py:validate_merchant_context()`

**What it checks:**
- Forbidden items present (e.g., electronics at fast food)
- Currency matches expected (e.g., USD at US Popeyes)
- Tax type matches expected (e.g., Sales Tax at US merchant)
- Total within expected range

**Output:**
```json
{
    "is_valid": true,
    "merchant_found": true,
    "warnings": [
        {"type": "TOTAL_BELOW_EXPECTED", "total_usd": 11.32, "min": 200.0}
    ],
    "errors": [
        {"type": "FORBIDDEN_ITEM_FOUND", "item": "laptop", "merchant": "popeyes"}
    ]
}
```

---

## ⏰ P2: Temporal Validation

**Location:** `app/pipelines/vision_llm.py:validate_temporal_logic()`

### What it checks:

1. **Future Date Detection**
   - Receipt date cannot be in the future
   - Severity: HIGH (fraud signal)

2. **Old Receipt Detection**
   - Receipts older than 2 years flagged
   - Severity: LOW (warning only)

3. **Operating Hours Check**
   - Transaction time vs merchant operating hours
   - Uses `typical_hours_open/close` from merchant context
   - Severity: MEDIUM (warning)

### Date Parsing

Supports multiple formats:
- `MM/DD/YY`, `MM/DD/YYYY`
- `DD/MM/YY`, `DD/MM/YYYY`
- `YYYY-MM-DD`

### Output

```json
{
    "is_valid": true,
    "warnings": [
        {"type": "OLD_DATE", "date": "6/13/2023", "message": "Receipt date is over 2 years old"}
    ],
    "errors": [
        {"type": "FUTURE_DATE", "date": "01/29/2027", "severity": "HIGH"}
    ]
}
```

---

## 📋 P3: Receipt Template Fingerprinting

### Database Schema

**Table:** `receipt_templates` in `app/data/geo.sqlite`

```sql
CREATE TABLE receipt_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_name_norm TEXT NOT NULL,
    template_version TEXT DEFAULT 'v1',
    header_pattern TEXT,
    footer_pattern TEXT,
    logo_position TEXT,
    field_order TEXT,
    date_format TEXT,
    time_format TEXT,
    currency_symbol_position TEXT,
    tax_label_pattern TEXT,
    total_label_pattern TEXT,
    address_lines INTEGER,
    typical_width_chars INTEGER,
    typical_line_count INTEGER,
    font_style TEXT,
    separator_style TEXT,
    structural_hash TEXT,
    confidence_threshold REAL DEFAULT 0.7,
    sample_count INTEGER DEFAULT 1,
    last_updated TEXT,
    notes TEXT
)
```

### Seed Templates (7 merchants)

| Merchant | Date Format | Currency Pos | Tax Pattern | Separator |
|----------|-------------|--------------|-------------|-----------|
| popeyes | MM/DD/YY | prefix ($) | TAX\|SALES TAX | dashes |
| mcdonald | MM/DD/YYYY | prefix | TAX | equals |
| starbucks | MM/DD/YY | prefix | TAX | spaces |
| zaffran | DD/MM/YY | suffix (₹) | CGST\|SGST\|GST | dashes |
| pizza hut | DD/MM/YYYY | suffix | CGST\|SGST | asterisks |
| walmart | MM/DD/YY | prefix | TAX\|TX | spaces |
| shell | MM/DD/YYYY | prefix | TAX | dashes |

### Template Validation

**Location:** `app/pipelines/vision_llm.py:validate_template_fingerprint()`

**What it checks:**

1. **Header Pattern Match**
   - Regex match against merchant header (e.g., `POPEYES|LOUISIANA KITCHEN`)

2. **Tax Label Pattern Match**
   - Tax names match expected patterns (e.g., `CGST|SGST|GST` for India)

3. **Date Format Consistency**
   - Date format matches expected (MM/DD/YY vs DD/MM/YY)

4. **Currency Position**
   - Prefix ($X.XX) vs Suffix (X.XX ₹) based on currency

### Match Score Calculation

```python
match_score = checks_passed / checks_total

if match_score < confidence_threshold:
    result["is_valid"] = False
    result["errors"].append({"type": "TEMPLATE_MISMATCH", ...})
```

### Output

```json
{
    "is_valid": true,
    "template_found": true,
    "template_match_score": 1.0,
    "template": {
        "merchant_name": "popeyes",
        "version": "v1",
        "date_format": "MM/DD/YY",
        ...
    },
    "warnings": [],
    "errors": []
}
```

---

## 🚨 Fraud Signals & Warnings

### Signal Types

| Type | Severity | Source | Description |
|------|----------|--------|-------------|
| TOTAL_MISMATCH | HIGH | Math | Subtotal + tax ≠ total |
| SUBTOTAL_MISMATCH | HIGH | Math | Sum of items ≠ subtotal |
| SUSPICIOUSLY_HIGH_PRICE | HIGH | P1 | Item price exceeds threshold |
| TAX_COUNTRY_MISMATCH | MEDIUM | P1 | Tax type doesn't match country |
| FORBIDDEN_ITEM_FOUND | HIGH | P2 | Item not expected at merchant |
| CURRENCY_MISMATCH | MEDIUM | P2 | Currency not expected at merchant |
| FUTURE_DATE | HIGH | P2 | Receipt date in future |
| OUTSIDE_HOURS | MEDIUM | P2 | Transaction outside operating hours |
| TEMPLATE_MISMATCH | HIGH | P3 | Structure doesn't match template |
| HEADER_PATTERN_MISMATCH | MEDIUM | P3 | Header doesn't match expected |

### Suspicion Determination

```python
is_suspicious = (
    not verification["is_math_correct"] or
    not price_check["is_plausible"] or
    not semantic_check["is_consistent"] or
    not merchant_check["is_valid"] or
    not temporal_check["is_valid"] or
    not template_check["is_valid"]
)
```

---

## 🧪 Testing

### Test Script

```bash
python test_semantic.py
```

### Sample Output

```
============================================================
Testing Hybrid Vision LLM with P1+P2+P3 Semantic Validation
============================================================

--- Popeyes (Fraud) ---
Merchant: Popeyes
Total: USD 88.89

📊 Validation Results:
  P1 Price Plausible: True
  P1 Semantic Consistent: True
  P2 Merchant Context Valid: True (found: True)
  P2 Temporal Valid: True
  P3 Template Valid: True (found: True, score: 100%)

🚨 Fraud Signals (1):
  - TOTAL_MISMATCH: $13.05

🔍 Overall: SUSPICIOUS
  Failed: math_failed
```

### API Endpoint

```bash
curl -X POST http://localhost:8000/analyze/hybrid \
  -F "file=@receipt.png"
```

---

## 📁 File Structure

```
app/
├── pipelines/
│   └── vision_llm.py          # All validation functions
│       ├── validate_price_plausibility()      # P1
│       ├── validate_cross_field_semantics()   # P1
│       ├── validate_merchant_context()        # P2
│       ├── validate_temporal_logic()          # P2
│       ├── validate_template_fingerprint()    # P3
│       └── hybrid_extract_and_verify()        # Main entry
├── geo/
│   ├── db.py                  # Query functions
│   │   ├── query_merchant_context()
│   │   ├── query_receipt_template()
│   │   └── list_all_templates()
│   └── bootstrap.py           # Schema & seed data
│       ├── merchant_context table
│       ├── receipt_templates table
│       ├── _get_seed_merchant_context()
│       └── _get_seed_receipt_templates()
└── data/
    └── geo.sqlite             # SQLite database
```

---

## 🔧 Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VISION_MODEL` | `qwen2.5vl:32b` | Ollama vision model |
| `HYBRID_VISION` | `true` | Enable hybrid pipeline |

### Bootstrap Database

```bash
python -c "from app.geo.bootstrap import bootstrap_geo_db; bootstrap_geo_db()"
```

---

## 🚀 Extending the System

### Add New Merchant Context

```python
# In _get_seed_merchant_context()
("new_merchant", "alias1,alias2", "restaurant", "US",
 "burger,fries,drink", "electronics,fuel",
 5.0, 100.0, 10, 22, False, "USD", "Sales Tax", "Notes"),
```

### Add New Template

```python
# In _get_seed_receipt_templates()
("new_merchant", "v1",
 r"HEADER_PATTERN",
 r"FOOTER_PATTERN",
 "top_center",
 "merchant,items,subtotal,tax,total",
 "MM/DD/YY",
 "HH:MM AM/PM",
 "prefix",
 r"TAX",
 r"TOTAL",
 2, 40, 25, "dashes", "hash_v1",
 "Description"),
```

### Re-bootstrap After Changes

```bash
rm app/data/geo.sqlite
python -c "from app.geo.bootstrap import bootstrap_geo_db; bootstrap_geo_db()"
```

---

## 📈 Performance Considerations

- **P1 checks**: ~1ms (in-memory)
- **P2 checks**: ~5ms (SQLite query)
- **P3 checks**: ~2ms (regex matching)
- **Total overhead**: <10ms per receipt

The semantic validation adds minimal latency while significantly improving fraud detection accuracy.
