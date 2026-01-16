"""
Reference Rules for Address Validation Features

⚠️ DESIGN PROOF, NOT ENFORCEMENT ⚠️

These rules demonstrate how to safely consume address features:
- V1: address_profile (basic validation)
- V2.1: merchant_address_consistency
- V2.2: multi_address_profile

GUARDRAILS (non-negotiable):
❌ No scoring
❌ No hard fail
✅ At least 2 signals per rule
✅ Always gated on confidence

These are ILLUSTRATIVE examples for:
- Future learned rules
- ML feature engineering
- Human review tooling
- Fraud pattern documentation

DO NOT operationalize without extensive testing and review.
"""

from typing import Dict, Any, List


# ============================================================================
# RULE EXAMPLES: Multi-Address + Consistency Anomalies
# ============================================================================

def rule_addr_multi_and_mismatch(
    doc_subtype: str,
    doc_profile_confidence: float,
    multi_address_profile: Dict[str, Any],
    merchant_address_consistency: Dict[str, Any],
) -> Dict[str, Any]:
    """
    RULE: Multiple addresses + merchant-address mismatch in high-confidence invoice.
    
    Signal Combination:
    - Document is classified as INVOICE with high confidence
    - Multiple distinct addresses detected (bill-to, ship-to, etc.)
    - Merchant name doesn't match any detected address
    
    Risk Hypothesis:
    - Legitimate: B2B invoices often have multiple addresses
    - Suspicious: When combined with other fraud signals (editing, template anomalies)
    
    Usage:
    - Emit as "address_anomaly_cluster" flag
    - Combine with PDF metadata, template quality, etc.
    - NEVER use alone to mark fraud
    
    Returns:
        Dict with status and evidence (no scoring)
    """
    # Confidence gate
    if doc_profile_confidence < 0.8:
        return {"status": "GATED", "reason": "doc_profile_confidence < 0.8"}
    
    # Check conditions
    is_invoice = doc_subtype in {"INVOICE", "TAX_INVOICE", "VAT_INVOICE", "COMMERCIAL_INVOICE"}
    has_multiple_addresses = multi_address_profile.get("status") == "MULTIPLE"
    has_mismatch = merchant_address_consistency.get("status") in {"WEAK_MISMATCH", "MISMATCH"}
    
    if is_invoice and has_multiple_addresses and has_mismatch:
        return {
            "status": "TRIGGERED",
            "rule_id": "RULE_ADDR_MULTI_AND_MISMATCH",
            "risk_hint": "address_anomaly_cluster",
            "evidence": {
                "doc_subtype": doc_subtype,
                "doc_profile_confidence": doc_profile_confidence,
                "multi_address_count": multi_address_profile.get("count", 0),
                "consistency_status": merchant_address_consistency.get("status"),
                "consistency_score": merchant_address_consistency.get("score", 0.0),
            },
            "interpretation": "Multiple addresses with merchant mismatch - review with other signals",
            "next_steps": [
                "Check PDF metadata for suspicious producers",
                "Review template quality signals",
                "Verify merchant legitimacy",
            ],
        }
    
    return {"status": "NOT_TRIGGERED"}


def rule_addr_multi_in_invoice_highconf(
    doc_subtype: str,
    doc_profile_confidence: float,
    multi_address_profile: Dict[str, Any],
    address_profile: Dict[str, Any],
) -> Dict[str, Any]:
    """
    RULE: Multiple addresses in high-confidence invoice (informational).
    
    Signal Combination:
    - Document is classified as INVOICE with high confidence
    - Multiple distinct addresses detected
    - At least one address is PLAUSIBLE or STRONG
    
    Risk Hypothesis:
    - Mostly legitimate (B2B invoices)
    - Useful for understanding document complexity
    
    Usage:
    - Emit as "review_hint" for complex documents
    - Track frequency for tuning
    - Combine with merchant confidence
    
    Returns:
        Dict with status and evidence (no scoring)
    """
    # Confidence gate
    if doc_profile_confidence < 0.8:
        return {"status": "GATED", "reason": "doc_profile_confidence < 0.8"}
    
    # Check conditions
    is_invoice = doc_subtype in {"INVOICE", "TAX_INVOICE", "VAT_INVOICE", "COMMERCIAL_INVOICE"}
    has_multiple_addresses = multi_address_profile.get("status") == "MULTIPLE"
    has_strong_address = address_profile.get("address_classification") in {"PLAUSIBLE_ADDRESS", "STRONG_ADDRESS"}
    
    if is_invoice and has_multiple_addresses and has_strong_address:
        return {
            "status": "TRIGGERED",
            "rule_id": "RULE_ADDR_MULTI_IN_INVOICE_HIGHCONF",
            "review_hint": "complex_invoice_structure",
            "evidence": {
                "doc_subtype": doc_subtype,
                "doc_profile_confidence": doc_profile_confidence,
                "multi_address_count": multi_address_profile.get("count", 0),
                "address_types": multi_address_profile.get("address_types", []),
                "primary_address_classification": address_profile.get("address_classification"),
            },
            "interpretation": "Complex invoice with multiple addresses - likely legitimate B2B",
            "telemetry_note": "Track frequency to understand invoice complexity distribution",
        }
    
    return {"status": "NOT_TRIGGERED"}


# ============================================================================
# RULE EXAMPLES: PO Box + Corporate Mismatch
# ============================================================================

def rule_addr_pobox_corporate_mismatch(
    merchant_name: str,
    merchant_confidence: float,
    address_profile: Dict[str, Any],
    doc_profile_confidence: float,
) -> Dict[str, Any]:
    """
    RULE: PO Box address for corporate merchant (potential red flag).
    
    Signal Combination:
    - Merchant name suggests corporate entity (Ltd, LLC, Corp, etc.)
    - Merchant confidence is high
    - Address is PO Box type
    - Document confidence is high
    
    Risk Hypothesis:
    - Legitimate: Small businesses, remote operations
    - Suspicious: Large corporations typically have physical addresses
    
    Usage:
    - Emit as "address_type_anomaly" flag
    - Combine with merchant size/legitimacy signals
    - NEVER use alone to mark fraud
    
    Returns:
        Dict with status and evidence (no scoring)
    """
    # Confidence gates
    if merchant_confidence < 0.7:
        return {"status": "GATED", "reason": "merchant_confidence < 0.7"}
    
    if doc_profile_confidence < 0.7:
        return {"status": "GATED", "reason": "doc_profile_confidence < 0.7"}
    
    # Check conditions
    corporate_suffixes = ["ltd", "llc", "corp", "corporation", "inc", "pvt", "private", "limited"]
    merchant_lower = merchant_name.lower()
    is_corporate = any(suffix in merchant_lower for suffix in corporate_suffixes)
    
    is_po_box = address_profile.get("address_type") == "PO_BOX"
    
    if is_corporate and is_po_box:
        return {
            "status": "TRIGGERED",
            "rule_id": "RULE_ADDR_POBOX_CORPORATE_MISMATCH",
            "risk_hint": "address_type_anomaly",
            "evidence": {
                "merchant_name": merchant_name,
                "merchant_confidence": merchant_confidence,
                "address_type": address_profile.get("address_type"),
                "address_classification": address_profile.get("address_classification"),
                "doc_profile_confidence": doc_profile_confidence,
            },
            "interpretation": "Corporate merchant with PO Box - review merchant legitimacy",
            "next_steps": [
                "Verify merchant registration",
                "Check if merchant is known/established",
                "Review other documents from same merchant",
            ],
        }
    
    return {"status": "NOT_TRIGGERED"}


# ============================================================================
# RULE EXAMPLES: Confidence-Based Suppression
# ============================================================================

def rule_addr_suppression_low_confidence(
    doc_profile_confidence: float,
    address_profile: Dict[str, Any],
    merchant_address_consistency: Dict[str, Any],
    multi_address_profile: Dict[str, Any],
) -> Dict[str, Any]:
    """
    RULE: Suppress address-derived rules when document confidence is low.
    
    Signal Combination:
    - Document profile confidence < 0.55
    - Any address features would be gated
    
    Risk Hypothesis:
    - Low confidence = unreliable OCR or unclear document type
    - Address signals are not trustworthy
    
    Usage:
    - Emit as "suppression_gate" flag
    - Prevent false positives from noisy documents
    - Track frequency to tune confidence thresholds
    
    Returns:
        Dict with status and evidence (no scoring)
    """
    if doc_profile_confidence < 0.55:
        return {
            "status": "TRIGGERED",
            "rule_id": "RULE_ADDR_SUPPRESSION_LOW_CONFIDENCE",
            "suppression_gate": "address_features_unreliable",
            "evidence": {
                "doc_profile_confidence": doc_profile_confidence,
                "address_features_gated": {
                    "merchant_address_consistency": merchant_address_consistency.get("status") == "UNKNOWN",
                    "multi_address_profile": multi_address_profile.get("status") == "UNKNOWN",
                },
            },
            "interpretation": "Low document confidence - address signals suppressed",
            "telemetry_note": "Track % of docs suppressed to tune confidence threshold",
        }
    
    return {"status": "NOT_TRIGGERED"}


def rule_addr_suppression_weak_merchant(
    merchant_confidence: float,
    merchant_address_consistency: Dict[str, Any],
) -> Dict[str, Any]:
    """
    RULE: Suppress merchant-address consistency when merchant confidence is low.
    
    Signal Combination:
    - Merchant confidence < 0.6
    - Merchant-address consistency would be gated
    
    Risk Hypothesis:
    - Low merchant confidence = uncertain merchant extraction
    - Consistency check is not trustworthy
    
    Usage:
    - Emit as "suppression_gate" flag
    - Prevent false positives from weak merchant signals
    - Track frequency to tune merchant extraction
    
    Returns:
        Dict with status and evidence (no scoring)
    """
    if merchant_confidence < 0.6:
        return {
            "status": "TRIGGERED",
            "rule_id": "RULE_ADDR_SUPPRESSION_WEAK_MERCHANT",
            "suppression_gate": "merchant_consistency_unreliable",
            "evidence": {
                "merchant_confidence": merchant_confidence,
                "consistency_status": merchant_address_consistency.get("status"),
                "consistency_gated": merchant_address_consistency.get("status") == "UNKNOWN",
            },
            "interpretation": "Low merchant confidence - consistency check suppressed",
            "telemetry_note": "Track % of docs suppressed to improve merchant extraction",
        }
    
    return {"status": "NOT_TRIGGERED"}


# ============================================================================
# RULE EXAMPLES: Template + Address Anomalies
# ============================================================================

def rule_addr_template_editing_suspicion(
    suspicious_pdf_producer: bool,
    multi_address_profile: Dict[str, Any],
    address_profile: Dict[str, Any],
    doc_profile_confidence: float,
) -> Dict[str, Any]:
    """
    RULE: Suspicious PDF producer + multiple addresses (editing suspicion).
    
    Signal Combination:
    - PDF producer is suspicious (e.g., online editors)
    - Multiple addresses detected
    - At least one address is PLAUSIBLE or STRONG
    - Document confidence is high
    
    Risk Hypothesis:
    - Legitimate: Users editing legitimate invoices
    - Suspicious: Fraudsters creating fake invoices with editing tools
    
    Usage:
    - Emit as "template_editing_suspicion" flag
    - Combine with other fraud signals (amounts, dates, etc.)
    - NEVER use alone to mark fraud
    
    Returns:
        Dict with status and evidence (no scoring)
    """
    # Confidence gate
    if doc_profile_confidence < 0.7:
        return {"status": "GATED", "reason": "doc_profile_confidence < 0.7"}
    
    # Check conditions
    has_multiple_addresses = multi_address_profile.get("status") == "MULTIPLE"
    has_strong_address = address_profile.get("address_classification") in {"PLAUSIBLE_ADDRESS", "STRONG_ADDRESS"}
    
    if suspicious_pdf_producer and has_multiple_addresses and has_strong_address:
        return {
            "status": "TRIGGERED",
            "rule_id": "RULE_ADDR_TEMPLATE_EDITING_SUSPICION",
            "risk_hint": "template_editing_suspicion",
            "evidence": {
                "suspicious_pdf_producer": suspicious_pdf_producer,
                "multi_address_count": multi_address_profile.get("count", 0),
                "address_classification": address_profile.get("address_classification"),
                "doc_profile_confidence": doc_profile_confidence,
            },
            "interpretation": "Suspicious PDF producer with multiple addresses - review editing patterns",
            "next_steps": [
                "Check PDF metadata for editing timestamps",
                "Review template quality signals",
                "Compare with known legitimate templates",
            ],
        }
    
    return {"status": "NOT_TRIGGERED"}


# ============================================================================
# HELPER: Rule Evaluation Engine (Illustrative)
# ============================================================================

def evaluate_address_rules(
    text_features: Dict[str, Any],
    doc_profile: Dict[str, Any],
    file_features: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Evaluate all reference address rules.
    
    ⚠️ ILLUSTRATIVE ONLY - NOT FOR PRODUCTION ⚠️
    
    This demonstrates how to:
    - Extract features from pipeline output
    - Call reference rules
    - Collect triggered rules
    - Emit structured evidence
    
    Args:
        text_features: Output from features.py
        doc_profile: Document profile from geo_detection
        file_features: File metadata features
    
    Returns:
        List of triggered rules with evidence
    """
    triggered_rules = []
    
    # Extract features
    address_profile = text_features.get("address_profile", {})
    merchant_address_consistency = text_features.get("merchant_address_consistency", {})
    multi_address_profile = text_features.get("multi_address_profile", {})
    
    doc_subtype = doc_profile.get("subtype", "UNKNOWN")
    doc_profile_confidence = doc_profile.get("confidence", 0.0)
    
    merchant_name = text_features.get("merchant_candidate", "")
    merchant_confidence = text_features.get("merchant_confidence", 0.0)
    
    suspicious_pdf_producer = file_features.get("suspicious_producer", False)
    
    # Evaluate rules
    rules_to_check = [
        rule_addr_multi_and_mismatch(
            doc_subtype=doc_subtype,
            doc_profile_confidence=doc_profile_confidence,
            multi_address_profile=multi_address_profile,
            merchant_address_consistency=merchant_address_consistency,
        ),
        rule_addr_multi_in_invoice_highconf(
            doc_subtype=doc_subtype,
            doc_profile_confidence=doc_profile_confidence,
            multi_address_profile=multi_address_profile,
            address_profile=address_profile,
        ),
        rule_addr_pobox_corporate_mismatch(
            merchant_name=merchant_name,
            merchant_confidence=merchant_confidence,
            address_profile=address_profile,
            doc_profile_confidence=doc_profile_confidence,
        ),
        rule_addr_suppression_low_confidence(
            doc_profile_confidence=doc_profile_confidence,
            address_profile=address_profile,
            merchant_address_consistency=merchant_address_consistency,
            multi_address_profile=multi_address_profile,
        ),
        rule_addr_suppression_weak_merchant(
            merchant_confidence=merchant_confidence,
            merchant_address_consistency=merchant_address_consistency,
        ),
        rule_addr_template_editing_suspicion(
            suspicious_pdf_producer=suspicious_pdf_producer,
            multi_address_profile=multi_address_profile,
            address_profile=address_profile,
            doc_profile_confidence=doc_profile_confidence,
        ),
    ]
    
    # Collect triggered rules
    for rule_result in rules_to_check:
        if rule_result.get("status") == "TRIGGERED":
            triggered_rules.append(rule_result)
    
    return triggered_rules


# ============================================================================
# USAGE EXAMPLE (Illustrative)
# ============================================================================

def example_usage():
    """
    Example of how to use reference rules.
    
    ⚠️ DO NOT COPY-PASTE INTO PRODUCTION ⚠️
    """
    # Mock features (in production, these come from features.py)
    text_features = {
        "address_profile": {
            "address_classification": "STRONG_ADDRESS",
            "address_score": 7,
            "address_type": "STANDARD",
        },
        "merchant_address_consistency": {
            "status": "WEAK_MISMATCH",
            "score": 0.4,
        },
        "multi_address_profile": {
            "status": "MULTIPLE",
            "count": 3,
            "address_types": ["STANDARD", "STANDARD", "PO_BOX"],
        },
        "merchant_candidate": "Acme Logistics Ltd",
        "merchant_confidence": 0.85,
    }
    
    doc_profile = {
        "subtype": "INVOICE",
        "confidence": 0.9,
    }
    
    file_features = {
        "suspicious_producer": True,
    }
    
    # Evaluate rules
    triggered = evaluate_address_rules(text_features, doc_profile, file_features)
    
    # Log results (no scoring, no hard fail)
    for rule in triggered:
        print(f"Rule triggered: {rule['rule_id']}")
        print(f"Risk hint: {rule.get('risk_hint', 'N/A')}")
        print(f"Evidence: {rule['evidence']}")
        print(f"Interpretation: {rule['interpretation']}")
        print("---")


if __name__ == "__main__":
    print("⚠️  REFERENCE RULES - DESIGN PROOF ONLY ⚠️")
    print("These rules demonstrate safe feature consumption.")
    print("DO NOT operationalize without extensive testing.\n")
    example_usage()
