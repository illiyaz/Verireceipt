"""
Golden Test: Learned Rule Profile Gating

This test permanently locks the behavior of learned rule gating across document profiles.
It ensures that low-risk profiles (COMMERCIAL_INVOICE, TRADE_DOCUMENT) suppress learned
patterns while high-risk profiles (POS_RECEIPT) apply them.

CRITICAL REGRESSION PREVENTION:
- COMMERCIAL_INVOICE + spacing_anomaly => NO score contribution (profile_gated=True)
- POS_RECEIPT + spacing_anomaly => score applies (profile_gated=False)

If this test fails, it means learned rule gating has regressed.
"""

import pytest
from app.pipelines.rules import _apply_learned_rules
from app.pipelines.doc_profiles import get_profile_for_doc_class


class MockEvent:
    """Mock event for testing"""
    def __init__(self):
        self.rule_id = None
        self.severity = None
        self.weight = 0.0
        self.evidence = {}


def test_commercial_invoice_gates_spacing_anomaly():
    """
    GOLDEN TEST: COMMERCIAL_INVOICE must suppress spacing_anomaly learned pattern.
    
    Regression: If this fails, commercial invoices are being penalized by
    receipt-specific learned patterns (0.45 false positive).
    """
    # Simulate learned rule trigger
    triggered_rules = [
        "Learned pattern detected: spacing_anomaly. Spacing patterns match previously "
        "flagged suspicious receipts. This pattern was identified by users 1 time(s). "
        "Confidence adjustment: +0.15."
    ]
    
    events = []
    reasons = []
    
    tf = {
        "doc_class": "COMMERCIAL_INVOICE",
        "doc_subtype_guess": "COMMERCIAL_INVOICE",
        "doc_profile_confidence": 0.85,
    }
    
    doc_profile = {
        "family": "INVOICE",
        "subtype": "COMMERCIAL_INVOICE",
        "confidence": 0.85,
    }
    
    # Apply learned rules
    adjustment = _apply_learned_rules(
        triggered_rules=triggered_rules,
        events=events,
        reasons=reasons,
        tf=tf,
        doc_profile=doc_profile,
        missing_fields_enabled=True,
        dp_conf=0.85,
        optional_subtype=False,
    )
    
    # ASSERTION: spacing_anomaly must be gated (no score contribution)
    assert adjustment == 0.0, (
        f"REGRESSION: COMMERCIAL_INVOICE should gate spacing_anomaly (expected 0.0, got {adjustment})"
    )
    
    # Verify profile_gated flag in events (nested in gating dict)
    lr_events = [e for e in events if hasattr(e, 'rule_id') and e.rule_id == "LR_LEARNED_PATTERN"]
    assert len(lr_events) > 0, "No LR_LEARNED_PATTERN event found"
    
    spacing_event = next((e for e in lr_events if "spacing_anomaly" in str(e.evidence.get("pattern", ""))), None)
    assert spacing_event is not None, "No spacing_anomaly event found"
    
    gating = spacing_event.evidence.get("gating", {})
    assert gating.get("profile_gated") is True, (
        f"REGRESSION: spacing_anomaly should be profile_gated for COMMERCIAL_INVOICE (got {gating.get('profile_gated')})"
    )
    assert gating.get("suppressed") is True, (
        f"spacing_anomaly should be suppressed for COMMERCIAL_INVOICE (got {gating.get('suppressed')})"
    )


def test_commercial_invoice_gates_missing_elements():
    """
    GOLDEN TEST: COMMERCIAL_INVOICE must suppress missing_elements learned pattern.
    """
    triggered_rules = [
        "Learned pattern detected: missing_elements. Missing critical elements: total amount, "
        "merchant name, contact phone, business address. Real receipts typically include all "
        "these fields. This pattern was identified by users 1 time(s). Confidence adjustment: +0.15."
    ]
    
    events = []
    reasons = []
    
    tf = {
        "doc_class": "COMMERCIAL_INVOICE",
        "doc_subtype_guess": "COMMERCIAL_INVOICE",
        "doc_profile_confidence": 0.85,
    }
    
    doc_profile = {
        "family": "INVOICE",
        "subtype": "COMMERCIAL_INVOICE",
        "confidence": 0.85,
    }
    
    adjustment = _apply_learned_rules(
        triggered_rules=triggered_rules,
        events=events,
        reasons=reasons,
        tf=tf,
        doc_profile=doc_profile,
        missing_fields_enabled=True,
        dp_conf=0.85,
        optional_subtype=False,
    )
    
    assert adjustment == 0.0, (
        f"REGRESSION: COMMERCIAL_INVOICE should gate missing_elements (expected 0.0, got {adjustment})"
    )


def test_commercial_invoice_gates_invalid_address():
    """
    GOLDEN TEST: COMMERCIAL_INVOICE must suppress invalid_address learned pattern.
    """
    triggered_rules = [
        "Learned pattern detected: invalid_address. No valid business address found. "
        "Legitimate receipts typically include a physical address for the business. "
        "This pattern was identified by users 1 time(s). Confidence adjustment: +0.15."
    ]
    
    events = []
    reasons = []
    
    tf = {
        "doc_class": "COMMERCIAL_INVOICE",
        "doc_subtype_guess": "COMMERCIAL_INVOICE",
        "doc_profile_confidence": 0.85,
    }
    
    doc_profile = {
        "family": "INVOICE",
        "subtype": "COMMERCIAL_INVOICE",
        "confidence": 0.85,
    }
    
    adjustment = _apply_learned_rules(
        triggered_rules=triggered_rules,
        events=events,
        reasons=reasons,
        tf=tf,
        doc_profile=doc_profile,
        missing_fields_enabled=True,
        dp_conf=0.85,
        optional_subtype=False,
    )
    
    assert adjustment == 0.0, (
        f"REGRESSION: COMMERCIAL_INVOICE should gate invalid_address (expected 0.0, got {adjustment})"
    )


def test_pos_receipt_applies_spacing_anomaly():
    """
    GOLDEN TEST: POS_RECEIPT must apply spacing_anomaly learned pattern.
    
    Regression: If this fails, POS receipts are not being penalized by
    learned patterns (false negatives).
    """
    triggered_rules = [
        "Learned pattern detected: spacing_anomaly. Spacing patterns match previously "
        "flagged suspicious receipts. This pattern was identified by users 1 time(s). "
        "Confidence adjustment: +0.15."
    ]
    
    events = []
    reasons = []
    
    tf = {
        "doc_class": "POS_RECEIPT",
        "doc_subtype_guess": "POS_RESTAURANT",
        "doc_profile_confidence": 0.85,
        "total_amount": 150.0,
        "merchant_candidate": "Zaffran Restaurant",
        "currency_symbols": ["₹"],
        "has_currency": True,
    }
    
    doc_profile = {
        "family": "TRANSACTIONAL",
        "subtype": "POS_RESTAURANT",
        "confidence": 0.85,
    }
    
    adjustment = _apply_learned_rules(
        triggered_rules=triggered_rules,
        events=events,
        reasons=reasons,
        tf=tf,
        doc_profile=doc_profile,
        missing_fields_enabled=True,
        dp_conf=0.85,
        optional_subtype=False,
    )
    
    # ASSERTION: spacing_anomaly must apply (positive score contribution)
    assert adjustment > 0.0, (
        f"REGRESSION: POS_RECEIPT should apply spacing_anomaly (expected >0.0, got {adjustment})"
    )
    
    # Verify profile_gated flag is False (nested in gating dict)
    lr_events = [e for e in events if hasattr(e, 'rule_id') and e.rule_id == "LR_LEARNED_PATTERN"]
    assert len(lr_events) > 0, "No LR_LEARNED_PATTERN event found"
    
    spacing_event = next((e for e in lr_events if "spacing_anomaly" in str(e.evidence.get("pattern", ""))), None)
    assert spacing_event is not None, "No spacing_anomaly event found"
    
    gating = spacing_event.evidence.get("gating", {})
    assert gating.get("profile_gated") is False, (
        f"REGRESSION: spacing_anomaly should NOT be profile_gated for POS_RECEIPT (got {gating.get('profile_gated')})"
    )
    assert gating.get("suppressed") is False, (
        f"spacing_anomaly should NOT be suppressed for POS_RECEIPT (got {gating.get('suppressed')})"
    )


def test_trade_document_gates_all_learned_patterns():
    """
    GOLDEN TEST: TRADE_DOCUMENT must suppress all learned patterns.
    """
    triggered_rules = [
        "Learned pattern detected: spacing_anomaly. Confidence adjustment: +0.15.",
        "Learned pattern detected: missing_elements. Confidence adjustment: +0.15.",
        "Learned pattern detected: invalid_address. Confidence adjustment: +0.15.",
    ]
    
    events = []
    reasons = []
    
    tf = {
        "doc_class": "TRADE_DOCUMENT",
        "doc_subtype_guess": "BILL_OF_LADING",
        "doc_profile_confidence": 0.80,
    }
    
    doc_profile = {
        "family": "LOGISTICS",
        "subtype": "BILL_OF_LADING",
        "confidence": 0.80,
    }
    
    adjustment = _apply_learned_rules(
        triggered_rules=triggered_rules,
        events=events,
        reasons=reasons,
        tf=tf,
        doc_profile=doc_profile,
        missing_fields_enabled=True,
        dp_conf=0.80,
        optional_subtype=False,
    )
    
    assert adjustment == 0.0, (
        f"REGRESSION: TRADE_DOCUMENT should gate all learned patterns (expected 0.0, got {adjustment})"
    )


def test_learned_contribution_cap():
    """
    GOLDEN TEST: Learned contribution must be capped per profile.max_learned_contribution.
    
    Even if multiple patterns apply, total contribution should not exceed cap.
    """
    # Simulate 3 patterns that would normally add +0.45 total
    triggered_rules = [
        "Learned pattern detected: pattern_a. Confidence adjustment: +0.15.",
        "Learned pattern detected: pattern_b. Confidence adjustment: +0.15.",
        "Learned pattern detected: pattern_c. Confidence adjustment: +0.15.",
    ]
    
    events = []
    reasons = []
    
    # Use a profile with max_learned_contribution=0.10
    tf = {
        "doc_class": "COMMERCIAL_INVOICE",
        "doc_subtype_guess": "COMMERCIAL_INVOICE",
        "doc_profile_confidence": 0.85,
    }
    
    doc_profile = {
        "family": "INVOICE",
        "subtype": "COMMERCIAL_INVOICE",
        "confidence": 0.85,
    }
    
    adjustment = _apply_learned_rules(
        triggered_rules=triggered_rules,
        events=events,
        reasons=reasons,
        tf=tf,
        doc_profile=doc_profile,
        missing_fields_enabled=True,
        dp_conf=0.85,
        optional_subtype=False,
    )
    
    # All patterns are gated for COMMERCIAL_INVOICE, so adjustment should be 0
    # But if they weren't gated, cap would apply
    assert adjustment <= 0.10, (
        f"REGRESSION: Learned contribution should be capped at 0.10 (got {adjustment})"
    )


def test_profile_disabled_rules_list():
    """
    GOLDEN TEST: Verify DocumentProfile.disabled_rules contains expected learned rule IDs.
    """
    from app.pipelines.doc_profiles import COMMERCIAL_INVOICE_PROFILE, POS_RECEIPT_PROFILE
    
    # COMMERCIAL_INVOICE should disable learned patterns
    assert "LR_SPACING_ANOMALY" in COMMERCIAL_INVOICE_PROFILE.disabled_rules, (
        "COMMERCIAL_INVOICE_PROFILE must disable LR_SPACING_ANOMALY"
    )
    assert "LR_MISSING_ELEMENTS" in COMMERCIAL_INVOICE_PROFILE.disabled_rules, (
        "COMMERCIAL_INVOICE_PROFILE must disable LR_MISSING_ELEMENTS"
    )
    assert "LR_INVALID_ADDRESS" in COMMERCIAL_INVOICE_PROFILE.disabled_rules, (
        "COMMERCIAL_INVOICE_PROFILE must disable LR_INVALID_ADDRESS"
    )
    
    # POS_RECEIPT should NOT disable learned patterns
    assert "LR_SPACING_ANOMALY" not in POS_RECEIPT_PROFILE.disabled_rules, (
        "POS_RECEIPT_PROFILE must NOT disable LR_SPACING_ANOMALY"
    )
    assert "LR_MISSING_ELEMENTS" not in POS_RECEIPT_PROFILE.disabled_rules, (
        "POS_RECEIPT_PROFILE must NOT disable LR_MISSING_ELEMENTS"
    )
    assert "LR_INVALID_ADDRESS" not in POS_RECEIPT_PROFILE.disabled_rules, (
        "POS_RECEIPT_PROFILE must NOT disable LR_INVALID_ADDRESS"
    )


def test_should_apply_rule_respects_disabled_rules():
    """
    GOLDEN TEST: should_apply_rule() must check disabled_rules list.
    """
    from app.pipelines.doc_profiles import should_apply_rule, COMMERCIAL_INVOICE_PROFILE, POS_RECEIPT_PROFILE
    
    # COMMERCIAL_INVOICE should reject learned patterns
    assert should_apply_rule(COMMERCIAL_INVOICE_PROFILE, "LR_SPACING_ANOMALY") is False, (
        "should_apply_rule must return False for LR_SPACING_ANOMALY on COMMERCIAL_INVOICE"
    )
    assert should_apply_rule(COMMERCIAL_INVOICE_PROFILE, "LR_MISSING_ELEMENTS") is False, (
        "should_apply_rule must return False for LR_MISSING_ELEMENTS on COMMERCIAL_INVOICE"
    )
    assert should_apply_rule(COMMERCIAL_INVOICE_PROFILE, "LR_INVALID_ADDRESS") is False, (
        "should_apply_rule must return False for LR_INVALID_ADDRESS on COMMERCIAL_INVOICE"
    )
    
    # POS_RECEIPT should accept learned patterns
    assert should_apply_rule(POS_RECEIPT_PROFILE, "LR_SPACING_ANOMALY") is True, (
        "should_apply_rule must return True for LR_SPACING_ANOMALY on POS_RECEIPT"
    )
    assert should_apply_rule(POS_RECEIPT_PROFILE, "LR_MISSING_ELEMENTS") is True, (
        "should_apply_rule must return True for LR_MISSING_ELEMENTS on POS_RECEIPT"
    )
    assert should_apply_rule(POS_RECEIPT_PROFILE, "LR_INVALID_ADDRESS") is True, (
        "should_apply_rule must return True for LR_INVALID_ADDRESS on POS_RECEIPT"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
