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

from typing import List, Dict, Tuple
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


def _run_easyocr(img: Image.Image) -> tuple[str, float, list]:
    """
    Run EasyOCR on a single image with confidence scoring.
    
    Returns:
        (text, avg_confidence, detailed_results)
    """
    try:
        reader = _get_easyocr_reader()
        # Convert PIL to numpy array
        img_array = np.array(img)
        # Run OCR with detail=1 to get confidence scores
        results = reader.readtext(img_array, detail=1)
        
        if not results:
            return "", 0.0, []
        
        # Extract text and confidence
        text_blocks = []
        confidences = []
        detailed = []
        
        for (bbox, text, conf) in results:
            text_blocks.append(text)
            confidences.append(conf)
            detailed.append({
                "text": text,
                "confidence": conf,
                "bbox": bbox
            })
        
        # Join all text blocks with newlines
        full_text = '\n'.join(text_blocks)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        return full_text, avg_confidence, detailed
    except Exception as e:
        logger.warning(f"EasyOCR failed: {e}")
        return "", 0.0, []


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


def run_ocr_on_images(images: List[Image.Image], preprocess: bool = True) -> Tuple[List[str], Dict]:
    """
    Run OCR on a list of images with preprocessing and confidence scoring.
    
    Automatically selects best available OCR engine:
    1. EasyOCR (if available)
    2. Tesseract (fallback)
    3. Empty strings (if no OCR available)
    
    Args:
        images: List of PIL Images
        preprocess: Apply image preprocessing for better OCR quality
    
    Returns:
        (ocr_texts, ocr_metadata)
        ocr_metadata contains confidence scores and preprocessing info
    """
    if not images:
        return [], {}
    
    # Import preprocessing if needed
    if preprocess:
        try:
            from app.pipelines.image_preprocessing import preprocess_batch
            images_processed, preprocessing_meta = preprocess_batch(images, auto_detect=True)
            logger.info(f"✅ Image preprocessing applied to {len(images)} images")
        except ImportError as e:
            logger.warning(f"⚠️ Image preprocessing not available: {e}. Using original images.")
            images_processed = images
            preprocessing_meta = [{}] * len(images)
        except Exception as e:
            logger.error(f"❌ Image preprocessing failed: {e}. Using original images.")
            images_processed = images
            preprocessing_meta = [{}] * len(images)
    else:
        images_processed = images
        preprocessing_meta = [{}] * len(images)
    
    # Determine which engine to use
    use_easyocr = HAS_EASYOCR and OCR_ENGINE in ["auto", "easyocr"]
    use_tesseract = HAS_TESSERACT and (OCR_ENGINE == "tesseract" or (OCR_ENGINE == "auto" and not use_easyocr))
    
    if not use_easyocr and not use_tesseract:
        logger.warning("⚠️ No OCR engine available. Install easyocr or pytesseract.")
        return [""] * len(images), {"engine": "none", "confidences": [0.0] * len(images)}
    
    results = []
    confidences = []
    detailed_results = []
    
    for i, img in enumerate(images_processed):
        logger.info(f"Running OCR on image {i+1}/{len(images)}...")
        
        if use_easyocr:
            text, conf, detailed = _run_easyocr(img)
            engine = "easyocr"
        elif use_tesseract:
            text = _run_tesseract(img)
            conf = None  # Tesseract doesn't provide confidence - use None not 0.0
            detailed = []
            engine = "tesseract"
        else:
            text = ""
            conf = None  # OCR not available - use None not 0.0
            detailed = []
            engine = "none"
        
        results.append(text)
        confidences.append(conf)
        detailed_results.append(detailed)
        conf_str = f"{conf:.2f}" if conf is not None else "N/A"
        logger.info(f"✅ OCR completed for image {i+1} ({len(text)} chars, conf={conf_str})")
    
    # Calculate average confidence, filtering out None values
    valid_confidences = [c for c in confidences if c is not None]
    avg_confidence = sum(valid_confidences) / len(valid_confidences) if valid_confidences else None
    
    ocr_metadata = {
        "engine": engine,
        "confidences": confidences,
        "avg_confidence": avg_confidence,
        "preprocessing": preprocessing_meta,
        "detailed_results": detailed_results,
    }
    
    return results, ocr_metadata