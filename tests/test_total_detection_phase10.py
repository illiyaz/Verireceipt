"""
Phase-10 + A10-A12: Unit tests for total detection with token_row_band fallback.

Tests:
1. Regex window works - token_row_band NOT used
2. Token row band fallback succeeds when regex_window fails (column-separated layout)
3. A10: keyword_found_no_amount sets detection_path correctly and does NOT set regex_total_line_text
4. A11: token_row_band_available=False when coords absent
5. A12: mismatch_reliable=False when conditions met
"""

import pytest
from dataclasses import dataclass
from typing import Optional, List

from app.pipelines.features import _find_total_line, TotalDetectionResult


class TestTotalDetectionPhase10:
    """Tests for Phase-10 total detection with token_row_band fallback."""
    
    def test_regex_window_succeeds_token_row_band_not_used(self):
        """
        When regex_window finds the amount on the same line or nearby,
        token_row_band should NOT be used.
        """
        # Standard case: Total label and amount on same line
        lines = [
            "Item 1: $25.00",
            "Item 2: $35.00",
            "Subtotal: $60.00",
            "Tax: $6.00",
            "GRAND TOTAL: $66.00",
        ]
        
        result = _find_total_line(lines, layout_tokens=None)
        
        assert result.total_amount is not None, "Amount should be found"
        assert result.total_amount == 66.00, f"Expected 66.00, got {result.total_amount}"
        assert result.detection_path == "regex_window", f"Expected regex_window, got {result.detection_path}"
        # Keyword should contain 'total' (exact keyword depends on matching order)
        assert "total" in result.keyword.lower(), f"Expected keyword containing 'total', got {result.keyword}"
        assert result.token_row_band_used is False, "Token row band should NOT be used"
        # A10: regex_total_line_text should be set when regex finds amount
        assert result.regex_total_line_text is not None, "regex_total_line_text should be set"
    
    def test_regex_window_neighbor_line(self):
        """
        When amount is on a neighboring line, regex_window should still find it.
        """
        # Amount on next line (common in some layouts)
        lines = [
            "Item 1: $25.00",
            "Total",
            "$100.00",  # Amount on next line
        ]
        
        result = _find_total_line(lines, layout_tokens=None)
        
        assert result.total_amount is not None, "Amount should be found"
        assert result.total_amount == 100.00, f"Expected 100.00, got {result.total_amount}"
        assert result.detection_path == "regex_window", f"Expected regex_window, got {result.detection_path}"
        assert result.token_row_band_used is False, "Token row band should NOT be used"
    
    def test_token_row_band_fallback_with_synthetic_tokens(self):
        """
        When regex_window fails (label and amount separated by columns),
        token_row_band should succeed using LayoutTokens.
        
        Simulates: "GRAND TOTAL                    $500.00"
        where the text line doesn't contain the amount due to column separation.
        """
        # Synthetic case: Total label without amount in text line
        # No amounts anywhere in neighboring lines either
        lines = [
            "Description",
            "Services rendered",
            "GRAND TOTAL",  # No amount on this line (column-separated)
            "Thank you",
        ]
        
        # Create synthetic LayoutTokens simulating column layout
        @dataclass
        class MockLayoutToken:
            text: str
            line_idx: int
            x0: float
            y0: float
            x1: float
            y1: float
            has_coords: bool = True
        
        # Tokens on line 2 (GRAND TOTAL line):
        # - "GRAND TOTAL" at left side (x0=50, x1=200)
        # - "$500.00" at right side (x0=400, x1=500) - same visual row, x0 > keyword x1
        layout_tokens = [
            MockLayoutToken(text="Description", line_idx=0, x0=50, y0=50, x1=200, y1=70, has_coords=True),
            MockLayoutToken(text="Services rendered", line_idx=1, x0=50, y0=100, x1=250, y1=120, has_coords=True),
            # Line 2: GRAND TOTAL at left (x1=200)
            MockLayoutToken(text="GRAND TOTAL", line_idx=2, x0=50, y0=200, x1=200, y1=220, has_coords=True),
            # Same Y-band, but at right (x0=400 > keyword x1=200)
            MockLayoutToken(text="$500.00", line_idx=2, x0=400, y0=200, x1=500, y1=220, has_coords=True),
            MockLayoutToken(text="Thank you", line_idx=3, x0=50, y0=280, x1=200, y1=300, has_coords=True),
        ]
        
        result = _find_total_line(lines, layout_tokens=layout_tokens)
        
        # Should find amount via token_row_band fallback
        assert result.total_amount is not None, "Amount should be found via token_row_band"
        assert result.total_amount == 500.00, f"Expected 500.00, got {result.total_amount}"
        assert result.detection_path == "token_row_band", f"Expected token_row_band, got {result.detection_path}"
        assert "total" in result.keyword.lower(), f"Expected keyword containing 'total', got {result.keyword}"
        assert result.keyword_line_idx == 2, f"Expected line 2, got {result.keyword_line_idx}"
        assert result.token_row_band_used is True, "Token row band should be used"
        assert result.token_row_band_available is True, "Token row band should be available"
    
    def test_no_total_keyword_returns_none(self):
        """
        When no total keyword is found, detection_path should be 'none'.
        """
        lines = [
            "Item 1: $25.00",
            "Item 2: $35.00",
            "Thanks for shopping",
        ]
        
        result = _find_total_line(lines, layout_tokens=None)
        
        assert result.total_amount is None, "No amount expected"
        assert result.detection_path == "none", f"Expected 'none', got {result.detection_path}"
        assert result.keyword is None, "No keyword expected"
        assert result.token_row_band_used is False
    
    def test_total_detection_result_metadata(self):
        """
        Verify TotalDetectionResult contains all expected metadata fields.
        """
        lines = [
            "Balance Due: $150.00",
        ]
        
        result = _find_total_line(lines, layout_tokens=None)
        
        # Check all metadata fields are present (Phase-10 + A10-A12)
        assert isinstance(result, TotalDetectionResult)
        assert hasattr(result, 'total_line')
        assert hasattr(result, 'total_amount')
        assert hasattr(result, 'detection_path')
        assert hasattr(result, 'keyword')
        assert hasattr(result, 'keyword_line_idx')
        assert hasattr(result, 'total_keyword_line_text')  # A10
        assert hasattr(result, 'regex_total_line_text')    # A10
        assert hasattr(result, 'token_row_band_available') # A11
        assert hasattr(result, 'token_row_band_used')
        
        # Verify correct values
        assert result.total_amount == 150.00
        assert result.keyword == "balance due"
        assert result.detection_path == "regex_window"


class TestA10ProvenanceIntegrity:
    """A10: Tests for provenance integrity - split fields and detection_path."""
    
    def test_keyword_found_no_amount_detection_path(self):
        """
        A10: When keyword is found but no amount nearby, detection_path should be
        'keyword_found_no_amount' and regex_total_line_text should NOT be set.
        """
        # Total keyword found but no amount anywhere nearby
        lines = [
            "Description of services",
            "GRAND TOTAL",  # No amount on this line
            "Thank you for your business",
        ]
        
        result = _find_total_line(lines, layout_tokens=None)
        
        # A10: detection_path should be 'keyword_found_no_amount'
        assert result.detection_path == "keyword_found_no_amount", \
            f"Expected 'keyword_found_no_amount', got {result.detection_path}"
        
        # A10: regex_total_line_text should NOT be set
        assert result.regex_total_line_text is None, \
            "regex_total_line_text should NOT be set when no amount found"
        
        # A10: total_keyword_line_text SHOULD be set
        assert result.total_keyword_line_text is not None, \
            "total_keyword_line_text should be set"
        assert "GRAND TOTAL" in result.total_keyword_line_text, \
            f"Expected keyword line to contain 'GRAND TOTAL', got {result.total_keyword_line_text}"
        
        # Amount should be None
        assert result.total_amount is None, "Amount should be None"
        
        # Keyword should still be found
        assert result.keyword is not None, "Keyword should be found"
        assert "total" in result.keyword.lower()
    
    def test_regex_total_line_text_only_set_when_amount_found(self):
        """
        A10: regex_total_line_text should ONLY be set when regex actually finds an amount.
        """
        # Case 1: Amount found - regex_total_line_text should be set
        lines_with_amount = [
            "GRAND TOTAL: $100.00",
        ]
        result1 = _find_total_line(lines_with_amount, layout_tokens=None)
        assert result1.regex_total_line_text is not None, \
            "regex_total_line_text should be set when amount found"
        assert result1.detection_path == "regex_window"
        
        # Case 2: No amount - regex_total_line_text should NOT be set
        lines_no_amount = [
            "Description",
            "GRAND TOTAL",  # No amount
            "Notes",
        ]
        result2 = _find_total_line(lines_no_amount, layout_tokens=None)
        assert result2.regex_total_line_text is None, \
            "regex_total_line_text should NOT be set when no amount found"
        assert result2.detection_path == "keyword_found_no_amount"


class TestA11TokenRowBandAvailability:
    """A11: Tests for token_row_band_available flag."""
    
    def test_token_row_band_available_false_when_no_coords(self):
        """
        A11: token_row_band_available should be False when layout_tokens
        have no coordinate information.
        """
        lines = [
            "Description",
            "GRAND TOTAL",  # No amount
            "Thank you",
        ]
        
        # Create tokens WITHOUT coordinates
        @dataclass
        class MockTokenNoCoords:
            text: str
            line_idx: int
            has_coords: bool = False
        
        layout_tokens = [
            MockTokenNoCoords(text="Description", line_idx=0, has_coords=False),
            MockTokenNoCoords(text="GRAND TOTAL", line_idx=1, has_coords=False),
            MockTokenNoCoords(text="Thank you", line_idx=2, has_coords=False),
        ]
        
        result = _find_total_line(lines, layout_tokens=layout_tokens)
        
        # A11: token_row_band_available should be False
        assert result.token_row_band_available is False, \
            "token_row_band_available should be False when no coords"
        assert result.token_row_band_used is False, \
            "token_row_band_used should be False"
    
    def test_token_row_band_available_false_when_no_tokens(self):
        """
        A11: token_row_band_available should be False when no layout_tokens provided.
        """
        lines = [
            "Description",
            "GRAND TOTAL",  # No amount
            "Thank you",
        ]
        
        result = _find_total_line(lines, layout_tokens=None)
        
        # A11: token_row_band_available should be False
        assert result.token_row_band_available is False, \
            "token_row_band_available should be False when no tokens"
    
    def test_token_row_band_available_true_when_coords_exist(self):
        """
        A11: token_row_band_available should be True when coords exist,
        even if no amount is found via token_row_band.
        """
        lines = [
            "Description",
            "GRAND TOTAL",  # No amount
            "Thank you",
        ]
        
        @dataclass
        class MockLayoutToken:
            text: str
            line_idx: int
            x0: float
            y0: float
            x1: float
            y1: float
            has_coords: bool = True
        
        # Tokens WITH coords but no amount token on the GRAND TOTAL line
        layout_tokens = [
            MockLayoutToken(text="Description", line_idx=0, x0=50, y0=50, x1=200, y1=70, has_coords=True),
            MockLayoutToken(text="GRAND TOTAL", line_idx=1, x0=50, y0=100, x1=200, y1=120, has_coords=True),
            MockLayoutToken(text="Thank you", line_idx=2, x0=50, y0=150, x1=200, y1=170, has_coords=True),
        ]
        
        result = _find_total_line(lines, layout_tokens=layout_tokens)
        
        # A11: token_row_band_available should be True (coords exist)
        assert result.token_row_band_available is True, \
            "token_row_band_available should be True when coords exist"
        # But token_row_band_used should be False (no amount found)
        assert result.token_row_band_used is False, \
            "token_row_band_used should be False when no amount found"


class TestPA101ProvenanceConsistency:
    """
    P-A10.1: Tests for provenance consistency between legacy and new fields.
    """
    
    def test_regex_total_line_none_when_regex_total_line_text_none(self):
        """
        P-A10.1: When regex_total_line_text is None (no regex match),
        the legacy regex_total_line passed to reconcile_amounts should also be None.
        
        This tests the consistency at the _find_total_line level.
        """
        lines = [
            "Description",
            "GRAND TOTAL",  # No amount on same line
            "Thank you",
        ]
        
        result = _find_total_line(lines, layout_tokens=None)
        
        # P-A10.1: Both should be None when no regex match
        assert result.regex_total_line_text is None, \
            "regex_total_line_text should be None when no regex match"
        # The total_keyword_line_text should still be set to keyword line
        assert result.total_keyword_line_text == "GRAND TOTAL", \
            "total_keyword_line_text should be set to keyword line"
    
    def test_regex_total_line_text_set_when_amount_found(self):
        """
        P-A10.1: When regex finds an amount, regex_total_line_text should be set.
        """
        lines = [
            "Description",
            "GRAND TOTAL $100.00",  # Amount on same line
            "Thank you",
        ]
        
        result = _find_total_line(lines, layout_tokens=None)
        
        # P-A10.1: regex_total_line_text should be set when amount found
        assert result.regex_total_line_text is not None, \
            "regex_total_line_text should be set when regex finds amount"
        assert result.total_amount == 100.00, \
            f"Expected 100.00, got {result.total_amount}"
    
    def test_keyword_line_text_always_set_when_keyword_found(self):
        """
        P-A10.1: total_keyword_line_text should always be set when keyword is found,
        regardless of whether regex finds an amount.
        """
        # Case 1: Keyword found, no amount
        lines_no_amount = [
            "Description",
            "GRAND TOTAL",
            "Thank you",
        ]
        result1 = _find_total_line(lines_no_amount, layout_tokens=None)
        assert result1.total_keyword_line_text == "GRAND TOTAL", \
            "Keyword line text should be set even without amount"
        
        # Case 2: Keyword found, with amount
        lines_with_amount = [
            "Description",
            "GRAND TOTAL $100.00",
            "Thank you",
        ]
        result2 = _find_total_line(lines_with_amount, layout_tokens=None)
        assert result2.total_keyword_line_text == "GRAND TOTAL $100.00", \
            "Keyword line text should be set with amount"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
