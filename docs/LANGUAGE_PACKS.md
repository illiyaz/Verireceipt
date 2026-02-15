# Language Packs System v1.1

**Date:** 2026-01-31  
**Status:** 🟢 COMPLETE

---

## Overview

VeriReceipt uses a YAML-based language pack system for multi-language support without hardcoding keywords in the extraction code. This enables:

- **Configurable:** Add new languages without code changes
- **Versioned:** Track language pack updates with semantic versioning
- **Validated:** Pydantic schema ensures data integrity

---

## Supported Languages

| Language | Pack ID | Scripts | Status |
|----------|---------|---------|--------|
| English | `en` | Latin | ✅ |
| Arabic | `ar` | Arabic | ✅ |
| Chinese | `zh` | Han | ✅ |
| Japanese | `ja` | Hiragana, Katakana, Kanji | ✅ |
| Korean | `ko` | Hangul | ✅ |
| Thai | `th` | Thai | ✅ |
| Malay | `ms` | Latin | ✅ |
| Vietnamese | `vi` | Latin | ✅ |
| German | `de` | Latin | ✅ |

---

## Keyword Categories

### Document Profiling
- `doc_titles` - Document title keywords
- `invoice`, `receipt`, `tax_invoice` - Document type keywords
- `ecommerce`, `fuel`, `parking`, `hotel_folio` - Industry keywords
- `utility`, `telecom` - Service type keywords
- `commercial_invoice`, `air_waybill`, `shipping_bill`, `bill_of_lading` - Logistics keywords

### Amount Extraction
- `total` - Total amount keywords
- `subtotal` - Subtotal keywords
- `tax` - Tax keywords
- `date` - Date keywords
- `amount` - Generic amount keywords

### Merchant Extraction (v1.1)
- `business_types` - Business type words (restaurant, hotel, store, clinic)
- `gratitude_phrases` - Footer phrases (thank you, visit again)
- `service_keywords` - Service/fee keywords for rejection logic

### Transaction Details (v1.1)
- `tip_keywords` - Tip/gratuity keywords
- `discount_keywords` - Discount/promo keywords
- `shipping_keywords` - Shipping/delivery keywords
- `payment_methods` - Payment method keywords (cash, card, UPI)
- `phone_keywords` - Contact keywords (phone, tel, mobile)

---

## File Structure

```
resources/langpacks/
├── _schema.yaml      # Human-readable schema documentation
├── common.yaml       # Shared patterns (inherited by all packs)
├── en.yaml           # English
├── ar.yaml           # Arabic
├── zh.yaml           # Chinese
├── ja.yaml           # Japanese
├── ko.yaml           # Korean
├── th.yaml           # Thai
├── ms.yaml           # Malay
├── vi.yaml           # Vietnamese
└── de.yaml           # German

app/pipelines/lang/
├── schema.py         # Pydantic validation schema
├── loader.py         # Pack loading and caching
├── router.py         # Script detection and routing
├── normalizer.py     # Text normalization
└── detect_script.py  # Unicode script detection
```

---

## Usage in Code

### Loading Language Packs

```python
from app.pipelines.lang.loader import LangPackLoader

loader = LangPackLoader()
packs = loader.get_all_packs()  # Returns list of all loaded packs
```

### Using Keywords in Extraction Functions

```python
def _find_tip_amount(lines: List[str], packs=None) -> Optional[float]:
    # Build keywords from language packs + fallback defaults
    tip_keywords = set(["tip", "gratuity", "service charge"])
    if packs:
        for pack in packs:
            if hasattr(pack, 'keywords') and hasattr(pack.keywords, 'tip_keywords'):
                tip_keywords.update([tk.lower() for tk in pack.keywords.tip_keywords])
    
    for line in lines:
        if any(k in line.lower() for k in tip_keywords):
            # Extract amount...
```

---

## Functions Using Language Packs

| Function | Uses Category | Purpose |
|----------|---------------|---------|
| `_looks_like_person_name()` | `business_types` | Reject business names as person names |
| `_looks_like_footer_or_gratitude()` | `gratitude_phrases` | Identify footer lines |
| `_find_tip_amount()` | `tip_keywords` | Extract tip amounts |
| `_find_discount_amount()` | `discount_keywords` | Extract discounts |
| `_find_shipping_amount()` | `shipping_keywords` | Extract shipping costs |
| Service rejection check | `service_keywords` | Reject fee/charge lines |

---

## Adding a New Language Pack

1. **Create YAML file** in `resources/langpacks/{lang_code}.yaml`

2. **Define required fields:**
```yaml
id: "fr"
version: "1.0.0"
name: "French"
scripts: ["Latin"]
locales: ["fr-FR", "fr-CA"]
```

3. **Add keyword groups:**
```yaml
keywords:
  total: ["total", "montant total", "à payer"]
  subtotal: ["sous-total", "sous total"]
  tax: ["taxe", "tva", "tps", "tvq"]
  tip_keywords: ["pourboire", "service"]
  # ... other categories
```

4. **Update loader** if needed (usually automatic)

5. **Run validation:**
```bash
python -c "from app.pipelines.lang.loader import LangPackLoader; LangPackLoader().get_all_packs()"
```

---

## Changelog

### v1.1 (2026-01-31)
- Added 8 new keyword categories for full extraction support
- Updated all 9 language packs with new categories
- Refactored `features.py` functions to use language packs
- Created `extractors/entity_types.py` module

### v1.0 (2026-01-15)
- Initial language pack system
- 9 languages supported
- Document profiling and amount extraction keywords

---

## Testing

```bash
# Validate all language packs load correctly
python -m pytest tests/test_langpacks_contract.py -v

# Run golden merchant tests (uses language packs)
python -m pytest tests/test_golden_merchant_cases.py -v

# Run entity extraction tests
python -m pytest tests/test_tip_entity_v2.py tests/test_discount_entity_v2.py -v
```

---

## Notes

- All functions maintain **English fallback defaults** when packs are not provided
- Keywords are **case-insensitive** (lowercased during matching)
- The loader **caches packs** for performance
- **Pydantic deprecation warnings** for validators are cosmetic (will migrate to v2 style)
