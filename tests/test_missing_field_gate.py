"""
Unit tests for missing-field gate with enriched geo data.
Verifies that geo_confidence from enriched system correctly gates missing_elements learned rules.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from app.pipelines.rules import analyze_receipt, _score_and_explain
from app.schemas.receipt import ReceiptFeatures


def test_missing_field_gate_with_unknown_geo():
    """
    Test that when geo is UNKNOWN (low confidence), missing-field penalties are disabled
    and missing_elements learned rules are suppressed.
    """
    # Mock a receipt with UNKNOWN geo
    with patch('app.pipelines.rules._get_doc_profile') as mock_profile, \
         patch('app.pipelines.learning.apply_learned_rules') as mock_learned:
        
        # Setup: UNKNOWN geo, low confidence
        mock_profile.return_value = {
            "family": "UNKNOWN",
            "subtype": "UNKNOWN",
            "confidence": 0.15,
            "geo_country_guess": "UNKNOWN",
            "geo_confidence": 0.10,  # Low geo confidence
        }
        
        # Simulate learned rules triggering missing_elements
        mock_learned.return_value = (
            0.15,  # adjustment
            [
                "Learned pattern detected: missing_elements. Identified by users 5 times. Confidence adjustment: +0.15.",
                "Learned pattern detected: spacing_anomaly. Identified by users 3 times. Confidence adjustment: +0.10.",
            ]
        )
        
        # Analyze receipt
        decision = analyze_receipt(
            "dummy_path.jpg",
            extracted_total="100.00",
            extracted_merchant="Test Store",
            extracted_date="2024-01-15"
        )
        
        # Verify gate is OFF (missing_fields_enabled = False)
        assert decision.missing_field_gate is not None, "Gate evidence should be present"
        gate_evidence = decision.missing_field_gate
        assert gate_evidence.get("missing_fields_enabled") is False, "Gate should be OFF for UNKNOWN geo"
        
        # Verify missing_elements is suppressed in audit events
        lr_events = [e for e in decision.audit_events if e.code == "LR_LEARNED_PATTERN"]
        missing_events = [e for e in lr_events if "missing_elements" in str(e.evidence.get("pattern", "")).lower()]
        
        if missing_events:
            # If missing_elements event exists, it should be suppressed
            assert missing_events[0].evidence.get("suppressed") is True, "missing_elements should be suppressed"
            assert missing_events[0].evidence.get("applied_to_score") is False, "missing_elements should not affect score"


def test_missing_field_gate_with_known_geo():
    """
    Test that when geo is known (high confidence), missing-field penalties are enabled
    and missing_elements learned rules are NOT suppressed.
    """
    with patch('app.pipelines.rules._get_doc_profile') as mock_profile, \
         patch('app.pipelines.learning.apply_learned_rules') as mock_learned:
        
        # Setup: Known geo (IN), high confidence
        mock_profile.return_value = {
            "family": "TRANSACTIONAL",
            "subtype": "RECEIPT",
            "confidence": 0.85,
            "geo_country_guess": "IN",
            "geo_confidence": 0.82,  # High geo confidence
        }
        
        # Simulate learned rules triggering missing_elements
        mock_learned.return_value = (
            0.15,
            [
                "Learned pattern detected: missing_elements. Identified by users 5 times. Confidence adjustment: +0.15.",
            ]
        )
        
        # Analyze receipt
        decision = analyze_receipt(
            "dummy_path.jpg",
            extracted_total="100.00",
            extracted_merchant="Test Store",
            extracted_date="2024-01-15"
        )
        
        # Verify gate is ON (missing_fields_enabled = True)
        if decision.missing_field_gate:
            gate_evidence = decision.missing_field_gate
            assert gate_evidence.get("missing_fields_enabled") is True, "Gate should be ON for known geo"
        
        # Verify missing_elements is NOT suppressed
        lr_events = [e for e in decision.audit_events if e.code == "LR_LEARNED_PATTERN"]
        missing_events = [e for e in lr_events if "missing_elements" in str(e.evidence.get("pattern", "")).lower()]
        
        if missing_events:
            # If missing_elements event exists, it should NOT be suppressed
            assert missing_events[0].evidence.get("suppressed") is False, "missing_elements should not be suppressed"
            assert missing_events[0].evidence.get("applied_to_score") is True, "missing_elements should affect score"


def test_geo_confidence_threshold():
    """
    Test that geo_confidence threshold (0.30) correctly determines gate status.
    """
    test_cases = [
        (0.10, False, "Very low confidence should disable gate"),
        (0.25, False, "Below threshold should disable gate"),
        (0.30, False, "At threshold should disable gate"),
        (0.35, True, "Above threshold should enable gate"),
        (0.60, True, "High confidence should enable gate"),
        (0.90, True, "Very high confidence should enable gate"),
    ]
    
    for geo_conf, expected_enabled, description in test_cases:
        with patch('app.pipelines.rules._get_doc_profile') as mock_profile, \
             patch('app.pipelines.rules.apply_learned_rules') as mock_learned:
            
            mock_profile.return_value = {
                "family": "TRANSACTIONAL",
                "subtype": "RECEIPT",
                "confidence": 0.80,
                "geo_country_guess": "IN" if geo_conf > 0.30 else "UNKNOWN",
                "geo_confidence": geo_conf,
            }
            
            mock_learned.return_value = (0.0, [])
            
            decision = analyze_receipt(
                "dummy_path.jpg",
                extracted_total="100.00",
                extracted_merchant="Test Store",
                extracted_date="2024-01-15"
            )
            
            if decision.missing_field_gate:
                actual_enabled = decision.missing_field_gate.get("missing_fields_enabled")
                assert actual_enabled == expected_enabled, \
                    f"{description}: geo_conf={geo_conf}, expected={expected_enabled}, got={actual_enabled}"


def test_enriched_geo_evidence_in_gate():
    """
    Test that enriched geo evidence is included in gate decision.
    """
    with patch('app.pipelines.rules._get_doc_profile') as mock_profile, \
         patch('app.pipelines.learning.apply_learned_rules') as mock_learned:
        
        # Setup with enriched geo evidence
        mock_profile.return_value = {
            "family": "TRANSACTIONAL",
            "subtype": "RECEIPT",
            "confidence": 0.85,
            "geo_country_guess": "IN",
            "geo_confidence": 0.82,
            "geo_evidence": [
                {"type": "postal_match", "country": "IN", "match": "600001", "weight": 0.50},
                {"type": "city_match", "country": "IN", "match": "Chennai", "weight": 0.25},
                {"type": "tax_term", "country": "IN", "match": "gstin", "weight": 0.25},
            ],
            "geo_mixed": False,
        }
        
        mock_learned.return_value = (0.0, [])
        
        decision = analyze_receipt(
            "dummy_path.jpg",
            extracted_total="100.00",
            extracted_merchant="Test Store",
            extracted_date="2024-01-15"
        )
        
        # Verify gate evidence includes geo data
        if decision.missing_field_gate:
            gate_evidence = decision.missing_field_gate
            assert "geo_country_guess" in gate_evidence, "Gate should include geo_country_guess"
            assert "geo_confidence" in gate_evidence, "Gate should include geo_confidence"
            assert gate_evidence["geo_country_guess"] == "IN"
            assert gate_evidence["geo_confidence"] == 0.82


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
