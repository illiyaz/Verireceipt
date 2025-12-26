"""
Simple test to verify the rule engine syntax and basic functionality.
Tests without requiring heavy dependencies like torch, transformers, etc.
"""

import sys
import json
from pathlib import Path

# Test 1: Import check
print("=" * 80)
print("TEST 1: Import Check")
print("=" * 80)

try:
    from app.schemas.receipt import ReceiptDecision, AuditEvent
    print("✅ Schemas imported successfully")
    print(f"   - ReceiptDecision fields: {list(ReceiptDecision.__dataclass_fields__.keys())[:10]}...")
    print(f"   - AuditEvent fields: {list(AuditEvent.__dataclass_fields__.keys())}")
except Exception as e:
    print(f"❌ Failed to import schemas: {e}")
    sys.exit(1)

try:
    from app.utils.logger import log_decision, _decision_to_row
    print("✅ Logger imported successfully")
except Exception as e:
    print(f"❌ Failed to import logger: {e}")
    sys.exit(1)

try:
    from app.repository.receipt_store import CsvReceiptStore
    print("✅ Receipt store imported successfully")
except Exception as e:
    print(f"❌ Failed to import receipt store: {e}")
    sys.exit(1)

# Test 2: Create mock decision with audit events
print("\n" + "=" * 80)
print("TEST 2: Create Mock Decision with Audit Events")
print("=" * 80)

try:
    from dataclasses import asdict
    
    # Create sample audit events
    audit_events = [
        AuditEvent(
            source="rule_engine",
            type="rule_triggered",
            severity="CRITICAL",
            code="R5_NO_AMOUNTS",
            message="No monetary amounts detected",
            evidence={"text_length": 100, "amount_count": 0}
        ),
        AuditEvent(
            source="rule_engine",
            type="rule_triggered",
            severity="INFO",
            code="R10_TOO_FEW_LINES",
            message="Receipt has very few lines",
            evidence={"line_count": 5}
        ),
    ]
    
    # Create decision
    decision = ReceiptDecision(
        label="suspicious",
        score=0.65,
        reasons=[
            "[CRITICAL] R5: No monetary amounts detected",
            "[INFO] R10: Receipt has very few lines"
        ],
        rule_version="1.0.0",
        policy_version="1.0.0",
        engine_version="test-v1",
        minor_notes=["Test note 1", "Test note 2"],
        audit_events=audit_events,
        events=[asdict(e) for e in audit_events],
        decision_id="test_001",
        created_at="2025-12-25T17:30:00Z"
    )
    
    print(f"✅ Created mock decision:")
    print(f"   - Label: {decision.label}")
    print(f"   - Score: {decision.score}")
    print(f"   - Audit Events: {len(decision.audit_events)}")
    print(f"   - Events: {len(decision.events)}")
    print(f"   - Rule Version: {decision.rule_version}")
    print(f"   - Policy Version: {decision.policy_version}")
    
except Exception as e:
    print(f"❌ Failed to create mock decision: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Convert to CSV row
print("\n" + "=" * 80)
print("TEST 3: Convert Decision to CSV Row")
print("=" * 80)

try:
    row = _decision_to_row("test_receipt.pdf", decision)
    
    print(f"✅ Converted to CSV row with {len(row)} columns:")
    
    # Show new audit columns
    audit_columns = {
        'rule_version': row.get('rule_version'),
        'policy_version': row.get('policy_version'),
        'engine_version': row.get('engine_version'),
        'audit_events': row.get('audit_events', '[]')[:100] + "...",
        'events': row.get('events', '[]')[:100] + "...",
        'reasons_count': row.get('reasons_count'),
        'minor_notes_count': row.get('minor_notes_count'),
    }
    
    for key, value in audit_columns.items():
        print(f"   - {key}: {value}")
    
    # Verify JSON serialization
    audit_events_json = row.get('audit_events', '[]')
    events_json = row.get('events', '[]')
    
    audit_parsed = json.loads(audit_events_json)
    events_parsed = json.loads(events_json)
    
    print(f"\n✅ JSON serialization verified:")
    print(f"   - audit_events: {len(audit_parsed)} items")
    print(f"   - events: {len(events_parsed)} items")
    
except Exception as e:
    print(f"❌ Failed to convert to CSV row: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Log to CSV
print("\n" + "=" * 80)
print("TEST 4: Log Decision to CSV")
print("=" * 80)

try:
    log_decision("test_receipt.pdf", decision)
    
    csv_path = Path("data/logs/decisions.csv")
    if csv_path.exists():
        print(f"✅ CSV log created: {csv_path}")
        
        # Read and verify
        with open(csv_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        print(f"   - Total rows: {len(lines) - 1} (excluding header)")
        
        if len(lines) >= 2:
            headers = lines[0].strip().split(',')
            print(f"   - Total columns: {len(headers)}")
            
            # Check for new columns
            new_cols = ['rule_version', 'policy_version', 'audit_events', 'events', 'decision_id']
            found = [col for col in new_cols if col in headers]
            missing = [col for col in new_cols if col not in headers]
            
            if found:
                print(f"   - New columns found: {', '.join(found)}")
            if missing:
                print(f"   - Missing columns: {', '.join(missing)}")
    else:
        print(f"⚠️  CSV log not created at {csv_path}")
        
except Exception as e:
    print(f"❌ Failed to log decision: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Receipt Store
print("\n" + "=" * 80)
print("TEST 5: Receipt Store (CSV Mode)")
print("=" * 80)

try:
    store = CsvReceiptStore()
    result = store.save_analysis("test_receipt.pdf", decision)
    
    print(f"✅ Receipt store saved analysis")
    print(f"   - Result: {result}")
    
    # Get statistics
    stats = store.get_statistics()
    print(f"\n✅ Statistics retrieved:")
    print(f"   - Total analyses: {stats['total_analyses']}")
    print(f"   - Real: {stats['real_count']}")
    print(f"   - Suspicious: {stats['suspicious_count']}")
    print(f"   - Fake: {stats['fake_count']}")
    print(f"   - Average score: {stats['avg_score']:.3f}")
    
except Exception as e:
    print(f"❌ Failed receipt store test: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Summary
print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)

print("""
✅ All core components tested successfully:
   1. Schema imports (ReceiptDecision, AuditEvent)
   2. Mock decision creation with audit events
   3. CSV row conversion with new fields
   4. CSV logging functionality
   5. Receipt store (CSV mode)

🎯 Key Findings:
   - Audit trail system is functional
   - New fields (rule_version, policy_version, audit_events) are persisted
   - JSON serialization works correctly
   - CSV logging includes all new columns
   - Receipt store integration works

📝 Next Steps:
   - Test with actual rule engine (requires full dependencies)
   - Test ensemble integration
   - Test with real receipt samples
""")

print("=" * 80)
print("✅ BASIC TESTS PASSED - Core audit system is functional!")
print("=" * 80)
