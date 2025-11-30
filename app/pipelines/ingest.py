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
    """
    return convert_from_path(path, dpi=dpi)


def _load_image(path: str) -> Image.Image:
    """
    Loads a single image and normalizes to RGB.
    """
    return Image.open(path).convert("RGB")


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