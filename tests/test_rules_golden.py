"""
Golden tests for geo/currency/tax validation rules.

These are lightweight, deterministic "golden" test cases for the highest-signal
fraud patterns. They intentionally test rule *behavior* using the smallest
possible surface area (mostly pure helpers) so they stay stable across refactors.

Running:
    python -m pytest tests/test_rules_golden.py -v

Coverage:
    - Currency mismatch detection (strict geos)
    - Tax regime mismatch detection
    - Cross-border soft behavior
    - Travel/hospitality softener
    - Merchant-currency plausibility
    - Positive controls (matching geo/currency/tax)
    - Edge cases (weak signals, no geo)
"""

import pytest
from typing import List, Dict, Any, Optional

from app.pipelines.rules import (
    _geo_currency_tax_consistency,
    RuleEvent,
)


# -----------------------------------------------------------------------------
# Test helpers
# -----------------------------------------------------------------------------

def _run_geo_rule(text: str, merchant: Optional[str] = None) -> List[str]:
    """Run only geo/currency/tax consistency + merchant-currency plausibility.

    Returns list of emitted rule_ids.
    """
    events: List[RuleEvent] = []
    reasons: List[str] = []
    minor_notes: List[str] = []

    _geo_currency_tax_consistency(
        text=text,
        merchant=merchant,
        reasons=reasons,
        minor_notes=minor_notes,
        events=events,
    )
    return [e.rule_id for e in events]


def _assert_any_rule(rule_ids: List[str], expected: str) -> None:
    assert expected in rule_ids, f"Expected rule_id={expected} in {rule_ids}"


def _assert_no_rule(rule_ids: List[str], unexpected: str) -> None:
    assert unexpected not in rule_ids, f"Did not expect rule_id={unexpected} in {rule_ids}"


# -----------------------------------------------------------------------------
# Golden test cases (20 cases)
# -----------------------------------------------------------------------------

_GOLDEN_FRAUD_CASES: List[Dict[str, Any]] = [
    # --- Currency mismatch (strict geos) ---
    {
        "name": "US_geo_EUR_currency_mismatch",
        "text": "New York, NY 10001\nTotal: €88.00\nSales Tax 8.25%\n",
        "merchant": "Generic Store",
        "must_include": ["GEO_CURRENCY_MISMATCH"],
        "must_exclude": [],
    },
    {
        "name": "IN_geo_USD_currency_mismatch",
        "text": "Bengaluru Karnataka 560001\nGSTIN 29ABCDE1234F1Z5\nTotal: $42.10\nGST 18%\n",
        "merchant": "Local Mart",
        "must_include": ["GEO_CURRENCY_MISMATCH"],
        "must_exclude": [],
    },
    {
        "name": "CA_geo_USD_currency_mismatch",
        "text": "Toronto ON M5V 2T6\nTotal: $120.00\nHST 13%\n",
        "merchant": "Downtown Cafe",
        "must_include": ["GEO_CURRENCY_MISMATCH"],
        "must_exclude": [],
    },

    # --- Tax regime mismatch ---
    {
        "name": "US_geo_VAT_tax_mismatch",
        "text": "California CA\nVAT 20%\nTotal: $10.00\n",
        "merchant": "Some Shop",
        "must_include": ["GEO_TAX_MISMATCH"],
        "must_exclude": [],
    },
    {
        "name": "UK_geo_SALES_TAX_tax_mismatch",
        "text": "London United Kingdom\nSales Tax 7%\nTotal: £9.99\n",
        "merchant": "Corner Shop",
        "must_include": ["GEO_TAX_MISMATCH"],
        "must_exclude": [],
    },
    {
        "name": "IN_geo_VAT_tax_mismatch",
        "text": "Hyderabad Telangana 500081\nVAT 5%\nTotal: ₹499.00\nGSTIN 36ABCDE1234F1Z5\n",
        "merchant": "Electronics",
        "must_include": ["GEO_TAX_MISMATCH"],
        "must_exclude": [],
    },

    # --- Cross-border soft behavior ---
    {
        "name": "cross_border_multi_geo_no_geo_penalty",
        "text": "New York NY\nToronto ON\nTotal: $20.00\n",
        "merchant": "Travel Vendor",
        "must_include": ["GEO_CROSS_BORDER_HINTS"],
        "must_exclude": ["GEO_CURRENCY_MISMATCH", "GEO_TAX_MISMATCH"],
    },
    {
        "name": "no_geo_detected_only_info",
        "text": "Thank you for your purchase\nTotal: $19.99\n",
        "merchant": "Unknown",
        "must_include": ["GEO_NO_REGION_HINT"],
        "must_exclude": ["GEO_CURRENCY_MISMATCH", "GEO_TAX_MISMATCH"],
    },

    # --- Travel softener ---
    {
        "name": "travel_softener_downgrades_geo",
        "text": "Hotel Booking\nCheck-in\nLondon United Kingdom\nTotal: $200.00\nVAT 20%\n",
        "merchant": "Hotel",
        "must_include": ["GEO_CURRENCY_MISMATCH", "GEO_TRAVEL_SOFTENER"],
        "must_exclude": [],
    },

    # --- Merchant–currency plausibility flags should always run ---
    {
        "name": "us_healthcare_with_cad_no_canada_hints",
        "text": "Hospital Billing Statement\nNew York NY\nTotal: CAD 120.00\n",
        "merchant": "St. Mary Hospital",
        "must_include": ["MERCHANT_CURRENCY_IMPLAUSIBLE"],
        "must_exclude": [],
    },
    {
        "name": "us_healthcare_with_inr_no_india_hints",
        "text": "Clinic Invoice\nCalifornia CA\nTotal: INR 5000\n",
        "merchant": "Sunrise Medical Clinic",
        "must_include": ["MERCHANT_CURRENCY_IMPLAUSIBLE"],
        "must_exclude": [],
    },

    # --- Canada hints suppress the US-healthcare CAD implausible rule (by design) ---
    {
        "name": "us_healthcare_with_cad_with_canada_hints_not_implausible",
        "text": "Hospital\nToronto ON M5V 2T6\nTotal: CAD 120.00\nHST 13%\n",
        "merchant": "Hospital",
        "must_include": [],
        "must_exclude": ["MERCHANT_CURRENCY_IMPLAUSIBLE"],
    },

    # --- Positive controls: matching geo/currency/tax should not emit mismatch ---
    {
        "name": "US_geo_USD_sales_tax_ok",
        "text": "Seattle WA\nSales Tax 10%\nTotal: $15.00\n",
        "merchant": "Store",
        "must_include": [],
        "must_exclude": ["GEO_CURRENCY_MISMATCH", "GEO_TAX_MISMATCH"],
    },
    {
        "name": "IN_geo_INR_gst_ok",
        "text": "Bengaluru Karnataka 560001\nGST 18%\nTotal: ₹250.00\nGSTIN 29ABCDE1234F1Z5\n",
        "merchant": "Shop",
        "must_include": [],
        "must_exclude": ["GEO_CURRENCY_MISMATCH", "GEO_TAX_MISMATCH"],
    },
    {
        "name": "CA_geo_CAD_hst_ok",
        "text": "Vancouver BC\nHST 13%\nTotal: CAD 19.00\n",
        "merchant": "Cafe",
        "must_include": [],
        "must_exclude": ["GEO_CURRENCY_MISMATCH", "GEO_TAX_MISMATCH"],
    },
    {
        "name": "UK_geo_GBP_vat_ok",
        "text": "London UK\nVAT 20%\nTotal: £9.99\n",
        "merchant": "Shop",
        "must_include": [],
        "must_exclude": ["GEO_CURRENCY_MISMATCH", "GEO_TAX_MISMATCH"],
    },

    # --- Edge cases: avoid false positives when signals are weak ---
    {
        "name": "weak_geo_signal_no_penalty",
        "text": "Receipt\nTotal: 10.00\n",
        "merchant": "Shop",
        "must_include": [],
        "must_exclude": ["GEO_CURRENCY_MISMATCH", "GEO_TAX_MISMATCH"],
    },

    # --- VAT keyword in generic text without geo should not produce mismatch ---
    {
        "name": "vat_without_geo_info_only",
        "text": "VAT included\nTotal: 19.99\n",
        "merchant": "Unknown",
        "must_include": ["GEO_NO_REGION_HINT"],
        "must_exclude": ["GEO_TAX_MISMATCH"],
    },

    # --- Multiple-region case should still emit cross-border info ---
    {
        "name": "multi_geo_emits_cross_border_info",
        "text": "New York NY\nToronto ON\nTotal: CAD 120.00\n",
        "merchant": "Vendor",
        "must_include": ["GEO_CROSS_BORDER_HINTS"],
        "must_exclude": [],
    },

    # --- UAE AED sanity: ensure no mismatch when currency matches ---
    {
        "name": "UAE_geo_AED_ok",
        "text": "Dubai UAE\nVAT 5%\nTotal: AED 100.00\n+971\n",
        "merchant": "Restaurant",
        "must_include": [],
        "must_exclude": ["GEO_CURRENCY_MISMATCH"],
    },

    # --- Canada GST ok ---
    {
        "name": "CA_geo_gst_ok",
        "text": "Canada\nGST 5%\nTotal: CAD 40.00\n",
        "merchant": "Store",
        "must_include": [],
        "must_exclude": ["GEO_TAX_MISMATCH"],
    },
]


# -----------------------------------------------------------------------------
# Parametrized test
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("case", _GOLDEN_FRAUD_CASES, ids=[c["name"] for c in _GOLDEN_FRAUD_CASES])
def test_golden_fraud_patterns(case: Dict[str, Any]) -> None:
    """Test golden fraud patterns for geo/currency/tax validation.
    
    Each case tests a specific fraud pattern or positive control:
    - Currency mismatches (e.g., EUR in US, USD in India)
    - Tax regime mismatches (e.g., VAT in US, Sales Tax in UK)
    - Cross-border behavior (multiple geos detected)
    - Travel softener (hotels/flights with geo mismatches)
    - Merchant-currency plausibility (US healthcare with CAD/INR)
    - Positive controls (matching geo/currency/tax)
    - Edge cases (weak signals, no geo detected)
    """
    rule_ids = _run_geo_rule(case["text"], merchant=case.get("merchant"))

    # Assert must_include rules are present
    for rid in case.get("must_include", []) or []:
        _assert_any_rule(rule_ids, rid)

    # Assert must_exclude rules are NOT present
    for rid in case.get("must_exclude", []) or []:
        _assert_no_rule(rule_ids, rid)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
