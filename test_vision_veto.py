"""
Test script to verify vision veto system integration.
Tests that vision_assessment correctly triggers HARD_FAIL when tampered.
"""

from app.pipelines.rules import _score_and_explain
from app.schemas.receipt import ReceiptFeatures

# Create minimal features for testing
def create_test_features():
    """Create minimal ReceiptFeatures for testing."""
    return ReceiptFeatures(
        file_features={
            "source_type": "image",
            "file_size": 100000,
            "page_count": 1,
        },
        text_features={
            "full_text": "Test Store\n123 Main St\nTotal: $100.00",
            "merchant": "Test Store",
            "total_amount": "100.00",
            "geo_country_guess": "US",
            "geo_confidence": 0.75,
        },
        layout_features={},
        forensic_features={},
    )

print("=" * 80)
print("TEST 1: Vision veto with 'tampered' visual_integrity")
print("=" * 80)

features = create_test_features()
vision_assessment_tampered = {
    "visual_integrity": "tampered",
    "confidence": 0.85,
    "observable_reasons": [
        "Visible editing artifacts around total amount",
        "Font inconsistency detected",
        "Digital manipulation signatures present"
    ]
}

decision = _score_and_explain(features, apply_learned=False, vision_assessment=vision_assessment_tampered)

print(f"\n📊 Decision: {decision.label}")
print(f"📈 Score: {decision.score:.2f}")
print(f"\n📋 Reasons ({len(decision.reasons)}):")
for r in decision.reasons[:5]:
    print(f"   - {r}")

print(f"\n🚨 Events ({len(decision.events)}):")
vision_events = [e for e in decision.events if e.get("rule_id") == "V1_VISION_TAMPERED"]
if vision_events:
    print(f"   ✅ Found V1_VISION_TAMPERED event!")
    for e in vision_events:
        print(f"      - Severity: {e.get('severity')}")
        print(f"      - Message: {e.get('message')}")
        print(f"      - Evidence: {e.get('evidence')}")
else:
    print(f"   ❌ No V1_VISION_TAMPERED event found!")

print(f"\n🔍 Debug info:")
print(f"   - vision_assessment in debug: {bool(decision.debug.get('vision_assessment'))}")
if decision.debug.get('vision_assessment'):
    print(f"   - visual_integrity: {decision.debug['vision_assessment'].get('visual_integrity')}")

# Verify HARD_FAIL drives label to 'fake'
assert decision.label == "fake", f"Expected label='fake', got '{decision.label}'"
assert len(vision_events) == 1, f"Expected 1 vision event, got {len(vision_events)}"
print("\n✅ TEST 1 PASSED: Vision veto correctly triggers HARD_FAIL → label=fake")

print("\n" + "=" * 80)
print("TEST 2: Vision veto with 'clean' visual_integrity (no veto)")
print("=" * 80)

features = create_test_features()
vision_assessment_clean = {
    "visual_integrity": "clean",
    "confidence": 0.90,
    "observable_reasons": []
}

decision = _score_and_explain(features, apply_learned=False, vision_assessment=vision_assessment_clean)

print(f"\n📊 Decision: {decision.label}")
print(f"📈 Score: {decision.score:.2f}")

vision_events = [e for e in decision.events if e.get("rule_id") == "V1_VISION_TAMPERED"]
if vision_events:
    print(f"\n❌ Unexpected V1_VISION_TAMPERED event found!")
else:
    print(f"\n✅ No V1_VISION_TAMPERED event (correct - visual_integrity='clean')")

# Verify no veto when clean
assert len(vision_events) == 0, f"Expected 0 vision events for 'clean', got {len(vision_events)}"
print("✅ TEST 2 PASSED: Vision veto does NOT trigger for 'clean' integrity")

print("\n" + "=" * 80)
print("TEST 3: Vision veto with 'suspicious' visual_integrity (AUDIT-ONLY, NO VETO)")
print("=" * 80)
print("⚠️  IMPORTANT: 'suspicious' is explicitly audit-only and must NOT trigger veto")
print("   This test prevents future regressions where someone 'helpfully' adds veto logic")

features = create_test_features()
vision_assessment_suspicious = {
    "visual_integrity": "suspicious",
    "confidence": 0.60,
    "observable_reasons": ["Some minor artifacts detected", "Possible scanner noise"]
}

decision = _score_and_explain(features, apply_learned=False, vision_assessment=vision_assessment_suspicious)

print(f"\n📊 Decision: {decision.label}")
print(f"📈 Score: {decision.score:.2f}")

# CRITICAL: Verify NO veto event is emitted
vision_events = [e for e in decision.events if e.get("rule_id") == "V1_VISION_TAMPERED"]
if vision_events:
    print(f"\n❌ CRITICAL FAILURE: V1_VISION_TAMPERED event found for 'suspicious'!")
    print(f"   This violates the audit-only contract for 'suspicious' visual_integrity")
    raise AssertionError("'suspicious' must NOT trigger veto events")
else:
    print(f"\n✅ No V1_VISION_TAMPERED event (correct - 'suspicious' is audit-only)")
    print(f"   'suspicious' provides context for audit reports but does NOT affect decision")

# Verify decision is based on rules, not vision
assert decision.label != "fake" or decision.score >= 0.5, "Decision should be based on rules, not vision 'suspicious'"

# Verify no veto when suspicious
assert len(vision_events) == 0, f"CRITICAL: 'suspicious' triggered {len(vision_events)} veto events (expected 0)"
print("✅ TEST 3 PASSED: 'suspicious' is audit-only, NO veto triggered")
print("   Contract verified: Only 'tampered' triggers veto, 'suspicious' is for audit/logging only")

print("\n" + "=" * 80)
print("TEST 4: No vision_assessment provided (graceful handling)")
print("=" * 80)

features = create_test_features()
decision = _score_and_explain(features, apply_learned=False, vision_assessment=None)

print(f"\n📊 Decision: {decision.label}")
print(f"📈 Score: {decision.score:.2f}")

vision_events = [e for e in decision.events if e.get("rule_id") == "V1_VISION_TAMPERED"]
assert len(vision_events) == 0, f"Expected 0 vision events when None, got {len(vision_events)}"
print("\n✅ TEST 4 PASSED: Gracefully handles None vision_assessment")

print("\n" + "=" * 80)
print("TEST 5: Backward compatibility with 'raw' field")
print("=" * 80)

features = create_test_features()
vision_assessment_raw = {
    "raw": {
        "visual_integrity": "tampered",
        "confidence": 0.80,
        "observable_reasons": ["Tampering detected in raw field"]
    }
}

decision = _score_and_explain(features, apply_learned=False, vision_assessment=vision_assessment_raw)

print(f"\n📊 Decision: {decision.label}")
vision_events = [e for e in decision.events if e.get("rule_id") == "V1_VISION_TAMPERED"]
if vision_events:
    print(f"✅ Found V1_VISION_TAMPERED event from 'raw' field!")
else:
    print(f"❌ No V1_VISION_TAMPERED event found from 'raw' field!")

assert decision.label == "fake", f"Expected label='fake' from raw field, got '{decision.label}'"
assert len(vision_events) == 1, f"Expected 1 vision event from raw, got {len(vision_events)}"
print("✅ TEST 5 PASSED: Backward compatibility with 'raw' field works")

print("\n" + "=" * 80)
print("🎉 ALL TESTS PASSED!")
print("=" * 80)
print("\n✅ Vision veto system is working correctly:")
print("   - 'tampered' → HARD_FAIL → label=fake")
print("   - 'clean' → no veto")
print("   - 'suspicious' → no veto")
print("   - None → graceful handling")
print("   - Backward compatibility with 'raw' field")
print("\n🚀 Ready for production testing with actual receipts!")
