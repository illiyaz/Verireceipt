"""
Unit test for amount reconciliation semantic soft-fallback behavior.

Tests the v2 reconciliation logic where semantic totals with confidence >= 0.55
should be accepted when regex and alignment fail.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.pipelines.features import reconcile_amounts


def test_semantic_soft_fallback_basic():
    """
    Test case: regex_total=None, semantic_total=525000, semantic_confidence=0.63
    Expected: total_source=semantic_soft_fallback, total_amount=525000
    """
    # Mock semantic amounts object
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
    
    assert result.total_amount == 525000.0, f"Expected total_amount=525000.0, got {result.total_amount}"
    assert result.provenance["total"] == "semantic_soft_fallback", f"Expected source=semantic_soft_fallback, got {result.provenance['total']}"
    assert result.confidence > 0.0, f"Expected confidence > 0, got {result.confidence}"
    
    # Check that branch note is present
    branch_notes = [n for n in result.notes if "✓ Branch:" in n]
    assert len(branch_notes) > 0, "Expected branch note in reconciliation notes"
    assert "semantic_soft_fallback" in branch_notes[0], f"Expected semantic_soft_fallback in branch note, got {branch_notes[0]}"
    
    print("✅ test_semantic_soft_fallback_basic PASSED")
    print(f"   Total: {result.total_amount}")
    print(f"   Source: {result.provenance['total']}")
    print(f"   Confidence: {result.confidence:.2f}")
    print(f"   Branch note: {branch_notes[0]}")


def test_semantic_soft_fallback_with_aligned_zero():
    """
    Test case: regex=None, aligned_total=0, semantic_total=525000, semantic_confidence=0.63
    Expected: total_source=semantic_soft_fallback, total_amount=525000
    """
    class MockSemanticAmounts:
        def __init__(self):
            self.total_amount = 525000.0
            self.confidence = 0.63
    
    aligned_amounts = {
        "hit": True,
        "total_amount": 0.0,
        "subtotal_amount": None,
        "tax_amount": 25000.0,
        "alignment_confidence": 0.75,
        "labels_found": ["SUBTOTAL", "TAX", "TOTAL"],
        "amounts_found": [500000.0, 25000.0, 0.0],
        "notes": ["Aligned amounts detected"]
    }
    
    result = reconcile_amounts(
        regex_total=None,
        regex_total_line=None,
        line_item_amounts=[],
        line_items_confidence=0.0,
        tax_amount=None,
        semantic_amounts=MockSemanticAmounts(),
        ocr_confidence=None,
        aligned_amounts=aligned_amounts
    )
    
    assert result.total_amount == 525000.0, f"Expected total_amount=525000.0, got {result.total_amount}"
    assert result.provenance["total"] == "semantic_soft_fallback", f"Expected source=semantic_soft_fallback, got {result.provenance['total']}"
    assert result.confidence > 0.0, f"Expected confidence > 0, got {result.confidence}"
    
    # Check aligned provenance is present
    assert result.provenance["aligned_hit"] == True, "Expected aligned_hit=True in provenance"
    assert result.provenance["aligned_total"] == 0.0, "Expected aligned_total=0.0 in provenance"
    
    print("✅ test_semantic_soft_fallback_with_aligned_zero PASSED")
    print(f"   Total: {result.total_amount}")
    print(f"   Source: {result.provenance['total']}")
    print(f"   Confidence: {result.confidence:.2f}")
    print(f"   Aligned hit: {result.provenance['aligned_hit']}")


def test_semantic_below_threshold_rejected():
    """
    Test case: semantic_confidence=0.50 (< 0.55 threshold)
    Expected: total_amount=None, source=none
    """
    class MockSemanticAmounts:
        def __init__(self):
            self.total_amount = 525000.0
            self.confidence = 0.50  # Below 0.55 threshold
    
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
    
    assert result.total_amount is None, f"Expected total_amount=None for low confidence, got {result.total_amount}"
    assert result.provenance["total"] == "none", f"Expected source=none, got {result.provenance['total']}"
    assert result.confidence == 0.0, f"Expected confidence=0.0, got {result.confidence}"
    
    print("✅ test_semantic_below_threshold_rejected PASSED")
    print(f"   Total: {result.total_amount}")
    print(f"   Source: {result.provenance['total']}")
    print(f"   Confidence: {result.confidence:.2f}")


if __name__ == "__main__":
    print("=" * 80)
    print("Testing Amount Reconciliation Semantic Soft-Fallback")
    print("=" * 80)
    
    test_semantic_soft_fallback_basic()
    print()
    test_semantic_soft_fallback_with_aligned_zero()
    print()
    test_semantic_below_threshold_rejected()
    
    print()
    print("=" * 80)
    print("✅ All tests PASSED")
    print("=" * 80)
