# Address Validation Telemetry

**Purpose:** Learn how often address signals fire in real traffic to tune heuristics and prevent false positives.

> "You don't tune what you can't see."

---

## 🎯 Overview

Lightweight observability for address validation features (V1, V2.1, V2.2). Tracks:

1. **Feature Distribution** - How often each classification/status appears
2. **Gating Rates** - % of docs suppressed due to low confidence
3. **Signal Overlaps** - Combinations like multi-address ∧ mismatch
4. **Address Types** - PO Box vs standard addresses

**Design Philosophy:**
- ✅ Lightweight counters/logs (no dashboards yet)
- ✅ JSON-structured output for easy parsing
- ✅ No performance impact (optional, async-friendly)
- ✅ Privacy-safe (no PII, only aggregates)

---

## 📊 Metrics Tracked

### 1. Address Profile Distribution

**Classification:**
- `address_classification.NOT_AN_ADDRESS` - No valid address detected
- `address_classification.WEAK_ADDRESS` - Weak signals (score 1-3)
- `address_classification.PLAUSIBLE_ADDRESS` - Plausible (score 4-5)
- `address_classification.STRONG_ADDRESS` - Strong (score ≥6)

**Address Type:**
- `address_type.STANDARD` - Standard physical address
- `address_type.PO_BOX` - PO Box address
- `address_type.UNKNOWN` - Type not determined

**Score Ranges:**
- `address_score.none` - Score 0
- `address_score.weak` - Score 1-3
- `address_score.plausible` - Score 4-5
- `address_score.strong` - Score ≥6

**Quality:**
- `address_quality.high` - PLAUSIBLE or STRONG (actionable signals)

---

### 2. Multi-Address Detection

**Status:**
- `multi_address.status.SINGLE` - Single address detected
- `multi_address.status.MULTIPLE` - Multiple distinct addresses
- `multi_address.status.UNKNOWN` - Gated or indeterminate

**Count Distribution:**
- `multi_address.count.zero` - No addresses
- `multi_address.count.single` - 1 address
- `multi_address.count.two` - 2 addresses
- `multi_address.count.three_plus` - ≥3 addresses

**Gating:**
- `multi_address.gated.low_doc_confidence` - Gated due to doc_profile_confidence <0.55

**Detection:**
- `multi_address.detected` - Count of MULTIPLE status

---

### 3. Merchant-Address Consistency

**Status:**
- `consistency.status.CONSISTENT` - Merchant matches address
- `consistency.status.WEAK_MISMATCH` - Weak mismatch
- `consistency.status.MISMATCH` - Strong mismatch
- `consistency.status.UNKNOWN` - Gated or indeterminate

**Score Ranges:**
- `consistency.score.high` - Score ≥0.8
- `consistency.score.medium` - Score 0.5-0.79
- `consistency.score.low` - Score 0.01-0.49
- `consistency.score.zero` - Score 0.0

**Gating:**
- `consistency.gated.low_doc_confidence` - Gated due to doc_profile_confidence <0.55
- `consistency.gated.low_merchant_confidence` - Gated due to merchant_confidence <0.6

**Detection:**
- `consistency.mismatch_detected` - Count of WEAK_MISMATCH or MISMATCH

---

### 4. Signal Overlaps

**Combinations:**
- `multi_and_mismatch` - Multiple addresses + merchant mismatch
- `multi_and_invoice` - Multiple addresses in invoice
- `mismatch_and_invoice` - Merchant mismatch in invoice
- `multi_and_mismatch_and_invoice` - All three signals

**Purpose:** Understand fraud pattern frequency and rule trigger rates.

---

## 🚀 Usage

### Option 1: Global Metrics (Recommended for Production)

Enable via environment variable:

```bash
export ENABLE_ADDRESS_TELEMETRY=true
```

Metrics are automatically recorded during `build_features()` in `features.py`.

**Retrieve Summary:**

```python
from app.telemetry import get_global_metrics

# Get summary after processing N documents
metrics = get_global_metrics()
summary = metrics.get_summary()

# Log to stdout
metrics.log_summary()

# Export to JSON
metrics.export_json("address_metrics_2024-01-16.json")

# Reset for next batch
from app.telemetry import reset_global_metrics
reset_global_metrics()
```

---

### Option 2: Custom Metrics Instance

For testing or batch processing:

```python
from app.telemetry import AddressMetrics

metrics = AddressMetrics()

# Process documents
for doc in documents:
    features = build_features(doc)
    
    # Record manually if ENABLE_ADDRESS_TELEMETRY=false
    metrics.record_address_profile(
        features["address_profile"],
        features["doc_profile_confidence"],
    )
    metrics.record_multi_address(
        features["multi_address_profile"],
        features["doc_profile_confidence"],
    )
    metrics.record_consistency(
        features["merchant_address_consistency"],
        features["merchant_confidence"],
        features["doc_profile_confidence"],
    )
    metrics.record_overlap(
        features["multi_address_profile"]["status"],
        features["merchant_address_consistency"]["status"],
        features["doc_subtype"],
    )

# Get summary
summary = metrics.get_summary()
print(json.dumps(summary, indent=2))
```

---

## 📈 Example Output

```json
{
  "metadata": {
    "start_time": "2024-01-16T10:00:00",
    "end_time": "2024-01-16T12:00:00",
    "doc_count": 1000
  },
  "summary": {
    "high_quality_addresses": {
      "count": 750,
      "percentage": 75.0
    },
    "multi_address_detected": {
      "count": 180,
      "percentage": 18.0
    },
    "mismatch_detected": {
      "count": 120,
      "percentage": 12.0
    },
    "gated_low_doc_confidence": {
      "count": 50,
      "percentage": 5.0
    },
    "gated_low_merchant_confidence": {
      "count": 80,
      "percentage": 8.0
    }
  },
  "counters": {
    "address_classification.STRONG_ADDRESS": {
      "count": 600,
      "percentage": 60.0
    },
    "address_classification.PLAUSIBLE_ADDRESS": {
      "count": 150,
      "percentage": 15.0
    },
    "address_classification.WEAK_ADDRESS": {
      "count": 200,
      "percentage": 20.0
    },
    "address_classification.NOT_AN_ADDRESS": {
      "count": 50,
      "percentage": 5.0
    },
    "address_type.STANDARD": {
      "count": 920,
      "percentage": 92.0
    },
    "address_type.PO_BOX": {
      "count": 80,
      "percentage": 8.0
    },
    "multi_address.status.SINGLE": {
      "count": 770,
      "percentage": 77.0
    },
    "multi_address.status.MULTIPLE": {
      "count": 180,
      "percentage": 18.0
    },
    "multi_address.status.UNKNOWN": {
      "count": 50,
      "percentage": 5.0
    },
    "consistency.status.CONSISTENT": {
      "count": 800,
      "percentage": 80.0
    },
    "consistency.status.WEAK_MISMATCH": {
      "count": 70,
      "percentage": 7.0
    },
    "consistency.status.MISMATCH": {
      "count": 50,
      "percentage": 5.0
    },
    "consistency.status.UNKNOWN": {
      "count": 80,
      "percentage": 8.0
    }
  },
  "overlaps": {
    "multi_and_mismatch": {
      "count": 45,
      "percentage": 4.5
    },
    "multi_and_invoice": {
      "count": 120,
      "percentage": 12.0
    },
    "mismatch_and_invoice": {
      "count": 80,
      "percentage": 8.0
    },
    "multi_and_mismatch_and_invoice": {
      "count": 30,
      "percentage": 3.0
    }
  }
}
```

---

## 🔍 Analysis Questions

Use telemetry to answer:

### 1. Feature Distribution
- **Q:** What % of docs have PLAUSIBLE/STRONG addresses?
- **A:** Check `summary.high_quality_addresses.percentage`
- **Action:** If <50%, address detection may be too conservative

### 2. Multi-Address Frequency
- **Q:** How often do we detect multiple addresses?
- **A:** Check `summary.multi_address_detected.percentage`
- **Action:** If >30%, may be too sensitive; if <5%, may be too conservative

### 3. Gating Rates
- **Q:** What % of docs are gated due to low confidence?
- **A:** Check `summary.gated_low_doc_confidence.percentage`
- **Action:** If >20%, consider lowering threshold or improving doc classification

### 4. Mismatch Frequency
- **Q:** How often do merchant-address mismatches occur?
- **A:** Check `summary.mismatch_detected.percentage`
- **Action:** If >30%, may be too strict; if <5%, may be too lenient

### 5. Fraud Pattern Frequency
- **Q:** How often does multi-address + mismatch occur in invoices?
- **A:** Check `overlaps.multi_and_mismatch_and_invoice.percentage`
- **Action:** If <1%, rule may be too rare to be useful

---

## 🎯 Tuning Guidelines

### Address Classification

**If too many WEAK_ADDRESS:**
- Lower minimum length threshold
- Add more locality keywords
- Reduce scoring strictness

**If too many STRONG_ADDRESS:**
- Increase scoring thresholds
- Add more validation checks
- Tighten classification criteria

### Multi-Address Detection

**If too many MULTIPLE:**
- Increase distinctness threshold
- Require more evidence for separation
- Tighten deduplication logic

**If too few MULTIPLE:**
- Lower distinctness threshold
- Reduce deduplication aggressiveness
- Add more separation signals

### Merchant-Address Consistency

**If too many MISMATCH:**
- Improve merchant extraction
- Add fuzzy matching
- Lower mismatch threshold

**If too few MISMATCH:**
- Tighten consistency scoring
- Add more validation checks
- Increase mismatch sensitivity

---

## 📊 Monitoring Recommendations

### Daily Checks
- High-quality address rate (target: 60-80%)
- Gating rate (target: <10%)
- Multi-address rate (target: 10-20% for B2B)

### Weekly Analysis
- Signal overlap trends
- False positive investigation
- Rule trigger frequency

### Monthly Review
- Threshold tuning based on FP/FN rates
- Heuristic evolution planning
- Golden test updates

---

## 🔒 Privacy & Security

**What We Track:**
- ✅ Aggregated counts and percentages
- ✅ Classification/status distributions
- ✅ Score ranges (no exact scores per doc)
- ✅ Signal overlaps

**What We DON'T Track:**
- ❌ Raw document text
- ❌ Merchant names
- ❌ Addresses
- ❌ User identifiers
- ❌ Any PII

**Data Retention:**
- Metrics are in-memory by default
- Export to JSON for persistence
- No automatic external transmission
- User controls when/where to export

---

## 🚀 Integration with Monitoring Systems

### Prometheus (Future)

```python
from prometheus_client import Counter, Histogram

address_classification_counter = Counter(
    'address_classification_total',
    'Address classification distribution',
    ['classification']
)

multi_address_counter = Counter(
    'multi_address_total',
    'Multi-address detection',
    ['status']
)

# Record metrics
address_classification_counter.labels(
    classification='STRONG_ADDRESS'
).inc()
```

### StatsD (Future)

```python
import statsd

c = statsd.StatsClient('localhost', 8125)

# Increment counters
c.incr('address.classification.strong')
c.incr('address.multi_detected')
c.incr('address.consistency.mismatch')
```

### CloudWatch (Future)

```python
import boto3

cloudwatch = boto3.client('cloudwatch')

cloudwatch.put_metric_data(
    Namespace='VeriReceipt/Address',
    MetricData=[
        {
            'MetricName': 'HighQualityAddressRate',
            'Value': 75.0,
            'Unit': 'Percent',
        },
    ]
)
```

---

## 📚 Related Documentation

- `app/telemetry/address_metrics.py` - Implementation
- `docs/REFERENCE_RULES_ADDRESS.md` - Rule patterns using these metrics
- `ADDRESS_VALIDATION_V1.md` - Feature design and scoring
- `tests/golden/address_cases.json` - Golden test cases

---

## 🎓 Key Insights

**What We Learned:**
- Telemetry is essential for tuning heuristics
- Lightweight counters are sufficient initially
- Privacy-safe aggregates provide actionable insights
- Signal overlaps reveal fraud pattern frequency

**What's Next:**
- Monitor production traffic for 1-2 weeks
- Analyze distributions and overlaps
- Tune thresholds based on FP/FN rates
- Update golden tests with real patterns

---

**Last Updated:** 2024-01-16  
**Version:** 1.0  
**Status:** Production Ready
