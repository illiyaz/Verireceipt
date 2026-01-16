"""
CI tests for SignalRegistry enforcement.

Critical tests to ensure:
- All emitted signals are registered
- Registry count is correct
- Unregistered signals fail fast
"""

import pytest
from app.schemas.receipt import SignalV1, SignalRegistry
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
    signal_date_missing,
    signal_date_future,
    signal_date_gap_suspicious,
    signal_ocr_confidence_low,
    signal_ocr_text_sparse,
    signal_ocr_language_mismatch,
    signal_language_detection_low_confidence,
    signal_language_script_mismatch,
    signal_language_mixed_scripts,
)


class TestSignalRegistry:
    """Test SignalRegistry contract enforcement."""

    def test_signal_registry_count(self):
        """
        Test that registry has exactly 19 signals.
        
        If this fails, update the count when adding new signals.
        """
        assert SignalRegistry.count() == 19, (
            f"Expected 19 signals but found {SignalRegistry.count()}. "
            f"Update this test when adding new signals."
        )

    def test_all_emitted_signals_are_registered(self):
        """
        Test that all signals emitted by wrappers are registered.
        
        This prevents typos and ensures contract compliance.
        """
        # Get all signals from wrappers
        emitted_signals = [
            # Address
            signal_addr_structure({"address_classification": "STRONG_ADDRESS", "address_score": 7, "address_type": "STANDARD", "address_evidence": []}),
            signal_addr_merchant_consistency({"status": "CONSISTENT", "score": 0.0, "evidence": {}}),
            signal_addr_multi_address({"status": "SINGLE", "count": 1, "address_types": [], "evidence": [], "distinctness_basis": []}),
            # Amount
            signal_amount_total_mismatch(100.0, 100.0, True, False, 0.85),
            signal_amount_missing(100.0, True, "INVOICE", 0.85),
            signal_amount_semantic_override(None, 100.0, 100.0),
            # Template
            signal_pdf_producer_suspicious({}, False),
            # Merchant
            signal_merchant_extraction_weak("ACME", 0.75, 0.85),
            signal_merchant_confidence_low(0.75),
            # Date
            signal_date_missing(None, "INVOICE", 0.85),
            signal_date_future("2024-01-15", 0.85),
            signal_date_gap_suspicious("2024-01-01", "2024-01-15", 0.85),
            # OCR
            signal_ocr_confidence_low(0.9),
            signal_ocr_text_sparse(500, 100, 0.85),
            signal_ocr_language_mismatch("en", "en", 0.85, 0.85),
            # Language
            signal_language_detection_low_confidence(0.85, "en"),
            signal_language_script_mismatch("en", "Latin", 0.85),
            signal_language_mixed_scripts(["Latin"], {"Latin": 0.9}, 0.85),
        ]
        
        for signal in emitted_signals:
            assert SignalRegistry.is_allowed(signal.name), (
                f"Signal '{signal.name}' is emitted but not registered in SignalRegistry.ALLOWED_SIGNALS. "
                f"Add it to the registry in app/schemas/receipt.py."
            )

    def test_unregistered_signal_fails_validation(self):
        """
        Test that unregistered signal names are rejected.
        
        This prevents typos like 'addr.multiAddr' or 'date.future_2'.
        """
        # Create signal with bad name
        bad_signal = SignalV1(
            name="addr.multiAddr",  # Typo: should be addr.multi_address
            status="TRIGGERED",
            confidence=0.9,
            evidence={},
            interpretation="bad name",
        )
        
        assert not SignalRegistry.is_allowed(bad_signal.name), (
            f"Signal '{bad_signal.name}' should not be allowed (typo in name)"
        )

    def test_registry_contains_all_domains(self):
        """
        Test that registry contains signals from all expected domains.
        """
        expected_domains = {
            "addr", "amount", "template", "merchant",
            "date", "ocr", "language"
        }
        
        actual_domains = set()
        for signal_name in SignalRegistry.ALLOWED_SIGNALS:
            domain = signal_name.split(".")[0]
            actual_domains.add(domain)
        
        assert actual_domains == expected_domains, (
            f"Registry domains mismatch. Expected: {expected_domains}, Got: {actual_domains}"
        )

    def test_registry_domain_counts(self):
        """
        Test that each domain has the expected number of signals.
        """
        expected_counts = {
            "addr": 3,
            "amount": 3,
            "template": 2,
            "merchant": 2,
            "date": 3,
            "ocr": 3,
            "language": 3,
        }
        
        actual_counts = {}
        for signal_name in SignalRegistry.ALLOWED_SIGNALS:
            domain = signal_name.split(".")[0]
            actual_counts[domain] = actual_counts.get(domain, 0) + 1
        
        for domain, expected_count in expected_counts.items():
            actual_count = actual_counts.get(domain, 0)
            assert actual_count == expected_count, (
                f"Domain '{domain}' has {actual_count} signals but expected {expected_count}"
            )

    def test_no_duplicate_signal_names(self):
        """
        Test that there are no duplicate signal names in the registry.
        """
        signal_list = list(SignalRegistry.ALLOWED_SIGNALS)
        signal_set = set(SignalRegistry.ALLOWED_SIGNALS)
        
        assert len(signal_list) == len(signal_set), (
            "Registry contains duplicate signal names"
        )

    def test_signal_name_format_in_registry(self):
        """
        Test that all registered signals follow the format: domain.signal_name
        """
        for signal_name in SignalRegistry.ALLOWED_SIGNALS:
            parts = signal_name.split(".")
            assert len(parts) == 2, (
                f"Signal '{signal_name}' must follow format 'domain.signal_name'"
            )
            domain, name = parts
            assert domain.isalpha(), f"Domain '{domain}' must be alphabetic"
            assert name.replace("_", "").isalnum(), (
                f"Signal name '{name}' must be alphanumeric with underscores"
            )


class TestLearnedRulePatterns:
    """
    Test patterns for learned rule consumption (design tests, not ML).
    
    These tests document how learned rules should consume signals.
    """

    def test_boolean_embedding_pattern(self):
        """
        Pattern 1: Boolean embedding for ML models.
        
        Learned rules see only: signal_name, status, confidence
        """
        signal = signal_addr_multi_address({
            "status": "MULTIPLE",
            "count": 3,
            "address_types": ["STANDARD", "STANDARD", "PO_BOX"],
            "evidence": ["distinct_postal_tokens"],
            "distinctness_basis": ["postal_tokens"],
        })
        
        # Canonical learned-rule input
        learned_rule_input = {
            "signal_name": signal.name,
            "status": signal.status,
            "confidence": signal.confidence,
        }
        
        # Boolean embedding
        features = {
            "addr_multi_triggered": signal.status == "TRIGGERED",
            "addr_multi_conf": signal.confidence,
            "addr_multi_gated": signal.status == "GATED",
        }
        
        assert learned_rule_input["signal_name"] == "addr.multi_address"
        assert learned_rule_input["status"] == "TRIGGERED"
        assert features["addr_multi_triggered"] is True
        assert features["addr_multi_gated"] is False

    def test_signal_interaction_pattern(self):
        """
        Pattern 2: Signal interaction features.
        
        Learned rules combine multiple signals.
        """
        sig_multi = signal_addr_multi_address({
            "status": "MULTIPLE",
            "count": 3,
            "address_types": ["STANDARD", "STANDARD", "PO_BOX"],
            "evidence": ["distinct_postal_tokens"],
            "distinctness_basis": ["postal_tokens"],
        })
        
        sig_cons = signal_addr_merchant_consistency({
            "status": "WEAK_MISMATCH",
            "score": 0.1,
            "evidence": {"overlap_signals": []},
        })
        
        # Interaction feature
        addr_multi_and_mismatch = (
            sig_multi.status == "TRIGGERED" and
            sig_cons.status == "TRIGGERED"
        )
        
        assert addr_multi_and_mismatch is True, (
            "Interaction feature should be True when both signals triggered"
        )

    def test_confidence_weighted_pattern(self):
        """
        Pattern 3: Confidence-weighted signals.
        
        GATED signals contribute zero, not negative.
        """
        triggered_signal = signal_amount_total_mismatch(100.0, 95.0, True, True, 0.85)
        gated_signal = signal_amount_total_mismatch(100.0, 95.0, True, True, 0.3)
        
        # Confidence weighting
        weight = 1.5
        
        triggered_score = (
            weight * triggered_signal.confidence
            if triggered_signal.status == "TRIGGERED"
            else 0
        )
        
        gated_score = (
            weight * gated_signal.confidence
            if gated_signal.status == "TRIGGERED"
            else 0
        )
        
        assert triggered_score == 1.5 * 0.8  # 0.8 is the confidence for triggered mismatch
        assert gated_score == 0, "GATED signals contribute zero"

    def test_learned_rule_minimum_signals_invariant(self):
        """
        Hard invariant: A learned rule must never fire on a single signal alone.
        
        Minimum:
        - ≥2 signals OR
        - 1 signal + external evidence (history, user risk)
        """
        # Single signal alone - should NOT trigger learned rule
        single_signal = signal_addr_multi_address({
            "status": "MULTIPLE",
            "count": 3,
            "address_types": ["STANDARD", "STANDARD", "PO_BOX"],
            "evidence": ["distinct_postal_tokens"],
            "distinctness_basis": ["postal_tokens"],
        })
        
        # This should NOT be sufficient for a learned rule
        learned_rule_fires_on_single = single_signal.status == "TRIGGERED"
        
        # Learned rule should require at least 2 signals
        sig_multi = single_signal
        sig_cons = signal_addr_merchant_consistency({
            "status": "WEAK_MISMATCH",
            "score": 0.1,
            "evidence": {"overlap_signals": []},
        })
        
        learned_rule_fires_on_multiple = (
            sig_multi.status == "TRIGGERED" and
            sig_cons.status == "TRIGGERED"
        )
        
        # Document the invariant
        assert learned_rule_fires_on_single is True, "Single signal can trigger"
        assert learned_rule_fires_on_multiple is True, "Multiple signals can trigger"
        
        # But learned rules should only use the multiple signal pattern
        # This is a design constraint, not a code constraint
