"""
Reference Rules Package

⚠️ DESIGN PROOF, NOT ENFORCEMENT ⚠️

This package contains illustrative examples of how to safely consume
address validation features in fraud detection rules.
"""

from .address_rules import (
    rule_addr_multi_and_mismatch,
    rule_addr_multi_in_invoice_highconf,
    rule_addr_pobox_corporate_mismatch,
    rule_addr_suppression_low_confidence,
    rule_addr_suppression_weak_merchant,
    rule_addr_template_editing_suspicion,
    evaluate_address_rules,
)

__all__ = [
    "rule_addr_multi_and_mismatch",
    "rule_addr_multi_in_invoice_highconf",
    "rule_addr_pobox_corporate_mismatch",
    "rule_addr_suppression_low_confidence",
    "rule_addr_suppression_weak_merchant",
    "rule_addr_template_editing_suspicion",
    "evaluate_address_rules",
]
