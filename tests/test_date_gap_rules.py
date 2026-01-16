"""
Golden tests for R16_SUSPICIOUS_DATE_GAP conditional severity.

These tests verify that date gap penalties are correctly downgraded based on
document profile confidence:
- Low confidence (< 0.4) + moderate gap (< 540 days) → WARNING (0.10)
- High confidence or extreme gap → CRITICAL (0.35)

Running:
    python -m pytest tests/test_date_gap_rules.py -v

Coverage:
    - Low dp_conf + gap < 540 → WARNING severity
    - High dp_conf + gap < 540 → CRITICAL severity
    - Low dp_conf + gap >= 540 → CRITICAL severity
    - Edge cases around thresholds
"""

import pytest
from datetime import datetime, timedelta
from typing import Dict, Any, List

from app.pipelines.rules import _score_and_explain, RuleEvent
from app.schemas.receipt import ReceiptFeatures, ReceiptRaw


# -----------------------------------------------------------------------------
# Test helpers
# -----------------------------------------------------------------------------

def _create_minimal_features(
    receipt_date_str: str,
    creation_date_str: str,
    doc_profile_confidence: float,
) -> Dict[str, Any]:
    """Create minimal text_features dict for date gap testing."""
    return {
        "receipt_date": receipt_date_str,
        "has_date": True,
        "doc_profile_confidence": doc_profile_confidence,
        "doc_subtype_guess": "UTILITY",
        "has_any_amount": True,
        "total_line_present": True,
        "merchant_candidate": "Test Merchant",
    }


def _find_event(events: List[RuleEvent], rule_id: str) -> RuleEvent:
    """Find event by rule_id."""
    for event in events:
        if event.rule_id == rule_id:
            return event
    raise AssertionError(f"Event {rule_id} not found in {[e.rule_id for e in events]}")


# -----------------------------------------------------------------------------
# Test: Low confidence + moderate gap → WARNING
# -----------------------------------------------------------------------------

def test_low_confidence_moderate_gap_downgraded():
    """Low dp_conf (< 0.4) + gap < 540 days → WARNING severity, weight ~0.10."""
    
    # Setup: 399 days gap, dp_conf = 0.2
    receipt_date = "2023-09-05"
    creation_date = "D:20241008184241+05'30'"  # ~399 days later
    
    tf = _create_minimal_features(
        receipt_date_str=receipt_date,
        creation_date_str=creation_date,
        doc_profile_confidence=0.2,  # Low confidence
    )
    
    # Create minimal ReceiptFeatures
    raw = ReceiptRaw(
        file_path="/tmp/test.pdf",
        full_text="Test receipt",
        metadata={"creation_date": creation_date},
    )
    
    features = ReceiptFeatures(
        raw=raw,
        text_features=tf,
        layout_features={},
        metadata_features={"creation_date": creation_date},
        doc_profile={
            "family": "TRANSACTIONAL",
            "subtype": "UTILITY",
            "confidence": 0.2,
        },
    )
    
    # Run scoring
    decision = _score_and_explain(features, apply_learned=False)
    
    # Find R16 event
    r16_event = _find_event(decision.events, "R16_SUSPICIOUS_DATE_GAP")
    
    # Assertions
    assert r16_event.severity == "WARNING", f"Expected WARNING severity, got {r16_event.severity}"
    assert r16_event.weight == 0.10, f"Expected weight 0.10, got {r16_event.weight}"
    assert r16_event.evidence.get("severity_downgraded") is True, "Should be marked as downgraded"
    assert r16_event.evidence.get("doc_profile_confidence") == 0.2, "Should include dp_conf in evidence"
    assert r16_event.evidence.get("gap_days") == 399 or r16_event.evidence.get("gap_days") >= 390, \
        f"Gap days should be ~399, got {r16_event.evidence.get('gap_days')}"


def test_low_confidence_edge_case_539_days():
    """Edge case: dp_conf = 0.39, gap = 539 days → should still be WARNING."""
    
    # Setup: 539 days gap (just under threshold), dp_conf = 0.39
    receipt_date = "2023-01-01"
    # 539 days later
    creation_datetime = datetime(2023, 1, 1) + timedelta(days=539)
    creation_date = creation_datetime.strftime("D:%Y%m%d120000+00'00'")
    
    tf = _create_minimal_features(
        receipt_date_str=receipt_date,
        creation_date_str=creation_date,
        doc_profile_confidence=0.39,  # Just under threshold
    )
    
    raw = ReceiptRaw(
        file_path="/tmp/test.pdf",
        full_text="Test receipt",
        metadata={"creation_date": creation_date},
    )
    
    features = ReceiptFeatures(
        raw=raw,
        text_features=tf,
        layout_features={},
        metadata_features={"creation_date": creation_date},
        doc_profile={
            "family": "TRANSACTIONAL",
            "subtype": "UTILITY",
            "confidence": 0.39,
        },
    )
    
    decision = _score_and_explain(features, apply_learned=False)
    r16_event = _find_event(decision.events, "R16_SUSPICIOUS_DATE_GAP")
    
    # Should be downgraded (both conditions met)
    assert r16_event.severity == "WARNING", "Should be WARNING for dp_conf=0.39, gap=539"
    assert r16_event.weight == 0.10, "Should have weight 0.10"


# -----------------------------------------------------------------------------
# Test: High confidence OR extreme gap → CRITICAL
# -----------------------------------------------------------------------------

def test_high_confidence_moderate_gap_critical():
    """High dp_conf (>= 0.4) + gap < 540 → CRITICAL severity, weight 0.35."""
    
    # Setup: 300 days gap, dp_conf = 0.7 (high confidence)
    receipt_date = "2023-01-01"
    creation_datetime = datetime(2023, 1, 1) + timedelta(days=300)
    creation_date = creation_datetime.strftime("D:%Y%m%d120000+00'00'")
    
    tf = _create_minimal_features(
        receipt_date_str=receipt_date,
        creation_date_str=creation_date,
        doc_profile_confidence=0.7,  # High confidence
    )
    
    raw = ReceiptRaw(
        file_path="/tmp/test.pdf",
        full_text="Test receipt",
        metadata={"creation_date": creation_date},
    )
    
    features = ReceiptFeatures(
        raw=raw,
        text_features=tf,
        layout_features={},
        metadata_features={"creation_date": creation_date},
        doc_profile={
            "family": "TRANSACTIONAL",
            "subtype": "POS_RESTAURANT",
            "confidence": 0.7,
        },
    )
    
    decision = _score_and_explain(features, apply_learned=False)
    r16_event = _find_event(decision.events, "R16_SUSPICIOUS_DATE_GAP")
    
    # Should NOT be downgraded (high confidence)
    assert r16_event.severity == "CRITICAL", f"Expected CRITICAL severity, got {r16_event.severity}"
    assert r16_event.weight == 0.35, f"Expected weight 0.35, got {r16_event.weight}"
    assert r16_event.evidence.get("severity_downgraded") is False, "Should NOT be marked as downgraded"


def test_low_confidence_extreme_gap_critical():
    """Low dp_conf (< 0.4) + gap >= 540 → CRITICAL severity, weight 0.35."""
    
    # Setup: 600 days gap (extreme), dp_conf = 0.2
    receipt_date = "2023-01-01"
    creation_datetime = datetime(2023, 1, 1) + timedelta(days=600)
    creation_date = creation_datetime.strftime("D:%Y%m%d120000+00'00'")
    
    tf = _create_minimal_features(
        receipt_date_str=receipt_date,
        creation_date_str=creation_date,
        doc_profile_confidence=0.2,  # Low confidence
    )
    
    raw = ReceiptRaw(
        file_path="/tmp/test.pdf",
        full_text="Test receipt",
        metadata={"creation_date": creation_date},
    )
    
    features = ReceiptFeatures(
        raw=raw,
        text_features=tf,
        layout_features={},
        metadata_features={"creation_date": creation_date},
        doc_profile={
            "family": "TRANSACTIONAL",
            "subtype": "UTILITY",
            "confidence": 0.2,
        },
    )
    
    decision = _score_and_explain(features, apply_learned=False)
    r16_event = _find_event(decision.events, "R16_SUSPICIOUS_DATE_GAP")
    
    # Should NOT be downgraded (extreme gap)
    assert r16_event.severity == "CRITICAL", "Should be CRITICAL for extreme gap (600 days)"
    assert r16_event.weight == 0.35, "Should have weight 0.35"
    assert r16_event.evidence.get("severity_downgraded") is False, "Should NOT be downgraded"


def test_edge_case_540_days_critical():
    """Edge case: gap = 540 days exactly → should be CRITICAL."""
    
    # Setup: exactly 540 days gap
    receipt_date = "2023-01-01"
    creation_datetime = datetime(2023, 1, 1) + timedelta(days=540)
    creation_date = creation_datetime.strftime("D:%Y%m%d120000+00'00'")
    
    tf = _create_minimal_features(
        receipt_date_str=receipt_date,
        creation_date_str=creation_date,
        doc_profile_confidence=0.2,
    )
    
    raw = ReceiptRaw(
        file_path="/tmp/test.pdf",
        full_text="Test receipt",
        metadata={"creation_date": creation_date},
    )
    
    features = ReceiptFeatures(
        raw=raw,
        text_features=tf,
        layout_features={},
        metadata_features={"creation_date": creation_date},
        doc_profile={
            "family": "TRANSACTIONAL",
            "subtype": "UTILITY",
            "confidence": 0.2,
        },
    )
    
    decision = _score_and_explain(features, apply_learned=False)
    r16_event = _find_event(decision.events, "R16_SUSPICIOUS_DATE_GAP")
    
    # Should be CRITICAL (gap >= 540)
    assert r16_event.severity == "CRITICAL", "Should be CRITICAL for gap=540 (at threshold)"
    assert r16_event.weight == 0.35, "Should have weight 0.35"


def test_edge_case_dp_conf_040_critical():
    """Edge case: dp_conf = 0.40 exactly → should be CRITICAL."""
    
    # Setup: dp_conf = 0.40 (at threshold), gap = 300
    receipt_date = "2023-01-01"
    creation_datetime = datetime(2023, 1, 1) + timedelta(days=300)
    creation_date = creation_datetime.strftime("D:%Y%m%d120000+00'00'")
    
    tf = _create_minimal_features(
        receipt_date_str=receipt_date,
        creation_date_str=creation_date,
        doc_profile_confidence=0.40,  # Exactly at threshold
    )
    
    raw = ReceiptRaw(
        file_path="/tmp/test.pdf",
        full_text="Test receipt",
        metadata={"creation_date": creation_date},
    )
    
    features = ReceiptFeatures(
        raw=raw,
        text_features=tf,
        layout_features={},
        metadata_features={"creation_date": creation_date},
        doc_profile={
            "family": "TRANSACTIONAL",
            "subtype": "UTILITY",
            "confidence": 0.40,
        },
    )
    
    decision = _score_and_explain(features, apply_learned=False)
    r16_event = _find_event(decision.events, "R16_SUSPICIOUS_DATE_GAP")
    
    # Should be CRITICAL (dp_conf >= 0.4)
    assert r16_event.severity == "CRITICAL", "Should be CRITICAL for dp_conf=0.40 (at threshold)"
    assert r16_event.weight == 0.35, "Should have weight 0.35"


# -----------------------------------------------------------------------------
# Test: Evidence payload
# -----------------------------------------------------------------------------

def test_evidence_includes_required_fields():
    """Evidence should include gap_days, doc_profile_confidence, severity_downgraded."""
    
    receipt_date = "2023-01-01"
    creation_datetime = datetime(2023, 1, 1) + timedelta(days=100)
    creation_date = creation_datetime.strftime("D:%Y%m%d120000+00'00'")
    
    tf = _create_minimal_features(
        receipt_date_str=receipt_date,
        creation_date_str=creation_date,
        doc_profile_confidence=0.3,
    )
    
    raw = ReceiptRaw(
        file_path="/tmp/test.pdf",
        full_text="Test receipt",
        metadata={"creation_date": creation_date},
    )
    
    features = ReceiptFeatures(
        raw=raw,
        text_features=tf,
        layout_features={},
        metadata_features={"creation_date": creation_date},
        doc_profile={
            "family": "TRANSACTIONAL",
            "subtype": "UTILITY",
            "confidence": 0.3,
        },
    )
    
    decision = _score_and_explain(features, apply_learned=False)
    r16_event = _find_event(decision.events, "R16_SUSPICIOUS_DATE_GAP")
    
    # Check evidence fields
    assert "gap_days" in r16_event.evidence, "Evidence should include gap_days"
    assert "doc_profile_confidence" in r16_event.evidence, "Evidence should include doc_profile_confidence"
    assert "severity_downgraded" in r16_event.evidence, "Evidence should include severity_downgraded"
    assert "receipt_date" in r16_event.evidence, "Evidence should include receipt_date"
    assert "creation_date" in r16_event.evidence, "Evidence should include creation_date"
    
    # Check values
    assert r16_event.evidence["doc_profile_confidence"] == 0.3, "Should match input dp_conf"
    assert isinstance(r16_event.evidence["severity_downgraded"], bool), "severity_downgraded should be boolean"
