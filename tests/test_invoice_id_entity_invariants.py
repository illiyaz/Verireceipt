"""
Invariant tests for Invoice ID Entity V2 to protect future refactors.
These tests enforce critical boundaries and semantic guarantees.
"""

import pytest
from app.pipelines.features import (
    build_features,
    _guess_invoice_id_entity,
    INVOICE_ID_CONFIDENCE_CAP_NUMERIC_ONLY,
    INVOICE_ID_CONFIDENCE_CAP_MULTI,
    INVOICE_ID_MAX_MARGIN,
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
    INVARIANT: Invoice ID confidence must always be in [0, 1].
    """
    test_cases = [
        "Invoice No: INV-12345",
        "Bill #: 98765",
        "Receipt: ABC123",
        "Reference: 12345",  # Numeric only
        "Random text without ID",
    ]
    
    for text in test_cases:
        lines = [text]
        result = _guess_invoice_id_entity(lines)
        
        assert 0.0 <= result.confidence <= 1.0, \
            f"Invoice ID confidence {result.confidence} out of range for: {text}"


def test_numeric_only_never_high_confidence():
    """
    INVARIANT: Numeric-only invoice IDs must never have HIGH confidence.
    
    HIGH threshold is 0.75, numeric-only cap is 0.55.
    """
    test_cases = [
        "Invoice No: 12345",
        "Bill #: 98765",
        "Receipt: 54321",
    ]
    
    for text in test_cases:
        lines = [text]
        result = _guess_invoice_id_entity(lines)
        
        # If an ID was found and it's numeric-only, confidence must be capped
        if result.value and result.evidence.get("is_numeric_only"):
            assert result.confidence <= INVOICE_ID_CONFIDENCE_CAP_NUMERIC_ONLY, \
                f"Numeric-only ID has confidence {result.confidence} > cap {INVOICE_ID_CONFIDENCE_CAP_NUMERIC_ONLY}"
            assert result.confidence_bucket != "HIGH", \
                f"Numeric-only ID has HIGH confidence bucket for: {text}"


def test_multiple_candidates_never_high_confidence():
    """
    INVARIANT: Multiple invoice ID candidates must cap confidence at MEDIUM.
    """
    text = """
    Invoice No: INV-001
    Reference: REF-002
    Bill #: BILL-003
    """
    lines = text.strip().split('\n')
    result = _guess_invoice_id_entity(lines)
    
    # If multiple candidates were found
    if result.evidence.get("total_candidates", 0) > 1:
        assert result.confidence <= INVOICE_ID_CONFIDENCE_CAP_MULTI, \
            f"Multi-candidate ID has confidence {result.confidence} > cap {INVOICE_ID_CONFIDENCE_CAP_MULTI}"


def test_evidence_always_complete():
    """
    INVARIANT: Invoice ID evidence must always have all required fields.
    """
    required_fields = {
        "total_candidates",
        "filtered_candidates",
        "winner_margin",
        "has_label",
        "has_strong_pattern",
        "is_numeric_only",
        "position_zone",
        "confidence_cap_applied"
    }
    
    test_cases = [
        "Invoice No: INV-12345",
        "Random text",
        "",
    ]
    
    for text in test_cases:
        lines = [text] if text else [""]
        result = _guess_invoice_id_entity(lines)
        
        missing_fields = required_fields - set(result.evidence.keys())
        assert not missing_fields, \
            f"Invoice ID evidence missing fields: {missing_fields} for text: {text}"


def test_invoice_id_entity_does_not_mutate_other_entities():
    """
    INVARIANT: Invoice ID extraction must not mutate or inspect other entities.
    
    This ensures entity-local isolation.
    """
    from app.pipelines.features import (
        _guess_merchant_entity,
        _guess_date_entity,
        _guess_currency_entity,
        _guess_tax_entity,
    )
    
    lines = ["Invoice No: INV-12345", "Total: $100", "Date: 2024-01-01"]
    
    # Extract all entities independently
    invoice_id_result = _guess_invoice_id_entity(lines)
    merchant_result = _guess_merchant_entity(lines)
    date_result = _guess_date_entity(lines)
    currency_result = _guess_currency_entity(lines)
    tax_result = _guess_tax_entity(lines)
    
    # Verify ML payloads are isolated
    invoice_id_ml = invoice_id_result.to_ml_dict()
    merchant_ml = merchant_result.to_ml_dict()
    date_ml = date_result.to_ml_dict()
    currency_ml = currency_result.to_ml_dict()
    tax_ml = tax_result.to_ml_dict()
    
    # Invoice ID ML should have invoice_id-specific fields
    assert "invoice_id_evidence" in invoice_id_ml
    assert "invoice_id_evidence" not in merchant_ml
    assert "invoice_id_evidence" not in date_ml
    assert "invoice_id_evidence" not in currency_ml
    assert "invoice_id_evidence" not in tax_ml
    
    # Other entities should not have invoice_id fields
    assert "has_label" not in merchant_ml.get("feature_flags", {}) or \
           merchant_ml["feature_flags"].get("has_label") != invoice_id_ml["feature_flags"].get("has_label")


def test_named_constants_enforced():
    """
    INVARIANT: All confidence caps must use named constants, not magic numbers.
    """
    # Verify constants exist and have expected values
    assert INVOICE_ID_CONFIDENCE_CAP_NUMERIC_ONLY == 0.55
    assert INVOICE_ID_CONFIDENCE_CAP_MULTI == 0.7
    assert INVOICE_ID_MAX_MARGIN == 40.0
    
    # Verify caps are applied correctly
    lines = ["Invoice: 12345"]  # Numeric only
    result = _guess_invoice_id_entity(lines)
    
    if result.value and result.evidence.get("is_numeric_only"):
        assert result.confidence <= INVOICE_ID_CONFIDENCE_CAP_NUMERIC_ONLY


def test_ml_payload_schema_version():
    """
    INVARIANT: Invoice ID ML payload must have schema_version = 2.
    
    This ensures ML payload parity with other V2 entities.
    """
    lines = ["Invoice No: INV-12345"]
    invoice_id_result = _guess_invoice_id_entity(lines)
    ml_payload = invoice_id_result.to_ml_dict()
    
    # Check schema version
    assert invoice_id_result.schema_version == 2, "Invoice ID schema_version must be 2"
    assert ml_payload.get("schema_version") == 2, "Invoice ID ML payload schema_version must be 2"
    
    # Check required ML payload fields
    assert "entity" in ml_payload
    assert "value" in ml_payload
    assert "confidence" in ml_payload
    assert "confidence_bucket" in ml_payload
    assert "winner_margin" in ml_payload
    assert "topk_gap" in ml_payload
    assert "feature_flags" in ml_payload
    assert "invoice_id_evidence" in ml_payload
    
    # Check invoice_id-specific feature flags
    feature_flags = ml_payload.get("feature_flags", {})
    invoice_id_flags = [
        "has_label",
        "has_strong_pattern",
        "is_numeric_only",
        "has_alphanumeric",
        "in_top_position",
        "multi_candidates_detected"
    ]
    
    for flag in invoice_id_flags:
        assert flag in feature_flags, f"Missing invoice_id feature flag: {flag}"
        assert isinstance(feature_flags[flag], bool), f"Feature flag {flag} must be boolean"


def test_no_high_confidence_on_fallback_paths():
    """
    INVARIANT: Fallback paths (numeric-only, multi-candidate) can never produce HIGH confidence.
    """
    # Test numeric-only fallback
    lines = ["Invoice: 12345"]
    result = _guess_invoice_id_entity(lines)
    
    if result.value and result.evidence.get("is_numeric_only"):
        assert result.confidence_bucket != "HIGH", \
            "Numeric-only fallback path produced HIGH confidence"
    
    # Test multi-candidate fallback
    lines = ["Invoice: INV-001", "Bill: BILL-002", "Ref: REF-003"]
    result = _guess_invoice_id_entity(lines)
    
    if result.evidence.get("total_candidates", 0) > 1:
        # Multi-candidate may be MEDIUM but never HIGH
        assert result.confidence <= INVOICE_ID_CONFIDENCE_CAP_MULTI


def test_build_features_integration():
    """
    INVARIANT: Invoice ID must integrate cleanly into build_features().
    """
    raw = create_test_receipt_raw("Invoice No: INV-12345\nTotal: $100")
    features = build_features(raw)
    
    # Verify invoice_id features are present in output
    text_features = features.text_features
    assert "invoice_id" in text_features
    assert "invoice_id_confidence" in text_features
    assert "invoice_id_confidence_bucket" in text_features
    assert "invoice_id_evidence" in text_features
    
    # Verify invoice_id evidence has expected structure
    invoice_id_evidence = text_features.get("invoice_id_evidence", {})
    assert isinstance(invoice_id_evidence, dict), "Invoice ID evidence must be a dict"
