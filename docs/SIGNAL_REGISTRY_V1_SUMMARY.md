# SignalRegistry V1 - Architecture Freeze Summary

**Status:** ✅ Production Ready  
**Version:** 1.0  
**Date:** 2024-01-16

---

## Overview

SignalRegistry V1 is now **frozen and production-ready**. This document summarizes the hardening work completed to achieve architecture freeze.

---

## What We Built

### 1. Formal SignalSpec Schema

**Before:** Simple set of signal names
```python
ALLOWED_SIGNALS = {"addr.structure", "addr.merchant_consistency", ...}
```

**After:** Rich metadata with formal specification
```python
@dataclass(frozen=True)
class SignalSpec:
    name: str
    domain: str
    version: str
    severity: str  # "weak" | "medium" | "strong"
    gated_by: List[str]
    privacy: str  # "safe" | "derived"
    description: str
```

**Why this matters:**
- **Immutable** - No runtime modification (frozen dataclass)
- **Machine-checkable** - CI enforces all invariants
- **Self-documenting** - Every signal has rich metadata
- **Version-aware** - Future migration support built-in

---

### 2. SignalRegistry with 19 Signals

**Domains (7):**
- **Address** (3): structure, merchant_consistency, multi_address
- **Amount** (3): total_mismatch, missing, semantic_override
- **Template** (2): pdf_producer_suspicious, quality_low
- **Merchant** (2): extraction_weak, confidence_low
- **Date** (3): missing, future, gap_suspicious
- **OCR** (3): confidence_low, text_sparse, language_mismatch
- **Language** (3): detection_low_confidence, script_mismatch, mixed_scripts

**Severity Distribution:**
- **Weak** (11): Low-risk signals, informational
- **Medium** (7): Moderate-risk signals, review recommended
- **Strong** (1): High-risk signals, immediate attention

**Privacy:**
- **All signals are "safe"** - No PII in evidence

---

### 3. CI Enforcement (Hard Fail)

**Location:** `app/pipelines/features.py`

```python
from app.schemas.receipt import SignalRegistry

for name in unified_signals.keys():
    if not SignalRegistry.is_allowed(name):
        raise ValueError(
            f"Unregistered signal emitted: '{name}'. "
            f"Add it to SignalRegistry.SIGNALS"
        )
```

**Why hard fail?**
- This is a **schema violation**, not soft degradation
- CI must fail to prevent corrupted telemetry
- Silent acceptance → broken ML joins + analytics

---

### 4. Comprehensive Test Suite

**31 Tests Passing:**

**Signal Invariants (7 tests):**
- `test_signal_key_matches_name` - Dict key == signal.name
- `test_gated_signals_are_emitted` - GATED ≠ absent
- `test_all_signals_registered` - All signals in registry
- `test_signal_registry_completeness` - 19 signals total
- `test_signal_name_format` - domain.signal_name format
- `test_gated_vs_not_triggered_distinction` - GATED ≠ NOT_TRIGGERED
- `test_signal_dict_key_invariant_in_pipeline` - Pipeline maintains invariant

**Signal Registry (11 tests):**
- `test_signal_registry_count` - Correct count
- `test_all_emitted_signals_are_registered` - Wrappers match registry
- `test_unregistered_signal_fails_validation` - Typos rejected
- `test_registry_contains_all_domains` - All domains present
- `test_registry_domain_counts` - Per-domain counts correct
- `test_no_duplicate_signal_names` - No duplicates
- `test_signal_name_format_in_registry` - Format validation
- `test_boolean_embedding_pattern` - ML pattern 1
- `test_signal_interaction_pattern` - ML pattern 2
- `test_confidence_weighted_pattern` - ML pattern 3
- `test_learned_rule_minimum_signals_invariant` - ≥2 signals required

**CI Enforcement (13 tests):**
- `test_all_registered_signals_have_valid_metadata` - Metadata validation
- `test_signal_domain_prefix_matches_metadata` - Domain prefix consistency
- `test_gated_by_conditions_are_valid` - Valid gating conditions
- `test_severity_distribution_is_balanced` - Balanced severity
- `test_all_signals_are_privacy_safe` - All signals privacy-safe
- `test_registry_immutability` - Frozen dataclass
- `test_get_by_domain_returns_correct_signals` - Domain filtering
- `test_unregistered_signal_detection` - Typo detection
- `test_signal_count_matches_expected` - Count validation
- `test_all_signals_are_v1` - Version consistency
- `test_version_format_is_valid` - Version format
- `test_all_signals_have_descriptions` - Description presence
- `test_descriptions_are_informative` - Description quality

---

### 5. Receipt Intake Testing Checklist

**Location:** `tests/test_receipt_intake_checklist.py`

**Purpose:** Data onboarding discipline (NOT unit testing)

**Checklist (5 sections):**

**A. Document Sanity:**
- OCR text length > minimum threshold
- doc_type & subtype confidence ≥ expected
- Language detected and confidence logged
- Template metadata extracted

**B. Signal Emission Completeness:**
- All registered signals present (even if GATED)
- No unregistered signals emitted
- No missing signals

**C. Confidence Gating Validation:**
- Low-confidence docs → signals GATED, not absent
- No rule fires when required signals GATED
- Gating reasons populated

**D. Distribution Checks (MOST IMPORTANT):**
- % of TRIGGERED per signal
- % of GATED per signal
- Signals that never fire → investigate
- Signals that fire >40% → suspicious heuristic

**E. Combination Sanity:**
- multi_address ∧ merchant_mismatch
- low_ocr ∧ language_mismatch
- template_low_quality ∧ amount_override

**Why this matters:**
> "Most fraud systems fail not due to logic, but due to: 'We never looked at the distributions.'"

---

### 6. ML Justification Thresholds

**Location:** `docs/ML_JUSTIFICATION_THRESHOLDS.md`

**❌ Do NOT Use ML If:**
- < 1,000 labeled receipts
- Labels disagree >20%
- Features still changing
- No A/B testing infrastructure
- Rule precision <60%
- < 3 months of production data
- Team size < 2 engineers
- No model monitoring

**✅ ML Is Justified When ALL True:**
- ≥1,000 labeled receipts with consensus
- ≥80% inter-annotator agreement
- SignalRegistry frozen for ≥1 month
- Rule baseline: precision ≥60%, recall ≥40%
- ≥3 months of production data
- A/B testing infrastructure ready
- Signal distributions monitored daily
- ≥2 engineers dedicated to ML

**Hard Invariant for Learned Rules:**
> A learned rule must **never** fire on a single signal alone.

**Minimum:** ≥2 signals OR 1 signal + external evidence

---

## Invariants Enforced

### Machine-Checkable Invariants

| Invariant | Why It Matters | Enforced By |
|-----------|----------------|-------------|
| `dict_key == signal.name` | Telemetry joins, ML features | Pipeline validation |
| Domain prefix (`addr.*`) | Grouping, dashboards | CI tests |
| Versioned (`v1`) | Future migration | CI tests |
| Known status set | GATED ≠ NOT_TRIGGERED | CI tests |
| Privacy class (`safe`) | Prevents PII leaks | CI tests |
| Severity distribution | Prevents over/under-alerting | CI tests |
| Description quality | Documentation standards | CI tests |

---

## How to Add New Signals

**Step-by-step:**

1. **Create signal wrapper** in `app/signals/`
   ```python
   def signal_new_domain_feature(...) -> SignalV1:
       return SignalV1(
           name="domain.feature",
           status="TRIGGERED",
           confidence=0.9,
           evidence={},
           interpretation="...",
       )
   ```

2. **Add to SignalRegistry** in `app/schemas/receipt.py`
   ```python
   "domain.feature": SignalSpec(
       name="domain.feature",
       domain="domain",
       version="v1",
       severity="medium",
       gated_by=["doc_profile_confidence"],
       privacy="safe",
       description="Detailed description (≥20 chars, informative)",
   ),
   ```

3. **Export in signals package** (`app/signals/__init__.py`)

4. **Update tests** in `tests/test_signal_registry.py`
   - Update expected counts
   - Add to `test_all_emitted_signals_are_registered`

5. **Update documentation** in `docs/UNIFIED_SIGNAL_CONTRACT_V1.md`

6. **Run CI tests** - All must pass before merge

---

## What's Next

### V1 is Frozen - Focus on:

1. **Collect production data** (≥3 months)
2. **Monitor signal distributions** (daily)
3. **Build rule baseline** (precision ≥60%)
4. **Label receipts** (≥1,000 with consensus)
5. **A/B testing infrastructure**
6. **Model monitoring dashboards**

### Do NOT:
- Add new signals without following the checklist
- Change signal names (breaks telemetry)
- Modify signal metadata without CI approval
- Rush to ML before thresholds met

---

## Success Metrics

**Architecture Freeze Achieved:**
- ✅ 19 signals across 7 domains
- ✅ Formal SignalSpec with metadata
- ✅ Immutable registry (frozen dataclass)
- ✅ Hard-fail CI enforcement
- ✅ 31 comprehensive tests passing
- ✅ Receipt intake checklist
- ✅ ML justification thresholds

**Ready to Scale:**
- ✅ Contract enforcement prevents typos
- ✅ Safer refactors (know exactly what exists)
- ✅ ML-feature stability (consistent names)
- ✅ Clean telemetry joins (no orphaned signals)
- ✅ Data onboarding discipline
- ✅ Clear ML go/no-go criteria

---

## Key Insights

**What We Learned:**
- Unified contracts enable composability
- Privacy-safe evidence prevents PII leakage
- Confidence gating prevents false positives
- Hard-fail enforcement catches errors early
- Distribution checks prevent silent bias
- ML requires discipline, not just data

**What's Critical:**
- SignalRegistry is single source of truth
- GATED signals are always emitted (not absent)
- Learned rules require ≥2 signals
- Most fraud systems succeed with rules, not ML
- "We never looked at the distributions" is the #1 failure mode

---

**Last Updated:** 2024-01-16  
**Version:** 1.0  
**Status:** Production Ready - Architecture Frozen

**Next Review:** After 3 months of production data collection
