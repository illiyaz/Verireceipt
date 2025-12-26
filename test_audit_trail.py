#!/usr/bin/env python3
"""
Quick test to analyze a PDF and view the audit trail.
"""

import requests
import json
from pathlib import Path

# Find a test PDF
test_dir = Path('data/raw')
pdfs = list(test_dir.glob('*.pdf'))

if not pdfs:
    print("❌ No PDFs found in data/raw")
    exit(1)

test_file = pdfs[0]
print(f"📄 Testing with: {test_file.name}\n")

# Analyze via hybrid endpoint
url = 'http://localhost:8000/analyze/hybrid'

with open(test_file, 'rb') as f:
    files = {'file': (test_file.name, f, 'application/pdf')}
    response = requests.post(url, files=files, timeout=120)

if response.status_code != 200:
    print(f"❌ Error: {response.status_code}")
    print(response.text)
    exit(1)

result = response.json()

print("="*80)
print("📊 ANALYSIS RESULT")
print("="*80)
print(f"\n🏷️  Final Label: {result.get('final_label', 'N/A')}")
print(f"📈 Confidence: {result.get('confidence', 'N/A')}")
print(f"⚡ Recommended Action: {result.get('recommended_action', 'N/A')}")

# Check ensemble verdict
ensemble_verdict = result.get('ensemble_verdict', {})
if ensemble_verdict:
    print(f"\n🤖 Ensemble Verdict:")
    print(f"   Label: {ensemble_verdict.get('final_label', 'N/A')}")
    print(f"   Confidence: {ensemble_verdict.get('confidence', 'N/A')}")
    print(f"   Agreement Score: {ensemble_verdict.get('agreement_score', 'N/A')}")
    
    # Reconciliation events
    rec_events = ensemble_verdict.get('reconciliation_events', [])
    print(f"\n🔍 Reconciliation Events: {len(rec_events)}")
    
    if rec_events:
        for i, event in enumerate(rec_events, 1):
            print(f"\n   [{i}] {event.get('code', 'N/A')}")
            print(f"       Message: {event.get('message', 'N/A')}")
            print(f"       Type: {event.get('type', 'N/A')}")
            print(f"       Severity: {event.get('severity', 'INFO')}")
            
            evidence = event.get('evidence', {})
            if evidence:
                print(f"       Evidence (showing first 5 keys):")
                for k, v in list(evidence.items())[:5]:
                    val_str = str(v)
                    if len(val_str) > 60:
                        val_str = val_str[:57] + "..."
                    print(f"         • {k}: {val_str}")

# Check rule-based results
rule_based = result.get('rule_based', {})
if rule_based:
    print(f"\n⚙️  Rule-Based Analysis:")
    print(f"   Label: {rule_based.get('label', 'N/A')}")
    print(f"   Score: {rule_based.get('score', 'N/A')}")
    
    events = rule_based.get('events', [])
    if events:
        print(f"   Rule Events: {len(events)}")
        for i, event in enumerate(events[:3], 1):  # Show first 3
            print(f"      [{i}] {event.get('rule_id', 'N/A')} ({event.get('severity', 'INFO')})")
            print(f"          {event.get('message', 'N/A')}")

print("\n" + "="*80)
print("💾 Check the CSV log for persisted audit events:")
print("   python view_audit_records.py")
print("="*80)
