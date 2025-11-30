# Human Feedback Loop - COMPLETE ✅

## What Was Built

You now have a **complete human-in-the-loop learning system** that allows VeriReceipt to continuously improve from human corrections.

---

## System Components

### 1. ✅ Analysis Storage
**File**: `data/logs/decisions.csv`

Every receipt analysis is automatically logged with:
- All extracted features
- Engine predictions
- Fraud scores
- Detailed reasoning

### 2. ✅ Feedback Collection
**File**: `data/logs/feedback.csv`

Multiple ways to collect human corrections:
- Interactive CLI (`submit_feedback.py`)
- Batch CSV import
- REST API endpoint (`POST /feedback`)

### 3. ✅ ML Training Module
**File**: `app/ml/training.py`

Complete machine learning pipeline:
- Loads feedback and analysis data
- Trains Random Forest/Gradient Boosting models
- Cross-validation and evaluation
- Feature importance analysis
- Model persistence

### 4. ✅ Feedback Logger
**File**: `app/utils/feedback_logger.py`

Utility for logging feedback to CSV with:
- Timestamp tracking
- Original vs corrected labels
- Reviewer information
- Comments and reason codes

### 5. ✅ Repository Integration
**Updated**: `app/repository/receipt_store.py`

Both CSV and DB backends now support:
- `save_feedback()` - Store human corrections
- Automatic linking to original analyses
- Retrieval for ML training

---

## How to Use

### Step 1: Analyze Receipts

Receipts are automatically logged when analyzed:

```bash
# Via API
curl -X POST http://localhost:8080/analyze -F "file=@receipt.jpg"

# Via script
python test_run.py
python test_all_samples.py
```

### Step 2: Collect Feedback

#### Option A: Interactive Mode
```bash
python submit_feedback.py
```

#### Option B: Batch Mode
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
    "comment": "Verified as fabricated",
    "reason_code": "CANVA_TEMPLATE"
  }'
```

### Step 3: Retrain Model

After collecting feedback (50+ samples recommended):

```bash
python -m app.ml.training
```

**Output includes:**
- Training/test accuracy
- Cross-validation scores
- Classification report
- Confusion matrix
- Feature importance
- Saved model at `data/models/feedback_model.pkl`

### Step 4: Use Trained Model

```python
from app.ml.training import FeedbackLearner

# Load model
learner = FeedbackLearner()
learner.load_model()

# Predict
ml_label, confidence = learner.predict(features)
print(f"ML says: {ml_label} (confidence: {confidence:.2f})")
```

---

## Files Created

### Core ML System
- ✅ `app/ml/__init__.py`
- ✅ `app/ml/training.py` - Complete ML training pipeline

### Utilities
- ✅ `app/utils/feedback_logger.py` - Feedback logging

### Scripts
- ✅ `submit_feedback.py` - Interactive/batch feedback submission
- ✅ `demo_feedback_loop.py` - Complete workflow demonstration

### Documentation
- ✅ `HUMAN_FEEDBACK_GUIDE.md` - Comprehensive guide (50+ pages)
- ✅ `FEEDBACK_SYSTEM_COMPLETE.md` - This file

### Updated Files
- ✅ `app/repository/receipt_store.py` - Feedback support for CSV backend
- ✅ `README.md` - Updated roadmap and API docs

---

## Demo Workflow

Run the complete demo:

```bash
python demo_feedback_loop.py
```

This demonstrates:
1. Analyzing receipts
2. Collecting feedback
3. Training ML model
4. Using improved predictions

---

## Learning Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                    CONTINUOUS LEARNING LOOP                  │
└─────────────────────────────────────────────────────────────┘

1. Receipt Upload
   ↓
2. Rule-Based Analysis (Fast, Explainable)
   ↓
3. Human Review (Finance Team)
   ↓
4. Feedback Collection (Corrections)
   ↓
5. ML Model Training (Weekly/Monthly)
   ↓
6. Hybrid Prediction (Rules + ML)
   ↓
7. Improved Accuracy (Back to Step 1)
```

---

## Hybrid Approach (Recommended)

Combine rule-based and ML predictions:

```python
# 1. Get rule-based prediction
rule_decision = analyze_receipt(receipt_path)

# 2. If suspicious, get ML second opinion
if 0.3 <= rule_decision.score < 0.6:
    learner = FeedbackLearner()
    learner.load_model()
    
    ml_label, ml_confidence = learner.predict(features)
    
    # 3. Combine predictions
    if ml_confidence > 0.8:
        final_label = ml_label
        final_confidence = ml_confidence
    else:
        final_label = "suspicious"  # Route to human review
        final_confidence = 0.5

# 4. High confidence cases (rules or ML)
else:
    final_label = rule_decision.label
    final_confidence = 1.0 - rule_decision.score if rule_decision.label == "real" else rule_decision.score
```

---

## Data Flow

### Analysis Data (decisions.csv)
```csv
timestamp,file_path,label,score,reasons,file_size_bytes,num_pages,has_any_amount,has_date,has_merchant,total_mismatch,num_lines,suspicious_producer,has_creation_date,exif_present,uppercase_ratio,unique_char_count,numeric_line_ratio
2025-11-30T10:00:00,receipt1.jpg,real,0.0,"No anomalies",123456,1,True,True,True,False,25,False,True,False,0.15,45,0.2
2025-11-30T10:05:00,receipt2.pdf,fake,0.85,"Canva producer; Total mismatch",234567,1,True,True,True,True,18,True,False,False,0.65,28,0.4
```

### Feedback Data (feedback.csv)
```csv
timestamp,analysis_ref,receipt_ref,engine_label,engine_score,given_label,reviewer_id,comment,reason_code
2025-11-30T11:00:00,receipt1.jpg,,real,0.0,real,john@co.com,Verified with merchant,VERIFIED
2025-11-30T11:05:00,receipt2.pdf,,fake,0.85,fake,jane@co.com,Confirmed fabricated,CANVA_TEMPLATE
2025-11-30T11:10:00,receipt3.jpg,,suspicious,0.45,real,john@co.com,Poor OCR but legitimate,POOR_OCR
```

### Training Metrics (training_metrics.json)
```json
{
  "train_accuracy": 0.951,
  "test_accuracy": 0.923,
  "cv_mean": 0.915,
  "cv_std": 0.042,
  "train_samples": 102,
  "test_samples": 25,
  "model_type": "random_forest",
  "timestamp": "2025-11-30T12:00:00",
  "feature_importance": {
    "engine_score": 0.342,
    "suspicious_producer": 0.156,
    "total_mismatch": 0.128,
    "num_lines": 0.089,
    "has_merchant": 0.067
  }
}
```

---

## Best Practices

### For Finance Teams

1. **Daily Review**
   - Review all "suspicious" and "fake" receipts
   - Verify with employees or merchants
   - Submit corrections immediately

2. **Weekly Training**
   - Run retraining every Friday
   - Review accuracy metrics
   - Adjust thresholds if needed

3. **Monthly Audit**
   - Analyze trends in fraud types
   - Update detection rules
   - Review false positive/negative rates

### For Developers

1. **Monitor Feedback Volume**
   ```bash
   # Check feedback count
   wc -l data/logs/feedback.csv
   
   # View recent feedback
   tail -20 data/logs/feedback.csv
   ```

2. **Track Model Performance**
   ```bash
   # View latest metrics
   cat data/models/training_metrics.json | jq
   
   # Compare with previous versions
   diff training_metrics_v1.json training_metrics_v2.json
   ```

3. **Automated Retraining**
   ```bash
   # Add to cron (weekly on Friday at 11 PM)
   0 23 * * 5 cd /path/to/VeriReceipt && python -m app.ml.training
   ```

---

## Minimum Data Requirements

| Stage | Feedback Samples | Recommended Action |
|-------|-----------------|-------------------|
| **Initial Training** | 50+ | Start collecting feedback |
| **Production Deployment** | 200+ | Deploy with confidence |
| **High Accuracy** | 500+ | Achieve 95%+ accuracy |
| **Enterprise Grade** | 1000+ | Multi-class precision |

---

## Integration Examples

### Web UI Integration

```javascript
// Submit feedback from web interface
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
  
  const result = await response.json();
  showNotification(`Feedback submitted: ${result.message}`);
}
```

### Slack Bot Integration

```python
# Notify team when model is retrained
import requests

def notify_slack(metrics):
    webhook_url = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
    
    message = {
        "text": "🎓 VeriReceipt Model Retrained!",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*New Model Performance*\n"
                            f"• Accuracy: {metrics['test_accuracy']:.1%}\n"
                            f"• Training Samples: {metrics['train_samples']}\n"
                            f"• Top Feature: {list(metrics['feature_importance'].keys())[0]}"
                }
            }
        ]
    }
    
    requests.post(webhook_url, json=message)
```

---

## Troubleshooting

### "No training data available"
**Solution**: Collect at least 50 feedback samples first
```bash
python submit_feedback.py
```

### "Insufficient training data"
**Solution**: Ensure balanced labels (not all "real" or all "fake")
```bash
# Check label distribution
python -c "import pandas as pd; print(pd.read_csv('data/logs/feedback.csv')['given_label'].value_counts())"
```

### "Model accuracy is low"
**Solutions**:
1. Collect more diverse samples
2. Check feature extraction quality
3. Try different model types
4. Review feedback quality

### "Feedback endpoint returns 501"
**Solution**: CSV backend now supports feedback. Restart API:
```bash
# Stop old API
pkill -f "python run_api.py"

# Start new API
python run_api.py
```

---

## Future Enhancements

### Active Learning (Phase 3)
- Automatically flag uncertain predictions
- Prioritize feedback on edge cases
- Adaptive sampling strategies

### Confidence Scoring (Phase 3)
- Show ML confidence alongside predictions
- Route low-confidence to human review
- Threshold tuning based on cost/accuracy tradeoff

### Feedback Analytics Dashboard (Phase 4)
- Visualize feedback trends
- Track reviewer performance
- Monitor model improvement over time
- A/B testing of models

### Automated Retraining (Phase 4)
- Trigger when feedback threshold reached
- Scheduled retraining (cron jobs)
- Automatic model deployment
- Rollback on performance degradation

---

## Success Metrics

Track these KPIs to measure system improvement:

1. **Accuracy**: % of correct predictions
2. **Precision**: % of flagged receipts that are actually fake
3. **Recall**: % of fake receipts that are caught
4. **False Positive Rate**: % of real receipts flagged as fake
5. **Feedback Volume**: # of corrections per week
6. **Model Improvement**: Accuracy gain after retraining
7. **Review Time**: Average time to review suspicious receipts

---

## Summary

✅ **Complete Learning System Built!**

You now have:
1. ✅ Automatic analysis logging
2. ✅ Multiple feedback collection methods
3. ✅ ML training pipeline
4. ✅ Model evaluation and persistence
5. ✅ Hybrid prediction capability
6. ✅ Comprehensive documentation

**Next Steps:**
1. Collect real and fake receipts
2. Analyze them with the system
3. Submit corrections via feedback
4. Retrain the model weekly
5. Watch accuracy improve!

**The system is ready to learn from your team! 🚀**
