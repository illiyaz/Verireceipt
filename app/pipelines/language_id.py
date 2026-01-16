"""
Deterministic Language Identification Module

This module provides robust, confidence-aware language detection for OCR text.
Uses fastText lid.176.bin for deterministic, offline language identification.

Key Features:
- Works on short OCR text
- Handles mixed-language receipts
- Never pollutes downstream rules with false confidence
- "mixed" is a first-class state

Design Principles:
- Deterministic (no LLM)
- Confidence-aware (gates downstream rules)
- OCR-noise resistant (preprocessing)
- Short-text safe (minimum length requirements)
"""

import logging
import unicodedata
from typing import Dict, Optional, Tuple, List
from pathlib import Path

logger = logging.getLogger(__name__)

# fastText model will be lazy-loaded
_FASTTEXT_MODEL = None
_MODEL_PATH = Path(__file__).parent.parent.parent / "resources" / "models" / "lid.176.bin"

# -----------------------------------------------------------------------------
# Script-aware detection (language-agnostic pre-gate)
# -----------------------------------------------------------------------------

_MIN_SCRIPT_ALPHA_CHARS = 30
_DOMINANT_SCRIPT_RATIO = 0.60

_SCRIPT_BUCKETS = (
    "latin",
    "arabic",
    "cyrillic",
    "han",
    "hiragana",
    "katakana",
    "hangul",
    "hebrew",
)

def _script_bucket(ch: str) -> str:
    o = ord(ch)
    if (0x0600 <= o <= 0x06FF) or (0x0750 <= o <= 0x077F) or (0x08A0 <= o <= 0x08FF):
        return "arabic"
    if 0x0590 <= o <= 0x05FF:
        return "hebrew"
    if (0x0400 <= o <= 0x04FF) or (0x0500 <= o <= 0x052F):
        return "cyrillic"
    if (0x4E00 <= o <= 0x9FFF) or (0x3400 <= o <= 0x4DBF):
        return "han"
    if 0x3040 <= o <= 0x309F:
        return "hiragana"
    if 0x30A0 <= o <= 0x30FF:
        return "katakana"
    if (0xAC00 <= o <= 0xD7AF) or (0x1100 <= o <= 0x11FF):
        return "hangul"
    if (0x0041 <= o <= 0x007A) or (0x00C0 <= o <= 0x024F):
        return "latin"
    return "other"

def _script_stats(text: str) -> Dict[str, float]:
    counts = {k: 0 for k in _SCRIPT_BUCKETS}
    counts["other"] = 0
    alpha_total = 0

    for ch in text:
        if not ch.isalpha():
            continue
        alpha_total += 1
        b = _script_bucket(ch)
        counts[b] = counts.get(b, 0) + 1

    if alpha_total <= 0:
        return {"alpha_total": 0, "dominant": "other", "dominant_ratio": 0.0, "ratios": {}}

    ratios = {k: (v / float(alpha_total)) for k, v in counts.items()}
    dominant = max(ratios.items(), key=lambda kv: kv[1])[0]
    return {
        "alpha_total": alpha_total,
        "dominant": dominant,
        "dominant_ratio": float(ratios[dominant]),
        "ratios": ratios,
    }

def _script_to_lang_hint(script: str, ratios: Dict[str, float]) -> Optional[str]:
    if script == "arabic":
        return "ar"
    if script == "hebrew":
        return "he"
    if script == "cyrillic":
        return "ru"
    if script == "hangul":
        return "ko"
    if script in ("hiragana", "katakana"):
        return "ja"
    if script == "han":
        kana_ratio = float(ratios.get("hiragana", 0.0) + ratios.get("katakana", 0.0))
        return "ja" if kana_ratio >= 0.02 else "zh"
    return None

def _script_based_language(text: str) -> Tuple[Optional[str], float]:
    st = _script_stats(text)

    if st["alpha_total"] < _MIN_SCRIPT_ALPHA_CHARS:
        return None, 0.0

    if st["dominant_ratio"] < _DOMINANT_SCRIPT_RATIO:
        return None, float(st["dominant_ratio"])

    if st["dominant"] == "latin":
        return None, float(st["dominant_ratio"])

    hint = _script_to_lang_hint(st["dominant"], st["ratios"])
    return (hint, float(st["dominant_ratio"])) if hint else (None, 0.0)


def _load_fasttext_model():
    """
    Lazy-load fastText language identification model.
    
    Returns:
        fastText model or None if unavailable
    """
    global _FASTTEXT_MODEL
    
    if _FASTTEXT_MODEL is not None:
        return _FASTTEXT_MODEL
    
    try:
        import fasttext
        # ------------------------------------------------------------------
        # NumPy 2.x compatibility patch for fasttext-wheel
        #
        # fasttext-wheel internally calls np.array(..., copy=False) which
        # raises ValueError under NumPy >= 2.0. We patch fasttext's local
        # numpy reference to safely fall back to np.asarray().
        # ------------------------------------------------------------------
        try:
            import numpy as _np
            import fasttext.FastText as _FT

            _orig_array = _FT.np.array

            def _patched_array(obj, *args, **kwargs):
                if kwargs.get("copy") is False:
                    try:
                        return _orig_array(obj, *args, **kwargs)
                    except ValueError:
                        return _np.asarray(obj)
                return _orig_array(obj, *args, **kwargs)

            _FT.np.array = _patched_array
        except Exception:
            pass

        if not _MODEL_PATH.exists():
            logger.warning(f"fastText model not found at {_MODEL_PATH}")
            logger.warning("Language detection will fall back to 'mixed' state")
            return None
        
        # Suppress fastText warnings
        fasttext.FastText.eprint = lambda x: None
        
        _FASTTEXT_MODEL = fasttext.load_model(str(_MODEL_PATH))
        logger.info(f"fastText language model loaded from {_MODEL_PATH}")
        return _FASTTEXT_MODEL
    
    except ImportError:
        logger.warning("fastText not installed. Install with: pip install fasttext-wheel")
        return None
    except Exception as e:
        logger.error(f"Failed to load fastText model: {e}")
        return None


def extract_language_text(text_lines: List[str]) -> str:
    """
    Preprocess OCR text for language identification.
    
    Filters out:
    - Numeric-only lines (prices, totals)
    - Very short lines (< 4 chars)
    - Lines with low alphabetic ratio (< 30%)
    
    Keeps:
    - Headers, labels, descriptions
    - Merchant names
    - Product descriptions
    
    Args:
        text_lines: List of OCR text lines
    
    Returns:
        Cleaned text suitable for language detection (max 2000 chars)
    """
    if not text_lines:
        return ""
    
    clean = []
    
    for line in text_lines:
        # Skip empty or very short lines
        if not line or len(line) < 4:
            continue
        
        # Calculate alphabetic ratio
        alpha_count = sum(c.isalpha() for c in line)
        alpha_ratio = alpha_count / max(len(line), 1)
        
        # Skip lines with low alphabetic content (likely prices/numbers)
        if alpha_ratio < 0.25:
            continue
        
        clean.append(line)
    
    # Join and cap at 2000 chars (fastText works best on shorter text)
    joined = " ".join(clean)
    return joined[:2000]


def detect_language(text: str, min_confidence: float = 0.40) -> Tuple[str, float]:
    """
    Detect language using fastText with receipt-aware gating.
    """

    # Defensive
    if not text:
        return "mixed", 0.0

    # Receipt-aware gating
    words = text.split()
    char_len = len(text)

    # Rules:
    # - Require semantic density (>= 6 words)
    # - Require minimum signal length (>= 60 chars)
    if len(words) < 6 or char_len < 60:
        return "mixed", 0.0

    # ---- Script-based pre-detection (language-agnostic) ----
    script_lang, script_conf = _script_based_language(text)
    if script_lang and script_conf >= 0.85:
        return script_lang, script_conf

    model = _load_fasttext_model()
    if model is None:
        return "mixed", 0.0

    try:
        labels, probs = model.predict(text.replace("\n", " "), k=1)

        if not labels or not probs:
            return "mixed", 0.0

        lang_code = labels[0].replace("__label__", "")
        confidence = float(probs[0])

        if confidence < min_confidence:
            return "mixed", confidence

        return lang_code, confidence

    except Exception as e:
        logger.error(f"Language detection failed: {e}")
        return "mixed", 0.0


def identify_language(text_lines: List[str]) -> Dict[str, any]:
    """
    Full language identification pipeline.
    
    Steps:
    1. Preprocess text (filter OCR noise)
    2. Detect language with confidence
    3. Return structured result
    
    Args:
        text_lines: List of OCR text lines
    
    Returns:
        {
            "lang": "en" | "es" | "zh" | "mixed",
            "lang_confidence": 0.0 - 1.0,
            "lang_source": "fasttext",
            "text_length": int,
            "lines_used": int
        }
    """
    # Preprocess text
    clean_text = extract_language_text(text_lines)
    
    # Detect language
    lang_code, confidence = detect_language(clean_text)
    
    return {
        "lang": lang_code,
        "lang_confidence": confidence,
        "lang_source": "fasttext",
        "text_length": len(clean_text),
        "lines_used": len([line for line in text_lines if line and len(line) >= 4]),
    }


def get_language_from_features(tf: Dict, lf: Dict) -> Dict[str, any]:
    """
    Extract language information from feature dictionaries.
    
    Tries multiple sources in order:
    1. Existing lang_guess/lang_confidence (if present)
    2. text_lines from tf
    3. lines from lf
    4. Fallback to "mixed"
    
    Args:
        tf: Text features dictionary
        lf: Layout features dictionary
    
    Returns:
        Language identification result
    """
    # Check if language already detected
    if tf.get("lang_guess") and tf.get("lang_confidence"):
        return {
            "lang": tf.get("lang_guess"),
            "lang_confidence": float(tf.get("lang_confidence", 0.0)),
            "lang_source": tf.get("lang_source", "unknown"),
            "text_length": 0,
            "lines_used": 0,
        }
    
    # Try to get text lines
    text_lines = tf.get("text_lines") or lf.get("lines") or []
    
    if not text_lines:
        # No text available
        return {
            "lang": "mixed",
            "lang_confidence": 0.0,
            "lang_source": "fallback",
            "text_length": 0,
            "lines_used": 0,
        }
    
    # Run language identification
    return identify_language(text_lines)
