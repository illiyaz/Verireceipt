"""
Golden tests for address validation features.

These tests lock behavior against real-world drift and prevent silent regressions.
Test cases are defined in tests/golden/address_cases.json.

Assertions are intentionally coarse (not brittle) to allow heuristic evolution:
- ✅ classification ∈ {PLAUSIBLE, STRONG}
- ✅ multi-address ∈ {SINGLE, MULTIPLE, UNKNOWN}
- ❌ no exact score matching
"""

import json
import pytest
from pathlib import Path
from app.address.validate import validate_address, assess_merchant_address_consistency, detect_multi_address_profile


def load_golden_cases():
    """Load golden test cases from JSON file."""
    golden_file = Path(__file__).parent / "golden" / "address_cases.json"
    with open(golden_file, "r") as f:
        data = json.load(f)
    return data["test_cases"]


class TestAddressGolden:
    """Golden tests for address validation features."""
    
    @pytest.mark.parametrize("case", load_golden_cases(), ids=lambda c: c["id"])
    def test_address_profile(self, case):
        """Test address_profile classification against golden expectations."""
        doc_text = case["doc_text"]
        expected = case["expected"]["address_profile"]
        
        # Run address validation
        result = validate_address(doc_text)
        
        # Assert classification is in expected set
        if "classification" in expected:
            assert result["address_classification"] in expected["classification"], \
                f"Expected classification in {expected['classification']}, got {result['address_classification']}"
        
        # Assert score is within expected range
        if "score_min" in expected:
            assert result["address_score"] >= expected["score_min"], \
                f"Expected score >= {expected['score_min']}, got {result['address_score']}"
        
        if "score_max" in expected:
            assert result["address_score"] <= expected["score_max"], \
                f"Expected score <= {expected['score_max']}, got {result['address_score']}"
        
        # Assert address type if specified
        if "address_type" in expected:
            assert result["address_type"] == expected["address_type"], \
                f"Expected address_type {expected['address_type']}, got {result['address_type']}"
    
    @pytest.mark.parametrize("case", load_golden_cases(), ids=lambda c: c["id"])
    def test_merchant_address_consistency(self, case):
        """Test merchant-address consistency against golden expectations."""
        doc_text = case["doc_text"]
        doc_profile_confidence = case["doc_profile_confidence"]
        expected = case["expected"].get("merchant_address_consistency", {})
        
        if not expected:
            pytest.skip("No merchant_address_consistency expectations for this case")
        
        # Extract merchant name (simple heuristic: first non-empty line)
        lines = doc_text.strip().split("\n")
        merchant_name = next((line.strip() for line in lines if line.strip()), "")
        
        # Compute merchant confidence (simple heuristic for testing)
        merchant_confidence = 0.8 if merchant_name else 0.0
        
        # Run address validation
        address_profile = validate_address(doc_text)
        
        # Run consistency check
        result = assess_merchant_address_consistency(
            merchant_name=merchant_name,
            merchant_confidence=merchant_confidence,
            address_profile=address_profile,
            doc_profile_confidence=doc_profile_confidence,
        )
        
        # Assert status is in expected set
        if "status" in expected:
            assert result["status"] in expected["status"], \
                f"Expected status in {expected['status']}, got {result['status']}"
    
    @pytest.mark.parametrize("case", load_golden_cases(), ids=lambda c: c["id"])
    def test_multi_address_profile(self, case):
        """Test multi-address detection against golden expectations."""
        doc_text = case["doc_text"]
        doc_profile_confidence = case["doc_profile_confidence"]
        expected = case["expected"].get("multi_address_profile", {})
        
        if not expected:
            pytest.skip("No multi_address_profile expectations for this case")
        
        # Run multi-address detection
        result = detect_multi_address_profile(
            text=doc_text,
            doc_profile_confidence=doc_profile_confidence,
        )
        
        # Assert status is in expected set
        if "status" in expected:
            assert result["status"] in expected["status"], \
                f"Expected status in {expected['status']}, got {result['status']}"
        
        # Assert count is within expected range
        if "count_min" in expected:
            assert result["count"] >= expected["count_min"], \
                f"Expected count >= {expected['count_min']}, got {result['count']}"
        
        if "count_max" in expected:
            assert result["count"] <= expected["count_max"], \
                f"Expected count <= {expected['count_max']}, got {result['count']}"
        
        # Assert exact count if specified
        if "count" in expected:
            assert result["count"] == expected["count"], \
                f"Expected count {expected['count']}, got {result['count']}"
    
    @pytest.mark.parametrize("case", load_golden_cases(), ids=lambda c: c["id"])
    def test_confidence_gating(self, case):
        """Test that low doc_profile_confidence properly gates features."""
        doc_profile_confidence = case["doc_profile_confidence"]
        
        # Only test cases with low confidence
        if doc_profile_confidence >= 0.55:
            pytest.skip("Confidence gating only applies when doc_profile_confidence < 0.55")
        
        doc_text = case["doc_text"]
        
        # Extract merchant name
        lines = doc_text.strip().split("\n")
        merchant_name = next((line.strip() for line in lines if line.strip()), "")
        merchant_confidence = 0.8
        
        # Run features
        address_profile = validate_address(doc_text)
        
        consistency_result = assess_merchant_address_consistency(
            merchant_name=merchant_name,
            merchant_confidence=merchant_confidence,
            address_profile=address_profile,
            doc_profile_confidence=doc_profile_confidence,
        )
        
        multi_result = detect_multi_address_profile(
            text=doc_text,
            doc_profile_confidence=doc_profile_confidence,
        )
        
        # Both should be gated (UNKNOWN)
        assert consistency_result["status"] == "UNKNOWN", \
            f"Consistency should be UNKNOWN when doc_profile_confidence < 0.55, got {consistency_result['status']}"
        
        assert multi_result["status"] == "UNKNOWN", \
            f"Multi-address should be UNKNOWN when doc_profile_confidence < 0.55, got {multi_result['status']}"


class TestGoldenCaseIntegrity:
    """Meta-tests to validate the golden test cases themselves."""
    
    def test_all_cases_have_required_fields(self):
        """Ensure all test cases have required fields."""
        cases = load_golden_cases()
        
        for case in cases:
            assert "id" in case, "Case missing 'id'"
            assert "description" in case, "Case missing 'description'"
            assert "doc_text" in case, "Case missing 'doc_text'"
            assert "doc_profile_confidence" in case, "Case missing 'doc_profile_confidence'"
            assert "expected" in case, "Case missing 'expected'"
            
            # At least one expectation should be present
            expected = case["expected"]
            assert any(k in expected for k in ["address_profile", "merchant_address_consistency", "multi_address_profile"]), \
                f"Case {case['id']} has no expectations"
    
    def test_case_ids_are_unique(self):
        """Ensure all test case IDs are unique."""
        cases = load_golden_cases()
        ids = [case["id"] for case in cases]
        
        assert len(ids) == len(set(ids)), f"Duplicate case IDs found: {[id for id in ids if ids.count(id) > 1]}"
    
    def test_confidence_values_are_valid(self):
        """Ensure doc_profile_confidence values are in valid range [0.0, 1.0]."""
        cases = load_golden_cases()
        
        for case in cases:
            conf = case["doc_profile_confidence"]
            assert 0.0 <= conf <= 1.0, \
                f"Case {case['id']} has invalid doc_profile_confidence: {conf}"
    
    def test_expected_classifications_are_valid(self):
        """Ensure expected classifications use valid values."""
        valid_classifications = {"NOT_AN_ADDRESS", "WEAK_ADDRESS", "PLAUSIBLE_ADDRESS", "STRONG_ADDRESS"}
        cases = load_golden_cases()
        
        for case in cases:
            if "address_profile" in case["expected"] and "classification" in case["expected"]["address_profile"]:
                expected_classes = case["expected"]["address_profile"]["classification"]
                for cls in expected_classes:
                    assert cls in valid_classifications, \
                        f"Case {case['id']} has invalid classification: {cls}"
    
    def test_expected_statuses_are_valid(self):
        """Ensure expected statuses use valid values."""
        valid_consistency_statuses = {"UNKNOWN", "CONSISTENT", "WEAK_MISMATCH", "MISMATCH"}
        valid_multi_statuses = {"UNKNOWN", "SINGLE", "MULTIPLE"}
        cases = load_golden_cases()
        
        for case in cases:
            # Check consistency statuses
            if "merchant_address_consistency" in case["expected"] and "status" in case["expected"]["merchant_address_consistency"]:
                expected_statuses = case["expected"]["merchant_address_consistency"]["status"]
                for status in expected_statuses:
                    assert status in valid_consistency_statuses, \
                        f"Case {case['id']} has invalid consistency status: {status}"
            
            # Check multi-address statuses
            if "multi_address_profile" in case["expected"] and "status" in case["expected"]["multi_address_profile"]:
                expected_statuses = case["expected"]["multi_address_profile"]["status"]
                for status in expected_statuses:
                    assert status in valid_multi_statuses, \
                        f"Case {case['id']} has invalid multi-address status: {status}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
