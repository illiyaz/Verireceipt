#!/usr/bin/env python3
"""
Golden tests for amount extraction intelligence:
- Percentage guard (never treat "TAX @ 5%" as total)
- Candidate scoring (prefer currency symbols, comma formatting)
- Arithmetic consistency solver (subtotal + tax ≈ total)
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.pipelines.features import (
    _is_percentage_line,
    _has_currency_symbol,
    _has_comma_formatting,
    _score_amount_candidate,
    _solve_arithmetic_consistency,
    _find_total_line,
    _AMOUNT_REGEX,
    _parse_amount,
    reconcile_amounts,
)
def test_aligned_should_win_when_semantic_below_trust_threshold():
    """Regression: do not override aligned totals with semantic when semantic confidence < 0.65."""
    print("\n" + "=" * 80)
    print("TEST: Aligned Wins When Semantic Below Trust Threshold")
    print("=" * 80)

    aligned_amounts = {
        "hit": True,
        "total_amount": 70000.0,
        "subtotal_amount": 66667.0,
        "tax_amount": 3333.0,
        "alignment_confidence": 0.75,
        "labels_found": ["SUBTOTAL", "TAX", "TOTAL"],
        "amounts_found": [66667.0, 3333.0, 70000.0],
        "notes": [
            "Found AMOUNT header at line 0",
            "Aligned 3 amounts to labels: {'SUBTOTAL': 66667.0, 'TAX': 3333.0, 'TOTAL': 70000.0}",
        ],
    }

    # Semantic proposes a conflicting total, but confidence is below trust threshold (0.65)
    semantic_amounts = {"total_amount": 2420.0, "confidence": 0.644}

    rec = reconcile_amounts(
        regex_total=None,
        regex_total_line=None,
        line_item_amounts=[],
        line_items_confidence=0.0,
        tax_amount=5.0,
        semantic_amounts=semantic_amounts,
        ocr_confidence=0.95,
        aligned_amounts=aligned_amounts,
    )

    assert rec.total_amount is not None, "Should produce a total when aligned hit exists"
    assert abs(rec.total_amount - 70000.0) < 0.01, f"Expected aligned total 70000.0, got {rec.total_amount}"
    assert rec.provenance.get("total") in ["aligned_columns", "aligned_confirmed_by_semantic"], (
        f"Expected aligned provenance, got {rec.provenance.get('total')}"
    )

    print(f"✅ Kept aligned total={rec.total_amount:.2f} despite semantic={semantic_amounts['total_amount']} (conf={semantic_amounts['confidence']})")


def test_percentage_line_detection():
    """Test that percentage lines are correctly identified."""
    print("\n" + "=" * 80)
    print("TEST: Percentage Line Detection")
    print("=" * 80)
    
    # Should be detected as percentage lines
    assert _is_percentage_line("TAX @ 5%") == True, "Should detect '@ 5%' as percentage"
    assert _is_percentage_line("Tax Rate: 5%") == True, "Should detect '5%' as percentage"
    assert _is_percentage_line("5 percent tax") == True, "Should detect 'percent' keyword"
    assert _is_percentage_line("GST @ 18") == True, "Should detect '@ 18' as rate indicator"
    
    # Should NOT be detected as percentage lines
    assert _is_percentage_line("Total: 70,000") == False, "Should not detect normal total as percentage"
    assert _is_percentage_line("Subtotal: 66,667") == False, "Should not detect subtotal as percentage"
    assert _is_percentage_line("Tax Amount: $3,333") == False, "Should not detect tax amount as percentage"
    
    print("✅ All percentage detection tests passed")


def test_currency_symbol_detection():
    """Test that currency symbols are correctly identified."""
    print("\n" + "=" * 80)
    print("TEST: Currency Symbol Detection")
    print("=" * 80)
    
    assert _has_currency_symbol("Total: $70,000") == True
    assert _has_currency_symbol("₹66,667") == True
    assert _has_currency_symbol("€1,234.56") == True
    assert _has_currency_symbol("£999.99") == True
    assert _has_currency_symbol("INR 50000") == True
    assert _has_currency_symbol("USD 1234") == True
    
    assert _has_currency_symbol("70000") == False
    assert _has_currency_symbol("Total: 70,000") == False
    
    print("✅ All currency symbol detection tests passed")


def test_comma_formatting_detection():
    """Test that comma-formatted numbers are correctly identified."""
    print("\n" + "=" * 80)
    print("TEST: Comma Formatting Detection")
    print("=" * 80)
    
    assert _has_comma_formatting("70,000") == True
    assert _has_comma_formatting("1,234,567") == True
    assert _has_comma_formatting("Total: 66,667") == True
    
    assert _has_comma_formatting("70000") == False
    assert _has_comma_formatting("1234") == False
    
    print("✅ All comma formatting detection tests passed")


def test_amount_regex_does_not_truncate_plain_digits():
    """Regression test: plain digits like '3333' should parse as 3333.0, not 333.0."""
    print("\n" + "=" * 80)
    print("TEST: Amount Regex Does Not Truncate Plain Digits")
    print("=" * 80)
    
    # Test plain digits (no commas) - should parse as full number
    test_cases = [
        ("3333", 3333.0),
        ("1234", 1234.0),
        ("56789", 56789.0),
        ("999", 999.0),
        ("1000", 1000.0),
    ]
    
    for text, expected in test_cases:
        # Find matches in the text
        matches = list(_AMOUNT_REGEX.finditer(text))
        assert len(matches) > 0, f"Should find amount in '{text}'"
        
        # Parse the first match
        amount_str = matches[0].group(1)
        parsed = _parse_amount(amount_str)
        
        assert abs(parsed - expected) < 0.01, f"Expected {expected}, got {parsed} for '{text}'"
        print(f"   ✅ '{text}' → {parsed:.1f}")
    
    # Test comma-formatted numbers still work
    comma_cases = [
        ("3,333", 3333.0),
        ("12,345", 12345.0),
        ("70,000", 70000.0),
    ]
    
    for text, expected in comma_cases:
        matches = list(_AMOUNT_REGEX.finditer(text))
        assert len(matches) > 0, f"Should find amount in '{text}'"
        
        amount_str = matches[0].group(1)
        parsed = _parse_amount(amount_str)
        
        assert abs(parsed - expected) < 0.01, f"Expected {expected}, got {parsed} for '{text}'"
        print(f"   ✅ '{text}' → {parsed:.1f}")
    
    print("✅ All amount regex regression tests passed")


def test_amount_candidate_scoring():
    """Test that amount candidates are scored correctly."""
    print("\n" + "=" * 80)
    print("TEST: Amount Candidate Scoring")
    print("=" * 80)
    
    # Percentage line without currency should be strongly rejected
    score_pct = _score_amount_candidate(5.0, "TAX @ 5%", is_total_label=False, proximity_to_total=1)
    assert score_pct < -100, f"Percentage line should be rejected, got score={score_pct}"
    print(f"✅ Percentage line rejected: score={score_pct:.1f}")
    
    # Currency symbol should score high
    score_currency = _score_amount_candidate(70000.0, "Total: $70,000", is_total_label=True, proximity_to_total=0)
    assert score_currency > 300, f"Currency + total label should score high, got {score_currency}"
    print(f"✅ Currency symbol + total label: score={score_currency:.1f}")
    
    # Comma formatting should boost score
    score_comma = _score_amount_candidate(70000.0, "Total: 70,000", is_total_label=True, proximity_to_total=0)
    assert score_comma > 250, f"Comma formatting + total label should score high, got {score_comma}"
    print(f"✅ Comma formatting + total label: score={score_comma:.1f}")
    
    # Plain number should score lower
    score_plain = _score_amount_candidate(70000.0, "70000", is_total_label=False, proximity_to_total=3)
    assert score_plain < score_comma, f"Plain number should score lower than formatted"
    print(f"✅ Plain number: score={score_plain:.1f}")
    
    # Small amounts should be penalized
    score_small = _score_amount_candidate(0.5, "0.5", is_total_label=False, proximity_to_total=1)
    assert score_small < 0, f"Small amount should be penalized, got {score_small}"
    print(f"✅ Small amount penalized: score={score_small:.1f}")
    
    print("✅ All candidate scoring tests passed")


def test_arithmetic_consistency_solver():
    """Test that arithmetic consistency solver finds correct combinations."""
    print("\n" + "=" * 80)
    print("TEST: Arithmetic Consistency Solver")
    print("=" * 80)
    
    # Perfect match: 66,667 + 3,333 = 70,000
    result = _solve_arithmetic_consistency(
        total_candidates=[70000.0, 5.0],  # Include the bad "5" from percentage line
        subtotal_candidates=[66667.0],
        tax_candidates=[3333.0],
        epsilon=0.02
    )
    
    assert result is not None, "Should find valid combination"
    subtotal, tax, total, score = result
    assert abs(subtotal - 66667.0) < 0.01, f"Should select subtotal=66667, got {subtotal}"
    assert abs(tax - 3333.0) < 0.01, f"Should select tax=3333, got {tax}"
    assert abs(total - 70000.0) < 0.01, f"Should select total=70000, got {total}"
    assert score < 0.01, f"Error should be very small, got {score}"
    
    print(f"✅ Found correct combination: {subtotal:.2f} + {tax:.2f} = {total:.2f} (error={score:.4f})")
    
    # No valid combination (tax rate too high)
    result_invalid = _solve_arithmetic_consistency(
        total_candidates=[100.0],
        subtotal_candidates=[50.0],
        tax_candidates=[50.0],  # 100% tax rate - invalid
        epsilon=0.02
    )
    
    assert result_invalid is None, "Should reject invalid tax rate"
    print("✅ Correctly rejected invalid tax rate (>30%)")
    
    print("✅ All arithmetic consistency tests passed")


def test_find_total_line_with_percentage_guard():
    """Test that _find_total_line correctly rejects percentage lines."""
    print("\n" + "=" * 80)
    print("TEST: Find Total Line with Percentage Guard")
    print("=" * 80)
    
    # Simulate invoice with percentage trap
    lines = [
        "INVOICE #12345",
        "Subtotal: 66,667",
        "TAX @ 5%",
        "Tax Amount: 3,333",
        "GRAND TOTAL",
        "70,000",
    ]
    
    total_line, total_amount = _find_total_line(lines)
    
    assert total_amount is not None, "Should find a total"
    assert abs(total_amount - 70000.0) < 0.01, f"Should find 70,000 not 5, got {total_amount}"
    
    print(f"✅ Correctly selected total={total_amount:.2f} (not 5 from percentage line)")
    print("✅ Percentage guard working correctly")


def test_find_total_line_with_currency_preference():
    """Test that _find_total_line prefers amounts with currency symbols."""
    print("\n" + "=" * 80)
    print("TEST: Find Total Line with Currency Preference")
    print("=" * 80)
    
    # Simulate invoice with multiple candidates
    lines = [
        "Subtotal",
        "66667",
        "Tax",
        "3333",
        "GRAND TOTAL",
        "$70,000",  # This should win due to currency symbol
    ]
    
    total_line, total_amount = _find_total_line(lines)
    
    assert total_amount is not None, "Should find a total"
    assert abs(total_amount - 70000.0) < 0.01, f"Should prefer $70,000, got {total_amount}"
    
    print(f"✅ Correctly preferred currency-formatted amount: ${total_amount:,.2f}")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("AMOUNT INTELLIGENCE GOLDEN TESTS")
    print("=" * 80)
    
    test_percentage_line_detection()
    test_currency_symbol_detection()
    test_comma_formatting_detection()
    test_amount_regex_does_not_truncate_plain_digits()
    test_amount_candidate_scoring()
    test_arithmetic_consistency_solver()
    test_find_total_line_with_percentage_guard()
    test_find_total_line_with_currency_preference()
    
    print("\n" + "=" * 80)
    print("✅ ALL AMOUNT INTELLIGENCE TESTS PASSED")
    print("=" * 80)
