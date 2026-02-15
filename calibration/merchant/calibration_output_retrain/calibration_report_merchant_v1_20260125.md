# Merchant Calibration Report - merchant_v1_20260125

## Executive Summary

The merchant calibration model achieved 80.5% accuracy with Expected Calibration Error (ECE) of 0.0175. Performance stable - can be deployed with standard monitoring.

## Dataset Statistics

- **Training Samples**: 1000
- **Test Samples**: 200
- **Positive Rate**: 0.805
- **Calibration Method**: piecewise_linear
- **Trained At**: 2026-01-25T22:26:12.291245

## Performance Metrics

| Metric | Current | Previous | Delta |
|--------|---------|----------|-------|
| Accuracy | 0.8050 | None | N/A |
| Precision | 0.8050 | None | N/A |
| Recall | 1.0000 | None | N/A |
| ECE | 0.0175 | None | N/A |
| Brier Score | 0.1573 | None | N/A |

## Confidence Bucket Analysis

| Bucket | Count | Precision | Avg Raw Conf | Avg Calibrated Conf |
|--------|-------|-----------|--------------|-------------------|
| MEDIUM | 200 | 0.805 | 0.787 | 0.787 |

## Calibration Quality Notes

- **Expected Calibration Error (ECE)**: 0.0175 ✅ Good
- **Brier Score**: 0.1573 ✅ Good
- **Reliability**: ✅ Well-calibrated

## Regression Analysis

ℹ️ No previous version available for comparison

## Recommendation

🚫 **Needs More Data** - Calibration quality below threshold. Collect more training samples.

## High-Confidence Errors

No high-confidence errors found.

---
*Report generated on 2026-01-25 22:26:12 UTC*
