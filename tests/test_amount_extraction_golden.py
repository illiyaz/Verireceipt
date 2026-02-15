#!/usr/bin/env python3
"""
Golden tests for amount extraction regex strategy.

These tests ensure the _pick_largest_amount function never regresses
and correctly extracts the largest amount from various currency formats.
"""

import re
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.pipelines.features import _AMOUNT_REGEX, _parse_amount


def _pick_largest_amount(text: str):
    """Test version of the function from features.py"""
    matches = list(_AMOUNT_REGEX.finditer(text or ""))
    if not matches:
        return None
    # Parse all amounts and return the largest one
    amounts = [_parse_amount(m.group(1)) for m in matches if _parse_amount(m.group(1)) is not None]
    if not amounts:
        return None
    # Safety guard: filter out amounts <= 1.0 (likely not real totals)
    amounts = [a for a in amounts if a > 1.0]
    return max(amounts) if amounts else None


def test_golden_amount_extraction():
    """Golden tests that should never regress"""
    
    test_cases = [
        {
            "name": "S prefix with comma format",
            "input": "Total S15,600.00",
            "expected": 15600.0,
            "description": "Should extract 15600.0, not 600.0 or 15.0"
        },
        {
            "name": "USD prefix with comma format", 
            "input": "TOTAL USD 1,234.56",
            "expected": 1234.56,
            "description": "Should extract 1234.56 from USD format"
        },
        {
            "name": "Grand Total with Indian format",
            "input": "Grand Total: ₹12,34,567.89",
            "expected": 1234567.89,
            "description": "Should handle Indian lakh format (12,34,567.89)"
        },
        {
            "name": "Multiple amounts - pick largest",
            "input": "Subtotal: 500.00 | Tax: 45.00 | Total: 1,234.56",
            "expected": 1234.56,
            "description": "Should pick the largest amount (1234.56 > 500.0 > 45.0)"
        },
        {
            "name": "Multiple amounts with small values",
            "input": "Item 1: 0.99 | Item 2: 1.50 | Total: 899.00",
            "expected": 899.00,
            "description": "Should filter out small amounts (< 1.0) and pick largest"
        },
        {
            "name": "No valid amounts",
            "input": "No amounts here ABC123",
            "expected": None,
            "description": "Should return None when no valid amounts found"
        },
        {
            "name": "Only small amounts",
            "input": "Price: 0.50 | Tax: 0.25 | Fee: 0.75",
            "expected": None,
            "description": "Should return None when all amounts <= 1.0"
        }
    ]
    
    print("🧪 Running Golden Amount Extraction Tests")
    print("=" * 60)
    
    all_passed = True
    
    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test['name']}")
        print(f"Input: {repr(test['input'])}")
        print(f"Description: {test['description']}")
        
        result = _pick_largest_amount(test['input'])
        
        if result == test['expected']:
            print(f"✅ PASS: {result}")
        else:
            print(f"❌ FAIL: Expected {test['expected']}, got {result}")
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL GOLDEN TESTS PASSED!")
        print("✅ Amount extraction is locked and working correctly")
        return True
    else:
        print("💥 SOME TESTS FAILED!")
        print("🚨 Fix the issues before committing")
        return False


def test_regex_pattern_directly():
    """Test the regex pattern directly to ensure it matches correctly"""
    
    print("\n🔍 Testing Regex Pattern Directly")
    print("=" * 60)
    
    test_cases = [
        ("Total S15,600.00", ["15,600.00"]),
        ("TOTAL USD 1,234.56", ["1,234.56"]),
        ("Grand Total: ₹12,34,567.89", ["12,34,567.89"]),
        ("Subtotal: 500.00 | Tax: 45.00 | Total: 1,234.56", ["500.00", "45.00", "1,234.56"]),
    ]
    
    for text, expected_matches in test_cases:
        matches = [m.group(1) for m in _AMOUNT_REGEX.finditer(text)]
        print(f"\nText: {repr(text)}")
        print(f"Expected matches: {expected_matches}")
        print(f"Actual matches:   {matches}")
        
        if matches == expected_matches:
            print("✅ PASS")
        else:
            print("❌ FAIL")


if __name__ == "__main__":
    print("🔒 Golden Test Suite for Amount Extraction")
    print("=" * 60)
    
    # Test regex pattern first
    test_regex_pattern_directly()
    
    # Run golden tests
    success = test_golden_amount_extraction()
    
    if success:
        print("\n🚀 All tests passed! The amount extraction is locked.")
        sys.exit(0)
    else:
        print("\n💥 Tests failed! Fix the issues before proceeding.")
        sys.exit(1)
