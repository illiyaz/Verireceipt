# app/pipelines/ingest.py

import os
from typing import List

from pdf2image import convert_from_path
from PIL import Image

from app.schemas.receipt import ReceiptInput, ReceiptRaw
from app.pipelines.metadata import extract_pdf_metadata, extract_image_metadata
from app.pipelines.ocr import run_ocr_on_images


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
PDF_EXTS = {".pdf"}


def _load_images_from_pdf(path: str, dpi: int = 300) -> List[Image.Image]:
    """
    Converts each page of a PDF into a PIL Image.
    Tries pdf2image first (requires poppler), falls back to PyMuPDF if that fails.
    """
    try:
        return convert_from_path(path, dpi=dpi)
    except Exception as e:
        # Fallback to PyMuPDF (fitz) if pdf2image fails
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(path)
            images = []
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                # Render page to pixmap at specified DPI
                zoom = dpi / 72  # 72 is default DPI
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                # Convert to PIL Image
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                images.append(img)
            doc.close()
            return images
        except ImportError:
            raise Exception(
                "Unable to process PDF. Please install either poppler (for pdf2image) "
                "or PyMuPDF (pip install pymupdf). Error: " + str(e)
            )
        except Exception as e2:
            raise Exception(f"Failed to load PDF with both pdf2image and PyMuPDF: {str(e2)}")


def _load_image(path: str) -> Image.Image:
    """
    Loads a single image and normalizes to RGB.
    """
    from PIL import ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True  # Allow truncated/corrupted images
    
    try:
        img = Image.open(path)
        # Load the image data to ensure it's valid
        img.load()
        # Convert to RGB
        return img.convert("RGB")
    except Exception as e:
        print(f"❌ Error loading image {path}: {e}")
        raise


def ingest_receipt(inp: ReceiptInput) -> ReceiptRaw:
    """
    Core ingestion pipeline:
    - loads file
    - converts to 1+ normalized images
    - extracts basic metadata
    - (OCR is done in ingest_and_ocr)
    """
    path = inp.file_path
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    ext = os.path.splitext(path)[1].lower()

    if ext in PDF_EXTS:
        images = _load_images_from_pdf(path)
        pdf_metadata = extract_pdf_metadata(path)
    elif ext in IMAGE_EXTS:
        img = _load_image(path)
        images = [img]
        pdf_metadata = extract_image_metadata(path)
    else:
        raise ValueError(f"Unsupported file extension: {ext}")

    file_size = pdf_metadata.get("file_size_bytes", os.path.getsize(path))

    return ReceiptRaw(
        images=images,
        ocr_text_per_page=[],   # will be filled by ingest_and_ocr
        pdf_metadata=pdf_metadata,
        file_size_bytes=file_size,
        num_pages=len(images),
    )


def ingest_and_ocr(inp: ReceiptInput) -> ReceiptRaw:
    """
    Ingests a receipt and runs OCR, returning a populated ReceiptRaw.
    """
    raw = ingest_receipt(inp)
    ocr_texts = run_ocr_on_images(raw.images)
    raw.ocr_text_per_page = ocr_texts
    return raw