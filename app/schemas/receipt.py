# app/schemas/receipt.py

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from PIL import Image
from pydantic import BaseModel, Field

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


class SignalV1(BaseModel):
    """
    Unified Signal Contract (v1)
    
    Privacy-safe, confidence-aware signal for fraud detection.
    
    Design Principles:
    - No raw text or PII
    - Confidence-gated (signals suppressed if confidence too low)
    - Structured evidence (machine-readable)
    - Human-readable interpretation
    
    Fields:
    - name: Signal name (e.g., "addr.structure")
    - status: Signal state (TRIGGERED, NOT_TRIGGERED, GATED, UNKNOWN)
    - confidence: Signal confidence [0.0-1.0]
    - evidence: Structured evidence (no PII)
    - interpretation: Human-readable explanation
    - gating_reason: Why signal was gated (if status=GATED)
    """
    name: str = Field(..., description="Signal name (e.g., addr.structure)")
    status: str = Field(..., description="TRIGGERED | NOT_TRIGGERED | GATED | UNKNOWN")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Signal confidence [0.0-1.0]")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Structured evidence (no PII)")
    interpretation: Optional[str] = Field(None, description="Human-readable explanation")
    gating_reason: Optional[str] = Field(None, description="Why signal was gated")


@dataclass(frozen=True)
class SignalSpec:
    """
    Formal specification for a signal in the registry.
    
    Immutable (frozen) to prevent runtime modification.
    """
    name: str
    domain: str
    version: str
    severity: str  # "weak" | "medium" | "strong"
    gated_by: List[str]  # Conditions that gate this signal
    privacy: str  # "safe" | "derived"
    description: str


class SignalRegistry:
    """
    Static registry of all allowed signals for Unified Signal Contract (V1).
    
    Purpose:
    - Contract enforcement (prevents typos like addr.multiAddr)
    - Safer refactors (know exactly what signals exist)
    - ML-feature stability (consistent signal names for learned rules)
    - Clean telemetry joins (no orphaned signal names)
    
    Design:
    - Static in V1 (no dynamic registration)
    - Hard fail on unregistered signals
    - CI-enforced completeness
    - Formal spec with metadata
    
    Invariants enforced:
    - dict_key == signal.name (telemetry joins, ML features)
    - domain prefix (addr.*) (grouping, dashboards)
    - versioned (future migration)
    - known status set (GATED ≠ NOT_TRIGGERED)
    - privacy class (prevents PII leaks)
    """
    
    SIGNALS: Dict[str, SignalSpec] = {
        # Address signals
        "addr.structure": SignalSpec(
            name="addr.structure",
            domain="address",
            version="v1",
            severity="weak",
            gated_by=["doc_profile_confidence"],
            privacy="safe",
            description="Address structure validation (STRONG_ADDRESS, WEAK_ADDRESS, etc.)",
        ),
        "addr.merchant_consistency": SignalSpec(
            name="addr.merchant_consistency",
            domain="address",
            version="v1",
            severity="medium",
            gated_by=["doc_profile_confidence"],
            privacy="safe",
            description="Merchant name and address consistency check",
        ),
        "addr.multi_address": SignalSpec(
            name="addr.multi_address",
            domain="address",
            version="v1",
            severity="medium",
            gated_by=["doc_profile_confidence"],
            privacy="safe",
            description="Multiple distinct addresses detected in document",
        ),
        
        # Amount signals
        "amount.total_mismatch": SignalSpec(
            name="amount.total_mismatch",
            domain="amount",
            version="v1",
            severity="strong",
            gated_by=["doc_profile_confidence"],
            privacy="safe",
            description="Total amount doesn't match line items sum",
        ),
        "amount.missing": SignalSpec(
            name="amount.missing",
            domain="amount",
            version="v1",
            severity="medium",
            gated_by=["doc_profile_confidence"],
            privacy="safe",
            description="Expected total amount is missing",
        ),
        "amount.semantic_override": SignalSpec(
            name="amount.semantic_override",
            domain="amount",
            version="v1",
            severity="weak",
            gated_by=[],
            privacy="safe",
            description="Semantic LLM corrected total amount",
        ),
        
        # Template / PDF signals
        "template.pdf_producer_suspicious": SignalSpec(
            name="template.pdf_producer_suspicious",
            domain="template",
            version="v1",
            severity="weak",
            gated_by=[],
            privacy="safe",
            description="PDF created by suspicious producer (online converter, editor)",
        ),
        "template.quality_low": SignalSpec(
            name="template.quality_low",
            domain="template",
            version="v1",
            severity="weak",
            gated_by=["doc_profile_confidence"],
            privacy="safe",
            description="Document template has poor formatting or structure quality indicators",
        ),
        
        # Merchant signals
        "merchant.extraction_weak": SignalSpec(
            name="merchant.extraction_weak",
            domain="merchant",
            version="v1",
            severity="weak",
            gated_by=["doc_profile_confidence"],
            privacy="safe",
            description="Merchant business entity identification has low confidence or ambiguous results",
        ),
        "merchant.confidence_low": SignalSpec(
            name="merchant.confidence_low",
            domain="merchant",
            version="v1",
            severity="weak",
            gated_by=[],
            privacy="safe",
            description="Merchant extraction confidence below threshold",
        ),
        
        # Date signals
        "date.missing": SignalSpec(
            name="date.missing",
            domain="date",
            version="v1",
            severity="medium",
            gated_by=["doc_profile_confidence"],
            privacy="safe",
            description="Required date field not found in document (invoice date, due date, etc.)",
        ),
        "date.future": SignalSpec(
            name="date.future",
            domain="date",
            version="v1",
            severity="strong",
            gated_by=["doc_profile_confidence"],
            privacy="safe",
            description="Document contains timestamp that occurs after current system time",
        ),
        "date.gap_suspicious": SignalSpec(
            name="date.gap_suspicious",
            domain="date",
            version="v1",
            severity="medium",
            gated_by=["doc_profile_confidence"],
            privacy="safe",
            description="Unusual time interval detected between invoice issuance and payment deadline",
        ),
        
        # OCR signals
        "ocr.confidence_low": SignalSpec(
            name="ocr.confidence_low",
            domain="ocr",
            version="v1",
            severity="weak",
            gated_by=[],
            privacy="safe",
            description="Optical character recognition quality score indicates unreliable text extraction",
        ),
        "ocr.text_sparse": SignalSpec(
            name="ocr.text_sparse",
            domain="ocr",
            version="v1",
            severity="medium",
            gated_by=["doc_profile_confidence"],
            privacy="safe",
            description="Document contains very little extractable content relative to expected volume",
        ),
        "ocr.language_mismatch": SignalSpec(
            name="ocr.language_mismatch",
            domain="ocr",
            version="v1",
            severity="weak",
            gated_by=["doc_profile_confidence"],
            privacy="safe",
            description="Identified document language differs from user-specified or system-expected locale",
        ),
        
        # Language signals
        "language.detection_low_confidence": SignalSpec(
            name="language.detection_low_confidence",
            domain="language",
            version="v1",
            severity="weak",
            gated_by=[],
            privacy="safe",
            description="Automatic language identification algorithm produced uncertain or ambiguous results",
        ),
        "language.script_mismatch": SignalSpec(
            name="language.script_mismatch",
            domain="language",
            version="v1",
            severity="medium",
            gated_by=["doc_profile_confidence"],
            privacy="safe",
            description="Writing system used in document inconsistent with identified spoken language",
        ),
        "language.mixed_scripts": SignalSpec(
            name="language.mixed_scripts",
            domain="language",
            version="v1",
            severity="medium",
            gated_by=["doc_profile_confidence"],
            privacy="safe",
            description="Document contains text in multiple writing systems which may indicate manipulation",
        ),
    }
    
    @classmethod
    def is_allowed(cls, name: str) -> bool:
        """Check if a signal name is registered."""
        return name in cls.SIGNALS
    
    @classmethod
    def get_spec(cls, name: str) -> Optional[SignalSpec]:
        """Get the formal specification for a signal."""
        return cls.SIGNALS.get(name)
    
    @classmethod
    def count(cls) -> int:
        """Return the number of registered signals."""
        return len(cls.SIGNALS)
    
    @classmethod
    def get_by_domain(cls, domain: str) -> List[SignalSpec]:
        """Get all signals for a specific domain."""
        return [spec for spec in cls.SIGNALS.values() if spec.domain == domain]
    
    @classmethod
    def get_all_names(cls) -> List[str]:
        """Get all registered signal names."""
        return list(cls.SIGNALS.keys())


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
    document_intent: Dict[str, Any] = field(default_factory=dict)
    signals: Dict[str, Any] = field(default_factory=dict)  # Unified signals (SignalV1)
    signal_version: str = "v1"  # Signal contract version



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

    # Optional human-grade explanation fields (backward compatible)
    title: Optional[str] = None               # short headline for UI
    why: Optional[str] = None                 # human-grade explanation
    next_step: Optional[str] = None           # suggested follow-up (optional)

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


# --- LearnedRuleAudit: audit trail for feedback-derived (learned) rules ---
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

    # --- Vision / Layout extraction signals (optional) ----------------------
    # Vision is veto-only: can only detect tampering, never upgrade trust.
    # Populate these when available so audits can query vision evidence.
    visual_integrity: Optional[str] = None          # "clean"|"suspicious"|"tampered"
    vision_confidence: Optional[float] = None       # float in [0,1]

    layoutlm_status: Optional[str] = None           # "good"|"bad"|"error"|"n/a"|"unknown"
    layoutlm_confidence: Optional[str] = None       # "low"|"medium"|"high"|"unknown"
    layoutlm_extracted: Optional[Dict[str, Any]] = None  # e.g., {"merchant":...,"total":...,"date":...}

    # --- Corroboration (extraction vs rules) -----------------------------
    # Cross-engine agreement signals (vision is veto-only, not part of corroboration).
    corroboration_score: Optional[float] = None     # float in [0,1] - higher means stronger cross-engine agreement
    corroboration_signals: Optional[Dict[str, Any]] = None  # structured evidence used to compute corroboration_score
    corroboration_flags: Optional[List[str]] = None         # e.g., ["LAYOUT_MISSING_TOTAL"]

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

    # --- Missing-field gating (geo/doc-profile aware) ----------------------
    # When False, we intentionally avoid treating missing totals/dates/merchant/etc as fraud.
    missing_fields_enabled: Optional[bool] = None
    missing_field_gate: Optional[Dict[str, Any]] = None  # structured evidence explaining the gate decision

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
        """Fill decision_id/created_at and normalize internal invariants."""

        # --- Identity / timestamps ---
        if not self.decision_id:
            self.decision_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

        # --- Normalize list fields (never None) ---
        if self.reasons is None:
            self.reasons = []

        if self.minor_notes is None:
            self.minor_notes = []

        if self.events is None:
            self.events = []

        if self.audit_events is None:
            self.audit_events = []

        if self.learned_rule_audits is None:
            self.learned_rule_audits = []

        if self.corroboration_flags is None:
            self.corroboration_flags = []

        # --- Normalize optional dict payloads ---
        # These are allowed to be None, but must never be "missing"
        if self.debug is None:
            self.debug = None

        if self.missing_field_gate is None:
            self.missing_field_gate = None

        if self.corroboration_signals is None:
            self.corroboration_signals = None

        if self.layoutlm_extracted is None:
            self.layoutlm_extracted = None

        if self.input_fingerprint is None:
            self.input_fingerprint = None

        # --- Finalize nested audit events ---
        for e in self.audit_events:
            if hasattr(e, "finalize_defaults"):
                e.finalize_defaults()

    def add_audit_event(self, event: AuditEvent) -> None:
        """Append an AuditEvent to the decision (auto-filling ids/timestamps)."""
        if hasattr(event, "finalize_defaults"):
            event.finalize_defaults()
        self.audit_events.append(event)

    def add_learned_rule_audit(self, audit: LearnedRuleAudit) -> None:
        """Append a LearnedRuleAudit to the decision."""
        self.learned_rule_audits.append(audit)

    def set_missing_field_gate(self, enabled: bool, evidence: Optional[Dict[str, Any]] = None) -> None:
        """Set missing-field penalty gate and its structured evidence."""
        self.missing_fields_enabled = bool(enabled)
        self.missing_field_gate = evidence or None

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict for persistence.
        
        Note: finalize_defaults() enforces all invariants (lists are lists, etc.).
        This method only handles serialization of nested dataclasses.
        """
        self.finalize_defaults()
        d = asdict(self)

        # Serialize nested dataclasses to dicts
        d["audit_events"] = [
            e.to_dict() if hasattr(e, "to_dict") else e
            for e in self.audit_events
        ]
        d["learned_rule_audits"] = [
            a.to_dict() if hasattr(a, "to_dict") else a
            for a in self.learned_rule_audits
        ]

        return d