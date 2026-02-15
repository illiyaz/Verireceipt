"""
Metrics export utilities for calibration artifacts.

Provides CSV and Markdown export functionality for calibration metrics.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import json


def export_calibration_summary(
    artifact_dir: Path,
    version: str,
    metrics: Dict[str, Any],
    artifact: Dict[str, Any],
    entity: str = "merchant"
) -> Path:
    """Export calibration summary to CSV."""
    
    # Calculate bucket precisions if available
    bucket_precisions = {}
    if 'bucket_metrics' in metrics:
        for bucket, bucket_data in metrics['bucket_metrics'].items():
            bucket_precisions[f"{bucket}_bucket_precision"] = bucket_data.get('precision', 0.0)
    
    # Create summary row
    summary_data = {
        "version": version,
        "n_samples": artifact.get('source_metrics', {}).get('n', 0),
        "accuracy": metrics.get('accuracy', 0.0),
        "precision": metrics.get('precision', 0.0),
        "recall": metrics.get('recall', 0.0),
        "ece": metrics.get('ece', 0.0),
        "brier": metrics.get('brier_score', 0.0),
        "high_bucket_precision": bucket_precisions.get('HIGH_bucket_precision', 0.0),
        "medium_bucket_precision": bucket_precisions.get('MEDIUM_bucket_precision', 0.0),
        "low_bucket_precision": bucket_precisions.get('LOW_bucket_precision', 0.0),
        "calibration_method": artifact.get('calibrator_type', 'unknown'),
        "trained_at": artifact.get('created_at', datetime.now().isoformat())
    }
    
    summary_path = artifact_dir / "calibration_summary.csv"
    
    # Check if file exists to determine if we need headers
    file_exists = summary_path.exists()
    
    # Append to summary CSV
    df_summary = pd.DataFrame([summary_data])
    df_summary.to_csv(summary_path, mode='a', header=not file_exists, index=False)
    
    return summary_path


def export_bucket_breakdown(
    artifact_dir: Path,
    version: str,
    test_results: pd.DataFrame,
    entity: str = "merchant"
) -> Path:
    """Export bucket breakdown analysis to CSV."""
    
    # Group by confidence bucket if available
    if 'confidence_bucket' not in test_results.columns:
        # Create buckets from calibrated confidence
        test_results['confidence_bucket'] = pd.cut(
            test_results['y_prob_calibrated'],
            bins=[0.0, 0.6, 0.8, 1.0],
            labels=['LOW', 'MEDIUM', 'HIGH'],
            include_lowest=True
        )
    
    bucket_stats = []
    for bucket in ['HIGH', 'MEDIUM', 'LOW']:
        bucket_data = test_results[test_results['confidence_bucket'] == bucket]
        
        if len(bucket_data) == 0:
            continue
            
        precision = bucket_data['y_true'].mean()  # For binary classification, mean = precision
        avg_calibrated = bucket_data['y_prob_calibrated'].mean()
        
        # Get raw confidence if available
        avg_raw = bucket_data.get('y_prob_raw', bucket_data['y_prob_calibrated']).mean()
        
        bucket_stats.append({
            "confidence_bucket": bucket,
            "count": len(bucket_data),
            "precision": precision,
            "avg_raw_confidence": avg_raw,
            "avg_calibrated_confidence": avg_calibrated
        })
    
    bucket_path = artifact_dir / f"bucket_breakdown_{version}.csv"
    df_bucket = pd.DataFrame(bucket_stats)
    df_bucket.to_csv(bucket_path, index=False)
    
    return bucket_path


def generate_markdown_report(
    artifact_dir: Path,
    version: str,
    metrics: Dict[str, Any],
    artifact: Dict[str, Any],
    test_results: pd.DataFrame,
    previous_metrics: Optional[Dict[str, Any]] = None,
    entity: str = "merchant"
) -> Path:
    """Generate human-readable markdown report."""
    
    # Calculate bucket statistics
    bucket_stats = calculate_bucket_stats(test_results)
    
    # Determine regression status
    regression_status = check_regression(metrics, previous_metrics)
    
    # Generate recommendation
    recommendation = generate_recommendation(metrics, previous_metrics, regression_status)
    
    # Create markdown content
    # Helper functions for formatting
    def fmt_metric(value):
        return f"{value:.4f}" if isinstance(value, (int, float)) else str(value)
    
    def fmt_delta(current, previous):
        if previous is None:
            return 'N/A'
        return f"{current - previous:+.4f}"
    
    md_content = f"""# {entity.title()} Calibration Report - {version}

## Executive Summary

{generate_executive_summary(metrics, previous_metrics, regression_status, entity)}

## Dataset Statistics

- **Training Samples**: {artifact.get('source_metrics', {}).get('n', 'N/A')}
- **Test Samples**: {len(test_results)}
- **Positive Rate**: {test_results['y_true'].mean():.3f}
- **Calibration Method**: {artifact.get('calibrator_type', 'unknown')}
- **Trained At**: {artifact.get('created_at', 'N/A')}

## Performance Metrics

| Metric | Current | Previous | Delta |
|--------|---------|----------|-------|
| Accuracy | {fmt_metric(metrics.get('accuracy', 0))} | {fmt_metric(previous_metrics.get('accuracy') if previous_metrics else None)} | {fmt_delta(metrics.get('accuracy', 0), previous_metrics.get('accuracy') if previous_metrics else None)} |
| Precision | {fmt_metric(metrics.get('precision', 0))} | {fmt_metric(previous_metrics.get('precision') if previous_metrics else None)} | {fmt_delta(metrics.get('precision', 0), previous_metrics.get('precision') if previous_metrics else None)} |
| Recall | {fmt_metric(metrics.get('recall', 0))} | {fmt_metric(previous_metrics.get('recall') if previous_metrics else None)} | {fmt_delta(metrics.get('recall', 0), previous_metrics.get('recall') if previous_metrics else None)} |
| ECE | {fmt_metric(metrics.get('ece', 0))} | {fmt_metric(previous_metrics.get('ece') if previous_metrics else None)} | {fmt_delta(metrics.get('ece', 0), previous_metrics.get('ece') if previous_metrics else None)} |
| Brier Score | {fmt_metric(metrics.get('brier_score', 0))} | {fmt_metric(previous_metrics.get('brier_score') if previous_metrics else None)} | {fmt_delta(metrics.get('brier_score', 0), previous_metrics.get('brier_score') if previous_metrics else None)} |

## Confidence Bucket Analysis

| Bucket | Count | Precision | Avg Raw Conf | Avg Calibrated Conf |
|--------|-------|-----------|--------------|-------------------|
{generate_bucket_table(bucket_stats)}

## Calibration Quality Notes

- **Expected Calibration Error (ECE)**: {metrics.get('ece', 0):.4f} {'✅ Good' if metrics.get('ece', 1) < 0.05 else '⚠️ Needs Improvement' if metrics.get('ece', 1) < 0.1 else '❌ Poor'}
- **Brier Score**: {metrics.get('brier_score', 0):.4f} {'✅ Good' if metrics.get('brier_score', 1) < 0.2 else '⚠️ Needs Improvement' if metrics.get('brier_score', 1) < 0.3 else '❌ Poor'}
- **Reliability**: {assess_reliability(metrics)}

## Regression Analysis

{regression_status}

## Recommendation

{recommendation}

## High-Confidence Errors

{generate_error_analysis(test_results)}

---
*Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}*
"""
    
    report_path = artifact_dir / f"calibration_report_{version}.md"
    with open(report_path, 'w') as f:
        f.write(md_content)
    
    return report_path


def calculate_bucket_stats(test_results: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Calculate bucket statistics."""
    if 'confidence_bucket' not in test_results.columns:
        # Create buckets from calibrated confidence
        test_results = test_results.copy()
        test_results['confidence_bucket'] = pd.cut(
            test_results['y_prob_calibrated'],
            bins=[0.0, 0.6, 0.8, 1.0],
            labels=['LOW', 'MEDIUM', 'HIGH'],
            include_lowest=True
        )
    
    bucket_stats = {}
    for bucket in ['HIGH', 'MEDIUM', 'LOW']:
        bucket_data = test_results[test_results['confidence_bucket'] == bucket]
        
        if len(bucket_data) > 0:
            bucket_stats[bucket] = {
                'count': len(bucket_data),
                'precision': bucket_data['y_true'].mean(),
                'avg_calibrated': bucket_data['y_prob_calibrated'].mean(),
                'avg_raw': bucket_data.get('y_prob_raw', bucket_data['y_prob_calibrated']).mean()
            }
    
    return bucket_stats


def check_regression(
    current_metrics: Dict[str, Any],
    previous_metrics: Optional[Dict[str, Any]]
) -> str:
    """Check for regression compared to previous version."""
    if not previous_metrics:
        return "ℹ️ No previous version available for comparison"
    
    issues = []
    
    # Check ECE regression
    current_ece = current_metrics.get('ece', 0)
    previous_ece = previous_metrics.get('ece', 0)
    if current_ece - previous_ece > 0.02:
        issues.append(f"ECE increased by {current_ece - previous_ece:.4f}")
    
    # Check HIGH bucket precision regression
    current_high_prec = current_metrics.get('bucket_metrics', {}).get('HIGH', {}).get('precision', 0)
    previous_high_prec = previous_metrics.get('bucket_metrics', {}).get('HIGH', {}).get('precision', 0)
    if current_high_prec < 0.90 and previous_high_prec >= 0.90:
        issues.append(f"HIGH bucket precision dropped below 0.90 ({current_high_prec:.3f})")
    
    if issues:
        return f"❌ **Regression Detected**\\n\\nIssues:\\n" + "\\n".join(f"- {issue}" for issue in issues)
    elif current_ece < previous_ece - 0.01:
        return "✅ **Improved** - ECE decreased significantly"
    else:
        return "⚠️ **Neutral** - No significant changes"


def generate_recommendation(
    metrics: Dict[str, Any],
    previous_metrics: Optional[Dict[str, Any]],
    regression_status: str
) -> str:
    """Generate deployment recommendation."""
    ece = metrics.get('ece', 1)
    high_precision = metrics.get('bucket_metrics', {}).get('HIGH', {}).get('precision', 0)
    
    if "❌" in regression_status:
        return "🚫 **Needs More Data** - Regression detected. Review training data and consider additional samples before deployment."
    elif ece < 0.05 and high_precision >= 0.90:
        return "✅ **Safe to Deploy** - Excellent calibration quality with no regressions."
    elif ece < 0.1 and high_precision >= 0.85:
        return "⚠️ **Deploy with Caution** - Acceptable calibration but could be improved with more data."
    else:
        return "🚫 **Needs More Data** - Calibration quality below threshold. Collect more training samples."


def generate_executive_summary(
    metrics: Dict[str, Any],
    previous_metrics: Optional[Dict[str, Any]],
    regression_status: str,
    entity: str = "merchant"
) -> str:
    """Generate executive summary."""
    ece = metrics.get('ece', 1)
    accuracy = metrics.get('accuracy', 0)
    
    summary = f"The {entity} calibration model achieved "
    summary += f"{accuracy:.1%} accuracy with "
    summary += f"Expected Calibration Error (ECE) of {ece:.4f}. "
    
    if previous_metrics:
        prev_ece = previous_metrics.get('ece', 1)
        if ece < prev_ece:
            summary += f"This represents an improvement over the previous version (ECE: {prev_ece:.4f}). "
        elif ece > prev_ece:
            summary += f"This is a regression from the previous version (ECE: {prev_ece:.4f}). "
        else:
            summary += f"This maintains similar performance to the previous version. "
    
    if "❌" in regression_status:
        summary += "Regression detected - review recommended before deployment."
    elif "✅" in regression_status:
        summary += "Performance improved - safe for deployment."
    else:
        summary += "Performance stable - can be deployed with standard monitoring."
    
    return summary


def generate_bucket_table(bucket_stats: Dict[str, Dict[str, float]]) -> str:
    """Generate markdown table for bucket statistics."""
    if not bucket_stats:
        return "| No bucket data available |"
    
    rows = []
    for bucket in ['HIGH', 'MEDIUM', 'LOW']:
        if bucket in bucket_stats:
            stats = bucket_stats[bucket]
            row = f"| {bucket} | {stats['count']} | {stats['precision']:.3f} | {stats['avg_raw']:.3f} | {stats['avg_calibrated']:.3f} |"
            rows.append(row)
    
    return "\\n".join(rows)


def assess_reliability(metrics: Dict[str, Any]) -> str:
    """Assess calibration reliability."""
    ece = metrics.get('ece', 1)
    
    if ece < 0.05:
        return "✅ Well-calibrated"
    elif ece < 0.1:
        return "⚠️ Moderately calibrated"
    else:
        return "❌ Poorly calibrated"


def generate_error_analysis(test_results: pd.DataFrame, top_n: int = 10) -> str:
    """Generate analysis of high-confidence errors."""
    # Find high-confidence errors
    high_conf_errors = test_results[
        (test_results['y_prob_calibrated'] > 0.8) & 
        (test_results['y_true'] == 0)
    ].sort_values('y_prob_calibrated', ascending=False)
    
    if len(high_conf_errors) == 0:
        return "No high-confidence errors found."
    
    analysis = f"Found {len(high_conf_errors)} high-confidence errors (confidence > 0.8, incorrect).\\n\\n"
    analysis += "Top examples:\\n\\n"
    
    for i, (_, row) in enumerate(high_conf_errors.head(top_n).iterrows()):
        doc_id = row.get('doc_id', f'sample_{i}')
        conf = row['y_prob_calibrated']
        analysis += f"- {doc_id}: {conf:.3f} confidence\\n"
    
    return analysis
