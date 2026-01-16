"""
Unit tests for unified signal emission (V1).

Tests that all signals are properly emitted with correct schema.
"""

import pytest
from app.schemas.receipt import SignalV1
from app.signals import (
    signal_addr_structure,
    signal_addr_merchant_consistency,
    signal_addr_multi_address,
    signal_amount_total_mismatch,
    signal_amount_missing,
    signal_pdf_producer_suspicious,
    signal_merchant_extraction_weak,
    signal_merchant_confidence_low,
)


class TestSignalEmission:
    """Test unified signal emission."""

    def test_signal_v1_schema(self):
        """Test SignalV1 schema validation."""
        signal = SignalV1(
            name="test.signal",
            status="TRIGGERED",
            confidence=0.85,
            evidence={"key": "value"},
            interpretation="Test signal",
        )
        
        assert signal.name == "test.signal"
        assert signal.status == "TRIGGERED"
        assert signal.confidence == 0.85
        assert signal.evidence == {"key": "value"}
        assert signal.interpretation == "Test signal"
        assert signal.gating_reason is None

    def test_address_structure_signal(self):
        """Test addr.structure signal emission."""
        address_profile = {
            "address_classification": "STRONG_ADDRESS",
            "address_score": 7,
            "address_type": "STANDARD",
            "address_evidence": ["street_indicator", "postal_token"],
        }
        
        signal = signal_addr_structure(address_profile)
        
        assert signal.name == "addr.structure"
        assert signal.status == "TRIGGERED"
        assert signal.confidence == 0.9
        assert "classification" in signal.evidence
        assert signal.interpretation is not None

    def test_address_merchant_consistency_signal(self):
        """Test addr.merchant_consistency signal emission."""
        consistency = {
            "status": "WEAK_MISMATCH",
            "score": 0.1,
            "evidence": {"overlap_signals": []},
        }
        
        signal = signal_addr_merchant_consistency(consistency)
        
        assert signal.name == "addr.merchant_consistency"
        assert signal.status == "TRIGGERED"
        assert signal.confidence > 0.0
        assert "consistency_status" in signal.evidence

    def test_address_multi_address_signal(self):
        """Test addr.multi_address signal emission."""
        multi_address = {
            "status": "MULTIPLE",
            "count": 3,
            "address_types": ["STANDARD", "STANDARD", "PO_BOX"],
            "evidence": ["distinct_postal_tokens"],
            "distinctness_basis": ["postal_tokens"],
        }
        
        signal = signal_addr_multi_address(multi_address)
        
        assert signal.name == "addr.multi_address"
        assert signal.status == "TRIGGERED"
        assert signal.confidence >= 0.6
        assert signal.evidence["count"] == 3

    def test_amount_total_mismatch_signal(self):
        """Test amount.total_mismatch signal emission."""
        signal = signal_amount_total_mismatch(
            total_amount=100.0,
            items_sum=95.0,
            has_line_items=True,
            total_mismatch=True,
            doc_profile_confidence=0.85,
        )
        
        assert signal.name == "amount.total_mismatch"
        assert signal.status == "TRIGGERED"
        assert signal.confidence == 0.8
        assert "mismatch_amount" in signal.evidence

    def test_amount_missing_signal(self):
        """Test amount.missing signal emission."""
        signal = signal_amount_missing(
            total_amount=None,
            has_currency=True,
            doc_subtype="INVOICE",
            doc_profile_confidence=0.85,
        )
        
        assert signal.name == "amount.missing"
        assert signal.status == "TRIGGERED"
        assert signal.confidence == 0.7

    def test_pdf_producer_suspicious_signal(self):
        """Test template.pdf_producer_suspicious signal emission."""
        pdf_metadata = {
            "Producer": "iLovePDF",
            "Creator": "Microsoft Word",
        }
        
        signal = signal_pdf_producer_suspicious(pdf_metadata, suspicious_producer=True)
        
        assert signal.name == "template.pdf_producer_suspicious"
        assert signal.status == "TRIGGERED"
        assert signal.confidence == 0.6
        assert "producer_flagged" in signal.evidence

    def test_merchant_extraction_weak_signal(self):
        """Test merchant.extraction_weak signal emission."""
        signal = signal_merchant_extraction_weak(
            merchant_candidate="ACME Corp",
            merchant_confidence=0.45,
            doc_profile_confidence=0.85,
        )
        
        assert signal.name == "merchant.extraction_weak"
        assert signal.status == "TRIGGERED"
        assert signal.confidence == 0.45

    def test_merchant_confidence_low_signal(self):
        """Test merchant.confidence_low signal emission."""
        signal = signal_merchant_confidence_low(merchant_confidence=0.55)
        
        assert signal.name == "merchant.confidence_low"
        assert signal.status == "TRIGGERED"
        assert signal.confidence > 0.0
        assert signal.evidence["below_threshold"] is True

    def test_signal_gating(self):
        """Test signal gating behavior."""
        # Low doc confidence should gate signals
        signal = signal_amount_total_mismatch(
            total_amount=100.0,
            items_sum=95.0,
            has_line_items=True,
            total_mismatch=True,
            doc_profile_confidence=0.3,  # Low confidence
        )
        
        assert signal.status == "GATED"
        assert signal.confidence == 0.0
        assert signal.gating_reason is not None

    def test_signal_not_triggered(self):
        """Test NOT_TRIGGERED status."""
        signal = signal_amount_total_mismatch(
            total_amount=100.0,
            items_sum=100.0,  # Match
            has_line_items=True,
            total_mismatch=False,
            doc_profile_confidence=0.85,
        )
        
        assert signal.status == "NOT_TRIGGERED"
        assert signal.confidence == 0.9

    def test_all_signals_have_name(self):
        """Test that all signals have name field."""
        # Address signals
        addr_profile = {"address_classification": "STRONG_ADDRESS", "address_score": 7, "address_type": "STANDARD", "address_evidence": []}
        assert signal_addr_structure(addr_profile).name == "addr.structure"
        
        consistency = {"status": "CONSISTENT", "score": 0.0, "evidence": {}}
        assert signal_addr_merchant_consistency(consistency).name == "addr.merchant_consistency"
        
        multi = {"status": "SINGLE", "count": 1, "address_types": [], "evidence": [], "distinctness_basis": []}
        assert signal_addr_multi_address(multi).name == "addr.multi_address"
        
        # Amount signals
        assert signal_amount_total_mismatch(100.0, 100.0, True, False, 0.85).name == "amount.total_mismatch"
        assert signal_amount_missing(100.0, True, "INVOICE", 0.85).name == "amount.missing"
        
        # Template signals
        assert signal_pdf_producer_suspicious({}, False).name == "template.pdf_producer_suspicious"
        
        # Merchant signals
        assert signal_merchant_extraction_weak("ACME", 0.75, 0.85).name == "merchant.extraction_weak"
        assert signal_merchant_confidence_low(0.75).name == "merchant.confidence_low"

    def test_signal_confidence_range(self):
        """Test that all signals have confidence in [0.0, 1.0]."""
        signals_to_test = [
            signal_addr_structure({"address_classification": "STRONG_ADDRESS", "address_score": 7, "address_type": "STANDARD", "address_evidence": []}),
            signal_amount_total_mismatch(100.0, 100.0, True, False, 0.85),
            signal_merchant_confidence_low(0.75),
        ]
        
        for signal in signals_to_test:
            assert 0.0 <= signal.confidence <= 1.0, f"Signal {signal.name} has invalid confidence: {signal.confidence}"

    def test_signal_evidence_no_pii(self):
        """Test that signal evidence doesn't contain PII."""
        # Address signal should not contain raw address text
        addr_profile = {
            "address_classification": "STRONG_ADDRESS",
            "address_score": 7,
            "address_type": "STANDARD",
            "address_evidence": ["street_indicator"],
            "address_raw_text": "123 Main St, Springfield, IL 62701",  # PII
        }
        
        signal = signal_addr_structure(addr_profile)
        
        # Evidence should not contain raw_text
        assert "address_raw_text" not in signal.evidence
        assert "raw_text" not in str(signal.evidence).lower()
        
        # But should contain classification info
        assert "classification" in signal.evidence
        assert "score" in signal.evidence
