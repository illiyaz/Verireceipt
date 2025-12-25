# app/schemas/receipt.py

from dataclasses import dataclass, field
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
class AuditEvent:
    """
    Append-only, structured explanation for *why* a decision was made.
    Persist this as JSON for audit/debug/analytics.
    """
    source: str                    # rule_engine / ensemble / vision_llm / layoutlm / donut ...
    type: str                      # rule_triggered / model_vote / override / normalization ...
    severity: Optional[str] = None # HARD_FAIL / CRITICAL / WARNING / INFO
    code: Optional[str] = None     # stable id (e.g., R16_SUSPICIOUS_DATE_GAP)
    message: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReceiptDecision:
    """
    Final decision returned by VeriReceipt.

    - reasons: user-facing summary strings
    - audit_events: structured, persisted "why we decided" trail (preferred)
    - events: legacy structured rule events (dicts) kept for compatibility
    """
    label: str
    score: float
    reasons: List[str]

    # --- Versioning / policy metadata ---------------------------------------
    rule_version: str = "0.0.0"       # Ruleset version used for this verdict
    policy_version: str = "0.0.0"     # Ensemble/conflict-resolution policy version used
    engine_version: str = "0.0.0"     # App/build version (optional but useful)

    # --- Decision identity / provenance -------------------------------------
    decision_id: str = ""             # UUID or stable id set by API layer
    created_at: str = ""              # ISO-8601 timestamp set by API layer
    input_fingerprint: Optional[Dict[str, Any]] = None  # sha256/file_size/filename/mime/etc.

    # --- Optional debugging / audit payloads --------------------------------
    features: Optional[ReceiptFeatures] = None
    minor_notes: Optional[List[str]] = None
    debug: Optional[Dict[str, Any]] = None

    # Primary "why we decided" trail (persist this)
    audit_events: List[AuditEvent] = field(default_factory=list)

    # Legacy structured rule events (RuleEvent dicts) - kept for backward compatibility
    events: Optional[List[Dict[str, Any]]] = None