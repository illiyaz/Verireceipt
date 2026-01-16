"""
CI enforcement tests for SignalRegistry violations.

These tests ensure that:
1. A signal cannot be emitted without being registered
2. A registered signal that's never emitted triggers a warning
3. Signal domain/version changes are detected
4. Privacy and severity metadata is validated
"""

import pytest
from app.schemas.receipt import SignalRegistry, SignalSpec, SignalV1


class TestRegistryCIEnforcement:
    """CI-level enforcement tests for SignalRegistry."""

    def test_all_registered_signals_have_valid_metadata(self):
        """
        Test that all registered signals have valid metadata.
        
        Validates:
        - name matches dict key
        - domain is non-empty
        - version is "v1"
        - severity in {"weak", "medium", "strong"}
        - privacy in {"safe", "derived"}
        - description is non-empty
        """
        for signal_name, spec in SignalRegistry.SIGNALS.items():
            # Name matches key
            assert spec.name == signal_name, (
                f"Signal key '{signal_name}' doesn't match spec.name '{spec.name}'"
            )
            
            # Domain is non-empty
            assert spec.domain, f"Signal '{signal_name}' has empty domain"
            
            # Version is v1
            assert spec.version == "v1", (
                f"Signal '{signal_name}' has version '{spec.version}', expected 'v1'"
            )
            
            # Severity is valid
            assert spec.severity in {"weak", "medium", "strong"}, (
                f"Signal '{signal_name}' has invalid severity '{spec.severity}'"
            )
            
            # Privacy is valid
            assert spec.privacy in {"safe", "derived"}, (
                f"Signal '{signal_name}' has invalid privacy '{spec.privacy}'"
            )
            
            # Description is non-empty
            assert spec.description, (
                f"Signal '{signal_name}' has empty description"
            )

    def test_signal_domain_prefix_matches_metadata(self):
        """
        Test that signal names have correct domain prefix.
        
        E.g., "addr.structure" should have domain="address"
        """
        domain_prefixes = {
            "address": "addr",
            "amount": "amount",
            "template": "template",
            "merchant": "merchant",
            "date": "date",
            "ocr": "ocr",
            "language": "language",
        }
        
        for signal_name, spec in SignalRegistry.SIGNALS.items():
            expected_prefix = domain_prefixes.get(spec.domain)
            assert expected_prefix, (
                f"Signal '{signal_name}' has unknown domain '{spec.domain}'"
            )
            
            actual_prefix = signal_name.split(".")[0]
            assert actual_prefix == expected_prefix, (
                f"Signal '{signal_name}' has prefix '{actual_prefix}' "
                f"but domain '{spec.domain}' expects '{expected_prefix}'"
            )

    def test_gated_by_conditions_are_valid(self):
        """
        Test that gated_by conditions are known and valid.
        
        Valid gating conditions:
        - doc_profile_confidence
        - ocr_confidence
        - merchant_confidence
        - (empty list for ungated signals)
        """
        valid_gating_conditions = {
            "doc_profile_confidence",
            "ocr_confidence",
            "merchant_confidence",
        }
        
        for signal_name, spec in SignalRegistry.SIGNALS.items():
            for condition in spec.gated_by:
                assert condition in valid_gating_conditions, (
                    f"Signal '{signal_name}' has unknown gating condition '{condition}'"
                )

    def test_severity_distribution_is_balanced(self):
        """
        Test that severity distribution is reasonable.
        
        We expect:
        - Some weak signals (low risk)
        - Some medium signals (moderate risk)
        - Few strong signals (high risk)
        
        This prevents over-alerting or under-alerting.
        """
        severity_counts = {"weak": 0, "medium": 0, "strong": 0}
        
        for spec in SignalRegistry.SIGNALS.values():
            severity_counts[spec.severity] += 1
        
        total = sum(severity_counts.values())
        
        # At least 20% weak signals
        assert severity_counts["weak"] >= total * 0.2, (
            f"Too few weak signals: {severity_counts['weak']}/{total}"
        )
        
        # At least 20% medium signals
        assert severity_counts["medium"] >= total * 0.2, (
            f"Too few medium signals: {severity_counts['medium']}/{total}"
        )
        
        # Strong signals should be rare (<30%)
        assert severity_counts["strong"] <= total * 0.3, (
            f"Too many strong signals: {severity_counts['strong']}/{total}"
        )

    def test_all_signals_are_privacy_safe(self):
        """
        Test that all signals are marked as privacy-safe.
        
        In V1, all signals should be "safe" (no PII).
        "derived" is reserved for future use.
        """
        for signal_name, spec in SignalRegistry.SIGNALS.items():
            assert spec.privacy == "safe", (
                f"Signal '{signal_name}' has privacy='{spec.privacy}', expected 'safe'"
            )

    def test_registry_immutability(self):
        """
        Test that SignalSpec is immutable (frozen).
        
        This prevents runtime modification of signal metadata.
        """
        spec = SignalRegistry.get_spec("addr.structure")
        assert spec is not None
        
        # Try to modify (should fail)
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            spec.name = "addr.modified"

    def test_get_by_domain_returns_correct_signals(self):
        """
        Test that get_by_domain() returns signals for the correct domain.
        """
        address_signals = SignalRegistry.get_by_domain("address")
        assert len(address_signals) == 3
        
        for spec in address_signals:
            assert spec.domain == "address"
            assert spec.name.startswith("addr.")

    def test_unregistered_signal_detection(self):
        """
        Test that unregistered signals are detected.
        
        This simulates the pipeline enforcement.
        """
        # Valid signal
        assert SignalRegistry.is_allowed("addr.structure")
        
        # Invalid signals (typos)
        assert not SignalRegistry.is_allowed("addr.multiAddr")
        assert not SignalRegistry.is_allowed("address.structure")
        assert not SignalRegistry.is_allowed("addr.structure_v2")

    def test_signal_count_matches_expected(self):
        """
        Test that signal count matches expected total.
        
        Update this when adding new signals.
        """
        expected_counts = {
            "address": 3,
            "amount": 3,
            "template": 2,
            "merchant": 2,
            "date": 3,
            "ocr": 3,
            "language": 3,
        }
        
        total_expected = sum(expected_counts.values())
        assert SignalRegistry.count() == total_expected, (
            f"Expected {total_expected} signals but found {SignalRegistry.count()}"
        )
        
        # Check per-domain counts
        for domain, expected_count in expected_counts.items():
            actual_count = len(SignalRegistry.get_by_domain(domain))
            assert actual_count == expected_count, (
                f"Domain '{domain}' has {actual_count} signals, expected {expected_count}"
            )


class TestSignalVersioning:
    """Test signal versioning and migration support."""

    def test_all_signals_are_v1(self):
        """
        Test that all signals are version v1.
        
        When we add v2, this test will need updating.
        """
        for signal_name, spec in SignalRegistry.SIGNALS.items():
            assert spec.version == "v1", (
                f"Signal '{signal_name}' has version '{spec.version}', expected 'v1'"
            )

    def test_version_format_is_valid(self):
        """
        Test that version follows format: v{major}.
        
        Future: v1.1, v2, v2.1, etc.
        """
        import re
        version_pattern = re.compile(r"^v\d+(\.\d+)?$")
        
        for signal_name, spec in SignalRegistry.SIGNALS.items():
            assert version_pattern.match(spec.version), (
                f"Signal '{signal_name}' has invalid version format '{spec.version}'"
            )


class TestSignalDocumentation:
    """Test that signals are properly documented."""

    def test_all_signals_have_descriptions(self):
        """
        Test that all signals have non-empty descriptions.
        """
        for signal_name, spec in SignalRegistry.SIGNALS.items():
            assert spec.description, (
                f"Signal '{signal_name}' has empty description"
            )
            assert len(spec.description) >= 20, (
                f"Signal '{signal_name}' description too short: '{spec.description}'"
            )

    def test_descriptions_are_informative(self):
        """
        Test that descriptions explain what the signal detects.
        
        Good: "Multiple distinct addresses detected in document"
        Bad: "Multi address signal"
        """
        for signal_name, spec in SignalRegistry.SIGNALS.items():
            # Description should not just repeat the signal name
            name_words = set(signal_name.replace(".", " ").replace("_", " ").lower().split())
            desc_words = set(spec.description.lower().split())
            
            # Description should have words beyond just the signal name
            unique_desc_words = desc_words - name_words
            assert len(unique_desc_words) >= 3, (
                f"Signal '{signal_name}' description is not informative enough: '{spec.description}'"
            )
