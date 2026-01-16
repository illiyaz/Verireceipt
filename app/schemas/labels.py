"""
Label schema for VeriReceipt ML training.

Frozen schema to prevent label drift and ensure consistency.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field, field_validator
from .receipt import SignalRegistry


class FieldLabel(BaseModel):
    """
    Label for an extracted field.
    
    Used for field-level validation and correction.
    """
    status: Literal["CORRECT", "INCORRECT", "MISSING", "UNCLEAR"] = Field(
        ..., description="Field validation status"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Labeler confidence in this judgment"
    )
    notes: Optional[str] = Field(
        None, description="Optional notes about the field label"
    )


class SignalReview(BaseModel):
    """
    Review of a specific signal's correctness.
    
    Allows annotators to agree/disagree with signal emission.
    """
    agree: bool = Field(
        ..., description="Whether annotator agrees with the signal"
    )
    comment: Optional[str] = Field(
        None, description="Optional comment about the signal"
    )


class AnnotatorJudgment(BaseModel):
    """
    Primary judgment from a human annotator.
    
    Core fraud assessment and evidence evaluation.
    """
    doc_outcome: Literal["GENUINE", "FRAUDULENT", "INCONCLUSIVE"] = Field(
        ..., description="Document classification"
    )
    fraud_types: List[str] = Field(
        default_factory=list, 
        description="Fraud type codes if doc_outcome == FRAUDULENT"
    )
    decision_reasons: List[str] = Field(
        default_factory=list,
        description="Reason codes for the decision"
    )
    evidence_strength: Literal["NONE", "WEAK", "MODERATE", "STRONG"] = Field(
        ..., description="Overall strength of evidence"
    )
    field_labels: Optional[Dict[str, FieldLabel]] = Field(
        None, description="Field-level labels (merchant, amount, date, etc.)"
    )
    signal_reviews: Optional[Dict[str, SignalReview]] = Field(
        None, description="Per-signal agreement reviews"
    )
    notes: Optional[str] = Field(
        None, description="Optional overall notes about the judgment"
    )
    
    @field_validator('fraud_types')
    @classmethod
    def validate_fraud_types(cls, v, info):
        """Fraud types only allowed for FRAUDULENT documents."""
        doc_outcome = info.data.get('doc_outcome')
        if doc_outcome == 'GENUINE' and v:
            raise ValueError("GENUINE documents cannot have fraud_types")
        if doc_outcome == 'FRAUDULENT' and not v:
            raise ValueError("FRAUDULENT documents must have fraud_types")
        return v
    
    @field_validator('decision_reasons')
    @classmethod
    def validate_decision_reasons(cls, v, info):
        """Decision reasons required for FRAUDULENT, optional for others."""
        doc_outcome = info.data.get('doc_outcome')
        if doc_outcome == 'FRAUDULENT' and len(v) < 2:
            raise ValueError("FRAUDULENT documents require ≥2 decision_reasons")
        return v
    
    @field_validator('evidence_strength')
    @classmethod
    def validate_evidence_strength(cls, v, info):
        """Evidence strength constraints by outcome."""
        doc_outcome = info.data.get('doc_outcome')
        if doc_outcome == 'GENUINE' and v not in {'NONE', 'WEAK'}:
            raise ValueError("GENUINE documents must have evidence_strength in {NONE, WEAK}")
        if doc_outcome == 'INCONCLUSIVE' and v == 'NONE':
            raise ValueError("INCONCLUSIVE documents cannot have evidence_strength == NONE")
        return v
    
    @field_validator('signal_reviews')
    @classmethod
    def validate_signal_reviews(cls, v):
        """All signal names must be registered."""
        if v:
            for signal_name in v.keys():
                if not SignalRegistry.is_allowed(signal_name):
                    raise ValueError(f"Signal '{signal_name}' is not registered in SignalRegistry")
        return v


class Adjudication(BaseModel):
    """
    Final adjudication when annotators disagree.
    
    Provides resolution path for conflicting judgments.
    """
    finalized_by: str = Field(
        ..., description="Who finalized the adjudication"
    )
    final_outcome: Literal["GENUINE", "FRAUDULENT", "INCONCLUSIVE"] = Field(
        ..., description="Final document outcome"
    )
    final_fraud_types: List[str] = Field(
        default_factory=list, description="Final fraud type codes"
    )
    final_decision_reasons: List[str] = Field(
        default_factory=list, description="Final decision reason codes"
    )
    final_evidence_strength: Literal["NONE", "WEAK", "MODERATE", "STRONG"] = Field(
        ..., description="Final evidence strength"
    )
    final_notes: Optional[str] = Field(
        None, description="Final adjudication notes"
    )
    
    @field_validator('final_fraud_types')
    @classmethod
    def validate_final_fraud_types(cls, v, info):
        """Final fraud types only for FRAUDULENT."""
        final_outcome = info.data.get('final_outcome')
        if final_outcome == 'GENUINE' and v:
            raise ValueError("GENUINE adjudication cannot have fraud_types")
        if final_outcome == 'FRAUDULENT' and not v:
            raise ValueError("FRAUDULENT adjudication must have fraud_types")
        return v


class DocumentLabelV1(BaseModel):
    """
    Complete label for a single document.
    
    This is the JSONL row format for the training dataset.
    """
    label_version: Literal["v1"] = Field(
        default="v1", description="Label schema version"
    )
    doc_id: str = Field(
        ..., description="Unique document identifier (hash)"
    )
    source_batch: str = Field(
        ..., description="Batch identifier for provenance"
    )
    created_at: datetime = Field(
        ..., description="When this label was created"
    )
    tool_version: Optional[str] = Field(
        None, description="Version of labeling tool used"
    )
    
    # Human judgments
    annotator_judgments: List[AnnotatorJudgment] = Field(
        ..., description="All annotator judgments for this document"
    )
    
    # Optional adjudication
    adjudication: Optional[Adjudication] = Field(
        None, description="Final adjudication if judgments disagree"
    )
    
    # Metadata
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Additional metadata"
    )
    
    @field_validator('annotator_judgments')
    @classmethod
    def validate_judgments(cls, v):
        """At least one annotator judgment required."""
        if not v:
            raise ValueError("At least one annotator judgment is required")
        return v
    
    @field_validator('adjudication')
    @classmethod
    def validate_adjudication(cls, v, info):
        """Adjudication only if multiple judgments disagree."""
        judgments = info.data.get('annotator_judgments', [])
        if len(judgments) <= 1 and v is not None:
            raise ValueError("Adjudication only needed with multiple judgments")
        return v
    
    def get_final_outcome(self) -> str:
        """Get the final outcome (adjudicated or majority)."""
        if self.adjudication:
            return self.adjudication.final_outcome
        
        # Simple majority vote (could be enhanced)
        outcomes = [j.doc_outcome for j in self.annotator_judgments]
        return max(set(outcomes), key=outcomes.count)
    
    def get_final_fraud_types(self) -> List[str]:
        """Get final fraud types."""
        if self.adjudication:
            return self.adjudication.final_fraud_types
        
        # For now, return from first judgment (could be enhanced)
        return self.annotator_judgments[0].fraud_types
    
    def get_final_evidence_strength(self) -> str:
        """Get final evidence strength."""
        if self.adjudication:
            return self.adjudication.final_evidence_strength
        
        # For now, return from first judgment (could be enhanced)
        return self.annotator_judgments[0].evidence_strength


# Fraud type taxonomy (for reference)
FRAUD_TYPES = [
    "FAKE_MERCHANT",      # Non-existent business
    "AMOUNT_MANIPULATION", # Total amount altered
    "DUPLICATE_INVOICE",   # Same invoice submitted multiple times
    "TEMPLATE_FORGERY",    # Fake template/manipulated PDF
    "MULTIPLE_ADDRESS",    # Suspicious multiple addresses
    "FUTURE_DATING",       # Future dates on historical docs
    "LANGUAGE_MISMATCH",   # Language inconsistencies
    "OCR_MANIPULATION",   # Text extraction tampering
    "OTHER",              # Catch-all for other types
]

# Decision reason taxonomy
DECISION_REASONS = [
    "MULTIPLE_ADDRESSES_DETECTED",
    "MERCHANT_ADDRESS_MISMATCH",
    "AMOUNT_TOTAL_MISMATCH",
    "AMOUNT_MISSING",
    "FUTURE_DATE_DETECTED",
    "TEMPLATE_QUALITY_POOR",
    "PDF_PRODUCER_SUSPICIOUS",
    "OCR_CONFIDENCE_LOW",
    "LANGUAGE_INCONSISTENT",
    "MERCHANT_EXTRACTION_WEAK",
    "EVIDENCE_INSUFFICIENT",
    "DOCUMENT_AMBIGUOUS",
    "OTHER",
]
