"""
Unit tests for EntityResult Schema V2 for ML labeling.
Tests backward compatibility, deterministic keys, and safe serialization.
"""

import pytest
import json
from typing import List, Dict, Any
from app.pipelines.features import EntityResult, EntityCandidate, _guess_merchant_entity


class TestEntityResultV2:
    """Test EntityResult V2 schema and helper methods."""

    def test_backward_compatibility(self):
        """Test that existing fields and behavior remain unchanged."""
        # Create basic EntityResult (V1 style)
        candidates = [
            EntityCandidate(
                value="Test Merchant",
                score=10.0,
                source="top_scan",
                line_idx=1,
                raw_line="Test Merchant",
                norm_line="test merchant",
                reasons=["company_name", "early_line"]
            )
        ]
        
        result = EntityResult(
            entity="merchant",
            value="Test Merchant",
            confidence=0.8,
            confidence_bucket="HIGH",
            candidates=candidates,
            evidence={"total_candidates": 1, "filtered_candidates": 1}
        )
        
        # Test V1 fields still work
        assert result.entity == "merchant"
        assert result.value == "Test Merchant"
        assert result.confidence == 0.8
        assert result.confidence_bucket == "HIGH"
        assert len(result.candidates) == 1
        assert result.candidates[0].value == "Test Merchant"
        assert result.evidence["total_candidates"] == 1
        
        # Test V2 fields have defaults
        assert result.schema_version == 1
        assert result.ml_payload is None
        assert result.candidates[0].penalties_applied == []
        assert result.candidates[0].boosts_applied == []
        assert result.candidates[0].matched_keywords == []
        assert result.candidates[0].zone == "none"

    def test_to_ml_dict_basic_structure(self):
        """Test to_ml_dict() returns stable JSON dict with required V2 fields."""
        candidates = [
            EntityCandidate(
                value="Global Trade Corp",
                score=12.0,
                source="top_scan",
                line_idx=2,
                raw_line="Global Trade Corp",
                norm_line="global trade corp",
                reasons=["seller_zone", "company_name"],
                zone="seller",
                penalties_applied=[{"name": "buyer_zone", "delta": -6}],
                boosts_applied=[{"name": "seller_zone", "delta": 8}],
                matched_keywords=["global", "trade"]
            ),
            EntityCandidate(
                value="Alternative Corp",
                score=8.0,
                source="label_next_line",
                line_idx=3,
                raw_line="Alternative Corp",
                norm_line="alternative corp",
                reasons=["label_next_line"],
                zone="none"
            )
        ]
        
        result = EntityResult(
            entity="merchant",
            value="Global Trade Corp",
            confidence=0.85,
            confidence_bucket="HIGH",
            candidates=candidates,
            evidence={
                "total_candidates": 2,
                "filtered_candidates": 2,
                "winner_margin": 4.0,
                "seller_zone_lines": [2, 3, 4],
                "buyer_zone_lines": []
            }
        )
        
        # Test ML dict generation
        ml_dict = result.to_ml_dict(
            doc_id="test_doc_123",
            page_count=1,
            lang_script="en-Latn"
        )
        
        # Verify required V2 fields
        assert ml_dict["schema_version"] == 2
        assert ml_dict["entity"] == "merchant"
        assert ml_dict["value"] == "Global Trade Corp"
        assert ml_dict["confidence"] == 0.85
        assert ml_dict["confidence_bucket"] == "HIGH"
        assert ml_dict["doc_id"] == "test_doc_123"
        assert ml_dict["page_count"] == 1
        assert ml_dict["lang_script"] == "en-Latn"
        
        # Verify mode trace
        assert isinstance(ml_dict["mode_trace"], list)
        assert len(ml_dict["mode_trace"]) == 1
        assert ml_dict["mode_trace"][0]["mode"] == "strict"
        assert ml_dict["mode_trace"][0]["winner"] == "Global Trade Corp"
        assert ml_dict["mode_trace"][0]["confidence"] == 0.85
        assert ml_dict["mode_trace"][0]["winner_margin"] == 4.0
        
        # Verify winner object
        winner = ml_dict["winner"]
        assert winner["value"] == "Global Trade Corp"
        assert winner["line_idx"] == 2
        assert winner["score"] == 12.0
        assert winner["source"] == "top_scan"
        assert winner["zone"] == "seller"
        assert len(winner["penalties_applied"]) == 1
        assert len(winner["boosts_applied"]) == 1
        assert len(winner["matched_keywords"]) == 2
        
        # Verify top-K candidates
        assert isinstance(ml_dict["top_k"], list)
        assert len(ml_dict["top_k"]) == 2
        assert ml_dict["top_k"][0]["rank"] == 1
        assert ml_dict["top_k"][0]["value"] == "Global Trade Corp"
        assert ml_dict["top_k"][1]["rank"] == 2
        assert ml_dict["top_k"][1]["value"] == "Alternative Corp"
        
        # Verify feature flags
        feature_flags = ml_dict["feature_flags"]
        assert feature_flags["in_seller_zone"] == True
        assert feature_flags["buyer_zone_penalty_applied"] == False
        assert feature_flags["company_name_hit"] == True
        assert feature_flags["label_next_line_hit"] == False
        
        # Verify labeling fields
        labeling = ml_dict["labeling_fields"]
        assert labeling["human_label"] is None
        assert labeling["labeler_notes"] is None
        assert labeling["error_type"] is None
        assert labeling["golden_case_id"] is None

    def test_to_candidate_rows(self):
        """Test to_candidate_rows() returns list of candidate-level rows."""
        candidates = [
            EntityCandidate(
                value="Winner Corp",
                score=15.0,
                source="top_scan",
                line_idx=1,
                raw_line="Winner Corp",
                norm_line="winner corp",
                reasons=["company_name"],
                zone="seller"
            ),
            EntityCandidate(
                value="Runner Up",
                score=10.0,
                source="label_next_line",
                line_idx=2,
                raw_line="Runner Up",
                norm_line="runner up",
                reasons=["label_next_line"],
                zone="none"
            )
        ]
        
        result = EntityResult(
            entity="merchant",
            value="Winner Corp",
            confidence=0.9,
            confidence_bucket="HIGH",
            candidates=candidates,
            evidence={"total_candidates": 2}
        )
        
        rows = result.to_candidate_rows(doc_id="test_doc_456")
        
        # Verify structure
        assert isinstance(rows, list)
        assert len(rows) == 2
        
        # Verify winner row
        winner_row = rows[0]
        assert winner_row["doc_id"] == "test_doc_456"
        assert winner_row["entity"] == "merchant"
        assert winner_row["candidate_rank"] == 1
        assert winner_row["is_winner"] == True
        assert winner_row["value"] == "Winner Corp"
        assert winner_row["score"] == 15.0
        assert winner_row["final_confidence"] == 0.9
        assert winner_row["final_confidence_bucket"] == "HIGH"
        
        # Verify runner-up row
        runner_row = rows[1]
        assert runner_row["candidate_rank"] == 2
        assert runner_row["is_winner"] == False
        assert runner_row["value"] == "Runner Up"
        assert runner_row["score"] == 10.0
        assert runner_row["final_confidence"] is None
        assert runner_row["final_confidence_bucket"] is None

    def test_safe_json_serialization(self):
        """Test that ML dict can be safely serialized to JSON."""
        candidates = [
            EntityCandidate(
                value="Test Entity",
                score=8.5,
                source="test",
                line_idx=0,
                raw_line="Test Entity",
                norm_line="test entity",
                reasons=["test_reason"]
            )
        ]
        
        result = EntityResult(
            entity="test",
            value="Test Entity",
            confidence=0.75,
            confidence_bucket="MEDIUM",
            candidates=candidates,
            evidence={"test": "value"}
        )
        
        # Generate ML dict
        ml_dict = result.to_ml_dict()
        
        # Test JSON serialization
        try:
            json_str = json.dumps(ml_dict)
            parsed_back = json.loads(json_str)
            
            # Verify round-trip works
            assert parsed_back["schema_version"] == 2
            assert parsed_back["entity"] == "test"
            assert parsed_back["value"] == "Test Entity"
            assert parsed_back["confidence"] == 0.75
            
        except (TypeError, ValueError) as e:
            pytest.fail(f"JSON serialization failed: {e}")

    def test_deterministic_keys_and_types(self):
        """Test that ML dict has deterministic keys and types."""
        candidates = [
            EntityCandidate(
                value="Deterministic Test",
                score=10.0,
                source="test",
                line_idx=1,
                raw_line="Deterministic Test",
                norm_line="deterministic test",
                reasons=["test"]
            )
        ]
        
        result = EntityResult(
            entity="test",
            value="Deterministic Test",
            confidence=0.8,
            confidence_bucket="HIGH",
            candidates=candidates,
            evidence={}
        )
        
        ml_dict = result.to_ml_dict()
        
        # Verify required keys exist
        required_keys = [
            "schema_version", "entity", "value", "confidence", "confidence_bucket",
            "mode_trace", "winner", "winner_margin", "topk_gap",
            "candidate_count_total", "candidate_count_filtered", "top_k",
            "rejection_stats", "feature_flags", "labeling_fields"
        ]
        
        for key in required_keys:
            assert key in ml_dict, f"Missing required key: {key}"
        
        # Verify types are JSON-serializable
        type_checks = {
            "schema_version": int,
            "entity": str,
            "value": (str, type(None)),
            "confidence": (float, int),
            "confidence_bucket": str,
            "mode_trace": list,
            "winner_margin": (float, int),
            "topk_gap": (float, int),
            "candidate_count_total": int,
            "candidate_count_filtered": int,
            "top_k": list,
            "rejection_stats": dict,
            "feature_flags": dict,
            "labeling_fields": dict
        }
        
        for key, expected_type in type_checks.items():
            value = ml_dict[key]
            if isinstance(expected_type, tuple):
                assert isinstance(value, expected_type), f"Key {key} has wrong type: {type(value)} vs {expected_type}"
            else:
                assert isinstance(value, expected_type), f"Key {key} has wrong type: {type(value)} vs {expected_type}"

    def test_mode_trace_with_llm(self):
        """Test mode trace includes LLM mode when used."""
        candidates = [
            EntityCandidate(
                value="LLM Selected",
                score=8.0,
                source="llm_tiebreak",
                line_idx=1,
                raw_line="LLM Selected",
                norm_line="llm selected",
                reasons=["llm_tiebreak"]
            )
        ]
        
        result = EntityResult(
            entity="merchant",
            value="LLM Selected",
            confidence=0.6,
            confidence_bucket="MEDIUM",
            candidates=candidates,
            evidence={
                "llm_used": True,
                "llm_choice": "LLM Selected",
                "winner_margin": 1.5
            }
        )
        
        ml_dict = result.to_ml_dict()
        mode_trace = ml_dict["mode_trace"]
        
        # Should have both strict and LLM modes
        assert len(mode_trace) == 2
        assert mode_trace[0]["mode"] == "strict"
        assert mode_trace[1]["mode"] == "llm_tiebreak"
        assert mode_trace[1]["enabled_llm"] == True
        assert mode_trace[1]["llm_choice"] == "LLM Selected"

    def test_debug_context_gating(self):
        """Test debug context is gated by environment flag."""
        candidates = [
            EntityCandidate(
                value="Test",
                score=10.0,
                source="test",
                line_idx=1,
                raw_line="Test",
                norm_line="test",
                reasons=[]
            )
        ]
        
        result = EntityResult(
            entity="test",
            value="Test",
            confidence=0.8,
            confidence_bucket="HIGH",
            candidates=candidates,
            evidence={
                "seller_zone_lines": [1, 2, 3],
                "buyer_zone_lines": [4, 5]
            }
        )
        
        # Without debug context (default)
        ml_dict_no_debug = result.to_ml_dict(include_debug_context=False)
        assert ml_dict_no_debug["debug_context"] is None
        
        # With debug context explicitly enabled
        ml_dict_with_debug = result.to_ml_dict(include_debug_context=True)
        debug_context = ml_dict_with_debug["debug_context"]
        assert debug_context is not None
        assert "seller_zone_lines" in debug_context
        assert "buyer_zone_lines" in debug_context

    def test_integration_with_merchant_extraction(self):
        """Test integration with actual merchant extraction."""
        lines = [
            "INVOICE",
            "Global Trade Corporation", 
            "Bill To:",
            "Customer Name",
            "Total: $500.00"
        ]
        
        # Get merchant result
        merchant_result = _guess_merchant_entity(lines)
        
        # Test V2 methods work with real data
        ml_dict = merchant_result.to_ml_dict(doc_id="integration_test")
        candidate_rows = merchant_result.to_candidate_rows(doc_id="integration_test")
        
        # Verify structure
        assert ml_dict["schema_version"] == 2
        assert ml_dict["entity"] == "merchant"
        assert ml_dict["value"] is not None
        assert isinstance(candidate_rows, list)
        assert len(candidate_rows) > 0
        
        # Verify JSON serializable
        json.dumps(ml_dict)
        json.dumps(candidate_rows)


if __name__ == "__main__":
    pytest.main([__file__])
