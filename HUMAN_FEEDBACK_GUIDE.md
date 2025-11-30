# Human Feedback Loop - Learning System Guide

## Overview

VeriReceipt includes a **complete human-in-the-loop learning system** that allows the AI to improve over time based on human corrections.

### How It Works

```
1. Receipt Analysis (Automated)
   ↓
2. Human Review & Correction
   ↓
3. Feedback Storage (CSV/Database)
   ↓
4. ML Model Retraining (Weekly/Monthly)
   ↓
5. Improved Detection (Back to Step 1)
```

---

## Components

### 1. Analysis Storage
**File**: `data/logs/decisions.csv`

Every receipt analysis is automatically logged with:
- File path and metadata
- Engine prediction (real/suspicious/fake)
- Fraud score (0.0 - 1.0)
- Detailed reasons
- All extracted features

### 2. Feedback Collection
**File**: `data/logs/feedback.csv`

Human reviewers can correct predictions:
- Original engine prediction
- Corrected label
- Reviewer ID
- Comments and reason codes
- Timestamp

### 3. ML Training Module
**File**: `app/ml/training.py`

Learns from feedback to improve detection:
- Loads feedback and analysis data
- Trains Random Forest or Gradient Boosting models
- Evaluates performance with cross-validation
- Saves trained models for future use

---

## Usage Guide

### Step 1: Analyze Receipts

Receipts are automatically logged when analyzed via API or scripts:

```bash
# Via API
curl -X POST http://localhost:8080/analyze -F "file=@receipt.jpg"

# Via script
python test_run.py
```

All analyses are saved to `data/logs/decisions.csv`.

---

### Step 2: Submit Human Feedback

#### Option A: Interactive Mode

```bash
python submit_feedback.py
```

You'll be prompted for:
- Receipt filename (e.g., `Gas_bill.jpeg`)
- Correct label (real/suspicious/fake)
- Your email/ID (optional)
- Reason for correction (optional)
- Reason code (optional)

**Example Session:**
```
Enter the receipt filename (e.g., Gas_bill.jpeg):
> fake_receipt_canva.pdf

What is the CORRECT label for this receipt?
  1. real
  2. suspicious
  3. fake
> 3

Your email or ID (optional, press Enter to skip):
> john.doe@company.com

Why did you correct this?
> This was created in Canva, clearly fabricated

Reason code (e.g., FAKE_MERCHANT, EDITED_TOTAL):
> CANVA_TEMPLATE

✅ Feedback submitted successfully!
```

#### Option B: Batch Mode (CSV)

Create a CSV file with feedback:

**feedback_batch.csv:**
```csv
analysis_ref,given_label,reviewer_id,comment,reason_code
fake_receipt_canva.pdf,fake,john@company.com,Created in Canva,CANVA_TEMPLATE
edited_total.jpg,fake,jane@company.com,Total was edited,EDITED_TOTAL
real_receipt.pdf,real,john@company.com,Verified with merchant,VERIFIED
```

Submit in batch:
```bash
python submit_feedback.py feedback_batch.csv
```

#### Option C: Via API

```bash
curl -X POST http://localhost:8080/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "analysis_ref": "receipt.jpg",
    "given_label": "fake",
    "reviewer_id": "john@company.com",
    "comment": "Merchant does not exist",
    "reason_code": "FAKE_MERCHANT"
  }'
```

**Python Example:**
```python
import requests

feedback = {
    "analysis_ref": "receipt.jpg",
    "given_label": "fake",
    "reviewer_id": "john@company.com",
    "comment": "Total was manually edited",
    "reason_code": "EDITED_TOTAL"
}

response = requests.post("http://localhost:8080/feedback", json=feedback)
print(response.json())
```

---

### Step 3: Retrain the Model

After collecting feedback (recommended: 50+ samples), retrain the ML model:

```bash
python -m app.ml.training
```

**Output:**
```
================================================================================
VeriReceipt - Retraining from Human Feedback
================================================================================

Loading feedback and analysis data...
✅ Loaded 127 training samples
   Label distribution: {0: 85, 1: 22, 2: 20}

Training model...

=== Training Results ===
Model: random_forest
Train Accuracy: 0.951
Test Accuracy: 0.923
CV Score: 0.915 (+/- 0.042)

Classification Report:
              precision    recall  f1-score   support

        real       0.95      0.97      0.96        17
  suspicious       0.88      0.78      0.82         9
        fake       0.93      1.00      0.96         4

    accuracy                           0.92        30
   macro avg       0.92      0.92      0.91        30
weighted avg       0.92      0.92      0.92        30

Confusion Matrix:
[[17  0  0]
 [ 2  7  0]
 [ 0  0  4]]

Top 5 Important Features:
  engine_score: 0.342
  suspicious_producer: 0.156
  total_mismatch: 0.128
  num_lines: 0.089
  has_merchant: 0.067

✅ Model saved to data/models/feedback_model.pkl
✅ Metrics saved to data/models/training_metrics.json

================================================================================
✅ Retraining complete!
================================================================================
```

---

### Step 4: Use the Trained Model

The trained model can be integrated into the analysis pipeline:

```python
from app.ml.training import FeedbackLearner

# Load trained model
learner = FeedbackLearner()
learner.load_model()

# Extract features from a receipt
features = extract_features(receipt)  # Your feature extraction

# Get ML prediction
ml_label, confidence = learner.predict(features)

print(f"ML Prediction: {ml_label} (confidence: {confidence:.2f})")
```

**Hybrid Approach (Recommended):**
```python
# 1. Get rule-based score
rule_score = analyze_receipt_with_rules(receipt)

# 2. If suspicious, get ML second opinion
if 0.3 <= rule_score < 0.6:
    ml_label, ml_confidence = learner.predict(features)
    
    # Combine scores
    if ml_confidence > 0.8:
        final_label = ml_label
    else:
        final_label = "suspicious"  # Keep for human review
```

---

## Feedback Workflow for Teams

### For Finance Teams

1. **Daily Review**
   - Review all receipts flagged as "suspicious" or "fake"
   - Verify with employees or merchants
   - Submit corrections via web interface

2. **Weekly Training**
   - Run retraining script every Friday
   - Review accuracy metrics
   - Adjust rule weights if needed

3. **Monthly Audit**
   - Review model performance trends
   - Identify common false positives/negatives
   - Update fraud detection rules

### For Developers

1. **Monitor Feedback**
   ```bash
   # Check feedback count
   wc -l data/logs/feedback.csv
   
   # View recent feedback
   tail -20 data/logs/feedback.csv
   ```

2. **Evaluate Model**
   ```bash
   # Retrain and check metrics
   python -m app.ml.training
   
   # View metrics
   cat data/models/training_metrics.json
   ```

3. **Deploy Updated Model**
   ```bash
   # Copy model to production
   cp data/models/feedback_model.pkl /path/to/production/
   
   # Restart API
   systemctl restart verireceipt-api
   ```

---

## Reason Codes (Standardized)

Use these codes for consistent feedback:

### Fake Receipt Codes
- `CANVA_TEMPLATE` - Created using Canva or similar tools
- `PHOTOSHOP_EDIT` - Edited in Photoshop/image editor
- `FAKE_MERCHANT` - Merchant does not exist
- `EDITED_TOTAL` - Total amount was manually changed
- `EDITED_DATE` - Date was altered
- `ONLINE_GENERATOR` - Created using fake receipt generator
- `DUPLICATE` - Duplicate submission
- `WRONG_CURRENCY` - Currency mismatch

### Real Receipt Codes
- `VERIFIED` - Verified with merchant
- `EMPLOYEE_CONFIRMED` - Employee confirmed authenticity
- `BANK_STATEMENT` - Matches bank statement
- `POOR_OCR` - Real but OCR failed
- `UNUSUAL_FORMAT` - Real but unusual layout

### Suspicious Codes
- `NEEDS_REVIEW` - Requires additional verification
- `PARTIAL_INFO` - Missing some information
- `UNCLEAR_IMAGE` - Image quality too poor to determine

---

## Data Files

### decisions.csv
```csv
timestamp,file_path,label,score,reasons,file_size_bytes,num_pages,...
2025-11-30T10:00:00,receipt1.jpg,real,0.0,"No anomalies",123456,1,...
2025-11-30T10:05:00,receipt2.pdf,fake,0.85,"Canva producer",234567,1,...
```

### feedback.csv
```csv
timestamp,analysis_ref,receipt_ref,engine_label,engine_score,given_label,reviewer_id,comment,reason_code
2025-11-30T11:00:00,receipt2.pdf,,fake,0.85,fake,john@co.com,Confirmed fake,CANVA_TEMPLATE
2025-11-30T11:05:00,receipt3.jpg,,suspicious,0.45,real,jane@co.com,Verified,VERIFIED
```

---

## Best Practices

### 1. Feedback Quality
- ✅ Provide detailed comments
- ✅ Use standardized reason codes
- ✅ Include reviewer ID for accountability
- ✅ Verify before correcting (don't guess)

### 2. Training Frequency
- **Small teams (< 100 receipts/week)**: Monthly retraining
- **Medium teams (100-1000 receipts/week)**: Weekly retraining
- **Large teams (> 1000 receipts/week)**: Daily retraining

### 3. Minimum Data Requirements
- **Initial training**: 50+ feedback samples
- **Production deployment**: 200+ feedback samples
- **High accuracy**: 500+ feedback samples

### 4. Model Evaluation
- Track accuracy over time
- Monitor false positive/negative rates
- Compare rule-based vs ML performance
- A/B test new models before deployment

---

## Integration with Web UI

The feedback system can be integrated into a web interface:

```javascript
// Example: Submit feedback from web UI
async function submitFeedback(receiptId, correctedLabel, comment) {
  const response = await fetch('http://localhost:8080/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      analysis_ref: receiptId,
      given_label: correctedLabel,
      reviewer_id: currentUser.email,
      comment: comment,
      reason_code: getReasonCode(correctedLabel)
    })
  });
  
  return response.json();
}
```

---

## Troubleshooting

### "No training data available"
- Ensure feedback.csv exists and has entries
- Check that analysis_ref matches file_path in decisions.csv
- Verify CSV format is correct

### "Insufficient training data"
- Collect at least 50 feedback samples before training
- Ensure balanced labels (not all "real" or all "fake")

### "Model accuracy is low"
- Collect more diverse feedback samples
- Check for data quality issues
- Review feature extraction logic
- Try different model types (random_forest vs gradient_boosting)

### "Feedback endpoint returns 501"
- You're using CSV backend (default)
- Feedback is now implemented for CSV backend
- Ensure API is restarted after code updates

---

## Future Enhancements

1. **Active Learning**
   - Automatically flag uncertain predictions for human review
   - Prioritize feedback collection on edge cases

2. **Confidence Scoring**
   - Show ML confidence alongside predictions
   - Route low-confidence cases to human review

3. **Feedback Analytics Dashboard**
   - Visualize feedback trends
   - Track reviewer performance
   - Monitor model improvement over time

4. **Automated Retraining**
   - Trigger retraining when feedback threshold reached
   - Scheduled retraining (cron jobs)
   - A/B testing of new models

---

## Summary

✅ **You now have a complete learning system:**

1. **Analysis logging** - Every receipt is tracked
2. **Feedback collection** - Multiple ways to submit corrections
3. **ML training** - Automated model improvement
4. **Model deployment** - Use trained models in production

**Start collecting feedback today and watch your system improve!** 🚀
