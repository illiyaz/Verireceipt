"""
Rule × Document Family Allow-List Matrix

Enforces which rules can execute on which document families.
This prevents rule bleed and accidental execution outside intended scope.

Usage:
    from app.pipelines.rule_family_matrix import is_rule_allowed_for_family
    
    if not is_rule_allowed_for_family("R7B_INVOICE_TOTAL_RECONCILIATION", doc_family):
        return  # silent skip
"""

from typing import Set, Dict, Optional
from enum import Enum


class ExecutionMode(Enum):
    """
    Rule execution mode for a document family.
    
    BLOCK: Full enforcement - rule fires, contributes to score, can block decision
    SOFT: Soft enforcement - rule fires, logs warning, minimal score contribution
    AUDIT: Audit only - rule fires, logs for analysis, zero score contribution
    FORBIDDEN: Silent skip - rule does not execute
    """
    BLOCK = "block"  # Full enforcement (score + decision impact)
    SOFT = "soft"  # Soft enforcement (logs + minimal score)
    AUDIT = "audit"  # Audit only (logs, zero score)
    FORBIDDEN = "forbidden"  # Silent skip


# Canonical Rule × Family Matrix (v1.0)
# This is the single source of truth for rule execution permissions
RULE_FAMILY_MATRIX: Dict[str, Dict[str, ExecutionMode]] = {
    "R7_TOTAL_MISMATCH": {
        "POS_RECEIPT": ExecutionMode.BLOCK,
        "POS_RESTAURANT": ExecutionMode.BLOCK,
        "POS_RETAIL": ExecutionMode.BLOCK,
        "COMMERCIAL_INVOICE": ExecutionMode.FORBIDDEN,
        "TAX_INVOICE": ExecutionMode.FORBIDDEN,
        "CREDIT_NOTE": ExecutionMode.FORBIDDEN,
        "LOGISTICS": ExecutionMode.FORBIDDEN,
        "SHIPPING_DOC": ExecutionMode.FORBIDDEN,
        "SUBSCRIPTION": ExecutionMode.FORBIDDEN,
        "SERVICE_STATEMENT": ExecutionMode.FORBIDDEN,
        "REIMBURSEMENT_SUPPORTING_DOC": ExecutionMode.FORBIDDEN,
        "UNKNOWN": ExecutionMode.FORBIDDEN,
    },
    "R7B_INVOICE_TOTAL_RECONCILIATION": {
        "POS_RECEIPT": ExecutionMode.FORBIDDEN,
        "COMMERCIAL_INVOICE": ExecutionMode.BLOCK,
        "TAX_INVOICE": ExecutionMode.BLOCK,
        "CREDIT_NOTE": ExecutionMode.FORBIDDEN,
        "LOGISTICS": ExecutionMode.FORBIDDEN,
        "SUBSCRIPTION": ExecutionMode.SOFT,  # Subscription invoices are messy, soft enforcement
        "REIMBURSEMENT_SUPPORTING_DOC": ExecutionMode.FORBIDDEN,
        "UNKNOWN": ExecutionMode.FORBIDDEN,
    },
    "R7C_CREDIT_NOTE_RECONCILIATION": {
        "POS_RECEIPT": ExecutionMode.FORBIDDEN,
        "COMMERCIAL_INVOICE": ExecutionMode.FORBIDDEN,
        "TAX_INVOICE": ExecutionMode.SOFT,  # Credit notes can be tax invoices, but soft enforcement
        "CREDIT_NOTE": ExecutionMode.BLOCK,
        "LOGISTICS": ExecutionMode.FORBIDDEN,
        "SUBSCRIPTION": ExecutionMode.FORBIDDEN,
        "REIMBURSEMENT_SUPPORTING_DOC": ExecutionMode.FORBIDDEN,
        "UNKNOWN": ExecutionMode.FORBIDDEN,
    },
    "R9B_DOC_TYPE_UNKNOWN_OR_MIXED": {
        "POS_RECEIPT": ExecutionMode.BLOCK,
        "POS_RESTAURANT": ExecutionMode.BLOCK,
        "POS_RETAIL": ExecutionMode.BLOCK,
        "COMMERCIAL_INVOICE": ExecutionMode.FORBIDDEN,  # Invoices can have mixed language
        "TAX_INVOICE": ExecutionMode.FORBIDDEN,
        "CREDIT_NOTE": ExecutionMode.FORBIDDEN,
        "LOGISTICS": ExecutionMode.FORBIDDEN,
        "SUBSCRIPTION": ExecutionMode.FORBIDDEN,
        "REIMBURSEMENT_SUPPORTING_DOC": ExecutionMode.FORBIDDEN,
        "UNKNOWN": ExecutionMode.FORBIDDEN,  # Already unknown, no point flagging
    },
    "R10_TEMPLATE_QUALITY": {
        "POS_RECEIPT": ExecutionMode.SOFT,  # Template quality is a soft heuristic
        "POS_RESTAURANT": ExecutionMode.SOFT,
        "POS_RETAIL": ExecutionMode.SOFT,
        "COMMERCIAL_INVOICE": ExecutionMode.SOFT,
        "TAX_INVOICE": ExecutionMode.SOFT,
        "CREDIT_NOTE": ExecutionMode.FORBIDDEN,
        "LOGISTICS": ExecutionMode.FORBIDDEN,
        "SUBSCRIPTION": ExecutionMode.FORBIDDEN,
        "REIMBURSEMENT_SUPPORTING_DOC": ExecutionMode.FORBIDDEN,
        "UNKNOWN": ExecutionMode.FORBIDDEN,  # Safety: never fire on unknown
    },
}


def is_rule_allowed_for_family(
    rule_id: str,
    doc_family: str,
    allow_soft: bool = True,
    allow_audit: bool = True
) -> bool:
    """
    Check if a rule is allowed to execute for a document family.
    
    Args:
        rule_id: Rule identifier (e.g., "R7B_INVOICE_TOTAL_RECONCILIATION")
        doc_family: Document family (e.g., "COMMERCIAL_INVOICE")
        allow_soft: If True, treat SOFT mode as allowed (default: True)
        allow_audit: If True, treat AUDIT mode as allowed (default: True)
    
    Returns:
        True if rule can execute, False otherwise
    """
    # Normalize inputs
    rule_id = rule_id.upper()
    doc_family = doc_family.upper()
    
    # Check if rule exists in matrix
    if rule_id not in RULE_FAMILY_MATRIX:
        # Unknown rules are forbidden by default (fail-safe)
        return False
    
    # Get execution mode for this family
    mode = RULE_FAMILY_MATRIX[rule_id].get(doc_family, ExecutionMode.FORBIDDEN)
    
    if mode == ExecutionMode.BLOCK:
        return True
    elif mode == ExecutionMode.SOFT and allow_soft:
        return True
    elif mode == ExecutionMode.AUDIT and allow_audit:
        return True
    else:
        return False


def get_allowed_families_for_rule(
    rule_id: str,
    include_soft: bool = True,
    include_audit: bool = True
) -> Set[str]:
    """
    Get all document families allowed for a rule.
    
    Args:
        rule_id: Rule identifier
        include_soft: If True, include SOFT mode families (default: True)
        include_audit: If True, include AUDIT mode families (default: True)
    
    Returns:
        Set of allowed document family names
    """
    rule_id = rule_id.upper()
    
    if rule_id not in RULE_FAMILY_MATRIX:
        return set()
    
    allowed = set()
    for family, mode in RULE_FAMILY_MATRIX[rule_id].items():
        if mode == ExecutionMode.BLOCK:
            allowed.add(family)
        elif mode == ExecutionMode.SOFT and include_soft:
            allowed.add(family)
        elif mode == ExecutionMode.AUDIT and include_audit:
            allowed.add(family)
    
    return allowed


def get_execution_mode(rule_id: str, doc_family: str) -> ExecutionMode:
    """
    Get the execution mode for a rule on a document family.
    
    Args:
        rule_id: Rule identifier
        doc_family: Document family
    
    Returns:
        ExecutionMode (ALLOWED, SOFT, or FORBIDDEN)
    """
    rule_id = rule_id.upper()
    doc_family = doc_family.upper()
    
    if rule_id not in RULE_FAMILY_MATRIX:
        return ExecutionMode.FORBIDDEN
    
    return RULE_FAMILY_MATRIX[rule_id].get(doc_family, ExecutionMode.FORBIDDEN)


def validate_rule_declaration(rule_id: str, declared_families: Set[str]) -> bool:
    """
    Validate that a rule's declared families match the matrix.
    Used in CI to enforce compliance.
    
    Args:
        rule_id: Rule identifier
        declared_families: Families declared in rule header
    
    Returns:
        True if declaration matches matrix, False otherwise
    """
    matrix_families = get_allowed_families_for_rule(rule_id, include_soft=True)
    
    # Normalize
    declared_families = {f.upper() for f in declared_families}
    
    return declared_families == matrix_families
