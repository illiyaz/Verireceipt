# VeriReceipt Feedback System - Status & Next Steps

## ✅ Completed Components

### Backend Infrastructure
- [x] Feedback data models (`app/models/feedback.py`)
- [x] SQLite storage (`app/repository/feedback_store.py`)
- [x] Learning engine (`app/pipelines/learning.py`)
- [x] Feedback API endpoints (`app/api/feedback.py`)
- [x] Integration with main API

### Frontend UI
- [x] Review page with feedback submission (`web/review.html`)
- [x] Stats dashboard (`web/stats.html`)
- [x] Navigation links in main interface
- [x] Success/error handling

### Learning Capabilities
- [x] False negative learning (increase detection)
- [x] False positive learning (reduce over-flagging)
- [x] Pattern extraction from user notes
- [x] Rule confidence adjustment
- [x] Rule enable/disable functionality

---

## 🔧 Pending Tasks

### 1. End-to-End Testing
**Priority:** HIGH
**Status:** Not tested yet

**Test Cases:**
```
Test 1: Submit feedback for correct verdict
- Upload receipt → Get verdict "fake (80%)"
- User confirms: "Yes, correct"
- Expected: Feedback saved, no rule changes

Test 2: Submit feedback for false negative
- Upload receipt → Get verdict "real (40%)"
- User corrects: "This is FAKE - iLovePDF detected"
- Expected: Rule updated, confidence increased

Test 3: Submit feedback for false positive
- Upload receipt → Get verdict "fake (75%)"
- User corrects: "This is REAL - legitimate business"
- Expected: Rule confidence decreased

Test 4: View stats dashboard
- Navigate to /stats.html
- Expected: See accuracy metrics, learned rules

Test 5: Enable/disable learned rules
- Toggle rule on/off
- Expected: Rule status updated in database
```

**Action Items:**
- [ ] Test feedback submission workflow
- [ ] Verify learning engine updates rules
- [ ] Check stats dashboard displays correctly
- [ ] Verify rule toggle functionality

---

### 2. Enhance Rule-Based Learning

**Current Limitations:**
- Only learns from explicit patterns (software, dates)
- Doesn't learn from merchant names
- Doesn't learn from address patterns
- Doesn't learn threshold adjustments

**Enhancements Needed:**

#### A. Merchant Name Learning
```python
# Add to learning.py
def _learn_merchant_patterns(feedback, store):
    """Learn which merchant names are suspicious/legitimate."""
    merchant = feedback.merchant_pattern
    
    if feedback.correct_verdict == "fake":
        # Add to suspicious merchant list
        create_rule(
            type="suspicious_merchant",
            pattern=merchant,
            confidence_adjustment=0.15
        )
    elif feedback.correct_verdict == "real":
        # Add to whitelist (reduce false positives)
        create_rule(
            type="legitimate_merchant",
            pattern=merchant,
            confidence_adjustment=-0.10  # Reduce suspicion
        )
```

#### B. Address Pattern Learning
```python
def _learn_address_patterns(feedback, store):
    """Learn address format patterns."""
    if "invalid address" in str(feedback.detected_indicators):
        if feedback.correct_verdict == "real":
            # This address format is actually valid
            create_rule(
                type="valid_address_format",
                pattern=extract_address_pattern(feedback),
                confidence_adjustment=-0.10
            )
```

#### C. Threshold Learning
```python
def _learn_thresholds(feedback, store):
    """Adjust detection thresholds based on feedback."""
    # If spacing was missed
    if "spacing" in feedback.missed_indicators:
        # Lower the spacing threshold
        update_threshold("spacing_consecutive_spaces", decrease=1)
    
    # If spacing was falsely flagged
    if "spacing" in feedback.false_indicators:
        # Raise the spacing threshold
        update_threshold("spacing_consecutive_spaces", increase=1)
```

**Action Items:**
- [ ] Implement merchant name learning
- [ ] Implement address pattern learning
- [ ] Implement threshold learning
- [ ] Add pattern extraction utilities

---

### 3. Improve Feedback Collection

**Current Issues:**
- Feedback form doesn't capture enough detail
- No way to annotate specific issues on receipt
- No way to mark specific text/regions as problematic

**Enhancements Needed:**

#### A. Rich Feedback Form
```javascript
// Add to review.html
<div className="feedback-details">
    <h3>What was wrong?</h3>
    
    {/* Specific issue checkboxes */}
    <label>
        <input type="checkbox" value="merchant_wrong" />
        Merchant name incorrect
    </label>
    <label>
        <input type="checkbox" value="total_wrong" />
        Total amount incorrect
    </label>
    <label>
        <input type="checkbox" value="date_wrong" />
        Date incorrect
    </label>
    <label>
        <input type="checkbox" value="spacing_missed" />
        Spacing anomaly not detected
    </label>
    <label>
        <input type="checkbox" value="software_missed" />
        Suspicious software not detected
    </label>
    
    {/* Free text for details */}
    <textarea placeholder="Additional details..." />
</div>
```

#### B. Visual Annotation (Future)
```javascript
// Allow users to draw boxes on receipt
<ImageAnnotator 
    image={receipt.image_url}
    onAnnotation={(bbox, label) => {
        // Save annotation: "This region has spacing issues"
        annotations.push({ bbox, label, issue: "spacing" })
    }}
/>
```

**Action Items:**
- [ ] Add detailed feedback checkboxes
- [ ] Add free-text notes field
- [ ] Improve feedback data structure
- [ ] (Future) Add visual annotation tool

---

### 4. Stats Dashboard Improvements

**Current Limitations:**
- Basic metrics only
- No trend visualization
- No per-rule accuracy tracking
- No comparison over time

**Enhancements Needed:**

#### A. Trend Charts
```javascript
// Add to stats.html
<LineChart 
    data={accuracyOverTime}
    xAxis="date"
    yAxis="accuracy"
    title="Accuracy Improvement Over Time"
/>
```

#### B. Per-Rule Analytics
```javascript
<RuleAnalytics 
    rule={rule}
    metrics={{
        times_triggered: 45,
        correct_predictions: 38,
        false_positives: 5,
        false_negatives: 2,
        accuracy: 84.4%
    }}
/>
```

#### C. Comparison View
```javascript
<ComparisonView>
    <Column title="Last Week">
        Accuracy: 85%
        False Positives: 12
    </Column>
    <Column title="This Week">
        Accuracy: 90% ⬆️
        False Positives: 6 ⬇️
    </Column>
</ComparisonView>
```

**Action Items:**
- [ ] Add trend tracking to database
- [ ] Implement chart visualization
- [ ] Add per-rule analytics
- [ ] Add time-based comparisons

---

### 5. Integration with Analysis Pipeline

**Current Issue:**
- Learned rules are stored but not applied during analysis
- Need to integrate learning engine with rule-based pipeline

**Required Changes:**

#### A. Apply Learned Rules During Analysis
```python
# In app/pipelines/rules.py
from app.pipelines.learning import apply_learned_rules

def analyze_receipt(file_path, **kwargs):
    # ... existing analysis ...
    
    # Apply learned rules
    learned_adjustment, triggered_rules = apply_learned_rules(features)
    
    # Adjust score
    decision.score += learned_adjustment
    
    # Add triggered rules to reasons
    for rule in triggered_rules:
        decision.reasons.append(f"📚 Learned: {rule}")
    
    return decision
```

#### B. Track Rule Performance
```python
# After each analysis, track if learned rules helped
def track_rule_performance(receipt_id, learned_rules_used, final_verdict):
    # Store for later validation when feedback arrives
    store_prediction(receipt_id, learned_rules_used, final_verdict)
```

**Action Items:**
- [ ] Integrate `apply_learned_rules()` into analysis pipeline
- [ ] Add learned rule indicators in verdict reasoning
- [ ] Track which learned rules were used
- [ ] Update rule accuracy based on feedback

---

## 📊 Testing Checklist

### Manual Testing
- [ ] Upload receipt → Analyze → Review → Submit feedback
- [ ] Verify feedback appears in stats dashboard
- [ ] Verify learned rules are created/updated
- [ ] Upload similar receipt → Verify improved detection
- [ ] Toggle rule on/off → Verify behavior changes

### Automated Testing
- [ ] Unit tests for learning engine
- [ ] Integration tests for feedback API
- [ ] End-to-end test for full workflow

---

## 🎯 Success Metrics

### After 100 Feedbacks:
- [ ] Accuracy improvement: +5-10%
- [ ] False positives reduced: -30%
- [ ] False negatives reduced: -20%
- [ ] 10-15 learned rules active

### After 500 Feedbacks:
- [ ] Accuracy improvement: +10-15%
- [ ] False positives reduced: -50%
- [ ] False negatives reduced: -40%
- [ ] 30-50 learned rules active

---

## 🚀 Next Phase: ML Model Fine-Tuning

**After completing rule-based learning:**

1. **RL Ensemble** (1-2 weeks)
   - Implement reinforcement learning for engine weights
   - Expected: +5% accuracy improvement

2. **Vision LLM Fine-Tuning** (2-4 weeks)
   - Collect 500+ annotated receipts
   - Fine-tune LLaVA on feedback data
   - Expected: +10-20% accuracy improvement

3. **DONUT Fine-Tuning** (2-4 weeks)
   - Fine-tune for better extraction
   - Expected: +20-30% extraction accuracy

---

## 📝 Documentation Needed

- [ ] User guide: How to submit feedback
- [ ] Admin guide: How to review learned rules
- [ ] Developer guide: How to add new learning patterns
- [ ] Deployment guide: How to export/import rules

---

## 🔧 Technical Debt

- [ ] Add proper error handling in learning engine
- [ ] Add transaction support for database operations
- [ ] Add logging for debugging
- [ ] Add validation for feedback data
- [ ] Add rate limiting for feedback API
- [ ] Add authentication for stats dashboard

---

## 💡 Future Enhancements

- [ ] Active learning: System asks for feedback on uncertain cases
- [ ] Confidence calibration: Adjust confidence scores based on feedback
- [ ] Multi-user feedback: Aggregate feedback from multiple reviewers
- [ ] Feedback quality scoring: Weight feedback by reviewer accuracy
- [ ] Automated testing: Generate synthetic receipts for validation
