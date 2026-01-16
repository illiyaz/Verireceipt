# ML Justification Thresholds

**Status:** Policy Document  
**Version:** 1.0  
**Last Updated:** 2024-01-16

---

## Purpose

Establish hard thresholds for when ML is justified vs. when rule-based systems are sufficient.

**Problem:** Most teams rush to ML before having the data, labels, or stability to support it.

**Solution:** Clear go/no-go criteria based on data quality, volume, and system maturity.

---

## ❌ Do NOT Use ML If Any of These Are True

| Condition | Why | Alternative |
|-----------|-----|-------------|
| **< 1,000 labeled receipts** | Model variance too high, overfitting guaranteed | Rule-based system with confidence gating |
| **Labels disagree >20%** | Garbage in, garbage out | Fix labeling process first, establish ground truth |
| **Features still changing** | Model retraining every week is unsustainable | Freeze feature set, use SignalRegistry V1 |
| **No A/B testing infrastructure** | Can't measure impact or rollback safely | Build experimentation framework first |
| **Rule precision <60%** | ML won't fix bad features | Improve feature engineering and rules |
| **< 3 months of production data** | Temporal drift unknown, seasonality not captured | Collect more data, monitor distributions |
| **Team size < 2 engineers** | ML maintenance burden too high | Focus on rule quality and observability |
| **No model monitoring** | Silent degradation will happen | Build monitoring dashboards first |

---

## ✅ ML Is Justified When ALL of These Are True

| Requirement | Threshold | Verification |
|-------------|-----------|--------------|
| **Labeled data** | ≥1,000 receipts with consensus labels | Run `test_d_distribution_checks` on labels |
| **Label agreement** | ≥80% inter-annotator agreement | Measure Cohen's kappa or Fleiss' kappa |
| **Feature stability** | SignalRegistry frozen for ≥1 month | No new signals added, no breaking changes |
| **Rule baseline** | Precision ≥60%, Recall ≥40% | Measure on held-out test set |
| **Production data** | ≥3 months of real traffic | Check temporal distribution stability |
| **A/B testing** | Can run controlled experiments | Deploy shadow mode first |
| **Monitoring** | Signal distributions tracked daily | Alerting on drift, gating, trigger rates |
| **Team capacity** | ≥2 engineers dedicated to ML | One for training, one for monitoring |

---

## ML Readiness Checklist

Before starting ML development, complete this checklist:

### Data Readiness

- [ ] **1,000+ labeled receipts** with consensus labels
- [ ] **Label distribution** documented (% fraud, % legitimate, % edge cases)
- [ ] **Inter-annotator agreement** ≥80%
- [ ] **Temporal coverage** ≥3 months of production data
- [ ] **Geographic coverage** across all target markets
- [ ] **Document type coverage** (invoices, receipts, credit notes, etc.)

### Feature Readiness

- [ ] **SignalRegistry frozen** (V1 locked, no breaking changes)
- [ ] **All signals emitted** for all receipts (no missing signals)
- [ ] **Distribution checks** passing (no signals >40% triggered, no signals never triggered)
- [ ] **Combination sanity** validated (expected signal correlations present)
- [ ] **Privacy audit** complete (no PII in signal evidence)

### System Readiness

- [ ] **Rule baseline** established (precision ≥60%, recall ≥40%)
- [ ] **A/B testing framework** deployed
- [ ] **Shadow mode** infrastructure ready
- [ ] **Model monitoring** dashboards built
- [ ] **Alerting** on signal drift, model performance
- [ ] **Rollback plan** documented and tested

### Team Readiness

- [ ] **≥2 engineers** dedicated to ML
- [ ] **On-call rotation** for model monitoring
- [ ] **Incident response** plan for model failures
- [ ] **Retraining pipeline** automated
- [ ] **Model versioning** and experiment tracking

---

## Recommended ML Approach (When Justified)

### Phase 1: Baseline (Weeks 1-2)

**Goal:** Establish rule-based baseline performance.

```python
# Simple logistic regression on signal combinations
features = {
    "addr_multi_and_mismatch": int(
        signals["addr.multi_address"].status == "TRIGGERED" and
        signals["addr.merchant_consistency"].status == "TRIGGERED"
    ),
    "amount_mismatch_conf": signals["amount.total_mismatch"].confidence,
    "date_future": int(signals["date.future"].status == "TRIGGERED"),
}

# Train logistic regression
model = LogisticRegression()
model.fit(X_train, y_train)
```

**Success criteria:**
- Precision ≥70%
- Recall ≥50%
- AUC ≥0.75

### Phase 2: Gradient Boosting (Weeks 3-4)

**Goal:** Improve performance with LightGBM.

```python
# LightGBM with signal interactions
features = {
    # Boolean embeddings
    "addr_multi_triggered": int(signals["addr.multi_address"].status == "TRIGGERED"),
    "addr_multi_conf": signals["addr.multi_address"].confidence,
    
    # Interaction features
    "addr_multi_and_mismatch": int(
        signals["addr.multi_address"].status == "TRIGGERED" and
        signals["addr.merchant_consistency"].status == "TRIGGERED"
    ),
    
    # Confidence-weighted
    "amount_mismatch_weighted": (
        signals["amount.total_mismatch"].confidence
        if signals["amount.total_mismatch"].status == "TRIGGERED"
        else 0
    ),
}

model = lgb.LGBMClassifier(
    max_depth=3,  # Shallow trees for interpretability
    num_leaves=8,
    min_child_samples=50,  # Prevent overfitting
)
```

**Success criteria:**
- Precision ≥75%
- Recall ≥55%
- AUC ≥0.80

### Phase 3: Production Deployment (Weeks 5-6)

**Goal:** Deploy in shadow mode, monitor, iterate.

```python
# Shadow mode: log predictions, don't act on them
prediction = model.predict_proba(features)[0][1]

log_prediction(
    receipt_id=receipt.id,
    fraud_score=prediction,
    signals_used=list(features.keys()),
    model_version="v1.0",
    timestamp=datetime.now(),
)

# Compare to rule-based system
rule_decision = evaluate_rules(receipt)
log_comparison(
    receipt_id=receipt.id,
    ml_decision=prediction > 0.5,
    rule_decision=rule_decision,
)
```

**Success criteria:**
- ML precision ≥ rule precision + 5%
- ML recall ≥ rule recall + 5%
- No silent failures (monitoring catches all issues)

---

## Hard Invariants for Learned Rules

### Minimum Signal Requirement

**Invariant:** A learned rule must **never** fire on a single signal alone.

**Minimum:**
- ≥2 signals OR
- 1 signal + external evidence (user history, risk profile)

**Why:** Single-signal rules are fragile and prone to false positives.

### Example (Correct)

```python
def learned_rule_addr_anomaly_cluster(signals: Dict[str, SignalV1]) -> Dict[str, Any]:
    """Requires ≥2 signals."""
    sig_multi = signals.get("addr.multi_address")
    sig_cons = signals.get("addr.merchant_consistency")
    
    # Both signals must be present and TRIGGERED
    if (sig_multi and sig_multi.status == "TRIGGERED" and
        sig_cons and sig_cons.status == "TRIGGERED"):
        return {"status": "TRIGGERED", "confidence": min(sig_multi.confidence, sig_cons.confidence)}
    
    return {"status": "NOT_TRIGGERED"}
```

### Example (Incorrect)

```python
# ❌ WRONG: Single signal rule
def learned_rule_addr_multi(signals: Dict[str, SignalV1]) -> Dict[str, Any]:
    sig = signals.get("addr.multi_address")
    if sig and sig.status == "TRIGGERED":
        return {"status": "TRIGGERED"}  # Too fragile!
    return {"status": "NOT_TRIGGERED"}
```

---

## When to Stop Using ML

ML is not a one-way door. Stop using ML if:

| Condition | Action |
|-----------|--------|
| **Precision drops <60%** | Revert to rules, investigate feature drift |
| **Model retraining >1x/week** | Features unstable, freeze SignalRegistry |
| **Monitoring alerts >5x/week** | System too fragile, simplify |
| **Team can't maintain** | Reduce to rule-based system |
| **Business value unclear** | Measure impact, consider sunsetting |

---

## Summary

**ML is a tool, not a goal.**

Use ML when:
- You have ≥1,000 labeled receipts
- Features are stable (SignalRegistry frozen)
- Rule baseline is strong (≥60% precision)
- Team can maintain it (≥2 engineers)

Otherwise:
- Focus on rule quality
- Improve feature engineering
- Build monitoring and observability
- Collect more data

**Remember:** Most fraud detection systems succeed with well-engineered rules, not ML.

---

**Last Updated:** 2024-01-16  
**Version:** 1.0  
**Status:** Policy Document
