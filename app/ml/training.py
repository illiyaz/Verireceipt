"""
Machine Learning Training Module for VeriReceipt

This module handles:
1. Loading feedback data (human corrections)
2. Extracting features from receipts
3. Training ML models to improve detection
4. Evaluating model performance
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import pickle
import json

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from sklearn.preprocessing import StandardScaler


class FeedbackLearner:
    """
    Learns from human feedback to improve fraud detection.
    
    Workflow:
    1. Collect feedback from CSV/DB
    2. Extract features from analyzed receipts
    3. Train ML model on corrected labels
    4. Use model to adjust rule weights or provide ML score
    """
    
    def __init__(self, model_path: str = "data/models/feedback_model.pkl"):
        self.model_path = Path(model_path)
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = []
        self.label_mapping = {"real": 0, "suspicious": 1, "fake": 2}
        self.reverse_label_mapping = {v: k for k, v in self.label_mapping.items()}
    
    def load_feedback_data(self, feedback_csv: str = "data/logs/feedback.csv") -> pd.DataFrame:
        """
        Load human feedback from CSV.
        
        Expected columns:
        - analysis_ref: Reference to original analysis
        - given_label: Human-corrected label (real/suspicious/fake)
        - reviewer_id: Who provided feedback
        - timestamp: When feedback was given
        """
        feedback_path = Path(feedback_csv)
        if not feedback_path.exists():
            print(f"No feedback data found at {feedback_csv}")
            return pd.DataFrame()
        
        return pd.read_csv(feedback_path)
    
    def load_analysis_data(self, decisions_csv: str = "data/logs/decisions.csv") -> pd.DataFrame:
        """
        Load all analysis results with features.
        """
        decisions_path = Path(decisions_csv)
        if not decisions_path.exists():
            print(f"No analysis data found at {decisions_csv}")
            return pd.DataFrame()
        
        return pd.read_csv(decisions_csv)
    
    def merge_feedback_with_features(
        self,
        feedback_df: pd.DataFrame,
        analysis_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Merge human feedback with extracted features.
        
        This creates the training dataset:
        - Features: All extracted features from analysis
        - Labels: Human-corrected labels from feedback
        """
        # Merge on analysis_ref (filename or ID)
        merged = pd.merge(
            feedback_df,
            analysis_df,
            left_on='analysis_ref',
            right_on='file_path',
            how='inner',
            suffixes=('_feedback', '_analysis')
        )
        
        return merged
    
    def extract_feature_vector(self, row: pd.Series) -> np.ndarray:
        """
        Extract numerical feature vector from analysis row.
        
        Features include:
        - Engine score
        - File size
        - Number of pages
        - Text features (amounts, dates, etc.)
        - Layout features
        - Forensic features
        """
        features = []
        
        # Basic features
        features.append(float(row.get('score', 0.0)))
        features.append(float(row.get('file_size_bytes', 0)) / 1024)  # KB
        features.append(float(row.get('num_pages', 1)))
        
        # Text features (parse from JSON if stored)
        features.append(1.0 if row.get('has_any_amount', False) else 0.0)
        features.append(1.0 if row.get('has_date', False) else 0.0)
        features.append(1.0 if row.get('has_merchant', False) else 0.0)
        features.append(1.0 if row.get('total_mismatch', False) else 0.0)
        features.append(float(row.get('num_lines', 0)))
        
        # Metadata features
        features.append(1.0 if row.get('suspicious_producer', False) else 0.0)
        features.append(1.0 if row.get('has_creation_date', True) else 0.0)
        features.append(1.0 if row.get('exif_present', False) else 0.0)
        
        # Forensic features
        features.append(float(row.get('uppercase_ratio', 0.0)))
        features.append(float(row.get('unique_char_count', 0)))
        features.append(float(row.get('numeric_line_ratio', 0.0)))
        
        return np.array(features)
    
    def prepare_training_data(
        self,
        feedback_csv: str = "data/logs/feedback.csv",
        analysis_csv: str = "data/logs/decisions.csv"
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare X (features) and y (labels) for training.
        """
        feedback_df = self.load_feedback_data(feedback_csv)
        analysis_df = self.load_analysis_data(analysis_csv)
        
        if feedback_df.empty or analysis_df.empty:
            print("Insufficient data for training")
            return np.array([]), np.array([])
        
        merged_df = self.merge_feedback_with_features(feedback_df, analysis_df)
        
        if merged_df.empty:
            print("No matching feedback and analysis data")
            return np.array([]), np.array([])
        
        # Extract features and labels
        X = np.array([self.extract_feature_vector(row) for _, row in merged_df.iterrows()])
        y = np.array([self.label_mapping[row['given_label']] for _, row in merged_df.iterrows()])
        
        self.feature_names = [
            'engine_score', 'file_size_kb', 'num_pages',
            'has_amount', 'has_date', 'has_merchant', 'total_mismatch', 'num_lines',
            'suspicious_producer', 'has_creation_date', 'exif_present',
            'uppercase_ratio', 'unique_char_count', 'numeric_line_ratio'
        ]
        
        return X, y
    
    def train_model(
        self,
        X: np.ndarray,
        y: np.ndarray,
        model_type: str = "random_forest"
    ) -> Dict[str, float]:
        """
        Train ML model on feedback data.
        
        Args:
            X: Feature matrix
            y: Labels (0=real, 1=suspicious, 2=fake)
            model_type: "random_forest" or "gradient_boosting"
        
        Returns:
            Dictionary with training metrics
        """
        if len(X) < 10:
            print(f"Insufficient training data: {len(X)} samples. Need at least 10.")
            return {}
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y if len(np.unique(y)) > 1 else None
        )
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train model
        if model_type == "random_forest":
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                class_weight='balanced'
            )
        elif model_type == "gradient_boosting":
            self.model = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=5,
                random_state=42
            )
        else:
            raise ValueError(f"Unknown model type: {model_type}")
        
        self.model.fit(X_train_scaled, y_train)
        
        # Evaluate
        y_pred = self.model.predict(X_test_scaled)
        
        metrics = {
            'train_accuracy': accuracy_score(y_train, self.model.predict(X_train_scaled)),
            'test_accuracy': accuracy_score(y_test, y_pred),
            'train_samples': len(X_train),
            'test_samples': len(X_test),
            'model_type': model_type,
            'timestamp': datetime.now().isoformat()
        }
        
        # Cross-validation score
        if len(X) >= 20:
            cv_scores = cross_val_score(self.model, X_train_scaled, y_train, cv=min(5, len(X_train) // 2))
            metrics['cv_mean'] = cv_scores.mean()
            metrics['cv_std'] = cv_scores.std()
        
        # Feature importance
        if hasattr(self.model, 'feature_importances_'):
            importance = dict(zip(self.feature_names, self.model.feature_importances_))
            metrics['feature_importance'] = importance
        
        print("\n=== Training Results ===")
        print(f"Model: {model_type}")
        print(f"Train Accuracy: {metrics['train_accuracy']:.3f}")
        print(f"Test Accuracy: {metrics['test_accuracy']:.3f}")
        if 'cv_mean' in metrics:
            print(f"CV Score: {metrics['cv_mean']:.3f} (+/- {metrics['cv_std']:.3f})")
        
        print("\nClassification Report:")
        print(classification_report(y_test, y_pred, target_names=['real', 'suspicious', 'fake']))
        
        print("\nConfusion Matrix:")
        print(confusion_matrix(y_test, y_pred))
        
        if 'feature_importance' in metrics:
            print("\nTop 5 Important Features:")
            sorted_features = sorted(metrics['feature_importance'].items(), key=lambda x: x[1], reverse=True)
            for feat, imp in sorted_features[:5]:
                print(f"  {feat}: {imp:.3f}")
        
        return metrics
    
    def save_model(self, metadata: Optional[Dict] = None):
        """Save trained model and scaler to disk."""
        if self.model is None:
            print("No model to save")
            return
        
        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'feature_names': self.feature_names,
            'label_mapping': self.label_mapping,
            'metadata': metadata or {}
        }
        
        with open(self.model_path, 'wb') as f:
            pickle.dump(model_data, f)
        
        print(f"\n✅ Model saved to {self.model_path}")
    
    def load_model(self):
        """Load trained model from disk."""
        if not self.model_path.exists():
            print(f"No saved model found at {self.model_path}")
            return False
        
        with open(self.model_path, 'rb') as f:
            model_data = pickle.load(f)
        
        self.model = model_data['model']
        self.scaler = model_data['scaler']
        self.feature_names = model_data['feature_names']
        self.label_mapping = model_data['label_mapping']
        
        print(f"✅ Model loaded from {self.model_path}")
        if 'metadata' in model_data:
            print(f"   Trained: {model_data['metadata'].get('timestamp', 'unknown')}")
            print(f"   Accuracy: {model_data['metadata'].get('test_accuracy', 'unknown')}")
        
        return True
    
    def predict(self, features: np.ndarray) -> Tuple[str, float]:
        """
        Predict label for new receipt using trained model.
        
        Args:
            features: Feature vector
        
        Returns:
            (predicted_label, confidence)
        """
        if self.model is None:
            raise ValueError("No model loaded. Train or load a model first.")
        
        features_scaled = self.scaler.transform(features.reshape(1, -1))
        prediction = self.model.predict(features_scaled)[0]
        probabilities = self.model.predict_proba(features_scaled)[0]
        
        label = self.reverse_label_mapping[prediction]
        confidence = probabilities[prediction]
        
        return label, confidence


def retrain_from_feedback():
    """
    Main function to retrain model from accumulated feedback.
    
    Run this periodically (e.g., weekly) to improve the system.
    """
    print("=" * 80)
    print("VeriReceipt - Retraining from Human Feedback")
    print("=" * 80)
    print()
    
    learner = FeedbackLearner()
    
    # Prepare data
    print("Loading feedback and analysis data...")
    X, y = learner.prepare_training_data()
    
    if len(X) == 0:
        print("\n❌ No training data available. Collect more feedback first.")
        return
    
    print(f"✅ Loaded {len(X)} training samples")
    print(f"   Label distribution: {dict(zip(*np.unique(y, return_counts=True)))}")
    print()
    
    # Train model
    print("Training model...")
    metrics = learner.train_model(X, y, model_type="random_forest")
    
    if not metrics:
        return
    
    # Save model
    learner.save_model(metadata=metrics)
    
    # Save metrics
    metrics_path = Path("data/models/training_metrics.json")
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert numpy types to Python types for JSON serialization
    json_metrics = {}
    for k, v in metrics.items():
        if isinstance(v, (np.integer, np.floating)):
            json_metrics[k] = float(v)
        elif isinstance(v, dict):
            json_metrics[k] = {str(k2): float(v2) if isinstance(v2, (np.integer, np.floating)) else v2 
                               for k2, v2 in v.items()}
        else:
            json_metrics[k] = v
    
    with open(metrics_path, 'w') as f:
        json.dump(json_metrics, f, indent=2)
    
    print(f"✅ Metrics saved to {metrics_path}")
    print()
    print("=" * 80)
    print("✅ Retraining complete!")
    print("=" * 80)


if __name__ == "__main__":
    retrain_from_feedback()
