"""
OCR quality signal wrappers for Unified Signal Contract (V1).

Signals:
- ocr.confidence_low: OCR confidence is below threshold
- ocr.text_sparse: Extracted text is too sparse
- ocr.language_mismatch: Detected language doesn't match expected
"""

from typing import Dict, Any, Optional
from app.schemas.receipt import SignalV1


def signal_ocr_confidence_low(
    ocr_confidence: float,
    threshold: float = 0.7,
) -> SignalV1:
    """
    Convert low OCR confidence to unified signal.
    
    Signal: ocr.confidence_low
    Purpose: Indicates OCR quality issues
    
    Args:
        ocr_confidence: OCR confidence score [0.0-1.0]
        threshold: Confidence threshold (default: 0.7)
    
    Returns:
        SignalV1 with privacy-safe evidence
    """
    if ocr_confidence < threshold:
        return SignalV1(
            name="ocr.confidence_low",
            status="TRIGGERED",
            confidence=1.0 - ocr_confidence,  # Invert: low OCR confidence = high signal confidence
            evidence={
                "ocr_confidence": round(ocr_confidence, 2),
                "threshold": threshold,
                "below_threshold": True,
            },
            interpretation=f"OCR confidence below threshold: {ocr_confidence:.2f} < {threshold}",
        )
    
    return SignalV1(
        name="ocr.confidence_low",
        status="NOT_TRIGGERED",
        confidence=ocr_confidence,
        evidence={
            "ocr_confidence": round(ocr_confidence, 2),
            "threshold": threshold,
            "below_threshold": False,
        },
        interpretation=f"OCR confidence acceptable: {ocr_confidence:.2f} >= {threshold}",
    )


def signal_ocr_text_sparse(
    text_length: int,
    word_count: int,
    doc_profile_confidence: float,
) -> SignalV1:
    """
    Convert sparse text to unified signal.
    
    Signal: ocr.text_sparse
    Purpose: Indicates insufficient text extraction
    
    Args:
        text_length: Length of extracted text
        word_count: Number of words extracted
        doc_profile_confidence: Document confidence
    
    Returns:
        SignalV1 with privacy-safe evidence
    """
    # Gate on confidence
    if doc_profile_confidence < 0.55:
        return SignalV1(
            name="ocr.text_sparse",
            status="GATED",
            confidence=0.0,
            evidence={},
            interpretation="OCR validation gated due to low document confidence",
            gating_reason="doc_profile_confidence < 0.55",
        )
    
    # Thresholds for sparse text
    MIN_TEXT_LENGTH = 50
    MIN_WORD_COUNT = 10
    
    is_sparse = text_length < MIN_TEXT_LENGTH or word_count < MIN_WORD_COUNT
    
    if is_sparse:
        return SignalV1(
            name="ocr.text_sparse",
            status="TRIGGERED",
            confidence=0.8,
            evidence={
                "text_length": text_length,
                "word_count": word_count,
                "min_text_length": MIN_TEXT_LENGTH,
                "min_word_count": MIN_WORD_COUNT,
            },
            interpretation=f"Sparse text detected: {word_count} words, {text_length} chars",
        )
    
    return SignalV1(
        name="ocr.text_sparse",
        status="NOT_TRIGGERED",
        confidence=0.9,
        evidence={
            "text_length": text_length,
            "word_count": word_count,
        },
        interpretation=f"Text extraction sufficient: {word_count} words, {text_length} chars",
    )


def signal_ocr_language_mismatch(
    detected_language: str,
    expected_language: Optional[str],
    language_confidence: float,
    doc_profile_confidence: float,
) -> SignalV1:
    """
    Convert language mismatch to unified signal.
    
    Signal: ocr.language_mismatch
    Purpose: Indicates detected language doesn't match expected
    
    Args:
        detected_language: Detected language code (e.g., "en", "ar")
        expected_language: Expected language code (optional)
        language_confidence: Language detection confidence
        doc_profile_confidence: Document confidence
    
    Returns:
        SignalV1 with privacy-safe evidence
    """
    # Gate on confidence
    if doc_profile_confidence < 0.55:
        return SignalV1(
            name="ocr.language_mismatch",
            status="GATED",
            confidence=0.0,
            evidence={},
            interpretation="Language validation gated due to low document confidence",
            gating_reason="doc_profile_confidence < 0.55",
        )
    
    # If no expected language, can't detect mismatch
    if not expected_language:
        return SignalV1(
            name="ocr.language_mismatch",
            status="NOT_TRIGGERED",
            confidence=0.0,
            evidence={
                "detected_language": detected_language,
                "expected_language": None,
            },
            interpretation="No expected language to compare",
        )
    
    # Check for mismatch
    is_mismatch = detected_language != expected_language
    
    if is_mismatch:
        return SignalV1(
            name="ocr.language_mismatch",
            status="TRIGGERED",
            confidence=language_confidence,
            evidence={
                "detected_language": detected_language,
                "expected_language": expected_language,
                "language_confidence": round(language_confidence, 2),
            },
            interpretation=f"Language mismatch: detected '{detected_language}' but expected '{expected_language}'",
        )
    
    return SignalV1(
        name="ocr.language_mismatch",
        status="NOT_TRIGGERED",
        confidence=language_confidence,
        evidence={
            "detected_language": detected_language,
            "expected_language": expected_language,
            "language_confidence": round(language_confidence, 2),
        },
        interpretation=f"Language matches: {detected_language}",
    )
