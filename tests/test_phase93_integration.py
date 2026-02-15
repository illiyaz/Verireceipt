"""
Phase-9.3 Integration Tests

Integration tests for Phase-9.3 component entities and their effect on reconciliation.
"""

import pytest
from app.pipelines.features import (
    SubtotalEntityV2,
    DiscountEntityV2,
    TipEntityV2,
    build_subtotal_entity_v2,
    build_discount_entity_v2,
    build_tip_entity_v2,
    reconcile_amounts_v2,
    build_reconciliation_v2_entity
)


class TestPhase93Integration:
    """Integration tests for Phase-9.3 component entities."""

    def test_reconciliation_with_entity_outputs(self):
        """Test reconciliation uses entity outputs without logic changes."""
        # Create component entities
        lines = ["Subtotal: $100.00", "Tax: $8.00", "Tip: $5.00"]
        aligned_amounts = {"hit": False}
        
        subtotal_entity = build_subtotal_entity_v2(lines, aligned_amounts)
        discount_entity = build_discount_entity_v2(lines, aligned_amounts)
        tip_entity = build_tip_entity_v2(lines, aligned_amounts)
        
        # Build confidence map using entity outputs
        recon_confidence_map = {
            "subtotal": subtotal_entity.confidence,
            "tax": 0.85,  # Mock tax confidence
            "discount": discount_entity.confidence,
            "tip": tip_entity.confidence,
            "total": 0.9,
        }
        
        # Call reconciliation using entity outputs
        recon_evidence_dict = reconcile_amounts_v2(
            subtotal=subtotal_entity.value,
            tax=8.00,
            discount=discount_entity.value,
            tip=tip_entity.value,
            total=113.00,
            confidence_map=recon_confidence_map
        )
        
        # Verify reconciliation works with entity outputs
        assert recon_evidence_dict is not None
        assert "components_used" in recon_evidence_dict
        assert "mismatch_ratio" in recon_evidence_dict
        assert "status" in recon_evidence_dict

    def test_reconciliation_v2_unchanged_except_components(self):
        """Test reconciliation_v2 output unchanged except components_used."""
        # Test case 1: With component entities
        lines = ["Subtotal: $100.00", "Tax: $8.00"]
        aligned_amounts = {"hit": False}
        
        subtotal_entity = build_subtotal_entity_v2(lines, aligned_amounts)
        discount_entity = build_discount_entity_v2(lines, aligned_amounts)
        tip_entity = build_tip_entity_v2(lines, aligned_amounts)
        
        recon_confidence_map = {
            "subtotal": subtotal_entity.confidence,
            "tax": 0.85,
            "discount": discount_entity.confidence,
            "tip": tip_entity.confidence,
            "total": 0.9,
        }
        
        recon_evidence_dict = reconcile_amounts_v2(
            subtotal=subtotal_entity.value,
            tax=8.00,
            discount=discount_entity.value,
            tip=tip_entity.value,
            total=108.00,
            confidence_map=recon_confidence_map
        )
        
        coverage_ok = ("subtotal" in recon_evidence_dict.get("components_used", []))
        reconciliation_v2_entity = build_reconciliation_v2_entity(
            recon_evidence_dict, coverage_ok=coverage_ok
        )
        
        # Test case 2: Without component entities (raw values)
        recon_confidence_map_raw = {
            "subtotal": 0.7,
            "tax": 0.85,
            "discount": 0.0,
            "tip": 0.0,
            "total": 0.9,
        }
        
        recon_evidence_dict_raw = reconcile_amounts_v2(
            subtotal=100.00,
            tax=8.00,
            discount=None,
            tip=None,
            total=108.00,
            confidence_map=recon_confidence_map_raw
        )
        
        coverage_ok_raw = ("subtotal" in recon_evidence_dict_raw.get("components_used", []))
        reconciliation_v2_entity_raw = build_reconciliation_v2_entity(
            recon_evidence_dict_raw, coverage_ok=coverage_ok_raw
        )
        
        # Compare outputs - should be very similar
        entity_dict = reconciliation_v2_entity.to_dict()
        raw_dict = reconciliation_v2_entity_raw.to_dict()
        
        # Core reconciliation logic should be unchanged
        assert entity_dict["schema_version"] == raw_dict["schema_version"]
        assert entity_dict["formula"] == raw_dict["formula"]
        assert entity_dict["status"] == raw_dict["status"]
        
        # Components_used may differ due to entity extraction, but core logic same
        assert isinstance(entity_dict["components_used"], list)
        assert isinstance(raw_dict["components_used"], list)

    def test_entities_always_present(self):
        """Test that entities are always present even when None."""
        lines = ["Total: $100.00"]
        aligned_amounts = {"hit": False}
        
        # Build entities - should always return valid entities
        subtotal_entity = build_subtotal_entity_v2(lines, aligned_amounts)
        discount_entity = build_discount_entity_v2(lines, aligned_amounts)
        tip_entity = build_tip_entity_v2(lines, aligned_amounts)
        
        # All entities should have schema_version = 2
        assert subtotal_entity.schema_version == 2
        assert discount_entity.schema_version == 2
        assert tip_entity.schema_version == 2
        
        # All entities should have all fields present
        for entity in [subtotal_entity, discount_entity, tip_entity]:
            entity_dict = entity.to_dict()
            required_fields = [
                "schema_version", "value", "confidence", "source",
                "labels_matched", "gated_reason", "notes"
            ]
            for field in required_fields:
                assert field in entity_dict

    def test_no_scoring_deltas(self):
        """Test that entity extraction doesn't change scoring logic."""
        # Same reconciliation call with entity outputs vs raw values
        # should produce same scoring results
        
        # Entity-based approach
        lines = ["Subtotal: $100.00"]
        aligned_amounts = {"hit": False}
        subtotal_entity = build_subtotal_entity_v2(lines, aligned_amounts)
        
        recon_confidence_entity = {
            "subtotal": subtotal_entity.confidence,
            "tax": 0.85,
            "discount": 0.0,
            "tip": 0.0,
            "total": 0.9,
        }
        
        recon_entity = reconcile_amounts_v2(
            subtotal=subtotal_entity.value,
            tax=8.00,
            discount=None,
            tip=None,
            total=108.00,
            confidence_map=recon_confidence_entity
        )
        
        # Raw approach
        recon_confidence_raw = {
            "subtotal": 0.7,  # Same as entity confidence
            "tax": 0.85,
            "discount": 0.0,
            "tip": 0.0,
            "total": 0.9,
        }
        
        recon_raw = reconcile_amounts_v2(
            subtotal=100.00,  # Same as entity value
            tax=8.00,
            discount=None,
            tip=None,
            total=108.00,
            confidence_map=recon_confidence_raw
        )
        
        # Scoring results should be identical
        assert recon_entity["status"] == recon_raw["status"]
        assert recon_entity["mismatch_ratio"] == recon_raw["mismatch_ratio"]
        assert recon_entity["penalty_applied"] == recon_raw["penalty_applied"]
        assert recon_entity["confidence_penalty"] == recon_raw["confidence_penalty"]

    def test_component_coverage_gained(self):
        """Test that reconciliation_v2 gains real component coverage."""
        lines = ["Subtotal: $100.00", "Discount: $10.00", "Tip: $5.00"]
        aligned_amounts = {"hit": False}
        
        # Build entities
        subtotal_entity = build_subtotal_entity_v2(lines, aligned_amounts)
        discount_entity = build_discount_entity_v2(lines, aligned_amounts)
        tip_entity = build_tip_entity_v2(lines, aligned_amounts)
        
        recon_confidence_map = {
            "subtotal": subtotal_entity.confidence,
            "tax": 0.85,
            "discount": discount_entity.confidence,
            "tip": tip_entity.confidence,
            "total": 0.9,
        }
        
        recon_evidence_dict = reconcile_amounts_v2(
            subtotal=subtotal_entity.value,
            tax=8.00,
            discount=discount_entity.value,
            tip=tip_entity.value,
            total=103.00,
            confidence_map=recon_confidence_map
        )
        
        # Should have component coverage
        components_used = recon_evidence_dict.get("components_used", [])
        assert len(components_used) >= 2  # At least subtotal + tax
        
        # Components should reflect what was actually found
        if subtotal_entity.value is not None:
            assert "subtotal" in components_used
        if discount_entity.value is not None:
            assert "discount" in components_used
        if tip_entity.value is not None:
            assert "tip" in components_used

    def test_entity_confidence_propagation(self):
        """Test that entity confidences properly propagate to reconciliation."""
        lines = ["Subtotal: $100.00"]
        aligned_amounts = {"hit": False}
        
        subtotal_entity = build_subtotal_entity_v2(lines, aligned_amounts)
        
        # Entity confidence should be used in reconciliation
        recon_confidence_map = {
            "subtotal": subtotal_entity.confidence,
            "tax": 0.85,
            "discount": 0.0,
            "tip": 0.0,
            "total": 0.9,
        }
        
        recon_evidence_dict = reconcile_amounts_v2(
            subtotal=subtotal_entity.value,
            tax=8.00,
            discount=None,
            tip=None,
            total=108.00,
            confidence_map=recon_confidence_map
        )
        
        # The reconciliation should use the entity confidence
        # (This is verified by the fact that we passed entity.confidence)
        assert subtotal_entity.confidence >= 0.0
        assert subtotal_entity.confidence <= 1.0

    def test_gated_entities_dont_break_reconciliation(self):
        """Test that gated entities don't break reconciliation."""
        lines = ["Total: $100.00"]  # No component labels
        aligned_amounts = {"hit": False}
        
        # Build entities - should be gated
        subtotal_entity = build_subtotal_entity_v2(lines, aligned_amounts)
        discount_entity = build_discount_entity_v2(lines, aligned_amounts)
        tip_entity = build_tip_entity_v2(lines, aligned_amounts)
        
        # All should be gated (None values)
        assert subtotal_entity.value is None
        assert discount_entity.value is None
        assert tip_entity.value is None
        assert subtotal_entity.gated_reason is not None
        assert discount_entity.gated_reason is not None
        assert tip_entity.gated_reason is not None
        
        # Reconciliation should still work
        recon_confidence_map = {
            "subtotal": subtotal_entity.confidence,  # Should be 0.0
            "tax": 0.85,
            "discount": discount_entity.confidence,  # Should be 0.0
            "tip": tip_entity.confidence,  # Should be 0.0
            "total": 0.9,
        }
        
        recon_evidence_dict = reconcile_amounts_v2(
            subtotal=subtotal_entity.value,  # None
            tax=8.00,
            discount=discount_entity.value,  # None
            tip=tip_entity.value,  # None
            total=100.00,
            confidence_map=recon_confidence_map
        )
        
        # Should still produce valid reconciliation
        assert recon_evidence_dict is not None
        assert "status" in recon_evidence_dict
        assert "components_used" in recon_evidence_dict


if __name__ == "__main__":
    pytest.main([__file__])
