"""
Runtime confidence calibration module.

Provides safe, gated calibration of entity extraction confidence scores
using pre-trained calibration artifacts. Falls back to raw confidence on any error.
"""

import json
import os
import logging
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class CalibrationModel:
    """Calibration model for entity confidence scores."""
    entity: str
    version: str
    calibrator_type: str
    breakpoints: list  # List of {"x": float, "y": float}
    feature_requirements: list
    created_at: str
    notes: str = ""
    
    @classmethod
    def load_from_path(cls, path: str) -> 'CalibrationModel':
        """Load calibration model from JSON artifact."""
        with open(path, 'r') as f:
            artifact = json.load(f)
        
        # Validate schema
        required_fields = ['entity', 'version', 'calibrator_type', 'breakpoints', 'feature_requirements']
        missing = [f for f in required_fields if f not in artifact]
        if missing:
            raise ValueError(f"Missing required fields in calibration artifact: {missing}")
        
        # Validate breakpoints
        breakpoints = artifact['breakpoints']
        if not isinstance(breakpoints, list) or len(breakpoints) < 2:
            raise ValueError("Breakpoints must be a list with at least 2 points")
        
        for bp in breakpoints:
            if not isinstance(bp, dict) or 'x' not in bp or 'y' not in bp:
                raise ValueError(f"Invalid breakpoint format: {bp}")
        
        # Sort breakpoints by x value
        breakpoints = sorted(breakpoints, key=lambda p: p['x'])
        
        return cls(
            entity=artifact['entity'],
            version=artifact['version'],
            calibrator_type=artifact['calibrator_type'],
            breakpoints=breakpoints,
            feature_requirements=artifact['feature_requirements'],
            created_at=artifact.get('created_at', 'unknown'),
            notes=artifact.get('notes', '')
        )
    
    def apply(self, raw_conf: float, features: Dict[str, Any]) -> float:
        """Apply calibration to raw confidence score."""
        # Validate feature requirements
        for req_feature in self.feature_requirements:
            if req_feature not in features:
                raise ValueError(f"Missing required feature: {req_feature}")
        
        # Apply calibration based on type
        if self.calibrator_type == "piecewise_linear":
            return self._apply_piecewise_linear(raw_conf)
        else:
            raise ValueError(f"Unsupported calibrator type: {self.calibrator_type}")
    
    def _apply_piecewise_linear(self, raw_conf: float) -> float:
        """Apply piecewise linear interpolation."""
        # Clamp input to [0, 1]
        x = max(0.0, min(1.0, raw_conf))
        
        # Find surrounding breakpoints
        breakpoints = self.breakpoints
        
        # Handle edge cases
        if x <= breakpoints[0]['x']:
            return max(0.0, min(1.0, breakpoints[0]['y']))
        if x >= breakpoints[-1]['x']:
            return max(0.0, min(1.0, breakpoints[-1]['y']))
        
        # Find the two breakpoints to interpolate between
        for i in range(len(breakpoints) - 1):
            x1, y1 = breakpoints[i]['x'], breakpoints[i]['y']
            x2, y2 = breakpoints[i + 1]['x'], breakpoints[i + 1]['y']
            
            if x1 <= x <= x2:
                # Linear interpolation
                if x2 == x1:
                    y = y1
                else:
                    t = (x - x1) / (x2 - x1)
                    y = y1 + t * (y2 - y1)
                
                # Clamp output to [0, 1]
                return max(0.0, min(1.0, y))
        
        # Should never reach here
        return raw_conf


# Module-level singleton cache
_calibration_cache: Dict[str, CalibrationModel] = {}

def _load_calibration_model(path: str, entity: str) -> Optional[CalibrationModel]:
    """Load calibration model with caching."""
    cache_key = f"{entity}:{path}"
    
    if cache_key in _calibration_cache:
        return _calibration_cache[cache_key]
    
    try:
        model = CalibrationModel.load_from_path(path)
        
        # Validate entity matches
        if model.entity != entity:
            logger.warning(f"Calibration artifact entity mismatch: expected {entity}, got {model.entity}")
            return None
        
        # Cache the model
        _calibration_cache[cache_key] = model
        logger.info(f"Loaded calibration model: {model.version} for entity {entity}")
        
        return model
        
    except Exception as e:
        logger.warning(f"Failed to load calibration model from {path}: {e}")
        return None


def calibrate_confidence(
    entity: str,
    raw_conf: float,
    features: Dict[str, Any],
    evidence: Dict[str, Any]
) -> Tuple[float, Dict[str, Any]]:
    """
    Apply confidence calibration to entity extraction result.
    
    Args:
        entity: Entity type (e.g., "merchant", "total")
        raw_conf: Raw heuristic confidence [0..1]
        features: Feature dict for calibration
        evidence: Evidence dict (for audit trail)
    
    Returns:
        (calibrated_confidence, metadata)
        
    Gating rules:
        - Only apply if ENABLE_CONFIDENCE_CALIBRATION=1
        - Path from CONFIDENCE_CALIBRATION_PATH (required if enabled)
        - Optionally restrict by CONFIDENCE_CALIBRATION_ENTITY
    """
    # Default metadata
    meta = {
        "applied": False,
        "version": None,
        "path": None,
        "error": None
    }
    
    # Check if calibration is enabled
    if os.getenv("ENABLE_CONFIDENCE_CALIBRATION", "0") != "1":
        return raw_conf, meta
    
    # Check entity restriction
    entity_filter = os.getenv("CONFIDENCE_CALIBRATION_ENTITY")
    if entity_filter and entity_filter != entity:
        meta["error"] = f"entity_filter_mismatch: {entity_filter} != {entity}"
        return raw_conf, meta
    
    # Get calibration path
    calibration_path = os.getenv("CONFIDENCE_CALIBRATION_PATH")
    if not calibration_path:
        meta["error"] = "missing_CONFIDENCE_CALIBRATION_PATH"
        return raw_conf, meta
    
    # Validate path exists
    if not Path(calibration_path).exists():
        meta["error"] = f"calibration_file_not_found: {calibration_path}"
        return raw_conf, meta
    
    try:
        # Load calibration model (with caching)
        model = _load_calibration_model(calibration_path, entity)
        
        if model is None:
            meta["error"] = "failed_to_load_model"
            return raw_conf, meta
        
        # Apply calibration
        calibrated_conf = model.apply(raw_conf, features)
        
        # Update metadata
        meta["applied"] = True
        meta["version"] = model.version
        meta["path"] = calibration_path
        meta["calibrator_type"] = model.calibrator_type
        meta["raw_confidence"] = raw_conf
        meta["calibrated_confidence"] = calibrated_conf
        meta["delta"] = calibrated_conf - raw_conf
        
        logger.debug(f"Calibration applied: {raw_conf:.3f} → {calibrated_conf:.3f} (Δ={meta['delta']:.3f})")
        
        return calibrated_conf, meta
        
    except Exception as e:
        # On any error, return raw confidence
        meta["error"] = str(e)
        logger.warning(f"Calibration failed for {entity}, using raw confidence: {e}")
        return raw_conf, meta


def get_calibration_info() -> Dict[str, Any]:
    """Get information about loaded calibration models."""
    info = {
        "enabled": os.getenv("ENABLE_CONFIDENCE_CALIBRATION", "0") == "1",
        "path": os.getenv("CONFIDENCE_CALIBRATION_PATH"),
        "entity_filter": os.getenv("CONFIDENCE_CALIBRATION_ENTITY"),
        "cached_models": len(_calibration_cache),
        "models": {}
    }
    
    for cache_key, model in _calibration_cache.items():
        entity, path = cache_key.split(":", 1)
        info["models"][entity] = {
            "version": model.version,
            "type": model.calibrator_type,
            "path": path,
            "breakpoints_count": len(model.breakpoints)
        }
    
    return info


def clear_calibration_cache():
    """Clear the calibration model cache (useful for testing)."""
    global _calibration_cache
    _calibration_cache.clear()
    logger.info("Calibration cache cleared")
