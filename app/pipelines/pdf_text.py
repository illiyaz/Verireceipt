"""
PDF Text Extraction with Quality-Based Fallback

This module implements a robust PDF text extraction chain:
1. Try PyMuPDF (fitz) first for native text extraction
2. Compute quality score based on multiple heuristics
3. Fallback to OCR if quality is too low

Design Goals:
- Avoid OCR failure modes (broken glyphs, letter-splitting)
- Provide quality diagnostics for debugging
- Support seamless fallback to OCR when needed
"""

import re
import logging
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import PyMuPDF
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    logger.warning("PyMuPDF (fitz) not available - will always use OCR fallback")


@dataclass
class TextCorpus:
    """
    Extracted text corpus with quality metrics and diagnostics.
    
    Attributes:
        source: Extraction method used ("pymupdf" | "ocr" | "vision_llm")
        pages: Normalized text per page
        full_text: Concatenated text from all pages
        quality: Quality scores and metrics
        diagnostics: Detailed diagnostics for debugging
    """
    source: str
    pages: List[str]
    full_text: str
    quality: Dict[str, Any]
    diagnostics: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization"""
        return asdict(self)


def _normalize_text(text: str) -> str:
    """
    Normalize text using the same logic as features.py.
    
    - Collapse multiple spaces
    - Normalize newlines
    - Strip leading/trailing whitespace
    """
    if not text:
        return ""
    # Normalize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse multiple spaces (but preserve single spaces)
    text = re.sub(r"[ \t]+", " ", text)
    # Collapse multiple newlines to double newline max
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _compute_quality_score(text: str) -> Dict[str, Any]:
    """
    Compute quality score for extracted text.
    
    Returns dict with:
        - quality_score: float in [0, 1]
        - char_count: int
        - alpha_ratio: float
        - unique_char_ratio: float
        - weird_spacing_ratio: float
        - line_count: int
        - avg_line_len: float
        - digit_ratio: float
        - diagnostics: dict with detailed info
    """
    if not text or not text.strip():
        return {
            "quality_score": 0.0,
            "char_count": 0,
            "alpha_ratio": 0.0,
            "unique_char_ratio": 0.0,
            "weird_spacing_ratio": 0.0,
            "line_count": 0,
            "avg_line_len": 0.0,
            "digit_ratio": 0.0,
            "diagnostics": {"reason": "empty_text"}
        }
    
    # Basic metrics
    char_count = len(text)
    alpha_count = sum(1 for c in text if c.isalpha())
    digit_count = sum(1 for c in text if c.isdigit())
    unique_chars = len(set(text))
    
    alpha_ratio = alpha_count / char_count if char_count > 0 else 0.0
    digit_ratio = digit_count / char_count if char_count > 0 else 0.0
    unique_char_ratio = unique_chars / char_count if char_count > 0 else 0.0
    
    # Line metrics
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    line_count = len(lines)
    avg_line_len = sum(len(line) for line in lines) / line_count if line_count > 0 else 0.0
    
    # Weird spacing detection (e.g., "A r o m a" or many single-letter tokens)
    # Count tokens that are single letters (excluding common ones like "a", "I")
    tokens = text.split()
    single_letter_tokens = [t for t in tokens if len(t) == 1 and t.isalpha() and t.lower() not in ['a', 'i']]
    weird_spacing_ratio = len(single_letter_tokens) / len(tokens) if tokens else 0.0
    
    # Quality score heuristic (0..1)
    # Start with base score
    score = 0.5
    
    # Boost for good characteristics
    if char_count >= 100:
        score += 0.1
    if char_count >= 500:
        score += 0.1
    
    if alpha_ratio >= 0.4:  # Reasonable amount of text
        score += 0.15
    
    if unique_char_ratio >= 0.05:  # Good character diversity
        score += 0.1
    
    if avg_line_len >= 20:  # Reasonable line lengths
        score += 0.1
    
    # Penalize for bad characteristics
    if weird_spacing_ratio > 0.15:  # Too many single letters
        score -= 0.3
    
    if alpha_ratio < 0.2:  # Too few letters
        score -= 0.2
    
    if unique_char_ratio < 0.02:  # Very low diversity
        score -= 0.2
    
    if avg_line_len < 5:  # Very short lines (broken text)
        score -= 0.2
    
    # Clamp to [0, 1]
    score = max(0.0, min(1.0, score))
    
    return {
        "quality_score": score,
        "char_count": char_count,
        "alpha_ratio": alpha_ratio,
        "unique_char_ratio": unique_char_ratio,
        "weird_spacing_ratio": weird_spacing_ratio,
        "line_count": line_count,
        "avg_line_len": avg_line_len,
        "digit_ratio": digit_ratio,
        "diagnostics": {
            "alpha_count": alpha_count,
            "digit_count": digit_count,
            "unique_chars": unique_chars,
            "single_letter_tokens": len(single_letter_tokens),
            "total_tokens": len(tokens)
        }
    }


def _extract_with_pymupdf(pdf_path: str) -> Optional[TextCorpus]:
    """
    Extract text from PDF using PyMuPDF (fitz).
    
    Returns TextCorpus or None if extraction fails.
    """
    if not HAS_PYMUPDF:
        return None
    
    try:
        doc = fitz.open(pdf_path)
        pages = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            normalized = _normalize_text(text)
            pages.append(normalized)
        
        doc.close()
        
        # Concatenate all pages
        full_text = "\n\n".join(pages)
        
        # Compute quality
        quality = _compute_quality_score(full_text)
        
        return TextCorpus(
            source="pymupdf",
            pages=pages,
            full_text=full_text,
            quality=quality,
            diagnostics={
                "method": "pymupdf",
                "page_count": len(pages),
                "pdf_path": str(pdf_path)
            }
        )
    
    except Exception as e:
        logger.warning(f"PyMuPDF extraction failed: {e}")
        return None


def extract_text_corpus(
    pdf_path: str,
    *,
    prefer_pymupdf: bool = True,
    quality_threshold: float = 0.55,
    ocr_fallback_fn: Optional[callable] = None
) -> TextCorpus:
    """
    Extract text from PDF with quality-based fallback.
    
    Strategy:
    1. Try PyMuPDF first (if prefer_pymupdf=True)
    2. Compute quality score
    3. If quality < threshold OR char_count very low, fallback to OCR
    
    Args:
        pdf_path: Path to PDF file
        prefer_pymupdf: Whether to try PyMuPDF first (default: True)
        quality_threshold: Minimum quality score to accept PyMuPDF (default: 0.55)
        ocr_fallback_fn: Optional function to call for OCR fallback
                        Should return (pages: List[str], metadata: dict)
    
    Returns:
        TextCorpus with extracted text and quality metrics
    """
    fallback_reason = None
    
    # Try PyMuPDF first
    if prefer_pymupdf and HAS_PYMUPDF:
        corpus = _extract_with_pymupdf(pdf_path)
        
        if corpus is not None:
            quality_score = corpus.quality["quality_score"]
            char_count = corpus.quality["char_count"]
            
            # Check if quality is acceptable
            if char_count < 50:
                fallback_reason = f"char_count too low ({char_count} < 50)"
            elif quality_score < quality_threshold:
                fallback_reason = f"quality_score too low ({quality_score:.2f} < {quality_threshold})"
            else:
                # Quality is good, use PyMuPDF result
                corpus.diagnostics["fallback_reason"] = None
                corpus.diagnostics["quality_acceptable"] = True
                logger.info(f"PyMuPDF extraction successful (quality={quality_score:.2f}, chars={char_count})")
                return corpus
    else:
        fallback_reason = "pymupdf_not_available" if not HAS_PYMUPDF else "prefer_pymupdf=False"
    
    # Fallback to OCR
    logger.info(f"Falling back to OCR: {fallback_reason}")
    
    if ocr_fallback_fn is not None:
        try:
            pages, metadata = ocr_fallback_fn(pdf_path)
            full_text = "\n\n".join(pages)
            quality = _compute_quality_score(full_text)
            
            return TextCorpus(
                source="ocr",
                pages=pages,
                full_text=full_text,
                quality=quality,
                diagnostics={
                    "method": "ocr",
                    "fallback_reason": fallback_reason,
                    "page_count": len(pages),
                    "pdf_path": str(pdf_path),
                    "ocr_metadata": metadata
                }
            )
        except Exception as e:
            logger.error(f"OCR fallback failed: {e}")
            # Return empty corpus
            return TextCorpus(
                source="ocr",
                pages=[],
                full_text="",
                quality=_compute_quality_score(""),
                diagnostics={
                    "method": "ocr",
                    "fallback_reason": fallback_reason,
                    "error": str(e)
                }
            )
    else:
        # No OCR fallback provided, return empty corpus
        logger.warning("No OCR fallback function provided")
        return TextCorpus(
            source="pymupdf",
            pages=[],
            full_text="",
            quality=_compute_quality_score(""),
            diagnostics={
                "method": "pymupdf",
                "fallback_reason": "no_ocr_fallback",
                "error": "OCR fallback not configured"
            }
        )
