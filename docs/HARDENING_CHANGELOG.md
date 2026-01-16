# Hardening Changelog

## January 10, 2026 - POS Detection & Field Expectations

### 1. POS Heuristic Upgrade (geo_detection.py)
**Problem:** Keyword-only detection missed valid POS receipts  
**Solution:** Added 6-signal structural detection (≥3 triggers POS_RESTAURANT)

**Signals:**
- Merchant name in ALL CAPS near top
- Currency = INR (₹)
- GST detected (CGST/SGST/IGST)
- Line items with qty × price pattern
- POS words (Bill, Qty, Amount, Total) - need ≥2
- NO invoice-specific blocks (Invoice No, Customer GSTIN)

**Result:** Confidence 0.6-0.85 when triggered, runs before keyword matching

### 2. LLM Gate Lowered (llm_classifier.py)
**Problem:** LLM called too late, missing repair opportunities  
**Solution:** More assertive gating when merchant present

**Logic:**
- With merchant: call LLM at `doc_conf < 0.4`
- Without merchant: call LLM at `doc_conf < 0.6`

**Result:** LLM acts as repair mechanism for ambiguous but structurally valid docs

### 3. Merchant-Present Bias (features.py)
**Problem:** Structurally valid docs collapsed to "unknown"  
**Solution:** +0.08 confidence boost when merchant + currency + line items present

**Result:** Prevents "unknown collapse" for valid transactions

### 4. R9B Downgrade (rules.py)
**Problem:** Valid POS receipts over-penalized for ambiguous language  
**Solution:** Severity downgrade based on structural signals

**Logic:**
- 3 structural signals (merchant + currency + table) → WARNING (weight 0.08)
- 2 structural signals → CRITICAL but 50% weight (0.075)
- Otherwise → CRITICAL (0.15)

**Result:** Reduced false positives on valid POS receipts

### 5. POS Field Expectations (domainpacks/pos_restaurant.yaml)
**Problem:** Generic expectations penalized POS-specific patterns  
**Solution:** Created POS-specific field expectations

**Required:**
- Total amount OR line items (at least one)

**Optional (no penalty):**
- Merchant phone
- Merchant address
- Date or time
- Receipt number

**Never Required (zero weight):**
- Invoice number
- Customer GSTIN
- PO number
- Customer name

**Result:** Learned rules stop overfiring on missing optional fields

### 6. Date Penalty Nuance (rules.py)
**Problem:** Indian POS receipts often have time but OCR misses date  
**Solution:** Downgrade R8_NO_DATE when alternative identifiers present

**Logic:**
- If time OR receipt_number present → WARNING (weight 0.10)
- Otherwise → CRITICAL (weight 0.20)

**Result:** 50% penalty reduction when alternative temporal identifier exists

### 7. Missing Elements Suppression (rules.py)
**Problem:** Learned "missing_elements" pattern penalized valid POS receipts  
**Solution:** Suppress for POS when core fields present

**Logic:**
- If POS subtype AND (total OR line_items) AND merchant AND currency → suppress

**Result:** Learned pattern no longer fires for structurally valid POS receipts

## Test Results (JointAlMandi.pdf)

**Before Hardening:**
- doc_subtype: unknown (confidence 0.0)
- R9B: CRITICAL (weight 0.15)
- R8_NO_DATE: CRITICAL (weight 0.20)
- missing_elements: Applied (+0.15 penalty)

**After Hardening:**
- doc_subtype: POS_RESTAURANT (confidence 0.85) ✅
- R9B: WARNING (weight 0.068) ✅
- R8_NO_DATE: CRITICAL (weight 0.17) - no time/receipt# in this doc
- missing_elements: SUPPRESSED ✅

## Impact Summary

**Precision Improvements:**
- POS detection: keyword-only → 6-signal structural
- LLM gating: fixed threshold → merchant-aware adaptive
- Field expectations: generic → subtype-specific
- Penalty logic: binary → nuanced with context

**False Positive Reduction:**
- R9B downgrade: ~55% weight reduction for valid POS
- missing_elements: suppressed when core fields present
- Date penalty: 50% reduction when time/receipt# present

**Maintainability:**
- POS expectations: centralized in pos_restaurant.yaml
- Subtype-aware logic: extensible to other document types
- Golden tests: prevent regression

## Next Steps (Future)

1. **Expand Golden Tests**
   - Add US POS receipts
   - Add UK POS receipts
   - Add fake POS receipts (Canva, edited)

2. **Additional Subtype Packs**
   - Invoice-specific expectations (require invoice#, customer GSTIN)
   - Logistics-specific expectations (require shipper, consignee)
   - Statement-specific expectations (require period, account#)

3. **OCR Quality Awareness**
   - Thermal print detection (lower expectations)
   - Faded receipt detection (downgrade missing field penalties)
   - Multi-language OCR confidence (adjust gates)

4. **Learned Rule Refinement**
   - Add more subtype-aware suppression rules
   - Track pattern accuracy by document type
   - Auto-tune confidence adjustments based on feedback
