# VeriReceipt Feedback Workflow - Testing Guide

## 🎯 Test Objective
Verify that the complete feedback loop works:
1. Analyze receipt → Get verdict
2. Submit feedback correction → System learns
3. Re-analyze similar receipt → Improved detection
4. View stats → See learned rules

---

## 🚀 Prerequisites

✅ Server running at: http://localhost:3000
✅ API running at: http://localhost:8000
✅ Test receipts available in: `data/raw/`

---

## 📝 Test Scenario 1: False Negative Learning

**Goal:** System misses fraud, user corrects it, system learns to detect it better

### Step 1: Baseline Analysis
1. Open http://localhost:3000
2. Upload: `data/raw/Apple Macbook receipt.pdf`
3. Wait for analysis to complete
4. **Record the verdict:** 
   - Label: ___________
   - Confidence: ___________
   - Detected indicators: ___________

### Step 2: Submit Feedback (Assume it's fake)
1. Click **"Human Review"** button
2. On review page, select verdict: **"Fake"**
3. Check any relevant reasons:
   - [ ] Software detected (if applicable)
   - [ ] Spacing issues
   - [ ] Date manipulation
4. Add notes: "This receipt has suspicious software/spacing"
5. Click **"Submit Feedback"**
6. **Expected:** Success message with learning info
   - Rules updated: X
   - New patterns learned: [list]

### Step 3: Verify Learning in Stats
1. Navigate to http://localhost:3000/stats.html
2. **Check:**
   - Total Feedback: Should be 1
   - Learned Rules: Should show new rule(s)
   - Rule details: Pattern, confidence adjustment
3. **Record learned rules:** ___________

### Step 4: Test Improved Detection
1. Go back to http://localhost:3000
2. Upload the **same receipt** again
3. Wait for analysis
4. **Compare with Step 1:**
   - New confidence: ___________ (should be higher)
   - New reasoning: Should include "📚 Learned Rule: ..."
5. **Expected:** System now detects it better

---

## 📝 Test Scenario 2: False Positive Learning

**Goal:** System over-flags real receipt, user corrects it, system becomes less aggressive

### Step 1: Find Over-Flagged Receipt
1. Upload: `data/raw/17492-22-SHYU.pdf`
2. **Record verdict:** ___________
3. If verdict is "fake" or "suspicious", proceed

### Step 2: Submit Feedback (Mark as Real)
1. Click **"Human Review"**
2. Select verdict: **"Real"**
3. Add notes: "This is a legitimate receipt, not fake"
4. Submit feedback

### Step 3: Verify Learning
1. Check stats dashboard
2. **Expected:** Rule confidence should be reduced or rule disabled
3. **Record:** ___________

### Step 4: Test Reduced Sensitivity
1. Upload same receipt again
2. **Expected:** Lower fraud score, less aggressive verdict

---

## 📝 Test Scenario 3: Multiple Feedbacks

**Goal:** Verify system improves with multiple corrections

### Step 1: Submit 5 Feedbacks
Upload and correct 5 different receipts:
1. Receipt 1: ___________
2. Receipt 2: ___________
3. Receipt 3: ___________
4. Receipt 4: ___________
5. Receipt 5: ___________

### Step 2: Check Stats Dashboard
1. Total Feedback: Should be 5+
2. Accuracy: Calculate based on corrections
3. Learned Rules: Should have multiple rules
4. Most Common Missed Indicators: Should show patterns

---

## 📝 Test Scenario 4: Rule Management

**Goal:** Verify rule enable/disable functionality

### Step 1: View Learned Rules
1. Go to stats dashboard
2. Find a learned rule
3. **Record:** Rule ID, pattern, status

### Step 2: Disable Rule
1. Click **"Disable"** button on a rule
2. **Expected:** Rule status changes to "Disabled"

### Step 3: Test Without Rule
1. Upload receipt that would trigger that rule
2. **Expected:** Rule should NOT be applied
3. Reasoning should NOT include that learned rule

### Step 4: Re-enable Rule
1. Go back to stats dashboard
2. Click **"Enable"** button
3. **Expected:** Rule status changes to "Active"

### Step 5: Verify Rule Applied
1. Upload same receipt again
2. **Expected:** Rule IS applied now

---

## 🔍 Verification Checklist

### Backend API
- [ ] POST /feedback/submit - Returns success with learning info
- [ ] GET /feedback/stats - Returns accurate statistics
- [ ] GET /feedback/history - Shows submitted feedback
- [ ] GET /feedback/learned-rules - Lists all learned rules
- [ ] POST /feedback/rules/{id}/toggle - Toggles rule status

### Database
- [ ] Check `data/feedback.db` exists
- [ ] Feedback records saved correctly
- [ ] Learned rules saved correctly
- [ ] Stats calculated correctly

### Learning Engine
- [ ] False negative → Increases confidence
- [ ] False positive → Decreases confidence
- [ ] New patterns discovered
- [ ] Rules applied during analysis
- [ ] Reasoning shows learned rules

### UI
- [ ] Review page loads correctly
- [ ] Feedback form works
- [ ] Success message displays
- [ ] Stats dashboard loads
- [ ] Charts/metrics display correctly
- [ ] Rule toggle works

---

## 🐛 Common Issues & Solutions

### Issue 1: Feedback submission fails
**Symptoms:** Error message when submitting feedback
**Check:**
- Browser console for errors
- Server logs for API errors
- Database file permissions

**Solution:**
```bash
# Check server logs
# Look for errors in terminal

# Check database
ls -la data/feedback.db

# Restart server if needed
pkill -f uvicorn
python run_web_demo.py
```

### Issue 2: Learned rules not applied
**Symptoms:** No "📚 Learned Rule" in reasoning
**Check:**
- Rules exist in database
- Rules are enabled
- apply_learned=True in rules.py

**Solution:**
```bash
# Check learned rules via API
curl http://localhost:8000/feedback/learned-rules

# Check server logs for learning errors
```

### Issue 3: Stats dashboard empty
**Symptoms:** No data showing in stats
**Check:**
- Feedback actually submitted
- Database has records
- API endpoint working

**Solution:**
```bash
# Test API directly
curl http://localhost:8000/feedback/stats

# Check database
sqlite3 data/feedback.db "SELECT COUNT(*) FROM feedback;"
```

---

## 📊 Expected Results

### After 1 Feedback:
- Total Feedback: 1
- Learned Rules: 1-2
- Accuracy: 100% or 0% (depending on if system was correct)

### After 5 Feedbacks:
- Total Feedback: 5
- Learned Rules: 3-5
- Accuracy: 60-80%
- Visible improvement in detection

### After 10 Feedbacks:
- Total Feedback: 10
- Learned Rules: 5-10
- Accuracy: 70-85%
- Clear patterns in "Most Common Missed Indicators"

---

## 🎯 Success Criteria

✅ **Feedback submission works** - No errors, success message shown
✅ **Learning happens** - Rules created/updated in database
✅ **Rules applied** - Subsequent analysis uses learned rules
✅ **Stats accurate** - Dashboard shows correct metrics
✅ **Rule management works** - Enable/disable functionality works
✅ **Improvement visible** - Re-analyzing same receipt shows better detection

---

## 📝 Test Results Template

```
Date: __________
Tester: __________

Test Scenario 1: False Negative Learning
- Baseline verdict: __________
- After feedback verdict: __________
- Improvement: __________
- Status: ✅ PASS / ❌ FAIL

Test Scenario 2: False Positive Learning
- Baseline verdict: __________
- After feedback verdict: __________
- Improvement: __________
- Status: ✅ PASS / ❌ FAIL

Test Scenario 3: Multiple Feedbacks
- Feedbacks submitted: __________
- Rules learned: __________
- Status: ✅ PASS / ❌ FAIL

Test Scenario 4: Rule Management
- Disable/enable works: __________
- Status: ✅ PASS / ❌ FAIL

Overall Status: ✅ PASS / ❌ FAIL

Issues Found:
1. __________
2. __________

Notes:
__________
```

---

## 🚀 Next Steps After Testing

If tests pass:
1. ✅ Enhance pattern learning (merchants, addresses)
2. ✅ Improve feedback UI (detailed checkboxes)
3. ✅ Add stats dashboard charts
4. ✅ Move to ML fine-tuning (Vision LLM, DONUT)

If tests fail:
1. Document issues
2. Debug and fix
3. Re-test
4. Iterate until passing
