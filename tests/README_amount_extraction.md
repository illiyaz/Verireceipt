# Amount Extraction Tests

This directory contains comprehensive tests for the amount extraction functionality in VeriReceipt.

## 🧪 Test Files

### `test_amount_extraction_golden.py`
**Golden tests that should never regress**

These tests lock in the core functionality of the `_pick_largest_amount` function and ensure it always extracts the largest amount from various currency formats.

**Golden Cases:**
- `"Total S15,600.00"` → `15600.0`
- `"TOTAL USD 1,234.56"` → `1234.56`
- `"Grand Total: ₹12,34,567.89"` → `1234567.89`

**Additional Test Cases:**
- Multiple amounts - picks largest
- Safety guard - filters amounts ≤ 1.0
- Edge cases - no amounts, only small amounts

### `test_amount_extraction_integration.py`
**Quick integration test**

Verifies the amount extraction works end-to-end with the actual codebase.

## 🚀 Running Tests

```bash
# Run golden tests (comprehensive)
python tests/test_amount_extraction_golden.py

# Run integration test (quick)
python tests/test_amount_extraction_integration.py
```

## 🔒 Safety Features

### Safety Guard
The implementation includes a safety guard that filters out amounts ≤ 1.0 before selecting the maximum:

```python
# Safety guard: filter out amounts <= 1.0 (likely not real totals)
amounts = [a for a in amounts if a > 1.0]
```

This prevents small values like "0.99" or "1.50" from being selected as totals when larger amounts are present.

### Largest Amount Strategy
The function uses `max(amounts)` instead of picking the last match, ensuring the largest monetary value is always selected.

## 🌍 Currency Support

The regex supports multiple currency formats:
- **USD/International**: `1,234.56`
- **Indian Lakhs**: `12,34,567.89`
- **Prefixes**: `$`, `₹`, `S`, `rs`, `inr`

## 🎯 Key Changes Made

1. **Regex Strategy**: Changed from "last match" to "largest amount"
2. **Enhanced Regex**: Updated to handle Indian lakh format `(?:,[0-9]{2,3})*`
3. **Safety Guard**: Added filter for amounts > 1.0
4. **Golden Tests**: Locked functionality with comprehensive test suite

## 📊 Test Results

All tests should pass:
```
🎉 ALL GOLDEN TESTS PASSED!
✅ Amount extraction is locked and working correctly
```

If any test fails, fix the issue before committing - these are regression tests that protect core functionality.
