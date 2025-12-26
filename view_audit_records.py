#!/usr/bin/env python3
"""
Utility script to view audit records from VeriReceipt analysis.

Usage:
    python view_audit_records.py                    # View latest analysis
    python view_audit_records.py --decision-id <id> # View specific decision
    python view_audit_records.py --last 5           # View last 5 analyses
"""

import json
import csv
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any


def load_latest_from_csv(csv_path: str, count: int = 1) -> List[Dict[str, Any]]:
    """Load the most recent N decisions from CSV log."""
    decisions = []
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            for row in reversed(rows[-count:]):
                decisions.append(row)
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
    return decisions


def load_by_decision_id(csv_path: str, decision_id: str) -> Optional[Dict[str, Any]]:
    """Load a specific decision by ID from CSV log."""
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('decision_id') == decision_id:
                    return row
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
    return None


def parse_json_field(value: str) -> Any:
    """Safely parse JSON field from CSV."""
    if not value or value == '[]' or value == '{}':
        return []
    try:
        return json.loads(value)
    except Exception:
        return []


def print_decision_summary(decision: Dict[str, Any], index: int = 0):
    """Pretty-print a decision with all audit trails."""
    print("\n" + "="*80)
    print(f"📄 DECISION #{index + 1}")
    print("="*80)
    
    # Basic info
    print(f"\n🔍 **Basic Information**")
    print(f"   Filename:        {decision.get('filename', 'N/A')}")
    print(f"   Decision ID:     {decision.get('decision_id', 'N/A')}")
    print(f"   Label:           {decision.get('label', 'N/A')}")
    print(f"   Score:           {decision.get('score', 'N/A')}")
    print(f"   Timestamp:       {decision.get('timestamp_utc', 'N/A')}")
    print(f"   Created At:      {decision.get('created_at', 'N/A')}")
    
    # Versioning
    print(f"\n📦 **Versioning**")
    print(f"   Rule Version:    {decision.get('rule_version', 'N/A')}")
    print(f"   Policy Version:  {decision.get('policy_version', 'N/A')}")
    print(f"   Policy Name:     {decision.get('policy_name', 'N/A')}")
    print(f"   Engine Version:  {decision.get('engine_version', 'N/A')}")
    
    # Extraction confidence
    print(f"\n📊 **Extraction Confidence**")
    print(f"   Score:           {decision.get('extraction_confidence_score', 'N/A')}")
    print(f"   Level:           {decision.get('extraction_confidence_level', 'N/A')}")
    
    # Monetary
    print(f"\n💰 **Monetary**")
    print(f"   Normalized Total: {decision.get('normalized_total', 'N/A')}")
    print(f"   Currency:         {decision.get('currency', 'N/A')}")
    
    # Audit Events (new structured trail)
    audit_events = parse_json_field(decision.get('audit_events', '[]'))
    print(f"\n🔍 **Audit Events** ({len(audit_events)} events)")
    if audit_events:
        for i, event in enumerate(audit_events, 1):
            print(f"\n   [{i}] {event.get('code', 'N/A')} ({event.get('severity', 'INFO')})")
            print(f"       Source:  {event.get('source', 'N/A')}")
            print(f"       Type:    {event.get('type', 'N/A')}")
            print(f"       Message: {event.get('message', 'N/A')}")
            print(f"       Event ID: {event.get('event_id', 'N/A')}")
            print(f"       Timestamp: {event.get('ts', 'N/A')}")
            
            evidence = event.get('evidence', {})
            if evidence:
                print(f"       Evidence:")
                for k, v in list(evidence.items())[:10]:  # Limit to first 10 keys
                    print(f"         • {k}: {v}")
    else:
        print("   ⚠️ No audit events recorded (legacy format or empty)")
    
    # Legacy Events (rule triggers)
    events = parse_json_field(decision.get('events', '[]'))
    print(f"\n⚙️ **Rule Events (Legacy)** ({len(events)} events)")
    if events:
        for i, event in enumerate(events, 1):
            print(f"\n   [{i}] {event.get('rule_id', 'N/A')} ({event.get('severity', 'INFO')})")
            print(f"       Weight:  {event.get('weight', 0.0)}")
            print(f"       Message: {event.get('message', 'N/A')}")
            
            evidence = event.get('evidence', {})
            if evidence:
                print(f"       Evidence:")
                for k, v in list(evidence.items())[:8]:
                    print(f"         • {k}: {v}")
    else:
        print("   ℹ️ No legacy rule events")
    
    # Learned Rule Audits (if present in future)
    # This field isn't in CSV yet, but will be added
    learned_audits = parse_json_field(decision.get('learned_rule_audits', '[]'))
    if learned_audits:
        print(f"\n🎓 **Learned Rule Audits** ({len(learned_audits)} audits)")
        for i, audit in enumerate(learned_audits, 1):
            print(f"\n   [{i}] Pattern: {audit.get('pattern', 'N/A')}")
            print(f"       Message: {audit.get('message', 'N/A')}")
            print(f"       Confidence Adjustment: {audit.get('confidence_adjustment', 0.0)}")
            print(f"       Times Seen: {audit.get('times_seen', 'N/A')}")
            print(f"       Severity: {audit.get('severity', 'INFO')}")
    
    print("\n" + "="*80)


def main():
    csv_path = Path(__file__).parent / "data" / "logs" / "decisions.csv"
    
    if not csv_path.exists():
        print(f"❌ CSV log not found at: {csv_path}")
        sys.exit(1)
    
    # Parse arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == '--decision-id' and len(sys.argv) > 2:
            decision_id = sys.argv[2]
            decision = load_by_decision_id(str(csv_path), decision_id)
            if decision:
                print_decision_summary(decision)
            else:
                print(f"❌ Decision ID not found: {decision_id}")
        elif sys.argv[1] == '--last' and len(sys.argv) > 2:
            count = int(sys.argv[2])
            decisions = load_latest_from_csv(str(csv_path), count)
            for i, decision in enumerate(decisions):
                print_decision_summary(decision, i)
        else:
            print("Usage:")
            print("  python view_audit_records.py                    # View latest")
            print("  python view_audit_records.py --decision-id <id> # View specific")
            print("  python view_audit_records.py --last 5           # View last 5")
    else:
        # Default: show latest
        decisions = load_latest_from_csv(str(csv_path), 1)
        if decisions:
            print_decision_summary(decisions[0])
        else:
            print("❌ No decisions found in CSV log")


if __name__ == "__main__":
    main()
