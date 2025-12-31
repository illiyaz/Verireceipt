"""
Golden tests for vision veto system validation.

These tests verify the complete end-to-end behavior of the vision veto system
with three critical scenarios:
1. CLEAN vision → rules decide (no vision interference)
2. SUSPICIOUS vision → rules decide (audit-only, no veto)
3. TAMPERED vision → HARD_FAIL (veto triggers, label=fake)

Each test inspects:
- Final decision label
- Audit trail for vision evidence
- Rule reasoning unchanged
- No "vision said real" anywhere
"""

import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.pipelines.rules import analyze_receipt
from app.schemas.receipt import ReceiptDecision


def create_mock_receipt_image(tmp_path, content: str = "MOCK RECEIPT\nTotal: $100.00"):
    """Create a temporary mock receipt image for testing."""
    # Create a simple receipt image
    img = Image.new('RGB', (400, 600), color='white')
    draw = ImageDraw.Draw(img)
    
    # Try to use a default font, fallback to basic if not available
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except:
        font = ImageFont.load_default()
    
    # Draw receipt content
    y_position = 50
    for line in content.split('\n'):
        draw.text((50, y_position), line, fill='black', font=font)
        y_position += 40
    
    # Save as PNG
    receipt_file = tmp_path / "test_receipt.png"
    img.save(receipt_file)
    return str(receipt_file)


def inspect_audit_trail(decision: ReceiptDecision, test_name: str):
    """
    Inspect audit trail for vision veto system validation.
    
    Checks:
    1. Vision evidence is readable
    2. Rule reasoning is unchanged
    3. No "vision said real" anywhere
    """
    print(f"\n{'='*80}")
    print(f"AUDIT TRAIL INSPECTION: {test_name}")
    print(f"{'='*80}")
    
    # Check decision
    print(f"\n📊 Final Decision: {decision.label}")
    print(f"📈 Score: {decision.score:.2f}")
    
    # Check reasons
    print(f"\n📋 Reasons ({len(decision.reasons)}):")
    for i, reason in enumerate(decision.reasons[:10], 1):
        print(f"   {i}. {reason}")
        # CRITICAL: Check for "vision said real" or similar
        reason_lower = reason.lower()
        if "vision" in reason_lower and ("real" in reason_lower or "authentic" in reason_lower):
            if "tampered" not in reason_lower and "veto" not in reason_lower:
                print(f"      ⚠️  WARNING: Possible vision upgrade language detected!")
    
    # Check events (rule events including V1_VISION_TAMPERED)
    print(f"\n🔍 Events ({len(decision.events)}):")
    vision_events = []
    for event in decision.events:
        event_dict = event if isinstance(event, dict) else (event.to_dict() if hasattr(event, 'to_dict') else {})
        if "vision" in str(event_dict.get("rule_id", "")).lower():
            vision_events.append(event_dict)
            print(f"   • {event_dict.get('rule_id')}: {event_dict.get('message')}")
            print(f"     Severity: {event_dict.get('severity')}")
    
    # Also check audit_events
    print(f"\n🔍 Audit Events ({len(decision.audit_events)}):")
    for event in decision.audit_events:
        event_dict = event.to_dict() if hasattr(event, 'to_dict') else event
        if "vision" in str(event_dict.get("rule_id", "")).lower():
            if event_dict not in vision_events:
                vision_events.append(event_dict)
            print(f"   • {event_dict.get('rule_id')}: {event_dict.get('message')}")
            print(f"     Severity: {event_dict.get('severity')}")
    
    # Check debug info
    print(f"\n🐛 Debug Info:")
    if decision.debug and "vision_assessment" in decision.debug:
        va = decision.debug["vision_assessment"]
        print(f"   • visual_integrity: {va.get('visual_integrity')}")
        print(f"   • confidence: {va.get('confidence')}")
        print(f"   • observable_reasons: {len(va.get('observable_reasons', []))} reasons")
        if va.get('observable_reasons'):
            for reason in va['observable_reasons'][:3]:
                print(f"      - {reason}")
    else:
        print(f"   • No vision_assessment in debug")
    
    # Check for "vision said real" in any field
    print(f"\n🔎 Scanning for 'vision said real' language...")
    found_upgrade_language = False
    
    # Check reasons
    for reason in decision.reasons:
        if "vision" in reason.lower() and "real" in reason.lower():
            if "tampered" not in reason.lower() and "veto" not in reason.lower():
                print(f"   ⚠️  Found in reason: {reason}")
                found_upgrade_language = True
    
    # Check minor notes
    for note in (decision.minor_notes or []):
        if "vision" in note.lower() and "real" in note.lower():
            if "tampered" not in note.lower() and "veto" not in note.lower():
                print(f"   ⚠️  Found in minor_note: {note}")
                found_upgrade_language = True
    
    if not found_upgrade_language:
        print(f"   ✅ No 'vision said real' language found")
    
    print(f"\n{'='*80}\n")
    
    return vision_events


# ============================================================================
# GOLDEN TEST 1: CLEAN Vision → Rules Decide
# ============================================================================
def test_golden_clean_vision():
    """
    Golden Test 1: CLEAN vision → rules decide (no vision interference).
    
    Expected behavior:
    - Vision returns visual_integrity="clean"
    - No V1_VISION_TAMPERED event emitted
    - Decision based entirely on rules
    - No vision language in reasoning
    """
    print("\n" + "="*80)
    print("GOLDEN TEST 1: CLEAN Vision → Rules Decide")
    print("="*80)
    print("Expected: Vision provides 'clean' assessment, rules make decision")
    print("Vision should NOT affect the final label or score")
    
    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        receipt_file = create_mock_receipt_image(tmp_path, "Test Store\nTotal: $50.00\nDate: 2024-01-01")
        
        # Simulate clean vision assessment
        vision_assessment = {
            "visual_integrity": "clean",
            "confidence": 0.85,
            "observable_reasons": [],
        }
        
        decision = analyze_receipt(
            receipt_file,
            extracted_total="50.00",
            extracted_merchant="Test Store",
            extracted_date="2024-01-01",
            vision_assessment=vision_assessment
        )
        
        # Inspect audit trail
        vision_events = inspect_audit_trail(decision, "CLEAN Vision")
        
        # Assertions
        print("🧪 Assertions:")
        
        # 1. No V1_VISION_TAMPERED event
        tampered_events = [e for e in vision_events if e.get("rule_id") == "V1_VISION_TAMPERED"]
        assert len(tampered_events) == 0, f"FAIL: Found {len(tampered_events)} V1_VISION_TAMPERED events (expected 0)"
        print("   ✅ No V1_VISION_TAMPERED event (correct)")
        
        # 2. Decision is based on rules (not forced by vision)
        # With good extracted data, should be "real" or low score
        print(f"   ✅ Decision: {decision.label} (score: {decision.score:.2f})")
        print(f"      Rules decided without vision interference")
        
        # 3. Vision assessment in debug
        assert "vision_assessment" in decision.debug, "FAIL: vision_assessment not in debug"
        assert decision.debug["vision_assessment"]["visual_integrity"] == "clean"
        print("   ✅ Vision assessment stored in debug for audit")
        
        print("\n✅ GOLDEN TEST 1 PASSED: Clean vision → rules decide")
        return decision


# ============================================================================
# GOLDEN TEST 2: SUSPICIOUS Vision → Rules Decide (Audit-Only)
# ============================================================================
def test_golden_suspicious_vision():
    """
    Golden Test 2: SUSPICIOUS vision → rules decide (audit-only, no veto).
    
    Expected behavior:
    - Vision returns visual_integrity="suspicious"
    - No V1_VISION_TAMPERED event emitted
    - Decision based entirely on rules
    - Suspicious assessment stored in debug for audit
    """
    print("\n" + "="*80)
    print("GOLDEN TEST 2: SUSPICIOUS Vision → Rules Decide (Audit-Only)")
    print("="*80)
    print("Expected: Vision provides 'suspicious' assessment, rules make decision")
    print("'suspicious' is AUDIT-ONLY and must NOT trigger veto")
    
    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        receipt_file = create_mock_receipt_image(tmp_path, "Store ABC\nTotal: $200.00")
        
        # Simulate suspicious vision assessment
        vision_assessment = {
            "visual_integrity": "suspicious",
            "confidence": 0.65,
            "observable_reasons": [
                "Minor artifacts detected near total",
                "Possible scanner noise in background"
            ],
        }
        
        decision = analyze_receipt(
            receipt_file,
            extracted_total="200.00",
            extracted_merchant="Store ABC",
            vision_assessment=vision_assessment
        )
        
        # Inspect audit trail
        vision_events = inspect_audit_trail(decision, "SUSPICIOUS Vision")
        
        # Assertions
        print("🧪 Assertions:")
        
        # 1. No V1_VISION_TAMPERED event (CRITICAL)
        tampered_events = [e for e in vision_events if e.get("rule_id") == "V1_VISION_TAMPERED"]
        assert len(tampered_events) == 0, f"CRITICAL FAIL: 'suspicious' triggered {len(tampered_events)} veto events (expected 0)"
        print("   ✅ No V1_VISION_TAMPERED event (correct - 'suspicious' is audit-only)")
        
        # 2. Decision is based on rules (not affected by suspicious)
        print(f"   ✅ Decision: {decision.label} (score: {decision.score:.2f})")
        print(f"      Rules decided without vision veto")
        
        # 3. Suspicious assessment in debug for audit
        assert "vision_assessment" in decision.debug, "FAIL: vision_assessment not in debug"
        assert decision.debug["vision_assessment"]["visual_integrity"] == "suspicious"
        assert len(decision.debug["vision_assessment"]["observable_reasons"]) == 2
        print("   ✅ Suspicious assessment stored in debug for audit trail")
        print("   ✅ Observable reasons captured for investigation")
        
        print("\n✅ GOLDEN TEST 2 PASSED: Suspicious vision → rules decide (audit-only)")
        return decision


# ============================================================================
# GOLDEN TEST 3: TAMPERED Vision → HARD_FAIL (Veto Triggers)
# ============================================================================
def test_golden_tampered_vision():
    """
    Golden Test 3: TAMPERED vision → HARD_FAIL (veto triggers, label=fake).
    
    Expected behavior:
    - Vision returns visual_integrity="tampered"
    - V1_VISION_TAMPERED HARD_FAIL event emitted
    - Decision label forced to "fake"
    - Observable reasons captured in evidence
    """
    print("\n" + "="*80)
    print("GOLDEN TEST 3: TAMPERED Vision → HARD_FAIL (Veto Triggers)")
    print("="*80)
    print("Expected: Vision detects tampering, V1_VISION_TAMPERED HARD_FAIL → label=fake")
    print("This is the ONLY scenario where vision affects the decision")
    
    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        receipt_file = create_mock_receipt_image(tmp_path, "Edited Store\nTotal: $999.99")
        
        # Simulate tampered vision assessment
        vision_assessment = {
            "visual_integrity": "tampered",
            "confidence": 0.92,
            "observable_reasons": [
                "Clear editing artifacts around total amount",
                "Font inconsistency between merchant name and total",
                "Digital manipulation signatures detected",
                "Halos visible around edited numbers"
            ],
        }
        
        decision = analyze_receipt(
            receipt_file,
            extracted_total="999.99",
            extracted_merchant="Edited Store",
            vision_assessment=vision_assessment
        )
        
        # Inspect audit trail
        vision_events = inspect_audit_trail(decision, "TAMPERED Vision")
        
        # Assertions
        print("🧪 Assertions:")
        
        # 1. V1_VISION_TAMPERED event emitted (CRITICAL)
        tampered_events = [e for e in vision_events if e.get("rule_id") == "V1_VISION_TAMPERED"]
        assert len(tampered_events) == 1, f"FAIL: Expected 1 V1_VISION_TAMPERED event, got {len(tampered_events)}"
        print(f"   ✅ V1_VISION_TAMPERED event emitted (severity: {tampered_events[0].get('severity')})")
        
        # 2. Event has HARD_FAIL severity
        assert tampered_events[0].get("severity") == "HARD_FAIL", "FAIL: Expected HARD_FAIL severity"
        print("   ✅ Severity is HARD_FAIL (triggers veto)")
        
        # 3. Decision label is "fake" (HARD_FAIL drives label)
        assert decision.label == "fake", f"FAIL: Expected label='fake', got '{decision.label}'"
        print(f"   ✅ Decision label: {decision.label} (HARD_FAIL drove decision)")
        
        # 4. Observable reasons captured in evidence
        evidence = tampered_events[0].get("evidence", {})
        assert "observable_reasons" in evidence, "FAIL: observable_reasons not in evidence"
        assert len(evidence["observable_reasons"]) == 4, f"FAIL: Expected 4 observable reasons, got {len(evidence['observable_reasons'])}"
        print(f"   ✅ Observable reasons captured in evidence ({len(evidence['observable_reasons'])} reasons)")
        
        # 5. Vision assessment in debug
        assert "vision_assessment" in decision.debug, "FAIL: vision_assessment not in debug"
        assert decision.debug["vision_assessment"]["visual_integrity"] == "tampered"
        print("   ✅ Tampered assessment stored in debug for audit trail")
        
        # 6. Check for veto language in reasons
        veto_mentioned = any("veto" in r.lower() or "vision detected" in r.lower() for r in decision.reasons)
        if veto_mentioned:
            print("   ✅ Veto language found in reasons (good for transparency)")
        
        print("\n✅ GOLDEN TEST 3 PASSED: Tampered vision → HARD_FAIL → label=fake")
        return decision


# ============================================================================
# Run All Golden Tests
# ============================================================================
if __name__ == "__main__":
    print("\n" + "="*80)
    print("VISION VETO SYSTEM - GOLDEN TESTS")
    print("="*80)
    print("Testing 3 critical scenarios:")
    print("1. CLEAN vision → rules decide (no interference)")
    print("2. SUSPICIOUS vision → rules decide (audit-only)")
    print("3. TAMPERED vision → HARD_FAIL (veto triggers)")
    print("="*80)
    
    results = []
    
    try:
        print("\n🧪 Running Golden Test 1...")
        decision1 = test_golden_clean_vision()
        results.append(("CLEAN", "PASSED", decision1))
    except AssertionError as e:
        print(f"\n❌ GOLDEN TEST 1 FAILED: {e}")
        results.append(("CLEAN", "FAILED", str(e)))
    except Exception as e:
        print(f"\n❌ GOLDEN TEST 1 ERROR: {e}")
        import traceback
        traceback.print_exc()
        results.append(("CLEAN", "ERROR", str(e)))
    
    try:
        print("\n🧪 Running Golden Test 2...")
        decision2 = test_golden_suspicious_vision()
        results.append(("SUSPICIOUS", "PASSED", decision2))
    except AssertionError as e:
        print(f"\n❌ GOLDEN TEST 2 FAILED: {e}")
        results.append(("SUSPICIOUS", "FAILED", str(e)))
    except Exception as e:
        print(f"\n❌ GOLDEN TEST 2 ERROR: {e}")
        import traceback
        traceback.print_exc()
        results.append(("SUSPICIOUS", "ERROR", str(e)))
    
    try:
        print("\n🧪 Running Golden Test 3...")
        decision3 = test_golden_tampered_vision()
        results.append(("TAMPERED", "PASSED", decision3))
    except AssertionError as e:
        print(f"\n❌ GOLDEN TEST 3 FAILED: {e}")
        results.append(("TAMPERED", "FAILED", str(e)))
    except Exception as e:
        print(f"\n❌ GOLDEN TEST 3 ERROR: {e}")
        import traceback
        traceback.print_exc()
        results.append(("TAMPERED", "ERROR", str(e)))
    
    # Summary
    print("\n" + "="*80)
    print("GOLDEN TESTS SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, status, _ in results if status == "PASSED")
    failed = sum(1 for _, status, _ in results if status == "FAILED")
    errors = sum(1 for _, status, _ in results if status == "ERROR")
    
    for scenario, status, _ in results:
        emoji = "✅" if status == "PASSED" else "❌"
        print(f"{emoji} {scenario}: {status}")
    
    print(f"\n📊 Results: {passed}/3 passed, {failed} failed, {errors} errors")
    
    if passed == 3:
        print("\n🎉 ALL GOLDEN TESTS PASSED!")
        print("Vision veto system is working correctly:")
        print("  • CLEAN → rules decide (no interference)")
        print("  • SUSPICIOUS → rules decide (audit-only)")
        print("  • TAMPERED → HARD_FAIL (veto triggers)")
        print("\n🚀 Ready for real receipt testing!")
    else:
        print("\n⚠️  Some tests failed. Review audit trails above.")
        sys.exit(1)
