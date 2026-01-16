"""
Signal wrappers for amount/financial features.

Converts amount features to unified SignalV1 contract.
"""

from typing import Dict, Any, Optional
from app.schemas.receipt import SignalV1


def signal_amount_total_mismatch(
    total_amount: Optional[float],
    items_sum: Optional[float],
    has_line_items: bool,
    total_mismatch: bool,
    doc_profile_confidence: float,
) -> SignalV1:
    """
    Convert total_mismatch to unified signal.
    
    Signal: amount.total_mismatch
    Purpose: Indicates line items sum doesn't match total
    
    Args:
        total_amount: Extracted total amount
        items_sum: Sum of line items
        has_line_items: Whether line items were detected
        total_mismatch: Whether mismatch was detected
        doc_profile_confidence: Document confidence
    
    Returns:
        SignalV1 with privacy-safe evidence
    """
    # Gate on confidence
    if doc_profile_confidence < 0.55:
        return SignalV1(
            status="GATED",
            confidence=0.0,
            evidence={},
            interpretation="Amount validation gated due to low document confidence",
            gating_reason="doc_profile_confidence < 0.55",
        )
    
    # Gate if missing required data
    if total_amount is None or not has_line_items:
        return SignalV1(
            status="NOT_TRIGGERED",
            confidence=0.0,
            evidence={
                "total_amount_present": total_amount is not None,
                "line_items_present": has_line_items,
            },
            interpretation="Insufficient data for total mismatch detection",
        )
    
    if total_mismatch:
        mismatch_amount = abs((items_sum or 0.0) - total_amount)
        mismatch_pct = (mismatch_amount / total_amount * 100) if total_amount > 0 else 0
        
        return SignalV1(
            status="TRIGGERED",
            confidence=0.8,  # High confidence in arithmetic
            evidence={
                "total_amount": round(total_amount, 2),
                "items_sum": round(items_sum or 0.0, 2),
                "mismatch_amount": round(mismatch_amount, 2),
                "mismatch_percentage": round(mismatch_pct, 2),
            },
            interpretation=f"Total amount mismatch detected: ${mismatch_amount:.2f} difference ({mismatch_pct:.1f}%)",
        )
    
    return SignalV1(
        status="NOT_TRIGGERED",
        confidence=0.9,
        evidence={
            "total_amount": round(total_amount, 2),
            "items_sum": round(items_sum or 0.0, 2),
        },
        interpretation="Total amount matches line items sum",
    )


def signal_amount_missing(
    total_amount: Optional[float],
    has_currency: bool,
    doc_subtype: str,
    doc_profile_confidence: float,
) -> SignalV1:
    """
    Convert missing amount to unified signal.
    
    Signal: amount.missing
    Purpose: Indicates expected amount is missing
    
    Args:
        total_amount: Extracted total amount
        has_currency: Whether currency was detected
        doc_subtype: Document subtype
        doc_profile_confidence: Document confidence
    
    Returns:
        SignalV1 with privacy-safe evidence
    """
    # Gate on confidence
    if doc_profile_confidence < 0.55:
        return SignalV1(
            status="GATED",
            confidence=0.0,
            evidence={},
            interpretation="Amount validation gated due to low document confidence",
            gating_reason="doc_profile_confidence < 0.55",
        )
    
    # Only trigger for transactional documents
    transactional_types = {"INVOICE", "TAX_INVOICE", "VAT_INVOICE", "POS_RECEIPT", "CREDIT_NOTE"}
    if doc_subtype not in transactional_types:
        return SignalV1(
            status="NOT_TRIGGERED",
            confidence=0.0,
            evidence={"doc_subtype": doc_subtype},
            interpretation=f"Amount not required for {doc_subtype}",
        )
    
    if total_amount is None:
        return SignalV1(
            status="TRIGGERED",
            confidence=0.7,
            evidence={
                "doc_subtype": doc_subtype,
                "has_currency": has_currency,
                "doc_profile_confidence": doc_profile_confidence,
            },
            interpretation=f"Missing total amount in {doc_subtype}",
        )
    
    return SignalV1(
        status="NOT_TRIGGERED",
        confidence=0.9,
        evidence={"total_amount": round(total_amount, 2)},
        interpretation="Total amount present",
    )


def signal_amount_semantic_override(
    semantic_amounts: Optional[Dict[str, Any]],
    original_total: Optional[float],
    semantic_total: Optional[float],
) -> SignalV1:
    """
    Convert semantic amount override to unified signal.
    
    Signal: amount.semantic_override
    Purpose: Indicates LLM corrected amount extraction
    
    Args:
        semantic_amounts: Semantic amounts result
        original_total: Original extracted total
        semantic_total: LLM-extracted total
    
    Returns:
        SignalV1 with privacy-safe evidence
    """
    if not semantic_amounts or semantic_total is None:
        return SignalV1(
            status="NOT_TRIGGERED",
            confidence=0.0,
            evidence={},
            interpretation="No semantic override applied",
        )
    
    confidence = semantic_amounts.get("confidence", 0.0)
    
    # Only trigger if semantic override actually changed the value
    if original_total is not None and abs(semantic_total - original_total) > 0.01:
        return SignalV1(
            status="TRIGGERED",
            confidence=confidence,
            evidence={
                "original_total": round(original_total, 2),
                "semantic_total": round(semantic_total, 2),
                "difference": round(abs(semantic_total - original_total), 2),
                "semantic_confidence": confidence,
            },
            interpretation=f"Semantic LLM corrected total: ${original_total:.2f} → ${semantic_total:.2f}",
        )
    
    return SignalV1(
        status="NOT_TRIGGERED",
        confidence=confidence,
        evidence={
            "semantic_total": round(semantic_total, 2),
            "semantic_confidence": confidence,
        },
        interpretation="Semantic LLM confirmed original total",
    )
