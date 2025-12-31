"""
Unit tests for ReceiptDecision serialization and audit event handling.
Ensures the serialization contract for ReceiptDecision.to_dict() is maintained.
"""

import pytest
from app.schemas.receipt import ReceiptDecision, AuditEvent


def test_receipt_decision_to_dict_events_vs_audit_events():
    """
    Ensure legacy `events` is always an empty list when unused,
    while `audit_events` contains the real audit trail.
    """
    decision = ReceiptDecision(
        label="fake",
        score=0.9,
        reasons=["test"]
    )

    decision.add_audit_event(
        AuditEvent(
            source="rules",
            type="rule_triggered",
            severity="CRITICAL",
            code="R_TEST",
            message="Test rule fired",
            evidence={"foo": "bar"},
        )
    )

    payload = decision.to_dict()

    assert payload["events"] == [], "legacy events must be an empty list"
    assert len(payload["audit_events"]) > 0, "audit_events must contain entries"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
