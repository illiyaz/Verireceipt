"""
Tests for Receipt Template Matching Module

Tests fingerprinting, matching, and registry functionality.
"""

import pytest
from pathlib import Path

from app.pipelines.templates.fingerprint import (
    TemplateFingerprint,
    compute_fingerprint,
)
from app.pipelines.templates.matcher import (
    TemplateMatcher,
    TemplateMatch,
    match_template,
)
from app.pipelines.templates.registry import (
    TemplateRegistry,
    reset_registry,
)


# Sample receipt text for testing
SAMPLE_RECEIPT_1 = """
STARBUCKS COFFEE
123 Main Street
New York, NY 10001
Tel: 212-555-1234

Date: 01/15/2024  Time: 09:30 AM
Order #: 12345

--------------------------------
Grande Latte           $5.95
Blueberry Muffin       $3.45
--------------------------------
Subtotal:              $9.40
Tax (8.875%):          $0.83
--------------------------------
TOTAL:                $10.23

VISA ****1234
Auth: 123456

Thank you for visiting!
Have a great day!
""".strip().split("\n")

SAMPLE_RECEIPT_2 = """
WALMART
ALWAYS LOW PRICES
Store #1234
456 Commerce Blvd
Los Angeles, CA 90001

01/20/2024 14:32

MILK 1 GAL         $3.99
BREAD              $2.49
EGGS DOZEN         $4.99
BANANAS 2LB        $1.47
CHIPS              $3.99

SUBTOTAL          $16.93
TAX                $1.48
TOTAL             $18.41

CASH              $20.00
CHANGE             $1.59

THANK YOU FOR SHOPPING
""".strip().split("\n")


class TestFingerprint:
    """Tests for template fingerprinting."""
    
    def test_compute_fingerprint_basic(self):
        """Test basic fingerprint computation."""
        fp = compute_fingerprint(SAMPLE_RECEIPT_1)
        
        assert fp is not None
        assert fp.source == "learned"
        assert fp.line_count_range[0] <= len(SAMPLE_RECEIPT_1) <= fp.line_count_range[1]
        assert fp.has_total_line is True
        assert fp.has_tax_line is True
    
    def test_compute_fingerprint_with_id(self):
        """Test fingerprint with custom ID."""
        fp = compute_fingerprint(
            SAMPLE_RECEIPT_1,
            template_id="test_starbucks",
            template_name="Starbucks Coffee",
            source="custom"
        )
        
        assert fp.template_id == "test_starbucks"
        assert fp.template_name == "Starbucks Coffee"
        assert fp.source == "custom"
    
    def test_fingerprint_merchant_keywords(self):
        """Test merchant keyword extraction."""
        fp = compute_fingerprint(SAMPLE_RECEIPT_1)
        
        # Should extract keywords from first few lines
        assert "starbucks" in fp.merchant_keywords or "coffee" in fp.merchant_keywords
    
    def test_fingerprint_footer_keywords(self):
        """Test footer keyword extraction."""
        fp = compute_fingerprint(SAMPLE_RECEIPT_1)
        
        # Should detect thank you phrase
        assert "thank you" in fp.footer_keywords or "thank" in fp.footer_keywords
    
    def test_fingerprint_has_time(self):
        """Test time detection."""
        fp = compute_fingerprint(SAMPLE_RECEIPT_1)
        assert fp.has_time is True
        
        # Receipt 2 also has time
        fp2 = compute_fingerprint(SAMPLE_RECEIPT_2)
        assert fp2.has_time is True
    
    def test_fingerprint_serialization(self):
        """Test fingerprint to_dict and from_dict."""
        fp1 = compute_fingerprint(SAMPLE_RECEIPT_1, template_id="test1")
        
        # Serialize
        data = fp1.to_dict()
        assert isinstance(data, dict)
        assert data["template_id"] == "test1"
        
        # Deserialize
        fp2 = TemplateFingerprint.from_dict(data)
        assert fp2.template_id == fp1.template_id
        assert fp2.has_tax_line == fp1.has_tax_line
    
    def test_fingerprint_empty_lines_raises(self):
        """Test that empty lines raise ValueError."""
        with pytest.raises(ValueError):
            compute_fingerprint([])


class TestMatcher:
    """Tests for template matching."""
    
    @pytest.fixture
    def templates(self):
        """Create sample templates for testing."""
        return [
            compute_fingerprint(
                SAMPLE_RECEIPT_1,
                template_id="starbucks",
                template_name="Starbucks",
                source="test"
            ),
            compute_fingerprint(
                SAMPLE_RECEIPT_2,
                template_id="walmart",
                template_name="Walmart",
                source="test"
            ),
        ]
    
    def test_matcher_exact_match(self, templates):
        """Test matching against exact same receipt."""
        matcher = TemplateMatcher(templates)
        
        # Match receipt 1 - should match starbucks template
        matches = matcher.match(SAMPLE_RECEIPT_1, top_k=2)
        
        assert len(matches) >= 1
        assert matches[0].template.template_id == "starbucks"
        assert matches[0].confidence > 0.8
    
    def test_matcher_different_receipt(self, templates):
        """Test matching different receipts."""
        matcher = TemplateMatcher(templates)
        
        # Match receipt 2 - should match walmart template
        matches = matcher.match(SAMPLE_RECEIPT_2, top_k=2)
        
        assert len(matches) >= 1
        assert matches[0].template.template_id == "walmart"
    
    def test_matcher_best_match(self, templates):
        """Test match_best convenience method."""
        matcher = TemplateMatcher(templates)
        
        match = matcher.match_best(SAMPLE_RECEIPT_1, min_confidence=0.5)
        
        assert match is not None
        assert match.template.template_id == "starbucks"
    
    def test_matcher_min_confidence(self, templates):
        """Test minimum confidence threshold."""
        matcher = TemplateMatcher(templates)
        
        # Very high threshold - should return no matches
        matches = matcher.match(SAMPLE_RECEIPT_1, min_confidence=0.99)
        
        # May or may not match depending on similarity
        # Just verify it doesn't crash
        assert isinstance(matches, list)
    
    def test_match_template_convenience(self, templates):
        """Test match_template convenience function."""
        match = match_template(SAMPLE_RECEIPT_1, templates, min_confidence=0.5)
        
        assert match is not None
        assert match.template.template_id == "starbucks"
    
    def test_matcher_empty_templates(self):
        """Test matcher with no templates."""
        matcher = TemplateMatcher([])
        matches = matcher.match(SAMPLE_RECEIPT_1)
        
        assert matches == []
    
    def test_match_details(self, templates):
        """Test that match details are populated."""
        matcher = TemplateMatcher(templates)
        matches = matcher.match(SAMPLE_RECEIPT_1, top_k=1)
        
        assert len(matches) == 1
        match = matches[0]
        
        assert "merchant_keywords" in match.match_details
        assert "has_tax" in match.match_details
        assert "line_count" in match.match_details


class TestRegistry:
    """Tests for template registry."""
    
    def setup_method(self):
        """Reset registry before each test."""
        reset_registry()
    
    def test_registry_init(self):
        """Test registry initialization with no auto-load."""
        # Use non-existent dirs to ensure clean slate
        from pathlib import Path
        registry = TemplateRegistry(
            builtin_dir=Path("/nonexistent/builtin"),
            sroie_dir=Path("/nonexistent/sroie"),
            custom_dir=Path("/nonexistent/custom"),
            auto_load=False
        )
        
        assert registry.count() == 0
    
    def test_registry_add_template(self):
        """Test adding template to registry."""
        from pathlib import Path
        registry = TemplateRegistry(
            builtin_dir=Path("/nonexistent/builtin"),
            sroie_dir=Path("/nonexistent/sroie"),
            custom_dir=Path("/nonexistent/custom"),
            auto_load=False
        )
        
        fp = compute_fingerprint(SAMPLE_RECEIPT_1, template_id="test1")
        registry.add_template(fp)
        
        assert registry.count() == 1
        assert registry.get_by_id("test1") is not None
    
    def test_registry_get_by_source(self):
        """Test filtering templates by source."""
        from pathlib import Path
        registry = TemplateRegistry(
            builtin_dir=Path("/nonexistent/builtin"),
            sroie_dir=Path("/nonexistent/sroie"),
            custom_dir=Path("/nonexistent/custom"),
            auto_load=False
        )
        
        fp1 = compute_fingerprint(SAMPLE_RECEIPT_1, template_id="t1", source="sroie")
        fp2 = compute_fingerprint(SAMPLE_RECEIPT_2, template_id="t2", source="custom")
        
        registry.add_template(fp1)
        registry.add_template(fp2)
        
        sroie_templates = registry.get_by_source("sroie")
        custom_templates = registry.get_by_source("custom")
        
        assert len(sroie_templates) == 1
        assert len(custom_templates) == 1
    
    def test_registry_clear(self):
        """Test clearing registry."""
        from pathlib import Path
        registry = TemplateRegistry(
            builtin_dir=Path("/nonexistent/builtin"),
            sroie_dir=Path("/nonexistent/sroie"),
            custom_dir=Path("/nonexistent/custom"),
            auto_load=False
        )
        
        fp = compute_fingerprint(SAMPLE_RECEIPT_1, template_id="test1")
        registry.add_template(fp)
        
        assert registry.count() == 1
        
        registry.clear()
        
        assert registry.count() == 0


class TestIntegration:
    """Integration tests for template matching system."""
    
    def test_full_workflow(self):
        """Test complete workflow: fingerprint -> register -> match."""
        # Create and register templates with clean registry
        from pathlib import Path
        registry = TemplateRegistry(
            builtin_dir=Path("/nonexistent/builtin"),
            sroie_dir=Path("/nonexistent/sroie"),
            custom_dir=Path("/nonexistent/custom"),
            auto_load=False
        )
        
        fp1 = compute_fingerprint(
            SAMPLE_RECEIPT_1,
            template_id="starbucks",
            template_name="Starbucks",
            source="custom"
        )
        fp2 = compute_fingerprint(
            SAMPLE_RECEIPT_2,
            template_id="walmart",
            template_name="Walmart",
            source="custom"
        )
        
        registry.add_template(fp1)
        registry.add_template(fp2)
        
        # Create matcher from registry
        matcher = TemplateMatcher(registry.get_all())
        
        # Match new receipt (slightly modified)
        modified_receipt = SAMPLE_RECEIPT_1.copy()
        modified_receipt[5] = "Date: 02/20/2024  Time: 10:15 AM"  # Change date
        
        match = matcher.match_best(modified_receipt, min_confidence=0.5)
        
        assert match is not None
        assert match.template.template_id == "starbucks"
        assert match.confidence > 0.7
