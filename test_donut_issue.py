#!/usr/bin/env python3
"""
Test DONUT to diagnose why it's not completing properly.
"""

import sys
from pathlib import Path

print("="*80)
print("DONUT Diagnostic Test")
print("="*80)

# Check if DONUT is available
try:
    from app.pipelines.donut_extractor import DONUT_AVAILABLE, extract_receipt_with_donut
    print(f"\n✅ DONUT Available: {DONUT_AVAILABLE}")
except ImportError as e:
    print(f"\n❌ Import Error: {e}")
    sys.exit(1)

if not DONUT_AVAILABLE:
    print("\n❌ DONUT dependencies not installed")
    print("Install with: pip install transformers torch pillow sentencepiece")
    sys.exit(1)

# Test on a sample receipt
test_file = "data/raw/Gas_bill.jpeg"
if not Path(test_file).exists():
    print(f"\n❌ Test file not found: {test_file}")
    sys.exit(1)

print(f"\n📄 Testing on: {test_file}")
print("⏳ This may take 10-20 seconds (model loading + inference)...\n")

try:
    import time
    start = time.time()
    
    result = extract_receipt_with_donut(test_file)
    
    elapsed = time.time() - start
    print(f"\n✅ DONUT completed in {elapsed:.1f}s")
    
    # Check what was extracted
    print("\n" + "="*80)
    print("DONUT Extraction Results")
    print("="*80)
    
    print(f"\nMerchant: {result.get('merchant', 'N/A')}")
    print(f"Total: ${result.get('total', 'N/A')}")
    print(f"Line Items: {len(result.get('line_items', []))}")
    print(f"Data Quality: {result.get('data_quality', 'N/A')}")
    
    # Show raw output
    print("\n" + "="*80)
    print("Raw DONUT Output (first 500 chars)")
    print("="*80)
    import json
    raw = json.dumps(result.get('raw_donut_output', {}), indent=2)
    print(raw[:500])
    if len(raw) > 500:
        print("...")
    
    # Diagnose the issue
    print("\n" + "="*80)
    print("Diagnosis")
    print("="*80)
    
    issues = []
    
    if not result.get('merchant'):
        issues.append("❌ Merchant not extracted")
    else:
        print("✅ Merchant extracted")
    
    if not result.get('total'):
        issues.append("❌ Total amount not extracted")
    else:
        print("✅ Total amount extracted")
    
    if len(result.get('line_items', [])) == 0:
        issues.append("❌ No line items extracted")
    else:
        print(f"✅ {len(result.get('line_items', []))} line items extracted")
    
    if issues:
        print("\n⚠️  Issues Found:")
        for issue in issues:
            print(f"   {issue}")
        
        print("\n💡 Why DONUT might fail:")
        print("   1. Model trained on CORD dataset (Korean receipts)")
        print("   2. Your receipt format doesn't match CORD format")
        print("   3. Receipt is in different language/layout")
        print("   4. Model can't parse the specific receipt structure")
        
        print("\n💡 Solutions:")
        print("   1. Use DONUT only for validation, not primary extraction")
        print("   2. Fine-tune DONUT on your receipt format")
        print("   3. Use alternative models (LayoutLM, TrOCR)")
        print("   4. Rely on Rule-Based + Vision LLM instead")
    else:
        print("\n✅ DONUT working well!")
    
    print("\n" + "="*80)
    
except Exception as e:
    print(f"\n❌ Error running DONUT: {e}")
    import traceback
    print("\nFull traceback:")
    traceback.print_exc()
    sys.exit(1)
