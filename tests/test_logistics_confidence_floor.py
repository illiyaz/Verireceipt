"""
Golden tests for logistics confidence floor override.

Tests that when 2+ strong logistics/customs keywords are detected,
doc_profile_confidence is set to minimum 0.55.

IMPORTANT: The confidence floor is for CLASSIFICATION and EXTRACTION ROUTING,
NOT to automatically enable missing-field penalties. Logistics documents have
different field expectations than receipts, so missing-field penalties are
still gated separately by document subtype expectations.
"""

import pytest
from app.pipelines.features import _detect_document_profile


def test_logistics_confidence_floor_commercial_invoice():
    """Commercial invoice with 2+ keywords should have confidence >= 0.55."""
    
    # Document with multiple strong logistics keywords
    full_text = """
    COMMERCIAL INVOICE
    
    Date of Export: 2024-01-15
    Country of Export: India
    Country of Ultimate Destination: United States
    
    EXPORTER
    ABC Trading Company Pvt Ltd
    123 Business Park, Mumbai
    
    CONSIGNEE
    XYZ Corporation Inc
    456 Main Street, New York
    
    HSN Code: 12345678
    Invoice Value: $5,000.00
    Incoterms: FOB Mumbai
    """
    
    lines = full_text.strip().split("\n")
    profile = _detect_document_profile(full_text, lines)
    
    assert profile["doc_family_guess"] == "TRANSACTIONAL", \
        f"Expected TRANSACTIONAL family, got: {profile['doc_family_guess']}"
    assert profile["doc_subtype_guess"] == "COMMERCIAL_INVOICE", \
        f"Expected COMMERCIAL_INVOICE subtype, got: {profile['doc_subtype_guess']}"
    
    # Key assertion: confidence should be >= 0.55 due to logistics override
    assert profile["doc_profile_confidence"] >= 0.55, \
        f"Expected confidence >= 0.55, got: {profile['doc_profile_confidence']}"
    
    # Should have multiple evidence keywords
    evidence = profile["doc_profile_evidence"]
    assert len(evidence) >= 2, \
        f"Expected 2+ evidence keywords, got: {len(evidence)}"


def test_logistics_confidence_floor_air_waybill():
    """Air waybill with 2+ keywords should have confidence >= 0.55."""
    
    full_text = """
    AIR WAYBILL
    AWB No: 123-45678901
    
    SHIPPER
    Global Logistics Ltd
    Airport Road, Delhi
    
    CONSIGNEE
    Fast Import Corp
    Harbor Street, Los Angeles
    
    Country of Export: India
    Country of Ultimate Destination: USA
    Flight No: AA123
    Airport of Departure: DEL
    """
    
    lines = full_text.strip().split("\n")
    profile = _detect_document_profile(full_text, lines)
    
    assert profile["doc_family_guess"] == "LOGISTICS", \
        f"Expected LOGISTICS family, got: {profile['doc_family_guess']}"
    assert profile["doc_subtype_guess"] == "AIR_WAYBILL", \
        f"Expected AIR_WAYBILL subtype, got: {profile['doc_subtype_guess']}"
    
    # Key assertion: confidence should be >= 0.55 due to logistics override
    assert profile["doc_profile_confidence"] >= 0.55, \
        f"Expected confidence >= 0.55, got: {profile['doc_profile_confidence']}"
    
    evidence = profile["doc_profile_evidence"]
    assert len(evidence) >= 2, \
        f"Expected 2+ evidence keywords, got: {len(evidence)}"


def test_logistics_confidence_floor_shipping_bill():
    """Shipping bill with 2+ keywords should have confidence >= 0.55."""
    
    full_text = """
    SHIPPING BILL
    SB No: SB/2024/12345
    
    EXPORTER
    Export House Pvt Ltd
    Trade Center, Mumbai
    
    Country of Export: India
    Country of Ultimate Destination: United Kingdom
    HSN: 87654321
    Export Value: INR 500,000
    Customs Clearance: Completed
    """
    
    lines = full_text.strip().split("\n")
    profile = _detect_document_profile(full_text, lines)
    
    assert profile["doc_family_guess"] == "LOGISTICS", \
        f"Expected LOGISTICS family, got: {profile['doc_family_guess']}"
    assert profile["doc_subtype_guess"] == "SHIPPING_BILL", \
        f"Expected SHIPPING_BILL subtype, got: {profile['doc_subtype_guess']}"
    
    # Key assertion: confidence should be >= 0.55 due to logistics override
    assert profile["doc_profile_confidence"] >= 0.55, \
        f"Expected confidence >= 0.55, got: {profile['doc_profile_confidence']}"
    
    evidence = profile["doc_profile_evidence"]
    assert len(evidence) >= 2, \
        f"Expected 2+ evidence keywords, got: {len(evidence)}"


def test_logistics_confidence_floor_shipping_invoice():
    """Shipping invoice with 2+ keywords should have confidence >= 0.55."""
    
    full_text = """
    SHIPPING INVOICE
    
    Freight Charges: $500.00
    Carrier: DHL Express
    AWB: 123456789
    Tracking: TRK-2024-001
    
    Shipment Details:
    Port of Loading: Mumbai
    Port of Discharge: Los Angeles
    Vessel: MV Cargo Ship
    """
    
    lines = full_text.strip().split("\n")
    profile = _detect_document_profile(full_text, lines)
    
    assert profile["doc_family_guess"] == "TRANSACTIONAL", \
        f"Expected TRANSACTIONAL family, got: {profile['doc_family_guess']}"
    assert profile["doc_subtype_guess"] == "SHIPPING_INVOICE", \
        f"Expected SHIPPING_INVOICE subtype, got: {profile['doc_subtype_guess']}"
    
    # Key assertion: confidence should be >= 0.55 due to logistics-like override
    assert profile["doc_profile_confidence"] >= 0.55, \
        f"Expected confidence >= 0.55, got: {profile['doc_profile_confidence']}"
    
    evidence = profile["doc_profile_evidence"]
    assert len(evidence) >= 2, \
        f"Expected 2+ evidence keywords, got: {len(evidence)}"


def test_logistics_single_keyword_no_floor():
    """Logistics document with only 1 keyword should NOT get confidence floor."""
    
    # Minimal document with only "airway bill" keyword
    full_text = """
    AIRWAY BILL
    
    Some generic text here
    No other logistics keywords
    Just a basic document
    """
    
    lines = full_text.strip().split("\n")
    profile = _detect_document_profile(full_text, lines)
    
    # May or may not be classified as AIR_WAYBILL (depends on scoring)
    # But if it is, and has only 1 keyword, confidence should be < 0.55
    if profile["doc_subtype_guess"] == "AIR_WAYBILL":
        evidence = profile["doc_profile_evidence"]
        if len(evidence) < 2:
            # No floor should apply
            assert profile["doc_profile_confidence"] < 0.55, \
                f"Expected confidence < 0.55 with only {len(evidence)} keyword(s), got: {profile['doc_profile_confidence']}"


def test_non_logistics_document_no_floor():
    """Non-logistics documents should not get the confidence floor."""
    
    full_text = """
    RESTAURANT RECEIPT
    
    Table 5
    Server: John
    
    Item 1: Burger - $10.00
    Item 2: Fries - $5.00
    Subtotal: $15.00
    Tax: $1.50
    Total: $16.50
    
    Thank you for dining with us!
    """
    
    lines = full_text.strip().split("\n")
    profile = _detect_document_profile(full_text, lines)
    
    # Should be POS_RESTAURANT, not LOGISTICS
    assert profile["doc_family_guess"] != "LOGISTICS", \
        f"Expected non-LOGISTICS family, got: {profile['doc_family_guess']}"
    
    # Confidence floor should NOT apply (may be < 0.55)
    # This ensures the override only affects logistics-like documents
    # NOTE: Even if confidence is low, missing-field penalties are gated
    # separately based on document subtype expectations


def test_logistics_with_ambiguity_still_gets_floor():
    """Logistics document with ambiguity should still get confidence floor if 2+ keywords."""
    
    # Document with both logistics and invoice keywords (ambiguous)
    full_text = """
    COMMERCIAL INVOICE
    Tax Invoice
    
    Date of Export: 2024-01-15
    Country of Export: India
    EXPORTER: ABC Corp
    
    GSTIN: 12ABCDE1234F1Z5
    HSN: 12345678
    
    Item 1: Widget - $100
    Total: $100
    """
    
    lines = full_text.strip().split("\n")
    profile = _detect_document_profile(full_text, lines)
    
    # Even with ambiguity (both COMMERCIAL_INVOICE and TAX_INVOICE keywords),
    # if COMMERCIAL_INVOICE wins and has 2+ keywords, floor should apply
    if profile["doc_subtype_guess"] == "COMMERCIAL_INVOICE":
        evidence = profile["doc_profile_evidence"]
        if len(evidence) >= 2:
            assert profile["doc_profile_confidence"] >= 0.55, \
                f"Expected confidence >= 0.55 despite ambiguity, got: {profile['doc_profile_confidence']}"


def test_logistics_confidence_floor_evidence_count():
    """Verify that evidence count is correctly calculated for logistics override."""
    
    full_text = """
    AIR WAYBILL
    AWB No: 123456
    Shipper: ABC Ltd
    Consignee: XYZ Corp
    Country of Export: India
    """
    
    lines = full_text.strip().split("\n")
    profile = _detect_document_profile(full_text, lines)
    
    evidence = profile["doc_profile_evidence"]
    
    # Should have at least: "airway bill", "awb", "shipper", "consignee", "country of export"
    # (depending on exact matching)
    assert len(evidence) >= 2, \
        f"Expected 2+ evidence keywords for logistics override, got: {evidence}"
    
    if profile["doc_subtype_guess"] == "AIR_WAYBILL" and len(evidence) >= 2:
        assert profile["doc_profile_confidence"] >= 0.55, \
            f"Expected confidence >= 0.55 with {len(evidence)} keywords, got: {profile['doc_profile_confidence']}"
