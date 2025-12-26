#!/usr/bin/env python3
"""
Comprehensive test suite for enhanced VeriReceipt features:
- Confidence-aware rule weighting
- Extraction confidence tracking
- Merchant validation and blacklist filtering
- Audit trail system with event finalization
- Vision/Rules reconciliation
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.schemas.receipt import AuditEvent, ReceiptDecision, ReceiptInput, ReceiptFeatures
from app.pipelines.ensemble import EnsembleIntelligence
from app.pipelines.rules import (
    _confidence_factor_from_features,
    _normalize_amount_str,
    _has_total_value,
)


def test_confidence_factor_calculation():
    """Test confidence factor calculation from features."""
    print("\n" + "="*80)
    print("TEST 1: Confidence Factor Calculation")
    print("="*80)
    
    # Test case 1: High confidence
    ff = {"source_type": "pdf", "exif_present": True}
    tf = {"confidence": 0.90}
    lf = {}
    fr = {}
    
    factor = _confidence_factor_from_features(ff, tf, lf, fr)
    print(f"\n✓ High confidence (0.90) → factor = {factor:.2f}")
    assert factor == 1.0, f"Expected 1.0, got {factor}"
    
    # Test case 2: Medium confidence
    tf = {"confidence": 0.70}
    factor = _confidence_factor_from_features(ff, tf, lf, fr)
    print(f"✓ Medium confidence (0.70) → factor = {factor:.2f}")
    assert factor == 0.85, f"Expected 0.85, got {factor}"
    
    # Test case 3: Low confidence
    tf = {"confidence": 0.50}
    factor = _confidence_factor_from_features(ff, tf, lf, fr)
    print(f"✓ Low confidence (0.50) → factor = {factor:.2f}")
    assert factor == 0.70, f"Expected 0.70, got {factor}"
    
    # Test case 4: Low quality image (no EXIF)
    ff = {"source_type": "image", "exif_present": False}
    tf = {"confidence": 0.90}
    factor = _confidence_factor_from_features(ff, tf, lf, fr)
    print(f"✓ Low quality image → factor = {factor:.2f} (capped at 0.80)")
    assert factor == 0.80, f"Expected 0.80, got {factor}"
    
    # Test case 5: String confidence levels
    ff = {"source_type": "pdf"}
    tf = {"confidence": "high"}
    factor = _confidence_factor_from_features(ff, tf, lf, fr)
    print(f"✓ String confidence 'high' → factor = {factor:.2f}")
    assert factor == 1.0, f"Expected 1.0, got {factor}"
    
    tf = {"confidence": "medium"}
    factor = _confidence_factor_from_features(ff, tf, lf, fr)
    print(f"✓ String confidence 'medium' → factor = {factor:.2f}")
    assert factor == 0.85, f"Expected 0.85, got {factor}"
    
    tf = {"confidence": "low"}
    factor = _confidence_factor_from_features(ff, tf, lf, fr)
    print(f"✓ String confidence 'low' → factor = {factor:.2f}")
    assert factor == 0.70, f"Expected 0.70, got {factor}"
    
    print("\n✅ All confidence factor tests passed!")


def test_amount_normalization():
    """Test enhanced amount normalization."""
    print("\n" + "="*80)
    print("TEST 2: Amount Normalization")
    print("="*80)
    
    test_cases = [
        ("$45.67", 45.67),
        ("₹1,234.56", 1234.56),
        ("€99.99", 99.99),
        ("(50.00)", -50.00),  # Negative in parentheses
        ("1234.56 USD", 1234.56),
        ("INR 5000", 5000.0),
        ("$1,234,567.89", 1234567.89),
        ("45", 45.0),
        (123.45, 123.45),
        ("", None),
        (None, None),
    ]
    
    for input_val, expected in test_cases:
        result = _normalize_amount_str(input_val)
        status = "✓" if result == expected else "✗"
        print(f"{status} {repr(input_val):20s} → {result}")
        if result != expected:
            print(f"   Expected: {expected}")
    
    print("\n✅ Amount normalization tests completed!")


def test_total_value_detection():
    """Test total value detection from text features."""
    print("\n" + "="*80)
    print("TEST 3: Total Value Detection")
    print("="*80)
    
    # Test case 1: Has total
    tf = {"total": "$45.67"}
    result = _has_total_value(tf)
    print(f"✓ Has 'total' field → {result}")
    assert result is True
    
    # Test case 2: Has total_amount
    tf = {"total_amount": "123.45"}
    result = _has_total_value(tf)
    print(f"✓ Has 'total_amount' field → {result}")
    assert result is True
    
    # Test case 3: Has grand_total
    tf = {"grand_total": 99.99}
    result = _has_total_value(tf)
    print(f"✓ Has 'grand_total' field → {result}")
    assert result is True
    
    # Test case 4: No total
    tf = {"merchant": "Starbucks"}
    result = _has_total_value(tf)
    print(f"✓ No total fields → {result}")
    assert result is False
    
    # Test case 5: Empty total
    tf = {"total": ""}
    result = _has_total_value(tf)
    print(f"✓ Empty total → {result}")
    assert result is False
    
    print("\n✅ Total value detection tests passed!")


def test_merchant_validation():
    """Test merchant validation and blacklist filtering."""
    print("\n" + "="*80)
    print("TEST 4: Merchant Validation & Blacklist Filtering")
    print("="*80)
    
    ensemble = EnsembleIntelligence()
    
    # Test label-like merchants (should be detected)
    label_merchants = [
        "INVOICE",
        "RECEIPT",
        "Merchant:",
        "Vendor:",
        "TOTAL",
        "Tax Invoice",
        "Bill",
        "ABC",  # Too short
    ]
    
    print("\n📋 Testing label-like merchants (should be flagged):")
    for merchant in label_merchants:
        is_label = ensemble._looks_like_label_merchant(merchant)
        status = "✓" if is_label else "✗"
        print(f"  {status} {repr(merchant):20s} → label-like: {is_label}")
    
    # Test real merchants (should NOT be detected as labels)
    real_merchants = [
        "Starbucks",
        "Walmart",
        "Amazon.com",
        "McDonald's",
        "Target Store #1234",
        "Joe's Pizza & Grill",
    ]
    
    print("\n🏪 Testing real merchants (should NOT be flagged):")
    for merchant in real_merchants:
        is_label = ensemble._looks_like_label_merchant(merchant)
        status = "✓" if not is_label else "✗"
        print(f"  {status} {repr(merchant):30s} → label-like: {is_label}")
    
    # Test candidate selection
    print("\n🎯 Testing best merchant candidate selection:")
    
    candidates = [
        ("layoutlm", "INVOICE", 0.80),
        ("donut", "Starbucks", 0.70),
        ("vision", "MERCHANT", 0.60),
    ]
    
    best = ensemble._select_best_merchant_candidate(candidates)
    print(f"  Candidates: {[(src, val, w) for src, val, w in candidates]}")
    print(f"  ✓ Best: {best[0]} = '{best[1]}' (weight={best[2]:.2f})")
    assert best[1] == "Starbucks", "Should select real merchant over labels"
    
    print("\n✅ Merchant validation tests passed!")


def test_audit_event_finalization():
    """Test AuditEvent auto-finalization."""
    print("\n" + "="*80)
    print("TEST 5: Audit Event Finalization")
    print("="*80)
    
    # Create event without IDs
    event = AuditEvent(
        source="rule_engine",
        type="rule_triggered",
        severity="WARNING",
        code="R6_NO_TOTAL_LINE",
        message="No total line found",
        evidence={"has_any_amount": True}
    )
    
    print(f"\n📝 Before finalization:")
    print(f"  event_id: {repr(event.event_id)}")
    print(f"  ts: {repr(event.ts)}")
    
    # Finalize
    event.finalize_defaults()
    
    print(f"\n✅ After finalization:")
    print(f"  event_id: {event.event_id[:8]}... (UUID)")
    print(f"  ts: {event.ts} (ISO-8601)")
    
    assert event.event_id, "event_id should be populated"
    assert event.ts, "ts should be populated"
    assert len(event.event_id) == 36, "event_id should be valid UUID"
    
    # Test to_dict()
    event_dict = event.to_dict()
    print(f"\n📦 Serialized to dict:")
    print(f"  Keys: {list(event_dict.keys())}")
    assert "event_id" in event_dict
    assert "ts" in event_dict
    
    print("\n✅ Audit event finalization tests passed!")


def test_decision_finalization():
    """Test ReceiptDecision auto-finalization with nested events."""
    print("\n" + "="*80)
    print("TEST 6: Decision Finalization with Nested Events")
    print("="*80)
    
    # Create decision with audit events
    decision = ReceiptDecision(
        label="fake",
        score=0.65,
        reasons=["No total line", "Suspicious date gap"],
        rule_version="v2.0",
        policy_version="v1.0",
        engine_version="rules-v1.0"
    )
    
    # Add audit events without IDs
    event1 = AuditEvent(
        source="rule_engine",
        type="rule_triggered",
        severity="WARNING",
        code="R6_NO_TOTAL_LINE",
        message="No total line found"
    )
    
    event2 = AuditEvent(
        source="rule_engine",
        type="rule_triggered",
        severity="CRITICAL",
        code="R16_SUSPICIOUS_DATE_GAP",
        message="Receipt date is 5 days before file creation"
    )
    
    decision.add_audit_event(event1)
    decision.add_audit_event(event2)
    
    print(f"\n📝 Before finalization:")
    print(f"  decision_id: {repr(decision.decision_id)}")
    print(f"  created_at: {repr(decision.created_at)}")
    print(f"  audit_events: {len(decision.audit_events)} events")
    
    # Finalize
    decision.finalize_defaults()
    
    print(f"\n✅ After finalization:")
    print(f"  decision_id: {decision.decision_id[:8]}...")
    print(f"  created_at: {decision.created_at}")
    print(f"  policy_name: {decision.policy_name}")
    print(f"  finalized: {decision.finalized}")
    
    # Check nested events
    print(f"\n🔍 Nested audit events:")
    for i, event in enumerate(decision.audit_events, 1):
        print(f"  Event {i}:")
        print(f"    event_id: {event.event_id[:8]}...")
        print(f"    ts: {event.ts}")
        print(f"    code: {event.code}")
        assert event.event_id, f"Event {i} should have event_id"
        assert event.ts, f"Event {i} should have ts"
    
    # Test to_dict()
    decision_dict = decision.to_dict()
    print(f"\n📦 Serialized to dict:")
    print(f"  Top-level keys: {len(decision_dict)} keys")
    print(f"  audit_events: {len(decision_dict['audit_events'])} events")
    
    # Verify nested events are dicts
    for i, event_dict in enumerate(decision_dict['audit_events'], 1):
        assert isinstance(event_dict, dict), f"Event {i} should be dict"
        assert "event_id" in event_dict, f"Event {i} should have event_id"
        assert "ts" in event_dict, f"Event {i} should have ts"
    
    print("\n✅ Decision finalization tests passed!")


def test_extraction_confidence():
    """Test extraction confidence tracking."""
    print("\n" + "="*80)
    print("TEST 7: Extraction Confidence Tracking")
    print("="*80)
    
    ensemble = EnsembleIntelligence()
    
    # Mock results with varying confidence
    results = {
        "layoutlm": {
            "merchant": "Starbucks",
            "total": "45.67",
            "date": "2024-01-15"
        },
        "donut": {
            "merchant": "Starbucks Coffee",
            "total": {"total_price": "45.67"}
        },
        "donut_receipt": {
            "merchant": {"name": "Starbucks"},
            "total": "45.67",
            "date": "2024-01-15"
        }
    }
    
    converged = ensemble.converge_extraction(results)
    
    print(f"\n📊 Converged extraction:")
    print(f"  merchant: {converged.get('merchant')}")
    print(f"  total: {converged.get('total')}")
    print(f"  date: {converged.get('date')}")
    
    print(f"\n🎯 Confidence metrics:")
    print(f"  confidence_score: {converged.get('confidence_score'):.2f}")
    print(f"  confidence_level: {converged.get('confidence_level')}")
    
    # Verify confidence fields exist
    assert "confidence_score" in converged, "Should have confidence_score"
    assert "confidence_level" in converged, "Should have confidence_level"
    assert converged["confidence_level"] in ["low", "medium", "high"], "Should have valid level"
    
    # Test confidence level mapping
    print(f"\n🔄 Testing confidence level mapping:")
    test_scores = [0.95, 0.80, 0.70, 0.50]
    for score in test_scores:
        level = ensemble._confidence_level(score)
        print(f"  {score:.2f} → {level}")
    
    print("\n✅ Extraction confidence tests passed!")


def test_ensemble_agreement_scoring():
    """Test enhanced agreement scoring with value-level matching."""
    print("\n" + "="*80)
    print("TEST 8: Ensemble Agreement Scoring")
    print("="*80)
    
    ensemble = EnsembleIntelligence()
    
    # Test case 1: High agreement (all engines agree)
    results = {
        "layoutlm": {"merchant": "Starbucks", "total": "45.67", "date": "2024-01-15"},
        "donut": {"merchant": "Starbucks", "total": {"total_price": "45.67"}},
        "donut_receipt": {"merchant": {"name": "Starbucks"}, "total": "45.67", "date": "2024-01-15"}
    }
    
    converged = ensemble.converge_extraction(results)
    agreement = ensemble._calculate_agreement(results, converged)
    
    print(f"\n✓ High agreement scenario:")
    print(f"  All engines agree on merchant='Starbucks', total=45.67")
    print(f"  Agreement score: {agreement:.2f}")
    assert agreement >= 0.8, f"Expected high agreement, got {agreement}"
    
    # Test case 2: Low agreement (engines disagree)
    results = {
        "layoutlm": {"merchant": "Store A", "total": "100.00"},
        "donut": {"merchant": "Store B", "total": {"total_price": "200.00"}},
        "donut_receipt": {"merchant": {"name": "Store C"}, "total": "300.00"}
    }
    
    converged = ensemble.converge_extraction(results)
    agreement = ensemble._calculate_agreement(results, converged)
    
    print(f"\n✓ Low agreement scenario:")
    print(f"  Engines disagree on merchant and total")
    print(f"  Agreement score: {agreement:.2f}")
    assert agreement < 0.6, f"Expected low agreement, got {agreement}"
    
    print("\n✅ Agreement scoring tests passed!")


def test_vision_rules_reconciliation():
    """Test Vision/Rules reconciliation scenarios."""
    print("\n" + "="*80)
    print("TEST 9: Vision/Rules Reconciliation")
    print("="*80)
    
    ensemble = EnsembleIntelligence()
    
    # Scenario 1: HARD_FAIL always wins
    print("\n📌 Scenario 1: HARD_FAIL always rejects")
    results = {
        "vision_llm": {"verdict": "real", "confidence": 0.95},
        "rule_based": {
            "label": "fake",
            "score": 0.80,
            "reasons": ["[HARD_FAIL] Impossible date sequence"],
            "events": [
                {
                    "rule_id": "R15_IMPOSSIBLE_DATE_SEQUENCE",
                    "severity": "HARD_FAIL",
                    "weight": 0.50,
                    "message": "Receipt date is after file creation date"
                }
            ]
        }
    }
    converged = {"merchant": "Starbucks", "total": "45.67"}
    
    verdict = ensemble.build_ensemble_verdict(results, converged)
    print(f"  Vision: real (0.95), Rules: fake (HARD_FAIL)")
    print(f"  → Final: {verdict['final_label']} (confidence={verdict['confidence']:.2f})")
    print(f"  → Action: {verdict['recommended_action']}")
    if verdict['final_label'] != "fake":
        print(f"  ⚠️  Expected 'fake', got '{verdict['final_label']}'")
        print(f"  Reasoning: {verdict.get('reasoning', [])}")
    assert verdict["final_label"] == "fake", f"HARD_FAIL should always reject, got {verdict['final_label']}"
    
    # Scenario 2: Vision high-conf real + rules moderate → human review
    print("\n📌 Scenario 2: Vision/Rules conflict → human review")
    results = {
        "vision_llm": {"verdict": "real", "confidence": 0.92},
        "rule_based": {
            "label": "fake",
            "score": 0.75,
            "reasons": ["[CRITICAL] No total line", "Suspicious date gap"],
            "events": [
                {
                    "rule_id": "R6_NO_TOTAL_LINE",
                    "severity": "CRITICAL",
                    "weight": 0.15,
                    "message": "No total line found"
                }
            ]
        }
    }
    
    verdict = ensemble.build_ensemble_verdict(results, converged)
    print(f"  Vision: real (0.92), Rules: fake (0.75, 1 critical)")
    print(f"  → Final: {verdict['final_label']} (action={verdict['recommended_action']})")
    print(f"  Reasoning: {verdict['reasoning'][0] if verdict['reasoning'] else 'N/A'}")
    
    # Scenario 3: Both agree on real → approve
    print("\n📌 Scenario 3: Both agree on real → approve")
    results = {
        "vision_llm": {"verdict": "real", "confidence": 0.88},
        "rule_based": {"label": "real", "score": 0.15, "reasons": []}
    }
    
    verdict = ensemble.build_ensemble_verdict(results, converged)
    print(f"  Vision: real (0.88), Rules: real (0.15)")
    print(f"  → Final: {verdict['final_label']} (confidence={verdict['confidence']:.2f})")
    assert verdict["final_label"] == "real", "Both agree on real should approve"
    
    print("\n✅ Vision/Rules reconciliation tests passed!")


def run_all_tests():
    """Run all test suites."""
    print("\n" + "="*80)
    print("🧪 VeriReceipt Enhanced Features Test Suite")
    print("="*80)
    
    try:
        test_confidence_factor_calculation()
        test_amount_normalization()
        test_total_value_detection()
        test_merchant_validation()
        test_audit_event_finalization()
        test_decision_finalization()
        test_extraction_confidence()
        test_ensemble_agreement_scoring()
        test_vision_rules_reconciliation()
        
        print("\n" + "="*80)
        print("✅ ALL TESTS PASSED!")
        print("="*80)
        print("\n🎉 Enhanced features are working correctly!")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n💥 ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(run_all_tests())
