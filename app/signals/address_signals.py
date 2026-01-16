"""
Signal wrappers for address validation features.

Converts address features to unified SignalV1 contract.
"""

from typing import Dict, Any
from app.schemas.receipt import SignalV1


def signal_addr_structure(address_profile: Dict[str, Any]) -> SignalV1:
    """
    Convert address_profile to unified signal.
    
    Signal: addr.structure
    Purpose: Indicates presence and quality of address structure
    
    Args:
        address_profile: Output from validate_address()
    
    Returns:
        SignalV1 with privacy-safe evidence
    """
    classification = address_profile.get("address_classification", "NOT_AN_ADDRESS")
    score = address_profile.get("address_score", 0)
    address_type = address_profile.get("address_type", "UNKNOWN")
    evidence_list = address_profile.get("address_evidence", [])
    
    # Map classification to signal status
    if classification == "NOT_AN_ADDRESS":
        status = "NOT_TRIGGERED"
        confidence = 0.0
        interpretation = "No valid address structure detected"
    elif classification == "WEAK_ADDRESS":
        status = "NOT_TRIGGERED"
        confidence = 0.3
        interpretation = "Weak address signals detected (score 1-3)"
    elif classification == "PLAUSIBLE_ADDRESS":
        status = "TRIGGERED"
        confidence = 0.6
        interpretation = "Plausible address structure detected (score 4-5)"
    elif classification == "STRONG_ADDRESS":
        status = "TRIGGERED"
        confidence = 0.9
        interpretation = "Strong address structure detected (score ≥6)"
    else:
        status = "UNKNOWN"
        confidence = 0.0
        interpretation = "Address validation failed"
    
    return SignalV1(
        status=status,
        confidence=confidence,
        evidence={
            "classification": classification,
            "score": score,
            "address_type": address_type,
            "signals_found": evidence_list,
        },
        interpretation=interpretation,
    )


def signal_addr_merchant_consistency(
    merchant_address_consistency: Dict[str, Any]
) -> SignalV1:
    """
    Convert merchant_address_consistency to unified signal.
    
    Signal: addr.merchant_consistency
    Purpose: Indicates merchant-address alignment
    
    Args:
        merchant_address_consistency: Output from assess_merchant_address_consistency()
    
    Returns:
        SignalV1 with privacy-safe evidence
    """
    status_raw = merchant_address_consistency.get("status", "UNKNOWN")
    score = merchant_address_consistency.get("score", 0.0)
    evidence_dict = merchant_address_consistency.get("evidence", {})
    
    # Map status to signal
    if status_raw == "UNKNOWN":
        gating_reason = evidence_dict.get("reason", "Unknown gating reason")
        return SignalV1(
            status="GATED",
            confidence=0.0,
            evidence={},
            interpretation="Merchant-address consistency check gated",
            gating_reason=gating_reason,
        )
    elif status_raw == "CONSISTENT":
        return SignalV1(
            status="NOT_TRIGGERED",
            confidence=score,
            evidence={
                "consistency_status": status_raw,
                "score": score,
                "overlap_signals": evidence_dict.get("overlap_signals", []),
            },
            interpretation=f"Merchant and address are consistent (score: {score:.2f})",
        )
    elif status_raw in {"WEAK_MISMATCH", "MISMATCH"}:
        return SignalV1(
            status="TRIGGERED",
            confidence=1.0 - score,  # Invert: low score = high mismatch confidence
            evidence={
                "consistency_status": status_raw,
                "score": score,
                "mismatch_type": status_raw,
            },
            interpretation=f"Merchant-address mismatch detected: {status_raw} (score: {score:.2f})",
        )
    else:
        return SignalV1(
            status="UNKNOWN",
            confidence=0.0,
            evidence={},
            interpretation="Merchant-address consistency check failed",
        )


def signal_addr_multi_address(
    multi_address_profile: Dict[str, Any]
) -> SignalV1:
    """
    Convert multi_address_profile to unified signal.
    
    Signal: addr.multi_address
    Purpose: Indicates presence of multiple distinct addresses
    
    Args:
        multi_address_profile: Output from detect_multi_address_profile()
    
    Returns:
        SignalV1 with privacy-safe evidence
    """
    status_raw = multi_address_profile.get("status", "UNKNOWN")
    count = multi_address_profile.get("count", 0)
    address_types = multi_address_profile.get("address_types", [])
    evidence_list = multi_address_profile.get("evidence", [])
    distinctness_basis = multi_address_profile.get("distinctness_basis", [])
    
    # Map status to signal
    if status_raw == "UNKNOWN":
        gating_reason = evidence_list[0] if evidence_list else "Unknown gating reason"
        return SignalV1(
            status="GATED",
            confidence=0.0,
            evidence={},
            interpretation="Multi-address detection gated",
            gating_reason=gating_reason,
        )
    elif status_raw == "SINGLE":
        return SignalV1(
            status="NOT_TRIGGERED",
            confidence=0.8,  # High confidence in single address
            evidence={
                "count": count,
                "address_types": address_types,
                "evidence": evidence_list,
            },
            interpretation=f"Single address detected (count: {count})",
        )
    elif status_raw == "MULTIPLE":
        # Confidence based on distinctness basis
        if "postal_tokens" in distinctness_basis:
            confidence = 0.9  # High confidence - postal codes are strong
        elif "address_type" in distinctness_basis:
            confidence = 0.7  # Medium confidence - type differences
        else:
            confidence = 0.6  # Lower confidence - structural only
        
        return SignalV1(
            status="TRIGGERED",
            confidence=confidence,
            evidence={
                "count": count,
                "address_types": address_types,
                "distinctness_basis": distinctness_basis,
                "evidence": evidence_list,
            },
            interpretation=f"Multiple distinct addresses detected (count: {count}, basis: {', '.join(distinctness_basis)})",
        )
    else:
        return SignalV1(
            status="UNKNOWN",
            confidence=0.0,
            evidence={},
            interpretation="Multi-address detection failed",
        )
