"""
Tests for calibration retraining functionality.

Tests versioning, regression detection, and metrics export.
"""

import pytest
import tempfile
import shutil
import json
import pandas as pd
import numpy as np
from pathlib import Path
from unittest.mock import patch, MagicMock

from calibration.merchant.versioning import (
    parse_version, generate_next_version, get_latest_version,
    load_previous_artifact, version_exists, validate_version_format
)
from calibration.merchant.metrics_export import (
    export_calibration_summary, export_bucket_breakdown,
    generate_markdown_report, check_regression, generate_recommendation
)
from calibration.merchant.retrain import retrain, calculate_bucket_metrics, check_regression as retrain_check_regression


class TestVersioning:
    """Test version resolution and management."""
    
    def test_parse_version(self):
        """Test version string parsing."""
        # Test standard format
        version_num, date_str = parse_version("merchant_v1_20260125")
        assert version_num == 1
        assert date_str == "20260125"
        
        # Test without date
        version_num, date_str = parse_version("merchant_v2")
        assert version_num == 2
        assert len(date_str) == 8  # Should be today's date
        
        # Test invalid format
        with pytest.raises(ValueError):
            parse_version("invalid_version")
        
        with pytest.raises(ValueError):
            parse_version("merchant_x1_20260125")
    
    def test_generate_next_version_empty_dir(self):
        """Test version generation in empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            version = generate_next_version(temp_path)
            
            assert version.startswith("merchant_v1_")
            assert validate_version_format(version)
    
    def test_generate_next_version_existing(self):
        """Test version generation with existing artifacts."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create existing artifacts
            existing_versions = ["merchant_v1_20260120", "merchant_v2_20260122"]
            for version in existing_versions:
                artifact = {
                    "version": version,
                    "entity": "merchant",
                    "schema_version": 1
                }
                artifact_file = temp_path / f"calibration_{version}.json"
                with open(artifact_file, 'w') as f:
                    json.dump(artifact, f)
            
            # Should generate v3
            version = generate_next_version(temp_path)
            assert version.startswith("merchant_v3_")
            assert validate_version_format(version)
    
    def test_get_latest_version(self):
        """Test getting latest version."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Empty directory
            assert get_latest_version(temp_path) is None
            
            # Create artifacts
            versions = ["merchant_v1_20260120", "merchant_v3_20260125", "merchant_v2_20260122"]
            for version in versions:
                artifact = {"version": version, "entity": "merchant"}
                artifact_file = temp_path / f"calibration_{version}.json"
                with open(artifact_file, 'w') as f:
                    json.dump(artifact, f)
            
            latest = get_latest_version(temp_path)
            assert latest == "merchant_v3_20260125"
    
    def test_load_previous_artifact(self):
        """Test loading previous artifact."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # No artifacts
            assert load_previous_artifact(temp_path) is None
            
            # Create artifact
            artifact = {
                "version": "merchant_v1_20260125",
                "entity": "merchant",
                "schema_version": 1,
                "source_metrics": {"n": 100}
            }
            artifact_file = temp_path / "calibration_merchant_v1_20260125.json"
            with open(artifact_file, 'w') as f:
                json.dump(artifact, f)
            
            loaded = load_previous_artifact(temp_path)
            assert loaded is not None
            assert loaded["version"] == "merchant_v1_20260125"
    
    def test_version_exists(self):
        """Test version existence check."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Non-existent version
            assert not version_exists(temp_path, "merchant_v1_20260125")
            
            # Create artifact
            artifact_file = temp_path / "calibration_merchant_v1_20260125.json"
            artifact_file.touch()
            
            assert version_exists(temp_path, "merchant_v1_20260125")


class TestRegressionDetection:
    """Test regression detection logic."""
    
    def test_regression_detection_ece_increase(self):
        """Test regression detection when ECE increases significantly."""
        current = {"ece": 0.08, "accuracy": 0.85}
        previous = {"ece": 0.04, "accuracy": 0.83}
        
        status = check_regression(current, previous)
        assert "❌" in status
        assert "Regression Detected" in status
        assert "ECE increased" in status
    
    def test_regression_detection_high_precision_drop(self):
        """Test regression detection when HIGH bucket precision drops."""
        current = {
            "ece": 0.04,
            "bucket_metrics": {"HIGH": {"precision": 0.88}}
        }
        previous = {
            "ece": 0.04,
            "bucket_metrics": {"HIGH": {"precision": 0.92}}
        }
        
        status = check_regression(current, previous)
        assert "❌" in status
        assert "Regression Detected" in status
        assert "HIGH bucket precision dropped" in status
    
    def test_no_regression_improvement(self):
        """Test no regression with improvement."""
        current = {"ece": 0.03, "accuracy": 0.87}
        previous = {"ece": 0.05, "accuracy": 0.85}
        
        status = check_regression(current, previous)
        assert "✅" in status
        assert "Improved" in status
    
    def test_no_regression_neutral(self):
        """Test no regression with neutral change."""
        current = {"ece": 0.04, "accuracy": 0.85}
        previous = {"ece": 0.04, "accuracy": 0.85}
        
        status = check_regression(current, previous)
        assert "⚠️" in status
        assert "Neutral" in status
    
    def test_no_previous_version(self):
        """Test regression detection with no previous version."""
        current = {"ece": 0.04, "accuracy": 0.85}
        
        status = check_regression(current, None)
        assert "ℹ️" in status
        assert "No previous version" in status


class TestMetricsExport:
    """Test metrics export functionality."""
    
    def test_export_calibration_summary(self):
        """Test calibration summary CSV export."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            version = "merchant_v1_20260125"
            metrics = {
                "accuracy": 0.85,
                "precision": 0.87,
                "recall": 0.92,
                "ece": 0.04,
                "brier_score": 0.15,
                "bucket_metrics": {
                    "HIGH": {"precision": 0.95},
                    "MEDIUM": {"precision": 0.85},
                    "LOW": {"precision": 0.75}
                }
            }
            artifact = {
                "source_metrics": {"n": 1000},
                "calibrator_type": "piecewise_linear",
                "created_at": "2026-01-25T10:00:00Z"
            }
            
            summary_path = export_calibration_summary(temp_path, version, metrics, artifact)
            
            assert summary_path.exists()
            df = pd.read_csv(summary_path)
            assert len(df) == 1
            assert df.iloc[0]["version"] == version
            assert df.iloc[0]["accuracy"] == 0.85
            assert df.iloc[0]["ece"] == 0.04
            assert df.iloc[0]["high_bucket_precision"] == 0.95
    
    def test_export_bucket_breakdown(self):
        """Test bucket breakdown CSV export."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            version = "merchant_v1_20260125"
            test_results = pd.DataFrame({
                'y_true': [1, 1, 0, 1, 0],
                'y_prob_calibrated': [0.9, 0.8, 0.7, 0.95, 0.4],
                'confidence_bucket': ['HIGH', 'MEDIUM', 'MEDIUM', 'HIGH', 'LOW']
            })
            
            bucket_path = export_bucket_breakdown(temp_path, version, test_results)
            
            assert bucket_path.exists()
            df = pd.read_csv(bucket_path)
            assert len(df) == 3  # HIGH, MEDIUM, LOW
            assert set(df["confidence_bucket"]) == {"HIGH", "MEDIUM", "LOW"}
    
    def test_generate_markdown_report(self):
        """Test markdown report generation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            version = "merchant_v1_20260125"
            metrics = {
                "accuracy": 0.85,
                "precision": 0.87,
                "recall": 0.92,
                "ece": 0.04,
                "brier_score": 0.15
            }
            artifact = {
                "source_metrics": {"n": 1000},
                "calibrator_type": "piecewise_linear",
                "created_at": "2026-01-25T10:00:00Z"
            }
            test_results = pd.DataFrame({
                'y_true': [1, 1, 0, 1, 0],
                'y_prob_calibrated': [0.9, 0.8, 0.7, 0.95, 0.4],
                'confidence_bucket': ['HIGH', 'MEDIUM', 'MEDIUM', 'HIGH', 'LOW']
            })
            
            # Provide previous_metrics to avoid None error
            previous_metrics = {
                "accuracy": 0.83,
                "precision": 0.85,
                "recall": 0.90,
                "ece": 0.05,
                "brier_score": 0.16
            }
            
            report_path = generate_markdown_report(temp_path, version, metrics, artifact, test_results, previous_metrics)
            
            assert report_path.exists()
            content = report_path.read_text()
            assert "# Merchant Calibration Report" in content
            assert version in content
            assert "## Executive Summary" in content
            assert "## Performance Metrics" in content
            assert "## Recommendation" in content
    
    def test_generate_recommendation(self):
        """Test recommendation generation."""
        # Good case
        metrics = {"ece": 0.03, "bucket_metrics": {"HIGH": {"precision": 0.95}}}
        recommendation = generate_recommendation(metrics, None, "✅ Improved")
        assert "Safe to Deploy" in recommendation
        
        # Needs improvement case
        metrics = {"ece": 0.12, "bucket_metrics": {"HIGH": {"precision": 0.80}}}
        recommendation = generate_recommendation(metrics, None, "⚠️ Neutral")
        assert "Needs More Data" in recommendation
        
        # Regression case
        recommendation = generate_recommendation(metrics, None, "❌ Regression Detected")
        assert "Needs More Data" in recommendation


class TestRetrainEntrypoint:
    """Test the main retrain functionality."""
    
    def test_calculate_bucket_metrics(self):
        """Test bucket metrics calculation."""
        test_results = pd.DataFrame({
            'y_true': [1, 1, 0, 1, 0, 1],
            'y_prob_calibrated': [0.9, 0.8, 0.7, 0.95, 0.4, 0.85],
            'confidence_bucket': ['HIGH', 'MEDIUM', 'MEDIUM', 'HIGH', 'LOW', 'HIGH']
        })
        
        bucket_metrics = calculate_bucket_metrics(test_results)
        
        assert "HIGH" in bucket_metrics
        assert "MEDIUM" in bucket_metrics
        assert "LOW" in bucket_metrics
        
        # Check HIGH bucket: indices 0, 3, 5 -> y_true [1, 1, 1] = 3/3 = 1.0 precision
        high_metrics = bucket_metrics["HIGH"]
        assert high_metrics["count"] == 3
        assert high_metrics["precision"] == 1.0
        
        # Check MEDIUM bucket: indices 1, 2 -> y_true [1, 0] = 1/2 = 0.5 precision
        medium_metrics = bucket_metrics["MEDIUM"]
        assert medium_metrics["count"] == 2
        assert medium_metrics["precision"] == 0.5
        
        # Check LOW bucket: index 4 -> y_true [0] = 0/1 = 0.0 precision
        low_metrics = bucket_metrics["LOW"]
        assert low_metrics["count"] == 1
        assert low_metrics["precision"] == 0.0
    
    @patch('calibration.merchant.retrain.load_dataset')
    @patch('calibration.merchant.retrain.prepare_features')
    @patch('calibration.merchant.retrain.train_isotonic_regression')
    @patch('calibration.merchant.calibrate.pickle.dump')
    def test_retrain_basic_flow(self, mock_pickle, mock_train, mock_prepare, mock_load):
        """Test basic retrain flow with mocked dependencies."""
        # Mock data
        df = pd.DataFrame({
            'doc_id': [f'doc_{i}' for i in range(100)],
            'is_correct': [1] * 80 + [0] * 20,
            'raw_confidence': np.random.random(100),
            'confidence_bucket': np.random.choice(['HIGH', 'MEDIUM', 'LOW'], 100)
        })
        mock_load.return_value = df
        
        # Mock features
        X = np.random.random((100, 5))
        feature_info = {
            "features_used": ["raw_confidence", "winner_margin"],
            "feature_types": {"raw_confidence": "float64", "winner_margin": "float64"},
            "n_samples": 100
        }
        mock_prepare.return_value = X, feature_info
        
        # Mock model
        from sklearn.isotonic import IsotonicRegression
        mock_model = MagicMock()
        mock_model.predict = MagicMock(return_value=np.random.random(20))
        # Make it look like a fitted model
        mock_model.X_thresholds_ = np.array([0.0, 0.5, 1.0])
        mock_model.y_thresholds_ = np.array([0.1, 0.6, 0.9])
        mock_train.return_value = (mock_model, np.random.random(80))
        
        # Run retrain
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create a temporary CSV file
            csv_path = temp_path / "test_data.csv"
            df.to_csv(csv_path, index=False)
            
            results = retrain(
                data_path=str(csv_path),
                output_dir=str(temp_path / "output"),
                method="isotonic"
            )
            
            # Verify results
            assert "version" in results
            assert results["version"].startswith("merchant_v")
            assert "calibration_path" in results
            assert "metrics_path" in results
            assert "report_path" in results
            
            # Verify files exist
            assert Path(results["calibration_path"]).exists()
            assert Path(results["metrics_path"]).exists()
            assert Path(results["report_path"]).exists()
    
    def test_version_collision_detection(self):
        """Test version collision detection."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create existing artifact
            existing_version = "merchant_v1_20260125"
            artifact = {"version": existing_version, "entity": "merchant"}
            artifact_file = temp_path / f"calibration_{existing_version}.json"
            with open(artifact_file, 'w') as f:
                json.dump(artifact, f)
            
            # Try to retrain with same version - should fail
            with patch('calibration.merchant.retrain.load_dataset') as mock_load:
                mock_load.return_value = pd.DataFrame({
                    'doc_id': ['doc_1'],
                    'is_correct': [1],
                    'raw_confidence': [0.8]
                })
                
                with pytest.raises(ValueError, match="Version .* already exists"):
                    retrain(
                        data_path="dummy.csv",
                        output_dir=str(temp_path),
                        version_tag=existing_version
                    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
