# Date Calibration Report - date_v1_20260125

## Executive Summary

The date calibration model achieved 67.5% accuracy with Expected Calibration Error (ECE) of 0.1515. Performance stable - can be deployed with standard monitoring.

## Dataset Statistics

- **Training Samples**: 200
- **Test Samples**: 40
- **Positive Rate**: 0.675
- **Calibration Method**: piecewise_linear
- **Trained At**: 2026-01-25T22:47:34.270431

## Performance Metrics

| Metric | Current | Previous | Delta |
|--------|---------|----------|-------|
| Accuracy | 0.6750 | None | N/A |
| Precision | 0.6842 | None | N/A |
| Recall | 0.9630 | None | N/A |
| ECE | 0.1515 | None | N/A |
| Brier Score | 0.2537 | None | N/A |

## Confidence Bucket Analysis

| Bucket | Count | Precision | Avg Raw Conf | Avg Calibrated Conf |
|--------|-------|-----------|--------------|-------------------|
| HIGH | 35 | 0.714 | 0.811 | 0.811 |
| MEDIUM | 3 | 0.333 | 0.750 | 0.750 |
| LOW | 2 | 0.500 | 0.208 | 0.208 |

## Calibration Quality Notes

- **Expected Calibration Error (ECE)**: 0.1515 ❌ Poor
- **Brier Score**: 0.2537 ⚠️ Needs Improvement
- **Reliability**: ❌ Poorly calibrated

## Regression Analysis

ℹ️ No previous version available for comparison

## Recommendation

🚫 **Needs More Data** - Calibration quality below threshold. Collect more training samples.

## High-Confidence Errors

Found 10 high-confidence errors (confidence > 0.8, incorrect).

Top examples:

- doc_0190: 1.000 confidence
- doc_0145: 0.806 confidence
- doc_0068: 0.806 confidence
- doc_0021: 0.806 confidence
- doc_0123: 0.806 confidence
- doc_0077: 0.806 confidence
- doc_0006: 0.806 confidence
- doc_0072: 0.806 confidence
- doc_0071: 0.806 confidence
- doc_0015: 0.806 confidence


---
*Report generated on 2026-01-25 22:47:34 UTC*
