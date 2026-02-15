"""
Unit tests for confidence calibration runtime hook.

Tests piecewise linear interpolation, gating logic, and integration with entity extraction.
"""

import pytest
import json
import os
import tempfile
from pathlib import Path
from app.pipelines.confidence_calibration import (
    CalibrationModel, calibrate_confidence, get_calibration_info, clear_calibration_cache
)
from app.pipelines.features import bucket_confidence


class TestPiecewiseLinearCalibration:
    """Test piecewise linear interpolation logic."""
    
    def test_exact_breakpoint_values(self):
        """Test that exact breakpoint values are returned correctly."""
        breakpoints = [
            {"x": 0.0, "y": 0.1},
            {"x": 0.5, "y": 0.6},
            {"x": 1.0, "y": 0.95}
        ]
        
        model = CalibrationModel(
            entity="test",
            version="test_v1",
            calibrator_type="piecewise_linear",
            breakpoints=breakpoints,
            feature_requirements=["raw_confidence"],
            created_at="2024-01-01"
        )
        
        # Test exact breakpoints
        assert model.apply(0.0, {"raw_confidence": 0.0}) == 0.1
        assert model.apply(0.5, {"raw_confidence": 0.5}) == 0.6
        assert model.apply(1.0, {"raw_confidence": 1.0}) == 0.95
    
    def test_interpolation_between_breakpoints(self):
        """Test linear interpolation between breakpoints."""
        breakpoints = [
            {"x": 0.0, "y": 0.0},
            {"x": 0.5, "y": 0.5},
            {"x": 1.0, "y": 1.0}
        ]
        
        model = CalibrationModel(
            entity="test",
            version="test_v1",
            calibrator_type="piecewise_linear",
            breakpoints=breakpoints,
            feature_requirements=["raw_confidence"],
            created_at="2024-01-01"
        )
        
        # Test midpoint interpolation
        result = model.apply(0.25, {"raw_confidence": 0.25})
        assert abs(result - 0.25) < 0.01  # Should be approximately 0.25
        
        result = model.apply(0.75, {"raw_confidence": 0.75})
        assert abs(result - 0.75) < 0.01  # Should be approximately 0.75
    
    def test_clamp_behavior(self):
        """Test that values outside [0, 1] are clamped."""
        breakpoints = [
            {"x": 0.0, "y": 0.1},
            {"x": 1.0, "y": 0.9}
        ]
        
        model = CalibrationModel(
            entity="test",
            version="test_v1",
            calibrator_type="piecewise_linear",
            breakpoints=breakpoints,
            feature_requirements=["raw_confidence"],
            created_at="2024-01-01"
        )
        
        # Test input clamping
        assert model.apply(-0.5, {"raw_confidence": -0.5}) == 0.1  # Clamps to 0.0, returns y at x=0.0
        assert model.apply(1.5, {"raw_confidence": 1.5}) == 0.9   # Clamps to 1.0, returns y at x=1.0
        
        # Test output clamping (if breakpoint y values exceed [0, 1])
        breakpoints_extreme = [
            {"x": 0.0, "y": -0.2},
            {"x": 1.0, "y": 1.2}
        ]
        
        model_extreme = CalibrationModel(
            entity="test",
            version="test_v1",
            calibrator_type="piecewise_linear",
            breakpoints=breakpoints_extreme,
            feature_requirements=["raw_confidence"],
            created_at="2024-01-01"
        )
        
        assert model_extreme.apply(0.0, {"raw_confidence": 0.0}) == 0.0  # Clamped from -0.2
        assert model_extreme.apply(1.0, {"raw_confidence": 1.0}) == 1.0  # Clamped from 1.2


class TestCalibrationGating:
    """Test gating logic for confidence calibration."""
    
    def setup_method(self):
        """Clear environment and cache before each test."""
        clear_calibration_cache()
        for key in ['ENABLE_CONFIDENCE_CALIBRATION', 'CONFIDENCE_CALIBRATION_PATH', 'CONFIDENCE_CALIBRATION_ENTITY']:
            if key in os.environ:
                del os.environ[key]
    
    def teardown_method(self):
        """Clean up after each test."""
        clear_calibration_cache()
        for key in ['ENABLE_CONFIDENCE_CALIBRATION', 'CONFIDENCE_CALIBRATION_PATH', 'CONFIDENCE_CALIBRATION_ENTITY']:
            if key in os.environ:
                del os.environ[key]
    
    def test_gating_disabled_returns_raw(self):
        """Test that calibration is skipped when disabled."""
        raw_conf = 0.75
        features = {"raw_confidence": raw_conf}
        evidence = {}
        
        # Calibration disabled (default)
        calibrated_conf, meta = calibrate_confidence("merchant", raw_conf, features, evidence)
        
        assert calibrated_conf == raw_conf
        assert meta["applied"] == False
        assert meta["version"] is None
    
    def test_missing_path_returns_raw_with_error_meta(self):
        """Test that missing calibration path returns raw confidence with error."""
        os.environ["ENABLE_CONFIDENCE_CALIBRATION"] = "1"
        # Don't set CONFIDENCE_CALIBRATION_PATH
        
        raw_conf = 0.75
        features = {"raw_confidence": raw_conf}
        evidence = {}
        
        calibrated_conf, meta = calibrate_confidence("merchant", raw_conf, features, evidence)
        
        assert calibrated_conf == raw_conf
        assert meta["applied"] == False
        assert meta["error"] == "missing_CONFIDENCE_CALIBRATION_PATH"
    
    def test_invalid_path_returns_raw_with_error(self):
        """Test that invalid calibration path returns raw confidence with error."""
        os.environ["ENABLE_CONFIDENCE_CALIBRATION"] = "1"
        os.environ["CONFIDENCE_CALIBRATION_PATH"] = "/nonexistent/path/calibration.json"
        
        raw_conf = 0.75
        features = {"raw_confidence": raw_conf}
        evidence = {}
        
        calibrated_conf, meta = calibrate_confidence("merchant", raw_conf, features, evidence)
        
        assert calibrated_conf == raw_conf
        assert meta["applied"] == False
        assert "calibration_file_not_found" in meta["error"]
    
    def test_entity_filter_mismatch_returns_raw(self):
        """Test that entity filter mismatch returns raw confidence."""
        os.environ["ENABLE_CONFIDENCE_CALIBRATION"] = "1"
        os.environ["CONFIDENCE_CALIBRATION_ENTITY"] = "total"  # Filter for total, not merchant
        
        raw_conf = 0.75
        features = {"raw_confidence": raw_conf}
        evidence = {}
        
        calibrated_conf, meta = calibrate_confidence("merchant", raw_conf, features, evidence)
        
        assert calibrated_conf == raw_conf
        assert meta["applied"] == False
        assert "entity_filter_mismatch" in meta["error"]
    
    def test_valid_calibration_applies_successfully(self):
        """Test that valid calibration artifact is applied correctly."""
        # Create temporary calibration artifact
        artifact = {
            "schema_version": 1,
            "entity": "merchant",
            "calibrator_type": "piecewise_linear",
            "version": "test_v1",
            "breakpoints": [
                {"x": 0.0, "y": 0.0},
                {"x": 0.5, "y": 0.4},  # Conservative mapping
                {"x": 1.0, "y": 0.9}
            ],
            "feature_requirements": ["raw_confidence"],
            "created_at": "2024-01-01"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(artifact, f)
            temp_path = f.name
        
        try:
            os.environ["ENABLE_CONFIDENCE_CALIBRATION"] = "1"
            os.environ["CONFIDENCE_CALIBRATION_PATH"] = temp_path
            
            raw_conf = 0.5
            features = {"raw_confidence": raw_conf}
            evidence = {}
            
            calibrated_conf, meta = calibrate_confidence("merchant", raw_conf, features, evidence)
            
            assert meta["applied"] == True
            assert meta["version"] == "test_v1"
            assert meta["path"] == temp_path
            assert calibrated_conf == 0.4  # From breakpoint
            assert abs(meta["delta"] - (-0.1)) < 0.01
            
        finally:
            Path(temp_path).unlink()
            clear_calibration_cache()


class TestCalibrationIntegration:
    """Test integration with entity extraction."""
    
    def setup_method(self):
        """Clear environment and cache before each test."""
        clear_calibration_cache()
        for key in ['ENABLE_CONFIDENCE_CALIBRATION', 'CONFIDENCE_CALIBRATION_PATH', 'CONFIDENCE_CALIBRATION_ENTITY']:
            if key in os.environ:
                del os.environ[key]
    
    def teardown_method(self):
        """Clean up after each test."""
        clear_calibration_cache()
        for key in ['ENABLE_CONFIDENCE_CALIBRATION', 'CONFIDENCE_CALIBRATION_PATH', 'CONFIDENCE_CALIBRATION_ENTITY']:
            if key in os.environ:
                del os.environ[key]
    
    def test_apply_wires_into_entity_result_bucket_change(self):
        """Test that calibration can change confidence bucket."""
        from app.pipelines.features import _guess_merchant_entity
        
        # Create calibration artifact that reduces confidence
        artifact = {
            "schema_version": 1,
            "entity": "merchant",
            "calibrator_type": "piecewise_linear",
            "version": "test_bucket_v1",
            "breakpoints": [
                {"x": 0.0, "y": 0.0},
                {"x": 0.5, "y": 0.3},   # Reduce mid-range confidence
                {"x": 1.0, "y": 0.7}    # Cap high confidence
            ],
            "feature_requirements": ["raw_confidence"],
            "created_at": "2024-01-01"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(artifact, f)
            temp_path = f.name
        
        try:
            # Test without calibration
            lines = ["INVOICE", "Test Merchant Corp", "Total: $100"]
            result_no_cal = _guess_merchant_entity(lines)
            raw_bucket = result_no_cal.confidence_bucket
            
            # Test with calibration
            os.environ["ENABLE_CONFIDENCE_CALIBRATION"] = "1"
            os.environ["CONFIDENCE_CALIBRATION_PATH"] = temp_path
            clear_calibration_cache()
            
            result_with_cal = _guess_merchant_entity(lines)
            calibrated_bucket = result_with_cal.confidence_bucket
            
            # Verify calibration was applied
            assert result_with_cal.evidence["confidence_calibration"]["applied"] == True
            assert "confidence_raw" in result_with_cal.evidence
            assert "confidence_calibrated" in result_with_cal.evidence
            
            # Verify confidence changed
            raw_conf = result_with_cal.evidence["confidence_raw"]
            cal_conf = result_with_cal.evidence["confidence_calibrated"]
            
            # With our conservative mapping, calibrated should be lower
            assert cal_conf <= raw_conf
            
            # Verify bucket might change
            raw_bucket_computed = bucket_confidence(raw_conf)
            cal_bucket_computed = bucket_confidence(cal_conf)
            
            assert result_with_cal.confidence_bucket == cal_bucket_computed
            
        finally:
            Path(temp_path).unlink()
            clear_calibration_cache()
    
    def test_calibration_metadata_in_evidence(self):
        """Test that calibration metadata is properly recorded in evidence."""
        from app.pipelines.features import _guess_merchant_entity
        
        artifact = {
            "schema_version": 1,
            "entity": "merchant",
            "calibrator_type": "piecewise_linear",
            "version": "test_meta_v1",
            "breakpoints": [
                {"x": 0.0, "y": 0.0},
                {"x": 1.0, "y": 1.0}
            ],
            "feature_requirements": ["raw_confidence"],
            "created_at": "2024-01-01"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(artifact, f)
            temp_path = f.name
        
        try:
            os.environ["ENABLE_CONFIDENCE_CALIBRATION"] = "1"
            os.environ["CONFIDENCE_CALIBRATION_PATH"] = temp_path
            clear_calibration_cache()
            
            lines = ["INVOICE", "Test Merchant", "Total: $100"]
            result = _guess_merchant_entity(lines)
            
            # Verify metadata structure
            cal_meta = result.evidence["confidence_calibration"]
            assert cal_meta["applied"] == True
            assert cal_meta["version"] == "test_meta_v1"
            assert cal_meta["path"] == temp_path
            assert cal_meta["calibrator_type"] == "piecewise_linear"
            assert "raw_confidence" in cal_meta
            assert "calibrated_confidence" in cal_meta
            assert "delta" in cal_meta
            
            # Verify raw and calibrated are in evidence
            assert "confidence_raw" in result.evidence
            assert "confidence_calibrated" in result.evidence
            
        finally:
            Path(temp_path).unlink()
            clear_calibration_cache()


class TestCalibrationModelLoading:
    """Test calibration model loading and validation."""
    
    def test_load_valid_artifact(self):
        """Test loading a valid calibration artifact."""
        artifact = {
            "schema_version": 1,
            "entity": "merchant",
            "calibrator_type": "piecewise_linear",
            "version": "test_v1",
            "breakpoints": [
                {"x": 0.0, "y": 0.0},
                {"x": 1.0, "y": 1.0}
            ],
            "feature_requirements": ["raw_confidence"],
            "created_at": "2024-01-01",
            "notes": "Test artifact"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(artifact, f)
            temp_path = f.name
        
        try:
            model = CalibrationModel.load_from_path(temp_path)
            
            assert model.entity == "merchant"
            assert model.version == "test_v1"
            assert model.calibrator_type == "piecewise_linear"
            assert len(model.breakpoints) == 2
            assert model.notes == "Test artifact"
            
        finally:
            Path(temp_path).unlink()
    
    def test_load_missing_fields_raises_error(self):
        """Test that missing required fields raises error."""
        artifact = {
            "entity": "merchant",
            "version": "test_v1"
            # Missing other required fields
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(artifact, f)
            temp_path = f.name
        
        try:
            with pytest.raises(ValueError, match="Missing required fields"):
                CalibrationModel.load_from_path(temp_path)
        finally:
            Path(temp_path).unlink()
    
    def test_breakpoints_sorted_by_x(self):
        """Test that breakpoints are sorted by x value."""
        artifact = {
            "schema_version": 1,
            "entity": "merchant",
            "calibrator_type": "piecewise_linear",
            "version": "test_v1",
            "breakpoints": [
                {"x": 1.0, "y": 0.9},
                {"x": 0.0, "y": 0.1},
                {"x": 0.5, "y": 0.5}
            ],
            "feature_requirements": ["raw_confidence"],
            "created_at": "2024-01-01"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(artifact, f)
            temp_path = f.name
        
        try:
            model = CalibrationModel.load_from_path(temp_path)
            
            # Verify breakpoints are sorted
            x_values = [bp['x'] for bp in model.breakpoints]
            assert x_values == sorted(x_values)
            assert x_values == [0.0, 0.5, 1.0]
            
        finally:
            Path(temp_path).unlink()


class TestSampleArtifact:
    """Test the sample calibration artifact."""
    
    def test_sample_artifact_loads_successfully(self):
        """Test that the sample artifact can be loaded."""
        sample_path = Path(__file__).parent.parent / "docs" / "calibration" / "merchant_confidence_v1.sample.json"
        
        if not sample_path.exists():
            pytest.skip(f"Sample artifact not found: {sample_path}")
        
        model = CalibrationModel.load_from_path(str(sample_path))
        
        assert model.entity == "merchant"
        assert model.calibrator_type == "piecewise_linear"
        assert len(model.breakpoints) > 0
        assert "raw_confidence" in model.feature_requirements
    
    def test_sample_artifact_conservative_mapping(self):
        """Test that sample artifact provides reasonable calibration mapping."""
        sample_path = Path(__file__).parent.parent / "docs" / "calibration" / "merchant_confidence_v1.sample.json"
        
        if not sample_path.exists():
            pytest.skip(f"Sample artifact not found: {sample_path}")
        
        model = CalibrationModel.load_from_path(str(sample_path))
        
        # Test that calibration is monotonic (higher raw -> higher calibrated)
        test_values = [0.1, 0.3, 0.5, 0.7, 0.9]
        calibrated_values = [model.apply(raw, {"raw_confidence": raw}) for raw in test_values]
        
        # Verify monotonicity
        for i in range(len(calibrated_values) - 1):
            assert calibrated_values[i] <= calibrated_values[i + 1], \
                f"Non-monotonic: {calibrated_values[i]} > {calibrated_values[i + 1]}"
        
        # Verify calibrated values are in valid range
        for cal in calibrated_values:
            assert 0.0 <= cal <= 1.0, f"Calibrated value out of range: {cal}"


class TestCalibrationCaching:
    """Test calibration model caching."""
    
    def setup_method(self):
        """Clear cache before each test."""
        clear_calibration_cache()
    
    def teardown_method(self):
        """Clean up after each test."""
        clear_calibration_cache()
        for key in ['ENABLE_CONFIDENCE_CALIBRATION', 'CONFIDENCE_CALIBRATION_PATH']:
            if key in os.environ:
                del os.environ[key]
    
    def test_calibration_model_cached(self):
        """Test that calibration model is cached after first load."""
        artifact = {
            "schema_version": 1,
            "entity": "merchant",
            "calibrator_type": "piecewise_linear",
            "version": "cache_test_v1",
            "breakpoints": [
                {"x": 0.0, "y": 0.0},
                {"x": 1.0, "y": 1.0}
            ],
            "feature_requirements": ["raw_confidence"],
            "created_at": "2024-01-01"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(artifact, f)
            temp_path = f.name
        
        try:
            os.environ["ENABLE_CONFIDENCE_CALIBRATION"] = "1"
            os.environ["CONFIDENCE_CALIBRATION_PATH"] = temp_path
            
            # First call should load and cache
            _, meta1 = calibrate_confidence("merchant", 0.5, {"raw_confidence": 0.5}, {})
            
            # Second call should use cache
            _, meta2 = calibrate_confidence("merchant", 0.6, {"raw_confidence": 0.6}, {})
            
            # Both should succeed
            assert meta1["applied"] == True
            assert meta2["applied"] == True
            assert meta1["version"] == meta2["version"]
            
            # Check cache info
            info = get_calibration_info()
            assert info["cached_models"] == 1
            assert "merchant" in info["models"]
            
        finally:
            Path(temp_path).unlink()
            clear_calibration_cache()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
