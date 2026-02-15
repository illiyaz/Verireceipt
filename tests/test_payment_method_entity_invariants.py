"""
Invariant tests for Payment Method Entity V2 to protect future refactors.
These tests enforce critical boundaries and semantic guarantees.
"""

import pytest
from app.pipelines.features import (
    build_features,
    _guess_payment_method_entity,
    PAYMENT_METHOD_CONFIDENCE_CAP_INFERRED,
    PAYMENT_METHOD_CONFIDENCE_CAP_MULTI,
    PAYMENT_METHOD_MAX_MARGIN,
)
from app.schemas.receipt import ReceiptRaw
from PIL import Image


def create_test_receipt_raw(ocr_text: str) -> ReceiptRaw:
    """Helper to create a minimal ReceiptRaw for testing."""
    dummy_image = Image.new('RGB', (1, 1), color='white')
    
    return ReceiptRaw(
        images=[dummy_image],
        ocr_text_per_page=[ocr_text],
        pdf_metadata={"file_path": "test_receipt.pdf"},
        file_size_bytes=1024,
        num_pages=1
    )


def test_confidence_always_in_valid_range():
    """
    INVARIANT: Payment method confidence must always be in [0, 1].
    """
    test_cases = [
        "Paid via UPI",
        "Payment Mode: Cash",
        "Card payment",
        "Random text without payment info",
    ]
    
    for text in test_cases:
        lines = [text]
        result = _guess_payment_method_entity(lines)
        
        assert 0.0 <= result.confidence <= 1.0, \
            f"Payment method confidence {result.confidence} out of range for: {text}"


def test_inferred_only_never_high_confidence():
    """
    INVARIANT: Inferred-only payment methods (keyword without phrase) must never have HIGH confidence.
    
    HIGH threshold is 0.75, inferred-only cap is 0.4.
    """
    test_cases = [
        "Cash",  # Keyword only, no phrase
        "Card",
        "UPI",
    ]
    
    for text in test_cases:
        lines = [text]
        result = _guess_payment_method_entity(lines)
        
        # If a method was found and it's inferred-only
        if result.value and result.evidence.get("is_inferred"):
            assert result.confidence <= PAYMENT_METHOD_CONFIDENCE_CAP_INFERRED, \
                f"Inferred-only method has confidence {result.confidence} > cap {PAYMENT_METHOD_CONFIDENCE_CAP_INFERRED}"
            assert result.confidence_bucket != "HIGH", \
                f"Inferred-only method has HIGH confidence bucket for: {text}"


def test_multiple_candidates_never_high_confidence():
    """
    INVARIANT: Multiple payment method candidates must cap confidence at MEDIUM.
    """
    text = """
    Paid via Cash
    Payment Mode: Card
    UPI Payment
    """
    lines = text.strip().split('\n')
    result = _guess_payment_method_entity(lines)
    
    # If multiple candidates were found
    if result.evidence.get("total_candidates", 0) > 1:
        assert result.confidence <= PAYMENT_METHOD_CONFIDENCE_CAP_MULTI, \
            f"Multi-candidate method has confidence {result.confidence} > cap {PAYMENT_METHOD_CONFIDENCE_CAP_MULTI}"


def test_evidence_always_complete():
    """
    INVARIANT: Payment method evidence must always have all required fields.
    """
    required_fields = {
        "total_candidates",
        "filtered_candidates",
        "winner_margin",
        "has_phrase",
        "has_keyword",
        "is_inferred",
        "position_zone",
        "confidence_cap_applied"
    }
    
    test_cases = [
        "Paid via UPI",
        "Random text",
        "",
    ]
    
    for text in test_cases:
        lines = [text] if text else [""]
        result = _guess_payment_method_entity(lines)
        
        missing_fields = required_fields - set(result.evidence.keys())
        assert not missing_fields, \
            f"Payment method evidence missing fields: {missing_fields} for text: {text}"


def test_payment_method_entity_does_not_mutate_other_entities():
    """
    INVARIANT: Payment method extraction must not mutate or inspect other entities.
    """
    from app.pipelines.features import (
        _guess_merchant_entity,
        _guess_date_entity,
        _guess_invoice_id_entity,
        _guess_tax_entity,
    )
    
    lines = ["Paid via UPI", "Total: $100", "Invoice: INV-001"]
    
    # Extract all entities independently
    payment_method_result = _guess_payment_method_entity(lines)
    merchant_result = _guess_merchant_entity(lines)
    date_result = _guess_date_entity(lines)
    invoice_id_result = _guess_invoice_id_entity(lines)
    tax_result = _guess_tax_entity(lines)
    
    # Verify ML payloads are isolated
    payment_method_ml = payment_method_result.to_ml_dict()
    merchant_ml = merchant_result.to_ml_dict()
    date_ml = date_result.to_ml_dict()
    invoice_id_ml = invoice_id_result.to_ml_dict()
    tax_ml = tax_result.to_ml_dict()
    
    # Payment method ML should have payment_method-specific fields
    assert "payment_method_evidence" in payment_method_ml
    assert "payment_method_evidence" not in merchant_ml
    assert "payment_method_evidence" not in date_ml
    assert "payment_method_evidence" not in invoice_id_ml
    assert "payment_method_evidence" not in tax_ml


def test_named_constants_enforced():
    """
    INVARIANT: All confidence caps must use named constants, not magic numbers.
    """
    # Verify constants exist and have expected values
    assert PAYMENT_METHOD_CONFIDENCE_CAP_INFERRED == 0.4
    assert PAYMENT_METHOD_CONFIDENCE_CAP_MULTI == 0.7
    assert PAYMENT_METHOD_MAX_MARGIN == 40.0
    
    # Verify caps are applied correctly
    lines = ["Cash"]  # Inferred only
    result = _guess_payment_method_entity(lines)
    
    if result.value and result.evidence.get("is_inferred"):
        assert result.confidence <= PAYMENT_METHOD_CONFIDENCE_CAP_INFERRED


def test_ml_payload_schema_version():
    """
    INVARIANT: Payment method ML payload must have schema_version = 2.
    """
    lines = ["Paid via UPI"]
    payment_method_result = _guess_payment_method_entity(lines)
    ml_payload = payment_method_result.to_ml_dict()
    
    # Check schema version
    assert payment_method_result.schema_version == 2, "Payment method schema_version must be 2"
    assert ml_payload.get("schema_version") == 2, "Payment method ML payload schema_version must be 2"
    
    # Check required ML payload fields
    assert "entity" in ml_payload
    assert "value" in ml_payload
    assert "confidence" in ml_payload
    assert "confidence_bucket" in ml_payload
    assert "feature_flags" in ml_payload
    assert "payment_method_evidence" in ml_payload
    
    # Check payment_method-specific feature flags
    feature_flags = ml_payload.get("feature_flags", {})
    payment_method_flags = [
        "has_phrase",
        "has_keyword",
        "is_inferred",
        "in_bottom_position",
        "multi_methods_detected"
    ]
    
    for flag in payment_method_flags:
        assert flag in feature_flags, f"Missing payment_method feature flag: {flag}"
        assert isinstance(feature_flags[flag], bool), f"Feature flag {flag} must be boolean"


def test_no_high_confidence_on_fallback_paths():
    """
    INVARIANT: Fallback paths (inferred-only, multi-candidate) can never produce HIGH confidence.
    """
    # Test inferred-only fallback
    lines = ["Cash"]
    result = _guess_payment_method_entity(lines)
    
    if result.value and result.evidence.get("is_inferred"):
        assert result.confidence_bucket != "HIGH", \
            "Inferred-only fallback path produced HIGH confidence"
    
    # Test multi-candidate fallback
    lines = ["Paid via Cash", "Payment: Card", "UPI"]
    result = _guess_payment_method_entity(lines)
    
    if result.evidence.get("total_candidates", 0) > 1:
        assert result.confidence <= PAYMENT_METHOD_CONFIDENCE_CAP_MULTI


def test_build_features_integration():
    """
    INVARIANT: Payment method must integrate cleanly into build_features().
    """
    raw = create_test_receipt_raw("Paid via UPI\nTotal: $100")
    features = build_features(raw)
    
    # Verify payment_method features are present in output
    text_features = features.text_features
    assert "payment_method" in text_features
    assert "payment_method_confidence" in text_features
    assert "payment_method_confidence_bucket" in text_features
    assert "payment_method_evidence" in text_features
    
    # Verify payment_method evidence has expected structure
    payment_method_evidence = text_features.get("payment_method_evidence", {})
    assert isinstance(payment_method_evidence, dict), "Payment method evidence must be a dict"
