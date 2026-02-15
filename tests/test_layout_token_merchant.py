"""
Tests for unified LayoutToken-based merchant extraction.

Tests cover:
- Seller vs buyer zone detection
- Multi-name documents (seller + multiple buyers)
- Mocked OCR tokens (EasyOCR style + Tesseract style)
- Structural label rejection
- Legal suffix detection
- No per-PDF special cases
"""

import pytest
from typing import List

from app.pipelines.layout_tokens import (
    LayoutToken,
    LayoutDocument,
    DocumentZones,
    MerchantCandidate,
    MerchantResult,
    build_tokens_from_lines,
    detect_zones,
    extract_merchant_from_tokens,
    extract_merchant_from_lines,
    is_structural_label,
    BUYER_ANCHORS,
    SELLER_ANCHORS,
    STRUCTURAL_LABELS,
    _has_legal_suffix,
    _is_plausible_company_name,
)


# -----------------------------------------------------------------------------
# Helper functions for creating test documents
# -----------------------------------------------------------------------------

def create_doc_with_coords(lines_with_coords: List[tuple]) -> LayoutDocument:
    """
    Create a LayoutDocument with coordinate data.
    
    Args:
        lines_with_coords: List of (text, x0, y0, x1, y1) tuples
        
    Returns:
        LayoutDocument with tokens including coordinates
    """
    tokens = []
    lines = []
    page_height = 800.0
    
    for idx, item in enumerate(lines_with_coords):
        text, x0, y0, x1, y1 = item
        tokens.append(LayoutToken(
            text=text,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            page=0,
            source="test",
            line_idx=idx,
        ))
        lines.append(text)
    
    return LayoutDocument(
        tokens=tokens,
        page_count=1,
        page_heights=[page_height],
        page_widths=[600.0],
        source="test",
        lines=lines,
    )


def create_easyocr_style_tokens(ocr_results: List[tuple]) -> LayoutDocument:
    """
    Create LayoutDocument mimicking EasyOCR output format.
    
    Args:
        ocr_results: List of (bbox, text, confidence) where bbox is [[x0,y0], [x1,y0], [x1,y1], [x0,y1]]
        
    Returns:
        LayoutDocument with EasyOCR-style tokens
    """
    tokens = []
    lines = []
    
    for idx, (bbox, text, conf) in enumerate(ocr_results):
        x_coords = [p[0] for p in bbox]
        y_coords = [p[1] for p in bbox]
        x0, x1 = min(x_coords), max(x_coords)
        y0, y1 = min(y_coords), max(y_coords)
        
        tokens.append(LayoutToken(
            text=text,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            page=0,
            source="easyocr",
            line_idx=idx,
            confidence=conf,
        ))
        lines.append(text)
    
    return LayoutDocument(
        tokens=tokens,
        page_count=1,
        page_heights=[800.0],
        page_widths=[600.0],
        source="easyocr",
        lines=lines,
        metadata={"avg_confidence": sum(t.confidence or 0 for t in tokens) / len(tokens) if tokens else 0}
    )


def create_tesseract_style_tokens(tsv_data: List[dict]) -> LayoutDocument:
    """
    Create LayoutDocument mimicking Tesseract TSV output.
    
    Args:
        tsv_data: List of dicts with {text, left, top, width, height, conf, line_num}
        
    Returns:
        LayoutDocument with Tesseract-style tokens
    """
    tokens = []
    lines = []
    current_line_words = []
    prev_line_num = -1
    line_idx = 0
    
    for item in tsv_data:
        text = item.get('text', '').strip()
        if not text:
            continue
        
        line_num = item.get('line_num', 0)
        if line_num != prev_line_num and current_line_words:
            lines.append(" ".join(current_line_words))
            current_line_words = []
            line_idx += 1
        prev_line_num = line_num
        
        x0 = item['left']
        y0 = item['top']
        w = item['width']
        h = item['height']
        conf = item.get('conf', 90)
        
        tokens.append(LayoutToken(
            text=text,
            x0=float(x0),
            y0=float(y0),
            x1=float(x0 + w),
            y1=float(y0 + h),
            page=0,
            source="tesseract",
            line_idx=line_idx,
            confidence=float(conf) / 100.0 if conf > 0 else None,
        ))
        current_line_words.append(text)
    
    if current_line_words:
        lines.append(" ".join(current_line_words))
    
    return LayoutDocument(
        tokens=tokens,
        page_count=1,
        page_heights=[800.0],
        page_widths=[600.0],
        source="tesseract",
        lines=lines,
    )


# -----------------------------------------------------------------------------
# Test: Zone Detection
# -----------------------------------------------------------------------------

class TestZoneDetection:
    """Test zone detection functionality."""
    
    def test_buyer_anchor_detection(self):
        """Test that buyer anchors are correctly detected."""
        lines = [
            "INVOICE",
            "ABC Corporation Ltd",
            "123 Main Street",
            "",
            "BILL TO:",
            "Customer Company Inc",
            "456 Customer Ave",
        ]
        
        doc = build_tokens_from_lines(lines)
        zones = detect_zones(doc)
        
        # Should detect BILL TO anchor
        assert "bill to" in zones.anchor_hits or any("bill" in k for k in zones.anchor_hits)
        
        # Customer lines should be in buyer zone
        assert 5 in zones.buyer_zone_indices or 6 in zones.buyer_zone_indices
    
    def test_seller_anchor_detection(self):
        """Test that seller anchors are correctly detected."""
        lines = [
            "COMMERCIAL INVOICE",
            "",
            "FROM:",
            "Seller Company LLC",
            "789 Seller Blvd",
            "",
            "BILL TO:",
            "Buyer Corp",
        ]
        
        doc = build_tokens_from_lines(lines)
        zones = detect_zones(doc)
        
        # Should detect FROM anchor
        assert "from" in zones.anchor_hits
        
        # Seller lines should be in seller zone
        assert 3 in zones.seller_zone_indices or 4 in zones.seller_zone_indices
    
    def test_header_zone_without_anchors(self):
        """Test that header region is marked as seller zone even without explicit anchors."""
        lines = [
            "ABC Manufacturing Inc",
            "100 Industrial Way",
            "Phone: 555-1234",
            "",
            "Item Description",
            "Product A - $100",
            "Product B - $200",
            "Total: $300",
        ]
        
        doc = build_tokens_from_lines(lines)
        zones = detect_zones(doc)
        
        # Early lines should be in seller zone (header region)
        assert 0 in zones.seller_zone_indices
    
    def test_multiple_buyer_zones(self):
        """Test document with both Bill To and Ship To zones."""
        lines = [
            "INVOICE",
            "Seller Inc",
            "",
            "BILL TO:",
            "Billing Customer",
            "Billing Address",
            "",
            "SHIP TO:",
            "Shipping Location",
            "Shipping Address",
        ]
        
        doc = build_tokens_from_lines(lines)
        zones = detect_zones(doc)
        
        # Both zones should be detected
        assert len(zones.billto_zone) > 0 or len(zones.shipto_zone) > 0
        
        # Seller should NOT be in buyer zone
        assert 1 not in zones.buyer_zone_indices


# -----------------------------------------------------------------------------
# Test: Structural Label Rejection
# -----------------------------------------------------------------------------

class TestStructuralLabelRejection:
    """Test rejection of structural labels as merchant candidates."""
    
    def test_financial_labels_rejected(self):
        """Financial field labels should be rejected."""
        labels = [
            "RECEIVED AMOUNT",
            "BALANCE DUE",
            "GRAND TOTAL",
            "SUBTOTAL",
            "TAX AMOUNT",
            "Total",
            "Amount",
        ]
        
        for label in labels:
            assert is_structural_label(label), f"'{label}' should be structural label"
    
    def test_document_labels_rejected(self):
        """Document type labels should be rejected."""
        labels = [
            "INVOICE",
            "RECEIPT",
            "DESCRIPTION",
            "QUANTITY",
        ]
        
        for label in labels:
            assert is_structural_label(label), f"'{label}' should be structural label"
    
    def test_company_names_not_rejected(self):
        """Legitimate company names should NOT be rejected."""
        names = [
            "ABC Corporation Ltd",
            "Global Trade Inc",
            "Tech Solutions LLC",
            "Smith & Associates",
        ]
        
        for name in names:
            assert not is_structural_label(name), f"'{name}' should NOT be structural label"


# -----------------------------------------------------------------------------
# Test: Legal Suffix Detection
# -----------------------------------------------------------------------------

class TestLegalSuffixDetection:
    """Test detection of legal entity suffixes."""
    
    def test_common_suffixes_detected(self):
        """Common legal suffixes should be detected."""
        names = [
            ("ABC Inc", True),
            ("XYZ LLC", True),
            ("Company Ltd", True),
            ("Corp America", True),
            ("Services GmbH", True),
            ("Holdings Pvt Ltd", True),
            ("Partners LLP", True),
        ]
        
        for name, expected in names:
            result = _has_legal_suffix(name)
            assert result == expected, f"'{name}' legal suffix detection: expected {expected}, got {result}"
    
    def test_no_suffix_not_detected(self):
        """Names without legal suffixes should not match."""
        names = [
            "John Smith",
            "Customer Name",
            "RECEIVED AMOUNT",
            "Total",
        ]
        
        for name in names:
            assert not _has_legal_suffix(name), f"'{name}' should NOT have legal suffix"


# -----------------------------------------------------------------------------
# Test: Merchant Extraction - Seller vs Buyer
# -----------------------------------------------------------------------------

class TestMerchantExtractionSellerVsBuyer:
    """Test that merchant extraction correctly identifies seller, not buyer."""
    
    def test_seller_selected_over_buyer(self):
        """Seller company should be selected over buyer company."""
        lines = [
            "INVOICE",
            "Acme Corporation Inc",
            "123 Seller Street",
            "Phone: 555-0100",
            "",
            "BILL TO:",
            "Customer Company LLC",
            "456 Buyer Ave",
        ]
        
        result = extract_merchant_from_lines(lines)
        
        # Should select seller, not buyer
        assert result.merchant == "Acme Corporation Inc", \
            f"Expected 'Acme Corporation Inc', got: {result.merchant}"
        
        # Should NOT select buyer
        assert result.merchant != "Customer Company LLC"
    
    def test_buyer_zone_company_rejected(self):
        """Company in buyer zone should be rejected even with legal suffix."""
        lines = [
            "INVOICE",
            "Seller Ltd",
            "",
            "BILL TO:",
            "Buyer Corporation Inc",
            "Address",
        ]
        
        result = extract_merchant_from_lines(lines)
        
        # Should select seller
        assert result.merchant == "Seller Ltd", \
            f"Expected 'Seller Ltd', got: {result.merchant}"
    
    def test_financial_labels_never_selected(self):
        """Financial labels should never be selected as merchant."""
        lines = [
            "COMMERCIAL INVOICE",
            "Secured General Insurance INC",
            "123 Insurance Plaza",
            "",
            "SUBTOTAL",
            "500,000.00",
            "TAX",
            "25,000.00",
            "RECEIVED AMOUNT",
            "525,000.00",
            "BALANCE",
            "0.00",
        ]
        
        result = extract_merchant_from_lines(lines)
        
        # Should select the company name
        assert result.merchant == "Secured General Insurance INC", \
            f"Expected 'Secured General Insurance INC', got: {result.merchant}"
        
        # Should NEVER select financial labels
        assert result.merchant not in ["RECEIVED AMOUNT", "BALANCE", "SUBTOTAL", "TAX"]


# -----------------------------------------------------------------------------
# Test: Multi-Name Documents
# -----------------------------------------------------------------------------

class TestMultiNameDocuments:
    """Test documents with multiple company names."""
    
    def test_seller_plus_multiple_buyers(self):
        """Document with seller and multiple buyer addresses."""
        lines = [
            "TAX INVOICE",
            "Global Trading Company Ltd",
            "100 Export Way",
            "Phone: +1-555-0000",
            "",
            "BILL TO:",
            "First Buyer Inc",
            "Billing Address 1",
            "",
            "SHIP TO:",
            "Second Destination LLC",
            "Shipping Address 2",
        ]
        
        result = extract_merchant_from_lines(lines)
        
        # Should select seller
        assert result.merchant == "Global Trading Company Ltd", \
            f"Expected 'Global Trading Company Ltd', got: {result.merchant}"
        
        # Should NOT select any buyer
        assert result.merchant not in ["First Buyer Inc", "Second Destination LLC"]
    
    def test_seller_at_bottom_with_doc_title(self):
        """Seller appearing after doc title at unusual position."""
        lines = [
            "AMOUNT",
            "500,000",
            "TAX",
            "25,000",
            "",
            "BILL TO:",
            "Customer Corp",
            "Customer Address",
            "",
            "SALES INVOICE",
            "Vendor Company Inc",
            "Vendor Address Line 1",
            "Phone: 555-1234",
        ]
        
        result = extract_merchant_from_lines(lines)
        
        # Should select vendor (seller) that appears after doc title
        # Note: This tests the doc-title-followed-by-company pattern
        assert result.merchant in ["Vendor Company Inc", None], \
            f"Got unexpected merchant: {result.merchant}"
        
        # Should NOT select customer (buyer)
        assert result.merchant != "Customer Corp"


# -----------------------------------------------------------------------------
# Test: Mocked OCR Tokens
# -----------------------------------------------------------------------------

class TestMockedOCRTokens:
    """Test with mocked OCR output formats."""
    
    def test_easyocr_style_tokens(self):
        """Test extraction from EasyOCR-style tokens with bounding boxes."""
        # Simulate EasyOCR output: (bbox, text, confidence)
        # bbox format: [[x0,y0], [x1,y0], [x1,y1], [x0,y1]]
        ocr_results = [
            ([[10, 10], [200, 10], [200, 30], [10, 30]], "INVOICE", 0.95),
            ([[10, 50], [300, 50], [300, 80], [10, 80]], "ABC Electronics Ltd", 0.92),
            ([[10, 90], [250, 90], [250, 110], [10, 110]], "123 Tech Street", 0.88),
            ([[10, 130], [150, 130], [150, 150], [10, 150]], "Phone: 555-1234", 0.90),
            ([[10, 200], [100, 200], [100, 220], [10, 220]], "BILL TO:", 0.94),
            ([[10, 240], [200, 240], [200, 260], [10, 260]], "Customer Inc", 0.91),
        ]
        
        doc = create_easyocr_style_tokens(ocr_results)
        zones = detect_zones(doc)
        result = extract_merchant_from_tokens(doc, zones)
        
        # Should select seller from header area
        assert result.merchant == "ABC Electronics Ltd", \
            f"Expected 'ABC Electronics Ltd', got: {result.merchant}"
        
        # Evidence should indicate coords were used
        assert result.evidence.get("has_coords") == True
    
    def test_tesseract_style_tokens(self):
        """Test extraction from Tesseract TSV-style tokens."""
        # Simulate Tesseract TSV output
        tsv_data = [
            {"text": "COMMERCIAL", "left": 10, "top": 10, "width": 100, "height": 20, "conf": 90, "line_num": 1},
            {"text": "INVOICE", "left": 120, "top": 10, "width": 80, "height": 20, "conf": 92, "line_num": 1},
            {"text": "XYZ", "left": 10, "top": 50, "width": 40, "height": 20, "conf": 88, "line_num": 2},
            {"text": "Manufacturing", "left": 60, "top": 50, "width": 100, "height": 20, "conf": 85, "line_num": 2},
            {"text": "LLC", "left": 170, "top": 50, "width": 30, "height": 20, "conf": 90, "line_num": 2},
            {"text": "BILL", "left": 10, "top": 150, "width": 40, "height": 20, "conf": 91, "line_num": 5},
            {"text": "TO:", "left": 60, "top": 150, "width": 30, "height": 20, "conf": 93, "line_num": 5},
            {"text": "Buyer", "left": 10, "top": 180, "width": 50, "height": 20, "conf": 89, "line_num": 6},
            {"text": "Corp", "left": 70, "top": 180, "width": 40, "height": 20, "conf": 87, "line_num": 6},
        ]
        
        doc = create_tesseract_style_tokens(tsv_data)
        zones = detect_zones(doc)
        result = extract_merchant_from_tokens(doc, zones)
        
        # Should detect a merchant (XYZ Manufacturing LLC or similar)
        assert result.merchant is not None, "Should detect merchant from Tesseract tokens"
        
        # Should NOT select buyer
        assert "Buyer" not in (result.merchant or "")
    
    def test_low_confidence_ocr(self):
        """Test handling of low confidence OCR results."""
        ocr_results = [
            ([[10, 10], [100, 10], [100, 30], [10, 30]], "INVOICE", 0.95),
            ([[10, 50], [200, 50], [200, 80], [10, 80]], "Seller Inc", 0.25),  # Low confidence
            ([[10, 100], [150, 100], [150, 120], [10, 120]], "BILL TO:", 0.92),
            ([[10, 140], [180, 140], [180, 160], [10, 160]], "Buyer LLC", 0.90),
        ]
        
        doc = create_easyocr_style_tokens(ocr_results)
        result = extract_merchant_from_tokens(doc)
        
        # Should still work even with low confidence
        # The zone detection and scoring should handle this


# -----------------------------------------------------------------------------
# Test: Confidence and Evidence
# -----------------------------------------------------------------------------

class TestConfidenceAndEvidence:
    """Test confidence calculation and evidence preservation."""
    
    def test_high_confidence_with_legal_suffix(self):
        """Company with legal suffix in seller zone should have higher confidence."""
        lines = [
            "INVOICE",
            "Strong Signal Corporation Inc",
            "123 Business Park",
            "Phone: 555-1234",
            "Email: info@company.com",
        ]
        
        result = extract_merchant_from_lines(lines)
        
        # Should have reasonable confidence
        assert result.confidence > 0.3, f"Expected higher confidence, got: {result.confidence}"
        assert result.merchant == "Strong Signal Corporation Inc"
    
    def test_evidence_contains_zone_info(self):
        """Evidence should contain zone detection information."""
        lines = [
            "INVOICE",
            "Seller Ltd",
            "",
            "BILL TO:",
            "Buyer Inc",
        ]
        
        result = extract_merchant_from_lines(lines)
        
        # Evidence should contain zone info
        assert "seller_zone_indices" in result.evidence
        assert "buyer_zone_indices" in result.evidence
        assert "anchor_hits" in result.evidence
    
    def test_low_margin_returns_none_or_low_confidence(self):
        """When winner margin is low, should return None or low confidence."""
        # Create scenario where candidates have similar scores (no seller zone boost)
        lines = [
            "BILL TO:",
            "Company A Inc",
            "Company B Ltd", 
            "Company C LLC",
        ]
        
        result = extract_merchant_from_lines(lines)
        
        # All companies are in buyer zone, so should have low/no confidence
        # or return None
        if result.merchant:
            # At least check that the algorithm makes a reasonable choice
            assert result.merchant in ["Company A Inc", "Company B Ltd", "Company C LLC", None]


# -----------------------------------------------------------------------------
# Test: No Per-PDF Special Cases
# -----------------------------------------------------------------------------

class TestNoSpecialCases:
    """Test that extraction works generically without per-document hardcoding."""
    
    def test_various_invoice_layouts(self):
        """Test various common invoice layouts."""
        layouts = [
            # Layout 1: Seller at top
            [
                "TAX INVOICE",
                "ABC Company Ltd",
                "Address Line 1",
                "Phone: 123-456",
                "BILL TO:",
                "Customer",
            ],
            # Layout 2: FROM header
            [
                "INVOICE",
                "FROM:",
                "XYZ Corporation Inc",
                "Seller Address",
                "TO:",
                "Buyer Name",
            ],
            # Layout 3: No explicit headers
            [
                "COMMERCIAL INVOICE",
                "Global Exports LLC",
                "Export Address",
                "Tel: +1-555-0000",
            ],
        ]
        
        expected_merchants = [
            "ABC Company Ltd",
            "XYZ Corporation Inc",
            "Global Exports LLC",
        ]
        
        for layout, expected in zip(layouts, expected_merchants):
            result = extract_merchant_from_lines(layout)
            assert result.merchant == expected, \
                f"For layout starting with '{layout[0]}', expected '{expected}', got: {result.merchant}"
    
    def test_receipt_layout(self):
        """Test receipt-style layout (typically shorter)."""
        lines = [
            "COFFEE SHOP LLC",
            "123 Main St",
            "Date: 2024-01-15",
            "Coffee $5.00",
            "Total $5.00",
        ]
        
        result = extract_merchant_from_lines(lines)
        
        assert result.merchant == "COFFEE SHOP LLC", \
            f"Expected 'COFFEE SHOP LLC', got: {result.merchant}"


# -----------------------------------------------------------------------------
# Test: Plausibility Checks
# -----------------------------------------------------------------------------

class TestPlausibilityChecks:
    """Test company name plausibility checks."""
    
    def test_instructional_text_rejected(self):
        """Instructional text should be rejected."""
        assert not _is_plausible_company_name("Please pay within 30 days")
        assert not _is_plausible_company_name("Thank you for your business")
        assert not _is_plausible_company_name("Contact us at support@company.com")
    
    def test_numeric_heavy_rejected(self):
        """Lines with too many digits should be rejected."""
        assert not _is_plausible_company_name("Invoice #12345678")
        assert not _is_plausible_company_name("123-456-7890")
        assert not _is_plausible_company_name("2024-01-15 10:30:00")
    
    def test_labels_with_colons_rejected(self):
        """Label patterns with colons should be rejected."""
        assert not _is_plausible_company_name("Date: 2024-01-15")
        assert not _is_plausible_company_name("Invoice No: 12345")
        assert not _is_plausible_company_name("Total: $500.00")
    
    def test_valid_company_names_accepted(self):
        """Valid company names should be accepted."""
        assert _is_plausible_company_name("ABC Corporation Inc")
        assert _is_plausible_company_name("Global Trade LLC")
        assert _is_plausible_company_name("Smith & Associates Ltd")


# -----------------------------------------------------------------------------
# Test: Zone Confidence Gating (C-lite + B3-lite)
# -----------------------------------------------------------------------------

class TestZoneConfidenceGating:
    """Test zone confidence computation and gating behavior."""
    
    def test_low_zone_confidence_zones_not_applied(self):
        """
        Case A: When zone_confidence is low, zone-based boosts/penalties 
        should NOT be applied to scoring, but merchant should still be selected.
        """
        # Create a minimal document with very few tokens (< 10)
        # This should trigger low zone confidence
        lines = [
            "ABC Company Inc",
            "123 Main St",
            "Bill To:",
            "Customer Corp",
        ]
        
        result = extract_merchant_from_lines(lines)
        
        # With few tokens, zone confidence should be low
        assert result.evidence.get("zone_confidence", 1.0) < 0.5, \
            f"Expected low zone_confidence for minimal doc, got: {result.evidence.get('zone_confidence')}"
        
        # Zone scoring should be gated
        assert result.evidence.get("zone_gated") is True, \
            "Expected zone_gated=True for low confidence"
        
        # Should still select a merchant (based on legal suffix, not zone)
        assert result.merchant is not None, \
            "Expected a merchant to be selected even with zone gating"
        assert "Inc" in result.merchant or "Corp" in result.merchant, \
            f"Expected a company name, got: {result.merchant}"
    
    def test_missing_buyer_zone_tokens_triggers_gating(self):
        """
        When buyer zone tokens are missing, zone_confidence must be < 0.5 
        AND zone_gated must be True to prevent unreliable zone scoring.
        """
        # Document with seller zone but NO buyer zone tokens
        # (no Bill To/Ship To anchors, just header content)
        lines = [
            "ACME Corporation Ltd",
            "123 Business Park",
            "Phone: 555-1234",
            "Email: sales@acme.com",
            "",
            "Invoice #12345",
            "Date: 2024-01-15",
            "",
            "Description: Services",
            "Amount: $1000.00",
            "Total: $1000.00",
        ]
        
        result = extract_merchant_from_lines(lines)
        
        # Check zone_confidence_reasons includes missing zone indicator
        reasons = result.evidence.get("zone_confidence_reasons", [])
        has_missing_zone_reason = any(
            "no_buyer_zone" in r or "no_seller_zone" in r or "no_zone" in r 
            for r in reasons
        )
        
        if has_missing_zone_reason:
            # If missing zone tokens, confidence must be low
            zone_conf = result.evidence.get("zone_confidence", 1.0)
            assert zone_conf < 0.5, \
                f"Missing zone tokens should result in zone_confidence < 0.5, got: {zone_conf}"
            
            # Gating must be enabled
            assert result.evidence.get("zone_gated") is True, \
                f"zone_gated must be True when zone tokens are missing, got: {result.evidence.get('zone_gated')}"
            
            # zone_gated_reason must be populated
            assert result.evidence.get("zone_gated_reason") is not None, \
                "zone_gated_reason must be populated when gating is active"
            
            # Candidates should NOT have seller_zone/buyer_zone in reasons
            for cand in result.candidates:
                assert "seller_zone" not in cand.reasons, \
                    f"seller_zone should not be in reasons when gated: {cand.reasons}"
                assert "buyer_zone" not in cand.reasons, \
                    f"buyer_zone should not be in reasons when gated: {cand.reasons}"
        
        # Merchant should still be selected via other signals (legal suffix)
        assert result.merchant is not None, "Merchant should still be selected"
    
    def test_high_zone_confidence_zones_applied(self):
        """
        Case B: When zone_confidence is high, zone-based boosts/penalties
        should be applied to scoring normally.
        """
        # Create a document with enough tokens and clear zone anchors
        lines = [
            "INVOICE",
            "Acme Corporation Ltd",
            "123 Business Park",
            "Phone: 555-1234",
            "Email: info@acme.com",
            "",
            "Bill To:",
            "Customer Inc",
            "456 Client Ave",
            "Phone: 555-5678",
            "",
            "Ship To:",
            "Customer Inc - Warehouse",
            "789 Shipping Rd",
            "",
            "Item Description",
            "Widget A - $100.00",
            "Widget B - $200.00",
            "",
            "Subtotal: $300.00",
            "Tax: $30.00",
            "Total: $330.00",
            "",
            "Thank you for your business",
            "",
            "Terms: Net 30",
            "",
            "Notes: Please include invoice number",
            "",
            "www.acme-corp.com",
        ]
        
        result = extract_merchant_from_lines(lines)
        
        # With many tokens and buyer anchors, zone confidence should be high
        zone_conf = result.evidence.get("zone_confidence", 0.0)
        assert zone_conf >= 0.5, \
            f"Expected high zone_confidence (>=0.5), got: {zone_conf}"
        
        # Zone scoring should NOT be gated
        assert result.evidence.get("zone_gated") is False, \
            f"Expected zone_gated=False for high confidence, got: {result.evidence.get('zone_gated')}"
        
        # Seller should be selected (not buyer)
        assert result.merchant is not None, "Expected a merchant"
        assert "Acme" in result.merchant, \
            f"Expected seller 'Acme Corporation Ltd', got: {result.merchant}"
        
        # Verify seller_zone boost was applied
        if result.candidates:
            winner = result.candidates[0]
            assert "seller_zone" in winner.reasons, \
                f"Expected 'seller_zone' in winner reasons, got: {winner.reasons}"
    
    def test_zone_confidence_reasons_populated(self):
        """Zone confidence reasons should be populated in evidence."""
        lines = [
            "Test Company LLC",
            "Address Line",
        ]
        
        result = extract_merchant_from_lines(lines)
        
        # Should have zone_confidence_reasons
        reasons = result.evidence.get("zone_confidence_reasons", [])
        assert isinstance(reasons, list), "zone_confidence_reasons should be a list"
        assert len(reasons) > 0, "zone_confidence_reasons should not be empty"
    
    def test_layout_diagnostics_populated(self):
        """Layout diagnostics should be populated in evidence."""
        lines = [
            "Company Name Inc",
            "123 Main Street",
            "City, State 12345",
        ]
        
        result = extract_merchant_from_lines(lines)
        
        # Should have layout_diagnostics
        diag = result.evidence.get("layout_diagnostics")
        assert diag is not None, "layout_diagnostics should be present"
        assert "token_count" in diag, "layout_diagnostics should have token_count"
        assert diag["token_count"] > 0, "token_count should be positive"
    
    def test_zone_reliable_boolean_gates_scoring(self):
        """
        When zone_reliable is False, seller_zone/buyer_zone score deltas
        should NOT be applied to candidates.
        """
        # Create a minimal document that triggers unreliable zone detection
        lines = [
            "ABC Corp Inc",
            "Bill To:",
            "Customer LLC",
        ]
        
        result = extract_merchant_from_lines(lines)
        
        # Check zone_reliable is populated
        zone_reliable = result.evidence.get("zone_reliable")
        assert zone_reliable is not None, "zone_reliable should be present in evidence"
        
        # Check zone_reliable_reasons is populated
        zone_reliable_reasons = result.evidence.get("zone_reliable_reasons", [])
        assert isinstance(zone_reliable_reasons, list), "zone_reliable_reasons should be a list"
        
        # With few tokens, zone should be unreliable
        if not zone_reliable:
            # When unreliable, candidates should NOT have zone boosts/penalties in reasons
            for cand in result.candidates:
                # seller_zone and buyer_zone should NOT be in reasons when unreliable
                assert "seller_zone" not in cand.reasons or zone_reliable, \
                    f"seller_zone should not be in reasons when zone_reliable=False: {cand.reasons}"
                assert "buyer_zone" not in cand.reasons or zone_reliable, \
                    f"buyer_zone should not be in reasons when zone_reliable=False: {cand.reasons}"
        
        # A merchant should still be selected based on other signals
        assert result.merchant is not None, "Merchant should still be selected with zone gating"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
