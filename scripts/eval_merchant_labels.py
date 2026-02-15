#!/usr/bin/env python3
"""
Evaluate merchant extraction results against human labels.

Produces:
- Overall accuracy
- Bucket precision table
- Calibration diagnostics
- Margin analysis
- Error type breakdown
"""

import argparse
import json
import csv
from pathlib import Path
from typing import Dict, Any, List
from collections import defaultdict, Counter
import sys


def load_labels(labels_csv: Path) -> Dict[str, Dict[str, Any]]:
    """Load human labels from CSV."""
    labels = {}
    
    with open(labels_csv, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            labels[row['doc_id']] = row
    
    return labels


def load_documents(doc_level_jsonl: Path) -> Dict[str, Dict[str, Any]]:
    """Load documents from JSONL."""
    documents = {}
    
    with open(doc_level_jsonl, 'r') as f:
        for line in f:
            doc = json.loads(line)
            documents[doc['doc_id']] = doc
    
    return documents


def compute_metrics(labels: Dict[str, Dict[str, Any]], documents: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Compute evaluation metrics."""
    
    # Overall accuracy
    total = len(labels)
    correct = sum(1 for label in labels.values() if label['winner_correct'] == 'yes')
    accuracy = correct / total if total > 0 else 0.0
    
    # Bucket precision
    bucket_stats = defaultdict(lambda: {'total': 0, 'correct': 0})
    
    for doc_id, label in labels.items():
        if doc_id not in documents:
            continue
        
        doc = documents[doc_id]
        bucket = doc.get('confidence_bucket', 'UNKNOWN')
        is_correct = label['winner_correct'] == 'yes'
        
        bucket_stats[bucket]['total'] += 1
        if is_correct:
            bucket_stats[bucket]['correct'] += 1
    
    bucket_precision = {}
    for bucket, stats in bucket_stats.items():
        precision = stats['correct'] / stats['total'] if stats['total'] > 0 else 0.0
        bucket_precision[bucket] = {
            'precision': precision,
            'count': stats['total'],
            'correct': stats['correct']
        }
    
    # Calibration diagnostics
    correct_confidences = []
    incorrect_confidences = []
    
    for doc_id, label in labels.items():
        if doc_id not in documents:
            continue
        
        doc = documents[doc_id]
        is_correct = label['winner_correct'] == 'yes'
        
        # Use calibrated confidence if available
        confidence = doc.get('confidence', 0.0)
        if doc.get('mode_trace'):
            for mode in doc['mode_trace']:
                if mode.get('mode') in ['strict', 'relaxed']:
                    confidence = mode.get('confidence', confidence)
                    break
        
        if is_correct:
            correct_confidences.append(confidence)
        else:
            incorrect_confidences.append(confidence)
    
    avg_conf_correct = sum(correct_confidences) / len(correct_confidences) if correct_confidences else 0.0
    avg_conf_incorrect = sum(incorrect_confidences) / len(incorrect_confidences) if incorrect_confidences else 0.0
    
    # Margin analysis for errors
    error_margins = []
    for doc_id, label in labels.items():
        if label['winner_correct'] == 'no' and doc_id in documents:
            doc = documents[doc_id]
            margin = doc.get('winner_margin', 0.0)
            error_margins.append(margin)
    
    avg_error_margin = sum(error_margins) / len(error_margins) if error_margins else 0.0
    
    # Error type breakdown
    error_types = Counter()
    for label in labels.values():
        if label['winner_correct'] == 'no' and label.get('error_type'):
            error_types[label['error_type']] += 1
    
    return {
        'overall': {
            'total': total,
            'correct': correct,
            'accuracy': accuracy
        },
        'bucket_precision': bucket_precision,
        'calibration': {
            'avg_confidence_correct': avg_conf_correct,
            'avg_confidence_incorrect': avg_conf_incorrect,
            'confidence_gap': avg_conf_correct - avg_conf_incorrect
        },
        'margin_analysis': {
            'avg_error_margin': avg_error_margin,
            'error_count': len(error_margins)
        },
        'error_types': dict(error_types)
    }


def print_report(metrics: Dict[str, Any]):
    """Print evaluation report to stdout."""
    print("\n" + "="*80)
    print("MERCHANT EXTRACTION EVALUATION REPORT")
    print("="*80)
    
    # Overall accuracy
    overall = metrics['overall']
    print(f"\n📊 Overall Performance:")
    print(f"   Total documents:  {overall['total']}")
    print(f"   Correct:          {overall['correct']}")
    print(f"   Accuracy:         {overall['accuracy']:.1%}")
    
    # Bucket precision
    print(f"\n📈 Bucket Precision:")
    bucket_order = ['HIGH', 'MEDIUM', 'LOW', 'NONE', 'UNKNOWN']
    bucket_prec = metrics['bucket_precision']
    
    for bucket in bucket_order:
        if bucket in bucket_prec:
            stats = bucket_prec[bucket]
            print(f"   {bucket:8s}: {stats['precision']:.1%} ({stats['correct']}/{stats['count']} correct)")
    
    # Calibration diagnostics
    cal = metrics['calibration']
    print(f"\n🎯 Calibration Diagnostics:")
    print(f"   Avg confidence (correct):   {cal['avg_confidence_correct']:.3f}")
    print(f"   Avg confidence (incorrect): {cal['avg_confidence_incorrect']:.3f}")
    print(f"   Confidence gap:             {cal['confidence_gap']:+.3f}")
    
    # Margin analysis
    margin = metrics['margin_analysis']
    print(f"\n📉 Margin Analysis:")
    print(f"   Errors with margin data: {margin['error_count']}")
    print(f"   Avg winner margin (errors): {margin['avg_error_margin']:.2f}")
    
    # Error types
    if metrics['error_types']:
        print(f"\n❌ Error Type Breakdown:")
        total_errors = sum(metrics['error_types'].values())
        for error_type, count in sorted(metrics['error_types'].items(), key=lambda x: -x[1]):
            pct = count / total_errors * 100 if total_errors > 0 else 0
            print(f"   {error_type:20s}: {count:3d} ({pct:.1f}%)")
    
    print("\n" + "="*80)


def write_markdown_report(metrics: Dict[str, Any], output_path: Path):
    """Write evaluation report as Markdown."""
    with open(output_path, 'w') as f:
        f.write("# Merchant Extraction Evaluation Report\n\n")
        
        # Overall
        overall = metrics['overall']
        f.write("## Overall Performance\n\n")
        f.write(f"- **Total documents**: {overall['total']}\n")
        f.write(f"- **Correct**: {overall['correct']}\n")
        f.write(f"- **Accuracy**: {overall['accuracy']:.1%}\n\n")
        
        # Bucket precision
        f.write("## Bucket Precision\n\n")
        f.write("| Bucket | Precision | Correct | Total |\n")
        f.write("|--------|-----------|---------|-------|\n")
        
        bucket_order = ['HIGH', 'MEDIUM', 'LOW', 'NONE', 'UNKNOWN']
        bucket_prec = metrics['bucket_precision']
        
        for bucket in bucket_order:
            if bucket in bucket_prec:
                stats = bucket_prec[bucket]
                f.write(f"| {bucket} | {stats['precision']:.1%} | {stats['correct']} | {stats['count']} |\n")
        
        f.write("\n")
        
        # Calibration
        cal = metrics['calibration']
        f.write("## Calibration Diagnostics\n\n")
        f.write(f"- **Avg confidence (correct)**: {cal['avg_confidence_correct']:.3f}\n")
        f.write(f"- **Avg confidence (incorrect)**: {cal['avg_confidence_incorrect']:.3f}\n")
        f.write(f"- **Confidence gap**: {cal['confidence_gap']:+.3f}\n\n")
        
        # Margin analysis
        margin = metrics['margin_analysis']
        f.write("## Margin Analysis\n\n")
        f.write(f"- **Errors with margin data**: {margin['error_count']}\n")
        f.write(f"- **Avg winner margin (errors)**: {margin['avg_error_margin']:.2f}\n\n")
        
        # Error types
        if metrics['error_types']:
            f.write("## Error Type Breakdown\n\n")
            f.write("| Error Type | Count | Percentage |\n")
            f.write("|------------|-------|------------|\n")
            
            total_errors = sum(metrics['error_types'].values())
            for error_type, count in sorted(metrics['error_types'].items(), key=lambda x: -x[1]):
                pct = count / total_errors * 100 if total_errors > 0 else 0
                f.write(f"| {error_type} | {count} | {pct:.1f}% |\n")


def write_json_metrics(metrics: Dict[str, Any], output_path: Path):
    """Write metrics as JSON."""
    with open(output_path, 'w') as f:
        json.dump(metrics, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate merchant extraction results against human labels"
    )
    parser.add_argument(
        '--doc_level_jsonl',
        type=str,
        required=True,
        help='Path to doc_level.jsonl file'
    )
    parser.add_argument(
        '--labels_csv',
        type=str,
        required=True,
        help='Path to labels CSV file'
    )
    parser.add_argument(
        '--output_dir',
        type=str,
        default='eval_output',
        help='Output directory for reports (default: eval_output)'
    )
    
    args = parser.parse_args()
    
    doc_level_path = Path(args.doc_level_jsonl)
    labels_path = Path(args.labels_csv)
    output_dir = Path(args.output_dir)
    
    # Validate inputs
    if not doc_level_path.exists():
        print(f"Error: {doc_level_path} not found")
        return
    
    if not labels_path.exists():
        print(f"Error: {labels_path} not found")
        return
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load data
    print(f"Loading labels from {labels_path}...")
    labels = load_labels(labels_path)
    print(f"  Loaded {len(labels)} labels")
    
    print(f"Loading documents from {doc_level_path}...")
    documents = load_documents(doc_level_path)
    print(f"  Loaded {len(documents)} documents")
    
    # Compute metrics
    print(f"\nComputing metrics...")
    metrics = compute_metrics(labels, documents)
    
    # Print report
    print_report(metrics)
    
    # Write outputs
    report_md = output_dir / "report.md"
    metrics_json = output_dir / "metrics.json"
    
    print(f"\nWriting outputs...")
    write_markdown_report(metrics, report_md)
    print(f"  ✓ {report_md}")
    
    write_json_metrics(metrics, metrics_json)
    print(f"  ✓ {metrics_json}")
    
    print(f"\n✅ Evaluation complete!")
    print(f"   Output directory: {output_dir}")


if __name__ == '__main__':
    main()
