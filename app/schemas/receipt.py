# app/schemas/receipt.py

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from PIL import Image


@dataclass
class ReceiptInput:
    """
    Input to the VeriReceipt engine.
    For now we assume we get a file path on disk.
    Later this can be extended for bytes/streams.
    """
    file_path: str


@dataclass
class ReceiptRaw:
    """
    Raw extracted content from the uploaded file.
    - images: list of page images (PDF → multiple, image → single)
    - ocr_text_per_page: plain OCR text, same length as images
    - pdf_metadata: metadata for PDF or image/FS metadata
    """
    images: List[Image.Image]
    ocr_text_per_page: List[str]
    pdf_metadata: Dict[str, Any]
    file_size_bytes: int
    num_pages: int


@dataclass
class ReceiptFeatures:
    """
    Engineered features we will compute from ReceiptRaw.
    These feed into rules / ML models.
    """
    file_features: Dict[str, Any]
    text_features: Dict[str, Any]
    layout_features: Dict[str, Any]
    forensic_features: Dict[str, Any]


@dataclass
class ReceiptDecision:
    """
    Final decision returned by VeriReceipt.
    """
    label: str                      # "real", "fake", "suspicious"
    score: float                    # 0.0 - 1.0
    reasons: List[str]              # human-readable explanations

    # --- Audit / explainability metadata ------------------------------------
    rule_version: str = "0.0.0"     # Ruleset version used for this verdict
    engine_version: str = "0.0.0"   # App/build version (optional but useful)

    # --- Optional debugging payloads ----------------------------------------
    features: Optional[ReceiptFeatures] = None  # optional, for debugging/analytics
    minor_notes: Optional[List[str]] = None
    debug: Optional[Dict[str, Any]] = None      # structured metadata (model scores, geo/currency, etc.)