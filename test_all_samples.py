#!/usr/bin/env python3
"""Test all sample receipts in data/raw/ directory."""

import os
from pathlib import Path
from app.pipelines.rules import analyze_receipt
from app.utils.logger import log_decision


def main():
    raw_dir = Path("data/raw")
    receipt_files = [
        f for f in raw_dir.iterdir()
        if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.pdf']
    ]
    
    if not receipt_files:
        print("No receipt files found in data/raw/")
        return
    
    print(f"Found {len(receipt_files)} receipt(s) to analyze\n")
    print("=" * 80)
    
    for receipt_path in sorted(receipt_files):
        print(f"\n📄 Analyzing: {receipt_path.name}")
        print("-" * 80)
        
        try:
            decision = analyze_receipt(str(receipt_path))
            
            # Color coding for terminal
            label_display = decision.label.upper()
            if decision.label == "real":
                label_display = f"✅ {label_display}"
            elif decision.label == "suspicious":
                label_display = f"⚠️  {label_display}"
            else:
                label_display = f"❌ {label_display}"
            
            print(f"Label : {label_display}")
            print(f"Score : {decision.score:.2f}")
            
            if decision.reasons:
                print("\nReasons:")
                for r in decision.reasons:
                    print(f"  • {r}")
            
            if decision.minor_notes:
                print("\nMinor Notes:")
                for note in decision.minor_notes:
                    print(f"  • {note}")
            
            # Log decision
            log_decision(str(receipt_path), decision)
            
        except Exception as e:
            print(f"❌ Error analyzing {receipt_path.name}: {e}")
        
        print()
    
    print("=" * 80)
    print("✅ All receipts analyzed. Results logged to data/logs/decisions.csv")


if __name__ == "__main__":
    main()
