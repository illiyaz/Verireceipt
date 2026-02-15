# app/pipelines/ocr.py
"""
OCR pipeline for VeriReceipt.

Supports multiple OCR engines with automatic fallback:
1. Tesseract (best accuracy on thermal/POS receipts, ~90%+)
2. EasyOCR (fallback for non-Latin scripts)
3. Empty strings (if no OCR available)

Benchmark (Popeyes POS receipt, Feb 2026):
- Tesseract: 8/10 accuracy, ~1s latency
- EasyOCR:   1/10 accuracy, ~2s latency ($ -> S, garbled amounts)

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


def _run_tesseract(img: Image.Image) -> tuple:
    """
    Run Tesseract OCR on a single image with confidence scoring.
    
    Returns:
        (text, avg_confidence, detailed_results)
    """
    try:
        # Get full text
        text = pytesseract.image_to_string(img)
        if not text:
            return "", 0.0, []
        
        # Get per-word confidence via image_to_data
        try:
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            word_confs = [int(c) for c in data.get("conf", []) if int(c) >= 0]
            avg_conf = (sum(word_confs) / len(word_confs) / 100.0) if word_confs else 0.5
            
            # Build detailed results with bounding boxes
            detailed = []
            for i in range(len(data.get("text", []))):
                word = data["text"][i].strip()
                conf = int(data["conf"][i])
                if word and conf >= 0:
                    detailed.append({
                        "text": word,
                        "confidence": conf / 100.0,
                        "bbox": [data["left"][i], data["top"][i],
                                  data["left"][i] + data["width"][i],
                                  data["top"][i] + data["height"][i]],
                    })
        except Exception:
            avg_conf = 0.5
            detailed = []
        
        return text, avg_conf, detailed
    except TesseractNotFoundError:
        logger.warning("Tesseract binary not found in PATH")
        return "", 0.0, []
    except Exception as e:
        logger.warning(f"Tesseract error: {e}")
        return "", 0.0, []


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
    
    # Determine which engine to use (Tesseract preferred since Feb 2026 benchmark)
    use_tesseract = HAS_TESSERACT and OCR_ENGINE in ["auto", "tesseract"]
    use_easyocr = HAS_EASYOCR and (OCR_ENGINE == "easyocr" or (OCR_ENGINE == "auto" and not use_tesseract))
    
    if not use_tesseract and not use_easyocr:
        logger.warning("No OCR engine available. Install pytesseract or easyocr.")
        return [""] * len(images), {"engine": "none", "confidences": [0.0] * len(images)}
    
    results = []
    confidences = []
    detailed_results = []
    
    for i, img in enumerate(images):
        logger.info(f"Running OCR on image {i+1}/{len(images)}...")
        
        if use_tesseract:
            # Strategy: try Tesseract on ORIGINAL image first (preprocessing
            # can degrade Tesseract output on clean images). Only retry with
            # preprocessed image if confidence is low.
            text, conf, detailed = _run_tesseract(img)
            engine = "tesseract"
            
            # If confidence is low and we have a preprocessed version, retry
            if conf < 0.5 and i < len(images_processed) and images_processed[i] is not img:
                text_pp, conf_pp, detailed_pp = _run_tesseract(images_processed[i])
                if conf_pp > conf and len(text_pp) >= len(text) * 0.8:
                    logger.info(f"Preprocessed image gave better Tesseract result ({conf_pp:.2f} vs {conf:.2f})")
                    text, conf, detailed = text_pp, conf_pp, detailed_pp
                    engine = "tesseract+preprocess"
        elif use_easyocr:
            # EasyOCR benefits from preprocessing, use preprocessed image
            img_for_ocr = images_processed[i] if i < len(images_processed) else img
            text, conf, detailed = _run_easyocr(img_for_ocr)
            engine = "easyocr"
        else:
            text = ""
            conf = None
            detailed = []
            engine = "none"
        
        results.append(text)
        confidences.append(conf)
        detailed_results.append(detailed)
        conf_str = f"{conf:.2f}" if conf is not None else "N/A"
        logger.info(f"OCR completed for image {i+1} ({engine}, {len(text)} chars, conf={conf_str})")
    
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