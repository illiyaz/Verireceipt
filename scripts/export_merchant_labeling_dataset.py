#!/usr/bin/env python3
"""
Export merchant extraction results for human labeling.

Generates:
- doc_level.jsonl: One JSON object per document with full EntityResult V2 payload
- candidate_level.csv: Flattened candidate rows for analysis
- manifest.csv: Summary of all documents with key metrics
"""

import argparse
import json
import csv
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.pipelines.features import _guess_merchant_entity


def redact_text(text: str, keep_tokens: int = 2) -> str:
    """Redact text keeping only first N tokens."""
    if not text:
        return text
    
    tokens = text.split()
    if len(tokens) <= keep_tokens:
        return text
    
    kept = ' '.join(tokens[:keep_tokens])
    return f"{kept} …"


def redact_phone_patterns(text: str) -> str:
    """Remove phone number patterns."""
    # Match common phone patterns
    text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[PHONE]', text)
    text = re.sub(r'\(\d{3}\)\s*\d{3}[-.]?\d{4}', '[PHONE]', text)
    return text


def redact_address_patterns(text: str) -> str:
    """Remove address-like patterns."""
    # Match street addresses (simplified)
    text = re.sub(r'\b\d+\s+[A-Z][a-z]+\s+(Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr)\b', 
                  '[ADDRESS]', text, flags=re.IGNORECASE)
    return text


def redact_debug_context(debug_context: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Redact PII from debug context."""
    if not debug_context:
        return debug_context
    
    redacted = debug_context.copy()
    
    # Redact first_40_lines
    if 'first_40_lines' in redacted and redacted['first_40_lines']:
        redacted_lines = []
        for line in redacted['first_40_lines']:
            line = redact_phone_patterns(line)
            line = redact_address_patterns(line)
            redacted_lines.append(line)
        redacted['first_40_lines'] = redacted_lines
    
    return redacted


def load_ocr_lines_from_file(file_path: Path) -> List[str]:
    """Load OCR lines from a file."""
    if file_path.suffix == '.json':
        # Assume JSON with 'lines' or 'ocr_lines' field
        with open(file_path, 'r') as f:
            data = json.load(f)
            if 'lines' in data:
                return data['lines']
            elif 'ocr_lines' in data:
                return data['ocr_lines']
            elif 'text' in data:
                return data['text'].split('\n')
            else:
                raise ValueError(f"JSON file must contain 'lines', 'ocr_lines', or 'text' field: {file_path}")
    elif file_path.suffix == '.txt':
        # Plain text file, one line per line
        with open(file_path, 'r') as f:
            return [line.rstrip('\n') for line in f]
    else:
        raise ValueError(f"Unsupported file format: {file_path.suffix}")


def export_dataset(
    input_dir: Path,
    output_dir: Path,
    limit: Optional[int] = None,
    include_debug_context: bool = False,
    redact: bool = True
):
    """Export merchant labeling dataset."""
    
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Output files
    doc_level_path = output_dir / "doc_level.jsonl"
    candidate_level_path = output_dir / "candidate_level.csv"
    manifest_path = output_dir / "manifest.csv"
    
    # Find input files
    input_files = []
    for pattern in ['*.json', '*.txt']:
        input_files.extend(input_dir.glob(pattern))
    
    if not input_files:
        print(f"No input files found in {input_dir}")
        return
    
    input_files = sorted(input_files)[:limit] if limit else sorted(input_files)
    
    print(f"Found {len(input_files)} input files")
    print(f"Output directory: {output_dir}")
    print(f"Redaction: {'enabled' if redact else 'disabled'}")
    print(f"Debug context: {'included' if include_debug_context else 'excluded'}")
    
    # Process files
    doc_level_records = []
    candidate_rows = []
    manifest_rows = []
    
    for i, file_path in enumerate(input_files, 1):
        try:
            print(f"Processing {i}/{len(input_files)}: {file_path.name}")
            
            # Load OCR lines
            lines = load_ocr_lines_from_file(file_path)
            
            if not lines:
                print(f"  Warning: No lines found in {file_path.name}, skipping")
                continue
            
            # Extract merchant
            doc_id = file_path.stem
            result = _guess_merchant_entity(lines)
            
            # Generate ML payload
            ml_dict = result.to_ml_dict(
                doc_id=doc_id,
                page_count=1,
                lang_script="en-Latn",
                include_debug_context=include_debug_context
            )
            
            # Apply redaction if enabled
            if redact:
                # Redact candidates (except winner)
                winner_value = ml_dict.get('value')
                
                for cand in ml_dict.get('top_k', []):
                    if cand['value'] != winner_value:
                        cand['value'] = redact_text(cand['value'], keep_tokens=2)
                
                # Redact debug context
                if ml_dict.get('debug_context'):
                    ml_dict['debug_context'] = redact_debug_context(ml_dict['debug_context'])
            
            # Add source file info
            ml_dict['source_file'] = file_path.name
            
            doc_level_records.append(ml_dict)
            
            # Generate candidate rows
            cand_rows = result.to_candidate_rows(doc_id=doc_id)
            
            # Apply redaction to candidate rows
            if redact:
                winner_value = result.value
                for row in cand_rows:
                    if row['value'] != winner_value:
                        row['value'] = redact_text(row['value'], keep_tokens=2)
            
            candidate_rows.extend(cand_rows)
            
            # Generate manifest row
            manifest_row = {
                'doc_id': doc_id,
                'file_name': file_path.name,
                'merchant_value': result.value,
                'confidence_raw': result.evidence.get('confidence_raw', result.confidence),
                'confidence_calibrated': result.evidence.get('confidence_calibrated', result.confidence),
                'confidence_bucket': result.confidence_bucket,
                'winner_margin': result.evidence.get('winner_margin', 0.0),
                'candidate_count': len(result.candidates),
                'mode': result.evidence.get('fallback_mode', 'strict')
            }
            manifest_rows.append(manifest_row)
            
            print(f"  Extracted: {result.value} (confidence: {result.confidence:.3f}, bucket: {result.confidence_bucket})")
            
        except Exception as e:
            print(f"  Error processing {file_path.name}: {e}")
            continue
    
    # Write doc_level.jsonl
    print(f"\nWriting {len(doc_level_records)} records to {doc_level_path}")
    with open(doc_level_path, 'w') as f:
        for record in doc_level_records:
            f.write(json.dumps(record) + '\n')
    
    # Write candidate_level.csv
    if candidate_rows:
        print(f"Writing {len(candidate_rows)} candidate rows to {candidate_level_path}")
        fieldnames = list(candidate_rows[0].keys())
        with open(candidate_level_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(candidate_rows)
    
    # Write manifest.csv
    if manifest_rows:
        print(f"Writing {len(manifest_rows)} manifest rows to {manifest_path}")
        fieldnames = list(manifest_rows[0].keys())
        with open(manifest_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(manifest_rows)
    
    print(f"\n✅ Export complete!")
    print(f"   Documents: {len(doc_level_records)}")
    print(f"   Candidates: {len(candidate_rows)}")
    print(f"   Output: {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Export merchant extraction results for human labeling"
    )
    parser.add_argument(
        '--input_dir',
        type=str,
        required=True,
        help='Input directory containing receipt samples (JSON or TXT files)'
    )
    parser.add_argument(
        '--output_dir',
        type=str,
        required=True,
        help='Output directory for labeling dataset'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of files to process'
    )
    parser.add_argument(
        '--include_debug_context',
        action='store_true',
        help='Include debug context (first 40 lines, zones) in output'
    )
    parser.add_argument(
        '--no_redact',
        action='store_true',
        help='Disable redaction of PII (default: redaction enabled)'
    )
    
    args = parser.parse_args()
    
    export_dataset(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        limit=args.limit,
        include_debug_context=args.include_debug_context,
        redact=not args.no_redact
    )


if __name__ == '__main__':
    main()
