"""
Phase-9.3 Tip Entity V2 Tests

Tests for TipEntityV2 extraction, gating, and schema stability.
"""

import pytest
from app.pipelines.features import (
    TipEntityV2,
    build_tip_entity_v2,
    _extract_tip_from_aligned,
    _extract_tip_from_regex
)


class TestTipEntityV2:
    """Test TipEntityV2 dataclass and contract."""

    def test_entity_schema_stability(self):
        """Test that entity schema is stable and frozen."""
        entity = TipEntityV2()
        
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
        entity = TipEntityV2(
            value=8.765432,
            confidence=0.456789,
            source="regex",
            labels_matched=["tip"],
            gated_reason=None,
            notes=["test"]
        )
        
        result = entity.to_dict()
        
        # Float rounding
        assert result["value"] == 8.77  # 2 decimal places
        assert result["confidence"] == 0.457  # 3 decimal places
        
        # Other fields unchanged
        assert result["schema_version"] == 2
        assert result["source"] == "regex"
        assert result["labels_matched"] == ["tip"]


class TestTipExtraction:
    """Test tip extraction from different sources."""

    def test_extract_from_aligned_always_none(self):
        """Test extraction from aligned amounts always returns None."""
        aligned_amounts = {
            "hit": True,
            "tip_amount": 5.00,  # Even if present
            "alignment_confidence": 0.75
        }
        
        value, confidence, labels_matched = _extract_tip_from_aligned(aligned_amounts)
        
        assert value is None
        assert confidence == 0.0
        assert labels_matched == []

    def test_extract_from_regex_match(self):
        """Test regex extraction with match."""
        lines = [
            "Tip: $5.00",
            "Total: $105.00"
        ]
        
        value, confidence, labels_matched = _extract_tip_from_regex(lines)
        
        assert value == 5.00
        assert confidence == 0.7
        assert len(labels_matched) > 0
        assert "tip" in labels_matched[0].lower()

    def test_extract_from_regex_no_match(self):
        """Test regex extraction with no match."""
        lines = [
            "Total: $100.00",
            "Tax: $8.00"
        ]
        
        value, confidence, labels_matched = _extract_tip_from_regex(lines)
        
        assert value is None
        assert confidence == 0.0
        assert labels_matched == []

    def test_extract_from_regex_various_formats(self):
        """Test regex extraction with various tip formats."""
        test_cases = [
            ("Tip: $3.00", 3.00),
            ("Gratuity: $5.50", 5.50),
            ("Tip amount: $7.25", 7.25),
            ("Service charge: $10.00", 10.00),
            ("tip $1,234.56", 1234.56),
        ]
        
        for line, expected_value in test_cases:
            value, confidence, labels_matched = _extract_tip_from_regex([line])
            assert value == expected_value
            assert confidence == 0.7

    def test_extract_from_regex_case_insensitive(self):
        """Test regex extraction is case insensitive."""
        test_cases = [
            "TIP: $5.00",
            "Tip: $5.00",
            "tip: $5.00",
            "TiP: $5.00"
        ]
        
        for line in test_cases:
            value, confidence, labels_matched = _extract_tip_from_regex([line])
            assert value == 5.00
            assert confidence == 0.7

    def test_extract_from_regex_gratuity_and_service_charge(self):
        """Test regex extraction for gratuity and service charge."""
        test_cases = [
            ("Gratuity: $8.00", 8.00),
            ("SERVICE CHARGE: $12.50", 12.50),
            ("Service charge: $15.75", 15.75),
        ]
        
        for line, expected_value in test_cases:
            value, confidence, labels_matched = _extract_tip_from_regex([line])
            assert value == expected_value
            assert confidence == 0.7


class TestTipEntityBuilder:
    """Test TipEntityV2 builder function."""

    def test_builder_regex_priority(self):
        """Test builder uses regex extraction (aligned always fails)."""
        lines = ["Tip: $8.00"]
        aligned_amounts = {"hit": True}  # Even with hit, aligned returns None
        
        entity = build_tip_entity_v2(lines, aligned_amounts)
        
        assert entity.value == 8.00
        assert entity.confidence == 0.7
        assert entity.source == "regex"
        assert len(entity.labels_matched) > 0
        assert entity.gated_reason is None

    def test_builder_existing_fallback(self):
        """Test builder falls back to existing value."""
        lines = ["Total: $100.00"]
        aligned_amounts = {"hit": False}
        existing_tip = 12.00
        
        entity = build_tip_entity_v2(lines, aligned_amounts, existing_tip)
        
        assert entity.value == 12.00
        assert entity.confidence == 0.6  # Lower confidence for existing
        assert entity.source == "existing"
        assert entity.labels_matched == ["existing_extraction"]
        assert entity.gated_reason is None

    def test_builder_no_value_gated(self):
        """Test builder applies gating when no value found."""
        lines = ["Total: $100.00"]
        aligned_amounts = {"hit": False}
        
        entity = build_tip_entity_v2(lines, aligned_amounts)
        
        assert entity.value is None
        assert entity.confidence == 0.0
        assert entity.source == "none"
        assert entity.gated_reason == "not_present_in_document"
        assert "No tip label found" in entity.notes[0]

    def test_builder_confidence_clamping(self):
        """Test builder clamps confidence to [0,1]."""
        lines = ["Tip: $15.00"]
        aligned_amounts = {"hit": False}
        
        entity = build_tip_entity_v2(lines, aligned_amounts)
        
        # Confidence should be clamped to valid range
        assert 0.0 <= entity.confidence <= 1.0
        assert entity.confidence == 0.7  # Expected value for regex

    def test_builder_schema_stability(self):
        """Test builder always returns stable schema."""
        lines = ["Total: $100.00"]
        aligned_amounts = {"hit": False}
        
        entity = build_tip_entity_v2(lines, aligned_amounts)
        
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
        lines = ["Tip: $9.99"]
        aligned_amounts = {"hit": False}
        
        entity1 = build_tip_entity_v2(lines, aligned_amounts)
        entity2 = build_tip_entity_v2(lines, aligned_amounts)
        
        assert entity1.to_dict() == entity2.to_dict()

    def test_builder_multiple_tip_formats(self):
        """Test builder handles multiple tip format matches."""
        lines = [
            "Tip: $5.00",
            "Gratuity: $6.00",
            "Service charge: $7.00"
        ]
        aligned_amounts = {"hit": False}
        
        entity = build_tip_entity_v2(lines, aligned_amounts)
        
        # Should find the first match
        assert entity.value == 5.00
        assert entity.source == "regex"
        assert entity.confidence == 0.7


class TestTipEntityIntegration:
    """Integration tests for TipEntityV2."""

    def test_extraction_priority_order(self):
        """Test extraction priority: aligned → regex → existing → None."""
        lines = ["Tip: $10.00"]
        aligned_amounts = {"hit": False}
        existing_tip = 8.00
        
        # Should prefer regex over existing
        entity = build_tip_entity_v2(lines, aligned_amounts, existing_tip)
        assert entity.value == 10.00
        assert entity.source == "regex"

    def test_gating_reasons_coverage(self):
        """Test all gating reasons are properly applied."""
        # Test not_present_in_document
        lines_no_match = ["Total: $100.00"]
        aligned_no_hit = {"hit": False}
        entity = build_tip_entity_v2(lines_no_match, aligned_no_hit)
        assert entity.gated_reason == "not_present_in_document"

    def test_contract_compliance(self):
        """Test entity contract compliance."""
        lines = ["Tip: $5.00"]
        aligned_amounts = {"hit": False}
        
        entity = build_tip_entity_v2(lines, aligned_amounts)
        
        # Contract checks
        assert entity.schema_version == 2
        assert 0.0 <= entity.confidence <= 1.0
        
        # If gated, confidence should be 0
        if entity.gated_reason is not None:
            assert entity.confidence == 0.0
            assert entity.value is None

    def test_tip_not_in_aligned_layouts(self):
        """Test that tip is not typically found in aligned layouts."""
        # This is a design choice - tip is usually not in column layouts
        aligned_amounts = {
            "hit": True,
            "subtotal_amount": 100.00,
            "tax_amount": 8.00,
            "total_amount": 108.00
        }
        
        value, confidence, labels_matched = _extract_tip_from_aligned(aligned_amounts)
        
        assert value is None
        assert confidence == 0.0
        assert labels_matched == []

    def test_various_tip_keywords(self):
        """Test extraction handles various tip-related keywords."""
        keywords_test_cases = [
            ("Tip: $5.00", "tip"),
            ("Gratuity: $8.00", "gratuity"),
            ("Service charge: $12.00", "service charge"),
            ("TIP AMOUNT: $15.00", "tip"),
        ]
        
        for line, keyword in keywords_test_cases:
            value, confidence, labels_matched = _extract_tip_from_regex([line])
            assert value is not None
            assert confidence == 0.7
            assert len(labels_matched) > 0


if __name__ == "__main__":
    pytest.main([__file__])
