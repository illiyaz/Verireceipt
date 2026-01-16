"""
Language signal wrappers for Unified Signal Contract (V1).

Signals:
- language.detection_low_confidence: Language detection confidence is low
- language.script_mismatch: Detected script doesn't match language
- language.mixed_scripts: Multiple scripts detected (potential fraud)
"""

from typing import Dict, Any, Optional, List
from app.schemas.receipt import SignalV1


def signal_language_detection_low_confidence(
    language_confidence: float,
    detected_language: str,
    threshold: float = 0.7,
) -> SignalV1:
    """
    Convert low language detection confidence to unified signal.
    
    Signal: language.detection_low_confidence
    Purpose: Indicates uncertain language detection
    
    Args:
        language_confidence: Language detection confidence [0.0-1.0]
        detected_language: Detected language code
        threshold: Confidence threshold (default: 0.7)
    
    Returns:
        SignalV1 with privacy-safe evidence
    """
    if language_confidence < threshold:
        return SignalV1(
            name="language.detection_low_confidence",
            status="TRIGGERED",
            confidence=1.0 - language_confidence,
            evidence={
                "language_confidence": round(language_confidence, 2),
                "detected_language": detected_language,
                "threshold": threshold,
                "below_threshold": True,
            },
            interpretation=f"Language detection confidence low: {language_confidence:.2f} < {threshold}",
        )
    
    return SignalV1(
        name="language.detection_low_confidence",
        status="NOT_TRIGGERED",
        confidence=language_confidence,
        evidence={
            "language_confidence": round(language_confidence, 2),
            "detected_language": detected_language,
            "threshold": threshold,
            "below_threshold": False,
        },
        interpretation=f"Language detection confident: {language_confidence:.2f} >= {threshold}",
    )


def signal_language_script_mismatch(
    detected_language: str,
    detected_script: str,
    doc_profile_confidence: float,
) -> SignalV1:
    """
    Convert script-language mismatch to unified signal.
    
    Signal: language.script_mismatch
    Purpose: Indicates detected script doesn't match language
    
    Args:
        detected_language: Detected language code (e.g., "ar", "en")
        detected_script: Detected script (e.g., "Arabic", "Latin")
        doc_profile_confidence: Document confidence
    
    Returns:
        SignalV1 with privacy-safe evidence
    """
    # Gate on confidence
    if doc_profile_confidence < 0.55:
        return SignalV1(
            name="language.script_mismatch",
            status="GATED",
            confidence=0.0,
            evidence={},
            interpretation="Script validation gated due to low document confidence",
            gating_reason="doc_profile_confidence < 0.55",
        )
    
    # Expected script mappings
    LANGUAGE_SCRIPT_MAP = {
        "ar": "Arabic",
        "en": "Latin",
        "es": "Latin",
        "fr": "Latin",
        "de": "Latin",
        "zh": "Han",
        "ja": "Han",  # Japanese uses Han (Kanji) + Hiragana + Katakana
        "ko": "Hangul",
        "th": "Thai",
        "vi": "Latin",
        "ms": "Latin",
    }
    
    expected_script = LANGUAGE_SCRIPT_MAP.get(detected_language)
    
    if not expected_script:
        return SignalV1(
            name="language.script_mismatch",
            status="NOT_TRIGGERED",
            confidence=0.0,
            evidence={
                "detected_language": detected_language,
                "detected_script": detected_script,
            },
            interpretation=f"No expected script mapping for language '{detected_language}'",
        )
    
    is_mismatch = detected_script != expected_script
    
    if is_mismatch:
        return SignalV1(
            name="language.script_mismatch",
            status="TRIGGERED",
            confidence=0.7,
            evidence={
                "detected_language": detected_language,
                "detected_script": detected_script,
                "expected_script": expected_script,
            },
            interpretation=f"Script mismatch: detected '{detected_script}' but expected '{expected_script}' for language '{detected_language}'",
        )
    
    return SignalV1(
        name="language.script_mismatch",
        status="NOT_TRIGGERED",
        confidence=0.9,
        evidence={
            "detected_language": detected_language,
            "detected_script": detected_script,
            "expected_script": expected_script,
        },
        interpretation=f"Script matches language: {detected_script} for {detected_language}",
    )


def signal_language_mixed_scripts(
    scripts_detected: List[str],
    script_percentages: Dict[str, float],
    doc_profile_confidence: float,
) -> SignalV1:
    """
    Convert mixed scripts to unified signal.
    
    Signal: language.mixed_scripts
    Purpose: Indicates multiple scripts detected (potential fraud indicator)
    
    Args:
        scripts_detected: List of detected scripts
        script_percentages: Percentage of each script
        doc_profile_confidence: Document confidence
    
    Returns:
        SignalV1 with privacy-safe evidence
    """
    # Gate on confidence
    if doc_profile_confidence < 0.55:
        return SignalV1(
            name="language.mixed_scripts",
            status="GATED",
            confidence=0.0,
            evidence={},
            interpretation="Script validation gated due to low document confidence",
            gating_reason="doc_profile_confidence < 0.55",
        )
    
    # Filter out "Common" (numbers, punctuation) and very small percentages
    significant_scripts = [
        script for script, pct in script_percentages.items()
        if script != "Common" and pct > 0.05  # > 5%
    ]
    
    num_scripts = len(significant_scripts)
    
    # Trigger if multiple significant scripts detected
    if num_scripts > 1:
        # Calculate confidence based on script distribution
        # More balanced distribution = higher confidence in mixed scripts
        max_pct = max(script_percentages.values()) if script_percentages else 0
        confidence = 1.0 - max_pct  # If one script dominates, lower confidence
        
        return SignalV1(
            name="language.mixed_scripts",
            status="TRIGGERED",
            confidence=min(0.8, confidence),
            evidence={
                "num_scripts": num_scripts,
                "scripts": significant_scripts,
                "script_percentages": {k: round(v, 2) for k, v in script_percentages.items()},
            },
            interpretation=f"Multiple scripts detected: {', '.join(significant_scripts)}",
        )
    
    return SignalV1(
        name="language.mixed_scripts",
        status="NOT_TRIGGERED",
        confidence=0.9,
        evidence={
            "num_scripts": num_scripts,
            "scripts": significant_scripts,
        },
        interpretation=f"Single script detected: {significant_scripts[0] if significant_scripts else 'None'}",
    )
