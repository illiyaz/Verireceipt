"""
Tests for label schema validation.
"""

import pytest
from datetime import datetime, timezone
from app.schemas.labels import (
    DocumentLabelV1,
    AnnotatorJudgment,
    Adjudication,
    FieldLabel,
    SignalReview,
    FRAUD_TYPES,
    DECISION_REASONS
)
from app.schemas.receipt import SignalRegistry


class TestLabelSchema:
    """Test label schema validation and business rules."""
    
    def test_minimal_genuine_label(self):
        """Test minimal valid GENUINE label."""
        judgment = AnnotatorJudgment(
            doc_outcome="GENUINE",
            fraud_types=[],
            decision_reasons=[],
            evidence_strength="NONE"
        )
        
        label = DocumentLabelV1(
            label_version="v1",
            doc_id="test_doc_123",
            source_batch="test_batch",
            created_at=datetime.now(timezone.utc),
            annotator_judgments=[judgment]
        )
        
        assert label.get_final_outcome() == "GENUINE"
        assert label.get_final_fraud_types() == []
        assert label.get_final_evidence_strength() == "NONE"
    
    def test_fraudulent_label_requirements(self):
        """Test FRAUDULENT label requirements."""
        # Missing fraud_types - should fail
        with pytest.raises(ValueError, match="FRAUDULENT documents must have fraud_types"):
            AnnotatorJudgment(
                doc_outcome="FRAUDULENT",
                fraud_types=[],
                decision_reasons=["MULTIPLE_ADDRESSES_DETECTED"],
                evidence_strength="STRONG"
            )
        
        # Missing decision reasons - should fail
        with pytest.raises(ValueError, match="FRAUDULENT documents require ≥2 decision_reasons"):
            AnnotatorJudgment(
                doc_outcome="FRAUDULENT",
                fraud_types=["MULTIPLE_ADDRESS"],
                decision_reasons=["MULTIPLE_ADDRESSES_DETECTED"],
                evidence_strength="STRONG"
            )
        
        # Valid fraudulent label
        judgment = AnnotatorJudgment(
            doc_outcome="FRAUDULENT",
            fraud_types=["MULTIPLE_ADDRESS", "FAKE_MERCHANT"],
            decision_reasons=[
                "MULTIPLE_ADDRESSES_DETECTED",
                "MERCHANT_ADDRESS_MISMATCH"
            ],
            evidence_strength="STRONG"
        )
        
        assert judgment.doc_outcome == "FRAUDULENT"
        assert len(judgment.fraud_types) == 2
        assert len(judgment.decision_reasons) == 2
    
    def test_inconclusive_label_requirements(self):
        """Test INCONCLUSIVE label requirements."""
        # Cannot have NONE evidence strength
        with pytest.raises(ValueError, match="INCONCLUSIVE documents cannot have evidence_strength == NONE"):
            AnnotatorJudgment(
                doc_outcome="INCONCLUSIVE",
                fraud_types=[],
                decision_reasons=["DOCUMENT_AMBIGUOUS"],
                evidence_strength="NONE"
            )
        
        # Valid inconclusive label
        judgment = AnnotatorJudgment(
            doc_outcome="INCONCLUSIVE",
            fraud_types=["MULTIPLE_ADDRESS"],
            decision_reasons=["DOCUMENT_AMBIGUOUS"],
            evidence_strength="WEAK"
        )
        
        assert judgment.doc_outcome == "INCONCLUSIVE"
        assert judgment.evidence_strength == "WEAK"
    
    def test_genuine_label_constraints(self):
        """Test GENUINE label constraints."""
        # Cannot have fraud_types
        with pytest.raises(ValueError, match="GENUINE documents cannot have fraud_types"):
            AnnotatorJudgment(
                doc_outcome="GENUINE",
                fraud_types=["MULTIPLE_ADDRESS"],
                decision_reasons=[],
                evidence_strength="NONE"
            )
        
        # Cannot have strong evidence
        with pytest.raises(ValueError, match="GENUINE documents must have evidence_strength"):
            AnnotatorJudgment(
                doc_outcome="GENUINE",
                fraud_types=[],
                decision_reasons=[],
                evidence_strength="STRONG"
            )
        
        # Valid genuine labels
        for evidence_strength in ["NONE", "WEAK"]:
            judgment = AnnotatorJudgment(
                doc_outcome="GENUINE",
                fraud_types=[],
                decision_reasons=[],
                evidence_strength=evidence_strength
            )
            assert judgment.evidence_strength == evidence_strength
    
    def test_signal_reviews_validation(self):
        """Test signal reviews only allow registered signals."""
        # Valid signal review
        judgment = AnnotatorJudgment(
            doc_outcome="FRAUDULENT",
            fraud_types=["MULTIPLE_ADDRESS"],
            decision_reasons=["MULTIPLE_ADDRESSES_DETECTED", "MERCHANT_ADDRESS_MISMATCH"],
            evidence_strength="STRONG",
            signal_reviews={
                "addr.multi_address": SignalReview(agree=True, comment="Clear multiple addresses"),
                "addr.merchant_consistency": SignalReview(agree=False, comment="Merchant seems legit")
            }
        )
        
        # Invalid signal name should fail
        with pytest.raises(ValueError, match="Signal 'addr.invalid_signal' is not registered"):
            AnnotatorJudgment(
                doc_outcome="FRAUDULENT",
                fraud_types=["MULTIPLE_ADDRESS"],
                decision_reasons=["MULTIPLE_ADDRESSES_DETECTED"],
                evidence_strength="STRONG",
                signal_reviews={
                    "addr.invalid_signal": SignalReview(agree=True)
                }
            )
    
    def test_field_labels(self):
        """Test field label validation."""
        field_label = FieldLabel(
            status="CORRECT",
            confidence=0.95,
            notes="Merchant name looks correct"
        )
        
        assert field_label.status == "CORRECT"
        assert field_label.confidence == 0.95
        assert field_label.notes is not None
        
        # Test all valid statuses
        valid_statuses = ["CORRECT", "INCORRECT", "MISSING", "UNCLEAR"]
        for status in valid_statuses:
            field_label = FieldLabel(status=status, confidence=0.8)
            assert field_label.status == status
    
    def test_adjudication_validation(self):
        """Test adjudication validation."""
        # Valid adjudication
        adjudication = Adjudication(
            finalized_by="senior_reviewer",
            final_outcome="FRAUDULENT",
            final_fraud_types=["MULTIPLE_ADDRESS"],
            final_decision_reasons=["MULTIPLE_ADDRESSES_DETECTED", "MERCHANT_ADDRESS_MISMATCH"],
            final_evidence_strength="STRONG"
        )
        
        assert adjudication.final_outcome == "FRAUDULENT"
        assert len(adjudication.final_fraud_types) == 1
        assert len(adjudication.final_decision_reasons) == 2
        
        # GENUINE adjudication cannot have fraud_types
        with pytest.raises(ValueError, match="GENUINE adjudication cannot have fraud_types"):
            Adjudication(
                finalized_by="senior_reviewer",
                final_outcome="GENUINE",
                final_fraud_types=["MULTIPLE_ADDRESS"],
                final_decision_reasons=[],
                final_evidence_strength="NONE"
            )
    
    def test_document_label_validation(self):
        """Test complete document label validation."""
        judgment1 = AnnotatorJudgment(
            doc_outcome="FRAUDULENT",
            fraud_types=["MULTIPLE_ADDRESS"],
            decision_reasons=["MULTIPLE_ADDRESSES_DETECTED", "MERCHANT_ADDRESS_MISMATCH"],
            evidence_strength="STRONG"
        )
        
        judgment2 = AnnotatorJudgment(
            doc_outcome="FRAUDULENT",
            fraud_types=["MULTIPLE_ADDRESS"],
            decision_reasons=["MULTIPLE_ADDRESSES_DETECTED", "EVIDENCE_INSUFFICIENT"],
            evidence_strength="MODERATE"
        )
        
        # Document with two judgments (no adjudication needed if they agree)
        label = DocumentLabelV1(
            label_version="v1",
            doc_id="test_doc_123",
            source_batch="test_batch",
            created_at=datetime.now(timezone.utc),
            annotator_judgments=[judgment1, judgment2]
        )
        
        assert len(label.annotator_judgments) == 2
        assert label.get_final_outcome() == "FRAUDULENT"
        
        # Document with adjudication
        adjudication = Adjudication(
            finalized_by="senior_reviewer",
            final_outcome="FRAUDULENT",
            final_fraud_types=["MULTIPLE_ADDRESS", "FAKE_MERCHANT"],
            final_decision_reasons=["MULTIPLE_ADDRESSES_DETECTED", "MERCHANT_ADDRESS_MISMATCH"],
            final_evidence_strength="STRONG"
        )
        
        label_with_adjudication = DocumentLabelV1(
            label_version="v1",
            doc_id="test_doc_456",
            source_batch="test_batch",
            created_at=datetime.now(timezone.utc),
            annotator_judgments=[judgment1, judgment2],
            adjudication=adjudication
        )
        
        assert label_with_adjudication.get_final_outcome() == "FRAUDULENT"
        assert label_with_adjudication.get_final_fraud_types() == ["MULTIPLE_ADDRESS", "FAKE_MERCHANT"]
    
    def test_label_version_must_be_v1(self):
        """Test that label_version is always 'v1'."""
        judgment = AnnotatorJudgment(
            doc_outcome="GENUINE",
            fraud_types=[],
            decision_reasons=[],
            evidence_strength="NONE"
        )
        
        # Should default to v1
        label = DocumentLabelV1(
            doc_id="test_doc",
            source_batch="test_batch",
            created_at=datetime.now(timezone.utc),
            annotator_judgments=[judgment]
        )
        
        assert label.label_version == "v1"
    
    def test_minimum_judgments_required(self):
        """Test that at least one judgment is required."""
        with pytest.raises(ValueError, match="At least one annotator judgment is required"):
            DocumentLabelV1(
                label_version="v1",
                doc_id="test_doc",
                source_batch="test_batch",
                created_at=datetime.now(timezone.utc),
                annotator_judgments=[]
            )
    
    def test_adjudication_only_with_multiple_judgments(self):
        """Test that adjudication is only allowed with multiple judgments."""
        judgment = AnnotatorJudgment(
            doc_outcome="GENUINE",
            fraud_types=[],
            decision_reasons=[],
            evidence_strength="NONE"
        )
        
        adjudication = Adjudication(
            finalized_by="senior_reviewer",
            final_outcome="GENUINE",
            final_fraud_types=[],
            final_decision_reasons=[],
            final_evidence_strength="NONE"
        )
        
        # Single judgment with adjudication should fail
        with pytest.raises(ValueError, match="Adjudication only needed with multiple judgments"):
            DocumentLabelV1(
                label_version="v1",
                doc_id="test_doc",
                source_batch="test_batch",
                created_at=datetime.now(timezone.utc),
                annotator_judgments=[judgment],
                adjudication=adjudication
            )


class TestTaxonomies:
    """Test fraud type and decision reason taxonomies."""
    
    def test_fraud_types_are_defined(self):
        """Test that all fraud types are defined."""
        assert len(FRAUD_TYPES) > 0
        assert "MULTIPLE_ADDRESS" in FRAUD_TYPES
        assert "FAKE_MERCHANT" in FRAUD_TYPES
        assert "OTHER" in FRAUD_TYPES
    
    def test_decision_reasons_are_defined(self):
        """Test that all decision reasons are defined."""
        assert len(DECISION_REASONS) > 0
        assert "MULTIPLE_ADDRESSES_DETECTED" in DECISION_REASONS
        assert "MERCHANT_ADDRESS_MISMATCH" in DECISION_REASONS
        assert "OTHER" in DECISION_REASONS
    
    def test_signal_registry_integration(self):
        """Test that signal registry is available for validation."""
        assert len(SignalRegistry.get_all_names()) > 0
        assert "addr.multi_address" in SignalRegistry.get_all_names()
        assert "amount.total_mismatch" in SignalRegistry.get_all_names()


class TestLabelExamples:
    """Test example label scenarios."""
    
    def test_complete_fraud_example(self):
        """Test a complete fraud example with all fields."""
        judgment = AnnotatorJudgment(
            doc_outcome="FRAUDULENT",
            fraud_types=["MULTIPLE_ADDRESS", "FAKE_MERCHANT"],
            decision_reasons=[
                "MULTIPLE_ADDRESSES_DETECTED",
                "MERCHANT_ADDRESS_MISMATCH"
            ],
            evidence_strength="STRONG",
            field_labels={
                "merchant_name": FieldLabel(
                    status="INCORRECT",
                    confidence=0.9,
                    notes="Merchant appears to be fake"
                ),
                "total_amount": FieldLabel(
                    status="CORRECT",
                    confidence=0.95
                )
            },
            signal_reviews={
                "addr.multi_address": SignalReview(
                    agree=True,
                    comment="Clear multiple addresses detected"
                ),
                "addr.merchant_consistency": SignalReview(
                    agree=True,
                    comment="Merchant name doesn't match any address"
                )
            },
            notes="Document shows clear signs of fake merchant with multiple addresses"
        )
        
        label = DocumentLabelV1(
            label_version="v1",
            doc_id="fraud_example_123",
            source_batch="test_batch",
            created_at=datetime.now(timezone.utc),
            annotator_judgments=[judgment]
        )
        
        assert label.get_final_outcome() == "FRAUDULENT"
        assert "MULTIPLE_ADDRESS" in label.get_final_fraud_types()
        assert label.get_final_evidence_strength() == "STRONG"
    
    def test_genuine_example_with_field_labels(self):
        """Test a genuine document with field validation."""
        judgment = AnnotatorJudgment(
            doc_outcome="GENUINE",
            fraud_types=[],
            decision_reasons=[],
            evidence_strength="WEAK",
            field_labels={
                "merchant_name": FieldLabel(
                    status="CORRECT",
                    confidence=0.95
                ),
                "total_amount": FieldLabel(
                    status="CORRECT",
                    confidence=0.9
                ),
                "invoice_date": FieldLabel(
                    status="CORRECT",
                    confidence=0.85
                )
            }
        )
        
        label = DocumentLabelV1(
            label_version="v1",
            doc_id="genuine_example_456",
            source_batch="test_batch",
            created_at=datetime.now(timezone.utc),
            annotator_judgments=[judgment]
        )
        
        assert label.get_final_outcome() == "GENUINE"
        assert label.get_final_fraud_types() == []
        assert label.get_final_evidence_strength() == "WEAK"
