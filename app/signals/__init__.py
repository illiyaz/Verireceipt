"""
Unified Signal Contract (V1) - Signal Wrappers

This package contains all signal wrapper functions that convert
feature extraction outputs into the unified SignalV1 contract.

Signal Domains:
- Address: addr.*
- Amount: amount.*
- Template: template.*
- Merchant: merchant.*
- Date: date.*
- OCR: ocr.*
- Language: language.*
"""

from app.signals.address_signals import (
    signal_addr_structure,
    signal_addr_merchant_consistency,
    signal_addr_multi_address,
)

from app.signals.amount_signals import (
    signal_amount_total_mismatch,
    signal_amount_missing,
    signal_amount_semantic_override,
)

from app.signals.template_signals import (
    signal_pdf_producer_suspicious,
    signal_template_quality_low,
)

from app.signals.merchant_signals import (
    signal_merchant_extraction_weak,
    signal_merchant_confidence_low,
)

from app.signals.date_signals import (
    signal_date_missing,
    signal_date_future,
    signal_date_gap_suspicious,
)

from app.signals.ocr_signals import (
    signal_ocr_confidence_low,
    signal_ocr_text_sparse,
    signal_ocr_language_mismatch,
)

from app.signals.language_signals import (
    signal_language_detection_low_confidence,
    signal_language_script_mismatch,
    signal_language_mixed_scripts,
)

__all__ = [
    # Address signals
    "signal_addr_structure",
    "signal_addr_merchant_consistency",
    "signal_addr_multi_address",
    # Amount signals
    "signal_amount_total_mismatch",
    "signal_amount_missing",
    "signal_amount_semantic_override",
    # Template signals
    "signal_pdf_producer_suspicious",
    "signal_template_quality_low",
    # Merchant signals
    "signal_merchant_extraction_weak",
    "signal_merchant_confidence_low",
    # Date signals
    "signal_date_missing",
    "signal_date_future",
    "signal_date_gap_suspicious",
    # OCR signals
    "signal_ocr_confidence_low",
    "signal_ocr_text_sparse",
    "signal_ocr_language_mismatch",
    # Language signals
    "signal_language_detection_low_confidence",
    "signal_language_script_mismatch",
    "signal_language_mixed_scripts",
]
