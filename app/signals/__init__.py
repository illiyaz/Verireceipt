"""
Unified Signal Wrappers Package

Converts feature outputs to SignalV1 contract.
"""

from .address_signals import (
    signal_addr_structure,
    signal_addr_merchant_consistency,
    signal_addr_multi_address,
)
from .amount_signals import (
    signal_amount_total_mismatch,
    signal_amount_missing,
    signal_amount_semantic_override,
)
from .template_signals import (
    signal_pdf_producer_suspicious,
    signal_template_quality_low,
)
from .merchant_signals import (
    signal_merchant_extraction_weak,
    signal_merchant_confidence_low,
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
]
