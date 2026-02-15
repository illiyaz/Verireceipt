# Merchant Confidence Calibration

## Background / Problem

The merchant extraction system in `_guess_merchant_entity()` produces a confidence score that is not calibrated to actual probability of correctness. The current score-to-confidence mapping `(best_score - 2) / 14` is heuristic and doesn't reflect real-world accuracy.

### Current Failure Patterns

- **Title-like merchants**: Legitimate business names that look like document titles get penalized
- **Buyer-zone confusion**: True merchants incorrectly classified as buyer information
- **OCR squashing**: "EXPORTER/SHIPPER" → "exportershipper" affects label matching
- **Language variations**: Non-English merchant names have different scoring characteristics

## Current Algorithm Summary

### Candidate Generation Sources

1. **Top Scan**: First 50 (strict) or 80 (relaxed) non-empty lines
2. **Next-Line Preference**: Lines following labels like "seller", "from", "exporter"

### Hard Rejects vs Soft Penalties

**Hard Rejects (immediate discard):**
- Symbol-only lines (`$$$`, `---`)
- Digit-heavy lines (>55% digits in relaxed mode)
- Document titles (strict mode only)
- Structural labels (strict mode, exact match only)
- Failed plausibility check

**Soft Penalties (score adjustments):**
- Buyer zone: -6 points
- Address-like: -3 points  
- Reference patterns: -2 points
- Title-like (relaxed mode): -4 points

### Scoring Components and Typical Ranges

| Component | Range | Typical Impact |
|-----------|-------|----------------|
| Base score | 0 | Starting point |
| Seller zone | +8 | Strong positive signal |
| Company name | +6 | Business name detection |
| Early position | +1 to +2 | Positional boost |
| Uppercase header | +2.5 | Format indicator |
| Buyer zone | -6 | Strong negative signal |
| Address-like | -3 | Content penalty |
| Reference patterns | -2 | Document structure penalty |

**Typical score ranges:**
- Strong merchants: 12-18 points
- Ambiguous merchants: 6-12 points  
- Weak merchants: 2-6 points
- Rejected: 0 points

### Strict vs Relaxed Behavior

| Feature | Strict Mode | Relaxed Mode |
|---------|-------------|--------------|
| Scan depth | 50 lines | 80 lines |
| Title blacklist | Hard reject | -4 penalty |
| Structural labels | Hard reject | No rejection |
| Digit ratio threshold | 0.55 | 0.55 |

## Current Confidence Computation

### Formula
```python
confidence = max(0.0, min(1.0, (best_score - 2) / 14))
```

### Bucket Mapping
```python
def bucket_confidence(conf: float) -> str:
    if conf >= 0.80: return "HIGH"
    elif conf >= 0.55: return "MEDIUM"  
    elif conf > 0: return "LOW"
    else: return "NONE"
```

### Current Limitations

1. **Non-calibrated**: Score ≠ probability
2. **Fixed mapping**: Doesn't adapt to data distribution
3. **No subtype awareness**: Same thresholds for all document types
4. **No language consideration**: Multi-language documents have different characteristics

## Calibration Targets

### Confidence Semantics

| Confidence Level | Target Precision | Operational Meaning |
|------------------|------------------|---------------------|
| HIGH (≥0.80) | ≥90% | Merchant is very likely correct |
| MEDIUM (0.55-0.79) | ≥75% | Merchant is probably correct |
| LOW (0.01-0.54) | ≥60% | Merchant might be correct |
| NONE (0.00) | N/A | No merchant found |

### Bucket Targets

- **HIGH bucket**: 90%+ precision, minimal false positives
- **MEDIUM bucket**: 75%+ precision, acceptable for automation
- **LOW bucket**: 60%+ precision, requires human review
- **NONE bucket**: Only when truly no merchant exists

## Calibration Approach

### Dataset Collection

**Required fields per document:**
```json
{
  "doc_id": "unique_identifier",
  "true_merchant": "actual_business_name", 
  "extracted_merchant": "system_output",
  "correctness": true/false,
  "doc_subtype": "receipt/invoice/etc",
  "language": "en/zh/ar/etc",
  "ocr_quality": "high/medium/low"
}
```

**Target dataset size:**
- Minimum: 1,000 labeled documents
- Ideal: 5,000+ labeled documents
- Stratified by subtype and language

### Features for Calibration

From EntityResult V2 schema:
- `best_score`: Raw winner score
- `winner_margin`: Gap to second best
- `mode_trace`: strict/relaxed/llm path
- `feature_flags`: Binary indicators
  - `in_seller_zone`
  - `buyer_zone_penalty_applied` 
  - `label_next_line_hit`
  - `company_name_hit`
  - `ref_like_hit`
  - `title_like_hit`
- `candidate_count_filtered`: Number of valid candidates
- `doc_subtype`: Document classification
- `lang_script`: Language and script

**Derived features:**
- `score_per_candidate`: best_score / candidate_count_filtered
- `has_strong_winner`: winner_margin > 5.0
- `zone_conflict`: seller_zone and buyer_zone both present

### Calibration Methods

#### Option 1: Isotonic Regression
```python
from sklearn.isotonic import IsotonicRegression

# Features: [best_score, winner_margin, candidate_count, zone_flags]
# Target: correctness (0/1)
calibrator = IsotonicRegression(out_of_bounds='clip')
calibrated_confidence = calibrator.predict(raw_features)
```

#### Option 2: Platt Scaling (Logistic)
```python
from sklearn.linear_model import LogisticRegression

# Same features, sigmoid calibration
calibrator = LogisticRegression()
calibrated_confidence = calibrator.predict_proba(raw_features)[:, 1]
```

#### Option 3: Small Neural Network
```python
# For complex interactions between features
# Hidden layers: [16, 8, 1] with sigmoid output
```

### Per-Subtype Calibration (if needed)

```python
calibrators = {
    'restaurant_receipt': isotonic_model_restaurant,
    'retail_receipt': isotonic_model_retail,
    'invoice': isotonic_model_invoice,
    'logistics': isotonic_model_logistics
}
```

## Evaluation

### Metrics

1. **Reliability Diagram**: Confidence vs. accuracy buckets
2. **Expected Calibration Error (ECE)**: Weighted average of bucket errors
3. **Maximum Calibration Error (MCE)**: Worst bucket error
4. **Brier Score**: Proper scoring rule for probabilities
5. **Precision-Recall by Bucket**: Operational performance

### Success Criteria

- **ECE < 0.05**: Well-calibrated system
- **MCE < 0.10**: No severely mis-calibrated buckets
- **HIGH bucket precision ≥ 0.90**: Meets target
- **Overall AUC ≥ 0.85**: Discriminatory power maintained

### Failure Analysis Slices

Evaluate calibration on:
- **OCR quality**: High vs medium vs low
- **Languages**: English vs non-English
- **Document subtypes**: Receipts vs invoices vs logistics
- **Geographic regions**: Different merchant naming conventions

## Operationalization

### Calibration Storage

**Option A: Configuration Table**
```sql
CREATE TABLE calibration_config (
    version VARCHAR(10) PRIMARY KEY,
    method VARCHAR(20),
    parameters JSONB,
    created_at TIMESTAMP,
    is_active BOOLEAN
);
```

**Option B: Constants File**
```python
# calibration_v2.py
CALIBRATION_VERSION = 2
CALIBRATION_COEFFS = {
    'intercept': -2.1,
    'best_score_coef': 0.08,
    'winner_margin_coef': 0.12,
    'zone_penalty_coef': -0.15
}
```

### Versioning and Rollout

```python
def apply_calibration(features: Dict[str, Any], version: int = 2) -> float:
    if version == 1:
        return legacy_confidence(features['best_score'])
    elif version == 2:
        return calibrated_confidence_v2(features)
    else:
        raise ValueError(f"Unknown calibration version: {version}")
```

### Safe Rollout Strategy

1. **Shadow Mode**: Run calibrated confidence alongside current system
2. **A/B Testing**: 10% traffic to new calibration, monitor metrics
3. **Gradual Rollout**: Increase traffic based on performance
4. **Full Rollout**: Complete migration after validation

### Monitoring

**Dashboard metrics:**
- Confidence distribution drift
- Bucket precision over time
- Calibration error (ECE) trends
- Failure rate by subtype/language

**Alerting thresholds:**
- ECE > 0.08 for 24 hours
- HIGH bucket precision < 0.85
- Sudden confidence distribution shifts

## Downstream Gating Rules

### Signal Emission

```python
# Emit low confidence signal
if merchant_result.confidence < 0.30:
    emit_signal("signal_merchant_confidence_low", {
        "confidence": merchant_result.confidence,
        "winner_margin": merchant_result.evidence.get("winner_margin"),
        "candidate_count": len(merchant_result.candidates)
    })
```

### LLM Tiebreak Activation

```python
# Current gating logic
should_use_llm = (
    enable_llm and
    os.getenv("ENABLE_LLM_MERCHANT_PICKER") == "1" and
    confidence < 0.30 and
    winner_margin < 2.0
)
```

### Invariant Handling

```python
# Receipt-like invariant with calibrated confidence
if is_receipt_like and merchant_candidate is None:
    # Try relaxed mode
    relaxed_result = _guess_merchant_entity(lines, strict=False)
    if relaxed_result.confidence < 0.20:  # Lower threshold for relaxed
        merchant_invariant_failed = True
```

## Examples

### HIGH Confidence Example

```json
{
  "value": "Global Trade Corporation",
  "confidence": 0.87,
  "confidence_bucket": "HIGH",
  "chosen_score": 16.0,
  "winner_margin": 8.5,
  "chosen_reasons": ["seller_zone", "company_name", "early_line"],
  "feature_flags": {
    "in_seller_zone": true,
    "company_name_hit": true,
    "buyer_zone_penalty_applied": false
  }
}
```

**Interpretation**: Strong seller zone signal + company name detection = high confidence

### MEDIUM Confidence Example

```json
{
  "value": "Local Store", 
  "confidence": 0.68,
  "confidence_bucket": "MEDIUM",
  "chosen_score": 10.5,
  "winner_margin": 3.2,
  "chosen_reasons": ["company_name", "early_line"],
  "feature_flags": {
    "in_seller_zone": false,
    "company_name_hit": true,
    "label_next_line_hit": false
  }
}
```

**Interpretation**: Company name detected but no strong positional signals

### LOW Confidence Example

```json
{
  "value": "Business Name",
  "confidence": 0.42,
  "confidence_bucket": "LOW", 
  "chosen_score": 7.8,
  "winner_margin": 1.1,
  "chosen_reasons": ["early_line", "ref_like"],
  "feature_flags": {
    "in_seller_zone": false,
    "company_name_hit": false,
    "ref_like_hit": true
  }
}
```

**Interpretation**: Weak signals with reference pattern penalty, close competition

## Runtime Hook

### Overview

The confidence calibration system provides a safe, gated runtime hook that applies pre-trained calibration to merchant extraction confidence scores. The system is designed to fail gracefully, falling back to raw heuristic confidence on any error.

### Environment Flags

**Required:**
- `ENABLE_CONFIDENCE_CALIBRATION=1` - Enable calibration (default: disabled)
- `CONFIDENCE_CALIBRATION_PATH=/path/to/artifact.json` - Path to calibration artifact

**Optional:**
- `CONFIDENCE_CALIBRATION_ENTITY=merchant` - Restrict calibration to specific entity type

### Calibration Artifact Format

Calibration artifacts are JSON files with the following schema:

```json
{
  "schema_version": 1,
  "entity": "merchant",
  "calibrator_type": "piecewise_linear",
  "version": "merchant_conf_v1_YYYYMMDD",
  "breakpoints": [
    {"x": 0.0, "y": 0.05},
    {"x": 0.5, "y": 0.68},
    {"x": 1.0, "y": 0.96}
  ],
  "feature_requirements": ["raw_confidence"],
  "created_at": "2026-01-25T10:00:00Z",
  "notes": "Description of calibration approach"
}
```

**Field Descriptions:**
- `schema_version`: Artifact schema version (currently 1)
- `entity`: Entity type (e.g., "merchant", "total")
- `calibrator_type`: Calibration method (currently "piecewise_linear")
- `version`: Unique version identifier
- `breakpoints`: List of (x, y) points for piecewise linear interpolation
- `feature_requirements`: Required features for calibration (v1: only "raw_confidence")
- `created_at`: ISO timestamp of artifact creation
- `notes`: Human-readable description

### Piecewise Linear Interpolation

The calibration applies piecewise linear interpolation:

1. **Input Clamping**: Raw confidence is clamped to [0, 1]
2. **Interpolation**: Linear interpolation between surrounding breakpoints
3. **Output Clamping**: Calibrated confidence is clamped to [0, 1]

**Example:**
```python
# Breakpoints: [(0.0, 0.05), (0.5, 0.68), (1.0, 0.96)]
# Raw confidence: 0.75
# Interpolate between (0.5, 0.68) and (1.0, 0.96)
# Result: 0.68 + (0.75 - 0.5) / (1.0 - 0.5) * (0.96 - 0.68) = 0.82
```

### Integration with Merchant Extraction

Calibration is automatically applied in `_guess_merchant_entity()` after computing raw heuristic confidence:

```python
# 1. Compute raw confidence from score
raw_confidence = max(0.0, min(1.0, (best_score - 2) / 14))

# 2. Build features for calibration
calibration_features = {
    "raw_confidence": raw_confidence,
    "winner_margin": evidence.get("winner_margin"),
    "topk_gap": evidence.get("topk_gap", 0.0),
    "mode": "relaxed" if evidence.get("fallback_mode") == "relaxed" else "strict",
    "candidate_count_filtered": evidence.get("filtered_candidates"),
}

# 3. Apply calibration (gated, safe fallback)
calibrated_confidence, calibration_meta = calibrate_confidence(
    entity="merchant",
    raw_conf=raw_confidence,
    features=calibration_features,
    evidence=evidence
)

# 4. Use calibrated confidence and recompute bucket
confidence = calibrated_confidence
confidence_bucket = bucket_confidence(confidence)
```

### Audit Trail

Calibration metadata is recorded in `EntityResult.evidence`:

```python
evidence["confidence_raw"] = raw_confidence
evidence["confidence_calibrated"] = calibrated_confidence
evidence["confidence_calibration"] = {
    "applied": True,
    "version": "merchant_conf_v1_20260125",
    "path": "/path/to/artifact.json",
    "calibrator_type": "piecewise_linear",
    "raw_confidence": 0.75,
    "calibrated_confidence": 0.82,
    "delta": 0.07
}
```

### Failure Modes and Fallbacks

The system is designed to fail gracefully:

| Failure Mode | Behavior | Metadata |
|--------------|----------|----------|
| Calibration disabled | Use raw confidence | `{"applied": False}` |
| Missing path | Use raw confidence | `{"applied": False, "error": "missing_CONFIDENCE_CALIBRATION_PATH"}` |
| File not found | Use raw confidence | `{"applied": False, "error": "calibration_file_not_found"}` |
| Invalid artifact | Use raw confidence | `{"applied": False, "error": "<exception message>"}` |
| Entity mismatch | Use raw confidence | `{"applied": False, "error": "entity_filter_mismatch"}` |
| Missing features | Use raw confidence | `{"applied": False, "error": "Missing required feature"}` |

### Sample Artifact

A sample calibration artifact is provided at:
```
docs/calibration/merchant_confidence_v1.sample.json
```

This artifact provides a slightly conservative mapping that reduces overconfidence in the 0.4-0.7 range.

### Usage Example

**Enable calibration:**
```bash
export ENABLE_CONFIDENCE_CALIBRATION=1
export CONFIDENCE_CALIBRATION_PATH=docs/calibration/merchant_confidence_v1.sample.json
```

**Verify calibration is active:**
```python
from app.pipelines.confidence_calibration import get_calibration_info

info = get_calibration_info()
print(f"Calibration enabled: {info['enabled']}")
print(f"Loaded models: {info['cached_models']}")
```

**Extract with calibration:**
```python
from app.pipelines.features import _guess_merchant_entity

result = _guess_merchant_entity(lines)

print(f"Raw confidence: {result.evidence['confidence_raw']:.3f}")
print(f"Calibrated confidence: {result.evidence['confidence_calibrated']:.3f}")
print(f"Bucket: {result.confidence_bucket}")
print(f"Calibration applied: {result.evidence['confidence_calibration']['applied']}")
```

### Caching

Calibration models are cached in memory after first load to avoid repeated file I/O:
- Cache key: `"{entity}:{path}"`
- Cache lifetime: Process lifetime
- Cache clearing: `clear_calibration_cache()` (useful for testing)

### Testing

Comprehensive unit tests are provided in `tests/test_confidence_calibration.py`:
- Piecewise linear interpolation correctness
- Input/output clamping behavior
- Gating logic (enabled/disabled, missing path, entity filter)
- Integration with merchant extraction
- Bucket changes due to calibration
- Metadata recording in evidence

## Next Steps

1. **Dataset Creation**: Start collecting labeled merchant extractions
2. **Feature Engineering**: Implement V2 schema extraction in production
3. **Baseline Evaluation**: Measure current calibration performance
4. **Model Development**: Train and validate calibration models
5. **Production Integration**: Deploy calibrated confidence with monitoring
6. **Monitoring Setup**: Create dashboards and alerting
7. **Continuous Improvement**: Regular recalibration with new data

## References

- **EntityResult V2 Schema**: `app/pipelines/features.py` - ML labeling payload structure
- **Calibration Module**: `app/pipelines/confidence_calibration.py` - Runtime hook implementation
- **Environment Flags**: `ENABLE_CONFIDENCE_CALIBRATION`, `CONFIDENCE_CALIBRATION_PATH`, `CONFIDENCE_CALIBRATION_ENTITY`
- **Sample Artifact**: `docs/calibration/merchant_confidence_v1.sample.json`
- **Tests**: `tests/test_confidence_calibration.py`
- **Related Systems**: Total extraction, date extraction (similar calibration approach)
