"""
Configuration for merchant confidence calibration pipeline.
"""

from typing import List, Dict, Any

# Calibration versioning
CALIBRATION_VERSION = "merchant_v1"
CALIBRATION_METHOD = "isotonic"  # Default method

# Feature configuration
FEATURES_USED = [
    "best_score",
    "winner_margin", 
    "candidate_count_filtered",
    "mode",
    "seller_zone",
    "buyer_zone_penalty",
    "label_next_line",
    "company_name",
    "uppercase_header",
    "title_like",
    "ref_like",
    "digit_heavy"
]

# Optional features (if available)
OPTIONAL_FEATURES = [
    "doc_subtype",
    "language", 
    "ocr_quality_bucket"
]

# Confidence bucket thresholds
BUCKET_THRESHOLDS = {
    "HIGH": 0.80,
    "MEDIUM": 0.55,
    "LOW": 0.25,
    "NONE": 0.00
}

# Model parameters
ISOTONIC_PARAMS = {
    "out_of_bounds": "clip",
    "increasing": True
}

LOGISTIC_PARAMS = {
    "penalty": "l2",
    "C": 1.0,
    "random_state": 42,
    "max_iter": 1000
}

# Evaluation settings
RANDOM_SEED = 42
TEST_SIZE = 0.2
STRATIFY_BY = "confidence_bucket"

# Plot settings
PLOT_DPI = 300
PLOT_STYLE = "seaborn-v0_8"
FIGURE_SIZE = (10, 6)

# Output paths
OUTPUT_DIR = "calibration_output"
CALIBRATION_FILE = "calibration_merchant_v1.json"
METRICS_FILE = "metrics_merchant_v1.json"
PLOTS_DIR = "plots"

# Data validation
REQUIRED_COLUMNS = [
    "doc_id",
    "entity", 
    "extracted_value",
    "is_correct",
    "best_score",
    "winner_margin",
    "candidate_count_filtered",
    "mode",
    "confidence_raw",
    "confidence_bucket",
    "seller_zone",
    "buyer_zone_penalty",
    "label_next_line",
    "company_name",
    "uppercase_header",
    "title_like",
    "ref_like",
    "digit_heavy"
]

BOOLEAN_COLUMNS = [
    "seller_zone",
    "buyer_zone_penalty", 
    "label_next_line",
    "company_name",
    "uppercase_header",
    "title_like",
    "ref_like",
    "digit_heavy"
]

def get_feature_list(include_optional: bool = False) -> List[str]:
    """Get the list of features to use for calibration."""
    features = FEATURES_USED.copy()
    if include_optional:
        features.extend(OPTIONAL_FEATURES)
    return features

def validate_config() -> None:
    """Validate configuration parameters."""
    # Check bucket thresholds are in descending order
    thresholds = sorted(BUCKET_THRESHOLDS.values(), reverse=True)
    if thresholds != list(BUCKET_THRESHOLDS.values()):
        raise ValueError("Bucket thresholds must be in descending order")
    
    # Check thresholds are between 0 and 1
    for name, threshold in BUCKET_THRESHOLDS.items():
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"Bucket threshold {name} must be between 0 and 1")
    
    # Check method is supported
    supported_methods = ["isotonic", "logistic"]
    if CALIBRATION_METHOD not in supported_methods:
        raise ValueError(f"Calibration method must be one of: {supported_methods}")

if __name__ == "__main__":
    validate_config()
    print("Configuration validated successfully")
    print(f"Calibration version: {CALIBRATION_VERSION}")
    print(f"Method: {CALIBRATION_METHOD}")
    print(f"Features: {len(get_feature_list())}")
