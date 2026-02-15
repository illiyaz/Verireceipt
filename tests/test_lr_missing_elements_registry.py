#!/usr/bin/env python3
"""
Regression test for LR_MISSING_ELEMENTS signal registry bug fix.

Ensures:
1. LR_MISSING_ELEMENTS is registered in SignalRegistry
2. LR_SPACING_ANOMALY is registered in SignalRegistry
3. LR_INVALID_ADDRESS is registered in SignalRegistry
4. No typo variants (e.g., LR_MISSING_ELELEMTNS) are emitted
5. Registry validation catches unregistered signals
"""

import pytest
from app.schemas.receipt import SignalRegistry, SignalV1


def test_lr_missing_elements_registered():
    """Test that LR_MISSING_ELEMENTS is registered in SignalRegistry."""
    assert SignalRegistry.is_allowed("LR_MISSING_ELEMENTS"), (
        "LR_MISSING_ELEMENTS must be registered in SignalRegistry"
    )
    
    spec = SignalRegistry.get_spec("LR_MISSING_ELEMENTS")
    assert spec is not None, "LR_MISSING_ELEMENTS spec must exist"
    assert spec.name == "LR_MISSING_ELEMENTS", "Signal name must match"
    assert spec.domain == "learned_rules", "Domain must be learned_rules"
    assert spec.version == "v1", "Version must be v1"


def test_lr_spacing_anomaly_registered():
    """Test that LR_SPACING_ANOMALY is registered in SignalRegistry."""
    assert SignalRegistry.is_allowed("LR_SPACING_ANOMALY"), (
        "LR_SPACING_ANOMALY must be registered in SignalRegistry"
    )
    
    spec = SignalRegistry.get_spec("LR_SPACING_ANOMALY")
    assert spec is not None, "LR_SPACING_ANOMALY spec must exist"
    assert spec.name == "LR_SPACING_ANOMALY", "Signal name must match"
    assert spec.domain == "learned_rules", "Domain must be learned_rules"


def test_lr_invalid_address_registered():
    """Test that LR_INVALID_ADDRESS is registered in SignalRegistry."""
    assert SignalRegistry.is_allowed("LR_INVALID_ADDRESS"), (
        "LR_INVALID_ADDRESS must be registered in SignalRegistry"
    )
    
    spec = SignalRegistry.get_spec("LR_INVALID_ADDRESS")
    assert spec is not None, "LR_INVALID_ADDRESS spec must exist"
    assert spec.name == "LR_INVALID_ADDRESS", "Signal name must match"
    assert spec.domain == "learned_rules", "Domain must be learned_rules"


def test_typo_variant_not_registered():
    """Test that typo variants are NOT registered (e.g., LR_MISSING_ELELEMTNS)."""
    # Common typo variants that should NOT be registered
    typo_variants = [
        "LR_MISSING_ELELEMTNS",  # Double L typo
        "LR_MISSING_ELEMTNS",    # Missing E
        "LR_MISSING_ELEMNTS",    # Transposed N and T
        "LR_MISSNG_ELEMENTS",    # Missing I
    ]
    
    for typo in typo_variants:
        assert not SignalRegistry.is_allowed(typo), (
            f"Typo variant '{typo}' should NOT be registered in SignalRegistry"
        )


def test_registry_validation_rejects_unregistered():
    """Test that SignalRegistry.is_allowed rejects unregistered signals."""
    # Test some obviously unregistered signal names
    unregistered_signals = [
        "FAKE_SIGNAL",
        "LR_MISSING_ELELEMTNS",  # Typo variant
        "random.signal",
        "LR_UNKNOWN_PATTERN",
    ]
    
    for signal_name in unregistered_signals:
        assert not SignalRegistry.is_allowed(signal_name), (
            f"Unregistered signal '{signal_name}' should be rejected by registry"
        )


def test_learned_rules_domain_signals():
    """Test that all learned_rules domain signals are registered."""
    learned_rules_signals = SignalRegistry.get_by_domain("learned_rules")
    
    assert len(learned_rules_signals) >= 3, (
        "At least 3 learned_rules signals should be registered"
    )
    
    # Verify expected signals are present
    signal_names = {spec.name for spec in learned_rules_signals}
    expected_signals = {
        "LR_SPACING_ANOMALY",
        "LR_MISSING_ELEMENTS",
        "LR_INVALID_ADDRESS",
    }
    
    assert expected_signals.issubset(signal_names), (
        f"Expected signals {expected_signals} not all present in {signal_names}"
    )


def test_signal_v1_creation_with_lr_signals():
    """Test that SignalV1 can be created with LR signal names."""
    # Test creating SignalV1 with LR_MISSING_ELEMENTS
    signal = SignalV1(
        name="LR_MISSING_ELEMENTS",
        status="TRIGGERED",
        confidence=0.75,
        evidence={
            "missing": ["total", "merchant"],
            "pattern": "missing_elements",
        },
        interpretation="Critical elements missing from document",
    )
    
    assert signal.name == "LR_MISSING_ELEMENTS"
    assert signal.status == "TRIGGERED"
    assert signal.confidence == 0.75
    assert "missing" in signal.evidence
    
    # Verify this signal is allowed by registry
    assert SignalRegistry.is_allowed(signal.name), (
        f"Signal {signal.name} should be allowed by registry"
    )


def test_canonical_name_consistency():
    """Test that canonical name LR_MISSING_ELEMENTS is used consistently."""
    # Get the spec
    spec = SignalRegistry.get_spec("LR_MISSING_ELEMENTS")
    
    # Verify the spec name matches the registry key
    assert spec.name == "LR_MISSING_ELEMENTS", (
        "Spec name must match registry key (canonical name)"
    )
    
    # Verify description mentions it's a learned pattern
    assert "learned" in spec.description.lower(), (
        "Description should mention this is a learned pattern"
    )
    
    # Verify it has proper gating
    assert "doc_profile_confidence" in spec.gated_by, (
        "LR_MISSING_ELEMENTS should be gated by doc_profile_confidence"
    )


if __name__ == "__main__":
    print("Running LR_MISSING_ELEMENTS registry regression tests...")
    
    try:
        test_lr_missing_elements_registered()
        print("✓ LR_MISSING_ELEMENTS registered")
        
        test_lr_spacing_anomaly_registered()
        print("✓ LR_SPACING_ANOMALY registered")
        
        test_lr_invalid_address_registered()
        print("✓ LR_INVALID_ADDRESS registered")
        
        test_typo_variant_not_registered()
        print("✓ Typo variants not registered")
        
        test_registry_validation_rejects_unregistered()
        print("✓ Registry validation rejects unregistered signals")
        
        test_learned_rules_domain_signals()
        print("✓ Learned rules domain signals present")
        
        test_signal_v1_creation_with_lr_signals()
        print("✓ SignalV1 creation with LR signals works")
        
        test_canonical_name_consistency()
        print("✓ Canonical name consistency verified")
        
        print("\n✅ All LR_MISSING_ELEMENTS registry tests passed!")
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        raise
