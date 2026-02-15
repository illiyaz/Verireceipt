"""
Golden test cases for merchant extraction.

These tests ensure that merchant extraction produces expected results for
a curated set of test cases, preventing regressions.
"""

import pytest
import json
from pathlib import Path
from app.pipelines.features import _guess_merchant_entity


def load_golden_cases():
    """Load golden test cases from JSONL file."""
    golden_path = Path(__file__).parent / "golden" / "merchant_cases.jsonl"
    
    if not golden_path.exists():
        pytest.skip(f"Golden cases file not found: {golden_path}")
    
    cases = []
    with open(golden_path, 'r') as f:
        for line in f:
            cases.append(json.loads(line))
    
    return cases


@pytest.mark.parametrize("case", load_golden_cases(), ids=lambda c: c['doc_id'])
def test_golden_merchant_extraction(case):
    """Test that merchant extraction matches expected value for golden cases."""
    doc_id = case['doc_id']
    ocr_lines = case['ocr_lines']
    expected_merchant = case['expected_merchant']
    
    # Extract merchant
    result = _guess_merchant_entity(ocr_lines)
    
    # Assert merchant matches expected
    assert result.value == expected_merchant, \
        f"Merchant mismatch for {doc_id}: expected '{expected_merchant}', got '{result.value}'"
    
    # Assert confidence bucket is not NONE for receipt-like documents
    # (All golden cases are receipt-like)
    assert result.confidence_bucket != "NONE", \
        f"Confidence bucket is NONE for {doc_id}, expected at least LOW"


def test_golden_cases_exist():
    """Test that golden cases file exists and is not empty."""
    golden_path = Path(__file__).parent / "golden" / "merchant_cases.jsonl"
    
    assert golden_path.exists(), f"Golden cases file not found: {golden_path}"
    
    cases = load_golden_cases()
    assert len(cases) > 0, "Golden cases file is empty"
    assert len(cases) >= 10, f"Expected at least 10 golden cases, found {len(cases)}"


def test_golden_cases_format():
    """Test that golden cases have required fields."""
    cases = load_golden_cases()
    
    required_fields = ['doc_id', 'ocr_lines', 'expected_merchant']
    
    for case in cases:
        for field in required_fields:
            assert field in case, f"Missing required field '{field}' in case {case.get('doc_id', 'unknown')}"
        
        assert isinstance(case['ocr_lines'], list), \
            f"ocr_lines must be a list in case {case['doc_id']}"
        
        assert len(case['ocr_lines']) > 0, \
            f"ocr_lines must not be empty in case {case['doc_id']}"
        
        assert isinstance(case['expected_merchant'], str), \
            f"expected_merchant must be a string in case {case['doc_id']}"
        
        assert len(case['expected_merchant']) > 0, \
            f"expected_merchant must not be empty in case {case['doc_id']}"


def test_golden_cases_deterministic():
    """Test that merchant extraction is deterministic for golden cases."""
    cases = load_golden_cases()
    
    # Run extraction twice for each case and ensure results are identical
    for case in cases[:5]:  # Test first 5 cases for performance
        ocr_lines = case['ocr_lines']
        
        result1 = _guess_merchant_entity(ocr_lines)
        result2 = _guess_merchant_entity(ocr_lines)
        
        assert result1.value == result2.value, \
            f"Non-deterministic extraction for {case['doc_id']}"
        
        assert result1.confidence == result2.confidence, \
            f"Non-deterministic confidence for {case['doc_id']}"
        
        assert result1.confidence_bucket == result2.confidence_bucket, \
            f"Non-deterministic bucket for {case['doc_id']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
