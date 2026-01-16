"""
Tests for merchant confidence scoring and gating in V2.1 consistency checks.

These tests verify that merchant_confidence < 0.6 properly gates the
merchant-address consistency assessment.
"""

import pytest
from app.address.validate import validate_address, assess_merchant_address_consistency
from app.pipelines.features import _compute_merchant_confidence


class TestMerchantConfidenceScoring:
    """Test merchant confidence heuristic scoring."""
    
    def test_strong_confidence_header_with_suffix_and_tax(self):
        """Strong confidence: top line + business suffix + tax context."""
        lines = [
            "Acme Logistics Ltd",
            "GSTIN: 29ABCDE1234F1Z5",
            "123 Main Street",
            "Invoice #12345",
        ]
        
        confidence = _compute_merchant_confidence("Acme Logistics Ltd", lines, "\n".join(lines))
        
        assert confidence >= 0.8, f"Expected strong confidence (>=0.8), got {confidence}"
    
    def test_medium_confidence_header_only(self):
        """Medium confidence: in header but no business suffix or tax context."""
        lines = [
            "Bob's Burgers",
            "123 Main Street",
            "Invoice #12345",
        ]
        
        confidence = _compute_merchant_confidence("Bob's Burgers", lines, "\n".join(lines))
        
        assert 0.6 <= confidence < 0.8, f"Expected medium confidence (0.6-0.79), got {confidence}"
    
    def test_medium_confidence_business_suffix_only(self):
        """Medium confidence: has business suffix but not in header."""
        lines = [
            "Invoice #12345",
            "Date: 2024-01-15",
            "",
            "Acme Corporation",
            "123 Main Street",
        ]
        
        confidence = _compute_merchant_confidence("Acme Corporation", lines, "\n".join(lines))
        
        assert 0.6 <= confidence < 0.8, f"Expected medium confidence (0.6-0.79), got {confidence}"
    
    def test_low_confidence_footer_only(self):
        """Low confidence: appears only in footer (after line 30)."""
        lines = ["Line " + str(i) for i in range(35)]
        lines[32] = "Acme Corp"
        
        confidence = _compute_merchant_confidence("Acme Corp", lines, "\n".join(lines))
        
        assert confidence < 0.6, f"Expected low confidence (<0.6), got {confidence}"
    
    def test_low_confidence_scattered(self):
        """Low confidence: scattered across document (gap > 10 lines)."""
        lines = ["Line " + str(i) for i in range(25)]
        lines[2] = "Acme Corp"
        lines[15] = "Acme Corp"
        
        confidence = _compute_merchant_confidence("Acme Corp", lines, "\n".join(lines))
        
        assert confidence < 0.6, f"Expected low confidence (<0.6), got {confidence}"
    
    def test_zero_confidence_empty_merchant(self):
        """Zero confidence: empty merchant name."""
        lines = ["Invoice #12345", "123 Main Street"]
        
        confidence = _compute_merchant_confidence("", lines, "\n".join(lines))
        
        assert confidence == 0.0


class TestMerchantConfidenceGating:
    """Test that merchant_confidence < 0.6 gates consistency checks."""
    
    def test_consistency_gated_low_merchant_confidence(self):
        """Consistency returns UNKNOWN when merchant_confidence < 0.6."""
        address_profile = validate_address("123 Main Street, Springfield, IL 62701")
        
        result = assess_merchant_address_consistency(
            merchant_name="Some Merchant",
            merchant_confidence=0.5,  # Below 0.6 threshold
            address_profile=address_profile,
            doc_profile_confidence=0.9,
        )
        
        assert result["status"] == "UNKNOWN", \
            "Should return UNKNOWN when merchant_confidence < 0.6"
        assert result["score"] == 0.0
        assert result["evidence"] == []
    
    def test_consistency_active_at_threshold(self):
        """Consistency is active when merchant_confidence >= 0.6."""
        address_profile = validate_address("123 Main Street, Springfield, IL 62701")
        
        result = assess_merchant_address_consistency(
            merchant_name="Acme Corp",
            merchant_confidence=0.6,  # At threshold
            address_profile=address_profile,
            doc_profile_confidence=0.9,
        )
        
        assert result["status"] != "UNKNOWN", \
            "Should be active when merchant_confidence >= 0.6"
    
    def test_consistency_active_high_confidence(self):
        """Consistency is active when merchant_confidence is high."""
        address_profile = validate_address("123 Main Street, Springfield, IL 62701")
        
        result = assess_merchant_address_consistency(
            merchant_name="Acme Logistics Ltd",
            merchant_confidence=0.85,
            address_profile=address_profile,
            doc_profile_confidence=0.9,
        )
        
        assert result["status"] != "UNKNOWN", \
            "Should be active when merchant_confidence is high"
    
    def test_consistency_requires_both_confidences(self):
        """Both merchant and doc confidence must be above thresholds."""
        address_profile = validate_address("123 Main Street, Springfield, IL 62701")
        
        # Low merchant confidence
        result_low_merchant = assess_merchant_address_consistency(
            merchant_name="Acme Corp",
            merchant_confidence=0.5,  # Below threshold
            address_profile=address_profile,
            doc_profile_confidence=0.9,  # Above threshold
        )
        
        # Low doc confidence
        result_low_doc = assess_merchant_address_consistency(
            merchant_name="Acme Corp",
            merchant_confidence=0.8,  # Above threshold
            address_profile=address_profile,
            doc_profile_confidence=0.5,  # Below threshold
        )
        
        # Both should be gated
        assert result_low_merchant["status"] == "UNKNOWN", \
            "Should be gated when merchant_confidence is low"
        assert result_low_doc["status"] == "UNKNOWN", \
            "Should be gated when doc_profile_confidence is low"
    
    def test_confidence_boundary_values(self):
        """Test exact boundary values for gating."""
        address_profile = validate_address("123 Main Street, Springfield, IL 62701")
        
        # Just below merchant threshold
        result_below = assess_merchant_address_consistency(
            merchant_name="Acme Corp",
            merchant_confidence=0.59,
            address_profile=address_profile,
            doc_profile_confidence=0.9,
        )
        
        # Just at merchant threshold
        result_at = assess_merchant_address_consistency(
            merchant_name="Acme Corp",
            merchant_confidence=0.6,
            address_profile=address_profile,
            doc_profile_confidence=0.9,
        )
        
        assert result_below["status"] == "UNKNOWN", \
            "Should be gated at 0.59"
        assert result_at["status"] != "UNKNOWN", \
            "Should be active at 0.6"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
