#!/usr/bin/env python3
"""
Run analyze_receipt on real receipt files from data/raw directory.

This script processes all receipt files in the data/raw directory and displays
comprehensive analysis results including:
- Decision label and score
- Top reasons for the decision
- Rule events triggered
- Vision assessment (if available)

Usage:
    python scripts/run_golden_real.py
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.pipelines.rules import analyze_receipt

RAW_DIR = Path("/Users/LENOVO/Documents/Projects/VeriReceipt/data/raw")

def run():
    """Run analysis on all real receipt files."""
    if not RAW_DIR.exists():
        print(f"❌ Directory not found: {RAW_DIR}")
        print(f"Please create the directory and add receipt files.")
        return
    
    files = sorted([p for p in RAW_DIR.iterdir() if p.is_file()])
    
    if not files:
        print(f"⚠️  No files found in {RAW_DIR}")
        print(f"Please add receipt files to analyze.")
        return

    print(f"🔍 Running analysis on {len(files)} real receipts\n")

    for f in files:
        print("\n" + "=" * 80)
        print(f"📄 FILE: {f.name}")
        print("=" * 80)

        try:
            decision = analyze_receipt(str(f))

            print(f"Label: {decision.label}")
            print(f"Score: {decision.score:.2f}")

            print("\nTop Reasons:")
            for r in decision.reasons[:5]:
                print(f" - {r}")

            print("\nEvents:")
            for e in decision.events:
                e = e if isinstance(e, dict) else e.to_dict()
                print(f" - {e.get('rule_id')} [{e.get('severity')}]")

            if decision.debug and "vision_assessment" in decision.debug:
                va = decision.debug["vision_assessment"]
                print("\nVision:")
                print(f" - integrity: {va.get('visual_integrity')}")
                print(f" - confidence: {va.get('confidence')}")
        
        except Exception as ex:
            print(f"❌ Error processing {f.name}: {ex}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 80)
    print(f"✅ Completed analysis of {len(files)} files")
    print("=" * 80)

if __name__ == "__main__":
    run()
