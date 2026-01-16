"""
Signal wrappers for template/PDF quality features.

Converts template and PDF metadata features to unified SignalV1 contract.
"""

from typing import Dict, Any
from app.schemas.receipt import SignalV1


def signal_pdf_producer_suspicious(
    pdf_metadata: Dict[str, Any],
    suspicious_producer: bool,
) -> SignalV1:
    """
    Convert suspicious PDF producer to unified signal.
    
    Signal: template.pdf_producer_suspicious
    Purpose: Indicates PDF created by suspicious tool
    
    Args:
        pdf_metadata: PDF metadata dict
        suspicious_producer: Whether producer is flagged
    
    Returns:
        SignalV1 with privacy-safe evidence
    """
    producer = pdf_metadata.get("Producer", "")
    creator = pdf_metadata.get("Creator", "")
    
    if suspicious_producer:
        return SignalV1(
            status="TRIGGERED",
            confidence=0.6,  # Medium confidence - producer alone isn't definitive
            evidence={
                "producer_flagged": True,
                "producer_hint": producer[:50] if producer else None,  # Truncated
                "creator_hint": creator[:50] if creator else None,
            },
            interpretation="PDF created by suspicious producer (e.g., online converter, editor)",
        )
    
    return SignalV1(
        status="NOT_TRIGGERED",
        confidence=0.8,
        evidence={
            "producer_flagged": False,
        },
        interpretation="PDF producer appears legitimate",
    )


def signal_template_quality_low(
    template_quality: Dict[str, Any],
    doc_profile_confidence: float,
) -> SignalV1:
    """
    Convert template quality to unified signal.
    
    Signal: template.quality_low
    Purpose: Indicates poor template quality (OCR noise, layout issues)
    
    Args:
        template_quality: Template quality assessment
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
            interpretation="Template quality check gated due to low document confidence",
            gating_reason="doc_profile_confidence < 0.55",
        )
    
    quality_score = template_quality.get("quality_score", 1.0)
    issues = template_quality.get("issues", [])
    
    # Trigger if quality score is low (< 0.6)
    if quality_score < 0.6:
        return SignalV1(
            status="TRIGGERED",
            confidence=0.7,
            evidence={
                "quality_score": round(quality_score, 2),
                "issues": issues,
                "issue_count": len(issues),
            },
            interpretation=f"Low template quality detected (score: {quality_score:.2f})",
        )
    
    return SignalV1(
        status="NOT_TRIGGERED",
        confidence=0.8,
        evidence={
            "quality_score": round(quality_score, 2),
        },
        interpretation=f"Template quality acceptable (score: {quality_score:.2f})",
    )
