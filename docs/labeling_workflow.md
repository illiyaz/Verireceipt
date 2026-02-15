# Merchant Extraction Labeling Workflow

This document describes the human labeling workflow for merchant extraction outputs, enabling quality assurance, calibration improvement, and regression prevention.

## Overview

The labeling workflow consists of four main stages:

1. **Export**: Generate labeling dataset from merchant extraction results
2. **Label**: Human labeling via CLI interface
3. **Evaluate**: Compute metrics and analyze errors
4. **Golden Tests**: Maintain regression test suite

## Prerequisites

- Python 3.8+
- VeriReceipt project installed
- Receipt samples (JSON or TXT format with OCR lines)

## Stage 1: Export Dataset

### Command

```bash
python scripts/export_merchant_labeling_dataset.py \
  --input_dir /path/to/receipt/samples \
  --output_dir labeling_output \
  --limit 100 \
  --include_debug_context \
  --no_redact  # Optional: disable redaction for internal use
```

### Parameters

- `--input_dir`: Directory containing receipt samples
  - Supported formats: JSON (with `lines`/`ocr_lines`/`text` field) or TXT (one line per line)
- `--output_dir`: Output directory for labeling dataset
- `--limit`: Optional limit on number of files to process
- `--include_debug_context`: Include first 40 OCR lines and zone info (useful for debugging)
- `--no_redact`: Disable PII redaction (default: redaction enabled)

### Outputs

The export script generates three files:

#### 1. `doc_level.jsonl`
One JSON object per document with full EntityResult V2 payload:

```json
{
  "schema_version": 2,
  "entity": "merchant",
  "value": "Global Trade Corporation",
  "confidence": 0.75,
  "confidence_bucket": "MEDIUM",
  "doc_id": "receipt_001",
  "winner": {
    "value": "Global Trade Corporation",
    "line_idx": 2,
    "score": 12.5,
    "reasons": ["seller_zone", "company_name"],
    "source": "top_scan"
  },
  "winner_margin": 4.2,
  "top_k": [...],
  "source_file": "receipt_001.json"
}
```

#### 2. `candidate_level.csv`
Flattened candidate rows for analysis:

```csv
doc_id,entity,candidate_rank,is_winner,value,score,reasons,...
receipt_001,merchant,1,True,Global Trade Corporation,12.5,"['seller_zone', 'company_name']",...
receipt_001,merchant,2,False,Alternative Corp,8.3,"['company_name']",...
```

#### 3. `manifest.csv`
Summary of all documents:

```csv
doc_id,file_name,merchant_value,confidence_raw,confidence_calibrated,confidence_bucket,winner_margin,...
receipt_001,receipt_001.json,Global Trade Corporation,0.75,0.82,MEDIUM,4.2,...
```

### Redaction Policy

**Default behavior (redaction enabled):**
- Non-winner candidates: Redacted to first 2 tokens + "…"
  - Example: "Global Trade Corporation" → "Global Trade …"
- Winner: Not redacted (needed for labeling)
- Debug context: Phone numbers → `[PHONE]`, addresses → `[ADDRESS]`

**When to disable redaction:**
- Internal labeling with trusted labelers
- Need full context for ambiguous cases
- Development/testing

## Stage 2: Label Dataset

### Command

```bash
python scripts/label_merchant_dataset.py \
  --doc_level_jsonl labeling_output/doc_level.jsonl \
  --labels_csv labels.csv \
  --show_lines  # Optional: show OCR lines by default
```

### Parameters

- `--doc_level_jsonl`: Path to exported doc_level.jsonl
- `--labels_csv`: Output path for labels (default: labels.csv)
- `--show_lines`: Show OCR lines by default
- `--start_from`: Start from document index (useful for resuming)

### Interactive Labeling

For each document, the CLI displays:

```
================================================================================
Document ID: receipt_001
Source File: receipt_001.json
================================================================================

Confidence:
  Raw:        0.750
  Calibrated: 0.820
  Bucket:     MEDIUM
  Margin:     4.20

✓ WINNER: Global Trade Corporation
  Score:   12.50
  Source:  top_scan
  Reasons: seller_zone, company_name
  Zone:    seller

Top 5 Candidates:
  ✓ 1. Global Trade Corporation
      Score: 12.50 | Reasons: seller_zone, company_name
    2. Alternative Corp
      Score: 8.30 | Reasons: company_name

--------------------------------------------------------------------------------
Is the winner correct? (y/n/s=skip/q=quit/l=show lines):
```

### Labeling Commands

- `y` - Winner is correct
- `n` - Winner is incorrect
- `s` - Skip this document
- `l` - Show OCR lines (first 20)
- `q` - Quit and save

### If Winner is Incorrect

The CLI prompts for:

1. **Correct merchant name** (optional)
   ```
   Enter correct merchant name (or press Enter to skip): Actual Merchant Name
   ```

2. **Error type** (required)
   ```
   Error type options: ocr_error, layout_error, heuristic_error, ambiguous, non_receipt, other
   Select error type: heuristic_error
   ```

3. **Notes** (optional)
   ```
   Additional notes (optional): Merchant was in buyer zone but should have been detected
   ```

### Labels Output

Labels are saved to CSV with the following fields:

```csv
doc_id,winner_correct,correct_merchant_text,error_type,notes,confidence_raw,confidence_calibrated,confidence_bucket,winner_margin
receipt_001,yes,,,0.750,0.820,MEDIUM,4.20
receipt_002,no,Actual Merchant,heuristic_error,Merchant in buyer zone,0.450,0.609,MEDIUM,2.10
```

### Resume Labeling

The labeling script is idempotent by `doc_id`. To resume:

```bash
python scripts/label_merchant_dataset.py \
  --doc_level_jsonl labeling_output/doc_level.jsonl \
  --labels_csv labels.csv
```

Already-labeled documents are automatically skipped.

## Stage 3: Evaluate Labels

### Command

```bash
python scripts/eval_merchant_labels.py \
  --doc_level_jsonl labeling_output/doc_level.jsonl \
  --labels_csv labels.csv \
  --output_dir eval_output
```

### Parameters

- `--doc_level_jsonl`: Path to doc_level.jsonl
- `--labels_csv`: Path to labels CSV
- `--output_dir`: Output directory for reports (default: eval_output)

### Outputs

#### 1. Console Report

```
================================================================================
MERCHANT EXTRACTION EVALUATION REPORT
================================================================================

📊 Overall Performance:
   Total documents:  100
   Correct:          87
   Accuracy:         87.0%

📈 Bucket Precision:
   HIGH    : 95.0% (38/40 correct)
   MEDIUM  : 85.0% (34/40 correct)
   LOW     : 75.0% (15/20 correct)

🎯 Calibration Diagnostics:
   Avg confidence (correct):   0.782
   Avg confidence (incorrect): 0.543
   Confidence gap:             +0.239

📉 Margin Analysis:
   Errors with margin data: 13
   Avg winner margin (errors): 1.85

❌ Error Type Breakdown:
   heuristic_error     :   7 (53.8%)
   layout_error        :   3 (23.1%)
   ocr_error          :   2 (15.4%)
   ambiguous          :   1 (7.7%)
```

#### 2. `report.md`

Markdown-formatted report with tables:

```markdown
# Merchant Extraction Evaluation Report

## Overall Performance

- **Total documents**: 100
- **Correct**: 87
- **Accuracy**: 87.0%

## Bucket Precision

| Bucket | Precision | Correct | Total |
|--------|-----------|---------|-------|
| HIGH   | 95.0%     | 38      | 40    |
| MEDIUM | 85.0%     | 34      | 40    |
| LOW    | 75.0%     | 15      | 20    |
...
```

#### 3. `metrics.json`

Machine-readable metrics:

```json
{
  "overall": {
    "total": 100,
    "correct": 87,
    "accuracy": 0.87
  },
  "bucket_precision": {
    "HIGH": {"precision": 0.95, "count": 40, "correct": 38},
    ...
  },
  ...
}
```

### Interpreting Results

**Good calibration indicators:**
- Confidence gap > 0.15 (correct predictions have higher confidence)
- Bucket precision decreases monotonically (HIGH > MEDIUM > LOW)
- Error margins are low (< 2.0)

**Issues to investigate:**
- HIGH bucket precision < 90% (overconfident)
- Confidence gap < 0.10 (poor discrimination)
- High error rate for specific error types

## Stage 4: Golden Tests

### Purpose

Golden tests prevent regressions by maintaining a curated set of test cases with expected outputs.

### Location

- Test cases: `tests/golden/merchant_cases.jsonl`
- Test suite: `tests/test_golden_merchant_cases.py`

### Golden Case Format

```json
{
  "doc_id": "golden_001",
  "ocr_lines": ["INVOICE", "Global Trade Corporation", "Total: $500"],
  "expected_merchant": "Global Trade Corporation",
  "notes": "Simple case with clear merchant name"
}
```

### Adding New Golden Cases

1. Identify a representative or edge case
2. Add entry to `tests/golden/merchant_cases.jsonl`:

```json
{"doc_id": "golden_016", "ocr_lines": [...], "expected_merchant": "...", "notes": "..."}
```

3. Run tests to verify:

```bash
pytest tests/test_golden_merchant_cases.py -v
```

### Running Golden Tests

```bash
# Run all golden tests
pytest tests/test_golden_merchant_cases.py -v

# Run specific test
pytest tests/test_golden_merchant_cases.py::test_golden_merchant_extraction[golden_001] -v

# Run in CI
pytest tests/test_golden_merchant_cases.py --tb=short
```

### Test Coverage

Golden tests verify:
- ✅ Extracted merchant matches expected value
- ✅ Confidence bucket is not NONE for receipt-like documents
- ✅ Extraction is deterministic (same input → same output)
- ✅ Golden cases file format is valid

### When to Add Golden Cases

- **Bug fixes**: Add case that triggered the bug
- **Edge cases**: Unusual formats, multilingual, OCR errors
- **Regressions**: Any case that failed in production
- **Coverage**: Ensure diverse document types (receipts, invoices, logistics)

## Complete Workflow Example

### 1. Export dataset from 50 receipts

```bash
python scripts/export_merchant_labeling_dataset.py \
  --input_dir data/receipts \
  --output_dir labeling_batch_001 \
  --limit 50
```

### 2. Label the dataset

```bash
python scripts/label_merchant_dataset.py \
  --doc_level_jsonl labeling_batch_001/doc_level.jsonl \
  --labels_csv labeling_batch_001/labels.csv
```

Label 50 documents (takes ~10-15 minutes)

### 3. Evaluate results

```bash
python scripts/eval_merchant_labels.py \
  --doc_level_jsonl labeling_batch_001/doc_level.jsonl \
  --labels_csv labeling_batch_001/labels.csv \
  --output_dir labeling_batch_001/eval
```

### 4. Review errors and add golden cases

```bash
# Review errors in eval report
cat labeling_batch_001/eval/report.md

# Add problematic cases to golden tests
# Edit tests/golden/merchant_cases.jsonl

# Verify golden tests pass
pytest tests/test_golden_merchant_cases.py -v
```

### 5. Use labels for calibration improvement

The labeled dataset can be used to:
- Train new calibration models (see `calibration/merchant/` pipeline)
- Identify systematic errors in heuristics
- Measure calibration quality (ECE, reliability diagrams)

## Best Practices

### Labeling Guidelines

1. **Winner correctness**: Judge if the extracted merchant is the actual business name
   - Ignore minor formatting differences (e.g., "Inc." vs "Inc")
   - Consider OCR errors (if OCR is wrong, mark as `ocr_error`)

2. **Error types**:
   - `ocr_error`: OCR misread the merchant name
   - `layout_error`: Document layout confused the extraction
   - `heuristic_error`: Extraction logic failed (wrong zone, wrong candidate)
   - `ambiguous`: Multiple valid interpretations
   - `non_receipt`: Document is not a receipt/invoice

3. **Notes**: Add context for future reference
   - Why the extraction failed
   - What the correct answer should be
   - Any unusual document characteristics

### Redaction Guidelines

**Enable redaction (default) when:**
- Sharing datasets externally
- Working with real customer data
- Compliance requirements (GDPR, CCPA)

**Disable redaction when:**
- Internal labeling only
- Synthetic/test data
- Need full context for debugging

### Quality Assurance

- **Inter-labeler agreement**: Have 10-20% of documents labeled by multiple people
- **Spot checks**: Periodically review labels for consistency
- **Calibration**: Use evaluation metrics to identify labeling issues

## Troubleshooting

### Export fails with "No lines found"

**Issue**: Input file format not recognized

**Solution**: Ensure JSON files have `lines`, `ocr_lines`, or `text` field:

```json
{
  "lines": ["Line 1", "Line 2", ...]
}
```

### Labeling script shows "All documents are already labeled"

**Issue**: All documents in doc_level.jsonl have entries in labels.csv

**Solution**: 
- Export more documents, or
- Use `--start_from` to skip to unlabeled documents, or
- Remove entries from labels.csv to re-label

### Golden tests fail after code changes

**Issue**: Merchant extraction behavior changed

**Solution**:
1. Review the failing cases
2. If change is intentional (improvement), update expected values in `merchant_cases.jsonl`
3. If change is a regression, fix the code

### Evaluation shows poor calibration

**Issue**: Confidence scores don't match actual accuracy

**Solution**:
1. Collect more labeled data (aim for 500+ labels)
2. Run offline calibration pipeline (see `calibration/merchant/`)
3. Apply calibrated confidence in runtime (see `docs/merchant_confidence_calibration.md`)

## Integration with Calibration Pipeline

The labeling workflow integrates with the offline calibration pipeline:

```bash
# 1. Export and label dataset
python scripts/export_merchant_labeling_dataset.py --input_dir data/receipts --output_dir labels
python scripts/label_merchant_dataset.py --doc_level_jsonl labels/doc_level.jsonl --labels_csv labels/labels.csv

# 2. Convert to calibration format
# (Create CSV with required fields for calibration training)

# 3. Train calibration model
cd calibration/merchant
python calibrate.py --data ../../labels/calibration_data.csv --output calibration_output

# 4. Evaluate calibration
python evaluate.py --calibration calibration_output/calibration_merchant_v1.json

# 5. Deploy to runtime
export ENABLE_CONFIDENCE_CALIBRATION=1
export CONFIDENCE_CALIBRATION_PATH=calibration/merchant/calibration_output/calibration_merchant_v1.json
```

## References

- **EntityResult V2 Schema**: `app/pipelines/features.py`
- **Confidence Calibration**: `docs/merchant_confidence_calibration.md`
- **Offline Calibration Pipeline**: `calibration/merchant/README.md`
- **Export Script**: `scripts/export_merchant_labeling_dataset.py`
- **Labeling Script**: `scripts/label_merchant_dataset.py`
- **Evaluation Script**: `scripts/eval_merchant_labels.py`
- **Golden Tests**: `tests/test_golden_merchant_cases.py`
