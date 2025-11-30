# app/pipelines/ocr.py
"""
OCR pipeline for VeriReceipt.

We intentionally make this robust in environments where the Tesseract
binary may not be installed (e.g. in a minimal Docker image).

Behavior:
- If pytesseract and the Tesseract binary are available, we run OCR
  on each image and return the recognized text.
- If they are not available, we log a warning and return empty strings
  so that the rest of the pipeline can continue using non-OCR signals
  (metadata, structure, etc.) instead of crashing.
"""

from typing import List
import logging

from PIL import Image

logger = logging.getLogger(__name__)

try:
    import pytesseract
    from pytesseract import TesseractNotFoundError  # type: ignore

    HAS_TESSERACT = True
except Exception:
    # Either pytesseract is not installed, or import failed for some reason.
    pytesseract = None  # type: ignore
    TesseractNotFoundError = Exception  # type: ignore
    HAS_TESSERACT = False


def run_ocr_on_images(images: List[Image.Image]) -> List[str]:
    """
    Runs OCR on each page image and returns a list of strings.

    If Tesseract/pytesseract are not available, this function:
    - logs a warning
    - returns a list of empty strings (one per image)

    This allows the upstream pipeline to continue without OCR,
    instead of failing the entire request.
    """
    texts: List[str] = []

    if not HAS_TESSERACT or pytesseract is None:
        logger.warning(
            "OCR skipped: Tesseract is not available in this environment. "
            "Returning empty OCR results."
        )
        # Preserve the length so callers don't break if they rely on len(images)
        return [""] * len(images)

    for idx, img in enumerate(images):
        try:
            # You can tweak lang / config later
            text = pytesseract.image_to_string(img)
            texts.append(text or "")
        except TesseractNotFoundError:
            logger.warning(
                "OCR failed on image index %d: Tesseract binary not found in PATH.",
                idx,
            )
            texts.append("")
        except Exception as exc:
            logger.warning(
                "OCR error on image index %d: %s. Returning empty text for this page.",
                idx,
                exc,
            )
            texts.append("")

    return texts