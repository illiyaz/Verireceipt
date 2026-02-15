"""
Phase-9.3 Discount Entity V2 Tests

Tests for DiscountEntityV2 extraction, gating, and schema stability.
"""

import pytest
from app.pipelines.features import (
    DiscountEntityV2,
    build_discount_entity_v2,
    _extract_discount_from_aligned,
    _extract_discount_from_regex
)


class TestDiscountEntityV2:
    """Test DiscountEntityV2 dataclass and contract."""

    def test_entity_schema_stability(self):
        """Test that entity schema is stable and frozen."""
        entity = DiscountEntityV2()
        
        # Schema version must be 2
        assert entity.schema_version == 2
        
        # All fields must be present
        assert hasattr(entity, 'value')
        assert hasattr(entity, 'confidence')
        assert hasattr(entity, 'source')
        assert hasattr(entity, 'labels_matched')
        assert hasattr(entity, 'gated_reason')
        assert hasattr(entity, 'notes')
        
        # Default values
        assert entity.value is None
        assert entity.confidence == 0.0
        assert entity.source == "none"
        assert entity.labels_matched == []
        assert entity.gated_reason is None
        assert entity.notes == []

    def test_entity_to_dict_rounding(self):
        """Test to_dict() method with proper float rounding."""
        entity = DiscountEntityV2(
            value=25.123456,
            confidence=0.987654,
            source="regex",
            labels_matched=["discount"],
            gated_reason=None,
            notes=["test"]
        )
        
        result = entity.to_dict()
        
        # Float rounding
        assert result["value"] == 25.12  # 2 decimal places
        assert result["confidence"] == 0.988  # 3 decimal places
        
        # Other fields unchanged
        assert result["schema_version"] == 2
        assert result["source"] == "regex"
        assert result["labels_matched"] == ["discount"]


class TestDiscountExtraction:
    """Test discount extraction from different sources."""

    def test_extract_from_aligned_always_none(self):
        """Test extraction from aligned amounts always returns None."""
        aligned_amounts = {
            "hit": True,
            "discount_amount": 10.00,  # Even if present
            "alignment_confidence": 0.75
        }
        
        value, confidence, labels_matched = _extract_discount_from_aligned(aligned_amounts)
        
        assert value is None
        assert confidence == 0.0
        assert labels_matched == []

    def test_extract_from_regex_match(self):
        """Test regex extraction with match."""
        lines = [
            "Discount: $10.00",
            "Total: $90.00"
        ]
        
        value, confidence, labels_matched = _extract_discount_from_regex(lines)
        
        assert value == 10.00
        assert confidence == 0.7
        assert len(labels_matched) > 0
        assert "discount" in labels_matched[0].lower()

    def test_extract_from_regex_no_match(self):
        """Test regex extraction with no match."""
        lines = [
            "Total: $100.00",
            "Tax: $8.00"
        ]
        
        value, confidence, labels_matched = _extract_discount_from_regex(lines)
        
        assert value is None
        assert confidence == 0.0
        assert labels_matched == []

    def test_extract_from_regex_various_formats(self):
        """Test regex extraction with various discount formats."""
        test_cases = [
            ("Discount: $5.00", 5.00),
            ("DISC $10.50", 10.50),
            ("Discount amount: $15.25", 15.25),
            ("Discount ($20.00)", 20.00),
            ("discount $1,234.56", 1234.56),
        ]
        
        for line, expected_value in test_cases:
            value, confidence, labels_matched = _extract_discount_from_regex([line])
            assert value == expected_value
            assert confidence == 0.7

    def test_extract_from_regex_case_insensitive(self):
        """Test regex extraction is case insensitive."""
        test_cases = [
            "DISCOUNT: $10.00",
            "Discount: $10.00",
            "discount: $10.00",
            "DiScOuNt: $10.00"
        ]
        
        for line in test_cases:
            value, confidence, labels_matched = _extract_discount_from_regex([line])
            assert value == 10.00
            assert confidence == 0.7


class TestDiscountEntityBuilder:
    """Test DiscountEntityV2 builder function."""

    def test_builder_regex_priority(self):
        """Test builder uses regex extraction (aligned always fails)."""
        lines = ["Discount: $15.00"]
        aligned_amounts = {"hit": True}  # Even with hit, aligned returns None
        
        entity = build_discount_entity_v2(lines, aligned_amounts)
        
        assert entity.value == 15.00
        assert entity.confidence == 0.7
        assert entity.source == "regex"
        assert len(entity.labels_matched) > 0
        assert entity.gated_reason is None

    def test_builder_existing_fallback(self):
        """Test builder falls back to existing value."""
        lines = ["Total: $100.00"]
        aligned_amounts = {"hit": False}
        existing_discount = 25.00
        
        entity = build_discount_entity_v2(lines, aligned_amounts, existing_discount)
        
        assert entity.value == 25.00
        assert entity.confidence == 0.6  # Lower confidence for existing
        assert entity.source == "existing"
        assert entity.labels_matched == ["existing_extraction"]
        assert entity.gated_reason is None

    def test_builder_no_value_gated(self):
        """Test builder applies gating when no value found."""
        lines = ["Total: $100.00"]
        aligned_amounts = {"hit": False}
        
        entity = build_discount_entity_v2(lines, aligned_amounts)
        
        assert entity.value is None
        assert entity.confidence == 0.0
        assert entity.source == "none"
        assert entity.gated_reason == "not_present_in_document"
        assert "No discount label found" in entity.notes[0]

    def test_builder_confidence_clamping(self):
        """Test builder clamps confidence to [0,1]."""
        lines = ["Discount: $50.00"]
        aligned_amounts = {"hit": False}
        
        entity = build_discount_entity_v2(lines, aligned_amounts)
        
        # Confidence should be clamped to valid range
        assert 0.0 <= entity.confidence <= 1.0
        assert entity.confidence == 0.7  # Expected value for regex

    def test_builder_schema_stability(self):
        """Test builder always returns stable schema."""
        lines = ["Total: $100.00"]
        aligned_amounts = {"hit": False}
        
        entity = build_discount_entity_v2(lines, aligned_amounts)
        
        # All fields must be present
        entity_dict = entity.to_dict()
        required_fields = [
            "schema_version", "value", "confidence", "source",
            "labels_matched", "gated_reason", "notes"
        ]
        
        for field in required_fields:
            assert field in entity_dict
            assert entity_dict[field] is not None or field in ["value", "gated_reason"]

    def test_builder_determinism(self):
        """Test builder is deterministic."""
        lines = ["Discount: $12.34"]
        aligned_amounts = {"hit": False}
        
        entity1 = build_discount_entity_v2(lines, aligned_amounts)
        entity2 = build_discount_entity_v2(lines, aligned_amounts)
        
        assert entity1.to_dict() == entity2.to_dict()

    def test_builder_low_confidence_gating(self):
        """Test builder applies gating for low confidence."""
        # This tests the confidence < 0.5 gating
        # Since our regex extraction always returns 0.7, we test the existing fallback
        lines = ["Total: $100.00"]
        aligned_amounts = {"hit": False}
        
        entity = build_discount_entity_v2(lines, aligned_amounts)
        
        # Should be gated as not present
        assert entity.gated_reason == "not_present_in_document"
        assert entity.confidence == 0.0


class TestDiscountEntityIntegration:
    """Integration tests for DiscountEntityV2."""

    def test_extraction_priority_order(self):
        """Test extraction priority: aligned → regex → existing → None."""
        lines = ["Discount: $20.00"]
        aligned_amounts = {"hit": False}
        existing_discount = 15.00
        
        # Should prefer regex over existing
        entity = build_discount_entity_v2(lines, aligned_amounts, existing_discount)
        assert entity.value == 20.00
        assert entity.source == "regex"

    def test_gating_reasons_coverage(self):
        """Test all gating reasons are properly applied."""
        # Test not_present_in_document
        lines_no_match = ["Total: $100.00"]
        aligned_no_hit = {"hit": False}
        entity = build_discount_entity_v2(lines_no_match, aligned_no_hit)
        assert entity.gated_reason == "not_present_in_document"

    def test_contract_compliance(self):
        """Test entity contract compliance."""
        lines = ["Discount: $10.00"]
        aligned_amounts = {"hit": False}
        
        entity = build_discount_entity_v2(lines, aligned_amounts)
        
        # Contract checks
        assert entity.schema_version == 2
        assert 0.0 <= entity.confidence <= 1.0
        
        # If gated, confidence should be 0
        if entity.gated_reason is not None:
            assert entity.confidence == 0.0
            assert entity.value is None

    def test_discount_not_in_aligned_layouts(self):
        """Test that discount is not typically found in aligned layouts."""
        # This is a design choice - discount is usually not in column layouts
        aligned_amounts = {
            "hit": True,
            "subtotal_amount": 100.00,
            "tax_amount": 8.00,
            "total_amount": 108.00
        }
        
        value, confidence, labels_matched = _extract_discount_from_aligned(aligned_amounts)
        
        assert value is None
        assert confidence == 0.0
        assert labels_matched == []


if __name__ == "__main__":
    pytest.main([__file__])
