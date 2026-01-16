"""
Golden tests for merchant extraction and structural label filtering.

These tests verify that merchant extraction correctly:
- Rejects structural labels like "BILL TO", "SHIP TO", "INVOICE"
- Prefers next-line company names after "BILL TO" / "SHIP TO"
- Rejects label-like content like "Date of Export", "Invoice No"
- Never treats document titles as merchants

Running:
    python -m pytest tests/test_merchant_extraction_golden.py -v

Coverage:
    - Structural label rejection (BILL TO, SHIP TO, INVOICE, etc.)
    - Next-line company name preference
    - Label-like content rejection
    - Document title rejection (COMMERCIAL INVOICE, etc.)
"""

import pytest
from typing import Optional

from app.pipelines.features import _guess_merchant_line, _looks_like_company_name


# -----------------------------------------------------------------------------
# Test: Structural label rejection
# -----------------------------------------------------------------------------

def test_structural_labels_rejected():
    """BILL TO, SHIP TO, INVOICE, etc. should never become merchant."""
    
    # Test cases: structural labels that should be rejected
    structural_labels = [
        ["BILL TO", "Acme Corp Inc", "123 Main St"],
        ["SHIP TO", "Global Logistics Ltd", "456 Oak Ave"],
        ["INVOICE", "Invoice #12345", "Date: 2024-01-01"],
        ["Invoice No", "INV-2024-001", "Customer: ABC"],
        ["DATE", "2024-01-01", "Total: $100"],
        ["DESCRIPTION", "Item 1", "Item 2"],
        ["SUBTOTAL", "$90.00", "Tax: $10.00"],
        ["TOTAL", "$100.00", "Payment: Cash"],
        ["TAX", "Sales Tax 8%", "Amount: $8.00"],
    ]
    
    for lines in structural_labels:
        merchant = _guess_merchant_line(lines)
        label = lines[0]
        
        # Merchant should NOT be the structural label itself
        assert merchant != label, f"Structural label '{label}' was incorrectly selected as merchant"
        
        # For BILL TO / SHIP TO, merchant should be next line if it looks like company
        if label.upper() in ["BILL TO", "SHIP TO"]:
            if len(lines) > 1 and _looks_like_company_name(lines[1]):
                assert merchant == lines[1], f"Expected next-line company name '{lines[1]}' after '{label}'"
            else:
                assert merchant is None or merchant == lines[2] if len(lines) > 2 else True
        else:
            # For other labels, merchant should be None or a later line
            assert merchant is None or merchant not in [label], f"Merchant should not be '{label}'"


def test_bill_to_ship_to_next_line_preference():
    """When BILL TO / SHIP TO is followed by company name, prefer the company name."""
    
    # BILL TO followed by company name
    lines1 = ["BILL TO", "Acme Corporation Inc", "123 Main Street"]
    merchant1 = _guess_merchant_line(lines1)
    assert merchant1 == "Acme Corporation Inc", "Should select company name after BILL TO"
    
    # SHIP TO followed by company name
    lines2 = ["SHIP TO", "Global Logistics Ltd", "456 Oak Avenue"]
    merchant2 = _guess_merchant_line(lines2)
    assert merchant2 == "Global Logistics Ltd", "Should select company name after SHIP TO"
    
    # BILL TO followed by non-company (should skip both)
    lines3 = ["BILL TO", "12345", "Some Company"]
    merchant3 = _guess_merchant_line(lines3)
    assert merchant3 != "BILL TO", "Should not select BILL TO label"
    assert merchant3 != "12345", "Should not select numeric line"
    # Should get "Some Company" or None depending on other filters


def test_label_like_content_rejected():
    """Date of Export, Invoice No, etc. should be rejected as merchants."""
    
    label_like_lines = [
        ["Date of Export", "2024-01-01", "Exporter: ABC Corp"],
        ["Invoice No", "INV-12345", "Customer: XYZ"],
        ["Order:", "ORD-98765", "Vendor: Test Inc"],
        ["Total:", "$100.00", "Payment Method: Cash"],
        ["Date:", "January 1, 2024", "Time: 10:00 AM"],
    ]
    
    for lines in label_like_lines:
        merchant = _guess_merchant_line(lines)
        label = lines[0]
        
        # Should NOT select the label-like first line
        assert merchant != label, f"Label-like content '{label}' was incorrectly selected as merchant"


# -----------------------------------------------------------------------------
# Test: Document title rejection
# -----------------------------------------------------------------------------

def test_document_titles_rejected():
    """COMMERCIAL INVOICE, PROFORMA INVOICE, etc. should never become merchant."""
    
    document_titles = [
        ["COMMERCIAL INVOICE", "Exporter: ABC Corp", "Date: 2024-01-01"],
        ["PROFORMA INVOICE", "Seller: XYZ Ltd", "Invoice #: 12345"],
        ["TAX INVOICE", "Business Name: Test Co", "ABN: 12345678"],
        ["PACKING LIST", "Shipper: Global Logistics", "Date: 2024-01-01"],
        ["PURCHASE ORDER", "Vendor: Supply Inc", "PO #: PO-001"],
        ["SALES ORDER", "Customer: Retail Store", "SO #: SO-123"],
        ["DELIVERY NOTE", "Carrier: Fast Shipping", "DN #: DN-456"],
        ["BILL OF LADING", "Consignee: Import Co", "BOL #: BOL-789"],
    ]
    
    for lines in document_titles:
        merchant = _guess_merchant_line(lines)
        title = lines[0]
        
        # Should NOT select the document title
        assert merchant != title, f"Document title '{title}' was incorrectly selected as merchant"
        
        # Should select a plausible company name from later lines if available
        # (or None if no plausible merchant found)


def test_commercial_invoice_regression():
    """Specific regression test for COMMERCIAL INVOICE bug."""
    
    # Real-world example that was failing
    lines = [
        "COMMERCIAL INVOICE",
        "Date of Export",
        "Exporter Details:",
        "ABC Trading Company Ltd",
        "123 Business Park",
    ]
    
    merchant = _guess_merchant_line(lines)
    
    # Should NOT be "COMMERCIAL INVOICE" or "Date of Export"
    assert merchant != "COMMERCIAL INVOICE", "COMMERCIAL INVOICE should never be merchant"
    assert merchant != "Date of Export", "Date of Export should never be merchant"
    
    # Should ideally be "ABC Trading Company Ltd" or None
    # (depending on how other filters evaluate the lines)
    if merchant:
        assert "ABC Trading Company" in merchant or merchant == "Exporter Details:", \
            f"Expected plausible merchant, got: {merchant}"


def test_logistics_structural_labels_rejected():
    """Logistics headers like Date of Export, Country of Export should be rejected."""
    
    logistics_labels = [
        ["Date of Export", "2024-01-15", "Exporter: ABC Corp"],
        ["Country of Export", "India", "Shipper: XYZ Ltd"],
        ["Country of Ultimate Destination", "United States", "Consignee: Global Inc"],
        ["Airway Bill No", "AWB-12345", "Carrier: Fast Air"],
        ["AWB No", "98765432", "Flight: AA123"],
        ["Inv Number", "INV-2024-001", "Customer: Test Co"],
        ["Invoice Number", "12345", "Vendor: Supply Inc"],
    ]
    
    for lines in logistics_labels:
        merchant = _guess_merchant_line(lines)
        label = lines[0]
        
        # Should NOT select the logistics label
        assert merchant != label, f"Logistics label '{label}' was incorrectly selected as merchant"


def test_exporter_shipper_next_line_preference():
    """EXPORTER/SHIPPER followed by company name should select the company."""
    
    # EXPORTER followed by company name
    lines1 = ["EXPORTER", "Global Trading Company Ltd", "123 Export Street"]
    merchant1 = _guess_merchant_line(lines1)
    assert merchant1 == "Global Trading Company Ltd", "Should select company name after EXPORTER"
    
    # SHIPPER followed by company name
    lines2 = ["SHIPPER", "ABC Logistics Pvt Ltd", "456 Shipping Lane"]
    merchant2 = _guess_merchant_line(lines2)
    assert merchant2 == "ABC Logistics Pvt Ltd", "Should select company name after SHIPPER"
    
    # CONSIGNEE followed by company name
    lines3 = ["CONSIGNEE", "XYZ Import Corporation", "789 Destination Blvd"]
    merchant3 = _guess_merchant_line(lines3)
    assert merchant3 == "XYZ Import Corporation", "Should select company name after CONSIGNEE"
    
    # Exporter (mixed case) followed by company name
    lines4 = ["Exporter", "International Trade Inc", "Country: India"]
    merchant4 = _guess_merchant_line(lines4)
    assert merchant4 == "International Trade Inc", "Should select company name after Exporter"


def test_logistics_document_with_multiple_labels():
    """Real-world logistics document with multiple structural labels."""
    
    lines = [
        "COMMERCIAL INVOICE",
        "Date of Export: 2024-01-15",
        "Country of Export: India",
        "EXPORTER",
        "ABC Trading Company Pvt Ltd",
        "123 Business Park, Mumbai",
        "CONSIGNEE",
        "XYZ Corporation Inc",
        "456 Main Street, New York",
    ]
    
    merchant = _guess_merchant_line(lines)
    
    # Should NOT be any of the labels
    assert merchant != "COMMERCIAL INVOICE"
    assert merchant != "Date of Export: 2024-01-15"
    assert merchant != "Country of Export: India"
    assert merchant != "EXPORTER"
    assert merchant != "CONSIGNEE"
    
    # Should be the first company name after EXPORTER
    assert merchant == "ABC Trading Company Pvt Ltd", \
        f"Expected 'ABC Trading Company Pvt Ltd', got: {merchant}"


# -----------------------------------------------------------------------------
# Test: Company name detection helper
# -----------------------------------------------------------------------------

def test_looks_like_company_name():
    """Test _looks_like_company_name helper function."""
    
    # Should be recognized as company names
    valid_companies = [
        "Acme Corporation Inc",
        "Global Logistics Ltd",
        "ABC Trading Company Pvt Ltd",
        "XYZ Services LLC",
        "Tech Solutions Corp",
        "RETAIL STORE INC",
        "Manufacturing Co",
    ]
    
    for name in valid_companies:
        assert _looks_like_company_name(name), f"'{name}' should be recognized as company name"
    
    # Should NOT be recognized as company names
    invalid_companies = [
        "12345",  # All numeric
        "INV-2024-001",  # Identifier
        "Date: 2024-01-01",  # Label with colon
        "123456789012345",  # Too many digits
        "AB",  # Too short
        "",  # Empty
        "   ",  # Whitespace only
    ]
    
    for name in invalid_companies:
        assert not _looks_like_company_name(name), f"'{name}' should NOT be recognized as company name"


# -----------------------------------------------------------------------------
# Test: Edge cases
# -----------------------------------------------------------------------------

def test_empty_and_whitespace_lines():
    """Empty lines and whitespace should be skipped."""
    
    lines = ["", "  ", "\t", "Valid Company Name", "123 Main St"]
    merchant = _guess_merchant_line(lines)
    
    assert merchant == "Valid Company Name", "Should skip empty/whitespace lines"


def test_mostly_numeric_lines_rejected():
    """Lines with >40% digits should be rejected."""
    
    lines = [
        "12345678",  # 100% digits
        "Invoice 12345",  # ~50% digits
        "ABC-123-456-789",  # High digit ratio
        "Acme Corp",  # Low digit ratio - should be selected
    ]
    
    merchant = _guess_merchant_line(lines)
    
    assert merchant == "Acme Corp", "Should skip mostly-numeric lines and select company name"


def test_no_plausible_merchant():
    """When no plausible merchant exists, should return None."""
    
    lines = [
        "INVOICE",
        "12345",
        "Date: 2024-01-01",
        "Total: $100.00",
    ]
    
    merchant = _guess_merchant_line(lines)
    
    # Should return None since no plausible merchant candidate exists
    assert merchant is None, "Should return None when no plausible merchant found"
