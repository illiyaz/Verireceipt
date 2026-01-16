#!/usr/bin/env python3
"""Debug script to see what's actually in the OCR text."""

import sys
sys.path.insert(0, '.')

from app.pipelines.ingest import ingest_and_ocr
from app.schemas.receipt import ReceiptInput

# Load the document
receipt_input = ReceiptInput(file_path='data/raw/81739-24-GLGA.pdf')
raw = ingest_and_ocr(receipt_input)

# Get full text
full_text = ''
if raw.ocr_results:
    for page_result in raw.ocr_results:
        if hasattr(page_result, 'text') and page_result.text:
            full_text += page_result.text + '\n'

text_lower = full_text.lower()

# Check for logistics markers
logistics_markers = [
    'exporter', 'shipper', 'consignee',
    'hs code', 'hsn', 'customs',
    'awb', 'airway bill', 'bill of lading',
    'shipping bill', 'port of loading', 'port of discharge',
    'country of export', 'country of ultimate destination',
]

print('=' * 80)
print('LOGISTICS MARKERS FOUND')
print('=' * 80)
found_markers = []
for marker in logistics_markers:
    if marker in text_lower:
        found_markers.append(marker)
        # Find context around the marker
        idx = text_lower.find(marker)
        context_start = max(0, idx - 30)
        context_end = min(len(text_lower), idx + len(marker) + 30)
        context = text_lower[context_start:context_end]
        print(f'✓ "{marker}" found in: ...{context}...')

print(f'\n{"=" * 80}')
print(f'Total logistics hits: {len(found_markers)}')
print(f'Boost will apply: {"YES" if len(found_markers) >= 2 else "NO"}')
print('=' * 80)

# Check what keywords matched for UTILITY
print('\nUTILITY KEYWORDS:')
utility_keywords = ['electricity', 'power bill', 'water bill', 'gas bill', 'meter', 'kwh', 'water', 'bill']
for kw in utility_keywords:
    if kw in text_lower:
        print(f'✓ "{kw}" found')

print(f'\n{"=" * 80}')
print('FIRST 1500 CHARACTERS OF OCR TEXT')
print('=' * 80)
print(full_text[:1500])
