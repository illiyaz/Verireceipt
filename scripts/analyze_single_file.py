#!/usr/bin/env python3
"""
Analyze a single receipt file and display detailed evidence payloads.

This script provides deep inspection of:
- All events with full evidence payloads
- Merchant candidates considered
- Empty extraction fields
- Vision assessment details
- Complete decision breakdown

Usage:
    python scripts/analyze_single_file.py <filename>
"""

import sys
import json
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.pipelines.rules import analyze_receipt

def analyze_file(filepath: str):
    """Analyze a single receipt file with detailed output."""
    file_path = Path(filepath)
    
    if not file_path.exists():
        print(f"❌ File not found: {filepath}")
        return
    
    print("=" * 80)
    print(f"📄 ANALYZING: {file_path.name}")
    print("=" * 80)
    
    try:
        decision = analyze_receipt(str(file_path))
        
        print(f"\n🎯 DECISION")
        print(f"   Label: {decision.label}")
        print(f"   Score: {decision.score:.4f}")
        print(f"   Confidence: {decision.confidence:.4f}")
        
        print(f"\n📋 TOP REASONS ({len(decision.reasons)} total)")
        for i, reason in enumerate(decision.reasons[:10], 1):
            print(f"   {i}. {reason}")
        
        print(f"\n🔍 EVENTS EVIDENCE ({len(decision.events)} events)")
        print("=" * 80)
        
        for i, event in enumerate(decision.events, 1):
            e = event if isinstance(event, dict) else event.to_dict()
            
            print(f"\n[{i}] {e.get('rule_id')} [{e.get('severity')}]")
            print(f"    Weight: {e.get('weight', 0):.4f}")
            print(f"    Message: {e.get('message', 'N/A')}")
            
            evidence = e.get('evidence', {})
            if evidence:
                print(f"    Evidence:")
                
                # Merchant candidates
                if 'merchant_candidates' in evidence:
                    print(f"      • merchant_candidates: {evidence['merchant_candidates']}")
                
                # Empty fields
                if 'empty_fields' in evidence:
                    print(f"      • empty_fields: {evidence['empty_fields']}")
                
                # Missing fields
                if 'missing_fields' in evidence:
                    print(f"      • missing_fields: {evidence['missing_fields']}")
                
                # Other important evidence
                for key, value in evidence.items():
                    if key not in ['merchant_candidates', 'empty_fields', 'missing_fields']:
                        if isinstance(value, (list, dict)):
                            print(f"      • {key}: {json.dumps(value, indent=8)}")
                        else:
                            print(f"      • {key}: {value}")
        
        # Vision assessment
        if decision.debug and "vision_assessment" in decision.debug:
            print(f"\n👁️  VISION ASSESSMENT")
            print("=" * 80)
            va = decision.debug["vision_assessment"]
            print(f"   Visual Integrity: {va.get('visual_integrity')}")
            print(f"   Confidence: {va.get('confidence')}")
            if 'observable_reasons' in va:
                print(f"   Observable Reasons:")
                for reason in va.get('observable_reasons', []):
                    print(f"      • {reason}")
        
        # Extraction fields
        if hasattr(decision, 'extracted_fields') and decision.extracted_fields:
            print(f"\n📊 EXTRACTED FIELDS")
            print("=" * 80)
            for key, value in decision.extracted_fields.items():
                if value:
                    print(f"   ✅ {key}: {value}")
                else:
                    print(f"   ❌ {key}: (empty)")
        
        # Debug info
        if decision.debug:
            print(f"\n🐛 DEBUG INFO")
            print("=" * 80)
            for key, value in decision.debug.items():
                if key != 'vision_assessment':  # Already displayed above
                    if isinstance(value, (list, dict)):
                        print(f"   {key}: {json.dumps(value, indent=6)}")
                    else:
                        print(f"   {key}: {value}")
        
        print("\n" + "=" * 80)
        print("✅ Analysis complete")
        print("=" * 80)
        
    except Exception as ex:
        print(f"\n❌ Error analyzing file: {ex}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/analyze_single_file.py <filepath>")
        print("\nExample:")
        print("  python scripts/analyze_single_file.py data/raw/81739-24-GLGA.pdf")
        sys.exit(1)
    
    analyze_file(sys.argv[1])
