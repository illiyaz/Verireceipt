#!/usr/bin/env python3
"""
Pre-download EasyOCR models to prevent server hang on first run.
Run this once before enabling EasyOCR in production.

Usage:
    python scripts/download_easyocr.py
"""

import sys
import os

print("=" * 60)
print("EasyOCR Model Downloader")
print("=" * 60)
print()

# Check if easyocr is installed
try:
    import easyocr
    print("✅ EasyOCR package found")
except ImportError:
    print("❌ EasyOCR not installed")
    print()
    print("Please install it first:")
    print("    pip install easyocr")
    print()
    sys.exit(1)

print()
print("Downloading EasyOCR models...")
print("This will download ~500MB of data (one-time only)")
print()
print("Models will be cached in:")
print(f"    {os.path.expanduser('~/.EasyOCR/')}")
print()

try:
    # Initialize reader - this triggers model download
    print("Initializing EasyOCR reader for English...")
    reader = easyocr.Reader(['en'], gpu=False, verbose=True)
    print()
    print("=" * 60)
    print("✅ SUCCESS! EasyOCR models downloaded")
    print("=" * 60)
    print()
    print("You can now enable EasyOCR:")
    print("    ENABLE_EASYOCR=true python run_web_demo.py")
    print()
    
    # Test it works
    print("Testing EasyOCR...")
    import numpy as np
    from PIL import Image
    
    # Create a simple test image with text
    test_img = Image.new('RGB', (200, 50), color='white')
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(test_img)
    draw.text((10, 10), "TEST 123", fill='black')
    
    # Convert to numpy array
    img_array = np.array(test_img)
    
    # Run OCR
    results = reader.readtext(img_array, detail=0)
    print(f"✅ Test successful! Detected: {results}")
    print()
    
except Exception as e:
    print()
    print("=" * 60)
    print("❌ ERROR during download")
    print("=" * 60)
    print(f"Error: {e}")
    print()
    print("Troubleshooting:")
    print("1. Check internet connection")
    print("2. Check disk space (~500MB needed)")
    print("3. Try again - downloads can be flaky")
    print()
    sys.exit(1)
