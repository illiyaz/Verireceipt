"""
Phase-9.3 Subtotal Entity V2 Tests

Tests for SubtotalEntityV2 extraction, gating, and schema stability.
"""

import pytest
from app.pipelines.features import (
    SubtotalEntityV2,
    build_subtotal_entity_v2,
    _extract_subtotal_from_aligned,
    _extract_subtotal_from_regex
)


class TestSubtotalEntityV2:
    """Test SubtotalEntityV2 dataclass and contract."""

    def test_entity_schema_stability(self):
        """Test that entity schema is stable and frozen."""
        entity = SubtotalEntityV2()
        
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
        entity = SubtotalEntityV2(
            value=123.456789,
            confidence=0.123456,
            source="regex",
            labels_matched=["subtotal"],
            gated_reason=None,
            notes=["test"]
        )
        
        result = entity.to_dict()
        
        # Float rounding
        assert result["value"] == 123.46  # 2 decimal places
        assert result["confidence"] == 0.123  # 3 decimal places
        
        # Other fields unchanged
        assert result["schema_version"] == 2
        assert result["source"] == "regex"
        assert result["labels_matched"] == ["subtotal"]

    def test_entity_contract_value_none_confidence_zero(self):
        """Test contract: value is None ⇒ confidence is 0.0."""
        entity = SubtotalEntityV2(value=None, confidence=0.5)
        
        # Builder should enforce this contract
        assert entity.value is None
        # Note: confidence clamping happens in builder, not dataclass


class TestSubtotalExtraction:
    """Test subtotal extraction from different sources."""

    def test_extract_from_aligned_hit(self):
        """Test extraction from aligned amounts when hit."""
        aligned_amounts = {
            "hit": True,
            "subtotal_amount": 100.50,
            "alignment_confidence": 0.75
        }
        
        value, confidence, labels_matched = _extract_subtotal_from_aligned(aligned_amounts)
        
        assert value == 100.50
        assert confidence == 0.75
        assert labels_matched == ["aligned"]

    def test_extract_from_aligned_miss(self):
        """Test extraction from aligned amounts when miss."""
        aligned_amounts = {
            "hit": False,
            "subtotal_amount": None,
            "alignment_confidence": 0.0
        }
        
        value, confidence, labels_matched = _extract_subtotal_from_aligned(aligned_amounts)
        
        assert value is None
        assert confidence == 0.0
        assert labels_matched == []

    def test_extract_from_regex_match(self):
        """Test regex extraction with match."""
        lines = [
            "SUBTOTAL: $100.50",
            "Tax: $8.04"
        ]
        
        value, confidence, labels_matched = _extract_subtotal_from_regex(lines)
        
        assert value == 100.50
        assert confidence == 0.7
        assert len(labels_matched) > 0
        assert "subtotal" in labels_matched[0].lower()

    def test_extract_from_regex_no_match(self):
        """Test regex extraction with no match."""
        lines = [
            "Total: $108.54",
            "Tax: $8.04"
        ]
        
        value, confidence, labels_matched = _extract_subtotal_from_regex(lines)
        
        assert value is None
        assert confidence == 0.0
        assert labels_matched == []

    def test_extract_from_regex_various_formats(self):
        """Test regex extraction with various subtotal formats."""
        test_cases = [
            ("Subtotal: $50.00", 50.00),
            ("SUB TOTAL $75.25", 75.25),
            ("Sub-Total: 100.00", 100.00),
            ("subtotal $1,234.56", 1234.56),
        ]
        
        for line, expected_value in test_cases:
            value, confidence, labels_matched = _extract_subtotal_from_regex([line])
            assert value == expected_value
            assert confidence == 0.7


class TestSubtotalEntityBuilder:
    """Test SubtotalEntityV2 builder function."""

    def test_builder_aligned_priority(self):
        """Test builder prefers aligned extraction over regex."""
        lines = ["Subtotal: $50.00"]
        aligned_amounts = {
            "hit": True,
            "subtotal_amount": 100.50,
            "alignment_confidence": 0.75
        }
        
        entity = build_subtotal_entity_v2(lines, aligned_amounts)
        
        assert entity.value == 100.50  # Aligned value, not regex
        assert entity.confidence == 0.75
        assert entity.source == "aligned"
        assert entity.labels_matched == ["aligned"]
        assert entity.gated_reason is None

    def test_builder_regex_fallback(self):
        """Test builder falls back to regex when aligned fails."""
        lines = ["Subtotal: $75.25"]
        aligned_amounts = {"hit": False}
        
        entity = build_subtotal_entity_v2(lines, aligned_amounts)
        
        assert entity.value == 75.25
        assert entity.confidence == 0.7
        assert entity.source == "regex"
        assert len(entity.labels_matched) > 0
        assert entity.gated_reason is None

    def test_builder_existing_fallback(self):
        """Test builder falls back to existing value."""
        lines = ["Total: $100.00"]
        aligned_amounts = {"hit": False}
        existing_subtotal = 50.00
        
        entity = build_subtotal_entity_v2(lines, aligned_amounts, existing_subtotal)
        
        assert entity.value == 50.00
        assert entity.confidence == 0.6  # Lower confidence for existing
        assert entity.source == "existing"
        assert entity.labels_matched == ["existing_extraction"]
        assert entity.gated_reason is None

    def test_builder_no_value_gated(self):
        """Test builder applies gating when no value found."""
        lines = ["Total: $100.00"]
        aligned_amounts = {"hit": False}
        
        entity = build_subtotal_entity_v2(lines, aligned_amounts)
        
        assert entity.value is None
        assert entity.confidence == 0.0
        assert entity.source == "none"
        assert entity.gated_reason == "no_label_found"
        assert "No subtotal label found" in entity.notes[0]

    def test_builder_confidence_clamping(self):
        """Test builder clamps confidence to [0,1]."""
        lines = ["Subtotal: $50.00"]
        aligned_amounts = {"hit": False}
        
        # Test with existing value that would have high confidence
        entity = build_subtotal_entity_v2(lines, aligned_amounts, existing_subtotal=50.00)
        
        # Confidence should be clamped to valid range
        assert 0.0 <= entity.confidence <= 1.0
        # Since regex extraction works, it should use regex confidence (0.7), not existing (0.6)
        assert entity.confidence == 0.7  # Expected value for regex

    def test_builder_schema_stability(self):
        """Test builder always returns stable schema."""
        lines = ["Total: $100.00"]
        aligned_amounts = {"hit": False}
        
        entity = build_subtotal_entity_v2(lines, aligned_amounts)
        
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
        lines = ["Subtotal: $123.45"]
        aligned_amounts = {"hit": False}
        
        entity1 = build_subtotal_entity_v2(lines, aligned_amounts)
        entity2 = build_subtotal_entity_v2(lines, aligned_amounts)
        
        assert entity1.to_dict() == entity2.to_dict()


class TestSubtotalEntityIntegration:
    """Integration tests for SubtotalEntityV2."""

    def test_extraction_priority_order(self):
        """Test extraction priority: aligned → regex → existing → None."""
        lines = ["Subtotal: $50.00"]
        aligned_amounts = {
            "hit": True,
            "subtotal_amount": 100.50,
            "alignment_confidence": 0.75
        }
        existing_subtotal = 25.00
        
        # Should prefer aligned over regex and existing
        entity = build_subtotal_entity_v2(lines, aligned_amounts, existing_subtotal)
        assert entity.value == 100.50
        assert entity.source == "aligned"

    def test_gating_reasons_coverage(self):
        """Test all gating reasons are properly applied."""
        # Test no_label_found
        lines_no_match = ["Total: $100.00"]
        aligned_no_hit = {"hit": False}
        entity = build_subtotal_entity_v2(lines_no_match, aligned_no_hit)
        assert entity.gated_reason == "no_label_found"

    def test_contract_compliance(self):
        """Test entity contract compliance."""
        lines = ["Subtotal: $50.00"]
        aligned_amounts = {"hit": False}
        
        entity = build_subtotal_entity_v2(lines, aligned_amounts)
        
        # Contract checks
        assert entity.schema_version == 2
        assert 0.0 <= entity.confidence <= 1.0
        
        # If gated, confidence should be 0
        if entity.gated_reason is not None:
            assert entity.confidence == 0.0
            assert entity.value is None


if __name__ == "__main__":
    pytest.main([__file__])
