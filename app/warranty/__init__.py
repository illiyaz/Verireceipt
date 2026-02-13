"""
Warranty Claims Fraud Detection Module

A separate vertical for analyzing automobile warranty claims,
detecting fraud through:
- Duplicate image detection (perceptual hashing)
- Rule-based anomaly signals (math, ratios, dates)
- Historical benchmark comparison
- ML-based risk scoring (LightGBM)
"""

from .models import WarrantyClaim, ClaimAnalysisResult, ExtractedImage
from .pipeline import analyze_warranty_claim

__all__ = [
    "WarrantyClaim",
    "ClaimAnalysisResult", 
    "ExtractedImage",
    "analyze_warranty_claim",
]
