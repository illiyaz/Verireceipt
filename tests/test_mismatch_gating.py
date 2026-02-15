"""
Unit tests for gated mismatch signaling.

Tests the "signal always, penalty gated" pattern where mismatch signals
are always emitted but penalties are only applied when support confidence is high.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.pipelines.features import reconcile_amounts, _compute_mismatch_signal


def test_mismatch_unknown_no_items():
    """
    Case A: final_total=525000, items_sum=None
    Expected: mismatch_strength=UNKNOWN, applied_to_score=False, gated_reason=insufficient_components
    """
    class MockSemanticAmounts:
        def __init__(self):
            self.total_amount = 525000.0
            self.confidence = 0.63
    
    result = reconcile_amounts(
        regex_total=None,
        regex_total_line=None,
        line_item_amounts=[],
        line_items_confidence=0.0,
        tax_amount=None,
        semantic_amounts=MockSemanticAmounts(),
        ocr_confidence=None,
        aligned_amounts=None
    )
    
    assert result.provenance["mismatch_strength"] == "UNKNOWN", f"Expected UNKNOWN, got {result.provenance['mismatch_strength']}"
    assert result.provenance["mismatch_applied_to_score"] == False, "Expected applied_to_score=False"
    assert result.provenance["mismatch_gated_reason"] == "insufficient_components", f"Expected insufficient_components, got {result.provenance['mismatch_gated_reason']}"
    assert result.provenance["mismatch_computable"] == False, "Expected mismatch_computable=False"
    
    print("✅ test_mismatch_unknown_no_items PASSED")
    print(f"   Strength: {result.provenance['mismatch_strength']}")
    print(f"   Applied to score: {result.provenance['mismatch_applied_to_score']}")
    print(f"   Gated reason: {result.provenance['mismatch_gated_reason']}")


def test_mismatch_strong_high_support():
    """
    Case B: final_total=525000, items_sum=25000, tax=0
    Expected: mismatch_ratio≈0.91, strength=STRONG, applied_to_score=True (high support)
    """
    result = reconcile_amounts(
        regex_total=525000.0,
        regex_total_line="TOTAL: 525000",
        line_item_amounts=[10000.0, 15000.0],
        line_items_confidence=0.9,
        tax_amount=0.0,
        semantic_amounts=None,
        ocr_confidence=0.85,
        aligned_amounts=None
    )
    
    assert result.provenance["mismatch_strength"] == "STRONG", f"Expected STRONG, got {result.provenance['mismatch_strength']}"
    assert result.provenance["mismatch_applied_to_score"] == True, "Expected applied_to_score=True"
    assert result.provenance["mismatch_computable"] == True, "Expected mismatch_computable=True"
    assert result.provenance["mismatch_ratio"] is not None, "Expected mismatch_ratio to be computed"
    assert result.provenance["mismatch_ratio"] > 0.15, f"Expected ratio > 0.15, got {result.provenance['mismatch_ratio']}"
    
    # Check support breakdown
    support = result.provenance["mismatch_support"]
    assert support["overall_support"] >= 0.65, f"Expected overall_support >= 0.65, got {support['overall_support']}"
    
    print("✅ test_mismatch_strong_high_support PASSED")
    print(f"   Strength: {result.provenance['mismatch_strength']}")
    print(f"   Ratio: {result.provenance['mismatch_ratio']:.3f}")
    print(f"   Overall support: {support['overall_support']:.2f}")
    print(f"   Applied to score: {result.provenance['mismatch_applied_to_score']}")


def test_mismatch_strong_low_support_gated():
    """
    Case C: Mismatch with line_items_conf=0.45 (above 0.35 threshold but below 0.65 gate)
    Expected: strength=STRONG, applied_to_score=False, gated_reason=low_support_conf
    """
    result = reconcile_amounts(
        regex_total=525000.0,
        regex_total_line="TOTAL: 525000",
        line_item_amounts=[10000.0, 15000.0],
        line_items_confidence=0.45,  # Above 0.35 threshold but below 0.65 gate
        tax_amount=0.0,
        semantic_amounts=None,
        ocr_confidence=0.85,
        aligned_amounts=None
    )
    
    assert result.provenance["mismatch_strength"] == "STRONG", f"Expected STRONG, got {result.provenance['mismatch_strength']}"
    assert result.provenance["mismatch_applied_to_score"] == False, "Expected applied_to_score=False (gated)"
    assert result.provenance["mismatch_gated_reason"] == "low_support_conf", f"Expected low_support_conf, got {result.provenance['mismatch_gated_reason']}"
    
    # Check support breakdown
    support = result.provenance["mismatch_support"]
    assert support["overall_support"] < 0.65, f"Expected overall_support < 0.65, got {support['overall_support']}"
    assert support["items_support"] == 0.45, f"Expected items_support=0.45, got {support['items_support']}"
    
    print("✅ test_mismatch_strong_low_support_gated PASSED")
    print(f"   Strength: {result.provenance['mismatch_strength']}")
    print(f"   Overall support: {support['overall_support']:.2f}")
    print(f"   Applied to score: {result.provenance['mismatch_applied_to_score']}")
    print(f"   Gated reason: {result.provenance['mismatch_gated_reason']}")


def test_mismatch_none_within_tolerance():
    """
    Test case where mismatch is within tolerance (< 3%)
    Expected: strength=NONE, applied_to_score=False, gated_reason=mismatch_within_tolerance
    """
    result = reconcile_amounts(
        regex_total=100.0,
        regex_total_line="TOTAL: 100",
        line_item_amounts=[95.0],
        line_items_confidence=0.9,
        tax_amount=4.5,  # Total should be 99.5, diff = 0.5%
        semantic_amounts=None,
        ocr_confidence=0.85,
        aligned_amounts=None
    )
    
    assert result.provenance["mismatch_strength"] == "NONE", f"Expected NONE, got {result.provenance['mismatch_strength']}"
    assert result.provenance["mismatch_applied_to_score"] == False, "Expected applied_to_score=False"
    assert result.provenance["mismatch_gated_reason"] == "mismatch_within_tolerance", f"Expected mismatch_within_tolerance, got {result.provenance['mismatch_gated_reason']}"
    assert result.provenance["mismatch_ratio"] < 0.03, f"Expected ratio < 0.03, got {result.provenance['mismatch_ratio']}"
    
    print("✅ test_mismatch_none_within_tolerance PASSED")
    print(f"   Strength: {result.provenance['mismatch_strength']}")
    print(f"   Ratio: {result.provenance['mismatch_ratio']:.4f}")
    print(f"   Gated reason: {result.provenance['mismatch_gated_reason']}")


def test_mismatch_low_confidence_items_still_computed():
    """
    Test case where line_items_confidence=0.2 (< 0.35 threshold)
    Expected: mismatch should still be STRONG (using raw_items_sum), but gated due to low support
    """
    result = reconcile_amounts(
        regex_total=525000.0,
        regex_total_line="TOTAL: 525000",
        line_item_amounts=[10000.0, 15000.0],  # raw_items_sum = 25000
        line_items_confidence=0.2,  # Below 0.35 threshold
        tax_amount=0.0,
        semantic_amounts=None,
        ocr_confidence=0.85,
        aligned_amounts=None
    )
    
    # Mismatch should be computable using raw_items_sum
    assert result.provenance["mismatch_computable"] == True, "Expected mismatch_computable=True (using raw_items_sum)"
    assert result.provenance["mismatch_strength"] == "STRONG", f"Expected STRONG, got {result.provenance['mismatch_strength']}"
    assert result.provenance["mismatch_ratio"] is not None, "Expected mismatch_ratio to be computed"
    assert result.provenance["mismatch_ratio"] > 0.90, f"Expected ratio > 0.90, got {result.provenance['mismatch_ratio']}"
    
    # Should be gated due to low support
    assert result.provenance["mismatch_applied_to_score"] == False, "Expected applied_to_score=False (gated)"
    assert result.provenance["mismatch_gated_reason"] == "low_support_conf", f"Expected low_support_conf, got {result.provenance['mismatch_gated_reason']}"
    
    # Check that raw_items_sum was used
    assert result.provenance["mismatch_used_raw_items_sum"] == True, "Expected mismatch_used_raw_items_sum=True"
    
    # Check support breakdown
    support = result.provenance["mismatch_support"]
    assert support["items_support"] == 0.2, f"Expected items_support=0.2, got {support['items_support']}"
    assert support["overall_support"] == 0.2, f"Expected overall_support=0.2 (min of 0.9 and 0.2), got {support['overall_support']}"
    
    # items_sum should be None (filtered out), but mismatch still computed
    assert result.items_sum is None, "Expected items_sum=None (filtered due to low confidence)"
    
    print("✅ test_mismatch_low_confidence_items_still_computed PASSED")
    print(f"   Strength: {result.provenance['mismatch_strength']}")
    print(f"   Ratio: {result.provenance['mismatch_ratio']:.3f}")
    print(f"   Items support: {support['items_support']:.2f}")
    print(f"   Overall support: {support['overall_support']:.2f}")
    print(f"   Applied to score: {result.provenance['mismatch_applied_to_score']}")
    print(f"   Used raw_items_sum: {result.provenance['mismatch_used_raw_items_sum']}")


def test_compute_mismatch_signal_direct():
    """
    Direct test of _compute_mismatch_signal helper
    """
    # Test STRONG mismatch with high support
    signal = _compute_mismatch_signal(
        final_total=1000.0,
        total_source="regex",
        semantic_confidence=0.0,
        aligned_confidence=0.0,
        ocr_confidence=0.85,
        raw_items_sum=500.0,
        line_items_confidence=0.9,
        tax_amount=0.0,
    )
    
    assert signal["mismatch_computable"] == True
    assert signal["mismatch_strength"] == "STRONG"
    assert signal["mismatch_ratio"] > 0.15
    assert signal["mismatch_applied_to_score"] == True
    assert signal["mismatch_support"]["overall_support"] >= 0.65
    assert signal["mismatch_used_raw_items_sum"] == True
    
    print("✅ test_compute_mismatch_signal_direct PASSED")
    print(f"   Strength: {signal['mismatch_strength']}")
    print(f"   Ratio: {signal['mismatch_ratio']:.3f}")
    print(f"   Overall support: {signal['mismatch_support']['overall_support']:.2f}")


if __name__ == "__main__":
    print("=" * 80)
    print("Testing Gated Mismatch Signaling")
    print("=" * 80)
    
    test_mismatch_unknown_no_items()
    print()
    test_mismatch_strong_high_support()
    print()
    test_mismatch_strong_low_support_gated()
    print()
    test_mismatch_none_within_tolerance()
    print()
    test_mismatch_low_confidence_items_still_computed()
    print()
    test_compute_mismatch_signal_direct()
    
    print()
    print("=" * 80)
    print("✅ All mismatch gating tests PASSED")
    print("=" * 80)
