# Changelog

All notable changes to VeriReceipt will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

#### Geo Detection False Positives (2026-01-15)
Complete overhaul to eliminate false country detections and ensure canonical data sourcing.

**Key Fixes:**
- **Removed Ambiguous Postal Patterns:** 6-digit patterns for India/Singapore removed from database
- **Multi-Signal Requirement:** India detection now requires ≥2 signals (was: single 6-digit number)
- **Weak Match Confidence Cap:** Weak-only matches capped at 0.25 confidence
- **UNKNOWN Confidence Zeroing:** geo_confidence = 0.0 when geo_country_guess = "UNKNOWN"
- **Fixed UNKNOWN Threshold:** Now checks both top_score < 0.30 AND confidence < 0.30
- **Canonical Data Sourcing:** All diagnostic events use final geo output (not raw/pre-canonical)
- **Improved Audit Messaging:** Clear "No reliable geographic origin detected" for UNKNOWN geo

**Files Modified:**
- `app/geo/bootstrap.py` - Removed 6-digit postal patterns
- `app/geo/infer.py` - Fixed UNKNOWN threshold, zeroed confidence
- `app/pipelines/geo_detection.py` - Removed ambiguous patterns, capped weak confidence
- `app/pipelines/rules.py` - Required ≥2 India signals, prioritized canonical geo
- `app/pipelines/features.py` - Populated doc_profile with canonical geo
- `app/utils/audit_formatter.py` - Improved UNKNOWN geo messaging

**Golden Tests:**
- `tests/golden/geo_false_india_detection.json` - Prevent false India detection
- `tests/golden/geo_true_india_detection.json` - Ensure genuine India receipts detected

**Documentation:**
- `GEO_CANONICAL_FIX.md` - Canonical data sourcing fix
- `GEO_DEFENSIVE_FIX.md` - Defensive data improvements
- `GEO_FIXES_SUMMARY.md` - Complete fix summary
- `GEO_CONFIDENCE_RUBRIC.md` - Scoring rubric and examples

### Added

#### DB-Backed Geo/VAT Logic (2026-01-01)
Complete refactoring of geo/currency/tax validation to use database-backed rules instead of hardcoded values.

**Core Changes:**
- **Database Integration:** All geo/VAT rules now queried from `geo.sqlite` database
- **No Hardcoded Rates:** VAT rates, currencies, and tax regimes come from DB tables
- **Human-Grade Explanations:** Every mismatch references specific DB sources
- **Full Traceability:** Geo profile IDs and VAT rule details in all evidence

**New Database Queries:**
- `query_geo_profile(country_code)` - Fetch country configuration
- `query_vat_rules(country_code)` - Fetch VAT/GST rules with rates
- `query_currency_countries(currency)` - Fetch countries for currency
- `query_doc_expectations(...)` - Fetch document expectations by geo

**Function Changes:**
- `_get_geo_config_from_db()` - Returns raw DB facts (no legacy shaping)
- `_geo_currency_tax_consistency()` - Applies DB logic at rule site
- Added `skip_geo_validation` flag for cross-border/no-geo cases
- Added `geo_penalty_applied` tracking for travel softener

**Evidence Enhancements:**
- Currency mismatch includes: `country_name`, `geo_profile_id`, `db_source`
- VAT mismatch includes: `vat_rules` array with rates and descriptions
- All events clearly indicate DB vs legacy matrix source

**Example Output:**
```
💱 Currency mismatch:
• Country detected: Germany (DE)
• Receipt currency: USD
• Typical currencies: EUR
• Source: Database (geo profile #42)
This inconsistency is uncommon in genuine receipts.

🧾 Tax regime mismatch:
• Country: Germany (DE)
• Tax shown: GST
• Expected tax types: VAT
• Source: Database (3 VAT rule(s))
Such mismatches commonly indicate fabricated receipts.
```

**Benefits:**
- ✅ Add new countries via DB, not code deployment
- ✅ Update VAT rates via DB, not code changes
- ✅ Regional variations handled in database
- ✅ Full audit trail with DB source attribution
- ✅ Graceful fallback to legacy matrix if DB unavailable

**Database Tables:**
- `geo_profiles` - Country configurations with currencies and enforcement tiers
- `vat_rules` - VAT/GST rules with rates and descriptions
- `currency_country_map` - Currency-to-country mappings
- `doc_expectations_by_geo` - Document expectations by geography

## [1.0.0] - 2026-01-01

### 🚨 BREAKING CHANGES - Vision Veto-Only Design

#### Vision System Refactor
Complete redesign of vision LLM integration to enforce strict veto-only behavior.

**Core Changes:**
- **Vision can only veto (reject), never approve**
- **Single canonical function:** `build_vision_assessment()`
- **New contract:** `{visual_integrity, confidence, observable_reasons}`
- **Removed:** `vision_verdict`, `vision_reasoning`, `authenticity_assessment`

#### Field Changes

| Old Field (Removed) | New Field | Type Change |
|---------------------|-----------|-------------|
| `vision_verdict` | `visual_integrity` | "real"/"fake" → "clean"/"suspicious"/"tampered" |
| `vision_reasoning` | N/A | Not exposed (use audit trail) |
| `authenticity_assessment` | N/A | Internal only |
| `authenticity_score` | N/A | No blending |

#### Behavioral Changes

**Vision Output Interpretation:**
- `"clean"` → No effect on decision (rules decide)
- `"suspicious"` → Audit only (rules decide)
- `"tampered"` → HARD_FAIL veto (receipt rejected)

**Corroboration Changes:**
- Vision NO LONGER part of corroboration scoring
- Removed all `VISION_REAL_*` and `VISION_FAKE_*` flags
- Only rules + extraction quality affect corroboration

**Streaming Endpoint:**
- Updated `/analyze/hybrid/stream` to use `build_vision_assessment()`
- Removed vision-based hybrid decisions
- Vision veto applied in rule-based engine only

### Added

#### Rules Engine Improvements (13 Critical Fixes)
Complete overhaul of `app/pipelines/rules.py` for robustness, accuracy, and maintainability.

**Currency Detection Hardening:**
- Fixed duplicate `_currency_hint()` definitions (renamed to `_currency_hint_base()`)
- Hardened short currency prefix detection (rm, rp) with regex word boundaries
- Added case-sensitive HK$ check to prevent false negatives
- Prevents false positives: "frm", "term", "property", "grp"

**Travel/Hospitality Softener:**
- Check travel context upfront (before emission)
- Reduce weights at emission time (not after):
  - Currency mismatch: 0.30 → 0.15 for travel
  - Tax mismatch: 0.18 → 0.10 for travel
- Downgrade severity: CRITICAL → WARNING for travel
- Apply to BOTH currency AND tax mismatches
- Prevents aggressive false positives on cross-border receipts

**Confidence-Based Rule Scaling:**
- Updated `_confidence_factor_from_features()` priority order:
  1. `extraction_confidence_score` (canonical 0-1 field)
  2. `extraction_confidence_level` (canonical "low"/"medium"/"high")
  3. `tf["confidence"]` (legacy field)
  4. Default to 0.70
- Matches `ReceiptDecision` schema preferences
- More accurate confidence-based rule scaling

**Evidence Mutation Prevention:**
- Copy evidence dict upfront in `_emit_event()`
- Changed: `base_evidence = evidence or {}` → `base_evidence = dict(evidence or {})`
- Prevents accidental mutation of caller's dict
- Eliminates subtle mutation bugs

**Code Quality:**
- Removed 12 redundant `import re` statements from helper functions
- Removed duplicate header comment
- Replaced 7 `print()` statements with `logger.debug()`
- Removed unused `_detect_sea_hint()` function
- Fixed `_detect_document_type()` docstring to match behavior

#### Vision Veto System
- **Canonical Function:** `build_vision_assessment()` (lines 493-595 in `vision_llm.py`)
- **Veto Event:** `V1_VISION_TAMPERED` with severity `HARD_FAIL`
- **Observable Reasons:** Structured evidence for tampering detection
- **Audit Trail:** Full vision assessment stored in debug for transparency

#### Comprehensive Enforcement Testing
- **`tests/test_veto_enforcement.py`:** Scans all 91 Python files
- **5 Critical Checks:**
  1. No `vision_verdict` anywhere
  2. No `authenticity_assessment` in production
  3. No vision corroboration flags
  4. No vision upgrade language
  5. Schema fields veto-safe
- **Automated Protection:** Fails CI/CD if violations found

#### Golden Tests
- **`tests/test_vision_veto_golden.py`:** 3 critical scenarios
  1. CLEAN → rules decide (no interference)
  2. SUSPICIOUS → rules decide (audit-only)
  3. TAMPERED → HARD_FAIL (veto triggers)

#### Documentation
- **`docs/VISION_VETO_DESIGN.md`:** Complete design rationale and implementation
- **`docs/API_DOCUMENTATION.md`:** Updated API docs with new fields
- **`docs/MIGRATION_GUIDE.md`:** Step-by-step migration from old system
- **`REAL_RECEIPT_TESTING_GUIDE.md`:** Real-world testing methodology

### Changed

#### Schema Updates (`app/schemas/receipt.py`)
- **Added:** `visual_integrity: Optional[str]` - "clean"|"suspicious"|"tampered"
- **Removed:** `vision_verdict: Optional[str]`
- **Removed:** `vision_reasoning: Optional[str]`
- **Updated:** Corroboration comments (vision not part of corroboration)

#### API Endpoints (`app/api/main.py`)
- **`/analyze/hybrid`:** Uses `build_vision_assessment()`, veto-safe response
- **`/analyze/hybrid/stream`:** Streaming endpoint fixed to be veto-safe
- **Error Fallbacks:** All use veto-safe fields

#### Ensemble Intelligence (`app/pipelines/ensemble.py`)
- **Vision Capture:** Audit-only, no decisioning
- **Removed:** Vision weights and blending logic
- **Removed:** Vision-based reconciliation events
- **Updated:** Module docstring to reflect veto-only design

#### Rules Engine (`app/pipelines/rules.py`)
- **Vision Veto Integration:** Checks `visual_integrity == "tampered"`
- **HARD_FAIL Event:** Emits `V1_VISION_TAMPERED` with observable reasons
- **No Trust Upgrading:** Vision cannot influence "real" decisions

### Removed

#### Deprecated Functions
- ❌ `analyze_receipt_with_vision()` - use `build_vision_assessment()`
- ❌ `get_hybrid_verdict()` - violated veto-only design
- ❌ `run_vision_authenticity()` - probabilistic blending

#### Deprecated Fields
- ❌ `vision_verdict` - replaced with `visual_integrity`
- ❌ `vision_reasoning` - not exposed in responses
- ❌ `authenticity_assessment` - internal structure only
- ❌ `authenticity_score` - no blending weights

#### Corroboration Flags
- ❌ `VISION_REAL_RULES_CRITICAL`
- ❌ `VISION_REAL_LAYOUT_MISSING_TOTAL`
- ❌ `VISION_REAL_RULES_FAKE`
- ❌ `VISION_FAKE_RULES_REAL`

### Fixed

#### Critical Design Violations
- **Trust Upgrading:** Vision can no longer say "real" or approve receipts
- **Probabilistic Blending:** Removed all vision score averaging
- **Inconsistent Decisions:** Single entry point ensures consistency
- **Corroboration Influence:** Vision removed from corroboration logic
- **Streaming Inconsistency:** Streaming and non-streaming now identical

#### Code Quality
- **Repo-Wide Scan:** Enforcement test catches violations in all files
- **No Blind Spots:** Scans all 91 Python files (not just 4 hardcoded)
- **No Bypasses:** Removed broad docstring skip that could hide violations
- **Schema Safety:** Dataclass enforces veto-safe fields

### Migration Guide

**For API Consumers:**
```python
# Before
if response["vision_verdict"] == "real":
    approve()

# After
if response["visual_integrity"] == "clean":
    # Vision found no issues, but rules still decide
    pass
```

**For Developers:**
```python
# Before
from app.pipelines.vision_llm import analyze_receipt_with_vision
vision_results = analyze_receipt_with_vision(image_path)
verdict = vision_results["authenticity_assessment"]["verdict"]

# After
from app.pipelines.vision_llm import build_vision_assessment
vision_assessment = build_vision_assessment(image_path)
visual_integrity = vision_assessment["visual_integrity"]
```

See `docs/MIGRATION_GUIDE.md` for complete migration instructions.

### Testing

**All Tests Passing:**
- ✅ Enforcement tests: 5/5 (scans 91 files)
- ✅ Golden tests: 3/3 (clean/suspicious/tampered)
- ✅ Geo enrichment: 14/14
- ✅ Vision veto (unit): 5/5

**Run Tests:**
```bash
python tests/test_veto_enforcement.py  # Comprehensive enforcement
python tests/test_vision_veto_golden.py  # Functional validation
```

### Benefits

#### 🎯 Design Integrity
- **No False Approvals:** Vision cannot upgrade trust
- **Consistent Behavior:** Single entry point, single contract
- **Auditable:** Clear evidence trail for all vision decisions
- **Safe:** No probabilistic influence on approvals
- **Robust Currency Detection:** Regex word boundaries prevent false positives
- **Evidence Safety:** No mutation bugs from shared dict references

#### 🔒 Security
- **Veto-Only:** Vision can only detect tampering, never approve
- **HARD_FAIL:** Tampering triggers immediate rejection
- **Observable Evidence:** Specific reasons for tampering detection
- **No Bypasses:** Automated enforcement prevents violations

#### 📊 Observability
- **Audit Trail:** Full vision assessment in debug
- **Structured Events:** `V1_VISION_TAMPERED` with evidence
- **Observable Reasons:** Human-readable tampering indicators
- **Debug Info:** Complete vision output for investigation
- **Production Logging:** logger.debug() instead of print() spam

#### 🌍 Global Coverage
- **Travel-Friendly:** Cross-border receipts get WARNING not CRITICAL
- **Currency Accuracy:** Hardened detection for MYR, IDR, HKD
- **Confidence Priority:** Uses canonical extraction_confidence_score first
- **Geo Softening:** Legitimate travel receipts less likely rejected

### Mental Model

```
Vision is a sensor, not a judge.
It can pull the emergency brake, but never press the accelerator.
```

**Allowed:**
- ✅ `tampered` → HARD_FAIL → fake (veto)
- ✅ `suspicious` → audit only (no effect)
- ✅ `clean` → no effect (rules decide)

**Forbidden:**
- ❌ No "real" or "fake" verdicts
- ❌ No trust upgrading
- ❌ No decision blending
- ❌ No corroboration influence

---

**Commit:** `6673c2b` - fix: Comprehensive veto-only enforcement - fix schema and add robust tests  
**Date:** 2026-01-01  
**Contributors:** VeriReceipt Team

---

## [0.9.0] - 2024-12-26

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
