#!/usr/bin/env python3
"""
Debug script to trace receipt analysis step-by-step.
Shows exactly what's being extracted and why decisions are made.
"""

import sys
from pathlib import Path
from datetime import datetime

def debug_receipt(file_path: str):
    """Debug a receipt file step by step."""
    
    print("=" * 80)
    print(f"🔍 DEBUGGING: {file_path}")
    print("=" * 80)
    print()
    
    # Step 1: Check file exists
    print("📁 STEP 1: File Check")
    print("-" * 80)
    path = Path(file_path)
    if not path.exists():
        print(f"❌ File not found: {file_path}")
        return
    print(f"✅ File exists: {path.name}")
    print(f"   Size: {path.stat().st_size / 1024:.2f} KB")
    print(f"   Extension: {path.suffix}")
    print()
    
    # Step 2: Extract metadata
    print("📋 STEP 2: Metadata Extraction")
    print("-" * 80)
    
    from app.pipelines.metadata import extract_pdf_metadata, extract_image_metadata
    
    if path.suffix.lower() == '.pdf':
        meta = extract_pdf_metadata(str(path))
        print("📄 PDF Metadata:")
    else:
        meta = extract_image_metadata(str(path))
        print("🖼️  Image Metadata:")
    
    print(f"   Producer: {meta.get('producer')}")
    print(f"   Creator: {meta.get('creator')}")
    print(f"   Creation Date: {meta.get('creation_date')}")
    print(f"   Mod Date: {meta.get('mod_date')}")
    print(f"   Title: {meta.get('title')}")
    print(f"   Author: {meta.get('author')}")
    
    if path.suffix.lower() != '.pdf':
        print(f"   Software: {meta.get('Software')}")
        print(f"   EXIF Present: {meta.get('exif_present')}")
        print(f"   EXIF Keys: {meta.get('exif_keys_count')}")
    
    print()
    
    # Step 3: Check suspicious producer
    print("🚨 STEP 3: Suspicious Producer Check")
    print("-" * 80)
    
    from app.pipelines.features import SUSPICIOUS_PRODUCERS
    
    producer = (meta.get('producer') or meta.get('creator') or meta.get('Software') or "").lower()
    print(f"   Producer (lowercase): '{producer}'")
    print(f"   Suspicious producers list: {SUSPICIOUS_PRODUCERS}")
    
    is_suspicious = any(p in producer for p in SUSPICIOUS_PRODUCERS)
    if is_suspicious:
        print(f"   ✅ MATCH FOUND! This is a suspicious producer!")
    else:
        print(f"   ❌ No match. Not flagged as suspicious.")
    print()
    
    # Step 4: Ingest and OCR
    print("📸 STEP 4: Image Loading & OCR")
    print("-" * 80)
    
    try:
        from app.pipelines.ingest import ingest_and_ocr
        from app.schemas.receipt import ReceiptInput
        
        inp = ReceiptInput(file_path=str(path))
        raw = ingest_and_ocr(inp)
        
        print(f"   ✅ Successfully loaded {raw.num_pages} page(s)")
        print(f"   Image sizes: {[f'{img.width}x{img.height}' for img in raw.images]}")
        print()
        print("   OCR Text (first 500 chars):")
        print("   " + "-" * 76)
        for i, text in enumerate(raw.ocr_text_per_page):
            print(f"   Page {i+1}:")
            print("   " + text[:500].replace('\n', '\n   '))
            if len(text) > 500:
                print(f"   ... ({len(text) - 500} more characters)")
        print()
        
    except Exception as e:
        print(f"   ❌ Failed to load/OCR: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 5: Extract features
    print("🔬 STEP 5: Feature Extraction")
    print("-" * 80)
    
    try:
        from app.pipelines.features import build_features
        
        feats = build_features(raw)
        
        print("   File Features:")
        ff = feats.file_features
        print(f"      suspicious_producer: {ff.get('suspicious_producer')}")
        print(f"      has_creation_date: {ff.get('has_creation_date')}")
        print(f"      creation_date: {ff.get('creation_date')}")
        print(f"      has_mod_date: {ff.get('has_mod_date')}")
        print(f"      mod_date: {ff.get('mod_date')}")
        print()
        
        print("   Text Features:")
        tf = feats.text_features
        print(f"      has_date: {tf.get('has_date')}")
        print(f"      receipt_date: {tf.get('receipt_date')}")
        print(f"      merchant_candidate: {tf.get('merchant_candidate')}")
        print(f"      has_any_amount: {tf.get('has_any_amount')}")
        print(f"      total_amount: {tf.get('total_amount')}")
        print()
        
        print("   Layout Features:")
        lf = feats.layout_features
        print(f"      num_lines: {lf.get('num_lines')}")
        print(f"      numeric_line_ratio: {lf.get('numeric_line_ratio'):.2f}")
        print()
        
    except Exception as e:
        print(f"   ❌ Failed to extract features: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 6: Date comparison
    print("📅 STEP 6: Date Mismatch Check (R15)")
    print("-" * 80)
    
    creation_date_raw = ff.get('creation_date')
    receipt_date_str = tf.get('receipt_date')
    
    print(f"   Creation date (raw): {creation_date_raw}")
    print(f"   Receipt date (extracted): {receipt_date_str}")
    
    if not ff.get('has_creation_date'):
        print(f"   ⚠️  No creation date in metadata")
    elif not receipt_date_str:
        print(f"   ⚠️  No receipt date found in OCR text")
    else:
        try:
            # Parse creation date
            if isinstance(creation_date_raw, str):
                creation_date = None
                for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M%S"]:
                    try:
                        creation_date = datetime.strptime(creation_date_raw.split()[0], fmt)
                        break
                    except:
                        continue
                if not creation_date:
                    try:
                        creation_date = datetime.fromisoformat(creation_date_raw.replace('Z', '+00:00'))
                    except:
                        pass
            else:
                creation_date = creation_date_raw
            
            # Parse receipt date
            receipt_date = datetime.strptime(receipt_date_str, "%Y-%m-%d")
            
            if creation_date and receipt_date:
                days_diff = (creation_date.date() - receipt_date.date()).days
                
                print(f"   ✅ Parsed successfully!")
                print(f"      Creation: {creation_date.date()}")
                print(f"      Receipt:  {receipt_date.date()}")
                print(f"      Difference: {days_diff} days")
                print()
                
                if days_diff < -1:
                    print(f"   🚨 CRITICAL: Receipt date is {abs(days_diff)} days AFTER creation!")
                    print(f"      This should add +0.4 to fraud score")
                elif days_diff > 2:
                    print(f"   ⚠️  SUSPICIOUS: File created {days_diff} days after receipt date")
                    print(f"      This should add +0.35 to fraud score")
                else:
                    print(f"   ✅ Normal: Receipt scanned within {days_diff} days")
            else:
                print(f"   ❌ Failed to parse dates")
                print(f"      creation_date object: {creation_date}")
                print(f"      receipt_date object: {receipt_date}")
                
        except Exception as e:
            print(f"   ❌ Date comparison failed: {e}")
            import traceback
            traceback.print_exc()
    
    print()
    
    # Step 7: Run full analysis
    print("⚖️  STEP 7: Full Rule-Based Analysis")
    print("-" * 80)
    
    try:
        from app.pipelines.rules import analyze_receipt
        
        decision = analyze_receipt(str(path))
        
        print(f"   Label: {decision.label.upper()}")
        print(f"   Score: {decision.score:.3f}")
        print()
        print("   Reasons:")
        for reason in decision.reasons:
            print(f"      • {reason}")
        print()
        
        if decision.minor_notes:
            print("   Minor Notes:")
            for note in decision.minor_notes:
                print(f"      • {note}")
        print()
        
    except Exception as e:
        print(f"   ❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Step 8: Summary
    print("=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print()
    
    issues = []
    
    if not is_suspicious and producer:
        issues.append(f"❌ Producer '{producer}' not in suspicious list")
    
    if ff.get('has_creation_date') and receipt_date_str:
        if 'days_diff' in locals() and days_diff > 2:
            issues.append(f"❌ Date mismatch ({days_diff} days) not caught")
    
    if not issues:
        print("✅ All checks working correctly!")
    else:
        print("🚨 Issues Found:")
        for issue in issues:
            print(f"   {issue}")
    
    print()
    print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug_receipt.py <receipt_file>")
        print()
        print("Examples:")
        print('  python debug_receipt.py "Apple Macbook mouse monitor.pdf"')
        print('  python debug_receipt.py "C Test2.jpg"')
        sys.exit(1)
    
    debug_receipt(sys.argv[1])
