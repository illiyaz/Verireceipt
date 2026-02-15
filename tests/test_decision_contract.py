"""
Decision Contract Tests

These tests enforce invariants that must hold for ReceiptDecision objects:
1. Lists are always lists (never None)
2. finalize_defaults() is idempotent
3. to_dict() produces valid JSON-serializable output
4. Nested objects are properly finalized

These tests prevent regressions in the decision schema contract.
"""

import pytest
from app.schemas.receipt import ReceiptDecision, AuditEvent, LearnedRuleAudit


class TestDecisionFinalizationInvariants:
    """Test that finalize_defaults() enforces all required invariants."""

    def test_decision_finalize_invariants_from_none(self):
        """Test that finalize_defaults() converts None lists to empty lists."""
        # Create decision with None values (simulating partial construction)
        d = ReceiptDecision(
            label="real",
            score=0.1,
            reasons=None,
            minor_notes=None,
            events=None,
            audit_events=None,
            learned_rule_audits=None,
            corroboration_flags=None,
        )
        
        # Before finalize, fields may be None
        assert d.reasons is None
        assert d.minor_notes is None
        
        # After finalize, all lists must be lists
        d.finalize_defaults()
        
        assert isinstance(d.events, list)
        assert isinstance(d.audit_events, list)
        assert isinstance(d.learned_rule_audits, list)
        assert isinstance(d.reasons, list)
        assert isinstance(d.minor_notes, list)
        assert isinstance(d.corroboration_flags, list)
        
        # Empty lists, not None
        assert d.events == []
        assert d.audit_events == []
        assert d.learned_rule_audits == []
        assert d.reasons == []
        assert d.minor_notes == []
        assert d.corroboration_flags == []

    def test_decision_finalize_preserves_existing_values(self):
        """Test that finalize_defaults() preserves existing non-None values."""
        d = ReceiptDecision(
            label="fake",
            score=0.8,
            reasons=["Test reason"],
            minor_notes=["Test note"],
        )
        
        d.finalize_defaults()
        
        # Existing values preserved
        assert d.reasons == ["Test reason"]
        assert d.minor_notes == ["Test note"]
        
        # Other lists initialized
        assert isinstance(d.events, list)
        assert isinstance(d.audit_events, list)

    def test_decision_finalize_is_idempotent(self):
        """Test that calling finalize_defaults() multiple times is safe."""
        d = ReceiptDecision(label="suspicious", score=0.5, reasons=None)
        
        # Call multiple times
        d.finalize_defaults()
        first_id = d.decision_id
        first_ts = d.created_at
        
        d.finalize_defaults()
        second_id = d.decision_id
        second_ts = d.created_at
        
        d.finalize_defaults()
        third_id = d.decision_id
        third_ts = d.created_at
        
        # IDs and timestamps should not change
        assert first_id == second_id == third_id
        assert first_ts == second_ts == third_ts
        
        # Lists should remain lists
        assert isinstance(d.reasons, list)
        assert isinstance(d.events, list)

    def test_decision_finalize_creates_ids_and_timestamps(self):
        """Test that finalize_defaults() creates decision_id and created_at."""
        d = ReceiptDecision(label="real", score=0.2, reasons=[])
        
        # Before finalize
        assert not d.decision_id
        assert not d.created_at
        
        d.finalize_defaults()
        
        # After finalize
        assert d.decision_id
        assert d.created_at
        assert len(d.decision_id) > 0
        assert len(d.created_at) > 0

    def test_decision_finalize_normalizes_optional_dicts(self):
        """Test that finalize_defaults() normalizes optional dict fields to None."""
        d = ReceiptDecision(label="real", score=0.1, reasons=[])
        
        d.finalize_defaults()
        
        # Optional dicts should be None (not missing)
        assert d.debug is None
        assert d.missing_field_gate is None
        assert d.corroboration_signals is None
        assert d.layoutlm_extracted is None
        assert d.input_fingerprint is None

    def test_decision_finalize_nested_audit_events(self):
        """Test that finalize_defaults() finalizes nested audit events."""
        # Create audit event without finalization
        event = AuditEvent(
            source="test",
            type="test_type",
            message="Test message",
        )
        
        d = ReceiptDecision(label="real", score=0.1, reasons=[])
        d.audit_events = [event]
        
        # Event not finalized yet
        assert not event.event_id
        assert not event.ts
        
        # Finalize decision (should finalize nested events)
        d.finalize_defaults()
        
        # Event should now be finalized
        assert event.event_id
        assert event.ts


class TestDecisionToDictContract:
    """Test that to_dict() produces valid, consistent output."""

    def test_to_dict_produces_serializable_output(self):
        """Test that to_dict() output is JSON-serializable."""
        import json
        
        d = ReceiptDecision(
            label="fake",
            score=0.9,
            reasons=["Reason 1", "Reason 2"],
            minor_notes=["Note 1"],
        )
        
        d_dict = d.to_dict()
        
        # Should be JSON-serializable
        json_str = json.dumps(d_dict)
        assert isinstance(json_str, str)
        
        # Should round-trip
        parsed = json.loads(json_str)
        assert parsed["label"] == "fake"
        assert parsed["score"] == 0.9

    def test_to_dict_always_has_lists_as_lists(self):
        """Test that to_dict() always returns lists as lists (never None)."""
        d = ReceiptDecision(label="real", score=0.1, reasons=None)
        
        d_dict = d.to_dict()
        
        # All list fields must be lists in output
        assert isinstance(d_dict["events"], list)
        assert isinstance(d_dict["audit_events"], list)
        assert isinstance(d_dict["learned_rule_audits"], list)
        assert isinstance(d_dict["reasons"], list)
        assert isinstance(d_dict["minor_notes"], list)
        assert isinstance(d_dict["corroboration_flags"], list)

    def test_to_dict_serializes_nested_dataclasses(self):
        """Test that to_dict() properly serializes nested AuditEvent objects."""
        event = AuditEvent(
            source="test_engine",
            type="test_type",
            message="Test message",
            evidence={"key": "value"},
        )
        
        d = ReceiptDecision(label="suspicious", score=0.6, reasons=[])
        d.add_audit_event(event)
        
        d_dict = d.to_dict()
        
        # Audit events should be serialized to dicts
        assert isinstance(d_dict["audit_events"], list)
        assert len(d_dict["audit_events"]) == 1
        assert isinstance(d_dict["audit_events"][0], dict)
        assert d_dict["audit_events"][0]["source"] == "test_engine"
        assert d_dict["audit_events"][0]["message"] == "Test message"

    def test_to_dict_calls_finalize_defaults(self):
        """Test that to_dict() calls finalize_defaults() automatically."""
        d = ReceiptDecision(label="real", score=0.1, reasons=[])
        
        # Don't call finalize manually
        assert not d.decision_id
        
        # to_dict() should call it
        d_dict = d.to_dict()
        
        # Decision should now be finalized
        assert d.decision_id
        assert d_dict["decision_id"]


class TestDecisionContractRegressions:
    """Test specific regression scenarios that have caused bugs."""

    def test_safe_iteration_over_events(self):
        """Test that consumers can safely iterate over events without None checks."""
        d = ReceiptDecision(label="real", score=0.1, reasons=[], events=None)
        d.finalize_defaults()
        
        # Should be safe to iterate without checking for None
        count = 0
        for e in d.events:
            count += 1
        
        assert count == 0  # Empty list, not None

    def test_safe_iteration_over_audit_events(self):
        """Test that consumers can safely iterate over audit_events without None checks."""
        d = ReceiptDecision(label="real", score=0.1, reasons=[])
        d.finalize_defaults()
        
        # Should be safe to iterate
        count = 0
        for e in d.audit_events:
            count += 1
        
        assert count == 0

    def test_safe_list_append_after_finalize(self):
        """Test that lists can be safely appended to after finalization."""
        d = ReceiptDecision(label="real", score=0.1, reasons=None)
        d.finalize_defaults()
        
        # Should be safe to append
        d.reasons.append("New reason")
        assert len(d.reasons) == 1
        assert d.reasons[0] == "New reason"

    def test_streaming_partial_decision(self):
        """Test that partial decisions (streaming use case) can be finalized safely."""
        # Simulate streaming scenario where decision is built incrementally
        d = ReceiptDecision(label="suspicious", score=0.5, reasons=["Initial reason"])
        
        # Finalize (should not break)
        d.finalize_defaults()
        
        # Add more data after finalization
        d.reasons.append("Additional reason")
        
        # Should work fine
        assert len(d.reasons) == 2
        
        # to_dict should work
        d_dict = d.to_dict()
        assert len(d_dict["reasons"]) == 2


class TestBehavioralContracts:
    """Test end-to-end behavioral expectations for specific document scenarios."""

    def test_low_confidence_logistics_doc_with_date_gap(self):
        """
        Contract: Low-confidence logistics doc with moderate date gap should not be marked fake.
        
        Scenario:
        - Document type: UTILITY/TRANSACTIONAL (low confidence 0.2)
        - Merchant: Structural label rejected ("Date of Export")
        - Date gap: 399 days (moderate, < 540)
        - Expected: R16 downgraded to WARNING, missing-field penalties gated OFF
        - Result: Should be "real" or "suspicious" (NOT "fake")
        """
        from app.pipelines.rules import _score_and_explain
        from app.schemas.receipt import ReceiptFeatures
        
        # Simulate low-confidence logistics document
        features = ReceiptFeatures(
            file_features={
                "file_size_bytes": 50000,
                "source_type": "pdf",
            },
            text_features={
                "receipt_date": "2023-09-05",
                "has_date": True,
                "doc_profile_confidence": 0.2,  # Low confidence
                "doc_subtype_guess": "UTILITY",
                "merchant_candidate": "Date of Export",  # Structural label (should be rejected)
                "has_any_amount": True,
                "total_line_present": False,
            },
            layout_features={},
            forensic_features={
                "creation_date": "D:20241008184241+05'30'",
            },
        )
        
        # Run scoring
        decision = _score_and_explain(features, apply_learned=False)
        
        # Contract assertions
        assert decision.label in ["real", "suspicious"], \
            f"Low-confidence doc with moderate gap should not be 'fake', got: {decision.label}"
        
        # Helper to get rule_id from event (dict or dataclass)
        def _rid(e):
            return e.get("rule_id") if isinstance(e, dict) else getattr(e, "rule_id", "")
        def _sev(e):
            return e.get("severity") if isinstance(e, dict) else getattr(e, "severity", "")
        def _wt(e):
            return e.get("weight") if isinstance(e, dict) else getattr(e, "weight", 0)
        def _msg(e):
            return e.get("message", "") if isinstance(e, dict) else getattr(e, "message", "")
        def _ev(e):
            return e.get("evidence", {}) if isinstance(e, dict) else getattr(e, "evidence", {})

        # Verify R16 was downgraded
        r16_events = [e for e in decision.events if _rid(e) == "R16_SUSPICIOUS_DATE_GAP"]
        if r16_events:
            r16 = r16_events[0]
            assert _sev(r16) == "WARNING", "R16 should be downgraded to WARNING"
            assert _wt(r16) == 0.10, "R16 weight should be 0.10"
            assert _ev(r16).get("severity_downgraded") is True
        
        # Verify missing-field gate was OFF
        gate_events = [e for e in decision.events if _rid(e) == "GATE_MISSING_FIELDS"]
        if gate_events:
            gate = gate_events[0]
            assert "DISABLED" in _msg(gate) or _ev(gate).get("missing_fields_enabled") is False, \
                "Missing-field penalties should be gated OFF"
        
        # Verify merchant implausible was gated
        merchant_events = [e for e in decision.events if "MERCHANT_IMPLAUSIBLE" in _rid(e)]
        if merchant_events:
            # Should be GATED version (INFO only)
            assert any("GATED" in _rid(e) for e in merchant_events), \
                "Merchant implausible should be gated when missing_fields_enabled is OFF"

    def test_high_confidence_receipt_with_large_date_gap(self):
        """
        Contract: High-confidence receipt with large date gap should be marked suspicious/fake.
        
        Scenario:
        - Document type: POS_RESTAURANT (high confidence 0.8)
        - Date gap: 600 days (extreme, > 540)
        - Expected: R16 remains CRITICAL, full penalties applied
        - Result: Should be "suspicious" or "fake"
        """
        from app.pipelines.rules import _score_and_explain
        from app.schemas.receipt import ReceiptFeatures
        from datetime import datetime, timedelta
        
        # High-confidence receipt with extreme date gap
        receipt_date = "2023-01-01"
        creation_datetime = datetime(2023, 1, 1) + timedelta(days=600)
        creation_date = creation_datetime.strftime("D:%Y%m%d120000+00'00'")
        
        features = ReceiptFeatures(
            file_features={
                "file_size_bytes": 50000,
                "source_type": "pdf",
                "creation_date": creation_date,
            },
            text_features={
                "receipt_date": receipt_date,
                "has_date": True,
                "doc_profile_confidence": 0.8,  # High confidence
                "doc_subtype_guess": "POS_RESTAURANT",
                "merchant_candidate": "Restaurant Name",
                "has_any_amount": True,
                "total_line_present": True,
                "total_amount": 45.00,
                "geo_country_guess": "US",
                "geo_confidence": 0.6,
                "lang_guess": "en",
                "lang_confidence": 0.9,
            },
            layout_features={},
            forensic_features={},
        )
        
        # Run scoring
        decision = _score_and_explain(features, apply_learned=False)
        
        # Contract assertions
        assert decision.label in ["suspicious", "fake"], \
            f"High-confidence receipt with extreme gap should be flagged, got: {decision.label}"
        
        # Helper to get rule_id from event (dict or dataclass)
        def _rid(e):
            return e.get("rule_id") if isinstance(e, dict) else getattr(e, "rule_id", "")
        def _sev(e):
            return e.get("severity") if isinstance(e, dict) else getattr(e, "severity", "")
        def _wt(e):
            return e.get("weight") if isinstance(e, dict) else getattr(e, "weight", 0)

        # Verify R16 was NOT downgraded
        r16_events = [e for e in decision.events if _rid(e) == "R16_SUSPICIOUS_DATE_GAP"]
        assert len(r16_events) > 0, "R16 should be triggered"
        
        r16 = r16_events[0]
        assert _sev(r16) == "CRITICAL", "R16 should remain CRITICAL for extreme gap"
        # raw_weight is the base weight before confidence scaling
        r16_raw = r16.get("raw_weight") if isinstance(r16, dict) else getattr(r16, "raw_weight", 0)
        assert r16_raw == 0.35, f"R16 raw_weight should be 0.35, got {r16_raw}"
        r16_ev = r16.get("evidence", {}) if isinstance(r16, dict) else getattr(r16, "evidence", {})
        assert r16_ev.get("severity_downgraded") is False, "Should NOT be downgraded"
        
        # Score should reflect significant fraud signals
        assert decision.score > 0.2, f"Score should reflect fraud signals, got: {decision.score}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
