"""
Invariant tests for currency entity V2 to protect future refactors.
These tests enforce critical boundaries and semantic guarantees.
"""

import pytest
from app.pipelines.features import build_features, _guess_currency_entity
from app.schemas.receipt import ReceiptRaw
from PIL import Image

# Import constants for verification
from app.pipelines.features import (
    CURRENCY_CONFIDENCE_CAP_AMBIGUOUS,
    CURRENCY_CONFIDENCE_CAP_MULTI,
    CURRENCY_TOP_ZONE_BONUS,
    CURRENCY_LABEL_BONUS,
    CURRENCY_SYMBOL_BONUS,
    CURRENCY_SYMBOLS,
    CURRENCY_CODES,
    CURRENCY_WORDS
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


def test_multiple_currencies_never_high_confidence():
    """
    INVARIANT: Multiple currencies present must never exceed MEDIUM confidence bucket
    
    This invariant protects the semantic guarantee that ambiguous currency
    situations are always treated with appropriate skepticism.
    """
    # Test multiple currency symbols
    multi_currency_patterns = [
        "Total: $15.50\nAmount: €12.00\nSubtotal: £8.75",
        "USD 100.00\nEUR 85.50\nGBP 70.25",
        "Price: $25.00\nCost: 20.00 EUR\nValue: 15.00 GBP",
        "Payment: $50.00\nRefund: 30.00 USD\nChange: 10.00 EUR"
    ]
    
    for ocr_text in multi_currency_patterns:
        raw = create_test_receipt_raw(ocr_text)
        features = build_features(raw)
        text_features = features.text_features
        
        # Verify multiple currencies detected
        evidence = text_features.get("currency_evidence", {})
        assert evidence.get("has_multiple_currencies", False), f"Multiple currencies not detected for: {ocr_text}"
        
        # Verify confidence never exceeds cap
        confidence = text_features.get("currency_confidence", 0.0)
        assert confidence <= CURRENCY_CONFIDENCE_CAP_MULTI, f"Multiple currencies confidence {confidence} exceeds cap {CURRENCY_CONFIDENCE_CAP_MULTI}"
        
        # Verify bucket is not HIGH
        bucket = text_features.get("currency_confidence_bucket", "NONE")
        assert bucket != "HIGH", f"Multiple currencies bucket {bucket} should not be HIGH for: {ocr_text}"


def test_symbol_plus_label_beats_code_only():
    """
    INVARIANT: Symbol + amount label beats code-only detection
    
    This invariant ensures that contextual currency signals are preferred
    over isolated currency codes.
    """
    # Test symbol + label vs code only
    test_cases = [
        {
            "symbol_label": "Total: $25.00",
            "code_only": "Amount: USD 25.00",
            "expected_winner": "USD"  # Both should detect USD, but symbol+label should have higher confidence
        },
        {
            "symbol_label": "Grand Total: €100.50",
            "code_only": "Payment: EUR 100.50", 
            "expected_winner": "EUR"  # Both should detect EUR, but symbol+label should win
        }
    ]
    
    for case in test_cases:
        # Test symbol + label case
        raw_symbol = create_test_receipt_raw(case["symbol_label"])
        features_symbol = build_features(raw_symbol)
        text_features_symbol = features_symbol.text_features
        
        # Test code only case
        raw_code = create_test_receipt_raw(case["code_only"])
        features_code = build_features(raw_code)
        text_features_code = features_code.text_features
        
        # Both should detect the same currency
        assert text_features_symbol.get("currency") == case["expected_winner"], f"Symbol+label failed to detect {case['expected_winner']}"
        assert text_features_code.get("currency") == case["expected_winner"], f"Code only failed to detect {case['expected_winner']}"
        
        # Symbol + label should have higher confidence
        confidence_symbol = text_features_symbol.get("currency_confidence", 0.0)
        confidence_code = text_features_code.get("currency_confidence", 0.0)
        
        assert confidence_symbol > confidence_code, f"Symbol+label confidence {confidence_symbol} should beat code-only {confidence_code}"
        
        # Symbol + label should have amount context flag
        evidence_symbol = text_features_symbol.get("currency_evidence", {})
        evidence_code = text_features_code.get("currency_evidence", {})
        
        # Check ML payload feature flags
        from app.pipelines.features import _guess_currency_entity
        lines_symbol = [case["symbol_label"]]
        lines_code = [case["code_only"]]
        
        result_symbol = _guess_currency_entity(lines_symbol)
        result_code = _guess_currency_entity(lines_code)
        
        ml_symbol = result_symbol.to_ml_dict()
        ml_code = result_code.to_ml_dict()
        
        flags_symbol = ml_symbol.get("feature_flags", {})
        flags_code = ml_code.get("feature_flags", {})
        
        assert flags_symbol.get("is_amount_context", False), f"Symbol+label should have amount context flag"
        assert flags_symbol.get("is_symbol_based", False), f"Symbol+label should have symbol-based flag"


def test_currency_isolated_from_date_merchant():
    """
    INVARIANT: Currency entity must not modify date/merchant results or ML payloads
    
    This invariant ensures entity isolation - currency extraction should not
    interfere with other entity extractions.
    """
    # Create receipt with multiple entity types
    raw = create_test_receipt_raw(
        "Starbucks Coffee\nDate: 2024-01-15\nTotal: $15.50\nThank you"
    )
    
    # Extract entities separately to establish baseline
    lines = ["Starbucks Coffee", "Date: 2024-01-15", "Total: $15.50", "Thank you"]
    
    # Get merchant entity alone
    from app.pipelines.features import _guess_merchant_entity
    merchant_result_alone = _guess_merchant_entity(lines)
    
    # Get date entity alone
    from app.pipelines.features import _guess_date_entity
    date_result_alone = _guess_date_entity(lines)
    
    # Get currency entity alone
    currency_result_alone = _guess_currency_entity(lines)
    
    # Now run full build_features
    features_full = build_features(raw)
    text_features_full = features_full.text_features
    
    # Verify merchant is unchanged
    assert text_features_full.get("merchant_candidate") == merchant_result_alone.value
    assert text_features_full.get("receipt_date_confidence") == date_result_alone.confidence
    assert text_features_full.get("currency_confidence") == currency_result_alone.confidence
    
    # Verify no cross-entity evidence contamination
    currency_evidence = text_features_full.get("currency_evidence", {})
    assert "date" not in currency_evidence.get("unique_currencies", [])
    assert "merchant" not in currency_evidence.get("unique_currencies", [])
    
    # Verify ML payloads are isolated
    merchant_ml = merchant_result_alone.to_ml_dict()
    date_ml = date_result_alone.to_ml_dict()
    currency_ml = currency_result_alone.to_ml_dict()
    
    # Currency ML should have currency-specific fields
    assert "currency_evidence" in currency_ml
    assert "currency_evidence" not in merchant_ml
    assert "currency_evidence" not in date_ml
    
    # Merchant ML should not have currency fields
    assert "is_symbol_based" not in merchant_ml.get("feature_flags", {})
    assert "is_code_based" not in merchant_ml.get("feature_flags", {})
    
    # Date ML should not have currency fields
    assert "is_symbol_based" not in date_ml.get("feature_flags", {})
    assert "is_code_based" not in date_ml.get("feature_flags", {})


def test_confidence_always_in_valid_range():
    """
    INVARIANT: Currency confidence must always be in [0,1] range
    
    This invariant ensures confidence values are always valid.
    """
    # Test various currency scenarios
    test_cases = [
        "Total: $25.00",
        "Amount: EUR 100.50", 
        "Price: £15.75",
        "Payment: USD 50.00",
        "Cost: 20.00 rupees",
        "No currency here",  # Should result in 0.0 confidence
        "Multiple: $10.00 and €8.50",  # Should be capped
        "Ambiguous: USD 25.00 dollars",  # Should be capped
    ]
    
    for ocr_text in test_cases:
        raw = create_test_receipt_raw(ocr_text)
        features = build_features(raw)
        text_features = features.text_features
        
        confidence = text_features.get("currency_confidence", 0.0)
        
        # Verify confidence is always in valid range
        assert 0.0 <= confidence <= 1.0, f"Currency confidence {confidence} outside [0,1] range for: {ocr_text}"
        
        # Verify bucket is valid
        bucket = text_features.get("currency_confidence_bucket", "NONE")
        assert bucket in ["HIGH", "MEDIUM", "LOW", "NONE"], f"Invalid bucket {bucket} for: {ocr_text}"


def test_evidence_always_complete():
    """
    INVARIANT: Currency evidence must always contain all required fields
    
    This invariant ensures evidence contract completeness.
    """
    # Test various scenarios
    test_cases = [
        "Total: $25.00",
        "No currency here",
        "Multiple: $10.00 and €8.50",
        "Amount: USD 25.00 dollars"
    ]
    
    for ocr_text in test_cases:
        raw = create_test_receipt_raw(ocr_text)
        features = build_features(raw)
        text_features = features.text_features
        
        evidence = text_features.get("currency_evidence", {})
        
        # All required fields must be present
        required_fields = [
            "winner_margin",
            "total_candidates",
            "filtered_candidates", 
            "unique_currencies",
            "has_multiple_currencies",
            "has_ambiguous_signals",
            "winner_signals"
        ]
        
        for field in required_fields:
            assert field in evidence, f"Missing required evidence field: {field} for: {ocr_text}"
        
        # Validate field types
        assert isinstance(evidence["winner_margin"], (int, float))
        assert isinstance(evidence["total_candidates"], int)
        assert isinstance(evidence["filtered_candidates"], int)
        assert isinstance(evidence["unique_currencies"], list)
        assert isinstance(evidence["has_multiple_currencies"], bool)
        assert isinstance(evidence["has_ambiguous_signals"], bool)
        assert isinstance(evidence["winner_signals"], dict)


def test_confidence_constants_are_respected():
    """
    INVARIANT: All confidence capping must respect defined constants
    
    This invariant ensures that the semantic caps defined in constants
    are actually enforced in the implementation.
    """
    # Test ambiguous currency cap
    raw_ambiguous = create_test_receipt_raw("Amount: USD 25.00 dollars")
    features_ambiguous = build_features(raw_ambiguous)
    confidence_ambiguous = features_ambiguous.text_features.get("currency_confidence", 0.0)
    assert confidence_ambiguous <= CURRENCY_CONFIDENCE_CAP_AMBIGUOUS
    
    # Test multiple currency cap
    raw_multi = create_test_receipt_raw("Total: $10.00 and €8.50")
    features_multi = build_features(raw_multi)
    confidence_multi = features_multi.text_features.get("currency_confidence", 0.0)
    assert confidence_multi <= CURRENCY_CONFIDENCE_CAP_MULTI


def test_currency_signals_detection():
    """
    INVARIANT: Currency signal detection must work for all supported types
    
    This invariant ensures all currency patterns are properly detected.
    """
    # Test symbols
    for symbol in CURRENCY_SYMBOLS:
        raw = create_test_receipt_raw(f"Total: {symbol}25.00")
        features = build_features(raw)
        currency = features.text_features.get("currency")
        assert currency is not None, f"Symbol {symbol} not detected"
    
    # Test codes
    for code in CURRENCY_CODES:
        raw = create_test_receipt_raw(f"Amount: {code} 25.00")
        features = build_features(raw)
        currency = features.text_features.get("currency")
        assert currency is not None, f"Code {code} not detected"
    
    # Test words (sample)
    word_samples = ["dollars", "rupees", "euros", "pounds", "yen"]
    for word in word_samples:
        raw = create_test_receipt_raw(f"Cost: 25.00 {word}")
        features = build_features(raw)
        currency = features.text_features.get("currency")
        assert currency is not None, f"Word {word} not detected"


def test_ml_payload_schema_version():
    """
    INVARIANT: Currency ML payload must have schema_version = 2
    
    This invariant ensures ML payload parity with other entities.
    """
    raw = create_test_receipt_raw("Total: $25.00")
    features = build_features(raw)
    
    # Get currency result directly to test ML payload
    lines = ["Total: $25.00"]
    currency_result = _guess_currency_entity(lines)
    ml_payload = currency_result.to_ml_dict()
    
    # Check schema version
    assert ml_payload.get("schema_version") == 2, "Currency ML payload schema_version must be 2"
    
    # Check required ML payload fields
    assert "entity" in ml_payload
    assert "value" in ml_payload
    assert "confidence" in ml_payload
    assert "confidence_bucket" in ml_payload
    assert "winner_margin" in ml_payload
    assert "topk_gap" in ml_payload
    assert "feature_flags" in ml_payload
    assert "currency_evidence" in ml_payload
    
    # Check currency-specific feature flags
    feature_flags = ml_payload.get("feature_flags", {})
    currency_flags = [
        "is_symbol_based",
        "is_code_based", 
        "is_word_based",
        "has_multiple_currencies",
        "has_ambiguous_signals",
        "is_amount_context"
    ]
    
    for flag in currency_flags:
        assert flag in feature_flags, f"Missing currency feature flag: {flag}"
        assert isinstance(feature_flags[flag], bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
