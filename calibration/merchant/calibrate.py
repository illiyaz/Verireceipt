"""
Merchant confidence calibration training script.

Loads labeled extraction results and trains calibration models
to map raw confidence scores to calibrated probabilities.
"""

import json
import pickle
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
import warnings

from .config import (
    CALIBRATION_VERSION, CALIBRATION_METHOD, FEATURES_USED, OPTIONAL_FEATURES,
    BUCKET_THRESHOLDS, ISOTONIC_PARAMS, LOGISTIC_PARAMS, RANDOM_SEED,
    OUTPUT_DIR, CALIBRATION_FILE, REQUIRED_COLUMNS, BOOLEAN_COLUMNS
)

# Set random seeds for reproducibility
np.random.seed(RANDOM_SEED)

def load_dataset(filepath: str) -> pd.DataFrame:
    """Load labeled dataset from CSV or Parquet."""
    path = Path(filepath)
    
    if path.suffix.lower() == '.csv':
        df = pd.read_csv(filepath)
    elif path.suffix.lower() == '.parquet':
        df = pd.read_parquet(filepath)
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}")
    
    # Validate required columns
    missing_cols = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
    
    # Filter to merchant entities only
    if 'entity' in df.columns:
        df = df[df['entity'] == 'merchant'].copy()
    
    print(f"Loaded {len(df)} merchant extraction results")
    return df

def prepare_features(df: pd.DataFrame, include_optional: bool = False) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Prepare features for calibration model."""
    features = FEATURES_USED.copy()
    if include_optional:
        optional_available = [f for f in OPTIONAL_FEATURES if f in df.columns]
        features.extend(optional_available)
    
    # Create feature matrix
    X = df[features].copy()
    
    # Handle categorical features
    categorical_features = ['mode']
    for col in categorical_features:
        if col in X.columns:
            # Convert mode to numeric (strict=0, relaxed=1)
            if col == 'mode':
                X[col] = (X[col] == 'relaxed').astype(int)
    
    # Handle missing values in optional features
    for col in OPTIONAL_FEATURES:
        if col in X.columns:
            X[col] = X[col].fillna('unknown')
    
    # Ensure boolean columns are properly typed
    for col in BOOLEAN_COLUMNS:
        if col in X.columns:
            X[col] = X[col].astype(bool)
    
    feature_info = {
        "features_used": features,
        "feature_types": {col: str(X[col].dtype) for col in features},
        "n_samples": len(X),
        "optional_features_included": include_optional
    }
    
    return X.values, feature_info

def train_isotonic_regression(X: np.ndarray, y: np.ndarray) -> Tuple[IsotonicRegression, np.ndarray]:
    """Train isotonic regression calibration model using raw_confidence."""
    # For runtime compatibility, we must use raw_confidence (0-1 range)
    # Find the raw_confidence column (should be first if present)
    if X.shape[1] > 0:
        # Use first column as raw_confidence
        raw_confidence = X[:, 0].astype(float)
        
        # Ensure raw_confidence is in [0, 1] range
        raw_confidence = np.clip(raw_confidence, 0.0, 1.0)
        
        print(f"Using raw_confidence range: [{raw_confidence.min():.3f}, {raw_confidence.max():.3f}]")
    else:
        raise ValueError("No features available for calibration")
    
    model = IsotonicRegression(**ISOTONIC_PARAMS)
    model.fit(raw_confidence, y)
    
    return model, raw_confidence

def train_logistic_regression(X: np.ndarray, y: np.ndarray) -> Pipeline:
    """Train logistic regression calibration model."""
    # Identify categorical vs numerical features
    categorical_features = []
    numerical_features = []
    
    # Map feature indices to names (assuming order from FEATURES_USED)
    feature_names = FEATURES_USED.copy()
    if X.shape[1] > len(FEATURES_USED):
        # Add optional features if present
        optional_available = [f for f in OPTIONAL_FEATURES if f in FEATURES_USED + OPTIONAL_FEATURES]
        feature_names.extend(optional_available[:X.shape[1] - len(FEATURES_USED)])
    
    for i, name in enumerate(feature_names[:X.shape[1]]):
        if name in ['mode'] or name in OPTIONAL_FEATURES:
            categorical_features.append(i)
        else:
            numerical_features.append(i)
    
    # Create preprocessing pipeline
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', 'passthrough', numerical_features),
            ('cat', OneHotEncoder(handle_unknown='ignore', sparse=False), categorical_features)
        ]
    )
    
    # Create full pipeline
    pipeline = Pipeline([
        ('preprocessor', preprocessor),
        ('classifier', LogisticRegression(**LOGISTIC_PARAMS))
    ])
    
    pipeline.fit(X, y)
    
    return pipeline

def export_isotonic_breakpoints(model: Any, n_points: int = 50) -> list:
    """Export isotonic regression model as breakpoints for runtime."""
    # Handle tuple return from train_isotonic_regression
    if isinstance(model, tuple):
        model = model[0]
    
    if not hasattr(model, 'X_thresholds_') or not hasattr(model, 'y_thresholds_'):
        raise ValueError("Isotonic model not fitted")
    
    # Get the trained monotonic mapping
    X_thresholds = model.X_thresholds_
    y_thresholds = model.y_thresholds_
    
    # Downsample to n_points for runtime efficiency
    if len(X_thresholds) > n_points:
        # Sample evenly across the range
        indices = np.linspace(0, len(X_thresholds) - 1, n_points, dtype=int)
        X_sampled = X_thresholds[indices]
        y_sampled = y_thresholds[indices]
    else:
        X_sampled = X_thresholds
        y_sampled = y_thresholds
    
    # Convert to breakpoint format
    breakpoints = [
        {"x": float(x), "y": float(y)}
        for x, y in zip(X_sampled, y_sampled)
    ]
    
    return breakpoints


def save_calibration_artifact(model: Any, feature_info: Dict[str, Any], 
                            metrics: Dict[str, Any], output_dir: str) -> str:
    """Save calibration artifact to JSON file."""
    # Base artifact structure (runtime-compatible)
    artifact = {
        "schema_version": 1,
        "entity": "merchant",
        "calibrator_type": CALIBRATION_METHOD if CALIBRATION_METHOD == "piecewise_linear" else "piecewise_linear",
        "version": CALIBRATION_VERSION,
        "created_at": datetime.now().isoformat(),
        "feature_requirements": ["raw_confidence"],  # Runtime v1 only needs raw_confidence
        "notes": f"Trained on {feature_info['n_samples']} samples using {CALIBRATION_METHOD} method",
        "source_metrics": {
            "ece": metrics.get("ece", 0.0),
            "brier": metrics.get("brier_score", 0.0),
            "accuracy": metrics.get("accuracy", 0.0),
            "n": feature_info["n_samples"]
        },
        "breakpoints": []
    }
    
    # Export model-specific breakpoints
    if CALIBRATION_METHOD == "isotonic":
        # Export isotonic model as breakpoints
        artifact["breakpoints"] = export_isotonic_breakpoints(model, n_points=50)
        
        # Also save model params for offline debugging
        # Handle tuple return from train_isotonic_regression
        iso_model = model[0] if isinstance(model, tuple) else model
        artifact["model_params"] = {}
        if hasattr(iso_model, 'X_thresholds_'):
            artifact["model_params"]["X_min"] = float(iso_model.X_min_)
            artifact["model_params"]["X_max"] = float(iso_model.X_max_)
            artifact["model_params"]["y_min"] = float(iso_model.y_thresholds_.min())
            artifact["model_params"]["y_max"] = float(iso_model.y_thresholds_.max())
            artifact["model_params"]["n_thresholds"] = len(iso_model.X_thresholds_)
    
    elif CALIBRATION_METHOD == "logistic":
        # For runtime compatibility we export a 1D curve over raw_confidence by holding other features at 0/false.
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
            "n_features": len(model.named_steps['preprocessor'].get_feature_names_out()),
            "coefficients": model.named_steps['classifier'].coef_.tolist(),
            "intercept": float(model.named_steps['classifier'].intercept_) if hasattr(model.named_steps['classifier'], 'intercept_') else 0.0
        }
    
    # Add offline training metadata (not used by runtime)
    artifact["training_metadata"] = {
        "features_used": feature_info["features_used"],
        "feature_types": feature_info["feature_types"],
        "bucket_thresholds": BUCKET_THRESHOLDS,
        "training_samples": feature_info["n_samples"],
        "metrics": metrics
    }
    
    # Save to file
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    calibration_file = output_path / CALIBRATION_FILE
    with open(calibration_file, 'w') as f:
        json.dump(artifact, f, indent=2)
    
    # Also save model pickle for easier loading
    model_file = output_path / f"model_{CALIBRATION_VERSION}.pkl"
    with open(model_file, 'wb') as f:
        pickle.dump(model, f)
    
    print(f"Calibration artifact saved to: {calibration_file}")
    print(f"Model pickle saved to: {model_file}")
    
    return str(calibration_file)

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
    from sklearn.metrics import accuracy_score, precision_score, recall_score, brier_score_loss
    
    metrics = {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, average='binary', zero_division=0),
        "recall": recall_score(y_true, y_pred, average='binary', zero_division=0),
        "brier_score": brier_score_loss(y_true, y_prob),
        "ece": expected_calibration_error(y_true, y_prob, n_bins=10),
    }
    
    return metrics

def main(data_path: str, output_dir: str = OUTPUT_DIR, 
         include_optional: bool = False, test_size: float = 0.2):
    """Main calibration training function."""
    print(f"Starting merchant confidence calibration")
    print(f"Method: {CALIBRATION_METHOD}")
    print(f"Version: {CALIBRATION_VERSION}")
    
    # Load data
    df = load_dataset(data_path)
    
    # Prepare features
    X, feature_info = prepare_features(df, include_optional)
    y = df['is_correct'].values
    
    from sklearn.model_selection import train_test_split

    # Split using row indices so doc_id mapping stays correct
    idx = np.arange(len(df))

    if 'confidence_bucket' in df.columns:
        idx_train, idx_test = train_test_split(
            idx,
            test_size=test_size,
            random_state=RANDOM_SEED,
            stratify=df['confidence_bucket']
        )
    else:
        idx_train, idx_test = train_test_split(
            idx,
            test_size=test_size,
            random_state=RANDOM_SEED
        )

    X_train, X_test = X[idx_train], X[idx_test]
    y_train, y_test = y[idx_train], y[idx_test]
    
    print(f"Training set: {len(X_train)} samples")
    print(f"Test set: {len(X_test)} samples")
    print(f"Positive rate: {y.mean():.3f}")
    
    # Train model
    if CALIBRATION_METHOD == "isotonic":
        model, composite_score = train_isotonic_regression(X_train, y_train)
        
        # Apply calibration to test set using raw_confidence
        if X_test.shape[1] > 0:
            test_raw_confidence = X_test[:, 0].astype(float)
            test_raw_confidence = np.clip(test_raw_confidence, 0.0, 1.0)
        else:
            test_raw_confidence = np.zeros(len(X_test))
        
        y_prob_calibrated = model.predict(test_raw_confidence)
        
    elif CALIBRATION_METHOD == "logistic":
        model = train_logistic_regression(X_train, y_train)
        y_prob_calibrated = model.predict_proba(X_test)[:, 1]
    
    else:
        raise ValueError(f"Unsupported calibration method: {CALIBRATION_METHOD}")
    
    # Convert probabilities to predictions
    y_pred_calibrated = (y_prob_calibrated >= 0.5).astype(int)
    
    # Calculate metrics
    metrics = calculate_basic_metrics(y_test, y_pred_calibrated, y_prob_calibrated)
    metrics["training_samples"] = len(X_train)
    metrics["test_samples"] = len(X_test)
    
    print(f"Test set metrics:")
    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")
    
    # Save calibration artifact
    calibration_path = save_calibration_artifact(model, feature_info, metrics, output_dir)
    
    # Save test predictions for evaluation
    test_doc_ids = df.iloc[idx_test]['doc_id'].values if 'doc_id' in df.columns else idx_test

    test_results = pd.DataFrame({
        'doc_id': test_doc_ids,
        'y_true': y_test,
        'y_prob_calibrated': y_prob_calibrated,
        'y_pred_calibrated': y_pred_calibrated
    })
    
    test_results_path = Path(output_dir) / "test_results.csv"
    test_results.to_csv(test_results_path, index=False)
    print(f"Test results saved to: {test_results_path}")
    
    return calibration_path, metrics

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Train merchant confidence calibration model")
    parser.add_argument("--data", required=True, help="Path to labeled dataset (CSV/Parquet)")
    parser.add_argument("--output", default=OUTPUT_DIR, help="Output directory")
    parser.add_argument("--include-optional", action="store_true", help="Include optional features")
    parser.add_argument("--test-size", type=float, default=0.2, help="Test set proportion")
    
    args = parser.parse_args()
    
    # Suppress warnings for cleaner output
    warnings.filterwarnings("ignore", category=FutureWarning)
    
    try:
        calibration_path, metrics = main(
            data_path=args.data,
            output_dir=args.output,
            include_optional=args.include_optional,
            test_size=args.test_size
        )
        print(f"\nCalibration completed successfully!")
        print(f"Artifact: {calibration_path}")
        
    except Exception as e:
        print(f"Calibration failed: {e}")
        raise
