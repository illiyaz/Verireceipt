#!/usr/bin/env python3
"""
Date confidence calibration retraining entrypoint.

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
import pickle

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, brier_score_loss

from calibration.date.versioning import (
    generate_next_version, get_latest_version, load_previous_artifact,
    get_artifact_path, get_metrics_path, get_report_path,
    get_summary_csv_path, get_bucket_csv_path, version_exists
)
from calibration.date.metrics_export import (
    export_calibration_summary, export_bucket_breakdown, generate_markdown_report
)


# Configuration
RANDOM_SEED = 42
ENTITY = "date"


def expected_calibration_error(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    """Compute Expected Calibration Error (ECE) for binary classification."""
    y_true = np.asarray(y_true).astype(int)
    y_prob = np.asarray(y_prob).astype(float)

    # Clamp probabilities
    y_prob = np.clip(y_prob, 0.0, 1.0)

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(y_prob)

    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        # include right edge in last bin
        if i == n_bins - 1:
            mask = (y_prob >= lo) & (y_prob <= hi)
        else:
            mask = (y_prob >= lo) & (y_prob < hi)

        if not np.any(mask):
            continue

        bin_prob = y_prob[mask]
        bin_true = y_true[mask]

        acc = bin_true.mean()
        conf = bin_prob.mean()
        ece += (len(bin_prob) / n) * abs(acc - conf)

    return float(ece)


def calculate_basic_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray) -> Dict[str, float]:
    """Calculate basic calibration metrics."""
    metrics = {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, average='binary', zero_division=0),
        "recall": recall_score(y_true, y_pred, average='binary', zero_division=0),
        "brier_score": brier_score_loss(y_true, y_prob),
        "ece": expected_calibration_error(y_true, y_prob, n_bins=10),
    }
    
    return metrics


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


def load_dataset(filepath: str) -> pd.DataFrame:
    """Load labeled dataset from CSV."""
    path = Path(filepath)
    
    if path.suffix.lower() == '.csv':
        df = pd.read_csv(filepath)
    elif path.suffix.lower() == '.parquet':
        df = pd.read_parquet(filepath)
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}")
    
    # Validate required columns
    required_cols = ['doc_id', 'is_correct', 'raw_confidence']
    missing_cols = set(required_cols) - set(df.columns)
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
    
    # Filter to date entities only if entity column exists
    if 'entity' in df.columns:
        df = df[df['entity'] == ENTITY].copy()
    
    # Ensure raw_confidence is in [0, 1] range
    df['raw_confidence'] = df['raw_confidence'].clip(0.0, 1.0)
    
    print(f"Loaded {len(df)} {ENTITY} extraction results")
    return df


def prepare_features(df: pd.DataFrame) -> tuple:
    """Prepare features for training."""
    # For date calibration, we use raw_confidence as the primary feature
    X = df[['raw_confidence']].values
    
    feature_info = {
        "features_used": ["raw_confidence"],
        "feature_types": {"raw_confidence": "float64"},
        "n_samples": len(X)
    }
    
    return X, feature_info


def train_isotonic_regression(X: np.ndarray, y: np.ndarray) -> tuple:
    """Train isotonic regression calibration model using raw_confidence."""
    # Use raw_confidence (first column)
    if X.shape[1] > 0:
        raw_confidence = X[:, 0].astype(float)
        raw_confidence = np.clip(raw_confidence, 0.0, 1.0)
        
        print(f"Using raw_confidence range: [{raw_confidence.min():.3f}, {raw_confidence.max():.3f}]")
    else:
        raise ValueError("No features available for calibration")
    
    model = IsotonicRegression(out_of_bounds='clip', increasing=True)
    model.fit(raw_confidence, y)
    
    return model, raw_confidence


def export_isotonic_breakpoints(model: Any, n_points: int = 50) -> list:
    """Export isotonic regression model as breakpoints for runtime."""
    # Handle tuple return from train_isotonic_regression
    if isinstance(model, tuple):
        model = model[0]
    
    if not hasattr(model, 'X_thresholds_') or not hasattr(model, 'y_thresholds_'):
        raise ValueError("Isotonic model not fitted")
    
    X_thresholds = model.X_thresholds_
    y_thresholds = model.y_thresholds_
    
    # Downsample if too many points
    if len(X_thresholds) > n_points:
        indices = np.linspace(0, len(X_thresholds) - 1, n_points, dtype=int)
        X_thresholds = X_thresholds[indices]
        y_thresholds = y_thresholds[indices]
    
    # Ensure values are in [0, 1] range
    X_thresholds = np.clip(X_thresholds, 0.0, 1.0)
    y_thresholds = np.clip(y_thresholds, 0.0, 1.0)
    
    breakpoints = [
        {"x": float(x), "y": float(y)}
        for x, y in zip(X_thresholds, y_thresholds)
    ]
    
    return breakpoints


def save_calibration_artifact(
    model: Any,
    feature_info: Dict[str, Any],
    metrics: Dict[str, Any],
    output_dir: str,
    version: str,
    method: str
) -> str:
    """Save calibration artifact to JSON file."""
    # Base artifact structure (runtime-compatible)
    artifact = {
        "schema_version": 1,
        "entity": ENTITY,
        "calibrator_type": "piecewise_linear",  # Always export as piecewise_linear for runtime
        "version": version,
        "created_at": datetime.now().isoformat(),
        "feature_requirements": ["raw_confidence"],
        "notes": f"Trained on {feature_info['n_samples']} samples using {method} method",
        "source_metrics": {
            "ece": metrics.get("ece", 0.0),
            "brier": metrics.get("brier_score", 0.0),
            "accuracy": metrics.get("accuracy", 0.0),
            "n": feature_info["n_samples"]
        },
        "breakpoints": []
    }
    
    # Export model-specific breakpoints
    if method == "isotonic":
        # Export isotonic model as breakpoints
        artifact["breakpoints"] = export_isotonic_breakpoints(model, n_points=50)
        
        # Also save model params for offline debugging
        iso_model = model[0] if isinstance(model, tuple) else model
        artifact["model_params"] = {}
        if hasattr(iso_model, 'X_thresholds_'):
            artifact["model_params"]["X_min"] = float(iso_model.X_min_)
            artifact["model_params"]["X_max"] = float(iso_model.X_max_)
            artifact["model_params"]["y_min"] = float(iso_model.y_thresholds_.min())
            artifact["model_params"]["y_max"] = float(iso_model.y_thresholds_.max())
            artifact["model_params"]["n_thresholds"] = len(iso_model.X_thresholds_)
    
    elif method == "logistic":
        # For runtime compatibility we export a 1D curve over raw_confidence
        x_range = np.linspace(0.0, 1.0, 50)

        n_features = len(feature_info["features_used"])
        X_curve = np.zeros((len(x_range), n_features), dtype=float)
        X_curve[:, 0] = x_range  # raw_confidence assumed to be first feature

        y_pred = model.predict_proba(X_curve)[:, 1]
        y_pred = np.clip(y_pred, 0.0, 1.0)

        artifact["breakpoints"] = [
            {"x": float(x), "y": float(y)}
            for x, y in zip(x_range, y_pred)
        ]
        
        # Save model params for offline debugging
        artifact["model_params"] = {
            "coefficients": model.coef_.tolist() if hasattr(model, 'coef_') else [],
            "intercept": float(model.intercept_) if hasattr(model, 'intercept_') else 0.0
        }
    
    # Add offline training metadata (not used by runtime)
    artifact["training_metadata"] = {
        "features_used": feature_info["features_used"],
        "feature_types": feature_info["feature_types"],
        "training_samples": feature_info["n_samples"],
        "metrics": metrics
    }
    
    # Save to file
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    calibration_file = output_path / f"calibration_{version}.json"
    with open(calibration_file, 'w') as f:
        json.dump(artifact, f, indent=2)
    
    # Also save model pickle for easier loading
    model_file = output_path / f"model_{version}.pkl"
    with open(model_file, 'wb') as f:
        pickle.dump(model, f)
    
    print(f"Calibration artifact saved to: {calibration_file}")
    print(f"Model pickle saved to: {model_file}")
    
    return str(calibration_file)


def apply_calibration_to_test_set(
    model: Any, X_test: np.ndarray, method: str
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
        return f"❌ **Regression Detected**\n\nIssues:\n" + "\n".join(f"- {issue}" for issue in issues)
    elif current_ece < previous_ece - 0.01:
        return "✅ **Improved** - ECE decreased significantly"
    else:
        return "⚠️ **Neutral** - No significant changes"


def retrain(
    data_path: str,
    output_dir: str,
    method: str = "isotonic",
    version_tag: Optional[str] = None,
    test_size: float = 0.2,
    seed: int = RANDOM_SEED
) -> Dict[str, Any]:
    """
    Retrain calibration model with versioning and metrics export.
    
    Args:
        data_path: Path to labeled CSV dataset
        output_dir: Directory to save artifacts
        method: Calibration method ('isotonic' or 'logistic')
        version_tag: Optional version tag (auto-generated if None)
        test_size: Test set size fraction
        seed: Random seed for deterministic results
        
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
        if not version_tag.startswith("date_v"):
            version_tag = f"date_v{version_tag}"
        
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
    X, feature_info = prepare_features(df)
    y = df['is_correct'].values
    
    # Set random seed for deterministic results
    np.random.seed(seed)
    
    # Split data using indices for proper doc_id mapping
    idx = np.arange(len(df))
    
    if 'confidence_bucket' in df.columns:
        idx_train, idx_test = train_test_split(
            idx, test_size=test_size, random_state=seed,
            stratify=df['confidence_bucket']
        )
    else:
        idx_train, idx_test = train_test_split(
            idx, test_size=test_size, random_state=seed
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
        model = LogisticRegression(random_state=seed, max_iter=1000)
        model.fit(X_train, y_train)
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
    calibration_path = save_calibration_artifact(model, feature_info, metrics, str(output_path), version_tag, method)
    
    # Save metrics
    metrics_path = get_metrics_path(output_path, version_tag)
    with open(metrics_path, 'w') as f:
        json.dump(metrics, f, indent=2, default=str)
    
    # Save test results
    test_results_path = output_path / f"test_results_{version_tag}.csv"
    test_results_df.to_csv(test_results_path, index=False)
    
    # Export CSV dashboards
    print("Exporting CSV dashboards...")
    
    # Load artifact for export
    with open(calibration_path, 'r') as f:
        artifact = json.load(f)
    
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
        "metrics_path": str(metrics_path),
        "test_results_path": str(test_results_path),
        "summary_csv_path": str(summary_csv_path),
        "bucket_csv_path": str(bucket_csv_path),
        "report_path": str(report_path),
        "metrics": metrics,
        "previous_version": previous_artifact.get('version') if previous_artifact else None,
        "regression_detected": "❌" in str(check_regression(metrics, previous_metrics))
    }
    
    print(f"\nRetraining completed successfully!")
    print(f"Version: {version_tag}")
    print(f"Calibration artifact: {calibration_path}")
    print(f"Metrics: {metrics_path}")
    print(f"Report: {report_path}")
    print(f"CSV summary: {summary_csv_path}")
    
    return results


def main():
    """Main entrypoint for retraining."""
    parser = argparse.ArgumentParser(
        description="Retrain date confidence calibration model with versioning and metrics export"
    )
    parser.add_argument(
        "--data", required=True,
        help="Path to labeled CSV dataset"
    )
    parser.add_argument(
        "--output", default="calibration/date/artifacts",
        help="Output directory for artifacts"
    )
    parser.add_argument(
        "--method", choices=["isotonic", "logistic"], default="isotonic",
        help="Calibration method"
    )
    parser.add_argument(
        "--version", help="Version tag (auto-generated if not provided)"
    )
    parser.add_argument(
        "--test-size", type=float, default=0.2,
        help="Test set size fraction"
    )
    parser.add_argument(
        "--seed", type=int, default=RANDOM_SEED,
        help="Random seed for deterministic results"
    )
    
    args = parser.parse_args()
    
    try:
        results = retrain(
            data_path=args.data,
            output_dir=args.output,
            method=args.method,
            version_tag=args.version,
            test_size=args.test_size,
            seed=args.seed
        )
        
        # Print deployment recommendation
        print(f"\n{'='*60}")
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
        
        print(f"\nFull report: {results['report_path']}")
        print(f"CSV summary: {results['summary_csv_path']}")
        
    except Exception as e:
        print(f"Error during retraining: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
