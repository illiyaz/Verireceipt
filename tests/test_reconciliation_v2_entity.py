"""
Phase-9.2: Amount Reconciliation V2 Entity Contract Tests

Tests that reconciliation_v2 is properly integrated as a first-class typed entity
in the AMOUNT_RECONCILIATION evidence payload.

Contract:
- reconciliation_v2 always present in evidence
- Gating contract preserved: gated_reason != None => penalty_applied == False
- Schema stability: all fields present even when not computable
"""

import pytest
from app.pipelines.features import (
    reconcile_amounts_v2,
    build_reconciliation_v2_entity,
    AmountReconciliationV2,
    _validate_reconciliation_v2_contract,
)


# ============================================================================
# ENTITY BUILDER TESTS
# ============================================================================

def test_entity_builder_with_no_total():
    """
    Test 1: When total is None => reconciliation_v2 exists, gated, penalty cleared.
    """
    # Call reconcile_amounts_v2 with no total
    evidence_dict = reconcile_amounts_v2(
        subtotal=100.0,
        tax=10.0,
        discount=None,
        tip=None,
        total=None,
        confidence_map={"subtotal": 0.9, "tax": 0.85, "total": 0.0}
    )
    
    # Build entity
    coverage_ok = ("subtotal" in evidence_dict.get("components_used", []))
    entity = build_reconciliation_v2_entity(evidence_dict, coverage_ok=coverage_ok)
    
    # Verify entity contract
    assert entity.schema_version == 2
    assert entity.formula == "subtotal+tax+tip-discount"
    assert entity.gated_reason == "no_total_to_reconcile"
    assert entity.penalty_applied is False
    assert entity.confidence_penalty == 0.0
    # Contract Freeze: gated_reason "no_total_to_reconcile" implies status=UNKNOWN
    assert entity.status == "UNKNOWN"
    assert entity.mismatch_ratio is None  # UNKNOWN implies mismatch_ratio is None
    
    # Verify to_dict() works
    entity_dict = entity.to_dict()
    assert isinstance(entity_dict, dict)
    assert entity_dict["schema_version"] == 2
    assert entity_dict["gated_reason"] == "no_total_to_reconcile"
    assert entity_dict["penalty_applied"] is False


def test_entity_builder_with_only_total():
    """
    Test 2: When only total present (no components) => gated with explicit reason, mismatch_ratio None.
    """
    # Call reconcile_amounts_v2 with only total
    evidence_dict = reconcile_amounts_v2(
        subtotal=None,
        tax=None,
        discount=None,
        tip=None,
        total=100.0,
        confidence_map={"total": 0.9}
    )
    
    # Build entity
    coverage_ok = False  # No components
    entity = build_reconciliation_v2_entity(evidence_dict, coverage_ok=coverage_ok)
    
    # Verify entity contract
    assert entity.schema_version == 2
    assert entity.gated_reason == "no_components_to_reconcile"
    assert entity.penalty_applied is False
    assert entity.confidence_penalty == 0.0
    # Contract Freeze: gated_reason "no_components_to_reconcile" implies status=UNKNOWN
    assert entity.status == "UNKNOWN"
    assert entity.mismatch_ratio is None  # UNKNOWN implies mismatch_ratio is None
    assert entity.actual_total == 100.0
    assert entity.expected_total is None  # Early return, not computed
    
    # Verify to_dict() works
    entity_dict = entity.to_dict()
    assert entity_dict["gated_reason"] == "no_components_to_reconcile"
    assert entity_dict["penalty_applied"] is False


def test_entity_builder_with_mismatch_and_high_confidence():
    """
    Test 3: When subtotal+tax present and mismatching with high confidence =>
    status WEAK/MEDIUM/STRONG and penalty_applied consistent with Phase-9.1 thresholds.
    """
    # Call reconcile_amounts_v2 with mismatch
    evidence_dict = reconcile_amounts_v2(
        subtotal=100.0,
        tax=10.0,
        discount=None,
        tip=None,
        total=150.0,  # 36% mismatch = STRONG
        confidence_map={"subtotal": 0.9, "tax": 0.85, "total": 0.9}
    )
    
    # Build entity
    coverage_ok = True  # Subtotal present
    entity = build_reconciliation_v2_entity(evidence_dict, coverage_ok=coverage_ok)
    
    # Verify entity contract
    assert entity.schema_version == 2
    assert entity.expected_total == 110.0
    assert entity.actual_total == 150.0
    assert entity.status == "STRONG"  # 36% mismatch
    assert entity.mismatch_ratio is not None
    assert entity.mismatch_ratio > 0.12  # Above MEDIUM threshold
    assert entity.penalty_applied is True
    assert entity.confidence_penalty > 0.0
    assert entity.gated_reason is None  # Not gated
    assert entity.coverage_ok is True
    assert "subtotal" in entity.components_used
    assert "tax" in entity.components_used
    
    # Verify to_dict() works
    entity_dict = entity.to_dict()
    assert entity_dict["status"] == "STRONG"
    assert entity_dict["penalty_applied"] is True


# ============================================================================
# VALIDATOR TESTS
# ============================================================================

def test_validator_enforces_gating_contract():
    """
    Validator must enforce: gated_reason != None => penalty_applied == False
    """
    # Create entity with gated_reason but penalty applied (contract violation)
    entity = AmountReconciliationV2(
        gated_reason="insufficient_component_coverage",
        penalty_applied=True,  # Violation!
        confidence_penalty=0.15,  # Violation!
    )
    
    # Validator should fix this in prod-safe mode
    _validate_reconciliation_v2_contract(entity)
    
    # After validation, contract should be enforced
    assert entity.penalty_applied is False
    assert entity.confidence_penalty == 0.0


def test_validator_clamps_support_confidence():
    """
    Validator must clamp support_confidence to [0, 1]
    """
    # Create entity with out-of-range confidence
    entity = AmountReconciliationV2(
        support_confidence=1.5  # Out of range!
    )
    
    # Validator should clamp this
    _validate_reconciliation_v2_contract(entity)
    
    # After validation, should be clamped
    assert 0.0 <= entity.support_confidence <= 1.0
    assert entity.support_confidence == 1.0  # Clamped to max


def test_validator_enforces_unknown_status_contract():
    """
    Validator must enforce: status == "UNKNOWN" => mismatch_ratio is None
    """
    # Create entity with UNKNOWN status but non-None mismatch_ratio
    entity = AmountReconciliationV2(
        status="UNKNOWN",
        mismatch_ratio=0.15  # Violation!
    )
    
    # Validator should fix this
    _validate_reconciliation_v2_contract(entity)
    
    # After validation, mismatch_ratio should be None
    assert entity.mismatch_ratio is None


# ============================================================================
# ENTITY SCHEMA STABILITY TESTS
# ============================================================================

def test_entity_always_has_all_fields():
    """
    All entity fields must always be present, even when not computable.
    """
    # Create minimal entity
    entity = AmountReconciliationV2()
    
    # Verify all required fields exist
    assert hasattr(entity, "schema_version")
    assert hasattr(entity, "formula")
    assert hasattr(entity, "expected_total")
    assert hasattr(entity, "actual_total")
    assert hasattr(entity, "mismatch_ratio")
    assert hasattr(entity, "status")
    assert hasattr(entity, "support_confidence")
    assert hasattr(entity, "coverage_ok")
    assert hasattr(entity, "penalty_applied")
    assert hasattr(entity, "confidence_penalty")
    assert hasattr(entity, "gated_reason")
    assert hasattr(entity, "components_used")
    assert hasattr(entity, "notes")
    
    # Verify to_dict includes all fields
    entity_dict = entity.to_dict()
    assert "schema_version" in entity_dict
    assert "formula" in entity_dict
    assert "expected_total" in entity_dict
    assert "actual_total" in entity_dict
    assert "mismatch_ratio" in entity_dict
    assert "status" in entity_dict
    assert "support_confidence" in entity_dict
    assert "coverage_ok" in entity_dict
    assert "penalty_applied" in entity_dict
    assert "confidence_penalty" in entity_dict
    assert "gated_reason" in entity_dict
    assert "components_used" in entity_dict
    assert "notes" in entity_dict


def test_entity_to_dict_float_rounding():
    """
    to_dict() must round floats consistently.
    """
    entity = AmountReconciliationV2(
        expected_total=123.456789,
        actual_total=234.567890,
        mismatch_ratio=0.123456789,
        support_confidence=0.876543210,
        confidence_penalty=0.123456789,
    )
    
    entity_dict = entity.to_dict()
    
    # Verify rounding
    assert entity_dict["expected_total"] == round(123.456789, 2)  # 2dp for totals
    assert entity_dict["actual_total"] == round(234.567890, 2)  # 2dp for totals
    assert entity_dict["mismatch_ratio"] == round(0.123456789, 4)  # 4dp for ratio
    assert entity_dict["support_confidence"] == round(0.876543210, 3)  # 3dp for confidence
    assert entity_dict["confidence_penalty"] == round(0.123456789, 3)  # 3dp for penalty


# ============================================================================
# INTEGRATION TESTS (Phase-9.1 + Phase-9.2)
# ============================================================================

def test_integration_gating_contract_preserved():
    """
    Phase-9.1 gating contract must be preserved in Phase-9.2 entity.
    """
    # Test coverage gating
    evidence_dict = reconcile_amounts_v2(
        subtotal=None,
        tax=5.0,
        discount=None,
        tip=None,
        total=20.0,
        confidence_map={"tax": 0.9, "total": 0.9}
    )
    
    coverage_ok = False  # Only tax, no subtotal
    entity = build_reconciliation_v2_entity(evidence_dict, coverage_ok=coverage_ok)
    
    # Gating contract: gated_reason => no penalty
    assert entity.gated_reason == "insufficient_component_coverage"
    assert entity.penalty_applied is False
    assert entity.confidence_penalty == 0.0
    # Contract Freeze: gated_reason "insufficient_component_coverage" implies status=UNKNOWN
    assert entity.status == "UNKNOWN"
    assert entity.mismatch_ratio is None  # UNKNOWN implies mismatch_ratio is None


def test_insufficient_components_gating_reason():
    """
    Test that "insufficient_components" gating reason (real Phase-9.1 string) 
    forces status=UNKNOWN and mismatch_ratio=None.
    """
    # Simulate evidence dict with "insufficient_components" gating
    evidence_dict = {
        "expected_total": 100.0,
        "actual_total": 120.0,
        "mismatch_ratio": 0.2,  # Will be forced to None
        "status": "MEDIUM",  # Will be forced to UNKNOWN
        "support_confidence": 0.8,
        "penalty_applied": False,
        "confidence_penalty": 0.0,
        "gated_reason": "insufficient_components",  # Real Phase-9.1 string
        "components_used": ["tax"]
    }
    
    coverage_ok = False
    entity = build_reconciliation_v2_entity(evidence_dict, coverage_ok=coverage_ok)
    
    # Contract Freeze: "insufficient_components" implies UNKNOWN
    assert entity.gated_reason == "insufficient_components"
    assert entity.status == "UNKNOWN"
    assert entity.mismatch_ratio is None
    assert entity.penalty_applied is False
    assert entity.confidence_penalty == 0.0


def test_integration_no_gating_when_coverage_and_confidence_ok():
    """
    When coverage and confidence are OK, penalties should be applied for mismatches.
    """
    evidence_dict = reconcile_amounts_v2(
        subtotal=100.0,
        tax=10.0,
        discount=None,
        tip=None,
        total=120.0,  # 9% mismatch
        confidence_map={"subtotal": 0.9, "tax": 0.85, "total": 0.9}
    )
    
    coverage_ok = True
    entity = build_reconciliation_v2_entity(evidence_dict, coverage_ok=coverage_ok)
    
    # No gating, penalty applied
    assert entity.gated_reason is None
    # 9% mismatch: 5-12% range = MEDIUM (not WEAK which is 2-5%)
    assert entity.status in ["WEAK", "MEDIUM"]  # Accept either based on exact calculation
    assert entity.penalty_applied is True
    assert entity.confidence_penalty > 0.0
