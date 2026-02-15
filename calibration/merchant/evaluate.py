"""
Merchant confidence calibration evaluation script.

Applies calibration model and computes detailed metrics including
ECE, reliability diagrams, and bucket-specific analysis.
"""

import json
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, Any, List, Tuple
import warnings

from config import (
    BUCKET_THRESHOLDS, RANDOM_SEED, OUTPUT_DIR, METRICS_FILE,
    PLOTS_DIR, FIGURE_SIZE, PLOT_DPI, PLOT_STYLE
)

# Set random seeds for reproducibility
np.random.seed(RANDOM_SEED)

def load_calibration_artifact(calibration_path: str) -> Dict[str, Any]:
    """Load calibration artifact from JSON file."""
    with open(calibration_path, 'r') as f:
        artifact = json.load(f)
    
    # Load model pickle
    model_path = Path(calibration_path).parent / f"model_{artifact['calibration_version']}.pkl"
    with open(model_path, 'rb') as f:
        model = pickle.load(f)
    
    return artifact, model

def load_test_results(output_dir: str) -> pd.DataFrame:
    """Load test results from calibration training."""
    test_results_path = Path(output_dir) / "test_results.csv"
    return pd.read_csv(test_results_path)

def apply_calibration(model: Any, artifact: Dict[str, Any], 
                    X_test: np.ndarray) -> np.ndarray:
    """Apply calibration model to test features."""
    method = artifact['method']
    
    if method == "isotonic":
        # Apply isotonic regression
        if X_test.shape[1] > 1:
            # Use same feature weights as in training
            feature_weights = np.array([1.0, 0.5, -0.1, 0.2, 0.3, -0.4, 0.6, 0.2, 0.1, -0.3, -0.2, -0.1])
            if len(feature_weights) > X_test.shape[1]:
                feature_weights = feature_weights[:X_test.shape[1]]
            elif len(feature_weights) < X_test.shape[1]:
                feature_weights = np.pad(feature_weights, (0, X_test.shape[1] - len(feature_weights)), 'constant')
            
            composite_score = np.dot(X_test, feature_weights)
        else:
            composite_score = X_test.flatten()
        
        y_prob_calibrated = model.predict(composite_score)
        
    elif method == "logistic":
        # Apply logistic regression pipeline
        y_prob_calibrated = model.predict_proba(X_test)[:, 1]
        
    else:
        raise ValueError(f"Unsupported calibration method: {method}")
    
    return y_prob_calibrated

def calculate_ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> Tuple[float, List[Tuple[float, float, int]]]:
    """Calculate Expected Calibration Error (ECE)."""
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    bin_lowers = bin_boundaries[:-1]
    bin_uppers = bin_boundaries[1:]
    
    ece = 0.0
    bin_stats = []
    
    for bin_lower, bin_upper in zip(bin_lowers, bin_uppers):
        # Find samples in this bin
        in_bin = (y_prob > bin_lower) & (y_prob <= bin_upper)
        prop_in_bin = in_bin.mean()
        
        if prop_in_bin > 0:
            # Calculate accuracy and confidence in this bin
            accuracy_in_bin = y_true[in_bin].mean() if in_bin.sum() > 0 else 0
            avg_confidence_in_bin = y_prob[in_bin].mean()
            
            # Add to ECE
            ece += np.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin
            
            bin_stats.append((bin_lower, bin_upper, in_bin.sum(), accuracy_in_bin, avg_confidence_in_bin))
        else:
            bin_stats.append((bin_lower, bin_upper, 0, 0, 0))
    
    return ece, bin_stats

def calculate_bucket_metrics(y_true: np.ndarray, y_prob: np.ndarray, 
                           bucket_thresholds: Dict[str, float]) -> Dict[str, Dict[str, Any]]:
    """Calculate metrics per confidence bucket."""
    bucket_metrics = {}
    
    # Sort thresholds in descending order
    sorted_buckets = sorted(bucket_thresholds.items(), key=lambda x: x[1], reverse=True)
    
    for i, (bucket_name, threshold) in enumerate(sorted_buckets):
        if i == 0:
            # Highest bucket (e.g., HIGH)
            mask = y_prob >= threshold
        elif i == len(sorted_buckets) - 1:
            # Lowest bucket (e.g., NONE)
            mask = y_prob < threshold
        else:
            # Middle buckets
            upper_threshold = sorted_buckets[i-1][1]
            mask = (y_prob >= threshold) & (y_prob < upper_threshold)
        
        if mask.sum() > 0:
            accuracy = y_true[mask].mean()
            precision = y_true[mask].mean()  # Same as accuracy for binary classification
            count = mask.sum()
            avg_confidence = y_prob[mask].mean()
            
            bucket_metrics[bucket_name] = {
                "threshold": threshold,
                "count": int(count),
                "accuracy": float(accuracy),
                "precision": float(precision),
                "avg_confidence": float(avg_confidence),
                "calibration_error": float(abs(avg_confidence - accuracy))
            }
        else:
            bucket_metrics[bucket_name] = {
                "threshold": threshold,
                "count": 0,
                "accuracy": 0.0,
                "precision": 0.0,
                "avg_confidence": 0.0,
                "calibration_error": 0.0
            }
    
    return bucket_metrics

def calculate_overall_metrics(y_true: np.ndarray, y_prob: np.ndarray, 
                            y_pred: np.ndarray) -> Dict[str, float]:
    """Calculate overall evaluation metrics."""
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, brier_score_loss, roc_auc_score
    
    metrics = {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, average='binary', zero_division=0),
        "recall": recall_score(y_true, y_pred, average='binary', zero_division=0),
        "f1": f1_score(y_true, y_pred, average='binary', zero_division=0),
        "brier_score": brier_score_loss(y_true, y_prob),
        "roc_auc": roc_auc_score(y_true, y_prob) if len(np.unique(y_true)) > 1 else 0.0
    }
    
    return metrics

def find_high_confidence_errors(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """Find high-confidence errors for manual inspection."""
    errors = df[(df['y_true'] == 0) & (df['y_prob_calibrated'] >= 0.7)]
    
    if len(errors) == 0:
        return pd.DataFrame(columns=['doc_id', 'y_prob_calibrated', 'error_type'])
    
    # Sort by confidence (highest first)
    errors_sorted = errors.sort_values('y_prob_calibrated', ascending=False)
    
    return errors_sorted.head(top_n)[['doc_id', 'y_prob_calibrated']]

def check_monotonicity(bucket_metrics: Dict[str, Dict[str, Any]]) -> bool:
    """Check if precision decreases with confidence (monotonicity violation)."""
    sorted_buckets = sorted(bucket_metrics.items(), key=lambda x: x[1]['threshold'], reverse=True)
    
    violations = []
    prev_precision = 1.0
    
    for bucket_name, metrics in sorted_buckets:
        if metrics['count'] > 0:  # Only check non-empty buckets
            current_precision = metrics['precision']
            if current_precision > prev_precision:
                violations.append((bucket_name, prev_precision, current_precision))
            prev_precision = current_precision
    
    if violations:
        print("⚠️  Monotonicity violations detected:")
        for bucket, prev, curr in violations:
            print(f"  {bucket}: {prev:.3f} → {curr:.3f}")
        return False
    else:
        print("✅ No monotonicity violations in confidence buckets")
        return True

def generate_evaluation_report(calibration_path: str, output_dir: str) -> Dict[str, Any]:
    """Generate comprehensive evaluation report."""
    print("Generating calibration evaluation report...")
    
    # Load calibration artifact and model
    artifact, model = load_calibration_artifact(calibration_path)
    
    # Load test results
    test_results = load_test_results(output_dir)
    
    y_true = test_results['y_true'].values
    y_prob = test_results['y_prob_calibrated'].values
    y_pred = test_results['y_pred_calibrated'].values
    
    # Calculate overall metrics
    overall_metrics = calculate_overall_metrics(y_true, y_prob, y_pred)
    
    # Calculate ECE
    ece, bin_stats = calculate_ece(y_true, y_prob)
    overall_metrics['ece'] = ece
    
    # Calculate bucket metrics
    bucket_metrics = calculate_bucket_metrics(y_true, y_prob, BUCKET_THRESHOLDS)
    
    # Check monotonicity
    monotonic_ok = check_monotonicity(bucket_metrics)
    
    # Find high-confidence errors
    high_conf_errors = find_high_confidence_errors(test_results)
    
    # Compile report
    report = {
        "calibration_version": artifact['calibration_version'],
        "method": artifact['method'],
        "evaluated_at": pd.Timestamp.now().isoformat(),
        "overall_metrics": overall_metrics,
        "bucket_metrics": bucket_metrics,
        "monotonicity_check": monotonic_ok,
        "high_confidence_errors": {
            "count": len(high_conf_errors),
            "top_examples": high_conf_errors.to_dict('records') if len(high_conf_errors) > 0 else []
        },
        "bin_stats": [
            {
                "bin_lower": float(lower),
                "bin_upper": float(upper),
                "count": int(count),
                "accuracy": float(accuracy),
                "avg_confidence": float(confidence)
            }
            for lower, upper, count, accuracy, confidence in bin_stats
        ]
    }
    
    # Save metrics report
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    metrics_file = output_path / METRICS_FILE
    with open(metrics_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"Evaluation report saved to: {metrics_file}")
    
    # Print summary
    print(f"\n📊 Evaluation Summary:")
    print(f"Method: {artifact['method']}")
    print(f"Samples: {len(y_true)}")
    print(f"Accuracy: {overall_metrics['accuracy']:.4f}")
    print(f"Precision: {overall_metrics['precision']:.4f}")
    print(f"ECE: {ece:.4f}")
    print(f"Brier Score: {overall_metrics['brier_score']:.4f}")
    print(f"Monotonicity: {'✅ OK' if monotonic_ok else '⚠️  Violations'}")
    print(f"High-confidence errors: {len(high_conf_errors)}")
    
    print(f"\n📈 Bucket Performance:")
    for bucket_name, metrics in bucket_metrics.items():
        if metrics['count'] > 0:
            print(f"  {bucket_name}: {metrics['precision']:.3f} precision ({metrics['count']} samples)")
    
    if len(high_conf_errors) > 0:
        print(f"\n⚠️  Top {len(high_conf_errors)} High-Confidence Errors:")
        for _, row in high_conf_errors.iterrows():
            print(f"  Doc {row['doc_id']}: {row['y_prob_calibrated']:.3f} confidence")
    
    return report

def main(calibration_path: str, output_dir: str = OUTPUT_DIR):
    """Main evaluation function."""
    print(f"Evaluating calibration: {calibration_path}")
    
    # Generate evaluation report
    report = generate_evaluation_report(calibration_path, output_dir)
    
    return report

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Evaluate merchant confidence calibration")
    parser.add_argument("--calibration", required=True, help="Path to calibration artifact JSON")
    parser.add_argument("--output", default=OUTPUT_DIR, help="Output directory")
    
    args = parser.parse_args()
    
    # Suppress warnings for cleaner output
    warnings.filterwarnings("ignore", category=FutureWarning)
    
    try:
        report = main(args.calibration, args.output)
        print(f"\n✅ Evaluation completed successfully!")
        
    except Exception as e:
        print(f"❌ Evaluation failed: {e}")
        raise
