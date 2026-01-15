"""
Golden tests for address validation.

Tests geo-agnostic, structure-based address validation.
"""

import pytest
from app.address.validate import validate_address


class TestAddressValidation:
    """Test address validation with various inputs."""
    
    def test_not_address_total_only(self):
        """Total amount alone is not an address."""
        result = validate_address("Total $45.00")
        assert result["address_classification"] == "NOT_AN_ADDRESS"
        assert result["address_score"] < 3
    
    def test_not_address_short_text(self):
        """Short text is not an address."""
        result = validate_address("Hello")
        assert result["address_classification"] == "NOT_AN_ADDRESS"
        assert result["address_score"] == 0
    
    def test_not_address_postal_only(self):
        """Postal code alone is not an address."""
        result = validate_address("560001")
        assert result["address_classification"] == "NOT_AN_ADDRESS"
        assert result["address_score"] < 3
    
    def test_weak_address_street_only(self):
        """Street with number is weak address."""
        result = validate_address("123 Main St")
        assert result["address_classification"] == "WEAK_ADDRESS"
        assert 3 <= result["address_score"] <= 4
        assert any("street_keyword" in e for e in result["address_evidence"])
    
    def test_weak_address_minimal(self):
        """Minimal address components."""
        result = validate_address("456 Oak Road")
        assert result["address_classification"] == "WEAK_ADDRESS"
        assert 3 <= result["address_score"] <= 4
    
    def test_plausible_address_with_city(self):
        """Address with street and city is plausible."""
        result = validate_address("123 Main St, Springfield")
        assert result["address_classification"] == "PLAUSIBLE_ADDRESS"
        assert 4 <= result["address_score"] <= 5
        assert any("street_keyword" in e for e in result["address_evidence"])
        assert "locality_tokens" in result["address_evidence"]
    
    def test_plausible_address_with_unit(self):
        """Address with unit/apartment is plausible."""
        result = validate_address("Apt 5B, 789 Elm Street, Boston")
        assert result["address_classification"] == "PLAUSIBLE_ADDRESS"
        assert 5 <= result["address_score"] <= 6
    
    def test_strong_address_complete(self):
        """Complete address with all components is strong."""
        result = validate_address("Suite 402, 221B Baker Street, London")
        assert result["address_classification"] == "STRONG_ADDRESS"
        assert result["address_score"] >= 6
        assert any("street_keyword" in e for e in result["address_evidence"])
        assert any("unit_keyword" in e for e in result["address_evidence"])
    
    def test_strong_address_with_location(self):
        """Address with explicit location mention is strong."""
        result = validate_address("123 Market Street, San Francisco, California, USA")
        assert result["address_classification"] == "STRONG_ADDRESS"
        assert result["address_score"] >= 6  # Location keyword now +1 instead of +2
        assert any("location_keyword" in e for e in result["address_evidence"])
    
    def test_address_with_postal_code(self):
        """Address with postal code."""
        result = validate_address("456 Park Avenue, New York, NY 10022")
        assert result["address_classification"] in {"PLAUSIBLE_ADDRESS", "STRONG_ADDRESS"}
        assert result["address_score"] >= 5
    
    def test_multiline_address(self):
        """Multiline address format."""
        text = """
        Acme Corporation
        123 Business Blvd
        Suite 500
        Chicago, IL 60601
        """
        result = validate_address(text)
        assert result["address_classification"] in {"PLAUSIBLE_ADDRESS", "STRONG_ADDRESS"}
        assert result["address_score"] >= 5
    
    def test_receipt_with_address(self):
        """Receipt text containing address."""
        text = """
        ABC Store
        456 Main Street
        Springfield, MA 01101
        
        Total: $45.00
        Thank you!
        """
        result = validate_address(text)
        assert result["address_classification"] in {"PLAUSIBLE_ADDRESS", "STRONG_ADDRESS"}
        assert result["address_score"] >= 5
    
    def test_receipt_without_address(self):
        """Receipt text without address."""
        text = """
        ABC Store
        
        Item 1: $10.00
        Item 2: $20.00
        Total: $30.00
        """
        result = validate_address(text)
        # May be weak or not an address depending on store name
        assert result["address_classification"] in {"NOT_AN_ADDRESS", "WEAK_ADDRESS"}
    
    def test_invoice_with_full_address(self):
        """Invoice with complete address."""
        text = """
        INVOICE #12345
        
        Bill To:
        John Smith
        789 Corporate Drive
        Building A, Floor 3
        Austin, Texas 78701
        
        Total: $1,500.00
        """
        result = validate_address(text)
        assert result["address_classification"] == "STRONG_ADDRESS"
        assert result["address_score"] >= 7
    
    def test_empty_input(self):
        """Empty input returns not an address."""
        result = validate_address("")
        assert result["address_classification"] == "NOT_AN_ADDRESS"
        assert result["address_score"] == 0
    
    def test_none_input(self):
        """None input returns not an address."""
        result = validate_address(None)
        assert result["address_classification"] == "NOT_AN_ADDRESS"
        assert result["address_score"] == 0
    
    def test_international_address_uk(self):
        """UK-style address."""
        result = validate_address("10 Downing Street, Westminster, London SW1A 2AA")
        assert result["address_classification"] in {"PLAUSIBLE_ADDRESS", "STRONG_ADDRESS"}
        assert result["address_score"] >= 5
    
    def test_international_address_india(self):
        """India-style address."""
        result = validate_address("123 MG Road, Bangalore, Karnataka 560001, India")
        assert result["address_classification"] == "STRONG_ADDRESS"
        assert result["address_score"] >= 6  # Location keyword now +1 instead of +2
    
    def test_po_box_address(self):
        """PO Box is not a strong address signal."""
        result = validate_address("PO Box 1234, Springfield")
        # PO Box doesn't match street keywords, so should be weak
        assert result["address_classification"] in {"NOT_AN_ADDRESS", "WEAK_ADDRESS"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
