#!/usr/bin/env python3
"""
Show detailed evidence payload for a specific receipt file.

Usage:
    python scripts/show_evidence.py /path/to/81739-24-GLGA.pdf
"""

import sys
import json
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.pipelines.rules import analyze_receipt

def show_evidence(filepath: str):
    """Show detailed evidence for a receipt file."""
    file_path = Path(filepath)
    
    if not file_path.exists():
        print(f"❌ File not found: {filepath}")
        print(f"\nSearching for file in common locations...")
        
        # Try common locations
        possible_paths = [
            Path("data/raw") / file_path.name,
            Path("data") / file_path.name,
            Path(".") / file_path.name,
        ]
        
        for p in possible_paths:
            if p.exists():
                print(f"✅ Found at: {p}")
                file_path = p
                break
        else:
            print(f"\n❌ Could not find file: {file_path.name}")
            return
    
    print("\n" + "=" * 80)
    print(f"📄 FILE: {file_path.name}")
    print("=" * 80)
    
    try:
        decision = analyze_receipt(str(file_path))
        
        print(f"\n🎯 DECISION: {decision.label} (score: {decision.score:.4f})")
        
        print(f"\n" + "=" * 80)
        print(f"🔍 EVENTS EVIDENCE PAYLOADS ({len(decision.events)} events)")
        print("=" * 80)
        
        for i, event in enumerate(decision.events, 1):
            e = event if isinstance(event, dict) else event.to_dict()
            
            print(f"\n{'─' * 80}")
            print(f"Event #{i}: {e.get('rule_id')} [{e.get('severity')}]")
            print(f"{'─' * 80}")
            print(f"Weight: {e.get('weight', 0):.4f}")
            print(f"Message: {e.get('message', 'N/A')}")
            
            evidence = e.get('evidence', {})
            if evidence:
                print(f"\n📦 Evidence Payload:")
                print(json.dumps(evidence, indent=2, default=str))
            else:
                print(f"\n(No evidence payload)")
        
        # Show merchant candidates specifically
        print(f"\n" + "=" * 80)
        print(f"🏪 MERCHANT CANDIDATES")
        print("=" * 80)
        
        merchant_events = [e for e in decision.events 
                          if 'merchant_candidates' in (e.evidence if hasattr(e, 'evidence') else e.get('evidence', {}))]
        
        if merchant_events:
            for event in merchant_events:
                e = event if isinstance(event, dict) else event.to_dict()
                evidence = e.get('evidence', {})
                print(f"\nFrom event: {e.get('rule_id')}")
                print(f"Merchant candidates: {evidence.get('merchant_candidates', [])}")
        else:
            print("No merchant candidate information found in events")
        
        # Show empty/missing fields specifically
        print(f"\n" + "=" * 80)
        print(f"📋 EMPTY/MISSING FIELDS")
        print("=" * 80)
        
        field_events = [e for e in decision.events 
                       if any(k in (e.evidence if hasattr(e, 'evidence') else e.get('evidence', {})) 
                             for k in ['empty_fields', 'missing_fields', 'missing_elements'])]
        
        if field_events:
            for event in field_events:
                e = event if isinstance(event, dict) else event.to_dict()
                evidence = e.get('evidence', {})
                print(f"\nFrom event: {e.get('rule_id')}")
                if 'empty_fields' in evidence:
                    print(f"  Empty fields: {evidence['empty_fields']}")
                if 'missing_fields' in evidence:
                    print(f"  Missing fields: {evidence['missing_fields']}")
                if 'missing_elements' in evidence:
                    print(f"  Missing elements: {evidence['missing_elements']}")
        else:
            print("No empty/missing field information found in events")
        
        # Show extraction fields
        if hasattr(decision, 'extracted_fields') and decision.extracted_fields:
            print(f"\n" + "=" * 80)
            print(f"📊 EXTRACTED FIELDS")
            print("=" * 80)
            
            empty_fields = []
            populated_fields = []
            
            for key, value in decision.extracted_fields.items():
                if value:
                    populated_fields.append(f"✅ {key}: {value}")
                else:
                    empty_fields.append(f"❌ {key}")
            
            if populated_fields:
                print("\nPopulated fields:")
                for field in populated_fields:
                    print(f"  {field}")
            
            if empty_fields:
                print(f"\nEmpty fields ({len(empty_fields)}):")
                for field in empty_fields:
                    print(f"  {field}")
        
        print("\n" + "=" * 80)
        print("✅ Complete evidence payload displayed")
        print("=" * 80)
        
    except Exception as ex:
        print(f"\n❌ Error: {ex}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/show_evidence.py <filepath>")
        print("\nExamples:")
        print("  python scripts/show_evidence.py data/raw/81739-24-GLGA.pdf")
        print("  python scripts/show_evidence.py /full/path/to/81739-24-GLGA.pdf")
        print("  python scripts/show_evidence.py 81739-24-GLGA.pdf")
        sys.exit(1)
    
    show_evidence(sys.argv[1])
