#!/usr/bin/env python3
"""
Label pack generator for VeriReceipt.

Pre-fills labeling information from pipeline output to speed up human annotation.
"""

import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.schemas.receipt import ReceiptFeatures
from app.pipelines.features import process_receipt


def generate_doc_id(file_path: Path) -> str:
    """
    Generate stable document ID from file content.
    
    Uses SHA256 of file bytes for uniqueness.
    """
    with open(file_path, 'rb') as f:
        file_bytes = f.read()
    
    return f"sha256:{hashlib.sha256(file_bytes).hexdigest()}"


def extract_fields_for_labeling(features: ReceiptFeatures) -> Dict[str, Any]:
    """
    Extract key fields that humans need to validate.
    
    Returns privacy-safe field information for labeling.
    """
    text_features = features.text_features
    
    # Extract key fields (privacy-safe)
    fields = {
        "merchant_name": text_features.get("merchant_candidate"),
        "total_amount": text_features.get("total_amount"),
        "invoice_date": text_features.get("invoice_date"),
        "due_date": text_features.get("due_date"),
        "merchant_address": text_features.get("merchant_address"),
    }
    
    # Remove None values for cleaner display
    return {k: v for k, v in fields.items() if v is not None}


def extract_signals_for_labeling(features: ReceiptFeatures) -> Dict[str, Any]:
    """
    Extract emitted signals for human review.
    
    Returns privacy-safe signal information.
    """
    signals = {}
    
    for signal_name, signal in features.signals.items():
        # Store only key information (no raw evidence)
        signals[signal_name] = {
            "status": signal.status,
            "confidence": signal.confidence,
            "interpretation": signal.interpretation,
            # Skip raw evidence to maintain privacy
        }
    
    return signals


def extract_metadata(file_path: Path, features: ReceiptFeatures) -> Dict[str, Any]:
    """
    Extract metadata for provenance and context.
    """
    file_features = features.file_features
    
    return {
        "file_name": file_path.name,
        "file_size": file_path.stat().st_size,
        "pdf_metadata": file_features.get("pdf_metadata", {}),
        "is_image": file_features.get("is_image", False),
        "doc_profile": features.document_intent,
        "language": features.text_features.get("language", {}),
    }


def create_label_pack(
    file_path: Path, 
    features: ReceiptFeatures,
    output_dir: Path
) -> Path:
    """
    Create a label pack JSON file for a single document.
    
    Returns the path to the created label pack.
    """
    doc_id = generate_doc_id(file_path)
    
    # Build label pack structure
    label_pack = {
        "doc_id": doc_id,
        "source_file": str(file_path),
        "created_at": datetime.utcnow().isoformat() + "Z",
        "tool_version": "labelpack_v1.0",
        
        # Pre-filled information for human review
        "extracted_fields": extract_fields_for_labeling(features),
        "emitted_signals": extract_signals_for_labeling(features),
        "metadata": extract_metadata(file_path, features),
        
        # Empty label fields for humans to fill
        "label": {
            "label_version": "v1",
            "doc_id": doc_id,
            "source_batch": f"batch_{datetime.now().strftime('%Y_%m_%d')}",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "tool_version": "labelpack_v1.0",
            "annotator_judgments": [],  # To be filled by humans
            "adjudication": None,      # To be filled if needed
        }
    }
    
    # Write label pack
    output_path = output_dir / f"{doc_id}.json"
    with open(output_path, 'w') as f:
        json.dump(label_pack, f, indent=2, sort_keys=True)
    
    return output_path


def process_folder(
    input_folder: Path, 
    output_dir: Path,
    batch_name: Optional[str] = None
) -> int:
    """
    Process all PDFs in a folder and generate label packs.
    
    Returns the number of label packs created.
    """
    if not input_folder.exists():
        print(f"Error: Input folder {input_folder} does not exist")
        return 0
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Find PDF files
    pdf_files = list(input_folder.glob("**/*.pdf"))
    image_files = list(input_folder.glob("**/*.png")) + list(input_folder.glob("**/*.jpg"))
    
    all_files = pdf_files + image_files
    
    if not all_files:
        print(f"No PDF or image files found in {input_folder}")
        return 0
    
    print(f"Found {len(all_files)} files to process")
    
    created_count = 0
    errors = []
    
    for file_path in all_files:
        try:
            print(f"Processing {file_path.name}...")
            
            # Process receipt
            features = process_receipt(str(file_path))
            
            # Create label pack
            label_pack_path = create_label_pack(file_path, features, output_dir)
            print(f"  Created: {label_pack_path}")
            
            created_count += 1
            
        except Exception as e:
            error_msg = f"Error processing {file_path}: {e}"
            print(f"  {error_msg}")
            errors.append(error_msg)
    
    # Summary
    print(f"\nSummary:")
    print(f"  Files processed: {len(all_files)}")
    print(f"  Label packs created: {created_count}")
    print(f"  Errors: {len(errors)}")
    
    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"  - {error}")
    
    return created_count


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate label packs from PDFs/images"
    )
    parser.add_argument(
        "--input-folder",
        required=True,
        type=Path,
        help="Folder containing PDFs or images to process"
    )
    parser.add_argument(
        "--output-dir",
        default="labelpacks",
        type=Path,
        help="Output directory for label packs (default: labelpacks)"
    )
    parser.add_argument(
        "--batch-name",
        help="Batch name for provenance (default: auto-generated)"
    )
    
    args = parser.parse_args()
    
    # Process folder
    count = process_folder(
        input_folder=args.input_folder,
        output_dir=args.output_dir,
        batch_name=args.batch_name
    )
    
    if count > 0:
        print(f"\n✅ Generated {count} label packs in {args.output_dir}")
        print("\nNext steps:")
        print("1. Review label packs in the output directory")
        print("2. Fill in the 'label' sections with human judgments")
        print("3. Run validation: python scripts/validate_labels.py")
        print("4. Build dataset: python app/ml/dataset_builder.py")
    else:
        print("\n❌ No label packs generated")
        sys.exit(1)


if __name__ == "__main__":
    main()
