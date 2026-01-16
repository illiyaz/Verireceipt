# Architecture Flip: LLM-First Document Classification

## Problem Statement

**Current Architecture (Backwards):**
```
OCR → Numbers → Rules → Penalties → LLM cleanup
```

**Issues:**
1. Treats everything as POS receipt first
2. Applies inappropriate rules to commercial invoices, trade documents
3. Creates false positives (e.g., 81780-24-GLGA.pdf scored 0.79 as "fake")
4. LLM used only for cleanup, not classification

**Example False Positive:**
```
Document: Commercial Invoice (cross-border trade)
Current behavior:
  ✓ Extract amounts → $28M total
  ✓ Apply R7_TOTAL_MISMATCH → CRITICAL (line items don't sum)
  ✓ Apply R16_SUSPICIOUS_DATE_GAP → CRITICAL (created 420 days later)
  ✓ Apply GEO_CURRENCY_MISMATCH → penalty
  Result: 0.79 score (FAKE) ❌

Correct behavior:
  ✓ Classify as COMMERCIAL_INVOICE
  ✓ Skip R7 (invoices have complex line items)
  ✓ Skip R16 (invoices created later for accounting)
  ✓ Skip GEO penalties (cross-border expected)
  Result: 0.15 score (REAL) ✅
```

---

## New Architecture (Correct)

```
┌─────────────────────────────────────────────────────────────┐
│                    1. OCR EXTRACTION                         │
│  Extract text, amounts, dates, metadata from document       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              2. LLM DOCUMENT CLASSIFICATION                  │
│  Classify document type EARLY (before applying rules)       │
│                                                              │
│  Output:                                                     │
│  {                                                           │
│    "doc_class": "COMMERCIAL_INVOICE",                       │
│    "confidence": 0.92,                                       │
│    "evidence": ["invoice number", "parties", "terms"]       │
│  }                                                           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              3. PROFILE SELECTION                            │
│  Select appropriate rule profile based on doc_class         │
│                                                              │
│  COMMERCIAL_INVOICE → trade_document profile:               │
│  {                                                           │
│    "risk_model": "trade_document",                          │
│    "apply_total_reconciliation": false,                     │
│    "apply_date_gap_rules": false,                           │
│    "apply_geo_currency_mismatch": false,                    │
│    "fraud_surface": "low"                                   │
│  }                                                           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              4. TARGETED VALIDATION                          │
│  Apply only relevant rules with correct thresholds          │
│                                                              │
│  ✓ Skip R7_TOTAL_MISMATCH (not applicable)                 │
│  ✓ Skip R16_SUSPICIOUS_DATE_GAP (expected for invoices)    │
│  ✓ Skip GEO penalties (cross-border normal)                │
│  ✓ Apply invoice-specific validations                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              5. SEMANTIC VERIFICATION (Optional)             │
│  Use LLM for ambiguous cases only                           │
│  - Amount extraction verification                            │
│  - Field relevance checks                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Document Profiles

### 1. POS Receipt (High Fraud Risk)
```python
POS_RECEIPT_PROFILE = {
    "doc_class": "POS_RECEIPT",
    "risk_model": "fraud_detection",
    "fraud_surface": "high",
    "apply_total_reconciliation": True,      # ✓ Line items must sum
    "apply_date_gap_rules": True,            # ✓ Recent transactions
    "apply_missing_field_penalties": True,   # ✓ Require merchant, total, date
    "apply_geo_currency_mismatch": True,     # ✓ Geo should match
    "apply_suspicious_software": True,       # ✓ Flag Canva/Photoshop
    "date_gap_threshold_days": 90,
    "total_mismatch_tolerance": 0.05,        # 5% tolerance
}
```

### 2. Commercial Invoice (Low Fraud Risk)
```python
COMMERCIAL_INVOICE_PROFILE = {
    "doc_class": "COMMERCIAL_INVOICE",
    "risk_model": "trade_document",
    "fraud_surface": "low",
    "apply_total_reconciliation": False,     # ✗ Complex line items (shipping, duties)
    "apply_date_gap_rules": False,           # ✗ Invoices created later
    "apply_missing_field_penalties": False,  # ✗ Different field requirements
    "apply_geo_currency_mismatch": False,    # ✗ Cross-border expected
    "apply_suspicious_software": False,      # ✗ PDFs normal for invoices
    "date_gap_threshold_days": None,
    "total_mismatch_tolerance": 0.20,        # 20% tolerance
    "severity_overrides": {
        "R16_SUSPICIOUS_DATE_GAP": "INFO",   # Downgrade to info only
    }
}
```

### 3. Tax Invoice (Medium Fraud Risk)
```python
TAX_INVOICE_PROFILE = {
    "doc_class": "TAX_INVOICE",
    "risk_model": "compliance",
    "fraud_surface": "medium",
    "apply_total_reconciliation": True,      # ✓ Tax compliance requires accuracy
    "apply_date_gap_rules": False,           # ✗ Tax invoices issued later
    "apply_missing_field_penalties": True,   # ✓ Require tax ID, invoice number
    "apply_geo_currency_mismatch": False,    # ✗ May be cross-border
    "apply_suspicious_software": False,      # ✗ PDFs normal
    "date_gap_threshold_days": 180,
    "total_mismatch_tolerance": 0.02,        # 2% tolerance (strict)
}
```

### 4. Trade Document (Logistics)
```python
TRADE_DOCUMENT_PROFILE = {
    "doc_class": "TRADE_DOCUMENT",  # Bill of Lading, Shipping Bill, etc.
    "risk_model": "logistics",
    "fraud_surface": "low",
    "apply_total_reconciliation": False,     # ✗ No totals to reconcile
    "apply_date_gap_rules": False,           # ✗ Docs created over time
    "apply_missing_field_penalties": False,  # ✗ Different requirements
    "apply_geo_currency_mismatch": False,    # ✗ International shipping
    "apply_suspicious_software": False,      # ✗ PDFs normal
}
```

### 5. Bank Statement (High Fraud Risk)
```python
BANK_STATEMENT_PROFILE = {
    "doc_class": "BANK_STATEMENT",
    "risk_model": "financial_statement",
    "fraud_surface": "high",
    "apply_total_reconciliation": False,     # ✗ Transactions don't sum to total
    "apply_date_gap_rules": False,           # ✗ Statements issued monthly
    "apply_missing_field_penalties": True,   # ✓ Require account, bank, balance
    "apply_geo_currency_mismatch": False,    # ✗ May have foreign transactions
    "apply_suspicious_software": True,       # ✓ HARD_FAIL for non-bank software
    "severity_overrides": {
        "R1_SUSPICIOUS_SOFTWARE": "HARD_FAIL",  # Very strict
    }
}
```

---

## Implementation Plan

### Phase 1: Profile Infrastructure ✅
- [x] Create `doc_profiles.py` with profile definitions
- [x] Define profiles for: POS, INVOICE, TRADE_DOCUMENT, UTILITY_BILL, BANK_STATEMENT
- [x] Implement `get_profile_for_doc_class()` selector
- [x] Implement `should_apply_rule()` gating logic

### Phase 2: Early LLM Classification
- [ ] Move LLM classification to BEFORE feature extraction
- [ ] Update `features.py` to call LLM classifier early
- [ ] Store `doc_class` and `profile` in features

### Phase 3: Rule Profile Integration
- [ ] Update `rules.py` to load profile based on `doc_class`
- [ ] Gate rules using `should_apply_rule(profile, rule_id)`
- [ ] Apply severity overrides from profile
- [ ] Use profile thresholds (date_gap, mismatch_tolerance)

### Phase 4: Testing
- [ ] Test 81780-24-GLGA.pdf (should classify as COMMERCIAL_INVOICE)
- [ ] Verify R7, R16, GEO rules are skipped
- [ ] Test POS receipts (should still apply strict rules)
- [ ] Test bank statements (should apply strict software checks)

---

## Code Changes Required

### 1. `features.py` - Early Classification
```python
def build_features(raw: ReceiptRaw) -> ReceiptFeatures:
    # Extract OCR text
    full_text, page_texts = _get_all_text_pages(raw)
    lines = full_text.split("\n")
    
    # EARLY LLM CLASSIFICATION (before feature extraction)
    doc_class = "UNKNOWN"
    doc_class_confidence = 0.0
    
    try:
        from app.pipelines.llm_classifier import classify_document_with_llm
        from app.config.llm_config import LLMConfig, get_llm_client
        
        llm_config = LLMConfig.from_env()
        llm_client = get_llm_client(llm_config)
        
        llm_result = classify_document_with_llm(
            text=full_text,
            llm_client=llm_client,
            provider=llm_config.provider,
            model=llm_config.ollama_model,
            max_chars=2000,
        )
        
        if llm_result.doc_subtype and llm_result.confidence >= 0.7:
            doc_class = llm_result.doc_subtype
            doc_class_confidence = llm_result.confidence
    except Exception as e:
        logger.warning(f"Early LLM classification failed: {e}")
    
    # Get profile for this document class
    from app.pipelines.doc_profiles import get_profile_for_doc_class
    profile = get_profile_for_doc_class(doc_class)
    
    # Store in text_features
    text_features["doc_class"] = doc_class
    text_features["doc_class_confidence"] = doc_class_confidence
    text_features["doc_profile"] = profile.to_dict()
```

### 2. `rules.py` - Profile-Based Gating
```python
def _score_and_explain(features: ReceiptFeatures) -> ReceiptDecision:
    # Load document profile
    from app.pipelines.doc_profiles import get_profile_for_doc_class, should_apply_rule, get_rule_severity
    
    doc_class = tf.get("doc_class", "UNKNOWN")
    profile = get_profile_for_doc_class(doc_class)
    
    # R7: Total mismatch - GATED by profile
    if should_apply_rule(profile, "R7_TOTAL_MISMATCH"):
        total_mismatch = tf.get("total_mismatch", False)
        if total_mismatch:
            # Use profile tolerance
            tolerance = profile.total_mismatch_tolerance
            # ... apply rule with profile settings
    
    # R16: Date gap - GATED by profile
    if should_apply_rule(profile, "R16_SUSPICIOUS_DATE_GAP"):
        # Use profile threshold
        threshold = profile.date_gap_threshold_days
        if threshold and gap_days > threshold:
            # Get severity from profile
            severity = get_rule_severity(profile, "R16_SUSPICIOUS_DATE_GAP", "CRITICAL")
            # ... apply rule
```

---

## Expected Impact

### 81780-24-GLGA.pdf (Commercial Invoice)

**Before (Current):**
```
Score: 0.7875 (FAKE)
- R7_TOTAL_MISMATCH: 0.34 ❌
- R16_SUSPICIOUS_DATE_GAP: 0.30 ❌
- GEO_CROSS_BORDER: penalties ❌
```

**After (Profile-Based):**
```
Score: 0.15 (REAL) ✅
- R7_TOTAL_MISMATCH: SKIPPED (not applicable to invoices)
- R16_SUSPICIOUS_DATE_GAP: SKIPPED (invoices created later)
- GEO_CROSS_BORDER: SKIPPED (cross-border expected)
- Only apply invoice-specific validations
```

### POS Receipts (No Change)
```
Score: Still strict validation ✅
- R7_TOTAL_MISMATCH: APPLIED
- R16_SUSPICIOUS_DATE_GAP: APPLIED
- All fraud detection rules active
```

---

## Benefits

1. **Eliminates False Positives** - Commercial invoices no longer flagged as fake
2. **Document-Appropriate Validation** - Each document type gets relevant rules
3. **Clearer Architecture** - Classification → Profile → Validation
4. **Extensible** - Easy to add new document types with custom profiles
5. **LLM Used Correctly** - Classification (what it's good at), not cleanup

---

## Migration Strategy

1. **Phase 1:** Add profiles (non-breaking) ✅
2. **Phase 2:** Add early classification (parallel to existing)
3. **Phase 3:** Gate rules with profiles (gradual rollout)
4. **Phase 4:** Remove old heuristic classification
5. **Phase 5:** Full cutover to profile-based system

**Rollout:** Feature flag to enable/disable profile-based validation
