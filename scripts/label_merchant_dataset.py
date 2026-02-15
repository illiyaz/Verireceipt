#!/usr/bin/env python3
"""
CLI-based merchant labeling tool.

Iterates through exported merchant extraction results and collects human labels.
"""

import argparse
import json
import csv
from pathlib import Path
from typing import Dict, Any, Optional, List
import sys

# Error type enum
ERROR_TYPES = [
    'ocr_error',
    'layout_error', 
    'heuristic_error',
    'ambiguous',
    'non_receipt',
    'other'
]


def load_existing_labels(labels_path: Path) -> Dict[str, Dict[str, Any]]:
    """Load existing labels from CSV (idempotent by doc_id)."""
    labels = {}
    
    if not labels_path.exists():
        return labels
    
    with open(labels_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            labels[row['doc_id']] = row
    
    return labels


def save_label(labels_path: Path, label_data: Dict[str, Any]):
    """Save a single label to CSV (append-only)."""
    fieldnames = [
        'doc_id',
        'winner_correct',
        'correct_merchant_text',
        'error_type',
        'notes',
        'confidence_raw',
        'confidence_calibrated',
        'confidence_bucket',
        'winner_margin'
    ]
    
    # Check if file exists
    file_exists = labels_path.exists()
    
    with open(labels_path, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        if not file_exists:
            writer.writeheader()
        
        writer.writerow(label_data)


def display_document(doc: Dict[str, Any], show_lines: bool = False):
    """Display document information for labeling."""
    print("\n" + "="*80)
    print(f"Document ID: {doc['doc_id']}")
    print(f"Source File: {doc.get('source_file', 'N/A')}")
    print("="*80)
    
    # Confidence info
    print(f"\nConfidence:")
    print(f"  Raw:        {doc.get('confidence', 0.0):.3f}")
    
    # Check if calibration was applied
    if doc.get('mode_trace'):
        for mode in doc['mode_trace']:
            if mode.get('mode') == 'strict' or mode.get('mode') == 'relaxed':
                print(f"  Calibrated: {mode.get('confidence', 0.0):.3f}")
                break
    
    print(f"  Bucket:     {doc.get('confidence_bucket', 'UNKNOWN')}")
    print(f"  Margin:     {doc.get('winner_margin', 0.0):.2f}")
    
    # Winner
    winner = doc.get('winner')
    if winner:
        print(f"\n✓ WINNER: {winner.get('value', 'N/A')}")
        print(f"  Score:   {winner.get('score', 0.0):.2f}")
        print(f"  Source:  {winner.get('source', 'N/A')}")
        print(f"  Reasons: {', '.join(winner.get('reasons', []))}")
        print(f"  Zone:    {winner.get('zone', 'none')}")
    
    # Top candidates
    top_k = doc.get('top_k', [])
    if len(top_k) > 1:
        print(f"\nTop {min(5, len(top_k))} Candidates:")
        for i, cand in enumerate(top_k[:5], 1):
            marker = "✓" if i == 1 else " "
            print(f"  {marker} {i}. {cand.get('value', 'N/A')}")
            print(f"      Score: {cand.get('score', 0.0):.2f} | Reasons: {', '.join(cand.get('reasons', []))}")
    
    # Optional: Show first 20 lines
    if show_lines:
        debug_ctx = doc.get('debug_context')
        if debug_ctx and debug_ctx.get('first_40_lines'):
            lines = debug_ctx['first_40_lines'][:20]
            print(f"\nFirst {len(lines)} OCR lines:")
            for i, line in enumerate(lines, 1):
                print(f"  {i:2d}. {line[:70]}{'...' if len(line) > 70 else ''}")


def get_user_input(prompt: str, valid_options: Optional[List[str]] = None) -> str:
    """Get user input with optional validation."""
    while True:
        response = input(prompt).strip()
        
        if valid_options and response.lower() not in [opt.lower() for opt in valid_options]:
            print(f"Invalid input. Please choose from: {', '.join(valid_options)}")
            continue
        
        return response


def label_document(doc: Dict[str, Any], show_lines: bool = False) -> Optional[Dict[str, Any]]:
    """Label a single document interactively."""
    display_document(doc, show_lines=show_lines)
    
    # Ask if winner is correct
    print("\n" + "-"*80)
    response = get_user_input(
        "Is the winner correct? (y/n/s=skip/q=quit/l=show lines): ",
        valid_options=['y', 'n', 's', 'skip', 'q', 'quit', 'l', 'lines']
    ).lower()
    
    if response in ['q', 'quit']:
        return None
    
    if response in ['l', 'lines']:
        # Show lines and re-prompt
        display_document(doc, show_lines=True)
        return label_document(doc, show_lines=True)
    
    if response in ['s', 'skip']:
        return {'skip': True}
    
    winner_correct = response == 'y'
    
    # Collect label data
    label_data = {
        'doc_id': doc['doc_id'],
        'winner_correct': 'yes' if winner_correct else 'no',
        'correct_merchant_text': '',
        'error_type': '',
        'notes': '',
        'confidence_raw': doc.get('confidence', 0.0),
        'confidence_calibrated': doc.get('confidence', 0.0),
        'confidence_bucket': doc.get('confidence_bucket', 'UNKNOWN'),
        'winner_margin': doc.get('winner_margin', 0.0)
    }
    
    # Get calibrated confidence if available
    if doc.get('mode_trace'):
        for mode in doc['mode_trace']:
            if mode.get('mode') in ['strict', 'relaxed']:
                label_data['confidence_calibrated'] = mode.get('confidence', label_data['confidence_raw'])
                break
    
    # If incorrect, get correct merchant and error type
    if not winner_correct:
        correct_merchant = input("Enter correct merchant name (or press Enter to skip): ").strip()
        if correct_merchant:
            label_data['correct_merchant_text'] = correct_merchant
        
        print(f"\nError type options: {', '.join(ERROR_TYPES)}")
        error_type = get_user_input(
            "Select error type: ",
            valid_options=ERROR_TYPES + ['']
        )
        if error_type:
            label_data['error_type'] = error_type
    
    # Optional notes
    notes = input("Additional notes (optional): ").strip()
    if notes:
        label_data['notes'] = notes
    
    return label_data


def main():
    parser = argparse.ArgumentParser(
        description="CLI tool for labeling merchant extraction results"
    )
    parser.add_argument(
        '--doc_level_jsonl',
        type=str,
        required=True,
        help='Path to doc_level.jsonl file from export'
    )
    parser.add_argument(
        '--labels_csv',
        type=str,
        default='labels.csv',
        help='Path to output labels CSV (default: labels.csv)'
    )
    parser.add_argument(
        '--show_lines',
        action='store_true',
        help='Show OCR lines by default'
    )
    parser.add_argument(
        '--start_from',
        type=int,
        default=0,
        help='Start from document index (0-based)'
    )
    
    args = parser.parse_args()
    
    doc_level_path = Path(args.doc_level_jsonl)
    labels_path = Path(args.labels_csv)
    
    if not doc_level_path.exists():
        print(f"Error: {doc_level_path} not found")
        return
    
    # Load existing labels
    existing_labels = load_existing_labels(labels_path)
    print(f"Loaded {len(existing_labels)} existing labels from {labels_path}")
    
    # Load documents
    documents = []
    with open(doc_level_path, 'r') as f:
        for line in f:
            documents.append(json.loads(line))
    
    print(f"Loaded {len(documents)} documents from {doc_level_path}")
    
    # Filter out already labeled documents
    unlabeled_docs = [
        doc for doc in documents[args.start_from:]
        if doc['doc_id'] not in existing_labels
    ]
    
    print(f"Found {len(unlabeled_docs)} unlabeled documents")
    
    if not unlabeled_docs:
        print("All documents are already labeled!")
        return
    
    # Start labeling
    print("\n" + "="*80)
    print("MERCHANT LABELING SESSION")
    print("="*80)
    print("\nCommands:")
    print("  y     - Winner is correct")
    print("  n     - Winner is incorrect")
    print("  s     - Skip this document")
    print("  l     - Show OCR lines")
    print("  q     - Quit and save")
    print("="*80)
    
    labeled_count = 0
    
    for i, doc in enumerate(unlabeled_docs, 1):
        print(f"\n\nProgress: {i}/{len(unlabeled_docs)} (Total labeled: {len(existing_labels) + labeled_count})")
        
        label_data = label_document(doc, show_lines=args.show_lines)
        
        if label_data is None:
            # User quit
            print(f"\n\nQuitting. Labeled {labeled_count} documents in this session.")
            break
        
        if label_data.get('skip'):
            print("Skipped.")
            continue
        
        # Save label
        save_label(labels_path, label_data)
        labeled_count += 1
        print(f"✓ Label saved to {labels_path}")
    
    print(f"\n\n{'='*80}")
    print(f"Labeling session complete!")
    print(f"  New labels: {labeled_count}")
    print(f"  Total labels: {len(existing_labels) + labeled_count}")
    print(f"  Output: {labels_path}")
    print(f"{'='*80}")


if __name__ == '__main__':
    main()
