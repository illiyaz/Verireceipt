#!/usr/bin/env python3
"""
Demo script showing where to find document tags after uploading for analysis.
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
print(f"📄 Analyzing: {test_file.name}\n")

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
print("📋 DOCUMENT TAGS - WHERE TO FIND THEM")
print("="*80)

# 1. Check rule-based results
rule_based = result.get('rule_based', {})
if rule_based:
    print("\n1️⃣  **Rule-Based Results** (result['rule_based'])")
    
    # Check debug section
    debug = rule_based.get('debug', {})
    if debug:
        doc_profile = debug.get('doc_profile', {})
        if doc_profile:
            print(f"\n   📍 Location: result['rule_based']['debug']['doc_profile']")
            print(f"\n   Document Family:    {doc_profile.get('doc_family_guess', 'N/A')}")
            print(f"   Document Subtype:   {doc_profile.get('doc_subtype_guess', 'N/A')}")
            print(f"   Confidence:         {doc_profile.get('doc_profile_confidence', 0.0):.2f}")
            print(f"   Evidence:           {doc_profile.get('doc_profile_evidence', [])}")

# 2. Check converged data
converged_data = result.get('converged_data', {})
if converged_data:
    print("\n2️⃣  **Converged Extraction Data** (result['converged_data'])")
    
    if converged_data.get('doc_family') or converged_data.get('doc_subtype'):
        print(f"\n   📍 Location: result['converged_data']")
        print(f"\n   Document Family:    {converged_data.get('doc_family', 'N/A')}")
        print(f"   Document Subtype:   {converged_data.get('doc_subtype', 'N/A')}")
        print(f"   Doc Confidence:     {converged_data.get('doc_profile_confidence', 'N/A')}")

# 3. Check ensemble reconciliation events
ensemble_verdict = result.get('ensemble_verdict', {})
rec_events = []
if ensemble_verdict:
    rec_events = ensemble_verdict.get('reconciliation_events', [])
    
    # Find ENS_DOC_PROFILE_TAGS event
    doc_profile_event = None
    for event in rec_events:
        if event.get('code') == 'ENS_DOC_PROFILE_TAGS':
            doc_profile_event = event
            break
    
    if doc_profile_event:
        print("\n3️⃣  **Ensemble Reconciliation Events** (result['ensemble_verdict']['reconciliation_events'])")
        print(f"\n   📍 Location: Find event with code='ENS_DOC_PROFILE_TAGS'")
        
        evidence = doc_profile_event.get('evidence', {})
        print(f"\n   Document Family:    {evidence.get('doc_family', 'N/A')}")
        print(f"   Document Subtype:   {evidence.get('doc_subtype', 'N/A')}")
        print(f"   Confidence:         {evidence.get('doc_profile_confidence', 'N/A')}")
        print(f"   Message:            {doc_profile_event.get('message', 'N/A')}")

# 4. Check ENS_FINAL_DECISION event
final_decision_event = None
for event in rec_events:
    if event.get('code') == 'ENS_FINAL_DECISION':
        final_decision_event = event
        break

if final_decision_event:
    print("\n4️⃣  **Final Decision Event** (result['ensemble_verdict']['reconciliation_events'])")
    print(f"\n   📍 Location: Find event with code='ENS_FINAL_DECISION'")
    
    evidence = final_decision_event.get('evidence', {})
    print(f"\n   Document Family:    {evidence.get('doc_family', 'N/A')}")
    print(f"   Document Subtype:   {evidence.get('doc_subtype', 'N/A')}")
    print(f"   Confidence:         {evidence.get('doc_profile_confidence', 'N/A')}")

print("\n" + "="*80)
print("💡 SUMMARY - HOW TO ACCESS DOCUMENT TAGS")
print("="*80)

print("""
When you upload a document via /analyze/hybrid, document tags appear in:

1. **Rule-Based Debug Info** (most detailed)
   Path: result['rule_based']['debug']['doc_profile']
   Fields:
   - doc_family_guess (TRANSACTIONAL/LOGISTICS/PAYMENT)
   - doc_subtype_guess (31 subtypes)
   - doc_profile_confidence (0.0-1.0)
   - doc_profile_evidence (list of matched keywords)

2. **Converged Data** (normalized across engines)
   Path: result['converged_data']
   Fields:
   - doc_family
   - doc_subtype
   - doc_profile_confidence

3. **Ensemble Reconciliation Events** (audit trail)
   Path: result['ensemble_verdict']['reconciliation_events']
   Find event with code='ENS_DOC_PROFILE_TAGS'
   Evidence contains: doc_family, doc_subtype, doc_profile_confidence

4. **Final Decision Event** (complete context)
   Path: result['ensemble_verdict']['reconciliation_events']
   Find event with code='ENS_FINAL_DECISION'
   Evidence contains all decision context including doc tags

5. **Persisted Audit Records** (CSV log)
   Run: python view_audit_records.py
   Shows audit_events with ENS_DOC_PROFILE_TAGS
""")

print("\n" + "="*80)
print("📊 EXAMPLE CODE TO EXTRACT TAGS")
print("="*80)

print("""
import requests

# Upload and analyze
with open('receipt.pdf', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/analyze/hybrid',
        files={'file': ('receipt.pdf', f, 'application/pdf')}
    )

result = response.json()

# Method 1: From rule-based debug
doc_profile = result['rule_based']['debug']['doc_profile']
print(f"Family: {doc_profile['doc_family_guess']}")
print(f"Subtype: {doc_profile['doc_subtype_guess']}")
print(f"Confidence: {doc_profile['doc_profile_confidence']}")
print(f"Evidence: {doc_profile['doc_profile_evidence']}")

# Method 2: From converged data
converged = result['converged_data']
print(f"Family: {converged.get('doc_family')}")
print(f"Subtype: {converged.get('doc_subtype')}")

# Method 3: From reconciliation events
for event in result['ensemble_verdict']['reconciliation_events']:
    if event['code'] == 'ENS_DOC_PROFILE_TAGS':
        evidence = event['evidence']
        print(f"Family: {evidence['doc_family']}")
        print(f"Subtype: {evidence['doc_subtype']}")
        print(f"Confidence: {evidence['doc_profile_confidence']}")
        break
""")

print("\n" + "="*80)
