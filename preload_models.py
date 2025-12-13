#!/usr/bin/env python
"""Pre-load all models to avoid meta tensor issues"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

print("=" * 60)
print("Pre-loading VeriReceipt Models")
print("=" * 60)

# Pre-load DONUT
print("\n1. Loading DONUT...")
try:
    from app.pipelines.donut_extractor import get_donut_extractor
    extractor = get_donut_extractor()
    extractor.load_model()  # Force load
    print("✅ DONUT loaded successfully")
except Exception as e:
    print(f"❌ DONUT failed: {e}")

# Pre-load Donut-Receipt
print("\n2. Loading Donut-Receipt...")
try:
    from app.models.donut_receipt import DonutReceiptModel
    model = DonutReceiptModel()
    print("✅ Donut-Receipt loaded successfully")
except Exception as e:
    print(f"❌ Donut-Receipt failed: {e}")

# Pre-load LayoutLM
print("\n3. Loading LayoutLM...")
try:
    from app.pipelines.layoutlm_extractor import get_layoutlm_extractor
    extractor = get_layoutlm_extractor()
    extractor.load_model()  # Force load
    print("✅ LayoutLM loaded successfully")
except Exception as e:
    print(f"❌ LayoutLM failed: {e}")

print("\n" + "=" * 60)
print("Model pre-loading complete!")
print("=" * 60)
