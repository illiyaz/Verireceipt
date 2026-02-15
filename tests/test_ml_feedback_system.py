"""
End-to-end tests for the ML feedback/learning system.

Tests the full pipeline:
1. Feedback submission → storage
2. Learning engine → rule creation
3. Learned rules → applied to new analysis
4. Data corrections → stored properly
5. Confirmed/false indicators → rule weight adjustments
"""

import sys
import os
import json
import uuid
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.feedback import (
    ReceiptFeedback,
    FeedbackSubmission,
    FeedbackType,
    CorrectVerdict,
    LearningRule,
)
from app.repository.feedback_store import FeedbackStore
from app.pipelines.learning import (
    learn_from_feedback,
    apply_learned_rules,
    _extract_pattern_from_indicator,
)


@pytest.fixture
def fresh_store(tmp_path):
    """Create a fresh SQLite feedback store in a temp directory."""
    db_path = str(tmp_path / "test_feedback.db")
    store = FeedbackStore(db_path=db_path)
    return store


@pytest.fixture
def sample_feedback():
    """Create a sample feedback object."""
    return ReceiptFeedback(
        feedback_id=f"fb_test_{uuid.uuid4().hex[:8]}",
        receipt_id="receipt_test_001",
        system_verdict="real",
        system_confidence=0.25,
        correct_verdict=CorrectVerdict.FAKE,
        feedback_type=FeedbackType.FALSE_NEGATIVE,
        user_notes="This receipt has spacing anomalies and date issues",
        missed_indicators=["spacing_anomalies", "date_manipulation"],
        false_indicators=[],
        confirmed_indicators=[],
        data_corrections={"merchant": "FAKE STORE", "total": 99.99},
        has_spacing_issue=True,
        has_date_issue=True,
    )


# =============================================================================
# Test 1: Feedback Storage
# =============================================================================

class TestFeedbackStorage:
    def test_save_and_retrieve_feedback(self, fresh_store, sample_feedback):
        """Feedback can be saved and retrieved."""
        fresh_store.save_feedback(sample_feedback)
        
        all_fb = fresh_store.get_all_feedback()
        assert len(all_fb) >= 1
        
        found = next((f for f in all_fb if f.feedback_id == sample_feedback.feedback_id), None)
        assert found is not None
        assert found.correct_verdict == CorrectVerdict.FAKE
        assert found.receipt_id == "receipt_test_001"
        assert found.system_verdict == "real"
        print(f"  [PASS] Feedback saved and retrieved: {found.feedback_id}")

    def test_multiple_feedbacks(self, fresh_store):
        """Multiple feedbacks can be stored."""
        for i in range(5):
            fb = ReceiptFeedback(
                feedback_id=f"fb_multi_{i}",
                receipt_id=f"receipt_{i}",
                system_verdict="suspicious",
                system_confidence=0.5,
                correct_verdict=CorrectVerdict.REAL if i % 2 == 0 else CorrectVerdict.FAKE,
                feedback_type=FeedbackType.VERDICT_CORRECTION,
            )
            fresh_store.save_feedback(fb)
        
        all_fb = fresh_store.get_all_feedback()
        assert len(all_fb) == 5
        print(f"  [PASS] Stored {len(all_fb)} feedbacks")

    def test_data_corrections_stored(self, fresh_store, sample_feedback):
        """Data corrections are preserved in storage."""
        fresh_store.save_feedback(sample_feedback)
        all_fb = fresh_store.get_all_feedback()
        found = next(f for f in all_fb if f.feedback_id == sample_feedback.feedback_id)
        assert found.data_corrections.get("merchant") == "FAKE STORE"
        assert found.data_corrections.get("total") == 99.99
        print(f"  [PASS] Data corrections stored: {found.data_corrections}")

    def test_missed_indicators_stored(self, fresh_store, sample_feedback):
        """Missed indicators are preserved."""
        fresh_store.save_feedback(sample_feedback)
        all_fb = fresh_store.get_all_feedback()
        found = next(f for f in all_fb if f.feedback_id == sample_feedback.feedback_id)
        assert "spacing_anomalies" in found.missed_indicators
        assert "date_manipulation" in found.missed_indicators
        print(f"  [PASS] Missed indicators stored: {found.missed_indicators}")


# =============================================================================
# Test 2: Learning Engine
# =============================================================================

class TestLearningEngine:
    def test_learn_from_false_negative(self, fresh_store, sample_feedback, monkeypatch):
        """Learning from false negative creates rules for spacing + date."""
        # Monkey-patch the global store
        monkeypatch.setattr(
            "app.pipelines.learning.get_feedback_store", lambda: fresh_store
        )
        
        rules_updated, new_patterns = learn_from_feedback(sample_feedback)
        
        assert rules_updated > 0, "Should have created at least one rule"
        print(f"  [PASS] False negative learning: {rules_updated} rules, patterns: {new_patterns}")

    def test_learn_from_missed_indicators(self, fresh_store, monkeypatch):
        """Missed indicators create new detection rules."""
        monkeypatch.setattr(
            "app.pipelines.learning.get_feedback_store", lambda: fresh_store
        )
        
        fb = ReceiptFeedback(
            feedback_id="fb_missed_test",
            receipt_id="receipt_missed",
            system_verdict="real",
            system_confidence=0.2,
            correct_verdict=CorrectVerdict.FAKE,
            feedback_type=FeedbackType.FALSE_NEGATIVE,
            missed_indicators=["spacing_anomalies", "invalid_address", "font_inconsistencies"],
        )
        
        rules_updated, patterns = learn_from_feedback(fb)
        
        # Check rules were created
        all_rules = fresh_store.get_learned_rules(enabled_only=False)
        pattern_types = [r.pattern for r in all_rules]
        
        assert "spacing_anomaly" in pattern_types, f"Missing spacing rule, got: {pattern_types}"
        assert "invalid_address" in pattern_types, f"Missing address rule, got: {pattern_types}"
        print(f"  [PASS] Missed indicators → rules: {pattern_types}")

    def test_learn_from_false_indicators(self, fresh_store, monkeypatch):
        """False alarm indicators reduce rule confidence or create whitelist."""
        monkeypatch.setattr(
            "app.pipelines.learning.get_feedback_store", lambda: fresh_store
        )
        
        fb = ReceiptFeedback(
            feedback_id="fb_false_test",
            receipt_id="receipt_false",
            system_verdict="fake",
            system_confidence=0.8,
            correct_verdict=CorrectVerdict.REAL,
            feedback_type=FeedbackType.FALSE_POSITIVE,
            false_indicators=["R7_TOTAL_MISMATCH: OCR error caused false total"],
        )
        
        rules_updated, patterns = learn_from_feedback(fb)
        
        all_rules = fresh_store.get_learned_rules(enabled_only=False)
        # Should have created a whitelist or reduced rule
        assert len(all_rules) > 0 or rules_updated > 0
        print(f"  [PASS] False indicator learning: {rules_updated} rules, patterns: {patterns}")

    def test_learn_from_data_corrections(self, fresh_store, monkeypatch):
        """Data corrections create merchant pattern rules."""
        monkeypatch.setattr(
            "app.pipelines.learning.get_feedback_store", lambda: fresh_store
        )
        
        fb = ReceiptFeedback(
            feedback_id="fb_correction_test",
            receipt_id="receipt_correction",
            system_verdict="suspicious",
            system_confidence=0.6,
            correct_verdict=CorrectVerdict.REAL,
            feedback_type=FeedbackType.VERDICT_CORRECTION,
            data_corrections={"merchant": "Starbucks", "total": 12.50},
        )
        
        rules_updated, patterns = learn_from_feedback(fb)
        
        all_rules = fresh_store.get_learned_rules(enabled_only=False)
        merchant_rules = [r for r in all_rules if r.rule_type == "merchant_pattern"]
        assert len(merchant_rules) > 0, "Should create merchant pattern rule"
        assert merchant_rules[0].pattern == "Starbucks"
        print(f"  [PASS] Data correction → merchant rule: {merchant_rules[0].pattern}")

    def test_confirmed_indicators_reinforce(self, fresh_store, monkeypatch):
        """Confirmed indicators increase rule confidence."""
        monkeypatch.setattr(
            "app.pipelines.learning.get_feedback_store", lambda: fresh_store
        )
        
        # First create a rule via missed indicator
        fb1 = ReceiptFeedback(
            feedback_id="fb_create_rule",
            receipt_id="receipt_create",
            system_verdict="real",
            system_confidence=0.2,
            correct_verdict=CorrectVerdict.FAKE,
            feedback_type=FeedbackType.FALSE_NEGATIVE,
            missed_indicators=["spacing_anomalies"],
        )
        learn_from_feedback(fb1)
        
        rules_before = fresh_store.get_learned_rules(enabled_only=False)
        spacing_before = next((r for r in rules_before if "spacing" in r.pattern.lower()), None)
        assert spacing_before is not None
        conf_before = spacing_before.confidence_adjustment
        
        # Now confirm the indicator
        fb2 = ReceiptFeedback(
            feedback_id="fb_confirm_rule",
            receipt_id="receipt_confirm",
            system_verdict="fake",
            system_confidence=0.8,
            correct_verdict=CorrectVerdict.FAKE,
            feedback_type=FeedbackType.VERDICT_CORRECTION,
            confirmed_indicators=["spacing_anomalies"],
        )
        learn_from_feedback(fb2)
        
        rules_after = fresh_store.get_learned_rules(enabled_only=False)
        spacing_after = next((r for r in rules_after if "spacing" in r.pattern.lower()), None)
        assert spacing_after is not None
        assert spacing_after.confidence_adjustment >= conf_before
        print(f"  [PASS] Confirmed indicator reinforced: {conf_before:.3f} → {spacing_after.confidence_adjustment:.3f}")


# =============================================================================
# Test 3: Apply Learned Rules
# =============================================================================

class TestApplyLearnedRules:
    def test_apply_spacing_rule(self, fresh_store, monkeypatch):
        """Learned spacing rule applies to features with spacing issues."""
        monkeypatch.setattr(
            "app.pipelines.learning.get_feedback_store", lambda: fresh_store
        )
        
        # Create a spacing rule
        rule = LearningRule(
            rule_id="lr_test_spacing",
            rule_type="spacing_threshold",
            pattern="consecutive_spaces",
            action="lower_threshold",
            confidence_adjustment=0.15,
            learned_from_feedback_count=3,
            auto_learned=True,
        )
        fresh_store.save_learned_rule(rule)
        
        # Apply to features with spacing issues
        features = {
            "forensic_features": {
                "has_excessive_spacing": True,
                "max_consecutive_spaces": 12,
            }
        }
        
        score_adj, triggered = apply_learned_rules(features)
        assert score_adj > 0, "Spacing rule should trigger"
        assert len(triggered) > 0
        assert "spacing" in triggered[0].lower()
        print(f"  [PASS] Spacing rule applied: adj={score_adj:.3f}, msg={triggered[0][:80]}")

    def test_apply_software_rule(self, fresh_store, monkeypatch):
        """Learned software rule applies to features with suspicious software."""
        monkeypatch.setattr(
            "app.pipelines.learning.get_feedback_store", lambda: fresh_store
        )
        
        rule = LearningRule(
            rule_id="lr_test_sw",
            rule_type="suspicious_software",
            pattern="iLovePDF",
            action="increase_fraud_score",
            confidence_adjustment=0.20,
            learned_from_feedback_count=5,
            auto_learned=True,
        )
        fresh_store.save_learned_rule(rule)
        
        features = {
            "file_features": {"producer": "iLovePDF Online"},
        }
        
        score_adj, triggered = apply_learned_rules(features)
        assert score_adj >= 0.20
        assert "iLovePDF" in triggered[0]
        print(f"  [PASS] Software rule applied: adj={score_adj:.3f}")

    def test_no_rules_no_adjustment(self, fresh_store, monkeypatch):
        """No learned rules means zero adjustment."""
        monkeypatch.setattr(
            "app.pipelines.learning.get_feedback_store", lambda: fresh_store
        )
        
        features = {"file_features": {}, "forensic_features": {}}
        score_adj, triggered = apply_learned_rules(features)
        assert score_adj == 0.0
        assert len(triggered) == 0
        print(f"  [PASS] No rules → zero adjustment")


# =============================================================================
# Test 4: Pattern Extraction
# =============================================================================

class TestPatternExtraction:
    def test_spacing_pattern(self):
        assert _extract_pattern_from_indicator("spacing_anomalies") == "spacing_anomaly"

    def test_address_pattern(self):
        assert _extract_pattern_from_indicator("invalid_address") == "invalid_address"

    def test_date_pattern(self):
        assert _extract_pattern_from_indicator("date_manipulation") == "date_manipulation"

    def test_phone_pattern(self):
        assert _extract_pattern_from_indicator("Invalid phone number") == "invalid_phone"

    def test_font_pattern(self):
        result = _extract_pattern_from_indicator("font_inconsistencies")
        assert result is not None and len(result) > 0


# =============================================================================
# Test 5: FeedbackSubmission Model (new fields)
# =============================================================================

class TestFeedbackSubmissionModel:
    def test_new_fields_present(self):
        """FeedbackSubmission accepts all new review fields."""
        sub = FeedbackSubmission(
            receipt_id="test_001",
            correct_verdict=CorrectVerdict.FAKE,
            user_notes="test note",
            missed_indicators=["spacing_anomalies"],
            false_indicators=["R7_TOTAL_MISMATCH: false alarm"],
            confirmed_indicators=["R_DATE_CONFLICT"],
            data_corrections={"merchant": "Starbucks", "total": 12.50},
            font_manipulation=True,
            address_issues="fake",
            visual_integrity_issues="edited",
            amount_verification_notes="math_error",
        )
        assert sub.confirmed_indicators == ["R_DATE_CONFLICT"]
        assert sub.data_corrections["merchant"] == "Starbucks"
        assert sub.font_manipulation is True
        assert sub.address_issues == "fake"
        assert sub.visual_integrity_issues == "edited"
        assert sub.amount_verification_notes == "math_error"
        print(f"  [PASS] FeedbackSubmission model accepts all 8-step review fields")

    def test_backward_compatible(self):
        """Old-style submissions still work (no new fields)."""
        sub = FeedbackSubmission(
            receipt_id="test_old",
            correct_verdict=CorrectVerdict.REAL,
        )
        assert sub.confirmed_indicators == []
        assert sub.data_corrections == {}
        assert sub.font_manipulation is False
        assert sub.address_issues is None
        print(f"  [PASS] Backward compatible: old submissions work")


# =============================================================================
# Test 6: Full Round-Trip
# =============================================================================

class TestFullRoundTrip:
    def test_feedback_to_learning_to_application(self, fresh_store, monkeypatch):
        """Full pipeline: submit feedback → learn → apply to new receipt."""
        monkeypatch.setattr(
            "app.pipelines.learning.get_feedback_store", lambda: fresh_store
        )
        
        # Step 1: Submit feedback saying system missed spacing fraud
        fb = ReceiptFeedback(
            feedback_id="fb_roundtrip",
            receipt_id="receipt_roundtrip",
            system_verdict="real",
            system_confidence=0.15,
            correct_verdict=CorrectVerdict.FAKE,
            feedback_type=FeedbackType.FALSE_NEGATIVE,
            missed_indicators=["spacing_anomalies"],
            has_spacing_issue=True,
            software_detected="FakeReceiptMaker",
        )
        
        # Step 2: Save and learn
        fresh_store.save_feedback(fb)
        rules_updated, patterns = learn_from_feedback(fb)
        assert rules_updated > 0
        
        # Step 3: Verify rules exist
        all_rules = fresh_store.get_learned_rules(enabled_only=True)
        assert len(all_rules) > 0
        
        # Step 4: Apply to a new receipt with similar features
        new_features = {
            "file_features": {"producer": "FakeReceiptMaker v2"},
            "forensic_features": {
                "has_excessive_spacing": True,
                "max_consecutive_spaces": 15,
            },
        }
        
        score_adj, triggered = apply_learned_rules(new_features)
        assert score_adj > 0, f"Rules should fire on similar features, got adj={score_adj}"
        assert len(triggered) > 0
        
        print(f"  [PASS] Full round-trip: feedback → {rules_updated} rules → adj={score_adj:.3f} on new receipt")
        print(f"         Triggered rules: {[t[:60] for t in triggered]}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
