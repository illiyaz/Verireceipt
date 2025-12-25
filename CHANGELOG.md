# Changelog

All notable changes to VeriReceipt will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

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
