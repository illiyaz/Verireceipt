# Golden Test Suite

Golden tests are reference documents with known-good expected outputs. They prevent regression and validate classification accuracy.

## Test Categories

### POS Restaurant
- `pos_restaurant_india_basic.json` - Indian POS receipt with GST, INR, line items
- `pos_restaurant_us_basic.json` - US POS receipt with sales tax, USD
- `pos_restaurant_uk_basic.json` - UK POS receipt with VAT, GBP

### Invoices
- `tax_invoice_india_gst.json` - Indian tax invoice with GSTIN
- `commercial_invoice_export.json` - Export commercial invoice

### Logistics
- `bill_of_lading_shipping.json` - International shipping BOL
- `air_waybill_freight.json` - Air freight AWB

### Fake Documents
- `fake_canva_receipt.json` - Canva-generated fake receipt
- `fake_edited_total.json` - Receipt with edited total amount
- `fake_spacing_anomaly.json` - Receipt with spacing manipulation

## Running Golden Tests

```bash
# Run all golden tests
python scripts/run_golden_tests.py

# Run specific category
python scripts/run_golden_tests.py --category pos_restaurant

# Run single test
python scripts/run_golden_tests.py --test pos_restaurant_india_basic
```

## Test Structure

Each golden test JSON contains:

```json
{
  "test_id": "unique_identifier",
  "description": "Human-readable description",
  "category": "pos_restaurant|invoice|logistics|fake",
  "region": "IN|US|UK|etc",
  "expected": {
    "doc_family": "TRANSACTIONAL",
    "doc_subtype": "POS_RESTAURANT",
    "doc_intent": "PURCHASE",
    "doc_profile_confidence_min": 0.6,
    "fraud_label": "genuine|suspicious|fake",
    "fraud_score_max": 0.3
  },
  "key_features": {
    "merchant_name": "Description",
    "currency": "INR|USD|etc",
    "gst": "Present|Absent"
  },
  "test_assertions": [
    {
      "field": "doc_subtype_guess",
      "operator": "equals|>=|<=|contains",
      "value": "POS_RESTAURANT"
    }
  ],
  "notes": [
    "Additional context about this test"
  ]
}
```

## Adding New Golden Tests

1. Create JSON spec in `tests/golden/`
2. Place corresponding PDF in `tests/golden/pdfs/`
3. Run test to validate
4. Commit both files

## Regression Prevention

Golden tests are run in CI/CD pipeline. Any changes that break golden tests must be:
- Justified with clear reasoning
- Documented in CHANGELOG
- Reviewed by team

## Current Coverage

- ✅ POS Restaurant (India): 1 test
- ⚠️ POS Restaurant (US): 0 tests (TODO)
- ⚠️ POS Restaurant (UK): 0 tests (TODO)
- ⚠️ Tax Invoice: 0 tests (TODO)
- ⚠️ Logistics: 0 tests (TODO)
- ⚠️ Fake Documents: 0 tests (TODO)

**Target:** 20+ golden tests covering all major document types and regions
