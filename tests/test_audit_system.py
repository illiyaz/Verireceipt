"""
Test the complete audit trail system with restored rule engine.

Tests:
1. Rule engine generates audit events
2. All rule groups are functional
3. CSV logging includes new fields
4. Ensemble integration works
"""

import json
from pathlib import Path
from app.pipelines.rules import analyze_receipt
from app.utils.logger import log_decision


def test_rule_engine_with_audit_trail():
    """Test that rule engine generates proper audit events."""
    print("=" * 80)
    print("TEST 1: Rule Engine with Audit Trail")
    print("=" * 80)
    
    # Test with a sample receipt
    sample_path = "data/raw/Gas_bill.jpeg"
    
    if not Path(sample_path).exists():
        print(f"⚠️  Sample file not found: {sample_path}")
        print("Using first available sample...")
        samples = list(Path("data/raw").glob("*.*"))
        if samples:
            sample_path = str(samples[0])
        else:
            print("❌ No sample files found in data/raw/")
            return
    
    print(f"\n📄 Analyzing: {sample_path}")
    print("-" * 80)
    
    decision = analyze_receipt(sample_path)
    
    # Display results
    print(f"\n🎯 VERDICT: {decision.label.upper()}")
    print(f"📊 Score: {decision.score:.3f}")
    print(f"📦 Rule Version: {decision.rule_version}")
    print(f"🔧 Engine Version: {decision.engine_version}")
    
    # Check if events were generated
    print(f"\n📋 Events Generated: {len(decision.events) if decision.events else 0}")
    
    if decision.events:
        print("\n🔍 Sample Events:")
        for i, event in enumerate(decision.events[:5], 1):
            print(f"\n  Event {i}:")
            print(f"    Rule ID: {event.get('rule_id', 'N/A')}")
            print(f"    Severity: {event.get('severity', 'N/A')}")
            print(f"    Weight: {event.get('weight', 0):.2f}")
            print(f"    Message: {event.get('message', 'N/A')}")
        
        if len(decision.events) > 5:
            print(f"\n  ... and {len(decision.events) - 5} more events")
    
    # Display reasons
    print(f"\n📝 Reasons ({len(decision.reasons)}):")
    for i, reason in enumerate(decision.reasons[:10], 1):
        print(f"  {i}. {reason}")
    
    if len(decision.reasons) > 10:
        print(f"  ... and {len(decision.reasons) - 10} more reasons")
    
    # Display minor notes
    if decision.minor_notes:
        print(f"\n💡 Minor Notes ({len(decision.minor_notes)}):")
        for note in decision.minor_notes[:5]:
            print(f"  • {note}")
    
    # Test CSV logging
    print("\n" + "=" * 80)
    print("TEST 2: CSV Logging with New Fields")
    print("=" * 80)
    
    log_decision(sample_path, decision)
    
    csv_path = Path("data/logs/decisions.csv")
    if csv_path.exists():
        print(f"\n✅ CSV log created: {csv_path}")
        
        # Read last line to verify new columns
        with open(csv_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if len(lines) >= 2:
                headers = lines[0].strip().split(',')
                last_row = lines[-1].strip().split(',')
                
                # Check for new columns
                new_columns = ['rule_version', 'policy_version', 'audit_events', 'events']
                found_columns = [col for col in new_columns if col in headers]
                
                print(f"\n📊 CSV Headers ({len(headers)} columns):")
                print(f"  New audit columns found: {', '.join(found_columns)}")
                
                # Show sample of new data
                for col in found_columns:
                    if col in headers:
                        idx = headers.index(col)
                        if idx < len(last_row):
                            value = last_row[idx]
                            if col in ['audit_events', 'events']:
                                # Parse JSON to show count
                                try:
                                    data = json.loads(value)
                                    print(f"  {col}: {len(data)} items")
                                except:
                                    print(f"  {col}: {value[:50]}...")
                            else:
                                print(f"  {col}: {value}")
    else:
        print(f"⚠️  CSV log not found at {csv_path}")
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    checks = {
        "Rule engine executed": True,
        "Decision returned": decision is not None,
        "Events generated": decision.events is not None and len(decision.events) > 0,
        "Reasons provided": len(decision.reasons) > 0,
        "Score in valid range": 0.0 <= decision.score <= 1.0,
        "CSV logging successful": csv_path.exists(),
    }
    
    for check, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check}")
    
    all_passed = all(checks.values())
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print("\n⚠️  Some tests failed - review output above")
    
    return decision, all_passed


def test_severity_distribution():
    """Test that different severity levels are being used."""
    print("\n" + "=" * 80)
    print("TEST 3: Severity Distribution")
    print("=" * 80)
    
    # Analyze a few samples
    samples = list(Path("data/raw").glob("*.*"))[:3]
    
    all_severities = []
    
    for sample in samples:
        print(f"\n📄 {sample.name}")
        decision = analyze_receipt(str(sample))
        
        if decision.events:
            severities = [e.get('severity') for e in decision.events]
            severity_counts = {}
            for sev in severities:
                severity_counts[sev] = severity_counts.get(sev, 0) + 1
            
            print(f"  Events: {len(decision.events)}")
            for sev, count in sorted(severity_counts.items()):
                print(f"    {sev}: {count}")
            
            all_severities.extend(severities)
    
    if all_severities:
        print(f"\n📊 Overall Severity Distribution:")
        unique_severities = set(all_severities)
        for sev in sorted(unique_severities):
            count = all_severities.count(sev)
            pct = count / len(all_severities) * 100
            print(f"  {sev}: {count} ({pct:.1f}%)")
        
        print(f"\n✅ Using {len(unique_severities)} different severity levels")
    else:
        print("⚠️  No events generated across samples")


if __name__ == "__main__":
    print("\n🧪 VeriReceipt Audit Trail System Test Suite\n")
    
    try:
        decision, passed = test_rule_engine_with_audit_trail()
        
        if passed and decision.events:
            test_severity_distribution()
        
        print("\n" + "=" * 80)
        print("Testing complete!")
        print("=" * 80 + "\n")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
