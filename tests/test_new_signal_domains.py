"""
Test new signal domains: date, OCR, and language.
"""

import pytest
from datetime import datetime, timedelta
from app.signals import (
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


class TestDateSignals:
    """Test date signal wrappers."""

    def test_date_missing_triggered(self):
        """Test date.missing signal when date is missing."""
        signal = signal_date_missing(
            date_value=None,
            doc_subtype="INVOICE",
            doc_profile_confidence=0.85,
        )
        
        assert signal.name == "date.missing"
        assert signal.status == "TRIGGERED"
        assert signal.confidence == 0.7

    def test_date_missing_not_triggered(self):
        """Test date.missing signal when date is present."""
        signal = signal_date_missing(
            date_value="2024-01-15",
            doc_subtype="INVOICE",
            doc_profile_confidence=0.85,
        )
        
        assert signal.name == "date.missing"
        assert signal.status == "NOT_TRIGGERED"
        assert signal.confidence == 0.9

    def test_date_future_triggered(self):
        """Test date.future signal when date is in future."""
        future_date = (datetime.now() + timedelta(days=30)).date().isoformat()
        
        signal = signal_date_future(
            date_value=future_date,
            doc_profile_confidence=0.85,
        )
        
        assert signal.name == "date.future"
        assert signal.status == "TRIGGERED"
        assert signal.confidence == 0.8
        assert signal.evidence["days_in_future"] > 1

    def test_date_gap_suspicious_negative(self):
        """Test date.gap_suspicious when due date is before issue date."""
        signal = signal_date_gap_suspicious(
            issue_date="2024-01-15",
            due_date="2024-01-10",  # Before issue date
            doc_profile_confidence=0.85,
        )
        
        assert signal.name == "date.gap_suspicious"
        assert signal.status == "TRIGGERED"
        assert signal.confidence == 0.9
        assert signal.evidence["anomaly"] == "due_before_issue"

    def test_date_gap_suspicious_too_long(self):
        """Test date.gap_suspicious when gap is too long."""
        signal = signal_date_gap_suspicious(
            issue_date="2024-01-01",
            due_date="2025-06-01",  # > 365 days
            doc_profile_confidence=0.85,
        )
        
        assert signal.name == "date.gap_suspicious"
        assert signal.status == "TRIGGERED"
        assert signal.evidence["anomaly"] == "gap_too_long"


class TestOCRSignals:
    """Test OCR signal wrappers."""

    def test_ocr_confidence_low_triggered(self):
        """Test ocr.confidence_low signal when confidence is low."""
        signal = signal_ocr_confidence_low(
            ocr_confidence=0.5,
            threshold=0.7,
        )
        
        assert signal.name == "ocr.confidence_low"
        assert signal.status == "TRIGGERED"
        assert signal.confidence == 0.5  # 1.0 - 0.5
        assert signal.evidence["below_threshold"] is True

    def test_ocr_confidence_low_not_triggered(self):
        """Test ocr.confidence_low signal when confidence is acceptable."""
        signal = signal_ocr_confidence_low(
            ocr_confidence=0.9,
            threshold=0.7,
        )
        
        assert signal.name == "ocr.confidence_low"
        assert signal.status == "NOT_TRIGGERED"
        assert signal.confidence == 0.9

    def test_ocr_text_sparse_triggered(self):
        """Test ocr.text_sparse signal when text is sparse."""
        signal = signal_ocr_text_sparse(
            text_length=30,
            word_count=5,
            doc_profile_confidence=0.85,
        )
        
        assert signal.name == "ocr.text_sparse"
        assert signal.status == "TRIGGERED"
        assert signal.confidence == 0.8

    def test_ocr_text_sparse_not_triggered(self):
        """Test ocr.text_sparse signal when text is sufficient."""
        signal = signal_ocr_text_sparse(
            text_length=500,
            word_count=100,
            doc_profile_confidence=0.85,
        )
        
        assert signal.name == "ocr.text_sparse"
        assert signal.status == "NOT_TRIGGERED"
        assert signal.confidence == 0.9

    def test_ocr_language_mismatch_triggered(self):
        """Test ocr.language_mismatch signal when languages don't match."""
        signal = signal_ocr_language_mismatch(
            detected_language="ar",
            expected_language="en",
            language_confidence=0.85,
            doc_profile_confidence=0.85,
        )
        
        assert signal.name == "ocr.language_mismatch"
        assert signal.status == "TRIGGERED"
        assert signal.confidence == 0.85


class TestLanguageSignals:
    """Test language signal wrappers."""

    def test_language_detection_low_confidence_triggered(self):
        """Test language.detection_low_confidence signal."""
        signal = signal_language_detection_low_confidence(
            language_confidence=0.5,
            detected_language="en",
            threshold=0.7,
        )
        
        assert signal.name == "language.detection_low_confidence"
        assert signal.status == "TRIGGERED"
        assert signal.confidence == 0.5  # 1.0 - 0.5

    def test_language_script_mismatch_triggered(self):
        """Test language.script_mismatch signal."""
        signal = signal_language_script_mismatch(
            detected_language="ar",
            detected_script="Latin",  # Should be Arabic
            doc_profile_confidence=0.85,
        )
        
        assert signal.name == "language.script_mismatch"
        assert signal.status == "TRIGGERED"
        assert signal.confidence == 0.7

    def test_language_script_mismatch_not_triggered(self):
        """Test language.script_mismatch signal when script matches."""
        signal = signal_language_script_mismatch(
            detected_language="ar",
            detected_script="Arabic",
            doc_profile_confidence=0.85,
        )
        
        assert signal.name == "language.script_mismatch"
        assert signal.status == "NOT_TRIGGERED"
        assert signal.confidence == 0.9

    def test_language_mixed_scripts_triggered(self):
        """Test language.mixed_scripts signal."""
        signal = signal_language_mixed_scripts(
            scripts_detected=["Latin", "Arabic"],
            script_percentages={"Latin": 0.6, "Arabic": 0.3, "Common": 0.1},
            doc_profile_confidence=0.85,
        )
        
        assert signal.name == "language.mixed_scripts"
        assert signal.status == "TRIGGERED"
        assert signal.evidence["num_scripts"] == 2

    def test_language_mixed_scripts_not_triggered(self):
        """Test language.mixed_scripts signal with single script."""
        signal = signal_language_mixed_scripts(
            scripts_detected=["Latin"],
            script_percentages={"Latin": 0.9, "Common": 0.1},
            doc_profile_confidence=0.85,
        )
        
        assert signal.name == "language.mixed_scripts"
        assert signal.status == "NOT_TRIGGERED"
        assert signal.confidence == 0.9


class TestSignalInvariantsForNewDomains:
    """Test that new signals follow all invariants."""

    def test_all_new_signals_have_correct_names(self):
        """Test that all new signals have name field matching their key."""
        test_cases = [
            ("date.missing", signal_date_missing(None, "INVOICE", 0.85)),
            ("date.future", signal_date_future("2024-01-15", 0.85)),
            ("date.gap_suspicious", signal_date_gap_suspicious("2024-01-01", "2024-01-15", 0.85)),
            ("ocr.confidence_low", signal_ocr_confidence_low(0.5)),
            ("ocr.text_sparse", signal_ocr_text_sparse(30, 5, 0.85)),
            ("ocr.language_mismatch", signal_ocr_language_mismatch("ar", "en", 0.85, 0.85)),
            ("language.detection_low_confidence", signal_language_detection_low_confidence(0.5, "en")),
            ("language.script_mismatch", signal_language_script_mismatch("ar", "Latin", 0.85)),
            ("language.mixed_scripts", signal_language_mixed_scripts(["Latin"], {"Latin": 0.9}, 0.85)),
        ]
        
        for expected_name, signal in test_cases:
            assert signal.name == expected_name, (
                f"Signal name mismatch: expected '{expected_name}' but got '{signal.name}'"
            )

    def test_gated_signals_emitted_for_new_domains(self):
        """Test that GATED signals are emitted for new domains."""
        # Date signals
        date_signal = signal_date_missing(None, "INVOICE", 0.3)
        assert date_signal.status == "GATED"
        assert date_signal.gating_reason is not None
        
        # OCR signals
        ocr_signal = signal_ocr_text_sparse(30, 5, 0.3)
        assert ocr_signal.status == "GATED"
        assert ocr_signal.gating_reason is not None
        
        # Language signals
        lang_signal = signal_language_script_mismatch("ar", "Latin", 0.3)
        assert lang_signal.status == "GATED"
        assert lang_signal.gating_reason is not None
