"""
Test signal contract invariants.

Critical invariants that must hold for telemetry, learned rules, and feature joins.
"""

import pytest
from app.schemas.receipt import SignalV1
from app.signals import (
    signal_addr_structure,
    signal_addr_merchant_consistency,
    signal_addr_multi_address,
    signal_amount_total_mismatch,
    signal_amount_missing,
    signal_amount_semantic_override,
    signal_pdf_producer_suspicious,
    signal_merchant_extraction_weak,
    signal_merchant_confidence_low,
)


# Registry    # Expected signal registry (should match SignalRegistry.SIGNALS)
SIGNAL_REGISTRY = SignalRegistry.get_all_names()


class TestSignalInvariants:
    """Test critical signal contract invariants."""

    def test_signal_key_matches_name(self):
        """
        INVARIANT A: signals[key].name == key
        
        Why it matters:
        - Telemetry aggregation
        - Learned rules
        - Feature joins
        """
        # Test all signal wrappers
        test_cases = [
            ("addr.structure", signal_addr_structure({"address_classification": "STRONG_ADDRESS", "address_score": 7, "address_type": "STANDARD", "address_evidence": []})),
            ("addr.merchant_consistency", signal_addr_merchant_consistency({"status": "CONSISTENT", "score": 0.0, "evidence": {}})),
            ("addr.multi_address", signal_addr_multi_address({"status": "SINGLE", "count": 1, "address_types": [], "evidence": [], "distinctness_basis": []})),
            ("amount.total_mismatch", signal_amount_total_mismatch(100.0, 100.0, True, False, 0.85)),
            ("amount.missing", signal_amount_missing(100.0, True, "INVOICE", 0.85)),
            ("amount.semantic_override", signal_amount_semantic_override(None, 100.0, 100.0)),
            ("template.pdf_producer_suspicious", signal_pdf_producer_suspicious({}, False)),
            ("merchant.extraction_weak", signal_merchant_extraction_weak("ACME", 0.75, 0.85)),
            ("merchant.confidence_low", signal_merchant_confidence_low(0.75)),
        ]
        
        for expected_key, signal in test_cases:
            assert signal.name == expected_key, (
                f"Signal key mismatch: expected '{expected_key}' but got '{signal.name}'"
            )

    def test_gated_signals_are_emitted(self):
        """
        INVARIANT B: GATED signals are emitted (not absent)
        
        GATED ≠ absent
        GATED ≠ NOT_TRIGGERED
        
        Gated signals must be present in the dict with status=GATED.
        """
        # Test that low confidence triggers GATED status
        signal = signal_amount_total_mismatch(
            total_amount=100.0,
            items_sum=95.0,
            has_line_items=True,
            total_mismatch=True,
            doc_profile_confidence=0.3,  # Low confidence
        )
        
        # Signal must exist and have GATED status
        assert signal is not None, "GATED signal must be emitted, not absent"
        assert signal.status == "GATED", "Low confidence should trigger GATED status"
        assert signal.name == "amount.total_mismatch", "GATED signal must have correct name"
        assert signal.gating_reason is not None, "GATED signal must have gating_reason"
        
        # GATED is distinct from NOT_TRIGGERED
        assert signal.status != "NOT_TRIGGERED", "GATED ≠ NOT_TRIGGERED"

    def test_all_signals_registered(self):
        """
        INVARIANT C: Every emitted signal must be in the registry.
        
        This prevents typos and ensures all signals are documented.
        """
        # Get all signals from wrappers
        emitted_signals = [
            signal_addr_structure({"address_classification": "STRONG_ADDRESS", "address_score": 7, "address_type": "STANDARD", "address_evidence": []}).name,
            signal_addr_merchant_consistency({"status": "CONSISTENT", "score": 0.0, "evidence": {}}).name,
            signal_addr_multi_address({"status": "SINGLE", "count": 1, "address_types": [], "evidence": [], "distinctness_basis": []}).name,
            signal_amount_total_mismatch(100.0, 100.0, True, False, 0.85).name,
            signal_amount_missing(100.0, True, "INVOICE", 0.85).name,
            signal_amount_semantic_override(None, 100.0, 100.0).name,
            signal_pdf_producer_suspicious({}, False).name,
            signal_merchant_extraction_weak("ACME", 0.75, 0.85).name,
            signal_merchant_confidence_low(0.75).name,
        ]
        
        for signal_name in emitted_signals:
            assert signal_name in SIGNAL_REGISTRY, (
                f"Signal '{signal_name}' is emitted but not registered in SIGNAL_REGISTRY. "
                f"Add it to the registry to prevent typos and ensure documentation."
            )

    def test_signal_registry_completeness(self):
        """
        Test that the signal registry is complete.
        
        This is a meta-test to ensure we update the registry when adding new signals.
        """
        # Count expected signals by domain
        expected_counts = {
            "addr": 3,      # structure, merchant_consistency, multi_address
            "amount": 3,    # total_mismatch, missing, semantic_override
            "template": 2,  # pdf_producer_suspicious, quality_low
            "merchant": 2,  # extraction_weak, confidence_low
            "date": 3,      # missing, future, gap_suspicious
            "ocr": 3,       # confidence_low, text_sparse, language_mismatch
            "language": 3,  # detection_low_confidence, script_mismatch, mixed_scripts
        }
        
        actual_counts = {}
        for signal_name in SIGNAL_REGISTRY:
            domain = signal_name.split(".")[0]
            actual_counts[domain] = actual_counts.get(domain, 0) + 1
        
        for domain, expected_count in expected_counts.items():
            actual_count = actual_counts.get(domain, 0)
            assert actual_count == expected_count, (
                f"Domain '{domain}' has {actual_count} signals but expected {expected_count}. "
                f"Update SIGNAL_REGISTRY or expected_counts."
            )

    def test_signal_name_format(self):
        """
        Test that all emitted signals are in the central registry.
        """
        from app.schemas.receipt import SignalRegistry
        
        for signal_name in SignalRegistry.get_all_names():
            assert SignalRegistry.is_allowed(signal_name), (
                f"Signal '{signal_name}' in registry but not allowed"
            )
            parts = signal_name.split(".")
            assert len(parts) == 2, (
                f"Signal name '{signal_name}' must follow format 'domain.signal_name'"
            )
            domain, name = parts
            assert domain.isalpha(), f"Domain '{domain}' must be alphabetic"
            assert name.replace("_", "").isalnum(), f"Signal name '{name}' must be alphanumeric with underscores"

    def test_gated_vs_not_triggered_distinction(self):
        """
        Test that GATED and NOT_TRIGGERED are distinct states.
        
        GATED: Signal would trigger but confidence too low
        NOT_TRIGGERED: Signal evaluated and did not trigger
        """
        # GATED: Low confidence prevents evaluation
        gated_signal = signal_amount_total_mismatch(
            total_amount=100.0,
            items_sum=95.0,
            has_line_items=True,
            total_mismatch=True,
            doc_profile_confidence=0.3,
        )
        
        # NOT_TRIGGERED: High confidence, no mismatch
        not_triggered_signal = signal_amount_total_mismatch(
            total_amount=100.0,
            items_sum=100.0,
            has_line_items=True,
            total_mismatch=False,
            doc_profile_confidence=0.85,
        )
        
        assert gated_signal.status == "GATED"
        assert not_triggered_signal.status == "NOT_TRIGGERED"
        assert gated_signal.status != not_triggered_signal.status
        
        # GATED has gating_reason, NOT_TRIGGERED does not
        assert gated_signal.gating_reason is not None
        assert not_triggered_signal.gating_reason is None

    def test_signal_dict_key_invariant_in_pipeline(self):
        """
        Test that the pipeline maintains the key == name invariant.
        
        This simulates what happens in features.py.
        """
        # Simulate signal emission
        signals = {}
        
        # Emit signals with correct keys
        signals["addr.structure"] = signal_addr_structure({
            "address_classification": "STRONG_ADDRESS",
            "address_score": 7,
            "address_type": "STANDARD",
            "address_evidence": []
        })
        
        signals["amount.total_mismatch"] = signal_amount_total_mismatch(
            100.0, 95.0, True, True, 0.85
        )
        
        # Validate invariant
        for key, signal in signals.items():
            assert signal.name == key, (
                f"Pipeline invariant violated: dict key='{key}' but signal.name='{signal.name}'"
            )
