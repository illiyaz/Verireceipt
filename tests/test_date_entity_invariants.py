"""
Invariant tests for date entity V2 to protect future refactors.
These tests enforce critical boundaries and semantic guarantees.
"""

import pytest
import re
from app.pipelines.features import build_features, _guess_date_entity
from app.schemas.receipt import ReceiptRaw
from PIL import Image

# Import constants for verification
from app.pipelines.features import (
    DATE_CONFIDENCE_CAP_DUE,
    DATE_CONFIDENCE_CAP_DELIVERY,
    DATE_CONFIDENCE_CAP_CONFLICT,
    DATE_CONFIDENCE_CAP_PREFERRED_CONFLICT,
    DATE_FAR_APART_DAYS
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


def test_due_date_never_high_confidence():
    """
    INVARIANT: due_date must never exceed LOW confidence bucket
    
    This invariant protects the semantic guarantee that due dates
    are always treated as low-confidence, non-transactional dates.
    """
    # Test various due date formats
    due_date_patterns = [
        "Receipt\nDue Date: 2024-01-15\nTotal: $50.00",
        "Invoice\nPayment Due: 01/15/2024\nAmount: $100.00", 
        "Bill\nDue by: 15 Jan 2024\nTotal: $75.00",
        "Statement\nDue: 2024-01-15\nBalance: $25.00"
    ]
    
    for ocr_text in due_date_patterns:
        raw = create_test_receipt_raw(ocr_text)
        features = build_features(raw)
        text_features = features.text_features
        
        # Verify due date classification
        evidence = text_features.get("receipt_date_evidence", {})
        assert evidence.get("date_type") == "due_date", f"Expected due_date type for: {ocr_text}"
        
        # Verify confidence never exceeds cap
        confidence = text_features.get("receipt_date_confidence", 0.0)
        assert confidence <= DATE_CONFIDENCE_CAP_DUE, f"Due date confidence {confidence} exceeds cap {DATE_CONFIDENCE_CAP_DUE}"
        
        # Verify bucket is LOW
        bucket = text_features.get("receipt_date_confidence_bucket", "NONE")
        assert bucket == "LOW", f"Due date bucket {bucket} should be LOW for: {ocr_text}"


def test_delivery_date_never_high_confidence():
    """
    INVARIANT: delivery_date must never exceed LOW confidence bucket
    
    Similar to due dates, delivery dates are non-transactional and
    should always be low-confidence.
    """
    # Test various delivery date formats
    delivery_date_patterns = [
        "Receipt\nDelivery Date: 2024-01-15\nTotal: $50.00",
        "Order\nShip Date: 01/15/2024\nAmount: $100.00",
        "Invoice\nShipping Date: 15 Jan 2024\nTotal: $75.00",
        "Package\nDeliver by: 2024-01-15\nCost: $25.00"
    ]
    
    for ocr_text in delivery_date_patterns:
        raw = create_test_receipt_raw(ocr_text)
        features = build_features(raw)
        text_features = features.text_features
        
        # Verify delivery date classification
        evidence = text_features.get("receipt_date_evidence", {})
        assert evidence.get("date_type") == "delivery_date", f"Expected delivery_date type for: {ocr_text}"
        
        # Verify confidence never exceeds cap
        confidence = text_features.get("receipt_date_confidence", 0.0)
        assert confidence <= DATE_CONFIDENCE_CAP_DELIVERY, f"Delivery date confidence {confidence} exceeds cap {DATE_CONFIDENCE_CAP_DELIVERY}"
        
        # Verify bucket is LOW
        bucket = text_features.get("receipt_date_confidence_bucket", "NONE")
        assert bucket == "LOW", f"Delivery date bucket {bucket} should be LOW for: {ocr_text}"


def test_far_apart_dates_reduce_confidence():
    """
    INVARIANT: Dates > DATE_FAR_APART_DAYS apart must reduce confidence below HIGH
    
    This invariant ensures that conflicting dates far apart in time
    are treated with appropriate skepticism.
    """
    # Test dates exactly at the threshold and beyond
    far_apart_scenarios = [
        # Exactly 30 days apart (should not trigger)
        ("Date: 2024-01-15\nDelivery Date: 2024-02-14", False),
        # 31 days apart (should trigger)
        ("Date: 2024-01-15\nDelivery Date: 2024-02-15", True),
        # Much further apart
        ("Date: 2024-01-01\nDue Date: 2024-04-15", True),
        # Different year
        ("Invoice Date: 2023-12-15\nDue Date: 2024-02-15", True)
    ]
    
    for dates_text, should_have_far_apart in far_apart_scenarios:
        raw = create_test_receipt_raw(f"Receipt\n{dates_text}\nTotal: $100.00")
        features = build_features(raw)
        text_features = features.text_features
        
        evidence = text_features.get("receipt_date_evidence", {})
        conflict = evidence.get("date_conflict", {})
        
        # Verify far-apart detection
        has_far_apart = conflict.get("has_far_apart_dates", False)
        assert has_far_apart == should_have_far_apart, f"Far-apart detection failed for: {dates_text}"
        
        if should_have_far_apart:
            # Verify confidence is reduced below HIGH
            confidence = text_features.get("receipt_date_confidence", 0.0)
            assert confidence < 0.8, f"Far-apart dates confidence {confidence} should be below HIGH (0.8)"
            
            # Verify bucket is not HIGH
            bucket = text_features.get("receipt_date_confidence_bucket", "NONE")
            assert bucket != "HIGH", f"Far-apart dates bucket {bucket} should not be HIGH for: {dates_text}"


def test_date_entity_does_not_mutate_other_entities():
    """
    INVARIANT: Date entity must not modify merchant/total results or ML payloads
    
    This invariant ensures entity isolation - date extraction should not
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
    
    # Get total entity alone  
    from app.pipelines.features import _find_total_line
    total_line_alone, total_amount_alone = _find_total_line(lines)
    
    # Get date entity alone
    date_result_alone = _guess_date_entity(lines)
    
    # Now run full build_features
    features_full = build_features(raw)
    text_features_full = features_full.text_features
    
    # Verify merchant is unchanged
    assert text_features_full.get("merchant_candidate") == merchant_result_alone.value
    assert text_features_full.get("receipt_date_confidence") == date_result_alone.confidence
    
    # Verify total is unchanged
    assert text_features_full.get("total_amount") == total_amount_alone
    
    # Verify no cross-entity evidence contamination
    date_evidence = text_features_full.get("receipt_date_evidence", {})
    assert "merchant" not in date_evidence.get("date_type", "").lower()
    assert "total" not in date_evidence.get("date_type", "").lower()
    
    # Verify ML payloads are isolated
    merchant_ml = merchant_result_alone.to_ml_dict()
    date_ml = date_result_alone.to_ml_dict()
    
    # Date ML should have date-specific fields
    assert "date_evidence" in date_ml
    assert "date_evidence" not in merchant_ml
    
    # Merchant ML should not have date fields
    assert "is_transaction_date" not in merchant_ml.get("feature_flags", {})
    assert "is_due_date" not in merchant_ml.get("feature_flags", {})


def test_confidence_constants_are_respected():
    """
    INVARIANT: All confidence capping must respect defined constants
    
    This invariant ensures that the semantic caps defined in constants
    are actually enforced in the implementation.
    """
    # Test due date cap
    raw_due = create_test_receipt_raw("Receipt\nDue Date: 2024-01-15\nTotal: $50.00")
    features_due = build_features(raw_due)
    confidence_due = features_due.text_features.get("receipt_date_confidence", 0.0)
    assert confidence_due <= DATE_CONFIDENCE_CAP_DUE
    
    # Test delivery date cap
    raw_delivery = create_test_receipt_raw("Receipt\nDelivery Date: 2024-01-15\nTotal: $50.00")
    features_delivery = build_features(raw_delivery)
    confidence_delivery = features_delivery.text_features.get("receipt_date_confidence", 0.0)
    assert confidence_delivery <= DATE_CONFIDENCE_CAP_DELIVERY
    
    # Test conflict cap (preferred transaction)
    raw_conflict = create_test_receipt_raw(
        "Invoice\nInvoice Date: 2024-01-15\nDue Date: 2024-02-15\nTotal: $100.00"
    )
    features_conflict = build_features(raw_conflict)
    confidence_conflict = features_conflict.text_features.get("receipt_date_confidence", 0.0)
    assert confidence_conflict <= DATE_CONFIDENCE_CAP_PREFERRED_CONFLICT
    
    # Test conflict cap (far apart)
    raw_far = create_test_receipt_raw(
        "Receipt\nDate: 2024-01-15\nDelivery Date: 2024-04-15\nTotal: $75.00"
    )
    features_far = build_features(raw_far)
    confidence_far = features_far.text_features.get("receipt_date_confidence", 0.0)
    assert confidence_far <= DATE_CONFIDENCE_CAP_CONFLICT


def test_date_threshold_constant_is_used():
    """
    INVARIANT: DATE_FAR_APART_DAYS constant must be used in conflict detection
    
    This invariant ensures the threshold constant is actually applied.
    """
    # Test exactly at threshold (30 days)
    raw_at_threshold = create_test_receipt_raw(
        f"Receipt\nDate: 2024-01-15\nDelivery Date: 2024-02-14\nTotal: $50.00"
    )
    features_at = build_features(raw_at_threshold)
    conflict_at = features_at.text_features.get("receipt_date_evidence", {}).get("date_conflict", {})
    
    # Should NOT be flagged as far apart (exactly 30 days)
    assert not conflict_at.get("has_far_apart_dates", False), "30-day difference should not trigger far-apart flag"
    
    # Test just over threshold (31 days)
    raw_over_threshold = create_test_receipt_raw(
        f"Receipt\nDate: 2024-01-15\nDelivery Date: 2024-02-15\nTotal: $50.00"
    )
    features_over = build_features(raw_over_threshold)
    conflict_over = features_over.text_features.get("receipt_date_evidence", {}).get("date_conflict", {})
    
    # Should be flagged as far apart (31 days)
    assert conflict_over.get("has_far_apart_dates", False), "31-day difference should trigger far-apart flag"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
