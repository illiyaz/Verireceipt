# app/pipelines/ocr.py
"""
OCR pipeline for VeriReceipt.

Supports multiple OCR engines with automatic fallback:
1. EasyOCR (best accuracy, ~85-90%)
2. Tesseract (fallback, ~60-70%)
3. Empty strings (if no OCR available)

This allows the pipeline to continue even without OCR,
using other signals (metadata, structure, etc.).
"""

from typing import List
import logging
import os

from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)

# Try to import EasyOCR (better accuracy)
try:
    import easyocr
    HAS_EASYOCR = True
    _easyocr_reader = None  # Lazy load
except ImportError:
    easyocr = None
    HAS_EASYOCR = False
    _easyocr_reader = None

# Try to import Tesseract (fallback)
try:
    import pytesseract
    from pytesseract import TesseractNotFoundError  # type: ignore
    HAS_TESSERACT = True
except Exception:
    pytesseract = None  # type: ignore
    TesseractNotFoundError = Exception  # type: ignore
    HAS_TESSERACT = False

# Check environment variable for OCR preference
OCR_ENGINE = os.getenv("OCR_ENGINE", "auto")  # auto, easyocr, tesseract


def _get_easyocr_reader():
    """Lazy load EasyOCR reader (downloads models on first use)"""
    global _easyocr_reader
    if _easyocr_reader is None:
        logger.info("Loading EasyOCR reader (first time may download ~500MB models)...")
        _easyocr_reader = easyocr.Reader(['en'], gpu=False)  # Use GPU=True if available
        logger.info("✅ EasyOCR reader loaded")
    return _easyocr_reader


def _run_easyocr(img: Image.Image) -> str:
    """Run EasyOCR on a single image"""
    try:
        reader = _get_easyocr_reader()
        # Convert PIL to numpy array
        img_array = np.array(img)
        # Run OCR
        results = reader.readtext(img_array, detail=0)  # detail=0 returns just text
        # Join all text blocks with newlines
        text = '\n'.join(results)
        return text
    except Exception as e:
        logger.warning(f"EasyOCR failed: {e}")
        return ""


def _run_tesseract(img: Image.Image) -> str:
    """Run Tesseract OCR on a single image"""
    try:
        text = pytesseract.image_to_string(img)
        return text or ""
    except TesseractNotFoundError:
        logger.warning("Tesseract binary not found in PATH")
        return ""
    except Exception as e:
        logger.warning(f"Tesseract error: {e}")
        return ""


def run_ocr_on_images(images: List[Image.Image]) -> List[str]:
    """
    Runs OCR on each page image and returns a list of strings.
    
    OCR Engine Selection (priority order):
    1. EasyOCR (if available and OCR_ENGINE != 'tesseract')
    2. Tesseract (fallback or if OCR_ENGINE == 'tesseract')
    3. Empty strings (if no OCR available)
    
    Environment Variables:
    - OCR_ENGINE: 'auto' (default), 'easyocr', 'tesseract'
    
    Returns:
        List of OCR text strings (one per image)
    """
    texts: List[str] = []
    
    # Determine which OCR engine to use
    use_easyocr = False
    use_tesseract = False
    
    if OCR_ENGINE == "easyocr" and HAS_EASYOCR:
        use_easyocr = True
        logger.info("Using EasyOCR (forced by OCR_ENGINE=easyocr)")
    elif OCR_ENGINE == "tesseract" and HAS_TESSERACT:
        use_tesseract = True
        logger.info("Using Tesseract (forced by OCR_ENGINE=tesseract)")
    elif OCR_ENGINE == "auto":
        # Auto-select: prefer EasyOCR if available
        if HAS_EASYOCR:
            use_easyocr = True
            logger.info("Using EasyOCR (auto-selected, better accuracy)")
        elif HAS_TESSERACT:
            use_tesseract = True
            logger.info("Using Tesseract (auto-selected, EasyOCR not available)")
    
    # If no OCR available, return empty strings
    if not use_easyocr and not use_tesseract:
        logger.warning(
            "OCR skipped: No OCR engine available. "
            "Install easyocr (pip install easyocr) or tesseract. "
            "Returning empty OCR results."
        )
        return [""] * len(images)
    
    # Run OCR on each image
    for idx, img in enumerate(images):
        if use_easyocr:
            text = _run_easyocr(img)
        else:
            text = _run_tesseract(img)
        
        texts.append(text)
        
        if text:
            logger.debug(f"OCR extracted {len(text)} characters from image {idx}")
        else:
            logger.warning(f"OCR returned empty text for image {idx}")
    
    return texts