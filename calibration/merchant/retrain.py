#!/usr/bin/env python3
"""
Merchant confidence calibration retraining entrypoint.

Provides scheduled retraining support with versioning, metrics export,
and regression detection for production deployment decisions.
"""

import argparse
import sys
import os
from pathlib import Path
import json
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any, Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from calibration.merchant.calibrate import (
    load_dataset, prepare_features, train_isotonic_regression, train_logistic_regression,
    calculate_basic_metrics, save_calibration_artifact
)
from calibration.merchant.config import CALIBRATION_METHOD, RANDOM_SEED
from calibration.merchant.versioning import (
    generate_next_version, get_latest_version, load_previous_artifact,
    get_artifact_path, get_metrics_path, get_report_path,
    get_summary_csv_path, get_bucket_csv_path, version_exists
)
from calibration.merchant.metrics_export import (
    export_calibration_summary, export_bucket_breakdown, generate_markdown_report
)


def calculate_bucket_metrics(test_results: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Calculate bucket-specific metrics."""
    if 'confidence_bucket' not in test_results.columns:
        # Create buckets from calibrated confidence
        test_results = test_results.copy()
        test_results['confidence_bucket'] = pd.cut(
            test_results['y_prob_calibrated'],
            bins=[0.0, 0.6, 0.8, 1.0],
            labels=['LOW', 'MEDIUM', 'HIGH'],
            include_lowest=True
        )
    
    bucket_metrics = {}
    for bucket in ['HIGH', 'MEDIUM', 'LOW']:
        bucket_data = test_results[test_results['confidence_bucket'] == bucket]
        
        if len(bucket_data) > 0:
            bucket_metrics[bucket] = {
                'precision': bucket_data['y_true'].mean(),
                'count': len(bucket_data),
                'avg_confidence': bucket_data['y_prob_calibrated'].mean()
            }
    
    return bucket_metrics


def apply_calibration_to_test_set(
    model: Any, X_test: np.ndarray, method: str = CALIBRATION_METHOD
) -> np.ndarray:
    """Apply calibration to test set."""
    if method == "isotonic":
        # Use raw_confidence (first column)
        if X_test.shape[1] > 0:
            test_raw_confidence = X_test[:, 0].astype(float)
            test_raw_confidence = np.clip(test_raw_confidence, 0.0, 1.0)
        else:
            test_raw_confidence = np.zeros(len(X_test))
        
        y_prob_calibrated = model.predict(test_raw_confidence)
        
    elif method == "logistic":
        y_prob_calibrated = model.predict_proba(X_test)[:, 1]
        y_prob_calibrated = np.clip(y_prob_calibrated, 0.0, 1.0)
    
    else:
        raise ValueError(f"Unsupported calibration method: {method}")
    
    return y_prob_calibrated


def retrain(
    data_path: str,
    output_dir: str,
    method: str = CALIBRATION_METHOD,
    version_tag: Optional[str] = None,
    include_optional: bool = False,
    test_size: float = 0.2
) -> Dict[str, Any]:
    """
    Retrain calibration model with versioning and metrics export.
    
    Args:
        data_path: Path to labeled CSV dataset
        output_dir: Directory to save artifacts
        method: Calibration method ('isotonic' or 'logistic')
        version_tag: Optional version tag (auto-generated if None)
        include_optional: Whether to include optional features
        test_size: Test set size fraction
        
    Returns:
        Dictionary with retrain results and paths
    """
    print(f"Starting {method} calibration retraining")
    print(f"Data: {data_path}")
    print(f"Output: {output_dir}")
    
    # Set up paths
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Generate or validate version
    if version_tag:
        if not version_tag.startswith("merchant_v"):
            version_tag = f"merchant_v{version_tag}"
        
        if version_exists(output_path, version_tag):
            raise ValueError(f"Version {version_tag} already exists")
    else:
        version_tag = generate_next_version(output_path)
    
    print(f"Version: {version_tag}")
    
    # Load previous artifact for comparison
    previous_artifact = load_previous_artifact(output_path)
    previous_metrics = None
    if previous_artifact:
        print(f"Previous version found: {previous_artifact.get('version', 'unknown')}")
        # Try to load previous metrics
        metrics_path = output_path / f"metrics_{previous_artifact['version']}.json"
        if metrics_path.exists():
            with open(metrics_path, 'r') as f:
                previous_metrics = json.load(f)
    
    # Load and prepare data
    print("Loading dataset...")
    df = load_dataset(data_path)
    print(f"Loaded {len(df)} samples")
    
    # Prepare features
    X, feature_info = prepare_features(df, include_optional)
    y = df['is_correct'].values
    
    # Set random seed for deterministic results
    np.random.seed(RANDOM_SEED)
    
    # Split data using indices for proper doc_id mapping
    from sklearn.model_selection import train_test_split
    idx = np.arange(len(df))
    
    if 'confidence_bucket' in df.columns:
        idx_train, idx_test = train_test_split(
            idx, test_size=test_size, random_state=RANDOM_SEED,
            stratify=df['confidence_bucket']
        )
    else:
        idx_train, idx_test = train_test_split(
            idx, test_size=test_size, random_state=RANDOM_SEED
        )
    
    X_train, X_test = X[idx_train], X[idx_test]
    y_train, y_test = y[idx_train], y[idx_test]
    
    print(f"Training set: {len(X_train)} samples")
    print(f"Test set: {len(X_test)} samples")
    print(f"Positive rate: {y.mean():.3f}")
    
    # Train model
    print(f"Training {method} model...")
    if method == "isotonic":
        model, _ = train_isotonic_regression(X_train, y_train)
    elif method == "logistic":
        model = train_logistic_regression(X_train, y_train)
    else:
        raise ValueError(f"Unsupported method: {method}")
    
    # Apply calibration to test set
    print("Evaluating on test set...")
    y_prob_calibrated = apply_calibration_to_test_set(model, X_test, method)
    y_pred_calibrated = (y_prob_calibrated >= 0.5).astype(int)
    
    # Calculate metrics
    metrics = calculate_basic_metrics(y_test, y_pred_calibrated, y_prob_calibrated)
    metrics["training_samples"] = len(X_train)
    metrics["test_samples"] = len(X_test)
    
    # Add bucket metrics
    test_results_df = pd.DataFrame({
        'doc_id': df.iloc[idx_test]['doc_id'].values if 'doc_id' in df.columns else idx_test,
        'y_true': y_test,
        'y_prob_calibrated': y_prob_calibrated,
        'y_pred_calibrated': y_pred_calibrated
    })
    
    bucket_metrics = calculate_bucket_metrics(test_results_df)
    metrics["bucket_metrics"] = bucket_metrics
    
    # Print metrics
    print(f"Test set metrics:")
    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")
    
    # Save calibration artifact
    print("Saving calibration artifact...")
    calibration_path = save_calibration_artifact(model, feature_info, metrics, str(output_path))
    
    # Update artifact with version
    with open(calibration_path, 'r') as f:
        artifact = json.load(f)
    artifact['version'] = version_tag
    with open(calibration_path, 'w') as f:
        json.dump(artifact, f, indent=2)
    
    # Save metrics
    metrics_path = get_metrics_path(output_path, version_tag)
    with open(metrics_path, 'w') as f:
        json.dump(metrics, f, indent=2)
    
    # Save test results
    test_results_path = output_path / f"test_results_{version_tag}.csv"
    test_results_df.to_csv(test_results_path, index=False)
    
    # Export CSV dashboards
    print("Exporting CSV dashboards...")
    summary_csv_path = export_calibration_summary(output_path, version_tag, metrics, artifact)
    bucket_csv_path = export_bucket_breakdown(output_path, version_tag, test_results_df)
    
    # Generate markdown report
    print("Generating markdown report...")
    report_path = generate_markdown_report(
        output_path, version_tag, metrics, artifact, test_results_df, previous_metrics
    )
    
    # Results summary
    results = {
        "version": version_tag,
        "calibration_path": calibration_path,
        "metrics_path": metrics_path,
        "test_results_path": test_results_path,
        "summary_csv_path": summary_csv_path,
        "bucket_csv_path": bucket_csv_path,
        "report_path": report_path,
        "metrics": metrics,
        "previous_version": previous_artifact.get('version') if previous_artifact else None,
        "regression_detected": "❌" in str(check_regression(metrics, previous_metrics))
    }
    
    print(f"\\nRetraining completed successfully!")
    print(f"Version: {version_tag}")
    print(f"Calibration artifact: {calibration_path}")
    print(f"Metrics: {metrics_path}")
    print(f"Report: {report_path}")
    print(f"CSV summary: {summary_csv_path}")
    
    return results


def check_regression(current_metrics: Dict[str, Any], previous_metrics: Optional[Dict[str, Any]]) -> str:
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


def main():
    """Main entrypoint for retraining."""
    parser = argparse.ArgumentParser(
        description="Retrain merchant confidence calibration model with versioning and metrics export"
    )
    parser.add_argument(
        "--data", required=True,
        help="Path to labeled CSV dataset"
    )
    parser.add_argument(
        "--output", default="calibration/merchant/artifacts",
        help="Output directory for artifacts"
    )
    parser.add_argument(
        "--method", choices=["isotonic", "logistic"], default=CALIBRATION_METHOD,
        help="Calibration method"
    )
    parser.add_argument(
        "--version", help="Version tag (auto-generated if not provided)"
    )
    parser.add_argument(
        "--include-optional", action="store_true",
        help="Include optional features in training"
    )
    parser.add_argument(
        "--test-size", type=float, default=0.2,
        help="Test set size fraction"
    )
    
    args = parser.parse_args()
    
    try:
        results = retrain(
            data_path=args.data,
            output_dir=args.output,
            method=args.method,
            version_tag=args.version,
            include_optional=args.include_optional,
            test_size=args.test_size
        )
        
        # Print deployment recommendation
        print(f"\\n{'='*60}")
        print("DEPLOYMENT RECOMMENDATION")
        print('='*60)
        
        if results["regression_detected"]:
            print("🚫 DO NOT DEPLOY - Regression detected")
            print("   Review the markdown report for details")
        else:
            ece = results["metrics"].get("ece", 1)
            high_prec = results["metrics"].get("bucket_metrics", {}).get("HIGH", {}).get("precision", 0)
            
            if ece < 0.05 and high_prec >= 0.90:
                print("✅ SAFE TO DEPLOY - Excellent calibration")
            elif ece < 0.1 and high_prec >= 0.85:
                print("⚠️ DEPLOY WITH CAUTION - Acceptable calibration")
            else:
                print("🚫 NEEDS MORE DATA - Below deployment thresholds")
        
        print(f"\\nFull report: {results['report_path']}")
        print(f"CSV summary: {results['summary_csv_path']}")
        
    except Exception as e:
        print(f"Error during retraining: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
