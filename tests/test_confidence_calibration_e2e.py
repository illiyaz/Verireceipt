"""
End-to-end smoke test for confidence calibration.

Tests the complete workflow from offline calibration artifact to runtime application.
"""

import pytest
import json
import os
import tempfile
from pathlib import Path
from app.pipelines.features import _guess_merchant_entity, bucket_confidence
from app.pipelines.confidence_calibration import (
    calibrate_confidence, get_calibration_info, clear_calibration_cache
)


class TestCalibrationDisabled:
    """Test behavior when calibration is disabled."""
    
    def setup_method(self):
        """Clear environment before each test."""
        clear_calibration_cache()
        for key in ['ENABLE_CONFIDENCE_CALIBRATION', 'CONFIDENCE_CALIBRATION_PATH']:
            if key in os.environ:
                del os.environ[key]
    
    def teardown_method(self):
        """Clean up after each test."""
        clear_calibration_cache()
        for key in ['ENABLE_CONFIDENCE_CALIBRATION', 'CONFIDENCE_CALIBRATION_PATH']:
            if key in os.environ:
                del os.environ[key]
    
    def test_disabled_flag_no_change(self):
        """Test that with flags off, confidence equals old value and no crash."""
        lines = ["INVOICE", "Test Merchant Corp", "Total: $100"]
        
        # Extract without calibration
        result = _guess_merchant_entity(lines)
        
        # Verify calibration was not applied
        assert result.evidence["confidence_calibration"]["applied"] == False
        
        # Verify confidence is present
        assert result.confidence > 0
        assert result.confidence_bucket in ["HIGH", "MEDIUM", "LOW", "NONE"]
        
        # Verify raw and calibrated are the same when not applied
        assert result.evidence["confidence_raw"] == result.evidence["confidence_calibrated"]


class TestCalibrationWithValidArtifact:
    """Test behavior with valid calibration artifact."""
    
    def setup_method(self):
        """Set up test environment."""
        clear_calibration_cache()
        for key in ['ENABLE_CONFIDENCE_CALIBRATION', 'CONFIDENCE_CALIBRATION_PATH']:
            if key in os.environ:
                del os.environ[key]
    
    def teardown_method(self):
        """Clean up after each test."""
        clear_calibration_cache()
        for key in ['ENABLE_CONFIDENCE_CALIBRATION', 'CONFIDENCE_CALIBRATION_PATH']:
            if key in os.environ:
                del os.environ[key]
    
    def test_valid_artifact_applies_mapping(self):
        """Test that valid artifact applies calibration deterministically."""
        # Use test fixture
        fixture_path = Path(__file__).parent / "fixtures" / "calibration_merchant_test.json"
        
        if not fixture_path.exists():
            pytest.skip(f"Test fixture not found: {fixture_path}")
        
        # Enable calibration
        os.environ["ENABLE_CONFIDENCE_CALIBRATION"] = "1"
        os.environ["CONFIDENCE_CALIBRATION_PATH"] = str(fixture_path)
        clear_calibration_cache()
        
        lines = ["INVOICE", "Test Merchant Corp", "Total: $100"]
        
        # Extract with calibration
        result = _guess_merchant_entity(lines)
        
        # Verify calibration was applied
        assert result.evidence["confidence_calibration"]["applied"] == True
        assert result.evidence["confidence_calibration"]["version"] == "merchant_test_v1"
        
        # Verify raw and calibrated are recorded
        assert "confidence_raw" in result.evidence
        assert "confidence_calibrated" in result.evidence
        
        # Verify calibrated confidence is used
        assert result.confidence == result.evidence["confidence_calibrated"]
        
        # Verify determinism - run again
        result2 = _guess_merchant_entity(lines)
        assert result2.confidence == result.confidence
        assert result2.confidence_bucket == result.confidence_bucket
    
    def test_bucket_changes_after_calibration(self):
        """Test that calibration can change confidence bucket."""
        fixture_path = Path(__file__).parent / "fixtures" / "calibration_merchant_test.json"
        
        if not fixture_path.exists():
            pytest.skip(f"Test fixture not found: {fixture_path}")
        
        # Create a more aggressive calibration that reduces confidence
        aggressive_artifact = {
            "schema_version": 1,
            "entity": "merchant",
            "calibrator_type": "piecewise_linear",
            "version": "merchant_aggressive_test",
            "created_at": "2026-01-25T00:00:00Z",
            "feature_requirements": ["raw_confidence"],
            "notes": "Aggressive conservative mapping for testing",
            "breakpoints": [
                {"x": 0.0, "y": 0.0},
                {"x": 0.5, "y": 0.3},   # Reduce mid-range significantly
                {"x": 1.0, "y": 0.7}    # Cap high confidence
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(aggressive_artifact, f)
            temp_path = f.name
        
        try:
            # Extract without calibration
            lines = ["INVOICE", "Test Merchant Corp", "Total: $100"]
            result_no_cal = _guess_merchant_entity(lines)
            raw_bucket = result_no_cal.confidence_bucket
            
            # Extract with aggressive calibration
            os.environ["ENABLE_CONFIDENCE_CALIBRATION"] = "1"
            os.environ["CONFIDENCE_CALIBRATION_PATH"] = temp_path
            clear_calibration_cache()
            
            result_with_cal = _guess_merchant_entity(lines)
            cal_bucket = result_with_cal.confidence_bucket
            
            # Verify calibration was applied
            assert result_with_cal.evidence["confidence_calibration"]["applied"] == True
            
            # Verify confidence changed
            raw_conf = result_with_cal.evidence["confidence_raw"]
            cal_conf = result_with_cal.evidence["confidence_calibrated"]
            
            # With aggressive mapping, calibrated should be lower
            assert cal_conf <= raw_conf
            
            # Verify bucket is computed from calibrated confidence
            expected_bucket = bucket_confidence(cal_conf)
            assert result_with_cal.confidence_bucket == expected_bucket
            
        finally:
            Path(temp_path).unlink()
            clear_calibration_cache()
    
    def test_evidence_contains_raw_and_meta(self):
        """Test that evidence contains all required audit fields."""
        fixture_path = Path(__file__).parent / "fixtures" / "calibration_merchant_test.json"
        
        if not fixture_path.exists():
            pytest.skip(f"Test fixture not found: {fixture_path}")
        
        os.environ["ENABLE_CONFIDENCE_CALIBRATION"] = "1"
        os.environ["CONFIDENCE_CALIBRATION_PATH"] = str(fixture_path)
        clear_calibration_cache()
        
        lines = ["INVOICE", "Test Merchant Corp", "Total: $100"]
        result = _guess_merchant_entity(lines)
        
        # Verify all required evidence fields
        assert "confidence_raw" in result.evidence
        assert "confidence_calibrated" in result.evidence
        assert "confidence_calibration" in result.evidence
        
        cal_meta = result.evidence["confidence_calibration"]
        
        # Verify calibration metadata structure
        assert "applied" in cal_meta
        assert "version" in cal_meta
        assert "path" in cal_meta
        assert "calibrator_type" in cal_meta
        
        # Verify values
        assert cal_meta["applied"] == True
        assert cal_meta["version"] == "merchant_test_v1"
        assert cal_meta["calibrator_type"] == "piecewise_linear"
        assert cal_meta["path"] == str(fixture_path)


class TestCalibrationWithInvalidArtifact:
    """Test fail-safe behavior with invalid artifacts."""
    
    def setup_method(self):
        """Set up test environment."""
        clear_calibration_cache()
        for key in ['ENABLE_CONFIDENCE_CALIBRATION', 'CONFIDENCE_CALIBRATION_PATH']:
            if key in os.environ:
                del os.environ[key]
    
    def teardown_method(self):
        """Clean up after each test."""
        clear_calibration_cache()
        for key in ['ENABLE_CONFIDENCE_CALIBRATION', 'CONFIDENCE_CALIBRATION_PATH']:
            if key in os.environ:
                del os.environ[key]
    
    def test_invalid_artifact_falls_back_raw(self):
        """Test that invalid artifact falls back to raw confidence."""
        # Create invalid artifact (missing required fields)
        invalid_artifact = {
            "entity": "merchant",
            "version": "invalid_test"
            # Missing: schema_version, calibrator_type, breakpoints, etc.
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(invalid_artifact, f)
            temp_path = f.name
        
        try:
            os.environ["ENABLE_CONFIDENCE_CALIBRATION"] = "1"
            os.environ["CONFIDENCE_CALIBRATION_PATH"] = temp_path
            clear_calibration_cache()
            
            lines = ["INVOICE", "Test Merchant Corp", "Total: $100"]
            result = _guess_merchant_entity(lines)
            
            # Verify calibration was NOT applied
            assert result.evidence["confidence_calibration"]["applied"] == False
            
            # Verify error is recorded
            assert "error" in result.evidence["confidence_calibration"]
            assert result.evidence["confidence_calibration"]["error"] is not None
            
            # Verify fallback to raw confidence
            assert result.confidence == result.evidence["confidence_raw"]
            
            # Verify no crash
            assert result.value is not None
            assert result.confidence > 0
            
        finally:
            Path(temp_path).unlink()
            clear_calibration_cache()
    
    def test_missing_file_falls_back_raw(self):
        """Test that missing calibration file falls back to raw confidence."""
        os.environ["ENABLE_CONFIDENCE_CALIBRATION"] = "1"
        os.environ["CONFIDENCE_CALIBRATION_PATH"] = "/nonexistent/path/calibration.json"
        clear_calibration_cache()
        
        lines = ["INVOICE", "Test Merchant Corp", "Total: $100"]
        result = _guess_merchant_entity(lines)
        
        # Verify calibration was NOT applied
        assert result.evidence["confidence_calibration"]["applied"] == False
        
        # Verify error is recorded
        assert "error" in result.evidence["confidence_calibration"]
        assert "calibration_file_not_found" in result.evidence["confidence_calibration"]["error"]
        
        # Verify fallback to raw confidence
        assert result.confidence == result.evidence["confidence_raw"]


class TestCalibrationCaching:
    """Test calibration model caching behavior."""
    
    def setup_method(self):
        """Set up test environment."""
        clear_calibration_cache()
        for key in ['ENABLE_CONFIDENCE_CALIBRATION', 'CONFIDENCE_CALIBRATION_PATH']:
            if key in os.environ:
                del os.environ[key]
    
    def teardown_method(self):
        """Clean up after each test."""
        clear_calibration_cache()
        for key in ['ENABLE_CONFIDENCE_CALIBRATION', 'CONFIDENCE_CALIBRATION_PATH']:
            if key in os.environ:
                del os.environ[key]
    
    def test_calibration_model_cached(self):
        """Test that calibration model is cached after first load."""
        fixture_path = Path(__file__).parent / "fixtures" / "calibration_merchant_test.json"
        
        if not fixture_path.exists():
            pytest.skip(f"Test fixture not found: {fixture_path}")
        
        os.environ["ENABLE_CONFIDENCE_CALIBRATION"] = "1"
        os.environ["CONFIDENCE_CALIBRATION_PATH"] = str(fixture_path)
        clear_calibration_cache()
        
        lines = ["INVOICE", "Test Merchant Corp", "Total: $100"]
        
        # First extraction - loads model
        result1 = _guess_merchant_entity(lines)
        assert result1.evidence["confidence_calibration"]["applied"] == True
        
        # Check cache
        info = get_calibration_info()
        assert info["cached_models"] == 1
        assert "merchant" in info["models"]
        
        # Second extraction - uses cache
        result2 = _guess_merchant_entity(lines)
        assert result2.evidence["confidence_calibration"]["applied"] == True
        
        # Verify same results (deterministic)
        assert result2.confidence == result1.confidence
        assert result2.confidence_bucket == result1.confidence_bucket


class TestRuntimeNoDependencies:
    """Test that runtime has no heavyweight dependencies."""
    
    def test_no_sklearn_import_in_runtime(self):
        """Test that runtime module doesn't import sklearn."""
        import app.pipelines.confidence_calibration as cal_module
        
        # Check module imports
        import sys
        sklearn_imported = any('sklearn' in name for name in sys.modules.keys())
        
        # If sklearn is imported, it should be from offline training, not runtime
        # The runtime module itself should not import sklearn
        module_source = Path(cal_module.__file__).read_text()
        
        assert 'import sklearn' not in module_source
        assert 'from sklearn' not in module_source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
