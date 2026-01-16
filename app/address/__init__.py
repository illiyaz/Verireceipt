"""
Address validation module for VeriReceipt.

Provides geo-agnostic, structure-based address validation.
"""

from .validate import (
    validate_address,
    assess_merchant_address_consistency,
    detect_multi_address_profile,
)

__all__ = [
    "validate_address",
    "assess_merchant_address_consistency",
    "detect_multi_address_profile",
]
