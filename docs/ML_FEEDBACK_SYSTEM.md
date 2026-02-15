# ML Feedback & Learning System

**Last Updated:** February 2026  
**Version:** 1.0.0

---

## Overview

VeriReceipt implements a **rule-based local learning system** that adapts fraud detection based on human feedback. When a human reviewer corrects a verdict (e.g., marks a "fake" receipt as actually "real"), the system extracts patterns from that feedback and creates `LearningRule`s that adjust future scoring.

This is **not** a neural network or deep learning system — it uses heuristic pattern extraction and confidence-weighted rule application.

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│              Human Feedback (Web UI)              │
│  review.html → /feedback/submit/structured       │
└─────────────────────┬────────────────────────────┘
                      ▼
┌──────────────────────────────────────────────────┐
│           Feedback Processing Layer               │
│           (app/pipelines/learning.py)             │
│                                                    │
│  • learn_from_false_negative()                    │
│  • learn_from_false_positive()                    │
│  • learn_from_missed_indicators()                 │
│  • reinforce_confirmed_indicators()               │
│  • learn_from_data_corrections()                  │
│                                                    │
│  Output: LearningRule objects                     │
└─────────────────────┬────────────────────────────┘
                      ▼
┌──────────────────────────────────────────────────┐
│           Persistence Layer                        │
│           (app/repository/feedback_store.py)       │
│                                                    │
│  • SQLite (local dev) / PostgreSQL (production)   │
│  • Tables: feedback, learned_rules                │
│  • JSONL export: data/labels/v1/labels.jsonl      │
└─────────────────────┬────────────────────────────┘
                      ▼
┌──────────────────────────────────────────────────┐
│           Rule Application Layer                   │
│           (app/pipelines/rules.py)                 │
│           _apply_learned_rules()                   │
│                                                    │
│  • Pattern matching against text features          │
│  • Confidence-weighted score adjustment            │
│  • Gated by doc_profile and missing_fields flag   │
│  • Capped impact: ±0.05 when dp_conf < 0.55      │
└──────────────────────────────────────────────────┘
```

---

## Data Models

### FeedbackSubmission (Structured)

```python
class StructuredFeedback(BaseModel):
    receipt_id: str                    # Receipt being reviewed
    correct_verdict: str               # "real" | "fake" | "suspicious"
    original_verdict: str              # What the system predicted
    original_score: float              # System's fraud score
    
    # Per-indicator review
    confirmed_indicators: List[str]    # Indicators reviewer agrees with
    rejected_indicators: List[str]     # False positive indicators
    missed_indicators: List[str]       # Indicators system missed
    
    # Data corrections
    corrections: Dict[str, str]        # {"merchant": "Correct Name", ...}
    
    reviewer_notes: Optional[str]
```

### LearningRule

```python
class LearningRule(BaseModel):
    rule_id: str                       # Unique identifier
    rule_type: str                     # "false_negative" | "false_positive" | "missed_indicator" | ...
    pattern: str                       # What to match (e.g., "missing_merchant")
    action: str                        # "increase_weight" | "decrease_weight" | "add_check"
    confidence_adjustment: float       # Score delta (e.g., +0.05 or -0.03)
    learned_from_feedback_count: int   # How many feedbacks reinforced this
    accuracy_on_validation: float      # Self-reported accuracy
    enabled: bool                      # Can be toggled via API
    auto_learned: bool                 # True if system-generated
    created_at: str
    last_updated: str
```

---

## Learning Algorithms

### 1. False Negative Learning

**Trigger:** System said "real" but human says "fake"

```python
def _learn_from_false_negative(feedback, store):
    """
    Extract patterns that the system missed.
    Creates rules to INCREASE suspicion for similar patterns.
    """
    # Extract features from the original analysis
    features = feedback.get("original_features", {})
    
    # For each missed indicator, create/update a rule
    for indicator in feedback.missed_indicators:
        rule = LearningRule(
            rule_type="false_negative",
            pattern=indicator,
            action="increase_weight",
            confidence_adjustment=+0.05,  # Small positive bump
        )
        store.save_learned_rule(rule)
```

### 2. False Positive Learning

**Trigger:** System said "fake" but human says "real"

```python
def _learn_from_false_positive(feedback, store):
    """
    Identify rules that over-triggered.
    Creates rules to DECREASE suspicion for similar patterns.
    """
    for indicator in feedback.rejected_indicators:
        rule = LearningRule(
            rule_type="false_positive",
            pattern=indicator,
            action="decrease_weight",
            confidence_adjustment=-0.03,  # Small negative adjustment
        )
        store.save_learned_rule(rule)
```

### 3. Missed Indicator Learning

**Trigger:** Human identifies fraud signals the system didn't catch

```python
def _learn_from_missed_indicators(feedback, store):
    """
    Learn new patterns from human-identified indicators.
    """
    for indicator in feedback.missed_indicators:
        rule = LearningRule(
            rule_type="missed_indicator",
            pattern=indicator,
            action="add_check",
            confidence_adjustment=+0.04,
        )
        store.save_learned_rule(rule)
```

### 4. Confirmed Indicator Reinforcement

**Trigger:** Human confirms system's fraud indicators were correct

```python
def _reinforce_confirmed_indicators(feedback, store):
    """
    Increase confidence in rules that humans agree with.
    """
    for indicator in feedback.confirmed_indicators:
        existing = store.find_rule_by_pattern(indicator)
        if existing:
            existing.learned_from_feedback_count += 1
            existing.accuracy_on_validation = min(1.0, 
                existing.accuracy_on_validation + 0.02)
            store.save_learned_rule(existing)
```

### 5. Data Correction Learning

**Trigger:** Human corrects extracted data (merchant name, total, etc.)

```python
def _learn_from_data_corrections(feedback, store):
    """
    Learn from corrected data to improve extraction.
    Saved to JSONL for future ML training.
    """
    if feedback.corrections:
        # Save to labels file for supervised training
        save_to_jsonl(feedback, "data/labels/v1/labels.jsonl")
```

---

## Rule Application

### Where Rules Are Applied

In `app/pipelines/rules.py`, the `_apply_learned_rules()` function is called during scoring:

```python
def _apply_learned_rules(
    events, reasons, tf, ff, score,
    missing_fields_enabled, legacy_doc_profile,
    confidence_factor
):
    """Apply learned rules from feedback store."""
    rules = feedback_store.get_learned_rules()
    
    for rule in rules:
        if not rule.enabled:
            continue
            
        if _rule_matches_features(rule, tf, ff):
            adjustment = rule.confidence_adjustment
            
            # Gate: suppress missing_elements rules when gate is OFF
            if "missing_elements" in rule.pattern and not missing_fields_enabled:
                continue  # Suppressed
            
            # Soft-gate: reduce impact for low-confidence docs
            dp_conf = legacy_doc_profile.get("confidence", 0.0)
            if dp_conf < 0.55:
                adjustment *= 0.65  # 35% reduction
                adjustment = max(-0.05, min(0.05, adjustment))  # Hard clamp
            
            score += adjustment
            _emit_event(
                events=events,
                rule_id=f"LEARNED_{rule.rule_id}",
                severity="INFO",
                weight=adjustment,
                message=f"Learned rule applied: {rule.pattern}",
                evidence={
                    "rule_type": rule.rule_type,
                    "feedback_count": rule.learned_from_feedback_count,
                    "accuracy": rule.accuracy_on_validation,
                }
            )
    
    return score
```

### Gating & Safety

| Gate | Condition | Effect |
|------|-----------|--------|
| **Rule Enabled** | `rule.enabled == True` | Skip disabled rules |
| **Pattern Match** | `_rule_matches_features()` | Only apply if relevant |
| **Missing Fields Gate** | `missing_elements` + gate OFF | Suppress rule |
| **Soft Gating** | `dp_conf < 0.55` | 35% reduction + ±0.05 clamp |
| **POS Receipt** | POS subtype detected | Suppress spacing/layout rules |

---

## API Endpoints

### Submit Feedback

```
POST /feedback/submit/structured
Content-Type: application/json

{
    "receipt_id": "abc-123",
    "correct_verdict": "real",
    "original_verdict": "fake",
    "original_score": 0.72,
    "confirmed_indicators": ["R16_SUSPICIOUS_DATE_GAP"],
    "rejected_indicators": ["R9_NO_MERCHANT"],
    "missed_indicators": [],
    "corrections": {"merchant": "Hunan Yusheng"},
    "reviewer_notes": "Merchant was not properly extracted"
}
```

### Get Feedback Stats

```
GET /feedback/stats?days=30

Response:
{
    "total_feedback": 15,
    "accuracy": 82.5,
    "false_positives": 3,
    "false_negatives": 1,
    "real_receipts": 8,
    "fake_receipts": 4,
    "suspicious_receipts": 3,
    "common_missed_indicators": [
        {"indicator": "missing_merchant", "count": 5}
    ]
}
```

### Manage Learned Rules

```
GET  /feedback/learned-rules          # List all rules
POST /feedback/rules/{id}/toggle      # Enable/disable a rule
GET  /feedback/export                 # Export rules as JSON
POST /feedback/import                 # Import rules from JSON
```

---

## Storage

### Database Schema

**feedback table:**
```sql
CREATE TABLE feedback (
    id TEXT PRIMARY KEY,
    receipt_id TEXT NOT NULL,
    correct_verdict TEXT NOT NULL,
    original_verdict TEXT NOT NULL,
    original_score REAL,
    feedback_data TEXT,  -- JSON blob
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**learned_rules table:**
```sql
CREATE TABLE learned_rules (
    rule_id TEXT PRIMARY KEY,
    rule_type TEXT NOT NULL,
    pattern TEXT NOT NULL,
    action TEXT NOT NULL,
    confidence_adjustment REAL DEFAULT 0.0,
    learned_from_feedback_count INTEGER DEFAULT 1,
    accuracy_on_validation REAL DEFAULT 0.5,
    enabled BOOLEAN DEFAULT TRUE,
    auto_learned BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Dual-Mode Persistence

- **Local dev:** SQLite (`data/feedback.db`)
- **Production:** PostgreSQL (via `DATABASE_URL` env var)

Both backends are abstracted by `FeedbackStore` class.

### JSONL Export

Structured feedback is also saved to `data/labels/v1/labels.jsonl` for future supervised ML training:

```jsonl
{"receipt_id": "abc-123", "correct_verdict": "real", "features": {...}, "timestamp": "2026-02-01T..."}
```

---

## Analytics Integration

The unified **Receipt Analysis** section in `web/stats.html` displays:

- **System accuracy** calculated from feedback submissions
- **False positive / negative counts** from `FeedbackStore.get_stats()`
- **Human-corrected verdict breakdown** (confirmed real/suspicious/fake)
- **Learned rules count and status** with enable/disable toggles
- **Common missed indicators** to identify systematic gaps

---

## Key Design Decisions

1. **Heuristic, not ML:** Rules are pattern-matched, not trained neural networks. This ensures explainability and auditability.

2. **Conservative adjustments:** Maximum ±0.05 score impact per learned rule when document confidence is low. Prevents feedback noise from dominating.

3. **Gated application:** Learned rules respect the same gating logic as core rules (missing fields gate, doc profile confidence, etc.).

4. **Human-in-the-loop:** Rules can be toggled on/off via API. Humans maintain control.

5. **JSONL for future ML:** Structured feedback is saved in a format ready for supervised learning when the system matures.

---

## Files Reference

| File | Purpose |
|------|---------|
| `app/api/feedback.py` | API endpoints for feedback submission and rule management |
| `app/pipelines/learning.py` | Core learning logic — pattern extraction from feedback |
| `app/repository/feedback_store.py` | Persistence layer (SQLite/PostgreSQL) |
| `app/models/feedback.py` | Pydantic models for feedback and learned rules |
| `app/pipelines/rules.py` | Rule application in `_apply_learned_rules()` |
| `web/stats.html` | Analytics UI showing feedback metrics and learned rules |
| `web/review.html` | Feedback submission UI with per-indicator review |

---

**Maintained by:** VeriReceipt Team  
**Last Updated:** February 2026
