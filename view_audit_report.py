#!/usr/bin/env python3
"""
View comprehensive audit report for a receipt analysis.

This script provides a human-readable, auditor-friendly view of receipt
analysis decisions, including geo-aware context and decision reasoning.

Usage:
    python view_audit_report.py <receipt_file_path>
    python view_audit_report.py --decision-id <decision_id>
    python view_audit_report.py --latest
"""

import sys
import json
import csv
from pathlib import Path
from typing import Optional, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from app.utils.audit_formatter import format_audit_for_human_review, format_audit_events_table


def load_decision_from_csv(decision_id: Optional[str] = None, latest: bool = False) -> Optional[Dict[str, Any]]:
    """Load a decision from the CSV log."""
    csv_path = Path("data/logs/decisions.csv")
    
    if not csv_path.exists():
        print(f"❌ CSV log not found: {csv_path}")
        return None
    
    decisions = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            decisions.append(row)
    
    if not decisions:
        print("❌ No decisions found in CSV log")
        return None
    
    if latest:
        # Return the most recent decision
        return decisions[-1]
    
    if decision_id:
        # Find decision by ID
        for decision in decisions:
            if decision.get("decision_id") == decision_id:
                return decision
        print(f"❌ Decision ID not found: {decision_id}")
        return None
    
    # Return latest by default
    return decisions[-1]


def parse_decision_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a CSV row into a decision dict with proper types."""
    decision = {
        "decision_id": row.get("decision_id"),
        "created_at": row.get("created_at"),
        "label": row.get("label"),
        "score": float(row.get("score", 0.0)),
        "reasons": json.loads(row.get("reasons", "[]")),
        "policy_name": row.get("policy_name", "default"),
        "policy_version": row.get("policy_version", "0.0.0"),
        "rule_version": row.get("rule_version", "0.0.0"),
        "engine_version": row.get("engine_version", "0.0.0"),
    }
    
    # Parse optional fields
    if row.get("lang_guess"):
        decision["lang_guess"] = row["lang_guess"]
    if row.get("lang_confidence"):
        decision["lang_confidence"] = float(row["lang_confidence"])
    if row.get("geo_country_guess"):
        decision["geo_country_guess"] = row["geo_country_guess"]
    if row.get("geo_confidence"):
        decision["geo_confidence"] = float(row["geo_confidence"])
    if row.get("doc_family"):
        decision["doc_family"] = row["doc_family"]
    if row.get("doc_subtype"):
        decision["doc_subtype"] = row["doc_subtype"]
    if row.get("doc_profile_confidence"):
        decision["doc_profile_confidence"] = float(row["doc_profile_confidence"])
    
    # Parse audit events
    if row.get("audit_events"):
        try:
            decision["audit_events"] = json.loads(row["audit_events"])
        except json.JSONDecodeError:
            decision["audit_events"] = []
    else:
        decision["audit_events"] = []
    
    # Parse debug info
    if row.get("debug"):
        try:
            decision["debug"] = json.loads(row["debug"])
        except json.JSONDecodeError:
            decision["debug"] = {}
    else:
        decision["debug"] = {}
    
    return decision


def analyze_receipt_file(file_path: str) -> Optional[Dict[str, Any]]:
    """Analyze a receipt file and return the decision."""
    import requests
    
    api_url = "http://localhost:8000/analyze/hybrid"
    
    try:
        with open(file_path, "rb") as f:
            files = {"file": f}
            response = requests.post(api_url, files=files, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            # Extract rule_based decision
            if "rule_based" in result:
                return result["rule_based"]
            return result
        else:
            print(f"❌ API error: {response.status_code}")
            print(response.text)
            return None
    except Exception as e:
        print(f"❌ Error analyzing file: {e}")
        return None


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python view_audit_report.py <receipt_file_path>")
        print("  python view_audit_report.py --decision-id <decision_id>")
        print("  python view_audit_report.py --latest")
        sys.exit(1)
    
    decision = None
    
    if sys.argv[1] == "--latest":
        print("Loading latest decision from CSV log...\n")
        row = load_decision_from_csv(latest=True)
        if row:
            decision = parse_decision_row(row)
    
    elif sys.argv[1] == "--decision-id":
        if len(sys.argv) < 3:
            print("❌ Please provide a decision ID")
            sys.exit(1)
        decision_id = sys.argv[2]
        print(f"Loading decision {decision_id} from CSV log...\n")
        row = load_decision_from_csv(decision_id=decision_id)
        if row:
            decision = parse_decision_row(row)
    
    else:
        # Analyze file
        file_path = sys.argv[1]
        if not Path(file_path).exists():
            print(f"❌ File not found: {file_path}")
            sys.exit(1)
        
        print(f"Analyzing receipt: {file_path}\n")
        decision = analyze_receipt_file(file_path)
    
    if not decision:
        print("❌ Could not load decision")
        sys.exit(1)
    
    # Generate comprehensive audit report
    print("\n" + "=" * 80)
    print("GENERATING COMPREHENSIVE AUDIT REPORT")
    print("=" * 80 + "\n")
    
    audit_report = format_audit_for_human_review(decision)
    print(audit_report)
    
    # Show audit events table
    if decision.get("audit_events"):
        print("\n" + "=" * 80)
        print("DETAILED AUDIT EVENTS")
        print("=" * 80 + "\n")
        events_table = format_audit_events_table(decision["audit_events"])
        print(events_table)
    
    # Show learned rules if any
    if decision.get("learned_rule_audits"):
        print("\n" + "=" * 80)
        print("LEARNED RULES APPLIED")
        print("=" * 80 + "\n")
        for i, audit in enumerate(decision["learned_rule_audits"], 1):
            print(f"{i}. Pattern: {audit.get('pattern')}")
            print(f"   Message: {audit.get('message')}")
            print(f"   Adjustment: {audit.get('confidence_adjustment', 0.0):+.2f}")
            print(f"   Times Seen: {audit.get('times_seen', 'N/A')}")
            print()


if __name__ == "__main__":
    main()
