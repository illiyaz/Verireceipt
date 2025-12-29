"""
Unit tests for learned rules mini-engine.
Tests dedupe and suppression logic for missing_elements and other learned patterns.
"""

import pytest
from app.pipelines import rules as r


def test_apply_learned_rules_dedupes_and_suppresses_missing_elements():
    """
    Test that _apply_learned_rules:
    1. Dedupes duplicate missing_elements triggers
    2. Suppresses missing_elements when gate is OFF (missing_fields_enabled=False)
    3. Applies non-suppressed rules correctly
    """
    triggered = [
        "Learned pattern detected: missing_elements. Identified by users 5 times. Confidence adjustment: +0.15.",
        "Learned pattern detected: missing_elements. Identified by users 5 times. Confidence adjustment: +0.15.",  # duplicate
        "Learned pattern detected: spacing_anomaly. Identified by users 3 times. Confidence adjustment: +0.10.",
    ]

    events = []
    reasons = []

    delta = r._apply_learned_rules(
        triggered_rules=triggered,
        events=events,
        reasons=reasons,
        tf={},
        doc_profile={"family": "UNKNOWN", "subtype": "UNKNOWN"},
        missing_fields_enabled=False,   # gate OFF => missing_elements suppressed
        dp_conf=1.0,
        optional_subtype=False,
    )

    # missing_elements suppressed, spacing_anomaly applies once
    assert abs(delta - 0.10) < 1e-9, f"Expected delta=0.10, got {delta}"

    # Only one missing_elements reason should exist after dedupe
    suppressed_reasons = [x for x in reasons if "missing_elements" in x.lower() and "suppressed" in x.lower()]
    assert len(suppressed_reasons) == 1, f"Expected 1 suppressed missing_elements reason, got {len(suppressed_reasons)}"

    # spacing_anomaly reason should exist and not be suppressed
    spacing_reasons = [x for x in reasons if "spacing_anomaly" in x.lower()]
    assert len(spacing_reasons) == 1, f"Expected 1 spacing_anomaly reason, got {len(spacing_reasons)}"
    assert "suppressed" not in spacing_reasons[0].lower(), "spacing_anomaly should not be suppressed"

    # Event emitted once per deduped trigger => 2 events expected
    lr_events = [e for e in events if getattr(e, "rule_id", "") == "LR_LEARNED_PATTERN"]
    assert len(lr_events) == 2, f"Expected 2 LR_LEARNED_PATTERN events, got {len(lr_events)}"

    # Verify missing_elements event is marked as suppressed
    missing_events = [e for e in lr_events if "missing_elements" in str(getattr(e, "evidence", {}).get("pattern", "")).lower()]
    assert len(missing_events) == 1, f"Expected 1 missing_elements event, got {len(missing_events)}"
    assert missing_events[0].evidence.get("suppressed") is True, "missing_elements event should be suppressed"
    assert missing_events[0].evidence.get("applied_to_score") is False, "missing_elements should not be applied to score"

    # Verify spacing_anomaly event is not suppressed
    spacing_events = [e for e in lr_events if "spacing_anomaly" in str(getattr(e, "evidence", {}).get("pattern", "")).lower()]
    assert len(spacing_events) == 1, f"Expected 1 spacing_anomaly event, got {len(spacing_events)}"
    assert spacing_events[0].evidence.get("suppressed") is False, "spacing_anomaly event should not be suppressed"
    assert spacing_events[0].evidence.get("applied_to_score") is True, "spacing_anomaly should be applied to score"


def test_apply_learned_rules_with_gate_enabled():
    """
    Test that when gate is ON (missing_fields_enabled=True),
    missing_elements rules are NOT suppressed and contribute to score.
    """
    triggered = [
        "Learned pattern detected: missing_elements. Identified by users 5 times. Confidence adjustment: +0.15.",
        "Learned pattern detected: spacing_anomaly. Identified by users 3 times. Confidence adjustment: +0.10.",
    ]

    events = []
    reasons = []

    delta = r._apply_learned_rules(
        triggered_rules=triggered,
        events=events,
        reasons=reasons,
        tf={},
        doc_profile={"family": "TRANSACTIONAL", "subtype": "RECEIPT"},
        missing_fields_enabled=True,   # gate ON => missing_elements NOT suppressed
        dp_conf=1.0,
        optional_subtype=False,
    )

    # Both rules apply: 0.15 + 0.10 = 0.25
    assert abs(delta - 0.25) < 1e-9, f"Expected delta=0.25, got {delta}"

    # No suppressed reasons
    suppressed_reasons = [x for x in reasons if "suppressed" in x.lower()]
    assert len(suppressed_reasons) == 0, f"Expected 0 suppressed reasons, got {len(suppressed_reasons)}"

    # Both events should not be suppressed
    lr_events = [e for e in events if getattr(e, "rule_id", "") == "LR_LEARNED_PATTERN"]
    assert len(lr_events) == 2, f"Expected 2 LR_LEARNED_PATTERN events, got {len(lr_events)}"
    
    for event in lr_events:
        assert event.evidence.get("suppressed") is False, f"Event {event.evidence.get('pattern')} should not be suppressed"
        assert event.evidence.get("applied_to_score") is True, f"Event {event.evidence.get('pattern')} should be applied to score"


def test_apply_learned_rules_soft_gating():
    """
    Test that soft-gating factors (low doc_conf, optional_subtype) are applied correctly.
    """
    triggered = [
        "Learned pattern detected: spacing_anomaly. Identified by users 3 times. Confidence adjustment: +0.10.",
    ]

    events = []
    reasons = []

    # Test with low doc_conf (< 0.55)
    delta = r._apply_learned_rules(
        triggered_rules=triggered,
        events=events,
        reasons=reasons,
        tf={},
        doc_profile={"family": "TRANSACTIONAL", "subtype": "RECEIPT"},
        missing_fields_enabled=True,
        dp_conf=0.40,  # Low confidence => 0.65 multiplier
        optional_subtype=False,
    )

    # 0.10 * 0.65 = 0.065
    assert abs(delta - 0.065) < 1e-9, f"Expected delta=0.065, got {delta}"

    # Test with optional_subtype
    events.clear()
    reasons.clear()
    
    delta = r._apply_learned_rules(
        triggered_rules=triggered,
        events=events,
        reasons=reasons,
        tf={},
        doc_profile={"family": "TRANSACTIONAL", "subtype": "RECEIPT"},
        missing_fields_enabled=True,
        dp_conf=1.0,
        optional_subtype=True,  # Optional subtype => 0.60 multiplier
    )

    # 0.10 * 0.60 = 0.06
    assert abs(delta - 0.06) < 1e-9, f"Expected delta=0.06, got {delta}"

    # Test with both factors
    events.clear()
    reasons.clear()
    
    delta = r._apply_learned_rules(
        triggered_rules=triggered,
        events=events,
        reasons=reasons,
        tf={},
        doc_profile={"family": "TRANSACTIONAL", "subtype": "RECEIPT"},
        missing_fields_enabled=True,
        dp_conf=0.40,  # 0.65 multiplier
        optional_subtype=True,  # 0.60 multiplier
    )

    # 0.10 * 0.65 * 0.60 = 0.039
    assert abs(delta - 0.039) < 1e-9, f"Expected delta=0.039, got {delta}"


def test_learned_rule_dedupe_key():
    """Test that dedupe key normalizes whitespace correctly."""
    assert r._learned_rule_dedupe_key("  Test   String  ") == "test string"
    assert r._learned_rule_dedupe_key("Test\n\tString") == "test string"
    assert r._learned_rule_dedupe_key("") == ""
    assert r._learned_rule_dedupe_key(None) == ""


def test_parse_learned_rule():
    """Test that learned rule parsing extracts all fields correctly."""
    raw = "Learned pattern detected: missing_elements. Identified by users 5 times. Confidence adjustment: +0.15."
    
    parsed = r._parse_learned_rule(raw)
    
    assert parsed["pattern"] == "missing_elements"
    assert parsed["times_seen"] == 5
    assert abs(parsed["confidence_adjustment"] - 0.15) < 1e-9
    assert parsed["raw"] == raw

    # Test with missing fields
    raw2 = "Some unknown format"
    parsed2 = r._parse_learned_rule(raw2)
    
    assert parsed2["pattern"] == "unknown"
    assert parsed2["times_seen"] is None
    assert parsed2["confidence_adjustment"] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
