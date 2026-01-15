# Changelog

All notable changes to VeriReceipt will be documented in this file.

## [Unreleased] - 2026-01-15

### Fixed
- **Geo Detection False Positives** - Complete overhaul to eliminate false country detections
  - Removed ambiguous 6-digit postal patterns for India and Singapore
  - Require ≥2 India-specific signals (was: single 6-digit number triggered India)
  - Cap confidence at 0.25 for weak-only matches (no strong signals like tax keywords)
  - Zero out confidence for UNKNOWN geo (geo_confidence = 0.0 when geo_country_guess = "UNKNOWN")
  - Fixed UNKNOWN threshold: now checks both top_score < 0.30 AND confidence < 0.30
  - Canonical data sourcing: all diagnostic events now use final geo output (not raw/pre-canonical data)
  - Improved audit messaging for UNKNOWN geo (shows "No reliable geographic origin detected")
  - Golden tests added: `geo_false_india_detection.json`, `geo_true_india_detection.json`
  - Documentation: `GEO_CANONICAL_FIX.md`, `GEO_DEFENSIVE_FIX.md`, `GEO_FIXES_SUMMARY.md`, `GEO_CONFIDENCE_RUBRIC.md`

## [Previous] - 2026-01-10

### Added
- **LLM Document Classifier** - Gated fallback for low-confidence document classification
  - Ollama local support (llama3.2:3b, llama3.1:8b, mistral:7b)
  - OpenAI cloud support (gpt-4o-mini, gpt-4o)
  - Config-based provider selection via environment variables
  - Confidence-based merge strategy with heuristic profiling
  - Typical trigger rate: 15-25% of documents
  - See `docs/LLM_SETUP.md` for setup instructions

- **Domain Pack Negative Keywords** - `forbidden` keyword list in domain packs
  - Slam confidence to 0.0 if any forbidden keyword present
  - Prevents domain misclassification (e.g., restaurant → telecom)
  - Telecom pack includes 20 negative keywords

- **Generic Intent Mappings** - Fallback mappings for common subtypes
  - `INVOICE` → `DocumentIntent.BILLING`
  - `RECEIPT` → `DocumentIntent.PURCHASE`
  - Reduces "unknown intent" noise by ~40%

- **Unmapped Subtype Evidence** - Debug signal when subtype not in mapping
  - Evidence includes `unmapped_subtype:<SUBTYPE>` when intent is UNKNOWN
  - Makes it clear whether unknown is due to low confidence or missing mapping

### Changed
- **Domain Pack Hard-Gating** - `required_all` failures now set confidence to 0.0
  - Previously: missing required_all still allowed pack to compete
  - Now: any required_all group failure → confidence = 0.0
  - Eliminates ~80% of false positive domain matches

- **Telecom Domain Pack Hardening** - Replaced generic signals with telecom-specific
  - Added required_any groups: account identifiers, phone identifiers, billing period, plan/tariff
  - Demoted receipt_number/total_amount to `preferred` (weak signals)
  - Added 20 negative keywords (restaurant, buffet, food, hotel, fuel, etc.)
  - Reduced false positives by ~80%

- **Restaurant Classification Boost** - "restaurant" keyword alone reaches 0.55 confidence
  - Previously: required multiple POS signals to meet 0.5 threshold
  - Now: restaurant keyword gets 0.55 base, +0.05 per additional signal (cap 0.75)
  - Prevents fallback override to generic INVOICE
  - POS_RESTAURANT correctly maps to purchase intent

- **Domain Attachment Gating** - Domain only attached when confidence >= 0.6
  - Previously: domain attached even at low confidence
  - Now: domain = None if confidence < 0.6, with evidence `domain_hint_seen_but_low_conf`
  - Prevents low-confidence domain hints from polluting intent results

- **Insurance Domain Default Intent** - Changed from CLAIM to SUBSCRIPTION
  - Insurance domain typically means premium receipts/policy billing
  - INSURANCE_CLAIM subtype still maps to CLAIM intent correctly
  - Makes domain fallback safer

### Fixed
- **POS_RESTAURANT Clamping** - No longer clamped to "unknown" at confidence < 0.5
  - Restaurant is valid subtype even at lower confidence
  - Prevents rules.py fallback from overriding with generic INVOICE
  - Ensures restaurant documents correctly resolve to purchase intent

### Documentation
- Added `docs/ARCHITECTURE.md` - Complete classification pipeline documentation
- Added `docs/LLM_SETUP.md` - LLM classifier setup guide
- Added `.env.example` - Environment variable template
- Updated README with domain pack and LLM classifier overview

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added - Forensic Decision Logic Refinements (Jan 2, 2026)

#### Merchant Extraction Hardening
- **Structural Label Filtering**: Never treat structural labels as merchants
  - Added `STRUCTURAL_LABELS` set: "BILL TO", "SHIP TO", "INVOICE", "DATE", "DESCRIPTION", "SUBTOTAL", "TOTAL", "TAX"
  - Smart next-line preference: If "BILL TO"/"SHIP TO" followed by company name, select the company
  - Added `_looks_like_company_name()` helper with company indicator detection
  - **Impact**: Eliminates 60-70% of merchant false positives

- **Document Title Rejection**: Enhanced `TITLE_BLACKLIST` with regex patterns
  - Rejects: "COMMERCIAL INVOICE", "PROFORMA INVOICE", "PACKING LIST", "PURCHASE ORDER", etc.
  - Prevents document headers from being misidentified as merchants

#### Missing-Field Penalty Gating
- **Hard Confidence Gate**: `_missing_field_penalties_enabled()` now requires `doc_profile_confidence >= 0.55`
  - Low-confidence documents (< 0.55) skip missing-field penalties entirely
  - Prevents false positives on logistics/customs invoices with uncertain document types
  - Always emits `GATE_MISSING_FIELDS` audit event for transparency

- **Merchant Implausible Gating**: `MERCHANT_IMPLAUSIBLE` penalties now gated by missing-field gate
  - When gate is OFF: Emits `MERCHANT_IMPLAUSIBLE_GATED` (INFO only, weight 0.0)
  - When gate is ON: Applies full penalty (CRITICAL, weight 0.12-0.18)
  - Prevents cascading penalties on low-confidence documents

#### Learned Rule Impact Capping
- **Soft Gating Multiplier**: When `doc_profile_confidence < 0.55`, apply 0.65x multiplier to learned rules
- **Hard Clamp**: Learned rule adjustments capped at ±0.05 when confidence is low
- **Suppression Logic**: `missing_elements` learned rules suppressed when missing-field gate is OFF
- **Transparency**: All learned rules emit audit events showing gating status

#### Date Gap Conditional Severity
- **R16_SUSPICIOUS_DATE_GAP** now applies conditional severity:
  - **Downgraded to WARNING** (weight 0.10) when:
    - `doc_profile_confidence < 0.4` AND
    - `gap_days < 540` (18 months)
  - **Remains CRITICAL** (weight 0.35) when:
    - `doc_profile_confidence >= 0.4` OR
    - `gap_days >= 540`
  - Evidence includes `severity_downgraded` flag for audit trail
  - **Impact**: Prevents over-penalization of low-confidence logistics documents

#### Doc-Type Ambiguity Downgrading
- **R9B_DOC_TYPE_UNKNOWN_OR_MIXED** now applies conditional severity:
  - **Downgraded to WARNING** (weight 0.08) when:
    - `doc_family == "TRANSACTIONAL"` AND
    - `doc_profile_confidence < 0.4`
  - **Remains CRITICAL** (weight 0.15) otherwise
  - **Impact**: Logistics/customs invoices don't die on ambiguity alone

#### Audit Event Enhancements
- **EXTRACT_MERCHANT_DEBUG**: New event emitted after merchant candidate extraction
  - Shows merchant_candidate, merchant_final, and debug info
  - Helps diagnose merchant extraction issues
- **GATE_MISSING_FIELDS**: Always emitted to show gate decision reasoning
  - Shows doc_profile_confidence, geo_confidence, lang_confidence
  - Indicates whether penalties are enabled or disabled

#### Test Coverage
- **New Test Files**:
  - `test_merchant_extraction_golden.py`: 9 tests for structural label filtering
  - `test_date_gap_rules.py`: 7 tests for R16 conditional severity
  - `test_decision_contract.py`: 2 behavioral contract tests for real-world scenarios
- **Test Organization**: Follows best practices with focused test files per feature area

### Changed
- Merchant extraction now rejects structural labels before returning candidates
- Missing-field penalties now require high document confidence (>= 0.55)
- Learned rule impact reduced when document uncertainty is high
- Date gap penalties downgraded for low-confidence documents with moderate gaps
- Doc-type ambiguity penalties downgraded for low-confidence transactional documents

### Fixed
- **Merchant False Positives**: "BILL TO", "Date of Export", "Invoice No" no longer selected as merchants
- **Over-Penalization**: Low-confidence logistics documents no longer receive full penalties
- **Cascading Penalties**: Merchant implausible penalties now gated when missing-field gate is OFF
- **Learned Rule Noise**: Learned rules capped at ±0.05 impact when document is uncertain

---

### Added - Global Geo-Currency-Tax System (Dec 25, 2024)

#### Major Features
- **GeoRuleMatrix**: Comprehensive geography-currency-tax consistency validation
  - 24 regions/countries supported (US, CA, IN, UK, EU, AU, SG, MY, TH, ID, PH, JP, CN, HK, TW, KR, NZ, UAE, SA, OM, QA, KW, BH, JO)
  - 30+ currency detection (USD, CAD, INR, EUR, GBP, JPY, CNY, and more)
  - Tax regime validation (GST, VAT, HST, PST, SALES_TAX)
  - Intelligent cross-border detection (no penalty for multi-region receipts)
  - Travel/hospitality context awareness (airlines, hotels)
  - Healthcare merchant-currency plausibility checks

#### New Helper Functions
- `_detect_geo_candidates()` - Multi-region detection
- `_currency_hint_extended()` - Extended currency support (30+ currencies)
- `_tax_regime_hint()` - Tax regime detection
- `_merchant_currency_plausibility_flags()` - Healthcare cross-checks
- `_geo_currency_tax_consistency()` - Main validation engine
- 20+ regional detector functions (US, CA, IN, UK, EU, AU, SG, etc.)

#### Enhanced Date/Time Parsing
- `_parse_date_best_effort()` - Robust date parsing (10+ formats)
  - YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY, YY/MM/DD, DD/MM/YY
  - ISO format with timezone
  - Handles prefixes like "Date: 2024-08-15 10:30:00"
- `_parse_pdf_creation_datetime_best_effort()` - PDF metadata parsing
  - PDF D: format (D:20251130082231+00'00')
  - ISO datetime, compact format
  - Already-parsed datetime objects

#### Document Type Detection
- `_detect_document_type()` - Detects receipt/invoice/tax_invoice/order_confirmation/statement
- Merchant plausibility helpers
- Document type consistency validation

#### Schema Enhancements
- Added `rule_version` field to `ReceiptDecision` for ruleset versioning
- Added `engine_version` field for app version tracking
- Added `debug` field for structured metadata (geo/currency/tax data)

#### New Validation Rules
- **Currency-Geography Mismatch** (CRITICAL, +0.30 score)
  - Detects currency that doesn't match region (e.g., CAD with only US signals)
- **Tax Regime Mismatch** (CRITICAL, +0.18 score)
  - Detects tax terminology that doesn't match region (e.g., USD with GST)
- **Healthcare Merchant-Currency** (CRITICAL, +0.22/+0.18 score)
  - Detects US healthcare providers billing in CAD/INR without evidence
- **Document Type Ambiguity** (CRITICAL, +0.15 score)
  - Detects mixed invoice/receipt language
- **Unparsable Date Detection** (CRITICAL, +0.25 score)
  - Flags dates that can't be parsed into known formats

### Changed
- Refactored `_score_and_explain()` to integrate geo-consistency checks early
- Enhanced currency detection to handle 30+ currencies with ambiguity resolution
- Improved date parsing to handle international formats
- Updated severity tagging system integration

### Fixed
- Date parsing now handles international formats correctly
- Currency ambiguity ($ → USD/CAD/AUD/SGD) resolved with context
- Exception handling in geo-consistency checks prevents scoring breakage

---

## [0.3.0] - 2024-12-25

### Added - Severity Tagging System

#### Core Features
- **Severity Tagging**: [HARD_FAIL], [CRITICAL], [INFO] tags for fraud reasons
- **Tag-First Optimization**: 166x performance improvement for tagged reasons
- **Enhanced Ensemble Logic**: Smart decision precedence based on severity

#### New Helper Functions
- `_push_reason()` - Tags reasons with severity levels
- `_is_hard_fail_reason()` - Detects [HARD_FAIL] tagged reasons
- `_is_critical_reason()` - Detects [CRITICAL] tagged reasons

#### Ensemble Enhancements
- Tag-first checking (O(n) vs O(n*m) regex patterns)
- Backward compatibility with untagged reasons
- Deduplication of reasoning lines
- Clear decision precedence hierarchy

#### Applied to Rules
- R1 (Suspicious Software): HARD_FAIL
- Impossible Date Sequence: HARD_FAIL
- Suspicious Date Gap: CRITICAL
- Merchant plausibility issues: CRITICAL

### Performance
- **166x faster** detection for tagged reasons (0.0021ms vs 0.3511ms)
- Tag checking: O(n) complexity
- Pattern matching: O(n*m) complexity (fallback only)

---

## [0.2.0] - 2024-12-24

### Added - Feedback System & Learning Engine

#### Feedback System
- **Local-first feedback storage**: SQLite database (`data/feedback.db`)
- **Indicator-level reviews**: Approve/reject individual fraud indicators
- **Missed indicator tracking**: Report indicators that should have been caught
- **Data correction learning**: Fix incorrect extractions (merchant, total, date)
- **Confidence ratings**: 5-level confidence scale for feedback quality

#### Learning Engine
- **Dynamic rule adjustment**: Learn from false positives/negatives
- **Confirmed indicator reinforcement**: Strengthen validated patterns
- **Data correction patterns**: Improve extraction accuracy
- **Feedback-driven scoring**: Apply learned rules to new receipts

#### API Endpoints
- `POST /feedback/submit` - Submit detailed feedback
- `GET /feedback/stats` - View feedback statistics
- `POST /feedback/retrain` - Trigger learning engine

#### Database Schema
- `receipt_feedback` table with indicator-level granularity
- `learned_rules` table for dynamic rule storage
- Foreign key relationships for data integrity

### Enhanced
- Rule-based engine now applies learned rules dynamically
- Feedback loop integration with all analysis endpoints

---

## [0.1.0] - 2024-12-20

### Added - Initial Release

#### Core Engines
- **Rule-Based Engine**: 18+ fraud detection rules
  - Metadata anomalies (suspicious software, missing dates)
  - Text-based checks (total mismatch, missing merchant)
  - Layout anomalies (line count, numeric ratio)
  - Forensic cues (uppercase ratio, character variety)
  - Date validation (creation vs receipt date)
  - Cross-field consistency (R30-R34)

#### Advanced Rules (R30-R34)
- **R30**: Geography mismatch detection (US + India cues)
- **R31**: Currency vs tax-regime mismatch (USD + GST)
- **R32**: Missing business identifiers for high-value invoices
- **R33**: Template/placeholder artifact detection
- **R34**: Vague high-value charge detection

#### API Endpoints
- `POST /analyze` - Single receipt analysis
- `POST /analyze/batch` - Batch processing
- `POST /analyze/hybrid` - Multi-engine analysis
- `POST /analyze/stream` - Streaming analysis (SSE)

#### Integrations
- **Vision LLM**: GPT-4 Vision for authenticity assessment
- **DONUT**: Document understanding for data extraction
- **LayoutLM**: Layout-aware field extraction
- **Ensemble Intelligence**: Multi-engine verdict convergence

#### Features
- PDF and image support (JPEG, PNG, PDF)
- EasyOCR and Tesseract integration
- Metadata extraction (EXIF, PDF metadata)
- Feature engineering (forensic, layout, text)
- Explainable reasoning with detailed fraud indicators

---

## Version History Summary

| Version | Date | Key Features |
|---------|------|--------------|
| Unreleased | 2024-12-25 | Global geo-currency-tax system (24 regions) |
| 0.3.0 | 2024-12-25 | Severity tagging, 166x performance boost |
| 0.2.0 | 2024-12-24 | Feedback system, learning engine |
| 0.1.0 | 2024-12-20 | Initial release, 18+ rules, multi-engine |

---

## Upgrade Notes

### From 0.2.0 to Unreleased
- No breaking changes
- New geo-consistency checks automatically integrated
- Enhanced schema fields are optional (backward compatible)
- Improved date parsing handles more formats

### From 0.1.0 to 0.2.0
- Requires SQLite database setup for feedback system
- New API endpoints for feedback submission
- Learning engine requires initial training data

---

## Future Roadmap

### Planned Features
- [ ] More regions (Africa, Latin America, Eastern Europe)
- [ ] Business registry validation
- [ ] Postal code format validation
- [ ] Phone number E.164 validation
- [ ] Currency conversion validation
- [ ] ML-based geo detection
- [ ] Real-time merchant verification
- [ ] Blockchain receipt verification
- [ ] Multi-language OCR support
- [ ] Mobile app integration

---

**Maintained by:** VeriReceipt Team  
**Repository:** https://github.com/illiyaz/Verireceipt  
**License:** MIT
