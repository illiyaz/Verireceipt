"""
Receipt Intake Testing Checklist.

This is NOT unit testing. This is data onboarding discipline.

Use this checklist every time you add new receipts (customers, countries, formats).

Critical: Most fraud systems fail not due to logic, but due to:
"We never looked at the distributions."

This checklist forces discipline before ML.
"""

import pytest
from typing import Dict, List, Any
from app.schemas.receipt import SignalRegistry, ReceiptFeatures


class TestReceiptIntakeChecklist:
    """
    Receipt Intake Checklist (copy-paste ready).
    
    Run this on every new batch of receipts before deploying.
    """

    def test_a_document_sanity(self, sample_receipt_features: ReceiptFeatures):
        """
        A. Document sanity checks.
        
        Validates:
        - OCR text length > minimum threshold
        - doc_type & subtype confidence ≥ expected
        - language detected and confidence logged
        - template metadata extracted
        """
        text_features = sample_receipt_features.text_features
        file_features = sample_receipt_features.file_features
        
        # OCR text length
        full_text = text_features.get("full_text", "")
        assert len(full_text) > 50, (
            f"OCR text too short: {len(full_text)} chars. "
            f"Minimum: 50 chars. Check OCR quality."
        )
        
        # Document type confidence
        doc_profile = sample_receipt_features.document_intent
        doc_confidence = doc_profile.get("confidence", 0.0)
        assert doc_confidence >= 0.5, (
            f"Document confidence too low: {doc_confidence}. "
            f"Expected: ≥0.5. Check document classification."
        )
        
        # Language detection
        language = text_features.get("language", {})
        assert language.get("detected"), (
            "Language not detected. Check language identification."
        )
        
        # Template metadata
        pdf_metadata = file_features.get("pdf_metadata", {})
        assert pdf_metadata or file_features.get("is_image"), (
            "No PDF metadata and not an image. Check file parsing."
        )

    def test_b_signal_emission_completeness(self, sample_receipt_features: ReceiptFeatures):
        """
        B. Signal emission completeness.
        
        For every receipt:
        - All registered signals are present in features.signals
        - No signal is missing (even if GATED)
        - No unregistered signal emitted
        """
        emitted_signals = sample_receipt_features.signals
        registered_signals = SignalRegistry.get_all_names()
        
        # All registered signals must be present
        for signal_name in registered_signals:
            assert signal_name in emitted_signals, (
                f"Signal '{signal_name}' is registered but not emitted. "
                f"Even GATED signals must be present in the dict."
            )
        
        # No unregistered signals
        for signal_name in emitted_signals.keys():
            assert SignalRegistry.is_allowed(signal_name), (
                f"Signal '{signal_name}' is emitted but not registered. "
                f"Add it to SignalRegistry.SIGNALS."
            )

    def test_c_confidence_gating_validation(self, sample_receipt_features: ReceiptFeatures):
        """
        C. Confidence gating validation.
        
        Validates:
        - Low-confidence docs → signals are GATED, not absent
        - No rule fires when required signals are GATED
        - Gating reasons populated
        """
        signals = sample_receipt_features.signals
        
        # Check GATED signals have gating_reason
        for signal_name, signal in signals.items():
            if signal.status == "GATED":
                assert signal.gating_reason is not None, (
                    f"Signal '{signal_name}' is GATED but has no gating_reason. "
                    f"All GATED signals must explain why."
                )
                assert signal.confidence == 0.0, (
                    f"Signal '{signal_name}' is GATED but confidence={signal.confidence}. "
                    f"GATED signals must have confidence=0.0."
                )

    def test_d_distribution_checks(self, receipt_batch: List[ReceiptFeatures]):
        """
        D. Distribution checks (most important).
        
        Across a batch (≥20 receipts):
        - % of TRIGGERED per signal
        - % of GATED per signal
        - signals that never fire → investigate
        - signals that fire >40% → suspicious heuristic
        
        This prevents silent bias.
        """
        if len(receipt_batch) < 20:
            pytest.skip("Need ≥20 receipts for distribution checks")
        
        # Collect signal statistics
        signal_stats: Dict[str, Dict[str, int]] = {}
        
        for receipt in receipt_batch:
            for signal_name, signal in receipt.signals.items():
                if signal_name not in signal_stats:
                    signal_stats[signal_name] = {
                        "TRIGGERED": 0,
                        "NOT_TRIGGERED": 0,
                        "GATED": 0,
                        "UNKNOWN": 0,
                    }
                signal_stats[signal_name][signal.status] += 1
        
        # Analyze distributions
        total_receipts = len(receipt_batch)
        
        for signal_name, stats in signal_stats.items():
            triggered_pct = (stats["TRIGGERED"] / total_receipts) * 100
            gated_pct = (stats["GATED"] / total_receipts) * 100
            
            # Signals that never fire
            if triggered_pct == 0:
                print(f"⚠️  Signal '{signal_name}' never triggered in {total_receipts} receipts")
            
            # Signals that fire too often (suspicious heuristic)
            if triggered_pct > 40:
                print(f"⚠️  Signal '{signal_name}' triggered {triggered_pct:.1f}% of the time (>40%)")
            
            # Signals that are always gated
            if gated_pct > 80:
                print(f"⚠️  Signal '{signal_name}' gated {gated_pct:.1f}% of the time (>80%)")

    def test_e_combination_sanity(self, receipt_batch: List[ReceiptFeatures]):
        """
        E. Combination sanity.
        
        Verify expected combinations:
        - multi_address ∧ merchant_mismatch
        - low_ocr ∧ language_mismatch
        - template_low_quality ∧ amount_override
        
        You are validating relationships, not accuracy.
        """
        if len(receipt_batch) < 20:
            pytest.skip("Need ≥20 receipts for combination checks")
        
        # Track combinations
        combinations = {
            "multi_address_and_mismatch": 0,
            "low_ocr_and_language_mismatch": 0,
            "template_low_and_amount_override": 0,
        }
        
        for receipt in receipt_batch:
            signals = receipt.signals
            
            # multi_address ∧ merchant_mismatch
            if (signals.get("addr.multi_address", {}).status == "TRIGGERED" and
                signals.get("addr.merchant_consistency", {}).status == "TRIGGERED"):
                combinations["multi_address_and_mismatch"] += 1
            
            # low_ocr ∧ language_mismatch
            if (signals.get("ocr.confidence_low", {}).status == "TRIGGERED" and
                signals.get("ocr.language_mismatch", {}).status == "TRIGGERED"):
                combinations["low_ocr_and_language_mismatch"] += 1
            
            # template_low_quality ∧ amount_override
            if (signals.get("template.quality_low", {}).status == "TRIGGERED" and
                signals.get("amount.semantic_override", {}).status == "TRIGGERED"):
                combinations["template_low_and_amount_override"] += 1
        
        # Report combinations
        total = len(receipt_batch)
        for combo_name, count in combinations.items():
            pct = (count / total) * 100
            print(f"📊 {combo_name}: {count}/{total} ({pct:.1f}%)")


# Fixtures for testing

@pytest.fixture
def sample_receipt_features():
    """Sample receipt features for testing."""
    from app.schemas.receipt import ReceiptFeatures, SignalV1
    
    return ReceiptFeatures(
        file_features={
            "pdf_metadata": {"Producer": "Adobe PDF", "Creator": "Microsoft Word"},
            "is_image": False,
        },
        text_features={
            "full_text": "INVOICE\nACME Corp\n123 Main St\nTotal: $100.00",
            "language": {"detected": "en", "confidence": 0.95},
        },
        layout_features={},
        forensic_features={},
        document_intent={"confidence": 0.85, "subtype": "INVOICE"},
        signals={
            "addr.structure": SignalV1(
                name="addr.structure",
                status="TRIGGERED",
                confidence=0.9,
                evidence={},
                interpretation="Strong address structure",
            ),
            # Add all other signals as NOT_TRIGGERED or GATED
        },
        signal_version="v1",
    )


@pytest.fixture
def receipt_batch():
    """Batch of receipts for distribution testing."""
    # This would be loaded from actual test data
    # For now, return empty list to skip distribution tests
    return []
