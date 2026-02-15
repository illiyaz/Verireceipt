"""
Test hardened date entity extraction integration in build_features().
"""

import pytest
import re
from app.pipelines.features import build_features
from app.schemas.receipt import ReceiptRaw
from PIL import Image
import io


def create_test_receipt_raw(ocr_text: str) -> ReceiptRaw:
    """Helper to create a minimal ReceiptRaw for testing."""
    # Create a dummy 1x1 image
    dummy_image = Image.new('RGB', (1, 1), color='white')
    
    return ReceiptRaw(
        images=[dummy_image],
        ocr_text_per_page=[ocr_text],
        pdf_metadata={"file_path": "test_receipt.pdf"},
        file_size_bytes=1024,
        num_pages=1
    )


def test_date_entity_normalization():
    """Test that dates are normalized to ISO-8601 format."""
    raw = create_test_receipt_raw(
        "Invoice\nJan 31, 2024\nTotal: $100.00"
    )
    
    features = build_features(raw)
    text_features = features.text_features
    
    # Should normalize to ISO format
    assert text_features.get("receipt_date") == "2024-01-31"
    assert text_features.get("receipt_date_confidence") > 0.0
    
    # Evidence should contain both raw and normalized values
    evidence = text_features.get("receipt_date_evidence", {})
    assert evidence.get("raw_value") == "Jan 31, 2024"
    assert evidence.get("normalized_value") == "2024-01-31"


def test_date_entity_type_classification():
    """Test date type classification and confidence capping."""
    # Test due date (should be capped at LOW)
    raw_due = create_test_receipt_raw(
        "Receipt\nDue Date: 2024-01-15\nTotal: $50.00"
    )
    
    features_due = build_features(raw_due)
    text_features_due = features_due.text_features
    
    assert text_features_due.get("receipt_date") == "2024-01-15"
    assert text_features_due.get("receipt_date_confidence_bucket") == "LOW"
    assert text_features_due.get("receipt_date_confidence") <= 0.4
    
    evidence_due = text_features_due.get("receipt_date_evidence", {})
    assert evidence_due.get("date_type") == "due_date"
    
    # Test transaction date (should have higher confidence)
    raw_trans = create_test_receipt_raw(
        "Receipt\nDate: 2024-01-15\nTotal: $50.00"
    )
    
    features_trans = build_features(raw_trans)
    text_features_trans = features_trans.text_features
    
    assert text_features_trans.get("receipt_date") == "2024-01-15"
    evidence_trans = text_features_trans.get("receipt_date_evidence", {})
    assert evidence_trans.get("date_type") == "transaction_date"


def test_date_entity_multiple_dates_conflict():
    """Test handling of multiple dates with conflicts."""
    raw = create_test_receipt_raw(
        "Invoice\nInvoice Date: 2024-01-15\nDue Date: 2024-02-15\nTotal: $100.00"
    )
    
    features = build_features(raw)
    text_features = features.text_features
    
    # Should prefer invoice date over due date
    assert text_features.get("receipt_date") == "2024-01-15"
    
    evidence = text_features.get("receipt_date_evidence", {})
    assert evidence.get("date_type") == "invoice_date"
    
    # Check conflict detection
    conflict = evidence.get("date_conflict", {})
    assert conflict is not None
    assert "invoice_date" in conflict.get("types_seen", [])
    assert "due_date" in conflict.get("types_seen", [])
    assert conflict.get("resolution") == "preferred_transaction_date"
    
    # Should have multiple candidates
    assert evidence.get("total_candidates") >= 2
    
    # Check that ML payload would have the right flags
    from app.pipelines.features import _guess_date_entity
    lines = ["Invoice", "Invoice Date: 2024-01-15", "Due Date: 2024-02-15", "Total: $100.00"]
    date_result = _guess_date_entity(lines)
    ml_payload = date_result.to_ml_dict()
    feature_flags = ml_payload.get("feature_flags", {})
    assert feature_flags.get("has_multiple_dates") == True
    assert feature_flags.get("is_invoice_date") == True
    assert feature_flags.get("is_due_date") == False  # Winner is invoice date


def test_date_entity_far_apart_conflict():
    """Test confidence capping for far-apart conflicting dates."""
    raw = create_test_receipt_raw(
        "Receipt\nDate: 2024-01-15\nDelivery Date: 2024-04-15\nTotal: $75.00"
    )
    
    features = build_features(raw)
    text_features = features.text_features
    
    evidence = text_features.get("receipt_date_evidence", {})
    conflict = evidence.get("date_conflict", {})
    
    # Should detect far-apart dates (>30 days)
    assert conflict.get("has_far_apart_dates", False)
    # Resolution should be preferred_transaction_date since we have transaction vs delivery
    assert conflict.get("resolution") == "preferred_transaction_date"
    
    # Confidence should be capped (transaction date wins but with penalty due to conflict)
    assert text_features.get("receipt_date_confidence_bucket") in ["LOW", "MEDIUM"]
    assert text_features.get("receipt_date_confidence") <= 0.7


def test_date_entity_evidence_completeness():
    """Test that evidence always contains all required fields."""
    raw = create_test_receipt_raw(
        "Receipt\nDate: 2024-01-15\nTotal: $25.00"
    )
    
    features = build_features(raw)
    text_features = features.text_features
    evidence = text_features.get("receipt_date_evidence", {})
    
    # All required fields must be present
    required_fields = [
        "winner_margin",
        "total_candidates", 
        "filtered_candidates",
        "raw_value",
        "normalized_value",
        "date_type",
        "date_conflict"
    ]
    
    for field in required_fields:
        assert field in evidence, f"Missing required evidence field: {field}"
    
    # Validate field types
    assert isinstance(evidence["winner_margin"], (int, float))
    assert isinstance(evidence["total_candidates"], int)
    assert isinstance(evidence["filtered_candidates"], int)
    assert isinstance(evidence["raw_value"], (str, type(None)))
    assert isinstance(evidence["normalized_value"], (str, type(None)))
    assert isinstance(evidence["date_type"], str)
    assert evidence["date_conflict"] is None or isinstance(evidence["date_conflict"], dict)


def test_date_entity_ml_payload_schema():
    """Test ML payload schema_version and date-specific flags."""
    raw = create_test_receipt_raw(
        "Invoice\nInvoice Date: 2024-01-15\nDue Date: 2024-02-15\nTotal: $100.00"
    )
    
    features = build_features(raw)
    date_result = None
    
    # Extract date_result from build_features context (we need to call it directly)
    from app.pipelines.features import _guess_date_entity
    lines = ["Invoice", "Invoice Date: 2024-01-15", "Due Date: 2024-02-15", "Total: $100.00"]
    date_result = _guess_date_entity(lines)
    
    # Generate ML payload
    ml_payload = date_result.to_ml_dict()
    
    # Check schema version
    assert ml_payload.get("schema_version") == 2
    
    # Check required ML payload fields
    assert "winner_margin" in ml_payload
    assert "topk_gap" in ml_payload
    assert "mode_trace" in ml_payload
    assert "feature_flags" in ml_payload
    
    # Check date-specific feature flags
    feature_flags = ml_payload.get("feature_flags", {})
    date_flags = [
        "is_transaction_date",
        "is_invoice_date", 
        "is_due_date",
        "has_multiple_dates",
        "has_conflicting_dates"
    ]
    
    for flag in date_flags:
        assert flag in feature_flags, f"Missing date feature flag: {flag}"
        assert isinstance(feature_flags[flag], bool)
    
    # Check date-specific evidence
    assert "date_evidence" in ml_payload
    date_evidence = ml_payload.get("date_evidence", {})
    assert "raw_value" in date_evidence
    assert "normalized_value" in date_evidence
    assert "date_type" in date_evidence
    assert "date_conflict" in date_evidence


def test_date_entity_edge_cases():
    """Test edge cases and error handling."""
    # Test no dates using direct entity extraction
    from app.pipelines.features import _guess_date_entity
    lines_no_date = ["Receipt", "Total: $25.00", "Thank you"]
    result_no_date = _guess_date_entity(lines_no_date)
    
    assert result_no_date.value is None
    assert result_no_date.confidence == 0.0
    assert result_no_date.confidence_bucket == "NONE"
    
    evidence_no_date = result_no_date.evidence
    assert evidence_no_date.get("total_candidates") == 0
    assert evidence_no_date.get("raw_value") is None
    assert evidence_no_date.get("normalized_value") is None
    assert evidence_no_date.get("date_type") is None
    assert evidence_no_date.get("date_conflict") is None
    
    # Test a simple valid date format
    lines_valid = ["Receipt", "Date: 2024-01-15", "Total: $25.00"]
    result_valid = _guess_date_entity(lines_valid)
    
    assert result_valid.value == "2024-01-15"
    assert result_valid.confidence > 0.0
    assert result_valid.confidence_bucket in ["LOW", "MEDIUM", "HIGH"]
    
    evidence_valid = result_valid.evidence
    assert evidence_valid.get("total_candidates") >= 1
    assert evidence_valid.get("raw_value") == "Date: 2024-01-15"
    assert evidence_valid.get("normalized_value") == "2024-01-15"
    assert evidence_valid.get("date_type") == "transaction_date"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
