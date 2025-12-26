# Changelog

All notable changes to VeriReceipt will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Confidence-Aware Rule Weighting System
- **RuleEvent Schema Enhancement**: Added `raw_weight` field to track original rule weight before confidence scaling
- **Confidence Factor Calculation**: New `_confidence_factor_from_features()` function computes scaling factor [0.6-1.0] based on OCR extraction confidence
- **Smart Rule Scaling**: Soft rules (WARNING, INFO) scaled by confidence; HARD_FAIL rules always use full weight
- **Evidence Tracking**: Each rule event now includes `confidence_factor`, `raw_weight`, and `applied_weight` in evidence dict

#### Enhanced Audit Trail System
- **AuditEvent Identity**: Added `event_id` (UUID) and `ts` (ISO-8601 timestamp) for event traceability
- **Auto-Finalization**: `finalize_defaults()` method auto-populates IDs and timestamps for events and decisions
- **Nested Event Handling**: `ReceiptDecision.finalize_defaults()` now recursively finalizes all nested audit events
- **JSON Serialization**: Enhanced `to_dict()` methods ensure proper JSON serialization of nested dataclasses

#### Extraction Confidence Tracking
- **ReceiptDecision Fields**:
  - `extraction_confidence_score`: Float in [0, 1] representing overall extraction quality
  - `extraction_confidence_level`: String ("low" | "medium" | "high") for human-readable confidence
- **Ensemble Confidence**: Weighted average of merchant (40%), total (40%), and date (20%) confidences
- **Confidence Level Mapping**: Automatic conversion between numeric scores and categorical levels

#### Monetary Extraction Enhancement
- **ReceiptDecision Fields**:
  - `parsed_totals`: List of all candidate totals with confidence scores
  - `normalized_total`: Single best total after normalization and validation
  - `currency`: ISO currency code (USD, EUR, INR, etc.)
- **Amount Normalization**: Enhanced `_normalize_amount_str()` handles multiple currency formats, parentheses for negatives, and common separators

#### Policy Tracking
- **ReceiptDecision Fields**:
  - `policy_name`: Human-friendly policy identifier (e.g., "default", "strict", "lenient")
  - `policy_notes`: Optional annotations about policy application
  - `finalized`: Boolean flag indicating final vs draft decision state

#### Merchant Validation System
- **Label Blacklist**: `_MERCHANT_LABEL_BLACKLIST` filters common OCR label confusion (e.g., "INVOICE", "MERCHANT", "TOTAL")
- **Heuristic Detection**: `_looks_like_label_merchant()` identifies field labels vs actual business names
- **Smart Selection**: `_select_best_merchant_candidate()` prefers non-label-like values with confidence adjustment
- **Confidence Reduction**: Label-like merchants get 15% confidence penalty

#### Vision/Rules Reconciliation
- **Nuanced Conflict Resolution**: High-confidence vision "real" + moderate rule "fake" → human review (not auto-reject)
- **Tunable Thresholds**:
  - `STRONG_RULE_REJECT_SCORE = 0.85`: Auto-reject threshold
  - `MODERATE_RULE_SCORE = 0.70`: Conflict zone threshold
- **Enhanced Reasoning**: More detailed explanations for conflict scenarios

#### Improved Agreement Scoring
- **Value-Level Matching**: Agreement now based on actual value comparison, not just presence
- **Merchant Agreement**: Normalized text comparison with duplicate detection
- **Total Agreement**: Tolerance-based numeric comparison (1% threshold)
- **Date Agreement**: Parsed date comparison for exact matching

### Changed

#### Rule Engine Improvements
- **Total Detection**: New `_has_total_value()` function checks for extracted total even without "TOTAL" keyword
- **False Positive Reduction**: No longer penalize missing "TOTAL" line if `extracted_total` exists from upstream engines
- **Minor Notes**: Added informative note when total extracted but keyword missing (instead of penalty)
- **All Rule Emissions**: Migrated from `_emit_event()` to confidence-aware `emit_event()` wrapper

#### Ensemble Intelligence
- **Confidence Consistency**: Always provides both `confidence_score` and `confidence_level` in converged data
- **Back-Compatibility**: Confidence also exposed under `confidence["overall"]` for legacy code
- **Amount Normalization**: Enhanced to handle INR, USD, EUR, GBP, JPY symbols and currency codes

### Fixed
- **Merchant Extraction**: Reduced false positives from OCR label confusion
- **Low OCR Quality**: Noisy receipts no longer auto-rejected due to confidence scaling
- **Total Line Detection**: Fixed false positives when upstream engines provide total but OCR misses keyword
- **Vision/Rules Conflicts**: Better handling of high-confidence vision vs moderate rule disagreements

### Persistence Layer Updates

#### CSV Logging (`app/utils/logger.py`)
Added columns:
- `policy_name`
- `decision_id`
- `created_at`
- `finalized`
- `policy_notes`
- `extraction_confidence_score`
- `extraction_confidence_level`
- `normalized_total`
- `currency`

#### Database Storage (`app/repository/receipt_store.py`)
Added fields to `Analysis` model:
- `policy_name`
- `decision_id`
- `created_at`
- `finalized`
- `policy_notes`
- `extraction_confidence_score`
- `extraction_confidence_level`
- `normalized_total`
- `currency`

### Documentation
- **New**: `docs/AUDIT_TRAIL_SYSTEM.md` - Comprehensive audit trail system documentation
- **Updated**: `docs/CHANGELOG.md` - This changelog

## Benefits Summary

### 🎯 Accuracy Improvements
- **Reduced False Positives**: Low OCR confidence receipts no longer auto-rejected
- **Better Merchant Extraction**: Filters common OCR label confusion
- **Smarter Total Detection**: Leverages upstream engine extractions

### 📊 Enhanced Observability
- **Full Audit Trail**: Every decision step tracked with provenance
- **Confidence Tracking**: OCR quality visible in audit events
- **Rich Evidence**: Raw vs applied weights preserved for analysis

### 🔄 Better Conflict Resolution
- **Nuanced Reconciliation**: Vision/Rules conflicts handled with context
- **Human Review Escalation**: Ambiguous cases flagged instead of auto-rejected
- **Detailed Reasoning**: Clear explanations for all decision paths

### 🛠️ Developer Experience
- **Auto-Finalization**: IDs and timestamps auto-populated
- **JSON Serialization**: Seamless persistence of complex objects
- **Backward Compatible**: All changes non-breaking

## Migration Guide

### No Breaking Changes
All enhancements are backward compatible. Existing code continues to work without modifications.

### New Field Defaults
- `extraction_confidence_score`: 0.70 (medium confidence)
- `extraction_confidence_level`: "medium"
- `policy_name`: "default"
- `finalized`: True
- `policy_notes`: None
- `normalized_total`: None
- `currency`: None

### Recommended Updates

#### 1. Use Auto-Finalization
```python
# Before
decision = analyze_receipt(file_path)
# Manually set IDs...

# After
decision = analyze_receipt(file_path)
decision.finalize_defaults()  # Auto-populates IDs, timestamps
```

#### 2. Leverage Extraction Confidence
```python
# Check extraction quality
if decision.extraction_confidence_level == "low":
    # Route to human review
    pass
```

#### 3. Use Enhanced Audit Events
```python
# Add custom audit events
event = AuditEvent(
    source="manual_review",
    type="override",
    code="HUMAN_APPROVED",
    message="Verified by compliance team"
)
decision.add_audit_event(event)  # Auto-finalizes
```

## Future Roadmap

### Phase 1: Adaptive Learning (Q1 2025)
- Learn optimal confidence thresholds from feedback
- Auto-adjust rule weights based on false positive rates
- Confidence calibration across engines

### Phase 2: Analytics Dashboard (Q2 2025)
- Visualize audit trails
- Confidence distribution analysis
- Rule performance metrics

### Phase 3: Advanced Reconciliation (Q3 2025)
- Multi-model voting with confidence weighting
- Dynamic threshold adjustment
- Explainable AI integration

---

**Commit**: `61c971a` - feat: Enhanced audit trail with confidence-aware rule weighting and extraction tracking
**Date**: 2024-12-26
**Contributors**: VeriReceipt Team
