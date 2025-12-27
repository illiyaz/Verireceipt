# 🌍 Geo-Aware Document Classification System

## Overview

VeriReceipt now uses a **smart, scalable 4-step geo-aware classification system** that automatically detects the language, country, and document type without hardcoded assumptions.

This solves the problem of receipts from different countries (Mexico, US, India, Canada, UAE, etc.) being misclassified due to different:
- Languages (Spanish, English, Hindi, Arabic)
- Tax systems (RFC/IVA, GSTIN/GST, Sales Tax)
- Phone formats (+52, +91, +1)
- Postal codes (C.P., ZIP, PIN)
- Currency symbols ($, ₹, AED)

---

## 🎯 The 4-Step System

### **Step 1: Language Detection** (Fast Heuristic)

**What it does:**
- Analyzes first 1000 characters of document
- Scores keywords and patterns for each language
- Returns language guess with confidence

**Supported Languages:**
- `es` - Spanish (Mexico, Spain, Latin America)
- `en` - English (US, Canada, UK)
- `hi` - Hindi/Indian English mix
- `ar` - Arabic (UAE, Saudi Arabia)

**How it works:**
```python
# Keyword scoring (1 point each)
Spanish: "total", "subtotal", "iva", "gracias", "fecha", "rfc"
English: "total", "tax", "thank", "receipt", "zip", "state"
Hindi/IN: "gstin", "cgst", "sgst", "bill", "upi", "paytm"

# Pattern scoring (3 points each - more reliable)
Spanish: r"\b(gracias por su compra|muchas gracias)\b"
English: r"\bsales tax\b"
Hindi/IN: r"\bgstin\b"
```

**Output:**
```json
{
  "lang_guess": "es",
  "lang_confidence": 0.82,
  "lang_evidence": ["total", "subtotal", "iva", "gracias", "fecha"]
}
```

---

### **Step 2: Country/Region Detection** (Multi-Signal Scoring)

**What it does:**
- Parallel evidence scoring across 5 signal types
- Combines multiple weak signals into strong classification
- Language hint bonus if matches expected language

**5 Signal Types:**

1. **Currency Symbols/Codes** (2 points each)
   - `$` is ambiguous (US/MX/CA) → needs other signals
   - `MXN`, `USD`, `INR`, `₹`, `AED` are strong signals

2. **Tax Keywords** (3 points each - strongest signal)
   - Mexico: `RFC`, `IVA`, `CFDI`, `SAT`, `folio fiscal`
   - US: `sales tax`, `state tax`, `tax rate`
   - India: `GSTIN`, `CGST`, `SGST`, `IGST`, `HSN`, `SAC`
   - UAE: `VAT`, `TRN`, `tax registration`

3. **Phone Patterns** (2 points each)
   - Mexico: `+52 followed by 10 digits`
   - US: `(555) 123-4567` or `555-123-4567`
   - India: `+91 followed by 10 digits` or `[6-9]xxxxxxxxx`

4. **Postal Code Patterns** (2 points each)
   - Mexico: `C.P. 12345` (5 digits, but ambiguous with US)
   - US: `12345` or `12345-6789` (ZIP or ZIP+4)
   - India: `PIN Code: 123456` (6 digits)

5. **Location Markers** (1 point each)
   - Mexico: `CDMX`, `Guadalajara`, `Monterrey`, `Col.`, `Delegación`
   - US: `CA`, `TX`, `NY`, `ZIP`, `State`
   - India: `Mumbai`, `Delhi`, `Bangalore`, `Nagar`, `Road`

**Language Hint Bonus:** +5 points if detected language matches expected language for country

**Confidence Calculation:**
```python
confidence = min(1.0, winner_score / max(10, total_score))
if winner_score >= 10:
    confidence += 0.2  # Boost for strong signals
```

**Output:**
```json
{
  "geo_country_guess": "MX",
  "geo_confidence": 0.84,
  "geo_evidence": [
    "tax:rfc",
    "tax:iva",
    "postal:C.P. 06000",
    "location:cdmx",
    "lang_match:es"
  ],
  "geo_scores": {
    "MX": 15,
    "US": 3,
    "IN": 0
  }
}
```

---

### **Step 3: Geo-Aware Document Subtype Detection**

**What it does:**
- Uses country-specific keyword sets for each document subtype
- Adjusts confidence based on geo confidence
- Returns document family and subtype

**Country-Specific Keywords:**

**Mexico (MX):**
```python
"POS_RESTAURANT": ["restaurante", "mesero", "propina", "mesa", "comida"]
"TAX_INVOICE": ["factura", "rfc", "cfdi", "folio fiscal", "sat"]
"FUEL": ["gasolina", "diesel", "combustible", "litros"]
```

**United States (US):**
```python
"POS_RESTAURANT": ["restaurant", "server", "tip", "gratuity", "table"]
"TAX_INVOICE": ["invoice", "tax id", "ein", "bill to"]
"HOTEL_FOLIO": ["hotel", "room", "night", "check-in", "folio"]
```

**India (IN):**
```python
"POS_RESTAURANT": ["restaurant", "hotel", "bill", "waiter", "table"]
"TAX_INVOICE": ["tax invoice", "gstin", "hsn", "sac", "bill of supply"]
"TELECOM": ["mobile", "recharge", "plan", "data"]
```

**Confidence Calculation:**
```python
base_confidence = min(1.0, keyword_matches / 5.0)
final_confidence = base_confidence * (0.5 + 0.5 * geo_confidence)
```

**Output:**
```json
{
  "doc_family_guess": "TRANSACTIONAL",
  "doc_subtype_guess": "POS_RESTAURANT",
  "doc_profile_confidence": 0.67,
  "doc_profile_evidence": ["restaurante", "mesero", "propina"]
}
```

---

### **Step 4: Country-Specific Feature Extraction**

**What it does:**
- Runs only the extractor for the detected country (scalable!)
- Extracts country-specific fields using regex patterns
- Returns structured data for downstream validation

**Mexico (MX) Extractor:**
```python
mx_rfc: r'\b[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}\b'  # ABC123456XYZ
mx_iva_rate: r'iva\s*:?\s*(\d+(?:\.\d+)?)\s*%?'  # 16%
mx_postal_code: r'C\.?P\.?\s*(\d{5})'  # C.P. 06000
mx_phone: r'\+?52[\s\-]?(\d{10})'  # +52 55 1234 5678
```

**US Extractor:**
```python
us_zip_code: r'\b(\d{5}(?:-\d{4})?)\b'  # 94102 or 94102-1234
us_state: r'\b([A-Z]{2})\s+\d{5}\b'  # CA 94102
us_ein: r'\b\d{2}-\d{7}\b'  # 12-3456789
us_phone: r'\((\d{3})\)\s*(\d{3})[-\s]?(\d{4})'  # (415) 555-1234
```

**India (IN) Extractor:**
```python
in_gstin: r'\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b'  # 15 chars
in_pin_code: r'\bpin\s*code?\s*:?\s*(\d{6})\b'  # PIN Code: 123456
in_hsn_code: r'\bhsn\s*code?\s*:?\s*(\d{4,8})\b'  # HSN Code: 1234
in_phone: r'\+?91[\s\-]?([6-9]\d{9})'  # +91 9876543210
```

**Output:**
```json
{
  "geo_specific_features": {
    "mx_rfc": "ABC123456XYZ",
    "mx_iva_rate": 16.0,
    "mx_postal_code": "06000",
    "mx_phone": "5512345678"
  }
}
```

---

## 🔧 Integration

### **In Features Pipeline**

The geo-aware system is integrated into `build_features()`:

```python
from app.pipelines.geo_detection import detect_geo_and_profile

# In build_features()
geo_profile = detect_geo_and_profile(full_text, lines)

# Results added to text_features
text_features.update({
    "lang_guess": geo_profile.get("lang_guess"),
    "lang_confidence": geo_profile.get("lang_confidence"),
    "geo_country_guess": geo_profile.get("geo_country_guess"),
    "geo_confidence": geo_profile.get("geo_confidence"),
    "geo_evidence": geo_profile.get("geo_evidence"),
})

# Geo-specific features (MX RFC, US ZIP, IN GSTIN, etc.)
text_features.update(geo_profile.get("geo_specific_features", {}))
```

### **In Ensemble Audit Trail**

Geo information is included in `ENS_DOC_PROFILE_TAGS` events:

```json
{
  "code": "ENS_DOC_PROFILE_TAGS",
  "evidence": {
    "doc_family": "TRANSACTIONAL",
    "doc_subtype": "POS_RESTAURANT",
    "doc_profile_confidence": 0.67,
    "lang_guess": "es",
    "lang_confidence": 0.82,
    "geo_country_guess": "MX",
    "geo_confidence": 0.84
  }
}
```

---

## 📊 Example Results

### **Mexico Restaurant Receipt**

**Input:**
```
RESTAURANTE LA COCINA
RFC: ABC123456XYZ
Sucursal Centro
Gracias por su compra

Fecha: 15/12/2023
Ticket: 12345

Subtotal: $250.00
IVA (16%): $40.00
Total: $290.00

C.P. 06000
CDMX, México
Tel: +52 55 1234 5678
```

**Output:**
```json
{
  "lang_guess": "es",
  "lang_confidence": 0.82,
  "geo_country_guess": "MX",
  "geo_confidence": 0.84,
  "doc_family_guess": "TRANSACTIONAL",
  "doc_subtype_guess": "POS_RESTAURANT",
  "doc_profile_confidence": 0.67,
  "geo_specific_features": {
    "mx_rfc": "ABC123456XYZ",
    "mx_postal_code": "06000"
  }
}
```

### **US Coffee Shop Receipt**

**Input:**
```
STARBUCKS COFFEE
Store #12345
123 Main Street
San Francisco, CA 94102

Date: 12/15/2023
Receipt: 98765

Subtotal: $15.50
Sales Tax (8.5%): $1.32
Total: $16.82

Thank you for your visit!
Phone: (415) 555-1234
```

**Output:**
```json
{
  "lang_guess": "en",
  "lang_confidence": 0.56,
  "geo_country_guess": "US",
  "geo_confidence": 0.74,
  "doc_family_guess": "TRANSACTIONAL",
  "doc_subtype_guess": "POS_RETAIL",
  "doc_profile_confidence": 0.52,
  "geo_specific_features": {
    "us_zip_code": "94102",
    "us_state": "CA",
    "us_phone": "(415) 555-1234"
  }
}
```

---

## 🚀 Benefits

### **1. No Hardcoded Assumptions**
- System adapts to any country automatically
- No more "assume US if $ symbol" logic

### **2. Scalable Architecture**
- Add new countries by adding to `GEO_SIGNALS` dict
- Add new languages by adding to `LANGUAGE_MARKERS` dict
- Country-specific extractors are modular

### **3. Multi-Signal Robustness**
- Single weak signal (like `$`) won't misclassify
- Combines language + tax + phone + postal + location
- Confidence reflects signal strength

### **4. Handles Ambiguity**
- `$` could be US, MX, or CA → uses other signals
- `5-digit postal code` could be US ZIP or MX C.P. → checks for "C.P." prefix
- Generic keywords like "total" → language detection helps

### **5. Audit Trail Transparency**
- Every classification includes evidence list
- Geo scores show why a country was chosen
- Debugging is straightforward

---

## 🧪 Testing

### **Test Language Detection**
```python
from app.pipelines.geo_detection import _detect_language

result = _detect_language("Gracias por su compra. Total: $100. IVA: 16%")
# Returns: {"lang_guess": "es", "lang_confidence": 0.8, ...}
```

### **Test Geo Detection**
```python
from app.pipelines.geo_detection import _detect_geo_country

result = _detect_geo_country("RFC: ABC123 IVA: 16% C.P. 06000 CDMX", lang_hint="es")
# Returns: {"geo_country_guess": "MX", "geo_confidence": 0.85, ...}
```

### **Test Full Pipeline**
```python
from app.pipelines.geo_detection import detect_geo_and_profile

text = "Your receipt text here..."
result = detect_geo_and_profile(text, text.split('\n'))
# Returns: Complete geo profile with all 4 steps
```

---

## 📝 Adding a New Country

To add support for a new country (e.g., Brazil):

1. **Add to `LANGUAGE_MARKERS`** (if new language):
```python
"pt": {  # Portuguese
    "keywords": ["total", "subtotal", "obrigado", "data", "recibo"],
    "patterns": [r"\bobrigado\b"],
}
```

2. **Add to `GEO_SIGNALS`**:
```python
"BR": {  # Brazil
    "currency": ["brl", "r$", "real"],
    "tax_keywords": ["cnpj", "icms", "nota fiscal"],
    "phone_patterns": [r"\+55[\s\-]?\d{10,11}"],
    "postal_patterns": [r"\b\d{5}-\d{3}\b"],  # CEP format
    "location_markers": ["são paulo", "rio", "brasília"],
    "language_hint": "pt",
}
```

3. **Add to `GEO_SUBTYPE_KEYWORDS`**:
```python
"BR": {
    "POS_RESTAURANT": ["restaurante", "garçom", "gorjeta"],
    "TAX_INVOICE": ["nota fiscal", "cnpj", "icms"],
}
```

4. **Create extractor function**:
```python
def extract_br_specific(text: str) -> Dict[str, Any]:
    features = {}
    # CNPJ (14 digits)
    cnpj_pattern = r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b'
    cnpj_match = re.search(cnpj_pattern, text)
    if cnpj_match:
        features["br_cnpj"] = cnpj_match.group(0)
    return features
```

5. **Add to `extract_geo_specific_features()`**:
```python
elif geo_country == "BR":
    return extract_br_specific(text)
```

Done! The system now supports Brazil.

---

## 🎓 Key Takeaways

1. **Language detection first** - Fast heuristic sets the stage
2. **Multi-signal geo detection** - Parallel scoring is robust
3. **Geo-aware subtypes** - Country-specific keywords improve accuracy
4. **Modular extractors** - Only run what's needed, easy to extend
5. **Evidence tracking** - Full audit trail for debugging

This system scales to any number of countries without touching existing code. Just add new signal definitions and extractors.
