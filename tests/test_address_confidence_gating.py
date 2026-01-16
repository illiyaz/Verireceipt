"""
CI assertion tests for address feature confidence gating.

These tests ensure that address-derived features correctly return UNKNOWN
when doc_profile_confidence is below the gating threshold (0.55).

This indirectly protects ordering assumptions in features.py.
"""

import pytest
from app.address.validate import assess_merchant_address_consistency, detect_multi_address_profile


class TestAddressConfidenceGating:
    """CI assertions for confidence gating in address features."""
    
    def test_merchant_consistency_gated_below_threshold(self):
        """Merchant-address consistency returns UNKNOWN when doc_profile_confidence < 0.55."""
        from app.address.validate import validate_address
        
        address_profile = validate_address("123 Main Street, Springfield, IL 62701")
        
        # Test at threshold boundary
        result_low = assess_merchant_address_consistency(
            merchant_name="Acme Corp",
            merchant_confidence=0.8,
            address_profile=address_profile,
            doc_profile_confidence=0.54,  # Below 0.55 threshold
        )
        
        assert result_low["status"] == "UNKNOWN", \
            "Consistency check should return UNKNOWN when doc_profile_confidence < 0.55"
        assert result_low["score"] == 0.0
        assert result_low["evidence"] == []
    
    def test_merchant_consistency_active_above_threshold(self):
        """Merchant-address consistency is active when doc_profile_confidence >= 0.55."""
        from app.address.validate import validate_address
        
        address_profile = validate_address("123 Main Street, Springfield, IL 62701")
        
        result_ok = assess_merchant_address_consistency(
            merchant_name="Acme Corp",
            merchant_confidence=0.8,
            address_profile=address_profile,
            doc_profile_confidence=0.55,  # At threshold
        )
        
        # Should not be UNKNOWN (could be CONSISTENT, WEAK_MISMATCH, or MISMATCH)
        assert result_ok["status"] != "UNKNOWN", \
            "Consistency check should be active when doc_profile_confidence >= 0.55"
    
    def test_multi_address_gated_below_threshold(self):
        """Multi-address detection returns UNKNOWN when doc_profile_confidence < 0.55."""
        text = """
        Invoice #12345
        
        Bill To:
        123 Main Street
        Springfield, IL 62701
        
        Ship To:
        456 Oak Avenue
        Chicago, IL 60601
        """
        
        result_low = detect_multi_address_profile(
            text=text,
            doc_profile_confidence=0.54,  # Below 0.55 threshold
        )
        
        assert result_low["status"] == "UNKNOWN", \
            "Multi-address detection should return UNKNOWN when doc_profile_confidence < 0.55"
        assert result_low["count"] == 0
        assert "gated:doc_profile_confidence" in result_low["evidence"]
    
    def test_multi_address_active_above_threshold(self):
        """Multi-address detection is active when doc_profile_confidence >= 0.55."""
        text = """
        Invoice #12345
        
        Bill To:
        123 Main Street
        Springfield, IL 62701
        
        Ship To:
        456 Oak Avenue
        Chicago, IL 60601
        """
        
        result_ok = detect_multi_address_profile(
            text=text,
            doc_profile_confidence=0.55,  # At threshold
        )
        
        # Should not be gated (could be SINGLE, MULTIPLE, or UNKNOWN for other reasons)
        assert "gated:doc_profile_confidence" not in result_ok["evidence"], \
            "Multi-address detection should be active when doc_profile_confidence >= 0.55"
    
    def test_confidence_threshold_consistency(self):
        """Both address features use the same confidence threshold (0.55)."""
        from app.address.validate import validate_address
        
        address_profile = validate_address("123 Main Street, Springfield, IL 62701")
        
        # Test consistency at 0.54 (below threshold)
        consistency_result = assess_merchant_address_consistency(
            merchant_name="Acme Corp",
            merchant_confidence=0.8,
            address_profile=address_profile,
            doc_profile_confidence=0.54,
        )
        
        # Test multi-address at 0.54 (below threshold)
        multi_result = detect_multi_address_profile(
            text="123 Main Street, Springfield, IL 62701",
            doc_profile_confidence=0.54,
        )
        
        # Both should be gated
        assert consistency_result["status"] == "UNKNOWN", \
            "Consistency should be gated at 0.54"
        assert multi_result["status"] == "UNKNOWN", \
            "Multi-address should be gated at 0.54"
        assert "gated:doc_profile_confidence" in multi_result["evidence"]
    
    def test_ordering_protection_implicit(self):
        """
        This test documents the ordering assumption:
        If conf is computed after address features are called,
        the features would receive an undefined or stale value.
        
        This test verifies that features correctly use the confidence
        parameter they receive, which indirectly protects against
        ordering bugs in features.py.
        """
        from app.address.validate import validate_address
        
        address_profile = validate_address("123 Main Street, Springfield, IL 62701")
        
        # Simulate what would happen if conf was undefined (None or 0.0)
        result_none = assess_merchant_address_consistency(
            merchant_name="Acme Corp",
            merchant_confidence=0.8,
            address_profile=address_profile,
            doc_profile_confidence=None,  # Would happen if conf not computed
        )
        
        result_zero = assess_merchant_address_consistency(
            merchant_name="Acme Corp",
            merchant_confidence=0.8,
            address_profile=address_profile,
            doc_profile_confidence=0.0,  # Would happen if conf defaulted
        )
        
        # Both should be gated (UNKNOWN)
        assert result_none["status"] == "UNKNOWN", \
            "Should be gated when confidence is None"
        assert result_zero["status"] == "UNKNOWN", \
            "Should be gated when confidence is 0.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
