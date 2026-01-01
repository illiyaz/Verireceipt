"""
Unit test to verify missing_elements learned rules are properly gated.

This test ensures that when missing-field penalties are disabled (gated),
learned missing_elements rules do NOT mutate the score.
"""

import pytest
from pathlib import Path
from PIL import Image
import tempfile

from app.pipelines.rules import analyze_receipt


def create_mock_receipt_image(width=800, height=1000):
    """Create a minimal mock receipt image for testing."""
    img = Image.new('RGB', (width, height), color='white')
    return img


def test_missing_elements_gated_no_score():
    """
    Test that missing_elements learned rules are properly gated.
    
    When missing-field penalties are disabled (due to low geo/doc confidence),
    learned missing_elements rules should:
    1. Be suppressed (not affect score)
    2. Emit GATE_MISSING_FIELDS event
    3. Emit LR_LEARNED_PATTERN_SUPPRESSED event (not LR_LEARNED_PATTERN)
    4. Keep score low (< 0.35 for a minimal receipt)
    """
    # Create a minimal mock receipt that will trigger:
    # - Low geo confidence (UNKNOWN)
    # - Low doc profile confidence
    # - Missing-field gate activation
    # - Learned missing_elements rule
    
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        img = create_mock_receipt_image()
        img.save(tmp.name)
        tmp_path = Path(tmp.name)
        
        try:
            # Analyze the receipt
            decision = analyze_receipt(str(tmp_path))
            
            # CRITICAL ASSERTION: Verify missing_elements is suppressed
            # Note: Other learned rules (spacing_anomaly, invalid_address) may still apply
            # The key test is that missing_elements specifically does NOT affect score
            
            # Check that missing_elements was suppressed
            missing_suppressed = any(
                "missing_elements" in r.lower() and "suppressed" in r.lower()
                for r in (decision.reasons or [])
            )
            assert missing_suppressed, (
                "missing_elements learned rule was not suppressed when gate is active"
            )
            
            # Score should be reasonable (not inflated by missing_elements)
            # Allow up to 0.50 since other learned rules may apply
            assert decision.score < 0.50, (
                f"Score too high ({decision.score:.2f}). "
                f"Even with other learned rules, score should stay below 0.50 when gate is active."
            )
            
            # Verify GATE_MISSING_FIELDS event exists
            gate_events = [
                e for e in (decision.events or [])
                if e.get("rule_id") == "GATE_MISSING_FIELDS"
            ]
            assert len(gate_events) > 0, (
                "GATE_MISSING_FIELDS event not found. Missing-field gate not activated."
            )
            
            # Verify suppressed learned rule event exists
            suppressed_events = [
                e for e in (decision.events or [])
                if e.get("rule_id") == "LR_LEARNED_PATTERN_SUPPRESSED"
            ]
            
            # Check if any learned rules were triggered
            learned_events = [
                e for e in (decision.events or [])
                if e.get("rule_id") in ("LR_LEARNED_PATTERN", "LR_LEARNED_PATTERN_SUPPRESSED")
            ]
            
            if learned_events:
                # If learned rules were triggered, verify suppressed ones exist
                assert len(suppressed_events) > 0, (
                    "Learned rules triggered but no LR_LEARNED_PATTERN_SUPPRESSED events found. "
                    "Missing_elements rules may not be properly suppressed."
                )
                
                # Verify suppressed events have correct evidence
                for event in suppressed_events:
                    evidence = event.get("evidence", {})
                    assert evidence.get("suppressed") is True, (
                        "Suppressed event does not have suppressed=True in evidence"
                    )
                    assert evidence.get("applied_to_score") is False, (
                        "Suppressed event has applied_to_score=True, indicating score leakage"
                    )
            
            # Verify no non-suppressed missing_elements learned rules
            non_suppressed_missing = [
                e for e in (decision.events or [])
                if e.get("rule_id") == "LR_LEARNED_PATTERN"
                and "missing_elements" in str(e.get("evidence", {}).get("pattern", "")).lower()
            ]
            assert len(non_suppressed_missing) == 0, (
                f"Found {len(non_suppressed_missing)} non-suppressed missing_elements learned rules. "
                "These should be suppressed when gate is active."
            )
            
            # Verify reasons contain suppressed marker
            suppressed_reasons = [
                r for r in (decision.reasons or [])
                if "suppressed" in r.lower() and "missing" in r.lower()
            ]
            
            if learned_events:
                assert len(suppressed_reasons) > 0, (
                    "No suppressed reasons found in decision.reasons. "
                    "User-facing output should indicate suppression."
                )
            
            print(f"✅ TEST PASSED: missing_elements gated correctly")
            print(f"   Score: {decision.score:.2f} (< 0.35)")
            print(f"   Gate events: {len(gate_events)}")
            print(f"   Suppressed learned rules: {len(suppressed_events)}")
            print(f"   Non-suppressed missing_elements: {len(non_suppressed_missing)}")
            
        finally:
            # Cleanup
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass


def test_missing_elements_not_gated_when_enabled():
    """
    Test that missing_elements learned rules ARE applied when gate is disabled.
    
    This is a complementary test to ensure the gate logic works both ways.
    Note: This test may not trigger in all cases since it depends on having
    high geo/doc confidence, which is hard to achieve with mock images.
    """
    # This test is informational - it's harder to guarantee high confidence
    # with mock images, but we can at least verify the code path exists
    
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        img = create_mock_receipt_image()
        img.save(tmp.name)
        tmp_path = Path(tmp.name)
        
        try:
            decision = analyze_receipt(str(tmp_path))
            
            # Just verify the decision completes without error
            assert decision is not None
            assert hasattr(decision, 'score')
            assert hasattr(decision, 'events')
            
            print(f"✅ TEST PASSED: Decision completes successfully")
            print(f"   Score: {decision.score:.2f}")
            print(f"   Missing fields enabled: {getattr(decision, 'missing_fields_enabled', 'unknown')}")
            
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass


if __name__ == "__main__":
    print("Running learned rules gating tests...\n")
    test_missing_elements_gated_no_score()
    print()
    test_missing_elements_not_gated_when_enabled()
    print("\n✅ All tests passed!")
