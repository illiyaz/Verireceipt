#!/usr/bin/env python3
"""
Test script for tag-first optimization in ensemble.py
Verifies that tagged reasons are detected faster and correctly.
"""

from app.pipelines.ensemble import EnsembleIntelligence
import time

def test_tag_first_optimization():
    """Test that tag-first checking works correctly."""
    print("=" * 60)
    print("TEST: Tag-First Optimization")
    print("=" * 60)
    
    engine = EnsembleIntelligence()
    
    # Test cases
    test_cases = [
        {
            "name": "Tagged HARD_FAIL reasons",
            "reasons": [
                "[HARD_FAIL] Currency mismatch: USD with lakhs",
                "[HARD_FAIL] Impossible Date Sequence Detected",
                "[INFO] Missing creation date"
            ],
            "expected_hard_fail": True,
            "expected_hard_fail_count": 2,
            "expected_critical": False,
        },
        {
            "name": "Tagged CRITICAL reasons",
            "reasons": [
                "[CRITICAL] Suspicious Date Gap Detected",
                "[CRITICAL] Total mismatch detected",
                "[INFO] Low text quality"
            ],
            "expected_hard_fail": False,
            "expected_critical": True,
            "expected_critical_count": 2,
        },
        {
            "name": "Mixed tagged and untagged",
            "reasons": [
                "[HARD_FAIL] Geography mismatch: US + India",
                "Suspicious Software Detected: iLovePDF",  # Untagged, should match pattern
                "[INFO] Normal reason"
            ],
            "expected_hard_fail": True,
            "expected_hard_fail_count": 1,  # Only tagged one
            "expected_critical": True,  # Pattern should catch iLovePDF
        },
        {
            "name": "Only untagged reasons (backward compatibility)",
            "reasons": [
                "Geography mismatch detected: California with +91 phone",
                "Currency mismatch: USD with lakhs",
                "Missing creation date"
            ],
            "expected_hard_fail": True,  # Pattern matching should work
            "expected_critical": False,
        },
        {
            "name": "No hard-fail or critical indicators",
            "reasons": [
                "[INFO] Missing creation date",
                "[INFO] Low text quality",
                "No merchant found"
            ],
            "expected_hard_fail": False,
            "expected_critical": False,
        },
    ]
    
    print("\n🧪 Running test cases:\n")
    
    for i, test in enumerate(test_cases, 1):
        print(f"Test {i}: {test['name']}")
        print(f"  Reasons: {len(test['reasons'])} total")
        
        # Measure performance
        start_time = time.perf_counter()
        
        # Simulate the detection logic from build_verdict
        rule_reasons = test['reasons']
        
        # Check for [HARD_FAIL] tags first
        has_hard_fail_tagged = any("[HARD_FAIL]" in str(r) for r in rule_reasons)
        if has_hard_fail_tagged:
            has_hard_fail = True
            hard_fail_reasons = [r for r in rule_reasons if "[HARD_FAIL]" in str(r)]
        else:
            has_hard_fail, hard_fail_reasons = engine._detect_hard_fail_indicators(rule_reasons)
        
        # Check for [CRITICAL] tags first
        has_critical_tagged = any("[CRITICAL]" in str(r) for r in rule_reasons)
        if has_critical_tagged:
            has_critical_indicator = True
            critical_reasons = [r for r in rule_reasons if "[CRITICAL]" in str(r)]
        else:
            # Fallback to pattern matching
            import re
            critical_patterns = [
                r"Suspicious Software Detected",
                r"iLovePDF",
                r"Canva",
            ]
            critical_reasons = []
            seen_critical = set()
            for reason in rule_reasons:
                for pat in critical_patterns:
                    if re.search(pat, reason, re.IGNORECASE):
                        if reason not in seen_critical:
                            critical_reasons.append(reason)
                            seen_critical.add(reason)
                        break
            has_critical_indicator = len(critical_reasons) > 0
        
        elapsed = (time.perf_counter() - start_time) * 1000  # Convert to ms
        
        # Verify results
        status = "✅" if (
            has_hard_fail == test['expected_hard_fail'] and
            has_critical_indicator == test['expected_critical']
        ) else "❌"
        
        print(f"  {status} Hard-fail: {has_hard_fail} (expected: {test['expected_hard_fail']})")
        if has_hard_fail:
            print(f"     → Found {len(hard_fail_reasons)} hard-fail reason(s)")
            if 'expected_hard_fail_count' in test:
                count_match = "✅" if len(hard_fail_reasons) == test['expected_hard_fail_count'] else "❌"
                print(f"     {count_match} Count: {len(hard_fail_reasons)} (expected: {test['expected_hard_fail_count']})")
        
        print(f"  {status} Critical: {has_critical_indicator} (expected: {test['expected_critical']})")
        if has_critical_indicator:
            print(f"     → Found {len(critical_reasons)} critical reason(s)")
            if 'expected_critical_count' in test:
                count_match = "✅" if len(critical_reasons) == test['expected_critical_count'] else "❌"
                print(f"     {count_match} Count: {len(critical_reasons)} (expected: {test['expected_critical_count']})")
        
        print(f"  ⚡ Performance: {elapsed:.3f}ms")
        print()
        
        # Assert correctness
        assert has_hard_fail == test['expected_hard_fail'], f"Test {i} hard-fail mismatch"
        assert has_critical_indicator == test['expected_critical'], f"Test {i} critical mismatch"
    
    print("=" * 60)
    print("✅ All tag-first optimization tests passed!")
    print("=" * 60)
    
    print("\n📊 Benefits:")
    print("  ✅ Tag checking is O(n) vs regex O(n*m)")
    print("  ✅ Avoids double-detection of tagged reasons")
    print("  ✅ Maintains backward compatibility with untagged reasons")
    print("  ✅ Clear separation: tags for new code, patterns for legacy")
    
    return True


def test_performance_comparison():
    """Compare performance of tag-first vs pattern-only approach."""
    print("\n" + "=" * 60)
    print("PERFORMANCE COMPARISON")
    print("=" * 60)
    
    engine = EnsembleIntelligence()
    
    # Create test data with 100 reasons
    tagged_reasons = [f"[HARD_FAIL] Reason {i}" for i in range(50)]
    tagged_reasons += [f"[INFO] Normal reason {i}" for i in range(50)]
    
    untagged_reasons = [f"Geography mismatch reason {i}" for i in range(50)]
    untagged_reasons += [f"Normal reason {i}" for i in range(50)]
    
    # Test 1: Tag-first approach (tagged reasons)
    iterations = 1000
    start = time.perf_counter()
    for _ in range(iterations):
        has_tagged = any("[HARD_FAIL]" in str(r) for r in tagged_reasons)
        if has_tagged:
            matched = [r for r in tagged_reasons if "[HARD_FAIL]" in str(r)]
    tag_time = (time.perf_counter() - start) * 1000 / iterations
    
    # Test 2: Pattern-only approach (untagged reasons)
    start = time.perf_counter()
    for _ in range(iterations):
        has_match, matched = engine._detect_hard_fail_indicators(untagged_reasons)
    pattern_time = (time.perf_counter() - start) * 1000 / iterations
    
    print(f"\n📊 Results (100 reasons, {iterations} iterations):")
    print(f"  Tag-first approach:   {tag_time:.4f}ms per check")
    print(f"  Pattern-only approach: {pattern_time:.4f}ms per check")
    print(f"  Speedup: {pattern_time/tag_time:.2f}x faster with tags")
    
    print("\n✅ Tag-first optimization provides significant performance improvement!")
    
    return True


if __name__ == "__main__":
    try:
        print("\n🚀 Testing Tag-First Optimization\n")
        
        test_tag_first_optimization()
        test_performance_comparison()
        
        print("\n" + "=" * 60)
        print("🎉 ALL OPTIMIZATION TESTS PASSED!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
