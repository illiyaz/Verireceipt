# DB-Backed Geo/VAT Logic

## Overview

VeriReceipt's geo/currency/tax validation system has been refactored to use database-backed rules instead of hardcoded values. This enables dynamic updates to VAT rates, currency mappings, and country configurations without code deployment.

## Architecture

### Database Tables

#### 1. `geo_profiles`
Country-level configuration and metadata.

**Schema:**
```sql
CREATE TABLE geo_profiles (
    id INTEGER PRIMARY KEY,
    country_code TEXT NOT NULL,
    country_name TEXT,
    primary_currency TEXT,
    secondary_currencies TEXT,  -- JSON array
    enforcement_tier TEXT,      -- STRICT | RELAXED
    region TEXT,                -- e.g., EU, MENA, APAC
    effective_from TEXT,
    effective_to TEXT
);
```

**Example:**
```json
{
    "id": 42,
    "country_code": "DE",
    "country_name": "Germany",
    "primary_currency": "EUR",
    "secondary_currencies": null,
    "enforcement_tier": "STRICT",
    "region": "EU",
    "effective_from": "2020-01-01",
    "effective_to": null
}
```

#### 2. `vat_rules`
VAT/GST rules with rates and descriptions.

**Schema:**
```sql
CREATE TABLE vat_rules (
    id INTEGER PRIMARY KEY,
    country_code TEXT NOT NULL,
    tax_name TEXT NOT NULL,     -- VAT, GST, HST, PST, etc.
    rate REAL,                  -- e.g., 0.19 for 19%
    description TEXT,
    effective_from TEXT,
    effective_to TEXT
);
```

**Example:**
```json
{
    "id": 123,
    "country_code": "DE",
    "tax_name": "VAT",
    "rate": 0.19,
    "description": "Standard VAT rate in Germany",
    "effective_from": "2020-01-01",
    "effective_to": null
}
```

#### 3. `currency_country_map`
Currency-to-country mappings with weights.

**Schema:**
```sql
CREATE TABLE currency_country_map (
    id INTEGER PRIMARY KEY,
    currency TEXT NOT NULL,
    country_code TEXT NOT NULL,
    is_primary BOOLEAN,
    weight REAL,
    effective_from TEXT,
    effective_to TEXT
);
```

#### 4. `doc_expectations_by_geo`
Document expectations by geography (country/region/global).

**Schema:**
```sql
CREATE TABLE doc_expectations_by_geo (
    id INTEGER PRIMARY KEY,
    geo_scope TEXT NOT NULL,    -- COUNTRY | REGION | GLOBAL
    geo_code TEXT NOT NULL,     -- country code, region name, or *
    doc_family TEXT NOT NULL,   -- TRANSACTIONAL, LOGISTICS, etc.
    doc_subtype TEXT NOT NULL,  -- POS_RESTAURANT, TAX_INVOICE, etc.
    expectations TEXT,          -- JSON with expected fields
    effective_from TEXT,
    effective_to TEXT
);
```

## Query Functions

### `query_geo_profile(country_code: str)`
Fetch active geo profile for a country.

**Returns:**
```python
{
    "id": 42,
    "country_code": "DE",
    "country_name": "Germany",
    "primary_currency": "EUR",
    "secondary_currencies": null,
    "enforcement_tier": "STRICT",
    "region": "EU"
}
```

### `query_vat_rules(country_code: str)`
Fetch active VAT/GST rules for a country.

**Returns:**
```python
[
    {
        "id": 123,
        "country_code": "DE",
        "tax_name": "VAT",
        "rate": 0.19,
        "description": "Standard VAT rate in Germany"
    },
    {
        "id": 124,
        "country_code": "DE",
        "tax_name": "VAT",
        "rate": 0.07,
        "description": "Reduced VAT rate in Germany"
    }
]
```

### `query_currency_countries(currency: str)`
Fetch countries commonly associated with a currency.

**Returns:**
```python
[
    {
        "currency": "EUR",
        "country_code": "DE",
        "is_primary": True,
        "weight": 1.0
    },
    {
        "currency": "EUR",
        "country_code": "FR",
        "is_primary": True,
        "weight": 1.0
    }
]
```

### `query_doc_expectations(...)`
Resolve document expectations with fallback: COUNTRY → REGION → GLOBAL.

**Parameters:**
- `country_code`: Country code (e.g., "DE")
- `region`: Region name (e.g., "EU")
- `doc_family`: Document family (e.g., "TRANSACTIONAL")
- `doc_subtype`: Document subtype (e.g., "POS_RESTAURANT")

**Returns:**
```python
{
    "geo_scope": "COUNTRY",
    "geo_code": "DE",
    "doc_family": "TRANSACTIONAL",
    "doc_subtype": "POS_RESTAURANT",
    "expectations": {...}
}
```

## Rules Engine Integration

### `_get_geo_config_from_db(country_code: str)`

Returns raw DB facts without legacy shaping.

**Returns:**
```python
{
    "db_source": True,
    "geo_profile": {...},
    "vat_rules": [...]
}
```

**Design Philosophy:**
- Returns raw DB facts only
- No interpretation or legacy shaping
- Interpretation happens at rule site
- Clean separation of concerns

### `_geo_currency_tax_consistency()`

Applies DB-backed logic at rule site.

**Flow:**
1. Detect currency and tax regime from receipt text
2. Detect geo candidates (countries)
3. Handle cross-border cases (skip validation if multiple geos)
4. Query DB for geo config
5. Extract expected currencies from geo profile
6. Extract expected tax names from VAT rules
7. Apply currency mismatch logic
8. Apply VAT/tax mismatch logic
9. Emit travel softener if applicable

**Control Flags:**
- `skip_geo_validation`: Skip validation for cross-border or no-geo cases
- `geo_penalty_applied`: Track if any geo penalty was applied (for travel softener)

## Evidence Structure

### Currency Mismatch Event

```python
{
    "rule_id": "GEO_CURRENCY_MISMATCH",
    "severity": "CRITICAL",  # or "WARNING" for travel
    "weight": 0.25,          # or 0.15 for travel
    "message": "Currency inconsistent with country profile (DB-backed)",
    "evidence": {
        "country": "DE",
        "country_name": "Germany",
        "currency_detected": "USD",
        "expected_currencies": ["EUR"],
        "geo_profile_id": 42,
        "db_source": True,
        "travel_softened": False
    }
}
```

### VAT Mismatch Event

```python
{
    "rule_id": "GEO_TAX_MISMATCH",
    "severity": "CRITICAL",  # or "WARNING" for travel
    "weight": 0.18,          # or 0.10 for travel
    "message": "Tax regime inconsistent with country VAT rules (DB-backed)",
    "evidence": {
        "country": "DE",
        "country_name": "Germany",
        "tax_detected": "GST",
        "expected_tax_names": ["VAT"],
        "vat_rules": [
            {
                "tax_name": "VAT",
                "rate": 0.19,
                "description": "Standard VAT rate in Germany"
            },
            {
                "tax_name": "VAT",
                "rate": 0.07,
                "description": "Reduced VAT rate in Germany"
            }
        ],
        "db_source": True,
        "travel_softened": False
    }
}
```

## Fallback Behavior

If DB query fails or returns no data, the system falls back to the legacy `GEO_RULE_MATRIX` hardcoded in `rules.py`.

**Fallback Indicators:**
- `db_source: False` in evidence
- Message includes "(legacy matrix)" instead of "(DB-backed)"
- No `geo_profile_id` or `vat_rules` in evidence

## Human-Grade Explanations

### Currency Mismatch

```
💱 Currency mismatch:
• Country detected: Germany (DE)
• Receipt currency: USD
• Typical currencies: EUR
• Source: Database (geo profile #42)
This inconsistency is uncommon in genuine receipts.
```

### VAT Mismatch

```
🧾 Tax regime mismatch:
• Country: Germany (DE)
• Tax shown: GST
• Expected tax types: VAT
• Source: Database (3 VAT rule(s))
Such mismatches commonly indicate fabricated receipts.
```

## Travel/Hospitality Softener

When travel/hospitality context is detected:
- Severity downgraded: `CRITICAL` → `WARNING`
- Weights reduced:
  - Currency: 0.25 → 0.15
  - Tax: 0.18 → 0.10
- `travel_softened: True` in evidence
- `GEO_TRAVEL_SOFTENER` info event emitted

**Trigger Conditions:**
- Enforcement tier is `STRICT`
- Travel/hospitality keywords detected in receipt text
- Geo penalty was actually applied

## Benefits

### Maintainability
- ✅ Add new countries via DB insert, not code deployment
- ✅ Update VAT rates via DB update, not code changes
- ✅ Regional variations handled in database
- ✅ No code changes needed for geo/VAT updates

### Traceability
- ✅ Every decision references DB source
- ✅ Geo profile ID for full audit trail
- ✅ VAT rule details in evidence
- ✅ Clear DB vs legacy matrix indication

### Explainability
- ✅ Human-readable country names
- ✅ Specific VAT rates and descriptions
- ✅ Source attribution in every message
- ✅ Mechanically generated explanations from DB facts

### Production Safety
- ✅ Graceful fallback to legacy matrix
- ✅ Error logging for DB query failures
- ✅ No breaking changes to existing logic
- ✅ All tests passing with DB integration

## Migration Path

### Phase 1: DB Integration (Complete)
- ✅ Add DB query functions
- ✅ Update rules engine to use DB
- ✅ Maintain legacy matrix as fallback
- ✅ Add DB source attribution

### Phase 2: DB Population (In Progress)
- Populate `geo_profiles` with all supported countries
- Populate `vat_rules` with current VAT rates
- Populate `currency_country_map` with mappings
- Populate `doc_expectations_by_geo` with expectations

### Phase 3: Legacy Deprecation (Future)
- Monitor DB query success rate
- Gradually remove legacy matrix entries
- Eventually deprecate `GEO_RULE_MATRIX` entirely
- Full DB-backed operation

## Testing

### Golden Tests
All existing golden tests pass with DB integration:
- ✅ CLEAN: Vision clean → rules decide
- ✅ SUSPICIOUS: Vision suspicious → rules decide (audit-only)
- ✅ TAMPERED: Vision tampered → HARD_FAIL veto

### DB Integration Tests
- Test DB query functions with mock data
- Test fallback to legacy matrix on DB failure
- Test evidence structure with DB sources
- Test human-grade explanations

## Example Usage

```python
from app.geo.db import query_geo_profile, query_vat_rules

# Query geo profile
geo = query_geo_profile("DE")
# Returns: {"country_code": "DE", "country_name": "Germany", ...}

# Query VAT rules
vat_rules = query_vat_rules("DE")
# Returns: [{"tax_name": "VAT", "rate": 0.19, ...}, ...]

# Rules engine automatically uses these in _geo_currency_tax_consistency()
```

## Database Bootstrap

The database is automatically bootstrapped on first use:

```python
from app.geo.bootstrap import bootstrap_geo_db

# Called automatically by get_connection() if DB doesn't exist
bootstrap_geo_db()
```

## Future Enhancements

1. **Rate History Tracking**: Track VAT rate changes over time
2. **Regional Variations**: Support state/province-level rules
3. **Multi-Rate Support**: Handle multiple VAT rates per country
4. **Dynamic Thresholds**: Store rule weights and thresholds in DB
5. **ML Training Data**: Use DB for training data generation
