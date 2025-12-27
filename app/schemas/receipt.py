# app/schemas/receipt.py

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from PIL import Image

import uuid
from datetime import datetime, timezone


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

    Notes:
    - `event_id` makes events referencable and dedupable.
    - `ts` provides ordering and auditability.
    - `source/type/code/severity/evidence` are stable, machine-friendly fields.
    """

    # Stable identity / ordering
    event_id: str = ""                 # UUID
    ts: str = ""                       # ISO-8601 UTC timestamp

    # Classification
    source: str = ""                   # rule_engine / ensemble / vision_llm / layoutlm / donut ...
    type: str = ""                     # rule_triggered / model_vote / override / normalization ...
    severity: Optional[str] = None      # HARD_FAIL / CRITICAL / WARNING / INFO
    code: Optional[str] = None          # stable id (e.g., R16_SUSPICIOUS_DATE_GAP)

    # Human-facing summary + machine evidence
    message: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    def finalize_defaults(self) -> None:
        """Fill event_id/ts if not already set."""
        if not self.event_id:
            self.event_id = str(uuid.uuid4())
        if not self.ts:
            self.ts = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict for storage/logging."""
        # Ensure defaults are filled even if caller forgot.
        self.finalize_defaults()
        return asdict(self)

@dataclass
class LearnedRuleAudit:
    """
    Structured audit record for feedback-derived (learned) rules.

    Persist this as JSON so we can explain *which learned pattern fired* and
    *what adjustment was applied* in a machine-queryable way.
    """
    pattern: str                         # e.g., "missing_elements", "spacing_anomaly"
    message: str                         # human-readable explanation
    confidence_adjustment: float = 0.0   # signed delta applied by learned rules
    times_seen: Optional[int] = None     # number of times users flagged this pattern
    severity: str = "INFO"              # INFO/WARNING/CRITICAL (kept simple for now)
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

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
    policy_name: str = "default"     # human-friendly policy name (e.g., default/strict)
    policy_notes: Optional[str] = None
    input_fingerprint: Optional[Dict[str, Any]] = None  # sha256/file_size/filename/mime/etc.

    # --- Optional debugging / audit payloads --------------------------------
    features: Optional[ReceiptFeatures] = None
    minor_notes: Optional[List[str]] = None
    debug: Optional[Dict[str, Any]] = None

    # --- Extraction confidence (normalized) ---------------------------------
    # Always prefer these two fields over any ad-hoc text_features["confidence"] usage.
    extraction_confidence_score: Optional[float] = None   # float in [0,1]
    extraction_confidence_level: Optional[str] = None     # "low"|"medium"|"high"

    # --- Geo/Language/Doc-profile tags (normalized, optional) ---------------
    # These are duplicated at the top-level for easier analytics/querying.
    # They should match what is emitted in ENS_DOC_PROFILE_TAGS (ensemble) and
    # what the geo-aware pipeline attaches into text/layout features.
    lang_guess: Optional[str] = None                 # e.g., "en", "es"
    lang_confidence: Optional[float] = None          # float in [0,1]

    geo_country_guess: Optional[str] = None          # e.g., "US", "MX", "IN", "UNKNOWN"
    geo_confidence: Optional[float] = None           # float in [0,1]

    doc_family: Optional[str] = None                 # e.g., "TRANSACTIONAL", "LOGISTICS", "PAYMENT"
    doc_subtype: Optional[str] = None                # e.g., "POS_RESTAURANT", "TAX_INVOICE", "MISC"
    doc_profile_confidence: Optional[float] = None   # float in [0,1]

    # --- Monetary extraction / normalization (optional) ---------------------
    parsed_totals: Optional[List[Dict[str, Any]]] = None  # e.g., [{"label":"total","raw":"$88.89","value":88.89,"confidence":0.95}]
    normalized_total: Optional[float] = None              # single best total chosen after normalization
    currency: Optional[str] = None                        # ISO currency if detected (e.g., USD, KES)

    finalized: bool = True            # indicates decision is final vs draft/partial

    # Primary "why we decided" trail (persist this as JSON)
    audit_events: List[AuditEvent] = field(default_factory=list)

    # Learned-rules (feedback) audit trail (persist this as JSON)
    learned_rule_audits: List[LearnedRuleAudit] = field(default_factory=list)

    # Legacy structured rule events (RuleEvent dicts) - kept for backward compatibility
    events: Optional[List[Dict[str, Any]]] = None

    def finalize_defaults(self) -> None:
        """Fill decision_id/created_at (and audit event ids/timestamps) if missing."""
        if not self.decision_id:
            self.decision_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

        # Finalize nested audit events for persistence
        if self.audit_events:
            for e in self.audit_events:
                if hasattr(e, "finalize_defaults"):
                    e.finalize_defaults()
        # Learned rule audits are plain dataclasses; nothing to finalize, but keep for symmetry
        if self.learned_rule_audits is None:
            self.learned_rule_audits = []

    def add_audit_event(self, event: AuditEvent) -> None:
        """Append an AuditEvent to the decision (auto-filling ids/timestamps)."""
        if hasattr(event, "finalize_defaults"):
            event.finalize_defaults()
        self.audit_events.append(event)
        
    def add_learned_rule_audit(self, audit: LearnedRuleAudit) -> None:
        """Append a LearnedRuleAudit to the decision."""
        self.learned_rule_audits.append(audit)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict for persistence."""
        self.finalize_defaults()
        d = asdict(self)

        # Ensure nested dataclasses remain JSON-friendly
        d["audit_events"] = [
            e.to_dict() if hasattr(e, "to_dict") else e
            for e in (self.audit_events or [])
        ]
        d["learned_rule_audits"] = [
            a.to_dict() if hasattr(a, "to_dict") else a
            for a in (self.learned_rule_audits or [])
        ]
        return d