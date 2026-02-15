# Merchant Confidence Calibration Pipeline

This directory contains the offline calibration pipeline for merchant extraction confidence scores. The pipeline learns a mapping from raw extraction features to calibrated probabilities that reflect real-world accuracy.

## Overview

The calibration system addresses the fact that heuristic confidence scores in `_guess_merchant_entity()` don't reflect actual probabilities. This pipeline:

1. **Learns** the relationship between extraction features and correctness
2. **Produces** calibrated confidence scores with meaningful semantics
3. **Enables** reliable downstream decision-making based on confidence thresholds

## File Structure

```
calibration/merchant/
├── README.md           # This file
├── config.py           # Configuration and constants
├── calibrate.py        # Main training script
├── evaluate.py         # Evaluation and metrics
├── plots.py           # Visualization utilities
└── calibration_output/  # Generated artifacts
    ├── calibration_merchant_v1.json
    ├── model_merchant_v1.pkl
    ├── metrics_merchant_v1.json
    ├── test_results.csv
    └── plots/
        ├── reliability_diagram.png
        ├── confidence_histogram.png
        ├── bucket_precision.png
        └── calibration_comparison.png
```

## Quick Start

### 1. Generate Labeled Dataset

First, create a labeled dataset using the EntityResult V2 schema:

```python
from app.pipelines.features import _guess_merchant_entity

# For each document:
result = _guess_merchant_entity(lines)
ml_dict = result.to_ml_dict(doc_id=doc_id)

# Extract features for calibration
features = {
    "doc_id": doc_id,
    "entity": "merchant",
    "extracted_value": result.value,
    "is_correct": 1 if result.value == true_merchant else 0,  # Human label
    "best_score": ml_dict["winner"]["score"] if ml_dict["winner"] else 0,
    "winner_margin": ml_dict["winner_margin"],
    "candidate_count_filtered": ml_dict["candidate_count_filtered"],
    "mode": ml_dict["mode_trace"][0]["mode"],
    "confidence_raw": result.confidence,
    "confidence_bucket": result.confidence_bucket,
    "seller_zone": ml_dict["feature_flags"]["in_seller_zone"],
    "buyer_zone_penalty": ml_dict["feature_flags"]["buyer_zone_penalty_applied"],
    "label_next_line": ml_dict["feature_flags"]["label_next_line_hit"],
    "company_name": ml_dict["feature_flags"]["company_name_hit"],
    "uppercase_header": ml_dict["feature_flags"]["uppercase_header_hit"],
    "title_like": ml_dict["feature_flags"]["title_like_hit"],
    "ref_like": ml_dict["feature_flags"]["ref_like_hit"],
    "digit_heavy": False,  # Add your own logic
    # Optional fields:
    "doc_subtype": "receipt",
    "language": "en",
    "ocr_quality_bucket": "high"
}
```

Save to CSV/Parquet with at least 1,000 labeled examples.

### 2. Train Calibration Model

```bash
cd calibration/merchant

python calibrate.py --data /path/to/labeled_data.csv --output calibration_output
```

Options:
- `--include-optional`: Include optional features (doc_subtype, language, etc.)
- `--test-size`: Test set proportion (default: 0.2)

### 3. Evaluate Results

```bash
python evaluate.py --calibration calibration_output/calibration_merchant_v1.json
```

This generates:
- Overall metrics (accuracy, precision, ECE, Brier score)
- Bucket-specific performance
- High-confidence error analysis
- Monotonicity checks

### 4. Generate Plots

```bash
python plots.py --output calibration_output
```

Generates visualization plots in `calibration_output/plots/`.

## Configuration

### Calibration Methods

**Isotonic Regression (Default)**
- Non-parametric, monotonic mapping
- Safer for score → probability calibration
- Uses weighted feature combination

**Logistic Regression (Optional)**
- Parametric approach with interpretable coefficients
- Uses multiple features with one-hot encoding
- More flexible but requires more data

### Confidence Buckets

```python
BUCKET_THRESHOLDS = {
    "HIGH": 0.80,    # Target: ≥90% precision
    "MEDIUM": 0.55,  # Target: ≥75% precision  
    "LOW": 0.25,     # Target: ≥60% precision
    "NONE": 0.00     # No merchant found
}
```

### Features Used

**Core Features:**
- `best_score`: Raw winner score
- `winner_margin`: Gap to second best
- `candidate_count_filtered`: Number of valid candidates
- `mode`: strict/relaxed/llm
- Boolean flags: seller_zone, buyer_zone_penalty, etc.

**Optional Features:**
- `doc_subtype`: Document classification
- `language`: Language code
- `ocr_quality_bucket`: OCR quality assessment

## Understanding Outputs

### Calibration Artifact (`calibration_merchant_v1.json`)

```json
{
  "calibration_version": "merchant_v1",
  "method": "isotonic",
  "trained_at": "2024-01-25T10:00:00",
  "features_used": ["best_score", "winner_margin", ...],
  "bucket_thresholds": {"HIGH": 0.80, "MEDIUM": 0.55, ...},
  "model_params": {...},
  "metrics": {
    "accuracy": 0.87,
    "precision": 0.89,
    "ece": 0.032,
    "brier_score": 0.12
  }
}
```

### Metrics Report (`metrics_merchant_v1.json`)

Contains detailed evaluation:
- Overall performance metrics
- Per-bucket precision and calibration error
- Monotonicity validation
- High-confidence error examples
- Reliability diagram bin statistics

### Plots

1. **Reliability Diagram**: Shows calibration quality (ECE)
2. **Confidence Histogram**: Distribution of calibrated scores
3. **Bucket Precision**: Precision per confidence bucket
4. **Calibration Comparison**: Raw vs calibrated confidence

## Interpreting Results

### Success Indicators

✅ **Good Calibration:**
- ECE < 0.05 (well-calibrated)
- No monotonicity violations in buckets
- HIGH bucket precision ≥ 0.90
- Reliability diagram close to diagonal

⚠️ **Issues to Address:**
- ECE > 0.08 (poor calibration)
- Monotonicity violations (precision increases as confidence decreases)
- HIGH bucket precision < 0.85 (overconfident)
- Large gap between confidence and accuracy in any bucket

### Common Failure Patterns

**Overconfidence:**
- HIGH bucket precision < 0.90
- Confidence histogram skewed high
- Reliability diagram above diagonal

**Underconfidence:**
- LOW bucket precision > 0.70
- Confidence histogram skewed low
- Reliability diagram below diagonal

**Non-monotonic Buckets:**
- MEDIUM precision > HIGH precision
- Indicates inconsistent feature signals

## Production Integration (Future)

To use calibration in production:

1. **Load Calibration Artifact:**
```python
with open('calibration_merchant_v1.json') as f:
    artifact = json.load(f)

with open('model_merchant_v1.pkl', 'rb') as f:
    model = pickle.load(f)
```

2. **Apply Calibration:**
```python
def apply_merchant_calibration(raw_features, model, artifact):
    if artifact['method'] == 'isotonic':
        # Apply isotonic regression
        calibrated_prob = model.predict(raw_features)
    elif artifact['method'] == 'logistic':
        # Apply logistic pipeline
        calibrated_prob = model.predict_proba(raw_features)[:, 1]
    
    return calibrated_prob
```

3. **Update Confidence Buckets:**
```python
def get_calibrated_bucket(confidence):
    if confidence >= 0.80: return "HIGH"
    elif confidence >= 0.55: return "MEDIUM"
    elif confidence > 0: return "LOW"
    else: return "NONE"
```

## Dataset Requirements

### Minimum Dataset Size

- **Development**: 1,000 labeled examples
- **Production**: 5,000+ labeled examples

### Quality Requirements

- **Stratified sampling** across confidence buckets
- **Representative coverage** of document subtypes
- **Balanced correctness** (mix of correct/incorrect extractions)
- **Consistent labeling** guidelines

### Labeling Guidelines

1. **Correct Extraction**: Extracted merchant matches true business name
2. **Incorrect Extraction**: Extracted merchant is wrong or None when merchant exists
3. **No Merchant**: True merchant doesn't exist (rare for receipts)

### Data Quality Checks

```python
# Validate dataset quality
def validate_dataset(df):
    # Check required columns
    required_cols = ['doc_id', 'is_correct', 'best_score', ...]
    assert all(col in df.columns for col in required_cols)
    
    # Check label distribution
    correct_rate = df['is_correct'].mean()
    assert 0.3 <= correct_rate <= 0.9, f"Suspicious correctness rate: {correct_rate}"
    
    # Check confidence distribution
    confidence_dist = df['confidence_raw'].describe()
    assert confidence_dist['mean'] > 0.1, "Too many low confidence predictions"
    
    print("✅ Dataset validation passed")
```

## Troubleshooting

### Common Issues

**Calibration Fails:**
- Check dataset size (need > 100 samples)
- Verify feature ranges and types
- Ensure labels are binary (0/1)

**Poor ECE:**
- Increase dataset size
- Add more diverse examples
- Check for data leakage

**Monotonicity Violations:**
- Review bucket definitions
- Check feature engineering
- Consider smoothing buckets

**Memory Issues:**
- Sample dataset for development
- Use efficient data types
- Process in chunks

### Debug Mode

Enable debug logging:

```bash
export ENTITY_EXTRACTION_DEBUG=1
python calibrate.py --data debug_data.csv --debug
```

## Versioning and Rollout

### Version Management

- **Calibration Version**: `merchant_v1`, `merchant_v2`, etc.
- **Artifact Storage**: Versioned JSON files
- **Model Backups**: Keep previous model pickles

### Safe Rollout Strategy

1. **Shadow Mode**: Run calibrated confidence alongside current system
2. **A/B Testing**: 10% traffic to new calibration
3. **Gradual Rollout**: Increase based on performance
4. **Full Rollout**: Complete migration after validation

### Monitoring

Set up alerts for:
- ECE > 0.08 for 24 hours
- HIGH bucket precision < 0.85
- Sudden confidence distribution shifts
- Increase in high-confidence errors

## Contributing

When adding new calibration methods or features:

1. Update `config.py` with new parameters
2. Add tests in `test_calibrate.py`
3. Update documentation
4. Validate with sample dataset

## References

- **EntityResult V2 Schema**: `app/pipelines/features.py`
- **Confidence Calibration Theory**: https://en.wikipedia.org/wiki/Calibration_(statistics)
- **Scikit-learn Calibration**: https://scikit-learn.org/stable/modules/calibration.html
