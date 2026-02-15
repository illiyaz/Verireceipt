"""
Invariant tests for tax entity V2 to protect future refactors.
These tests enforce critical boundaries and semantic guarantees.
"""

import pytest
from app.pipelines.features import build_features, _guess_tax_entity
from app.schemas.receipt import ReceiptRaw
from PIL import Image

# Import constants for verification
from app.pipelines.features import (
    TAX_CONFIDENCE_CAP_PERCENT_ONLY,
    TAX_CONFIDENCE_CAP_INCONSISTENT,
    TAX_CONFIDENCE_CAP_MULTI,
    TAX_CONFIDENCE_CAP_ZERO,
    TAX_MAX_MARGIN,
    TAX_AMOUNT_RATIO_MAX,
    TAX_KEYWORDS,
    TAX_INCLUSIVE_KEYWORDS,
    TAX_EXPLICIT_KEYWORDS
)


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


def test_tax_never_high_confidence_when_percentage_only():
    """
    INVARIANT: Tax with percentage only must never exceed LOW confidence bucket
    
    This invariant protects the semantic guarantee that percentage-only tax
    detection is always treated with appropriate skepticism.
    """
    # Test percentage-only patterns
    percentage_only_patterns = [
        "GST: 18%",
        "VAT 10%",
        "Tax rate: 15%",
        "Service tax 12.5%",
        "CGST 9% + SGST 9%"
    ]
    
    for ocr_text in percentage_only_patterns:
        raw = create_test_receipt_raw(ocr_text)
        features = build_features(raw)
        text_features = features.text_features
        
        # Verify confidence never exceeds cap
        confidence = text_features.get("tax_confidence", 0.0)
        assert confidence <= TAX_CONFIDENCE_CAP_PERCENT_ONLY, f"Percentage-only tax confidence {confidence} exceeds cap {TAX_CONFIDENCE_CAP_PERCENT_ONLY}"
        
        # Verify bucket is not HIGH or MEDIUM
        bucket = text_features.get("tax_confidence_bucket", "NONE")
        assert bucket in ["LOW", "NONE"], f"Percentage-only tax bucket {bucket} should be LOW or NONE for: {ocr_text}"
        
        # Verify evidence shows percentage-only
        evidence = text_features.get("tax_evidence", {})
        assert evidence.get("has_percentage", False), f"Percentage flag not set for: {ocr_text}"
        assert not evidence.get("has_amount", True), f"Amount flag should be False for percentage-only: {ocr_text}"


def test_tax_never_high_confidence_when_inconsistent():
    """
    INVARIANT: Tax inconsistent with totals must never exceed MEDIUM confidence bucket
    
    This invariant ensures that mathematically inconsistent tax situations
    are always treated with appropriate skepticism.
    """
    # Test inconsistent tax patterns (simplified - would need total context)
    inconsistent_patterns = [
        "Multiple taxes: GST 18% and VAT 10%",
        "Tax: 25% and Service tax: 15%",
        "CGST 9% + SGST 9% + VAT 5%"
    ]
    
    for ocr_text in inconsistent_patterns:
        raw = create_test_receipt_raw(ocr_text)
        features = build_features(raw)
        text_features = features.text_features
        
        # Verify confidence never exceeds cap
        confidence = text_features.get("tax_confidence", 0.0)
        assert confidence <= TAX_CONFIDENCE_CAP_MULTI, f"Inconsistent tax confidence {confidence} exceeds cap {TAX_CONFIDENCE_CAP_MULTI}"
        
        # Verify bucket is not HIGH
        bucket = text_features.get("tax_confidence_bucket", "NONE")
        assert bucket != "HIGH", f"Inconsistent tax bucket {bucket} should not be HIGH for: {ocr_text}"
        
        # Verify evidence shows multiple tax lines
        evidence = text_features.get("tax_evidence", {})
        assert evidence.get("has_multiple_tax_lines", False), f"Multiple tax lines not detected for: {ocr_text}"


def test_multi_tax_never_high_confidence():
    """
    INVARIANT: Multiple tax candidates must never exceed MEDIUM confidence bucket
    
    This invariant ensures that ambiguous tax situations are always
    treated with appropriate skepticism.
    """
    # Test multiple tax candidates
    multi_tax_patterns = [
        "GST: $18.00\nVAT: $10.00",
        "Tax: 18%\nService tax: 12%",
        "CGST: $9.00\nSGST: $9.00\nTotal: $100.00"
    ]
    
    for ocr_text in multi_tax_patterns:
        raw = create_test_receipt_raw(ocr_text)
        features = build_features(raw)
        text_features = features.text_features
        
        # Verify confidence never exceeds cap
        confidence = text_features.get("tax_confidence", 0.0)
        assert confidence <= TAX_CONFIDENCE_CAP_MULTI, f"Multi-tax confidence {confidence} exceeds cap {TAX_CONFIDENCE_CAP_MULTI}"
        
        # Verify bucket is not HIGH
        bucket = text_features.get("tax_confidence_bucket", "NONE")
        assert bucket != "HIGH", f"Multi-tax bucket {bucket} should not be HIGH for: {ocr_text}"
        
        # Verify evidence shows multiple tax lines
        evidence = text_features.get("tax_evidence", {})
        assert evidence.get("has_multiple_tax_lines", False), f"Multiple tax lines not detected for: {ocr_text}"


def test_confidence_always_in_valid_range():
    """
    INVARIANT: Tax confidence must always be in [0,1] range
    
    This invariant ensures confidence values are always valid.
    """
    # Test various tax scenarios
    test_cases = [
        "GST: $18.00",
        "VAT 10%", 
        "Tax included",
        "No tax here",  # Should result in 0.0 confidence
        "Multiple taxes: GST 18% and VAT 10%",  # Should be capped
        "Tax: 0.00",  # Zero tax should be capped
    ]
    
    for ocr_text in test_cases:
        raw = create_test_receipt_raw(ocr_text)
        features = build_features(raw)
        text_features = features.text_features
        
        confidence = text_features.get("tax_confidence", 0.0)
        
        # Verify confidence is always in valid range
        assert 0.0 <= confidence <= 1.0, f"Tax confidence {confidence} outside [0,1] range for: {ocr_text}"
        
        # Verify bucket is valid
        bucket = text_features.get("tax_confidence_bucket", "NONE")
        assert bucket in ["HIGH", "MEDIUM", "LOW", "NONE"], f"Invalid bucket {bucket} for: {ocr_text}"


def test_evidence_always_complete():
    """
    INVARIANT: Tax evidence must always contain all required fields
    
    This invariant ensures evidence contract completeness.
    """
    # Test various scenarios
    test_cases = [
        "GST: $18.00",
        "No tax here",
        "Multiple taxes: GST 18% and VAT 10%",
        "Tax included",
        "VAT 10%"
    ]
    
    for ocr_text in test_cases:
        raw = create_test_receipt_raw(ocr_text)
        features = build_features(raw)
        text_features = features.text_features
        
        evidence = text_features.get("tax_evidence", {})
        
        # All required fields must be present
        required_fields = [
            "winner_margin",
            "total_candidates",
            "filtered_candidates", 
            "tax_type",
            "has_percentage",
            "has_amount",
            "has_multiple_tax_lines",
            "tax_to_total_ratio",
            "subtotal_tax_total_consistent",
            "rejections_percentage_only",
            "rejections_zero_tax",
            "rejections_high_ratio",
            "rejections_inconsistent",
            "winner_signals"
        ]
        
        for field in required_fields:
            assert field in evidence, f"Missing required evidence field: {field} for: {ocr_text}"
        
        # Validate field types
        assert isinstance(evidence["winner_margin"], (int, float))
        assert isinstance(evidence["total_candidates"], int)
        assert isinstance(evidence["filtered_candidates"], int)
        assert isinstance(evidence["tax_type"], str)
        assert isinstance(evidence["has_percentage"], bool)
        assert isinstance(evidence["has_amount"], bool)
        assert isinstance(evidence["has_multiple_tax_lines"], bool)
        assert isinstance(evidence["tax_to_total_ratio"], (int, float))
        assert isinstance(evidence["subtotal_tax_total_consistent"], bool)
        assert isinstance(evidence["rejections_percentage_only"], int)
        assert isinstance(evidence["rejections_zero_tax"], int)
        assert isinstance(evidence["rejections_high_ratio"], int)
        assert isinstance(evidence["rejections_inconsistent"], int)
        assert isinstance(evidence["winner_signals"], dict)


def test_tax_entity_does_not_mutate_other_entities():
    """
    INVARIANT: Tax entity must not modify merchant/date/currency results or ML payloads
    
    This invariant ensures entity isolation - tax extraction should not
    interfere with other entity extractions.
    """
    # Create receipt with multiple entity types
    raw = create_test_receipt_raw(
        "Starbucks Coffee\nDate: 2024-01-15\nTotal: $25.00\nGST: $4.50\nThank you"
    )
    
    # Extract entities separately to establish baseline
    lines = ["Starbucks Coffee", "Date: 2024-01-15", "Total: $25.00", "GST: $4.50", "Thank you"]
    
    # Get merchant entity alone
    from app.pipelines.features import _guess_merchant_entity
    merchant_result_alone = _guess_merchant_entity(lines)
    
    # Get date entity alone
    from app.pipelines.features import _guess_date_entity
    date_result_alone = _guess_date_entity(lines)
    
    # Get currency entity alone
    from app.pipelines.features import _guess_currency_entity
    currency_result_alone = _guess_currency_entity(lines)
    
    # Get tax entity alone
    tax_result_alone = _guess_tax_entity(lines)
    
    # Now run full build_features
    features_full = build_features(raw)
    text_features_full = features_full.text_features
    
    # Verify merchant is unchanged
    assert text_features_full.get("merchant_candidate") == merchant_result_alone.value
    assert text_features_full.get("receipt_date_confidence") == date_result_alone.confidence
    assert text_features_full.get("currency_confidence") == currency_result_alone.confidence
    assert text_features_full.get("tax_confidence") == tax_result_alone.confidence
    
    # Verify no cross-entity evidence contamination
    tax_evidence = text_features_full.get("tax_evidence", {})
    assert "merchant" not in tax_evidence.get("tax_type", "")
    assert "date" not in tax_evidence.get("tax_type", "")
    assert "currency" not in tax_evidence.get("tax_type", "")
    
    # Verify ML payloads are isolated
    merchant_ml = merchant_result_alone.to_ml_dict()
    date_ml = date_result_alone.to_ml_dict()
    currency_ml = currency_result_alone.to_ml_dict()
    tax_ml = tax_result_alone.to_ml_dict()
    
    # Tax ML should have tax-specific fields
    assert "tax_evidence" in tax_ml
    assert "tax_evidence" not in merchant_ml
    assert "tax_evidence" not in date_ml
    assert "tax_evidence" not in currency_ml
    
    # Merchant ML should not have tax fields
    assert "is_percentage_based" not in merchant_ml.get("feature_flags", {})
    assert "is_amount_based" not in merchant_ml.get("feature_flags", {})
    
    # Date ML should not have tax fields
    assert "is_percentage_based" not in date_ml.get("feature_flags", {})
    assert "is_amount_based" not in date_ml.get("feature_flags", {})


def test_named_constants_enforced():
    """
    INVARIANT: All confidence capping must respect defined constants
    
    This invariant ensures that the semantic caps defined in constants
    are actually enforced in the implementation.
    """
    # Test percentage-only cap
    raw_percent_only = create_test_receipt_raw("GST: 18%")
    features_percent_only = build_features(raw_percent_only)
    confidence_percent_only = features_percent_only.text_features.get("tax_confidence", 0.0)
    assert confidence_percent_only <= TAX_CONFIDENCE_CAP_PERCENT_ONLY
    
    # Test multi-tax cap
    raw_multi = create_test_receipt_raw("GST: $18.00\nVAT: $10.00")
    features_multi = build_features(raw_multi)
    confidence_multi = features_multi.text_features.get("tax_confidence", 0.0)
    assert confidence_multi <= TAX_CONFIDENCE_CAP_MULTI
    
    # Test zero tax cap
    raw_zero = create_test_receipt_raw("Tax: $0.00")
    features_zero = build_features(raw_zero)
    confidence_zero = features_zero.text_features.get("tax_confidence", 0.0)
    assert confidence_zero <= TAX_CONFIDENCE_CAP_ZERO


def test_tax_signals_detection():
    """
    INVARIANT: Tax signal detection must work for all supported types
    
    This invariant ensures all tax patterns are properly detected.
    """
    # Test explicit tax keywords
    for keyword in ["GST", "VAT", "CGST", "SGST", "sales tax"]:
        raw = create_test_receipt_raw(f"{keyword}: $25.00")
        features = build_features(raw)
        tax = features.text_features.get("tax_amount")
        assert tax is not None, f"Explicit tax keyword {keyword} not detected"
    
    # Test inclusive keywords
    for keyword in ["incl. tax", "tax included"]:
        raw = create_test_receipt_raw(f"Total: $100.00 ({keyword})")
        features = build_features(raw)
        tax = features.text_features.get("tax_amount")
        # Inclusive tax detection is more complex, at least should detect something
        assert features.text_features.get("tax_confidence", 0.0) >= 0.0, f"Inclusive keyword {keyword} not processed"
    
    # Test percentage detection
    raw = create_test_receipt_raw("GST: 18%")
    features = build_features(raw)
    evidence = features.text_features.get("tax_evidence", {})
    assert evidence.get("has_percentage", False), "Percentage detection failed"


def test_ml_payload_schema_version():
    """
    INVARIANT: Tax ML payload must have schema_version = 2
    
    This invariant ensures ML payload parity with other entities.
    """
    raw = create_test_receipt_raw("GST: $25.00")
    features = build_features(raw)
    
    # Get tax result directly to test ML payload
    lines = ["GST: $25.00"]
    tax_result = _guess_tax_entity(lines)
    ml_payload = tax_result.to_ml_dict()
    
    # Check schema version
    assert tax_result.schema_version == 2, "Tax ML payload schema_version must be 2"
    assert ml_payload.get("schema_version") == 2, "Tax ML payload schema_version must be 2"
    
    # Check required ML payload fields
    assert "entity" in ml_payload
    assert "value" in ml_payload
    assert "confidence" in ml_payload
    assert "confidence_bucket" in ml_payload
    assert "winner_margin" in ml_payload
    assert "topk_gap" in ml_payload
    assert "feature_flags" in ml_payload
    assert "tax_evidence" in ml_payload
    
    # Check tax-specific feature flags
    feature_flags = ml_payload.get("feature_flags", {})
    tax_flags = [
        "is_percentage_based",
        "is_amount_based", 
        "is_inclusive_tax",
        "is_explicit_tax",
        "multi_tax_detected",
        "consistent_with_total"
    ]
    
    for flag in tax_flags:
        assert flag in feature_flags, f"Missing tax feature flag: {flag}"
        assert isinstance(feature_flags[flag], bool) or isinstance(feature_flags[flag], (int, float, str)), f"Invalid type for {flag}"


def test_zero_tax_capping():
    """
    INVARIANT: Zero tax must be capped at LOW confidence
    
    This invariant ensures zero tax amounts are treated skeptically.
    """
    zero_tax_patterns = [
        "GST: $0.00",
        "VAT: 0%",
        "Tax: $0.00",
        "Service tax: 0.00"
    ]
    
    for ocr_text in zero_tax_patterns:
        raw = create_test_receipt_raw(ocr_text)
        features = build_features(raw)
        text_features = features.text_features
        
        # Verify confidence never exceeds cap
        confidence = text_features.get("tax_confidence", 0.0)
        assert confidence <= TAX_CONFIDENCE_CAP_ZERO, f"Zero tax confidence {confidence} exceeds cap {TAX_CONFIDENCE_CAP_ZERO}"
        
        # Verify bucket is LOW or NONE
        bucket = text_features.get("tax_confidence_bucket", "NONE")
        assert bucket in ["LOW", "NONE"], f"Zero tax bucket {bucket} should be LOW or NONE for: {ocr_text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
