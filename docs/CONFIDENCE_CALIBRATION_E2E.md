# Confidence Calibration: Offline Training to Runtime Deployment

## Overview

This document describes the complete end-to-end workflow for merchant confidence calibration, from offline training to runtime deployment.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    OFFLINE TRAINING PIPELINE                     │
│                  (calibration/merchant/)                         │
│                                                                   │
│  Input: Labeled Data (CSV)                                       │
│    ↓                                                              │
│  calibrate.py → Train Isotonic/Logistic Model                    │
│    ↓                                                              │
│  Export Runtime-Compatible Artifact                              │
│    ↓                                                              │
│  Output: calibration_merchant_v1.json (breakpoints)              │
│          model_merchant_v1.pkl (offline debugging)               │
│          metrics_merchant_v1.json                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      RUNTIME DEPLOYMENT                          │
│              (app/pipelines/confidence_calibration.py)           │
│                                                                   │
│  Load JSON Artifact (cached)                                     │
│    ↓                                                              │
│  Apply Piecewise Linear Interpolation                            │
│    ↓                                                              │
│  Calibrated Confidence → Recompute Bucket                        │
│    ↓                                                              │
│  Record Audit Trail in Evidence                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Artifact Format (Runtime-Compatible)

### Schema

```json
{
  "schema_version": 1,
  "entity": "merchant",
  "calibrator_type": "piecewise_linear",
  "version": "merchant_conf_v1_20260125",
  "created_at": "2026-01-25T16:07:50Z",
  "feature_requirements": ["raw_confidence"],
  "notes": "Trained on 800 samples using isotonic method",
  "source_metrics": {
    "ece": 0.1512,
    "brier": 0.1512,
    "accuracy": 0.8050,
    "n": 800
  },
  "breakpoints": [
    {"x": 0.0, "y": 0.05},
    {"x": 0.1, "y": 0.15},
    ...
    {"x": 1.0, "y": 0.97}
  ],
  "training_metadata": {
    "features_used": [...],
    "bucket_thresholds": {...},
    "metrics": {...}
  }
}
```

### Key Fields

- **`schema_version`**: Artifact schema version (currently 1)
- **`entity`**: Entity type (e.g., "merchant", "total")
- **`calibrator_type`**: Always "piecewise_linear" for runtime
- **`version`**: Unique version identifier
- **`breakpoints`**: Array of (x, y) points for piecewise linear interpolation
  - Sorted by x value (ascending)
  - Runtime interpolates between points
  - Clamped to [0, 1] range
- **`feature_requirements`**: Features needed by runtime (v1: only "raw_confidence")
- **`training_metadata`**: Offline training details (not used by runtime)

## Offline Training Pipeline

### 1. Generate Calibration Artifact

```bash
cd calibration/merchant

# Train on labeled data
python calibrate.py \
  --data labeled_data.csv \
  --output calibration_output \
  --method isotonic

# Output:
# - calibration_output/calibration_merchant_v1.json (runtime artifact)
# - calibration_output/model_merchant_v1.pkl (offline debugging)
# - calibration_output/metrics_merchant_v1.json
```

### 2. Artifact Export Process

The offline pipeline converts the trained isotonic regression model into runtime-compatible breakpoints:

```python
def export_isotonic_breakpoints(model, n_points=50):
    """Export isotonic model as breakpoints for runtime."""
    # Get trained monotonic mapping
    X_thresholds = model.X_thresholds_
    y_thresholds = model.y_thresholds_
    
    # Downsample to n_points for efficiency
    if len(X_thresholds) > n_points:
        indices = np.linspace(0, len(X_thresholds) - 1, n_points, dtype=int)
        X_sampled = X_thresholds[indices]
        y_sampled = y_thresholds[indices]
    
    # Convert to breakpoint format
    breakpoints = [
        {"x": float(x), "y": float(y)}
        for x, y in zip(X_sampled, y_sampled)
    ]
    
    return breakpoints
```

### 3. Validation

```bash
# Evaluate calibration quality
python evaluate.py \
  --calibration calibration_output/calibration_merchant_v1.json \
  --output calibration_output

# Generate plots
python plots.py --output calibration_output
```

## Runtime Deployment

### 1. Environment Configuration

```bash
# Enable calibration
export ENABLE_CONFIDENCE_CALIBRATION=1
export CONFIDENCE_CALIBRATION_PATH=/path/to/calibration_merchant_v1.json

# Optional: Restrict to specific entity
export CONFIDENCE_CALIBRATION_ENTITY=merchant
```

### 2. Runtime Module (`app/pipelines/confidence_calibration.py`)

**Key Features:**
- ✅ **No sklearn dependency** - Pure Python with json + math
- ✅ **Cached loading** - Artifact loaded once per process
- ✅ **Fail-safe** - Falls back to raw confidence on any error
- ✅ **Gated** - Disabled by default, enabled via env flags

**Core Functions:**

```python
def calibrate_confidence(entity, raw_conf, features, evidence):
    """Apply confidence calibration with gating and fail-safe."""
    # Check if enabled
    if os.getenv("ENABLE_CONFIDENCE_CALIBRATION", "0") != "1":
        return raw_conf, {"applied": False}
    
    try:
        # Load cached model
        model = _load_calibration_model(path, entity)
        
        # Apply piecewise linear interpolation
        calibrated_conf = model.apply(raw_conf, features)
        
        return calibrated_conf, {
            "applied": True,
            "version": model.version,
            "path": path,
            "calibrator_type": model.calibrator_type,
            "delta": calibrated_conf - raw_conf
        }
    except Exception as e:
        # Fail-safe: return raw confidence
        return raw_conf, {"applied": False, "error": str(e)}
```

### 3. Integration with Merchant Extraction

In `_guess_merchant_entity()`:

```python
# 1. Compute raw heuristic confidence
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

# 4. Use calibrated confidence
confidence = calibrated_confidence
confidence_bucket = bucket_confidence(confidence)

# 5. Record audit trail
evidence["confidence_raw"] = raw_confidence
evidence["confidence_calibrated"] = calibrated_confidence
evidence["confidence_calibration"] = calibration_meta
```

### 4. Audit Trail

Every extraction records complete calibration metadata:

```python
result.evidence = {
    "confidence_raw": 0.429,
    "confidence_calibrated": 0.609,
    "confidence_calibration": {
        "applied": True,
        "version": "merchant_conf_v1_20260125",
        "path": "/path/to/calibration_merchant_v1.json",
        "calibrator_type": "piecewise_linear",
        "raw_confidence": 0.429,
        "calibrated_confidence": 0.609,
        "delta": 0.180
    }
}
```

## Testing

### Unit Tests (`tests/test_confidence_calibration.py`)

- ✅ Piecewise linear interpolation correctness
- ✅ Input/output clamping behavior
- ✅ Gating logic (enabled/disabled, missing path, entity filter)
- ✅ Integration with merchant extraction
- ✅ Bucket changes due to calibration
- ✅ Metadata recording in evidence

### End-to-End Smoke Tests (`tests/test_confidence_calibration_e2e.py`)

- ✅ Disabled flag → no change, no crash
- ✅ Valid artifact → deterministic calibration
- ✅ Invalid artifact → fallback to raw confidence
- ✅ Bucket changes after calibration
- ✅ Evidence contains all audit fields
- ✅ Model caching works correctly
- ✅ Runtime has no sklearn dependencies

### Test Fixtures

- `tests/fixtures/calibration_merchant_test.json` - Simple test artifact with known breakpoints

### Running Tests

```bash
# Unit tests
pytest tests/test_confidence_calibration.py -v

# End-to-end smoke tests
pytest tests/test_confidence_calibration_e2e.py -v

# All calibration tests
pytest tests/test_confidence_calibration*.py -v
```

## Deployment Workflow

### 1. Train Offline Calibration

```bash
cd calibration/merchant
python calibrate.py --data labeled_data.csv --output production_v1
```

### 2. Validate Artifact

```bash
# Check artifact format
python -c "
import json
artifact = json.load(open('production_v1/calibration_merchant_v1.json'))
print('Version:', artifact['version'])
print('Breakpoints:', len(artifact['breakpoints']))
print('Entity:', artifact['entity'])
"

# Run evaluation
python evaluate.py --calibration production_v1/calibration_merchant_v1.json
```

### 3. Deploy to Staging

```bash
# Copy artifact to deployment location
cp production_v1/calibration_merchant_v1.json /deploy/staging/

# Enable in staging environment
export ENABLE_CONFIDENCE_CALIBRATION=1
export CONFIDENCE_CALIBRATION_PATH=/deploy/staging/calibration_merchant_v1.json

# Restart application
systemctl restart verireceipt-staging
```

### 4. Monitor and Validate

```bash
# Check calibration is active
curl http://staging/api/health/calibration

# Sample extractions and verify evidence
curl -X POST http://staging/api/extract \
  -d '{"lines": ["INVOICE", "Test Corp", "Total: $100"]}' \
  | jq '.merchant.evidence.confidence_calibration'
```

### 5. Deploy to Production

```bash
# Copy artifact
cp production_v1/calibration_merchant_v1.json /deploy/production/

# Enable in production
export ENABLE_CONFIDENCE_CALIBRATION=1
export CONFIDENCE_CALIBRATION_PATH=/deploy/production/calibration_merchant_v1.json

# Rolling restart
kubectl rollout restart deployment/verireceipt-production
```

## Rollback Procedure

### Quick Disable

```bash
# Disable calibration (fallback to raw confidence)
export ENABLE_CONFIDENCE_CALIBRATION=0

# Restart application
systemctl restart verireceipt
```

### Revert to Previous Version

```bash
# Use previous artifact
export CONFIDENCE_CALIBRATION_PATH=/deploy/production/calibration_merchant_v1_previous.json

# Restart application
systemctl restart verireceipt
```

## Monitoring

### Key Metrics to Track

1. **Calibration Application Rate**
   - % of extractions with `confidence_calibration.applied = True`
   - Should be 100% when enabled

2. **Confidence Distribution**
   - Compare raw vs calibrated confidence distributions
   - Monitor bucket distribution changes

3. **Error Rate**
   - Track `confidence_calibration.error` occurrences
   - Alert on unexpected errors

4. **Performance Impact**
   - Calibration adds minimal overhead (~1ms per extraction)
   - Monitor p95/p99 latency

### Sample Monitoring Query

```sql
SELECT
  COUNT(*) as total_extractions,
  SUM(CASE WHEN confidence_calibration.applied THEN 1 ELSE 0 END) as calibrated,
  AVG(confidence_raw) as avg_raw_confidence,
  AVG(confidence_calibrated) as avg_calibrated_confidence,
  AVG(confidence_calibrated - confidence_raw) as avg_delta
FROM merchant_extractions
WHERE timestamp > NOW() - INTERVAL '1 hour'
```

## Troubleshooting

### Calibration Not Applied

**Symptoms:** `confidence_calibration.applied = False`

**Possible Causes:**
1. `ENABLE_CONFIDENCE_CALIBRATION` not set to "1"
2. `CONFIDENCE_CALIBRATION_PATH` not set or invalid
3. Artifact file not found
4. Artifact format invalid
5. Entity filter mismatch

**Solution:** Check environment variables and artifact path

### Confidence Values Unchanged

**Symptoms:** `confidence_raw == confidence_calibrated`

**Possible Causes:**
1. Calibration is identity mapping (breakpoints are y=x)
2. Raw confidence outside breakpoint range (clamped)

**Solution:** Review artifact breakpoints and training data

### Performance Degradation

**Symptoms:** Increased extraction latency

**Possible Causes:**
1. Artifact not cached (loading on every request)
2. Too many breakpoints (>100)

**Solution:** Verify caching is working, reduce breakpoint count

## Best Practices

### Artifact Management

1. **Version Control**
   - Store artifacts in version control
   - Tag with semantic versioning (v1.0.0, v1.1.0)

2. **Naming Convention**
   - `calibration_{entity}_{version}_{date}.json`
   - Example: `calibration_merchant_v1_20260125.json`

3. **Backup**
   - Keep previous versions for rollback
   - Store in artifact repository (S3, GCS)

### Training Data

1. **Sample Size**
   - Minimum 500 labeled samples
   - Target 1000+ for production

2. **Data Quality**
   - Balanced across confidence buckets
   - Representative of production distribution

3. **Refresh Cadence**
   - Retrain monthly or when accuracy drops
   - Monitor for data drift

### Deployment

1. **Gradual Rollout**
   - Deploy to staging first
   - Canary deployment in production (10% → 50% → 100%)

2. **A/B Testing**
   - Compare calibrated vs raw confidence
   - Measure impact on downstream metrics

3. **Monitoring**
   - Alert on calibration errors
   - Track confidence distribution shifts

## References

- **Runtime Module**: `app/pipelines/confidence_calibration.py`
- **Offline Pipeline**: `calibration/merchant/`
- **Unit Tests**: `tests/test_confidence_calibration.py`
- **E2E Tests**: `tests/test_confidence_calibration_e2e.py`
- **Documentation**: `docs/merchant_confidence_calibration.md`
- **Labeling Workflow**: `docs/labeling_workflow.md`
