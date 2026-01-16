"""
Document Type Profiles - Rule Configuration by Document Class

Architecture:
    OCR → LLM Classification → Profile Selection → Targeted Validation

Instead of applying all rules to all documents, we:
1. Classify document type early (via LLM)
2. Select appropriate rule profile
3. Apply only relevant rules with correct thresholds

This prevents false positives on commercial invoices, trade documents, etc.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class DocumentProfile:
    """
    Rule configuration profile for a specific document class.
    
    Defines which rules apply and with what severity/thresholds.
    """
    doc_class: str  # COMMERCIAL_INVOICE, POS_RECEIPT, TRADE_DOCUMENT, etc.
    risk_model: str  # fraud_detection, trade_document, compliance, etc.
    
    # Rule toggles
    apply_total_reconciliation: bool = True
    apply_date_gap_rules: bool = True
    apply_missing_field_penalties: bool = True
    apply_geo_currency_mismatch: bool = True
    apply_suspicious_software: bool = True
    
    # Fraud surface
    fraud_surface: str = "medium"  # low, medium, high
    
    # Thresholds
    date_gap_threshold_days: Optional[int] = 90
    total_mismatch_tolerance: float = 0.05  # 5%
    ocr_confidence_threshold: float = 0.5
    
    # Expected fields (for missing field penalties)
    required_fields: List[str] = field(default_factory=list)
    optional_fields: List[str] = field(default_factory=list)
    
    # Rule severity overrides
    severity_overrides: Dict[str, str] = field(default_factory=dict)
    
    # Disabled rules (including learned patterns)
    disabled_rules: List[str] = field(default_factory=list)
    
    # Learned rule caps (max total contribution from learned patterns)
    max_learned_contribution: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_class": self.doc_class,
            "risk_model": self.risk_model,
            "apply_total_reconciliation": self.apply_total_reconciliation,
            "apply_date_gap_rules": self.apply_date_gap_rules,
            "apply_missing_field_penalties": self.apply_missing_field_penalties,
            "apply_geo_currency_mismatch": self.apply_geo_currency_mismatch,
            "apply_suspicious_software": self.apply_suspicious_software,
            "fraud_surface": self.fraud_surface,
            "date_gap_threshold_days": self.date_gap_threshold_days,
            "total_mismatch_tolerance": self.total_mismatch_tolerance,
            "ocr_confidence_threshold": self.ocr_confidence_threshold,
            "required_fields": self.required_fields,
            "optional_fields": self.optional_fields,
            "severity_overrides": self.severity_overrides,
            "disabled_rules": self.disabled_rules,
            "max_learned_contribution": self.max_learned_contribution,
        }


# ============================================================================
# PROFILE DEFINITIONS
# ============================================================================

# POS Receipt (High fraud risk - strict validation)
POS_RECEIPT_PROFILE = DocumentProfile(
    doc_class="POS_RECEIPT",
    risk_model="fraud_detection",
    fraud_surface="high",
    apply_total_reconciliation=True,
    apply_date_gap_rules=True,
    apply_missing_field_penalties=True,
    apply_geo_currency_mismatch=True,
    apply_suspicious_software=True,
    date_gap_threshold_days=90,
    total_mismatch_tolerance=0.05,
    required_fields=["merchant", "total", "date"],
    optional_fields=["line_items", "tax", "payment_method"],
)

# Commercial Invoice (Trade document - different validation)
COMMERCIAL_INVOICE_PROFILE = DocumentProfile(
    doc_class="COMMERCIAL_INVOICE",
    risk_model="trade_document",
    fraud_surface="low",
    apply_total_reconciliation=False,  # Line items may not sum (shipping, duties, etc.)
    apply_date_gap_rules=False,  # Invoices often created later for accounting
    apply_missing_field_penalties=False,  # Different field requirements
    apply_geo_currency_mismatch=False,  # Cross-border is expected
    apply_suspicious_software=False,  # PDFs are normal for invoices
    date_gap_threshold_days=None,  # No limit
    total_mismatch_tolerance=0.20,  # 20% tolerance for complex invoices
    required_fields=["invoice_number", "total", "date", "parties"],
    optional_fields=["line_items", "tax", "shipping", "terms"],
    severity_overrides={
        "R16_SUSPICIOUS_DATE_GAP": "INFO",  # Downgrade to info only
        "R1_SUSPICIOUS_SOFTWARE": "INFO",
    },
    disabled_rules=[
        "LR_SPACING_ANOMALY",  # Commercial invoices have varied layouts
        "LR_MISSING_ELEMENTS",  # Different field requirements than receipts
        "LR_INVALID_ADDRESS",  # Multi-line addresses, OCR noise common
    ],
    max_learned_contribution=0.10,  # Cap learned patterns at +0.10 total
)

# Tax Invoice (Formal business document)
TAX_INVOICE_PROFILE = DocumentProfile(
    doc_class="TAX_INVOICE",
    risk_model="compliance",
    fraud_surface="medium",
    apply_total_reconciliation=True,
    apply_date_gap_rules=False,  # Tax invoices can be issued later
    apply_missing_field_penalties=True,
    apply_geo_currency_mismatch=False,  # May be cross-border
    apply_suspicious_software=False,
    date_gap_threshold_days=180,
    total_mismatch_tolerance=0.02,  # Strict for tax compliance
    required_fields=["tax_id", "invoice_number", "total", "tax_amount", "date"],
    optional_fields=["line_items", "payment_terms"],
)

# Bill of Lading / Shipping Document
TRADE_DOCUMENT_PROFILE = DocumentProfile(
    doc_class="TRADE_DOCUMENT",
    risk_model="logistics",
    fraud_surface="low",
    apply_total_reconciliation=False,  # No totals to reconcile
    apply_date_gap_rules=False,  # Shipping docs created over time
    apply_missing_field_penalties=False,
    apply_geo_currency_mismatch=False,
    apply_suspicious_software=False,
    date_gap_threshold_days=None,
    required_fields=["document_number", "date", "parties"],
    optional_fields=["cargo_details", "vessel", "port"],
    disabled_rules=[
        "LR_SPACING_ANOMALY",
        "LR_MISSING_ELEMENTS",
        "LR_INVALID_ADDRESS",
    ],
    max_learned_contribution=0.05,
)

# Utility Bill
UTILITY_BILL_PROFILE = DocumentProfile(
    doc_class="UTILITY_BILL",
    risk_model="recurring_billing",
    fraud_surface="medium",
    apply_total_reconciliation=False,  # Complex billing with fees
    apply_date_gap_rules=False,  # Bills issued monthly
    apply_missing_field_penalties=True,
    apply_geo_currency_mismatch=True,
    apply_suspicious_software=True,
    date_gap_threshold_days=60,
    total_mismatch_tolerance=0.10,
    required_fields=["account_number", "total", "date", "provider"],
    optional_fields=["usage", "previous_balance", "payment_due"],
    disabled_rules=[
        "LR_SPACING_ANOMALY",  # Utility bills have varied formats
        "LR_INVALID_ADDRESS",  # Address formats vary by provider
    ],
    max_learned_contribution=0.10,
)

# Bank Statement
BANK_STATEMENT_PROFILE = DocumentProfile(
    doc_class="BANK_STATEMENT",
    risk_model="financial_statement",
    fraud_surface="high",
    apply_total_reconciliation=False,  # Transactions don't sum to total
    apply_date_gap_rules=False,  # Statements issued monthly
    apply_missing_field_penalties=True,
    apply_geo_currency_mismatch=False,
    apply_suspicious_software=True,  # Bank statements should be from bank software
    date_gap_threshold_days=45,
    required_fields=["account_number", "date", "bank_name", "balance"],
    optional_fields=["transactions", "interest", "fees"],
    severity_overrides={
        "R1_SUSPICIOUS_SOFTWARE": "HARD_FAIL",  # Very strict for bank docs
    }
)

# Expense Report
EXPENSE_REPORT_PROFILE = DocumentProfile(
    doc_class="EXPENSE_REPORT",
    risk_model="fraud_detection",
    fraud_surface="high",
    apply_total_reconciliation=True,
    apply_date_gap_rules=True,
    apply_missing_field_penalties=True,
    apply_geo_currency_mismatch=True,
    apply_suspicious_software=True,
    date_gap_threshold_days=30,  # Strict - expenses should be recent
    total_mismatch_tolerance=0.01,  # Very strict
    required_fields=["employee", "total", "date", "receipts"],
    optional_fields=["category", "project", "approver"],
)

# Unknown/Fallback (Conservative - apply most rules)
UNKNOWN_DOCUMENT_PROFILE = DocumentProfile(
    doc_class="UNKNOWN",
    risk_model="fraud_detection",
    fraud_surface="medium",
    apply_total_reconciliation=True,
    apply_date_gap_rules=True,
    apply_missing_field_penalties=False,  # Don't penalize unknown docs
    apply_geo_currency_mismatch=True,
    apply_suspicious_software=True,
    date_gap_threshold_days=90,
    total_mismatch_tolerance=0.10,
    required_fields=[],
    optional_fields=[],
)


# ============================================================================
# PROFILE REGISTRY
# ============================================================================

DOCUMENT_PROFILES: Dict[str, DocumentProfile] = {
    "POS_RECEIPT": POS_RECEIPT_PROFILE,
    "POS_RESTAURANT": POS_RECEIPT_PROFILE,  # Alias
    "POS_RETAIL": POS_RECEIPT_PROFILE,  # Alias
    "POS_FUEL": POS_RECEIPT_PROFILE,  # Alias
    
    "COMMERCIAL_INVOICE": COMMERCIAL_INVOICE_PROFILE,
    "SALES_INVOICE": COMMERCIAL_INVOICE_PROFILE,  # Alias
    "PROFORMA_INVOICE": COMMERCIAL_INVOICE_PROFILE,  # Alias
    
    "TAX_INVOICE": TAX_INVOICE_PROFILE,
    "VAT_INVOICE": TAX_INVOICE_PROFILE,  # Alias
    
    "TRADE_DOCUMENT": TRADE_DOCUMENT_PROFILE,
    "BILL_OF_LADING": TRADE_DOCUMENT_PROFILE,  # Alias
    "SHIPPING_BILL": TRADE_DOCUMENT_PROFILE,  # Alias
    "AIR_WAYBILL": TRADE_DOCUMENT_PROFILE,  # Alias
    
    "UTILITY_BILL": UTILITY_BILL_PROFILE,
    "ELECTRICITY_BILL": UTILITY_BILL_PROFILE,  # Alias
    "WATER_BILL": UTILITY_BILL_PROFILE,  # Alias
    "TELECOM_BILL": UTILITY_BILL_PROFILE,  # Alias
    
    "BANK_STATEMENT": BANK_STATEMENT_PROFILE,
    "CARD_STATEMENT": BANK_STATEMENT_PROFILE,  # Alias
    
    "EXPENSE_REPORT": EXPENSE_REPORT_PROFILE,
    "EXPENSE_CLAIM": EXPENSE_REPORT_PROFILE,  # Alias
    
    "UNKNOWN": UNKNOWN_DOCUMENT_PROFILE,
}


def get_profile_for_doc_class(doc_class: str) -> DocumentProfile:
    """
    Get rule profile for a document class.
    
    Args:
        doc_class: Document class (e.g., "COMMERCIAL_INVOICE", "POS_RECEIPT")
    
    Returns:
        DocumentProfile with appropriate rule configuration
    """
    doc_class_upper = str(doc_class).upper().strip()
    
    # Direct match
    if doc_class_upper in DOCUMENT_PROFILES:
        return DOCUMENT_PROFILES[doc_class_upper]
    
    # Fuzzy match for POS variants
    if doc_class_upper.startswith("POS_"):
        return POS_RECEIPT_PROFILE
    
    # Fuzzy match for invoice variants
    if "INVOICE" in doc_class_upper:
        if "TAX" in doc_class_upper or "VAT" in doc_class_upper:
            return TAX_INVOICE_PROFILE
        return COMMERCIAL_INVOICE_PROFILE
    
    # Fuzzy match for bill variants
    if "BILL" in doc_class_upper:
        if any(x in doc_class_upper for x in ["UTILITY", "ELECTRIC", "WATER", "TELECOM"]):
            return UTILITY_BILL_PROFILE
        if "LADING" in doc_class_upper or "SHIPPING" in doc_class_upper:
            return TRADE_DOCUMENT_PROFILE
    
    # Fuzzy match for statement variants
    if "STATEMENT" in doc_class_upper:
        return BANK_STATEMENT_PROFILE
    
    # Default to unknown
    return UNKNOWN_DOCUMENT_PROFILE


def should_apply_rule(profile, rule_id: str) -> bool:
    """
    Check if a rule should be applied for this document profile.
    
    Args:
        profile: Document profile (DocumentProfile object or dict)
        rule_id: Rule ID (e.g., "R7_TOTAL_MISMATCH", "LR_SPACING_ANOMALY")
    
    Returns:
        True if rule should be applied
    """
    # Handle both DocumentProfile objects and dicts
    if isinstance(profile, dict):
        # Convert dict to DocumentProfile for consistency
        doc_class = profile.get("doc_class", "UNKNOWN")
        profile = get_profile_for_doc_class(doc_class)
    
    # Check disabled_rules list first (for learned patterns and explicit disables)
    if rule_id in profile.disabled_rules:
        return False
    
    # Rule-specific gates
    if rule_id == "R7_TOTAL_MISMATCH":
        return profile.apply_total_reconciliation
    
    if rule_id == "R16_SUSPICIOUS_DATE_GAP":
        return profile.apply_date_gap_rules
    
    if rule_id.startswith("R3_") or rule_id.startswith("R4_") or rule_id.startswith("R5_"):
        # Missing field rules
        return profile.apply_missing_field_penalties
    
    if rule_id == "GEO_CURRENCY_MISMATCH":
        return profile.apply_geo_currency_mismatch
    
    if rule_id == "R1_SUSPICIOUS_SOFTWARE":
        return profile.apply_suspicious_software
    
    # Default: apply rule
    return True


def get_rule_severity(profile, rule_id: str, default_severity: str) -> str:
    """
    Get rule severity for this document profile.
    
    Args:
        profile: Document profile (DocumentProfile object or dict)
        rule_id: Rule ID
        default_severity: Default severity if no override
    
    Returns:
        Severity level (HARD_FAIL, CRITICAL, WARNING, INFO)
    """
    # Handle both DocumentProfile objects and dicts
    if isinstance(profile, dict):
        # Convert dict to DocumentProfile for consistency
        doc_class = profile.get("doc_class", "UNKNOWN")
        profile = get_profile_for_doc_class(doc_class)
    
    return profile.severity_overrides.get(rule_id, default_severity)
