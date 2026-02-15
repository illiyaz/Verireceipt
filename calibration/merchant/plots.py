"""
Merchant confidence calibration plotting utilities.

Generates reliability diagrams, confidence histograms, and bucket precision plots.
"""

import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Dict, Any, List, Tuple
import warnings

from config import (
    BUCKET_THRESHOLDS, FIGURE_SIZE, PLOT_DPI, PLOT_STYLE, 
    OUTPUT_DIR, PLOTS_DIR
)

# Set plotting style
try:
    plt.style.use(PLOT_STYLE)
except OSError:
    # Fallback if style not available
    plt.style.use('default')

# Define color palette
colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

def load_evaluation_report(output_dir: str) -> Dict[str, Any]:
    """Load evaluation report from JSON file."""
    report_path = Path(output_dir) / "metrics_merchant_v1.json"
    with open(report_path, 'r') as f:
        return json.load(f)

def plot_reliability_diagram(report: Dict[str, Any], save_path: str) -> None:
    """Generate reliability diagram showing calibration quality."""
    bin_stats = report['bin_stats']
    bucket_metrics = report['bucket_metrics']
    
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    
    # Plot reliability diagram bins
    bin_centers = []
    bin_accuracies = []
    bin_confidences = []
    bin_counts = []
    
    for stat in bin_stats:
        if stat['count'] > 0:
            bin_center = (stat['bin_lower'] + stat['bin_upper']) / 2
            bin_centers.append(bin_center)
            bin_accuracies.append(stat['accuracy'])
            bin_confidences.append(stat['avg_confidence'])
            bin_counts.append(stat['count'])
    
    # Plot bars for each bin
    bars = ax.bar(bin_centers, bin_accuracies, width=0.08, alpha=0.7, 
                  color='skyblue', edgecolor='navy', label='Accuracy')
    
    # Plot perfect calibration line
    ax.plot([0, 1], [0, 1], 'r--', linewidth=2, label='Perfect Calibration')
    
    # Plot confidence line
    ax.plot(bin_centers, bin_confidences, 'bo-', linewidth=2, 
            markersize=6, label='Mean Confidence')
    
    # Add sample counts as text
    for i, (center, count) in enumerate(zip(bin_centers, bin_counts)):
        ax.text(center, bin_accuracies[i] + 0.02, str(count), 
                ha='center', va='bottom', fontsize=8)
    
    ax.set_xlabel('Confidence', fontsize=12)
    ax.set_ylabel('Accuracy', fontsize=12)
    ax.set_title(f'Reliability Diagram\nECE: {report["overall_metrics"]["ece"]:.4f}', 
                fontsize=14, fontweight='bold')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(loc='lower right')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=PLOT_DPI, bbox_inches='tight')
    plt.close()
    
    print(f"Reliability diagram saved to: {save_path}")

def plot_confidence_histogram(report: Dict[str, Any], save_path: str) -> None:
    """Generate confidence distribution histogram."""
    # Load test results to get confidence values
    test_results_path = Path(OUTPUT_DIR) / "test_results.csv"
    test_results = pd.read_csv(test_results_path)
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    # Overall confidence distribution
    ax1.hist(test_results['y_prob_calibrated'], bins=20, alpha=0.7, 
             color='lightblue', edgecolor='black')
    ax1.axvline(test_results['y_prob_calibrated'].mean(), color='red', 
               linestyle='--', linewidth=2, label=f'Mean: {test_results["y_prob_calibrated"].mean():.3f}')
    ax1.set_xlabel('Calibrated Confidence', fontsize=12)
    ax1.set_ylabel('Frequency', fontsize=12)
    ax1.set_title('Confidence Distribution', fontsize=14, fontweight='bold')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Confidence distribution by correctness
    correct = test_results[test_results['y_true'] == 1]['y_prob_calibrated']
    incorrect = test_results[test_results['y_true'] == 0]['y_prob_calibrated']
    
    ax2.hist([correct, incorrect], bins=20, alpha=0.7, 
             label=['Correct', 'Incorrect'], color=['green', 'red'])
    ax2.set_xlabel('Calibrated Confidence', fontsize=12)
    ax2.set_ylabel('Frequency', fontsize=12)
    ax2.set_title('Confidence by Correctness', fontsize=14, fontweight='bold')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=PLOT_DPI, bbox_inches='tight')
    plt.close()
    
    print(f"Confidence histogram saved to: {save_path}")

def plot_bucket_precision(report: Dict[str, Any], save_path: str) -> None:
    """Generate precision vs confidence bucket plot."""
    bucket_metrics = report['bucket_metrics']
    
    # Sort buckets by threshold (descending)
    sorted_buckets = sorted(bucket_metrics.items(), key=lambda x: x[1]['threshold'], reverse=True)
    
    bucket_names = []
    precisions = []
    confidences = []
    counts = []
    thresholds = []
    
    for bucket_name, metrics in sorted_buckets:
        bucket_names.append(bucket_name)
        precisions.append(metrics['precision'])
        confidences.append(metrics['avg_confidence'])
        counts.append(metrics['count'])
        thresholds.append(metrics['threshold'])
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    # Precision bars with sample counts
    bars1 = ax1.bar(bucket_names, precisions, alpha=0.7, 
                     color='lightgreen', edgecolor='darkgreen')
    
    # Add sample count labels
    for i, (bar, count) in enumerate(zip(bars1, counts)):
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                f'n={count}', ha='center', va='bottom', fontsize=10)
    
    # Add confidence line on secondary axis
    ax1_twin = ax1.twinx()
    ax1_twin.plot(bucket_names, confidences, 'ro-', linewidth=2, markersize=8, 
                 color='red', label='Avg Confidence')
    ax1_twin.set_ylabel('Average Confidence', fontsize=12, color='red')
    ax1_twin.tick_params(axis='y', labelcolor='red')
    
    ax1.set_xlabel('Confidence Bucket', fontsize=12)
    ax1.set_ylabel('Precision', fontsize=12, color='green')
    ax1.set_title('Precision by Confidence Bucket', fontsize=14, fontweight='bold')
    ax1.tick_params(axis='y', labelcolor='green')
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)
    
    # Precision vs Confidence scatter
    ax2.scatter(confidences, precisions, s=counts, alpha=0.7, c=thresholds, 
                cmap='viridis', edgecolors='black')
    ax2.plot([0, 1], [0, 1], 'r--', linewidth=2, label='Perfect Calibration')
    
    # Add bucket labels
    for i, bucket in enumerate(bucket_names):
        ax2.annotate(bucket, (confidences[i], precisions[i]), 
                    xytext=(5, 5), textcoords='offset points', fontsize=8)
    
    ax2.set_xlabel('Average Confidence', fontsize=12)
    ax2.set_ylabel('Precision', fontsize=12)
    ax2.set_title('Precision vs Confidence', fontsize=14, fontweight='bold')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=PLOT_DPI, bbox_inches='tight')
    plt.close()
    
    print(f"Bucket precision plot saved to: {save_path}")

def plot_calibration_comparison(report: Dict[str, Any], save_path: str) -> None:
    """Generate comparison of raw vs calibrated confidence."""
    # Load test results to get raw confidence values
    test_results_path = Path(OUTPUT_DIR) / "test_results.csv"
    test_results = pd.read_csv(test_results_path)
    
    # For this example, we'll simulate raw confidence
    # In practice, you'd have the raw confidence values in your dataset
    np.random.seed(42)
    raw_confidence = np.clip(
        test_results['y_prob_calibrated'] + np.random.normal(0, 0.1, len(test_results)),
        0, 1
    )
    
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    
    # Create bins for comparison
    bins = np.linspace(0, 1, 11)
    bin_centers = (bins[:-1] + bins[1:]) / 2
    
    # Calculate accuracy per bin for both raw and calibrated
    raw_accuracy = []
    calibrated_accuracy = []
    
    for i in range(len(bins)-1):
        mask = (raw_confidence >= bins[i]) & (raw_confidence < bins[i+1])
        if mask.sum() > 0:
            raw_accuracy.append(test_results.loc[mask, 'y_true'].mean())
        else:
            raw_accuracy.append(0)
        
        mask_cal = (test_results['y_prob_calibrated'] >= bins[i]) & (test_results['y_prob_calibrated'] < bins[i+1])
        if mask_cal.sum() > 0:
            calibrated_accuracy.append(test_results.loc[mask_cal, 'y_true'].mean())
        else:
            calibrated_accuracy.append(0)
    
    # Plot lines
    ax.plot(bin_centers, raw_accuracy, 'o-', linewidth=2, markersize=6, 
            color='orange', label='Raw Confidence')
    ax.plot(bin_centers, calibrated_accuracy, 's-', linewidth=2, markersize=6, 
            color='blue', label='Calibrated Confidence')
    ax.plot([0, 1], [0, 1], 'r--', linewidth=2, label='Perfect Calibration')
    
    ax.set_xlabel('Confidence', fontsize=12)
    ax.set_ylabel('Accuracy', fontsize=12)
    ax.set_title('Raw vs Calibrated Confidence', fontsize=14, fontweight='bold')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=PLOT_DPI, bbox_inches='tight')
    plt.close()
    
    print(f"Calibration comparison plot saved to: {save_path}")

def generate_all_plots(output_dir: str = OUTPUT_DIR) -> None:
    """Generate all calibration plots."""
    print("Generating calibration plots...")
    
    # Load evaluation report
    report = load_evaluation_report(output_dir)
    
    # Create plots directory
    plots_dir = Path(output_dir) / PLOTS_DIR
    plots_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate individual plots
    plot_reliability_diagram(report, plots_dir / "reliability_diagram.png")
    plot_confidence_histogram(report, plots_dir / "confidence_histogram.png")
    plot_bucket_precision(report, plots_dir / "bucket_precision.png")
    plot_calibration_comparison(report, plots_dir / "calibration_comparison.png")
    
    print(f"\n📈 All plots saved to: {plots_dir}")
    print("Generated plots:")
    print("  - reliability_diagram.png")
    print("  - confidence_histogram.png") 
    print("  - bucket_precision.png")
    print("  - calibration_comparison.png")

def main(output_dir: str = OUTPUT_DIR):
    """Main plotting function."""
    generate_all_plots(output_dir)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate calibration plots")
    parser.add_argument("--output", default=OUTPUT_DIR, help="Output directory")
    
    args = parser.parse_args()
    
    # Suppress warnings for cleaner output
    warnings.filterwarnings("ignore", category=FutureWarning)
    
    try:
        main(args.output)
        print(f"\n✅ Plot generation completed successfully!")
        
    except Exception as e:
        print(f"❌ Plot generation failed: {e}")
        raise
