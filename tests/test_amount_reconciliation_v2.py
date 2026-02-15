"""
Phase-9: Amount Reconciliation V2 Tests

Tests for deterministic cross-entity reconciliation logic.
Covers golden scenarios, safety invariants, and confidence gating.
"""

import pytest
from app.pipelines.features import (
    reconcile_amounts_v2,
    RECONCILIATION_TOLERANCE_NONE,
    RECONCILIATION_TOLERANCE_WEAK,
    RECONCILIATION_TOLERANCE_MEDIUM,
    RECONCILIATION_MIN_SUPPORT_CONFIDENCE,
    RECONCILIATION_PENALTY_WEAK,
    RECONCILIATION_PENALTY_MEDIUM,
    RECONCILIATION_PENALTY_STRONG,
)


# ============================================================================
# GOLDEN RECONCILIATION TESTS
# ============================================================================

def test_perfect_match():
    """Golden case: subtotal + tax = total (perfect match)"""
    result = reconcile_amounts_v2(
        subtotal=100.0,
        tax=10.0,
        discount=None,
        tip=None,
        total=110.0,
        confidence_map={"subtotal": 0.9, "tax": 0.85, "total": 0.9}
    )
    
    assert result["expected_total"] == 110.0
    assert result["actual_total"] == 110.0
    assert result["mismatch_ratio"] == 0.0
    assert result["status"] == "NONE"
    assert result["penalty_applied"] is False
    assert result["confidence_penalty"] == 0.0
    assert result["components_used"] == ["subtotal", "tax"]


def test_missing_subtotal():
    """Golden case: tax-only receipt (no subtotal)"""
    result = reconcile_amounts_v2(
        subtotal=None,
        tax=15.0,
        discount=None,
        tip=None,
        total=115.0,
        confidence_map={"tax": 0.8, "total": 0.9}
    )
    
    # Should reconcile with just tax
    assert result["expected_total"] == 15.0
    assert result["actual_total"] == 115.0
    assert result["status"] == "STRONG"  # Large mismatch
    # But coverage NOT OK (only 1 component) - Phase-9.1.1 fix
    assert result["penalty_applied"] is False
    assert result["gated_reason"] == "insufficient_component_coverage"


def test_discount_larger_than_subtotal():
    """Golden case: discount reduces total below subtotal"""
    result = reconcile_amounts_v2(
        subtotal=100.0,
        tax=10.0,
        discount=30.0,
        tip=None,
        total=80.0,
        confidence_map={"subtotal": 0.9, "tax": 0.85, "discount": 0.8, "total": 0.9}
    )
    
    # expected = 100 + 10 - 30 = 80
    assert result["expected_total"] == 80.0
    assert result["actual_total"] == 80.0
    assert result["mismatch_ratio"] == 0.0
    assert result["status"] == "NONE"
    assert result["penalty_applied"] is False


def test_tip_only_receipt():
    """Golden case: tip-only receipt (restaurant)"""
    result = reconcile_amounts_v2(
        subtotal=None,
        tax=None,
        discount=None,
        tip=5.0,
        total=105.0,
        confidence_map={"tip": 0.75, "total": 0.9}
    )
    
    # expected = 5.0 (tip only)
    assert result["expected_total"] == 5.0
    assert result["actual_total"] == 105.0
    assert result["status"] == "STRONG"  # Large mismatch
    # But coverage NOT OK (only 1 component) - Phase-9.1.1 fix
    assert result["penalty_applied"] is False
    assert result["gated_reason"] == "insufficient_component_coverage"


def test_tax_inclusive_total():
    """Golden case: tax-inclusive receipt (common in some regions)"""
    result = reconcile_amounts_v2(
        subtotal=90.91,
        tax=9.09,
        discount=None,
        tip=None,
        total=100.0,
        confidence_map={"subtotal": 0.85, "tax": 0.8, "total": 0.9}
    )
    
    # expected = 90.91 + 9.09 = 100.0
    assert result["expected_total"] == 100.0
    assert result["actual_total"] == 100.0
    assert result["mismatch_ratio"] == 0.0
    assert result["status"] == "NONE"


def test_ocr_broken_subtotal_with_good_total():
    """Golden case: OCR error in subtotal but total is correct"""
    result = reconcile_amounts_v2(
        subtotal=95.0,  # OCR misread as 95 instead of 100
        tax=10.0,
        discount=None,
        tip=None,
        total=110.0,
        confidence_map={"subtotal": 0.5, "tax": 0.9, "total": 0.9}  # Low subtotal confidence
    )
    
    # expected = 95 + 10 = 105, actual = 110
    # mismatch = 5/105 = 4.76% (WEAK)
    assert result["expected_total"] == 105.0
    assert result["actual_total"] == 110.0
    assert 0.045 < result["mismatch_ratio"] < 0.050
    assert result["status"] == "WEAK"
    
    # Support confidence = min(0.5, 0.9, 0.9) = 0.5 < 0.65
    # Should NOT apply penalty (gated)
    assert result["support_confidence"] == 0.5
    assert result["penalty_applied"] is False
    assert result["gated_reason"] == "support_confidence_below_threshold"


def test_all_components_present():
    """Golden case: all components present (subtotal + tax + tip - discount)"""
    result = reconcile_amounts_v2(
        subtotal=100.0,
        tax=10.0,
        discount=5.0,
        tip=15.0,
        total=120.0,
        confidence_map={"subtotal": 0.9, "tax": 0.85, "discount": 0.8, "tip": 0.75, "total": 0.9}
    )
    
    # expected = 100 + 10 + 15 - 5 = 120
    assert result["expected_total"] == 120.0
    assert result["actual_total"] == 120.0
    assert result["mismatch_ratio"] == 0.0
    assert result["status"] == "NONE"
    assert result["components_used"] == ["subtotal", "tax", "tip", "discount"]


def test_all_components_with_shipping():
    """Golden case: all components including shipping (e-commerce receipt)"""
    result = reconcile_amounts_v2(
        subtotal=100.0,
        tax=10.0,
        discount=5.0,
        tip=None,
        shipping=12.0,
        total=117.0,
        confidence_map={"subtotal": 0.9, "tax": 0.85, "discount": 0.8, "shipping": 0.85, "total": 0.9}
    )
    
    # expected = 100 + 10 + 12 - 5 = 117
    assert result["expected_total"] == 117.0
    assert result["actual_total"] == 117.0
    assert result["mismatch_ratio"] == 0.0
    assert result["status"] == "NONE"
    assert result["components_used"] == ["subtotal", "tax", "shipping", "discount"]


def test_shipping_mismatch():
    """Edge case: shipping extracted but not included in total by merchant"""
    result = reconcile_amounts_v2(
        subtotal=100.0,
        tax=10.0,
        discount=None,
        tip=None,
        shipping=15.0,  # Free shipping promo - not added to total
        total=110.0,
        confidence_map={"subtotal": 0.9, "tax": 0.85, "shipping": 0.7, "total": 0.9}
    )
    
    # expected = 100 + 10 + 15 = 125, actual = 110
    # mismatch = 15/125 = 12% (exactly at STRONG threshold)
    assert result["expected_total"] == 125.0
    assert result["actual_total"] == 110.0
    assert result["status"] == "STRONG"  # 12% is at the boundary, falls into STRONG


# ============================================================================
# SAFETY INVARIANT TESTS
# ============================================================================

def test_invariant_strong_mismatch_with_high_support_applies_penalty():
    """
    INVARIANT: If mismatch STRONG + support >= 0.65 → penalty MUST be applied
    """
    result = reconcile_amounts_v2(
        subtotal=100.0,
        tax=10.0,
        discount=None,
        tip=None,
        total=150.0,  # 36% mismatch
        confidence_map={"subtotal": 0.9, "tax": 0.85, "total": 0.9}
    )
    
    # Mismatch = (150 - 110) / 110 = 36% > 12% = STRONG
    assert result["status"] == "STRONG"
    assert result["support_confidence"] == 0.85  # min(0.9, 0.85, 0.9)
    assert result["support_confidence"] >= RECONCILIATION_MIN_SUPPORT_CONFIDENCE
    assert result["penalty_applied"] is True
    assert result["confidence_penalty"] == RECONCILIATION_PENALTY_STRONG


def test_invariant_weak_mismatch_with_high_support_applies_penalty():
    """
    INVARIANT: If mismatch WEAK + support >= 0.65 → penalty MUST be applied
    """
    result = reconcile_amounts_v2(
        subtotal=100.0,
        tax=10.0,
        discount=None,
        tip=None,
        total=113.0,  # 2.7% mismatch
        confidence_map={"subtotal": 0.9, "tax": 0.85, "total": 0.9}
    )
    
    # Mismatch = (113 - 110) / 110 = 2.7% (WEAK)
    assert result["status"] == "WEAK"
    assert result["support_confidence"] >= RECONCILIATION_MIN_SUPPORT_CONFIDENCE
    assert result["penalty_applied"] is True
    assert result["confidence_penalty"] == RECONCILIATION_PENALTY_WEAK


def test_invariant_medium_mismatch_with_high_support_applies_penalty():
    """
    INVARIANT: If mismatch MEDIUM + support >= 0.65 → penalty MUST be applied
    """
    result = reconcile_amounts_v2(
        subtotal=100.0,
        tax=10.0,
        discount=None,
        tip=None,
        total=120.0,  # 9% mismatch
        confidence_map={"subtotal": 0.9, "tax": 0.85, "total": 0.9}
    )
    
    # Mismatch = (120 - 110) / 110 = 9% (MEDIUM)
    assert result["status"] == "MEDIUM"
    assert result["support_confidence"] >= RECONCILIATION_MIN_SUPPORT_CONFIDENCE
    assert result["penalty_applied"] is True
    assert result["confidence_penalty"] == RECONCILIATION_PENALTY_MEDIUM


def test_invariant_low_support_never_applies_penalty():
    """
    INVARIANT: If support < 0.65 → penalty MUST NOT be applied (regardless of mismatch)
    """
    result = reconcile_amounts_v2(
        subtotal=100.0,
        tax=10.0,
        discount=None,
        tip=None,
        total=150.0,  # 36% mismatch (STRONG)
        confidence_map={"subtotal": 0.6, "tax": 0.5, "total": 0.9}  # Low component confidence
    )
    
    # Support = min(0.6, 0.5, 0.9) = 0.5 < 0.65
    assert result["status"] == "STRONG"
    assert result["support_confidence"] == 0.5
    assert result["support_confidence"] < RECONCILIATION_MIN_SUPPORT_CONFIDENCE
    assert result["penalty_applied"] is False
    assert result["confidence_penalty"] == 0.0
    assert result["gated_reason"] == "support_confidence_below_threshold"


def test_invariant_no_total_no_reconciliation():
    """
    INVARIANT: If total is None or < 0 → no reconciliation
    """
    result = reconcile_amounts_v2(
        subtotal=100.0,
        tax=10.0,
        discount=None,
        tip=None,
        total=None,
        confidence_map={"subtotal": 0.9, "tax": 0.85, "total": 0.0}
    )
    
    assert result["status"] == "NONE"
    assert result["penalty_applied"] is False
    assert result["gated_reason"] == "no_total_to_reconcile"


def test_invariant_no_components_no_reconciliation():
    """
    INVARIANT: If no components available → no reconciliation
    """
    result = reconcile_amounts_v2(
        subtotal=None,
        tax=None,
        discount=None,
        tip=None,
        total=100.0,
        confidence_map={}
    )
    
    assert result["status"] == "NONE"
    assert result["penalty_applied"] is False
    assert result["gated_reason"] == "no_components_to_reconcile"


def test_invariant_penalty_magnitude_correct():
    """
    INVARIANT: Penalty magnitudes must match constants
    """
    # WEAK penalty
    result_weak = reconcile_amounts_v2(
        subtotal=100.0, tax=10.0, discount=None, tip=None, total=113.0,
        confidence_map={"subtotal": 0.9, "tax": 0.85, "total": 0.9}
    )
    assert result_weak["confidence_penalty"] == RECONCILIATION_PENALTY_WEAK
    
    # MEDIUM penalty
    result_medium = reconcile_amounts_v2(
        subtotal=100.0, tax=10.0, discount=None, tip=None, total=120.0,
        confidence_map={"subtotal": 0.9, "tax": 0.85, "total": 0.9}
    )
    assert result_medium["confidence_penalty"] == RECONCILIATION_PENALTY_MEDIUM
    
    # STRONG penalty
    result_strong = reconcile_amounts_v2(
        subtotal=100.0, tax=10.0, discount=None, tip=None, total=150.0,
        confidence_map={"subtotal": 0.9, "tax": 0.85, "total": 0.9}
    )
    assert result_strong["confidence_penalty"] == RECONCILIATION_PENALTY_STRONG


def test_invariant_support_confidence_is_minimum():
    """
    INVARIANT: support_confidence = min(participating component confidences + total)
    """
    result = reconcile_amounts_v2(
        subtotal=100.0,
        tax=10.0,
        discount=5.0,
        tip=None,
        total=105.0,
        confidence_map={"subtotal": 0.9, "tax": 0.7, "discount": 0.85, "total": 0.8}
    )
    
    # Support should be min(0.9, 0.7, 0.85, 0.8) = 0.7
    assert result["support_confidence"] == 0.7


def test_invariant_components_used_accurate():
    """
    INVARIANT: components_used must accurately reflect which components were used
    """
    result = reconcile_amounts_v2(
        subtotal=100.0,
        tax=None,
        discount=5.0,
        tip=15.0,
        total=110.0,
        confidence_map={"subtotal": 0.9, "discount": 0.8, "tip": 0.75, "total": 0.9}
    )
    
    # Only subtotal, tip, discount should be in components_used (not tax)
    # Phase-9.1.1: deterministic order
    assert result["components_used"] == ["subtotal", "tip", "discount"]
    assert "tax" not in result["components_used"]


# ============================================================================
# EDGE CASES
# ============================================================================

def test_edge_case_zero_expected_total():
    """Edge case: discount equals subtotal + tax"""
    result = reconcile_amounts_v2(
        subtotal=100.0,
        tax=10.0,
        discount=110.0,
        tip=None,
        total=0.0,
        confidence_map={"subtotal": 0.9, "tax": 0.85, "discount": 0.8, "total": 0.9}
    )
    
    # expected = 100 + 10 - 110 = 0
    assert result["expected_total"] == 0.0
    assert result["mismatch_ratio"] == 0.0  # Can't divide by zero, should be 0


def test_edge_case_negative_components_ignored():
    """Edge case: negative amounts should be ignored"""
    result = reconcile_amounts_v2(
        subtotal=-100.0,  # Invalid
        tax=10.0,
        discount=None,
        tip=None,
        total=110.0,
        confidence_map={"subtotal": 0.9, "tax": 0.85, "total": 0.9}
    )
    
    # Negative subtotal should be ignored
    assert "subtotal" not in result["components_used"]
    assert result["components_used"] == ["tax"]
    # Coverage NOT OK (only 1 component) - Phase-9.1.1 fix
    assert result["penalty_applied"] is False
    assert result["gated_reason"] == "insufficient_component_coverage"


def test_edge_case_very_small_mismatch():
    """Edge case: mismatch < 0.01% should be NONE"""
    result = reconcile_amounts_v2(
        subtotal=100.0,
        tax=10.0,
        discount=None,
        tip=None,
        total=110.01,  # 0.009% mismatch
        confidence_map={"subtotal": 0.9, "tax": 0.85, "total": 0.9}
    )
    
    assert result["mismatch_ratio"] < RECONCILIATION_TOLERANCE_NONE
    assert result["status"] == "NONE"
    assert result["penalty_applied"] is False


# ============================================================================
# PHASE-9.1.1 HARDENING TESTS
# ============================================================================

def test_hardening_expected_zero_total_nonzero_strong():
    """
    Phase-9.1.1 Fix A4: expected==0, total!=0 → STRONG
    
    When discount equals subtotal+tax, expected=0 but total!=0 should be STRONG mismatch.
    """
    result = reconcile_amounts_v2(
        subtotal=10.0,
        tax=None,
        discount=10.0,
        tip=None,
        total=1.0,
        confidence_map={"subtotal": 0.9, "discount": 0.85, "total": 0.9}
    )
    
    assert result["expected_total"] == 0.0
    assert result["actual_total"] == 1.0
    assert result["status"] == "STRONG"
    assert result["mismatch_ratio"] > 0
    # Coverage OK (subtotal present), support OK → penalty applied
    assert result["penalty_applied"] is True
    assert result["confidence_penalty"] == RECONCILIATION_PENALTY_STRONG


def test_hardening_expected_zero_total_zero_none():
    """
    Phase-9.1.1 Fix A4: expected==0, total==0 → NONE
    
    When both expected and total are zero, it's a perfect match.
    """
    result = reconcile_amounts_v2(
        subtotal=10.0,
        tax=None,
        discount=10.0,
        tip=None,
        total=0.0,
        confidence_map={"subtotal": 0.9, "discount": 0.85, "total": 0.9}
    )
    
    assert result["expected_total"] == 0.0
    assert result["actual_total"] == 0.0
    assert result["mismatch_ratio"] == 0.0
    assert result["status"] == "NONE"
    assert result["penalty_applied"] is False


def test_hardening_support_confidence_includes_total():
    """
    Phase-9.1.1 Fix A2: support confidence includes total confidence
    
    Even if components have high confidence, low total confidence should gate penalty.
    """
    result = reconcile_amounts_v2(
        subtotal=100.0,
        tax=10.0,
        discount=None,
        tip=None,
        total=150.0,  # 36% mismatch
        confidence_map={"subtotal": 0.9, "tax": 0.9, "total": 0.2}  # Low total confidence
    )
    
    # Support = min(0.9, 0.9, 0.2) = 0.2 < 0.65
    assert result["support_confidence"] == 0.2
    assert result["status"] == "STRONG"
    assert result["penalty_applied"] is False
    assert result["gated_reason"] == "support_confidence_below_threshold"


def test_hardening_coverage_gate_tax_only():
    """
    Phase-9.1.1 Fix A3: coverage gate prevents tax-only penalty
    
    Tax-only receipts have insufficient coverage and should not be penalized.
    """
    result = reconcile_amounts_v2(
        subtotal=None,
        tax=5.0,
        discount=None,
        tip=None,
        total=20.0,
        confidence_map={"tax": 0.9, "total": 0.9}
    )
    
    # Mismatch = (20 - 5) / 5 = 300% = STRONG
    assert result["status"] == "STRONG"
    # But coverage NOT OK (only 1 component, no subtotal)
    assert result["penalty_applied"] is False
    assert result["gated_reason"] == "insufficient_component_coverage"
    assert result["confidence_penalty"] == 0.0


def test_hardening_coverage_gate_two_components_ok():
    """
    Phase-9.1.1 Fix A3: coverage OK with 2+ components (no subtotal)
    
    If we have 2+ components (even without subtotal), coverage is OK.
    """
    result = reconcile_amounts_v2(
        subtotal=None,
        tax=10.0,
        tip=5.0,
        discount=None,
        total=20.0,  # expected = 15, mismatch = 33% = STRONG
        confidence_map={"tax": 0.9, "tip": 0.85, "total": 0.9}
    )
    
    # Coverage OK (2 components: tax + tip)
    # Support OK (min = 0.85)
    assert result["status"] == "STRONG"
    assert result["penalty_applied"] is True
    assert result["confidence_penalty"] == RECONCILIATION_PENALTY_STRONG


def test_hardening_deterministic_components_used_order():
    """
    Phase-9.1.1 Fix A1: components_used has deterministic order
    
    Regardless of argument order, components_used should always be in canonical order.
    """
    # Provide components in random order via dict
    result = reconcile_amounts_v2(
        discount=5.0,
        tip=15.0,
        subtotal=100.0,
        tax=10.0,
        total=120.0,
        confidence_map={"subtotal": 0.9, "tax": 0.85, "tip": 0.8, "discount": 0.75, "total": 0.9}
    )
    
    # components_used should be in canonical order: subtotal, tax, tip, discount
    assert result["components_used"] == ["subtotal", "tax", "tip", "discount"]


def test_hardening_gated_reason_stable_no_floats():
    """
    Phase-9.1.1 Fix A5: gated_reason should not contain floating point numbers
    
    Ensures gated_reason is stable for ML training and testing.
    """
    result = reconcile_amounts_v2(
        subtotal=100.0,
        tax=10.0,
        discount=None,
        tip=None,
        total=150.0,
        confidence_map={"subtotal": 0.5, "tax": 0.4, "total": 0.3}
    )
    
    # Should be gated due to low support
    assert result["penalty_applied"] is False
    assert result["gated_reason"] == "support_confidence_below_threshold"
    # Ensure no floating point numbers in gated_reason
    assert "0.3" not in result["gated_reason"]
    assert "0.4" not in result["gated_reason"]


def test_hardening_coverage_gate_subtotal_present_always_ok():
    """
    Phase-9.1.1 Fix A3: if subtotal is present, coverage is always OK
    
    Even with just subtotal alone, coverage should be OK.
    """
    result = reconcile_amounts_v2(
        subtotal=100.0,
        tax=None,
        discount=None,
        tip=None,
        total=150.0,
        confidence_map={"subtotal": 0.9, "total": 0.9}
    )
    
    # Coverage OK (subtotal present)
    # Support OK (min = 0.9)
    # Mismatch = 50% = STRONG
    assert result["status"] == "STRONG"
    assert result["penalty_applied"] is True
    assert result["confidence_penalty"] == RECONCILIATION_PENALTY_STRONG


# ============================================================================
# OPTIONAL SAFETY CHECKS
# ============================================================================

def test_optional_check_gated_reason_implies_no_penalty():
    """
    Optional Check 2: If gated_reason is set, penalty_applied MUST be False
    
    This is a critical invariant that prevents logic errors.
    """
    # Test all gating scenarios
    test_cases = [
        # Coverage gating
        (
            {"subtotal": None, "tax": 5.0, "discount": None, "tip": None, "total": 20.0,
             "confidence_map": {"tax": 0.9, "total": 0.9}},
            "insufficient_component_coverage"
        ),
        # Support confidence gating
        (
            {"subtotal": 100.0, "tax": 10.0, "discount": None, "tip": None, "total": 150.0,
             "confidence_map": {"subtotal": 0.5, "tax": 0.4, "total": 0.3}},
            "support_confidence_below_threshold"
        ),
    ]
    
    for params, expected_gated_reason in test_cases:
        result = reconcile_amounts_v2(**params)
        
        # If gated_reason is set, penalty MUST NOT be applied
        if result["gated_reason"] is not None:
            assert result["penalty_applied"] is False, \
                f"gated_reason='{result['gated_reason']}' but penalty_applied=True"
            assert result["confidence_penalty"] == 0.0, \
                f"gated_reason='{result['gated_reason']}' but confidence_penalty={result['confidence_penalty']}"
            assert result["gated_reason"] == expected_gated_reason, \
                f"Expected gated_reason='{expected_gated_reason}' but got '{result['gated_reason']}'"


def test_optional_check_mismatch_ratio_never_negative():
    """
    Optional Check 1: mismatch_ratio must always be >= 0
    
    Protects against math regressions and keeps ML features sane.
    """
    test_cases = [
        # Normal case
        {"subtotal": 100.0, "tax": 10.0, "discount": None, "tip": None, "total": 110.0,
         "confidence_map": {"subtotal": 0.9, "tax": 0.85, "total": 0.9}},
        # Zero expected
        {"subtotal": 10.0, "tax": None, "discount": 10.0, "tip": None, "total": 0.0,
         "confidence_map": {"subtotal": 0.9, "discount": 0.85, "total": 0.9}},
        # Large mismatch
        {"subtotal": 100.0, "tax": 10.0, "discount": None, "tip": None, "total": 200.0,
         "confidence_map": {"subtotal": 0.9, "tax": 0.85, "total": 0.9}},
        # Very small amounts
        {"subtotal": 0.01, "tax": 0.01, "discount": None, "tip": None, "total": 0.02,
         "confidence_map": {"subtotal": 0.9, "tax": 0.85, "total": 0.9}},
    ]
    
    for test_case in test_cases:
        result = reconcile_amounts_v2(**test_case)
        
        # mismatch_ratio must NEVER be negative
        assert result["mismatch_ratio"] >= 0.0, \
            f"mismatch_ratio={result['mismatch_ratio']} is negative - this should never happen"
