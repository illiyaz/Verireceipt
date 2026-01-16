"""
Golden Test Runner for VeriReceipt Rules Engine

Canonical tests that lock in behavior per document family.
These tests prevent entropy and ensure rules remain sane over time.

Usage:
    python tests/golden_test_runner.py
    python tests/golden_test_runner.py --test invoice
    python tests/golden_test_runner.py --strict  # Fail on any deviation
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from app.pipelines.rules import _score_and_explain
from app.pipelines.features import ReceiptFeatures


@dataclass
class GoldenTestResult:
    """Result of a golden test execution"""
    name: str
    passed: bool
    errors: List[str]
    warnings: List[str]
    actual_decision: Optional[str] = None
    actual_score: Optional[float] = None
    actual_rules_fired: Optional[List[str]] = None


class GoldenTestRunner:
    """Runs canonical golden tests to prevent rule regression"""
    
    def __init__(self, golden_dir: Path = Path("tests/golden")):
        self.golden_dir = golden_dir
        self.results: List[GoldenTestResult] = []
    
    def create_features_from_input(self, input_data: Dict[str, Any]) -> ReceiptFeatures:
        """Create ReceiptFeatures object from golden test input"""
        features = ReceiptFeatures(
            file_features={},
            text_features={},
            layout_features={},
            forensic_features={}
        )
        
        # Set all input fields as attributes
        for key, value in input_data.items():
            setattr(features, key, value)
        
        return features
    
    def run_test(self, test_file: Path) -> GoldenTestResult:
        """Run a single golden test"""
        with open(test_file) as f:
            test_data = json.load(f)
        
        name = test_data.get("name", test_file.stem)
        input_data = test_data.get("input", {})
        expected = test_data.get("expected", {})
        
        errors = []
        warnings = []
        
        try:
            # Create features and run scoring
            features = self.create_features_from_input(input_data)
            result = _score_and_explain(features, apply_learned=False)
            
            # Extract actual results
            actual_decision = "fake" if result.score >= 0.5 else "real"
            actual_score = result.score
            actual_rules_fired = [e.rule_id for e in result.events if e.weight > 0]
            
            # Validate decision
            expected_decision = expected.get("decision")
            if expected_decision and actual_decision != expected_decision:
                errors.append(
                    f"Decision mismatch: expected '{expected_decision}', got '{actual_decision}'"
                )
            
            # Validate score range
            expected_max_score = expected.get("max_score") or expected.get("score_max")
            expected_min_score = expected.get("min_score") or expected.get("score_min")
            
            if expected_max_score is not None and actual_score > expected_max_score:
                errors.append(
                    f"Score too high: expected <= {expected_max_score}, got {actual_score:.4f}"
                )
            
            if expected_min_score is not None and actual_score < expected_min_score:
                errors.append(
                    f"Score too low: expected >= {expected_min_score}, got {actual_score:.4f}"
                )
            
            # Validate exact score (if specified)
            expected_exact_score = expected.get("score")
            if expected_exact_score is not None:
                tolerance = expected.get("score_tolerance", 0.01)
                if abs(actual_score - expected_exact_score) > tolerance:
                    errors.append(
                        f"Score mismatch: expected {expected_exact_score} ± {tolerance}, got {actual_score:.4f}"
                    )
            
            # Validate rules fired
            expected_rules_fired = expected.get("rules_fired", [])
            for rule_id in expected_rules_fired:
                if rule_id not in actual_rules_fired:
                    errors.append(f"Expected rule '{rule_id}' did not fire")
            
            # Validate rules NOT fired
            expected_rules_not_fired = expected.get("rules_not_fired", [])
            for rule_id in expected_rules_not_fired:
                if rule_id in actual_rules_fired:
                    errors.append(f"Rule '{rule_id}' fired but should NOT have")
            
            # Check for unexpected high-severity events
            critical_events = [e for e in result.events if e.severity == "CRITICAL"]
            if critical_events and not expected.get("allow_critical", False):
                warnings.append(
                    f"CRITICAL events fired: {[e.rule_id for e in critical_events]}"
                )
            
            passed = len(errors) == 0
            
            return GoldenTestResult(
                name=name,
                passed=passed,
                errors=errors,
                warnings=warnings,
                actual_decision=actual_decision,
                actual_score=actual_score,
                actual_rules_fired=actual_rules_fired,
            )
            
        except Exception as e:
            return GoldenTestResult(
                name=name,
                passed=False,
                errors=[f"Test execution failed: {str(e)}"],
                warnings=[],
            )
    
    def run_all_tests(self, test_filter: Optional[str] = None) -> bool:
        """Run all golden tests in the golden directory"""
        test_files = sorted(self.golden_dir.glob("*.json"))
        
        if test_filter:
            test_files = [f for f in test_files if test_filter in f.stem]
        
        if not test_files:
            print(f"❌ No golden tests found in {self.golden_dir}")
            return False
        
        print(f"🧪 Running {len(test_files)} golden test(s)...\n")
        
        for test_file in test_files:
            result = self.run_test(test_file)
            self.results.append(result)
            
            # Print result
            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"{status} {result.name}")
            
            if result.actual_decision:
                print(f"   Decision: {result.actual_decision} (score: {result.actual_score:.4f})")
            
            if result.actual_rules_fired:
                print(f"   Rules fired: {', '.join(result.actual_rules_fired)}")
            
            for error in result.errors:
                print(f"   ❌ {error}")
            
            for warning in result.warnings:
                print(f"   ⚠️  {warning}")
            
            print()
        
        # Summary
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed
        
        print("=" * 60)
        print(f"Golden Test Summary: {passed} passed, {failed} failed")
        print("=" * 60)
        
        return failed == 0
    
    def check_misc_safe(self) -> bool:
        """
        CRITICAL: Verify that misc_safe.json passes.
        This test prevents 90% of future false positives.
        """
        misc_safe = self.golden_dir / "misc_safe.json"
        if not misc_safe.exists():
            print("⚠️  WARNING: misc_safe.json not found - this is CRITICAL")
            return False
        
        result = self.run_test(misc_safe)
        
        if not result.passed:
            print("🚨 CRITICAL: misc_safe.json FAILED")
            print("   This test prevents false positives on unknown documents")
            print("   DO NOT MERGE until this passes")
            return False
        
        print("✅ CRITICAL: misc_safe.json PASSED")
        return True


def main():
    """Main entry point for golden test runner"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run VeriReceipt golden tests")
    parser.add_argument("--test", help="Filter tests by name")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings")
    parser.add_argument("--check-misc", action="store_true", help="Only check misc_safe.json")
    
    args = parser.parse_args()
    
    runner = GoldenTestRunner()
    
    if args.check_misc:
        success = runner.check_misc_safe()
        sys.exit(0 if success else 1)
    
    success = runner.run_all_tests(test_filter=args.test)
    
    # Check for warnings in strict mode
    if args.strict and success:
        has_warnings = any(r.warnings for r in runner.results)
        if has_warnings:
            print("❌ STRICT MODE: Tests passed but warnings present")
            sys.exit(1)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
