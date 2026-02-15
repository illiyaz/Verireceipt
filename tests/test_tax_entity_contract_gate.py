"""
Phase-7.3 Tax V2 Go/No-Go Gate Tests

These tests verify critical contract guarantees before proceeding to Phase-8.
They enforce:
- No circular imports in ML payload builders
- Entity-local overrides only
- Type contracts (Any/Optional[Any])
- Unified to_ml_dict() contract
- Defensive feature flag construction
- No ml_payload direct assignment outside to_ml_dict()
"""

import pytest
import inspect
from typing import get_type_hints
from app.pipelines.features import (
    build_features,
    _guess_tax_entity,
    _guess_date_entity,
    _guess_currency_entity,
    _guess_merchant_entity,
    EntityCandidate,
    EntityResult,
)
from app.schemas.receipt import ReceiptRaw
from PIL import Image


def create_test_receipt_raw(ocr_text: str) -> ReceiptRaw:
    """Helper to create a minimal ReceiptRaw for testing."""
    dummy_image = Image.new('RGB', (1, 1), color='white')
    
    return ReceiptRaw(
        images=[dummy_image],
        ocr_text_per_page=[ocr_text],
        pdf_metadata={"file_path": "test_receipt.pdf"},
        file_size_bytes=1024,
        num_pages=1
    )


def test_no_ml_payload_direct_assignment_outside_to_ml_dict():
    """
    STATIC CONTRACT CHECK: Ensure no code assigns .ml_payload directly outside to_ml_dict().
    
    This prevents future regressions where entities bypass the unified contract.
    Only EntityResult.to_ml_dict() and entity-specific ML payload builders should assign ml_payload.
    """
    import app.pipelines.features as features_module
    source = inspect.getsource(features_module)
    
    # Find all occurrences of ".ml_payload ="
    lines = source.split('\n')
    ml_payload_assignments = []
    
    for line_num, line in enumerate(lines, 1):
        if '.ml_payload =' in line:
            ml_payload_assignments.append((line_num, line.strip()))
    
    # We expect exactly 4 assignments:
    # 1. In EntityResult.to_ml_dict()
    # 2. In _build_tax_ml_payload()
    # 3. In _build_invoice_id_ml_payload()
    # 4. In _build_payment_method_ml_payload()
    assert len(ml_payload_assignments) == 4, \
        f"Expected exactly 4 ml_payload assignments (in to_ml_dict and entity ML payload builders), " \
        f"found {len(ml_payload_assignments)}: {ml_payload_assignments}"
    
    # Verify they're in the right places
    for line_num, line in ml_payload_assignments:
        # Get surrounding context to verify it's in a valid function
        # Look back up to 50 lines to find function definition
        start = max(0, line_num - 50)
        context = '\n'.join(lines[start:line_num])
        
        # Must be inside either to_ml_dict or _build_*_ml_payload
        valid_context = (
            'def to_ml_dict(' in context or 
            'def _build_tax_ml_payload(' in context or
            'def _build_invoice_id_ml_payload(' in context or
            'def _build_payment_method_ml_payload(' in context
        )
        
        assert valid_context, \
            f"ml_payload assignment at line {line_num} is not inside to_ml_dict() or entity ML payload builder: {line}"


def test_tax_ml_payload_override_has_no_self_import():
    """
    CHECK A: Ensure tax payload build path contains no imports of app.pipelines.features
    and that tax_result.to_ml_dict() executes without recursion.
    """
    lines = ["GST: $25.00"]
    tax_result = _guess_tax_entity(lines)
    
    # Verify to_ml_dict exists and is callable
    assert hasattr(tax_result, "to_ml_dict"), "Tax result must have to_ml_dict method"
    assert callable(tax_result.to_ml_dict), "to_ml_dict must be callable"
    
    # Execute to_ml_dict without recursion
    ml_payload = tax_result.to_ml_dict()
    
    # Verify successful execution
    assert ml_payload is not None, "ML payload must be generated"
    assert isinstance(ml_payload, dict), "ML payload must be a dict"
    assert ml_payload.get("schema_version") == 2, "ML payload must have schema_version = 2"
    
    # Verify no circular import by checking the source code
    # The _build_tax_ml_payload function should not import from app.pipelines.features
    import app.pipelines.features as features_module
    source = inspect.getsource(features_module._build_tax_ml_payload)
    
    # Check that there's no self-import pattern
    assert "from app.pipelines.features import" not in source, \
        "Tax ML payload builder must not import from app.pipelines.features (circular import)"


def test_tax_payload_builder_is_entity_local_override():
    """
    CHECK A: Verify tax result overrides to_ml_dict only for that instance,
    and other entities still use default implementation.
    """
    lines = ["GST: $25.00"]
    tax_result = _guess_tax_entity(lines)
    
    # Get other entity results
    date_result = _guess_date_entity(lines)
    currency_result = _guess_currency_entity(lines)
    merchant_result = _guess_merchant_entity(lines)
    
    # Verify all have to_ml_dict
    assert hasattr(tax_result, "to_ml_dict")
    assert hasattr(date_result, "to_ml_dict")
    assert hasattr(currency_result, "to_ml_dict")
    assert hasattr(merchant_result, "to_ml_dict")
    
    # Verify tax has entity-local override (different implementation)
    # Tax should have a custom to_ml_dict that calls _build_tax_ml_payload
    tax_ml = tax_result.to_ml_dict()
    assert "tax_evidence" in tax_ml, "Tax ML payload must have tax_evidence"
    
    # Verify other entities don't have tax-specific fields
    date_ml = date_result.to_ml_dict()
    currency_ml = currency_result.to_ml_dict()
    merchant_ml = merchant_result.to_ml_dict()
    
    assert "tax_evidence" not in date_ml, "Date ML should not have tax_evidence"
    assert "tax_evidence" not in currency_ml, "Currency ML should not have tax_evidence"
    assert "tax_evidence" not in merchant_ml, "Merchant ML should not have tax_evidence"


def test_entity_value_types_are_any_optional_any():
    """
    CHECK B: Assert type annotations are correct for numeric entities.
    """
    from typing import Any, Optional
    
    # Get type hints for EntityCandidate
    candidate_hints = get_type_hints(EntityCandidate)
    
    # Verify EntityCandidate.value is Any
    assert candidate_hints.get("value") == Any, \
        f"EntityCandidate.value must be Any, got {candidate_hints.get('value')}"
    
    # Get type hints for EntityResult
    result_hints = get_type_hints(EntityResult)
    
    # Verify EntityResult.value is Optional[Any]
    assert result_hints.get("value") == Optional[Any], \
        f"EntityResult.value must be Optional[Any], got {result_hints.get('value')}"
    
    # Verify numeric values work
    tax_candidate = EntityCandidate(
        value=4.5,  # float
        score=1.0,
        source="test",
        line_idx=0,
        raw_line="test",
        norm_line="test"
    )
    assert isinstance(tax_candidate.value, float), "EntityCandidate must accept float values"
    
    tax_result = EntityResult(
        entity="tax",
        value=4.5,  # float
        confidence=1.0,
        confidence_bucket="HIGH"
    )
    assert isinstance(tax_result.value, float), "EntityResult must accept float values"
    
    # Verify string values still work
    merchant_candidate = EntityCandidate(
        value="Acme Corp",  # str
        score=1.0,
        source="test",
        line_idx=0,
        raw_line="test",
        norm_line="test"
    )
    assert isinstance(merchant_candidate.value, str), "EntityCandidate must accept string values"


def test_ml_payload_contract_unified_to_ml_dict():
    """
    CHECK B: Verify unified ML payload contract via to_ml_dict().
    """
    lines = ["GST: $25.00"]
    tax_result = _guess_tax_entity(lines)
    
    # Before to_ml_dict() - ml_payload may or may not be set
    # (it's set during to_ml_dict call in the override)
    
    # Call to_ml_dict()
    ml_payload = tax_result.to_ml_dict()
    
    # After to_ml_dict() - payload must exist
    assert ml_payload is not None, "ML payload must exist after to_ml_dict()"
    assert isinstance(ml_payload, dict), "ML payload must be a dict"
    
    # Verify schema_version at both levels
    assert tax_result.schema_version == 2, "EntityResult.schema_version must be 2"
    assert ml_payload.get("schema_version") == 2, "ML payload schema_version must be 2"
    
    # Verify ml_payload is stored on the result
    assert tax_result.ml_payload is not None, "EntityResult.ml_payload must be set"
    assert tax_result.ml_payload == ml_payload, "Stored ml_payload must match returned payload"


def test_feature_flags_are_defensive_and_non_mutating():
    """
    CHECK C (NEW): Verify feature flags are defensive and don't mutate evidence.
    
    This ensures:
    1. Empty or partial evidence doesn't crash payload generation
    2. Feature flags default to False for missing evidence
    3. Evidence is not mutated during payload build
    """
    # Test 1: Empty evidence
    lines = ["Some random text without tax"]
    tax_result = _guess_tax_entity(lines)
    
    # Should not crash even with no tax found
    ml_payload = tax_result.to_ml_dict()
    assert ml_payload is not None, "ML payload must be generated even with empty evidence"
    
    # Feature flags should exist and be booleans
    feature_flags = ml_payload.get("feature_flags", {})
    assert "is_percentage_based" in feature_flags
    assert "is_amount_based" in feature_flags
    assert "is_inclusive_tax" in feature_flags
    assert "is_explicit_tax" in feature_flags
    
    # All should be booleans
    for flag_name, flag_value in feature_flags.items():
        if flag_name.startswith("is_") or flag_name.startswith("has_") or flag_name.startswith("multi_"):
            assert isinstance(flag_value, bool), f"Feature flag {flag_name} must be boolean, got {type(flag_value)}"
    
    # Test 2: Partial evidence (missing some keys)
    lines = ["GST: $25.00"]
    tax_result = _guess_tax_entity(lines)
    
    # Store original evidence for comparison
    original_evidence = dict(tax_result.evidence)
    original_evidence_id = id(tax_result.evidence)
    
    # Build ML payload
    ml_payload = tax_result.to_ml_dict()
    
    # Verify evidence was not mutated
    assert id(tax_result.evidence) == original_evidence_id, "Evidence dict should not be replaced"
    
    # Verify evidence keys are unchanged (no new keys added)
    for key in original_evidence:
        assert key in tax_result.evidence, f"Evidence key {key} should still exist"
    
    # Verify no evidence keys were added during payload build
    # (evidence should only be read, not written)
    evidence_keys_before = set(original_evidence.keys())
    evidence_keys_after = set(tax_result.evidence.keys())
    assert evidence_keys_before == evidence_keys_after, \
        "Evidence keys should not change during ML payload build"
    
    # Test 3: Missing winner_signals in evidence
    # Create a minimal tax result with incomplete evidence
    minimal_result = EntityResult(
        entity="tax",
        value=10.0,
        confidence=0.5,
        confidence_bucket="MEDIUM",
        evidence={}  # Empty evidence
    )
    minimal_result.schema_version = 2
    
    # Import the payload builder
    from app.pipelines.features import _build_tax_ml_payload
    
    # Should not crash with empty evidence
    try:
        payload = _build_tax_ml_payload(minimal_result)
        assert payload is not None, "Payload should be generated even with empty evidence"
        
        # Feature flags should default to False
        flags = payload.get("feature_flags", {})
        assert flags.get("is_percentage_based") == False
        assert flags.get("is_amount_based") == False
        assert flags.get("multi_tax_detected") == False
        
    except KeyError as e:
        pytest.fail(f"ML payload builder should not crash on missing evidence keys: {e}")
    except Exception as e:
        pytest.fail(f"ML payload builder should handle empty evidence gracefully: {e}")


def test_no_circular_imports_in_date_and_currency():
    """
    CHECK A: Verify date and currency ML payload builders also have no circular imports.
    """
    import app.pipelines.features as features_module
    
    # Check date ML payload builder
    date_source = inspect.getsource(features_module._build_date_ml_payload)
    assert "from app.pipelines.features import" not in date_source, \
        "Date ML payload builder must not import from app.pipelines.features (circular import)"
    
    # Check currency ML payload builder
    currency_source = inspect.getsource(features_module._build_currency_ml_payload)
    assert "from app.pipelines.features import" not in currency_source, \
        "Currency ML payload builder must not import from app.pipelines.features (circular import)"


def test_build_features_uses_unified_contract():
    """
    Verify build_features() calls to_ml_dict() for all entities uniformly.
    """
    raw = create_test_receipt_raw("GST: $25.00\nTotal: $100.00")
    features = build_features(raw)
    
    # Verify tax features are present in output
    text_features = features.text_features
    assert "tax_amount" in text_features
    assert "tax_confidence" in text_features
    assert "tax_confidence_bucket" in text_features
    assert "tax_evidence" in text_features
    
    # Verify tax evidence has expected structure
    tax_evidence = text_features.get("tax_evidence", {})
    assert isinstance(tax_evidence, dict), "Tax evidence must be a dict"
