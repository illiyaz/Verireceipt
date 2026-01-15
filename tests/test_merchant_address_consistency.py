"""
Tests for V2.1 merchant-address consistency checking.

These tests verify the feature-only consistency assessment between
merchant names and addresses.
"""

import pytest
from app.address.validate import validate_address, assess_merchant_address_consistency


class TestMerchantAddressConsistency:
    """Test merchant-address consistency assessment."""
    
    def test_consistency_unknown_when_merchant_confidence_low(self):
        """Low merchant confidence should return UNKNOWN."""
        ap = validate_address("221B Baker Street, London")
        result = assess_merchant_address_consistency(
            merchant_name="Acme Logistics Pvt Ltd",
            merchant_confidence=0.2,  # Low confidence -> gated
            address_profile=ap,
            doc_profile_confidence=0.9,
        )
        assert result["status"] == "UNKNOWN"
        assert result["score"] == 0.0
        assert result["evidence"] == []
    
    def test_consistency_unknown_when_address_weak(self):
        """Weak address classification should return UNKNOWN."""
        ap = validate_address("123 Main St")  # WEAK_ADDRESS
        result = assess_merchant_address_consistency(
            merchant_name="Acme Corp",
            merchant_confidence=0.8,
            address_profile=ap,
            doc_profile_confidence=0.9,
        )
        assert result["status"] == "UNKNOWN"
        assert result["score"] == 0.0
    
    def test_consistency_unknown_when_doc_profile_confidence_low(self):
        """Low doc profile confidence should return UNKNOWN."""
        ap = validate_address("123 Main Street, Springfield, IL 62701")
        result = assess_merchant_address_consistency(
            merchant_name="Acme Corp",
            merchant_confidence=0.8,
            address_profile=ap,
            doc_profile_confidence=0.4,  # Low confidence -> gated
        )
        assert result["status"] == "UNKNOWN"
        assert result["score"] == 0.0
    
    def test_consistency_unknown_when_merchant_missing(self):
        """Missing merchant name should return UNKNOWN."""
        ap = validate_address("123 Main Street, Springfield, IL 62701")
        result = assess_merchant_address_consistency(
            merchant_name="",  # Missing
            merchant_confidence=0.8,
            address_profile=ap,
            doc_profile_confidence=0.9,
        )
        assert result["status"] == "UNKNOWN"
        assert result["score"] == 0.0
    
    def test_po_box_vs_corporate_mismatch(self):
        """Corporate merchant with PO Box should flag mismatch (if address is strong enough)."""
        # PO Box with street address makes it plausible
        ap = validate_address("P.O. Box 1234, 123 Main Street, Springfield, IL 62701")
        result = assess_merchant_address_consistency(
            merchant_name="Acme Logistics Ltd",
            merchant_confidence=0.8,
            address_profile=ap,
            doc_profile_confidence=0.9,
        )
        assert result["status"] == "MISMATCH"
        assert result["score"] == 0.2
        assert "address_type_mismatch:po_box_vs_corporate" in result["evidence"]
    
    def test_po_box_weak_returns_unknown(self):
        """PO Box alone is too weak and should return UNKNOWN."""
        ap = validate_address("P.O. Box 1234, Springfield, IL 62701")
        result = assess_merchant_address_consistency(
            merchant_name="John's Pizza",
            merchant_confidence=0.8,
            address_profile=ap,
            doc_profile_confidence=0.9,
        )
        # PO Box alone scores too low (NOT_AN_ADDRESS), so gated
        assert result["status"] == "UNKNOWN"
        assert result["score"] == 0.0
    
    def test_token_overlap_weak_mismatch(self):
        """Token overlap should create weak mismatch signal."""
        ap = validate_address("123 Acme Street, Springfield, IL 62701")
        result = assess_merchant_address_consistency(
            merchant_name="Acme Corporation",
            merchant_confidence=0.8,
            address_profile=ap,
            doc_profile_confidence=0.9,
        )
        assert result["status"] == "WEAK_MISMATCH"
        assert result["score"] == 0.1
        assert any("merchant_token_overlap" in e for e in result["evidence"])
    
    def test_no_overlap_consistent(self):
        """No overlap and no mismatch signals should be CONSISTENT."""
        ap = validate_address("123 Main Street, Springfield, IL 62701")
        result = assess_merchant_address_consistency(
            merchant_name="Bob's Burgers",
            merchant_confidence=0.8,
            address_profile=ap,
            doc_profile_confidence=0.9,
        )
        assert result["status"] == "CONSISTENT"
        assert result["score"] == 0.0
        assert result["evidence"] == []
    
    def test_corporate_with_standard_address_consistent(self):
        """Corporate merchant with standard address should be consistent."""
        ap = validate_address("123 Corporate Drive, Building A, Austin, TX 78701")
        result = assess_merchant_address_consistency(
            merchant_name="Acme Logistics Ltd",
            merchant_confidence=0.8,
            address_profile=ap,
            doc_profile_confidence=0.9,
        )
        # No mismatch, but may have token overlap
        assert result["status"] in {"CONSISTENT", "WEAK_MISMATCH"}
        assert result["score"] <= 0.1
    
    def test_filters_common_corporate_tokens(self):
        """Should filter out common corporate tokens like ltd, inc, corp."""
        ap = validate_address("123 Limited Street, Springfield, IL 62701")
        result = assess_merchant_address_consistency(
            merchant_name="Acme Limited",
            merchant_confidence=0.8,
            address_profile=ap,
            doc_profile_confidence=0.9,
        )
        # "Limited" should be filtered from merchant tokens
        # So no overlap with "Limited Street"
        assert result["status"] == "CONSISTENT"
        assert result["score"] == 0.0
    
    def test_combined_signals_mismatch(self):
        """Multiple signals should combine scores."""
        # Include street address to make it plausible
        ap = validate_address("P.O. Box 1234, 456 Acme Plaza Street, Springfield, IL 62701")
        result = assess_merchant_address_consistency(
            merchant_name="Acme Logistics Ltd",
            merchant_confidence=0.8,
            address_profile=ap,
            doc_profile_confidence=0.9,
        )
        # Should have both token overlap (+0.1) and PO Box mismatch (+0.2)
        # But capped at 0.2
        assert result["status"] == "MISMATCH"
        assert result["score"] == 0.2
        assert len(result["evidence"]) >= 1  # At least PO Box mismatch
    
    def test_address_type_detection_po_box_variants(self):
        """Should detect various PO Box formats."""
        variants = [
            "P.O. Box 1234",
            "PO Box 1234",
            "P O Box 1234",
            "po box 1234",
        ]
        
        for variant in variants:
            ap = validate_address(f"{variant}, Springfield, IL 62701")
            assert ap["address_type"] == "PO_BOX", f"Failed to detect: {variant}"
            assert "address_type:po_box" in ap["address_evidence"]
    
    def test_address_type_standard(self):
        """Standard addresses should be marked as STANDARD."""
        ap = validate_address("123 Main Street, Springfield, IL 62701")
        assert ap["address_type"] == "STANDARD"
        assert "address_type:po_box" not in ap["address_evidence"]
    
    def test_address_raw_text_preserved(self):
        """Original address text should be preserved."""
        original_text = "123 Main Street, Springfield, IL 62701"
        ap = validate_address(original_text)
        assert ap["address_raw_text"] == original_text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
