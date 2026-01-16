"""
Adapter to convert legacy feedback to LabelV1 schema.

Bridges existing feedback system with new ML-ready label schema.
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pathlib import Path
import hashlib

from app.models.feedback import ReceiptFeedback, CorrectVerdict
from app.schemas.labels import (
    DocumentLabelV1,
    AnnotatorJudgment,
    FRAUD_TYPES,
    DECISION_REASONS
)


class FeedbackToLabelAdapter:
    """Converts legacy feedback to structured LabelV1 format."""
    
    # Mapping from legacy verdicts to new outcomes
    VERDICT_MAPPING = {
        "real": "GENUINE",
        "suspicious": "INCONCLUSIVE",
        "fake": "FRAUDULENT",
        "uncertain": "INCONCLUSIVE"
    }
    
    # Mapping from legacy verdicts to evidence strength
    EVIDENCE_MAPPING = {
        "real": "WEAK",
        "suspicious": "MODERATE",
        "fake": "STRONG",
        "uncertain": "WEAK"
    }
    
    def __init__(self):
        pass
    
    def convert_feedback_to_label(
        self,
        feedback: ReceiptFeedback,
        doc_id: Optional[str] = None
    ) -> DocumentLabelV1:
        """
        Convert legacy ReceiptFeedback to DocumentLabelV1.
        
        Args:
            feedback: Legacy feedback object
            doc_id: Document ID (generated if not provided)
        
        Returns:
            DocumentLabelV1 object ready for ML training
        """
        # Generate doc_id if not provided
        if not doc_id:
            doc_id = feedback.receipt_id or f"fb_{feedback.feedback_id}"
        
        # Map legacy verdict to new outcome
        doc_outcome = self.VERDICT_MAPPING.get(
            feedback.correct_verdict.value,
            "INCONCLUSIVE"
        )
        
        # Infer fraud types from legacy indicators
        fraud_types = self._infer_fraud_types(feedback)
        
        # Infer decision reasons from legacy indicators
        decision_reasons = self._infer_decision_reasons(feedback)
        
        # Map to evidence strength
        evidence_strength = self.EVIDENCE_MAPPING.get(
            feedback.correct_verdict.value,
            "MODERATE"
        )
        
        # Create annotator judgment
        judgment = AnnotatorJudgment(
            doc_outcome=doc_outcome,
            fraud_types=fraud_types,
            decision_reasons=decision_reasons,
            evidence_strength=evidence_strength,
            notes=feedback.user_notes
        )
        
        # Create document label
        label = DocumentLabelV1(
            label_version="v1",
            doc_id=doc_id,
            source_batch="legacy_migration",
            created_at=feedback.created_at,
            tool_version="feedback_adapter_v1.0",
            annotator_judgments=[judgment],
            metadata={
                "legacy_feedback_id": feedback.feedback_id,
                "legacy_verdict": feedback.correct_verdict.value,
                "system_verdict": feedback.system_verdict,
                "system_confidence": feedback.system_confidence,
                "migrated_at": datetime.now(timezone.utc).isoformat()
            }
        )
        
        return label
    
    def _infer_fraud_types(self, feedback: ReceiptFeedback) -> list:
        """Infer fraud types from legacy feedback indicators."""
        fraud_types = []
        
        # Only for fraudulent documents
        if feedback.correct_verdict.value != "fake":
            return fraud_types
        
        # Map from legacy indicators to new fraud types
        indicator_mapping = {
            "iLovePDF": "TEMPLATE_FORGERY",
            "PDFCreator": "TEMPLATE_FORGERY",
            "suspicious software": "TEMPLATE_FORGERY",
            "multiple addresses": "MULTIPLE_ADDRESS",
            "fake merchant": "FAKE_MERCHANT",
            "edited total": "AMOUNT_MANIPULATION",
            "total mismatch": "AMOUNT_MANIPULATION",
            "future date": "FUTURE_DATING",
            "spacing": "TEMPLATE_FORGERY",
            "language": "LANGUAGE_MISMATCH",
        }
        
        # Check missed and confirmed indicators
        all_indicators = (
            feedback.missed_indicators +
            feedback.confirmed_indicators +
            feedback.detected_indicators
        )
        
        for indicator in all_indicators:
            indicator_lower = indicator.lower()
            for pattern, fraud_type in indicator_mapping.items():
                if pattern in indicator_lower:
                    if fraud_type not in fraud_types:
                        fraud_types.append(fraud_type)
        
        # Check user notes
        if feedback.user_notes:
            notes_lower = feedback.user_notes.lower()
            for pattern, fraud_type in indicator_mapping.items():
                if pattern in notes_lower:
                    if fraud_type not in fraud_types:
                        fraud_types.append(fraud_type)
        
        # Default if no specific type found
        if not fraud_types:
            fraud_types.append("OTHER")
        
        return fraud_types
    
    def _infer_decision_reasons(self, feedback: ReceiptFeedback) -> list:
        """Infer decision reasons from legacy feedback."""
        reasons = []
        
        # Map from legacy indicators to decision reasons
        indicator_mapping = {
            "multiple addresses": "MULTIPLE_ADDRESSES_DETECTED",
            "merchant": "MERCHANT_ADDRESS_MISMATCH",
            "total mismatch": "AMOUNT_TOTAL_MISMATCH",
            "missing amount": "AMOUNT_MISSING",
            "future date": "FUTURE_DATE_DETECTED",
            "template": "TEMPLATE_QUALITY_POOR",
            "iLovePDF": "PDF_PRODUCER_SUSPICIOUS",
            "PDFCreator": "PDF_PRODUCER_SUSPICIOUS",
            "ocr": "OCR_CONFIDENCE_LOW",
            "language": "LANGUAGE_INCONSISTENT",
            "spacing": "TEMPLATE_QUALITY_POOR",
        }
        
        # Check all indicators
        all_indicators = (
            feedback.missed_indicators +
            feedback.confirmed_indicators +
            feedback.detected_indicators
        )
        
        for indicator in all_indicators:
            indicator_lower = indicator.lower()
            for pattern, reason in indicator_mapping.items():
                if pattern in indicator_lower:
                    if reason not in reasons:
                        reasons.append(reason)
        
        # Check user notes
        if feedback.user_notes:
            notes_lower = feedback.user_notes.lower()
            for pattern, reason in indicator_mapping.items():
                if pattern in notes_lower:
                    if reason not in reasons:
                        reasons.append(reason)
        
        # For GENUINE documents
        if feedback.correct_verdict.value == "real":
            if not reasons:
                reasons.append("EVIDENCE_INSUFFICIENT")
        
        # For FRAUDULENT documents, ensure at least 2 reasons
        elif feedback.correct_verdict.value == "fake":
            if len(reasons) < 2:
                if "OTHER" not in reasons:
                    reasons.append("OTHER")
                if len(reasons) < 2:
                    reasons.append("EVIDENCE_INSUFFICIENT")
        
        # For INCONCLUSIVE documents
        else:
            if not reasons:
                reasons.append("DOCUMENT_AMBIGUOUS")
        
        return reasons


def migrate_legacy_feedback_to_labels(
    feedback_csv: str = "data/logs/feedback.csv",
    output_jsonl: str = "data/labels/v1/labels.jsonl"
):
    """
    Migrate all legacy feedback to LabelV1 format.
    
    Args:
        feedback_csv: Path to legacy feedback CSV
        output_jsonl: Path to output labels JSONL
    """
    import pandas as pd
    import json
    from app.repository.feedback_store import get_feedback_store
    
    adapter = FeedbackToLabelAdapter()
    
    # Load legacy feedback
    store = get_feedback_store()
    all_feedback = store.get_all_feedback(limit=10000)
    
    print(f"Migrating {len(all_feedback)} legacy feedback entries...")
    
    # Convert to labels
    labels = []
    for feedback in all_feedback:
        try:
            label = adapter.convert_feedback_to_label(feedback)
            labels.append(label)
        except Exception as e:
            print(f"Error converting feedback {feedback.feedback_id}: {e}")
    
    # Write to JSONL
    output_path = Path(output_jsonl)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        for label in labels:
            f.write(label.model_dump_json() + '\n')
    
    print(f"✅ Migrated {len(labels)} labels to {output_jsonl}")
    
    # Validate
    from scripts.validate_labels import LabelValidator
    validator = LabelValidator()
    validator.validate_jsonl_file(output_path)
    validator.print_report()


if __name__ == "__main__":
    migrate_legacy_feedback_to_labels()
