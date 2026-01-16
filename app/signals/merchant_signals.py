"""
Signal wrappers for merchant extraction features.

Converts merchant extraction features to unified SignalV1 contract.
"""

from typing import Optional
from app.schemas.receipt import SignalV1


def signal_merchant_extraction_weak(
    merchant_candidate: Optional[str],
    merchant_confidence: float,
    doc_profile_confidence: float,
) -> SignalV1:
    """
    Convert weak merchant extraction to unified signal.
    
    Signal: merchant.extraction_weak
    Purpose: Indicates merchant name extraction is uncertain
    
    Args:
        merchant_candidate: Extracted merchant name
        merchant_confidence: Merchant extraction confidence
        doc_profile_confidence: Document confidence
    
    Returns:
        SignalV1 with privacy-safe evidence
    """
    # Gate on document confidence
    if doc_profile_confidence < 0.55:
        return SignalV1(
            name="merchant.extraction_weak",
            status="GATED",
            confidence=0.0,
            evidence={},
            interpretation="Merchant extraction check gated due to low document confidence",
            gating_reason="doc_profile_confidence < 0.55",
        )
    
    # No merchant found
    if not merchant_candidate:
        return SignalV1(
            name="merchant.extraction_weak",
            status="TRIGGERED",
            confidence=0.9,
            evidence={
                "merchant_present": False,
                "merchant_confidence": 0.0,
            },
            interpretation="No merchant name detected",
        )
    
    # Weak merchant confidence
    if merchant_confidence < 0.6:
        return SignalV1(
            name="merchant.extraction_weak",
            status="TRIGGERED",
            confidence=merchant_confidence,
            evidence={
                "merchant_present": True,
                "merchant_confidence": round(merchant_confidence, 2),
                "merchant_length": len(merchant_candidate),
            },
            interpretation=f"Weak merchant extraction (confidence: {merchant_confidence:.2f})",
        )
    
    return SignalV1(
        name="merchant.extraction_weak",
        status="NOT_TRIGGERED",
        confidence=merchant_confidence,
        evidence={
            "merchant_present": True,
            "merchant_confidence": round(merchant_confidence, 2),
        },
        interpretation=f"Strong merchant extraction (confidence: {merchant_confidence:.2f})",
    )


def signal_merchant_confidence_low(
    merchant_confidence: float,
    threshold: float = 0.6,
) -> SignalV1:
    """
    Convert merchant confidence threshold to unified signal.
    
    Signal: merchant.confidence_low
    Purpose: Indicates merchant confidence below threshold
    
    Args:
        merchant_confidence: Merchant extraction confidence
        threshold: Confidence threshold (default: 0.6)
    
    Returns:
        SignalV1 with privacy-safe evidence
    """
    if merchant_confidence < threshold:
        return SignalV1(
            name="merchant.confidence_low",
            status="TRIGGERED",
            confidence=1.0 - merchant_confidence,  # Invert: low confidence = high signal
            evidence={
                "merchant_confidence": round(merchant_confidence, 2),
                "threshold": threshold,
                "below_threshold": True,
            },
            interpretation=f"Merchant confidence below threshold: {merchant_confidence:.2f} < {threshold}",
        )
    
    return SignalV1(
        name="merchant.confidence_low",
        status="NOT_TRIGGERED",
        confidence=merchant_confidence,
        evidence={
            "merchant_confidence": round(merchant_confidence, 2),
            "threshold": threshold,
            "below_threshold": False,
        },
        interpretation=f"Merchant confidence above threshold: {merchant_confidence:.2f} >= {threshold}",
    )
