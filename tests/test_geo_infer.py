"""
Unit tests for geo inference module.
Tests postal patterns, city matching, term matching, and scoring rubric.
"""

import pytest
from app.geo.infer import infer_geo


def test_india_receipt_high_confidence():
    """Test Indian receipt with PIN code, city, and GSTIN."""
    text = """
    ABC Store
    123 Main Street, Chennai 600001
    Tamil Nadu, India
    GSTIN: 29ABCDE1234F1Z5
    
    Invoice #12345
    Date: 2024-01-15
    
    Item 1: Rs. 500
    Item 2: Rs. 300
    CGST: Rs. 40
    SGST: Rs. 40
    Total: Rs. 880
    """
    
    result = infer_geo(text)
    
    assert result["geo_country_guess"] == "IN", f"Expected IN, got {result['geo_country_guess']}"
    assert result["geo_confidence"] > 0.70, f"Expected confidence > 0.70, got {result['geo_confidence']}"
    assert not result["geo_mixed"], "Should not be mixed signals"
    
    # Check evidence types
    evidence_types = {e["type"] for e in result["geo_evidence"]}
    assert "postal_match" in evidence_types, "Should have postal match"
    assert "city_match" in evidence_types, "Should have city match"
    assert "tax_term" in evidence_types, "Should have tax term"


def test_germany_receipt_high_confidence():
    """Test German receipt with postal code, city, and MwSt."""
    text = """
    Supermarkt Berlin
    Hauptstraße 45
    10115 Berlin
    Deutschland
    
    Rechnung Nr. 98765
    Datum: 15.01.2024
    
    Artikel 1: 25,00 EUR
    Artikel 2: 15,50 EUR
    MwSt. 19%: 7,70 EUR
    USt-IdNr: DE123456789
    Gesamt: 48,20 EUR
    """
    
    result = infer_geo(text)
    
    assert result["geo_country_guess"] == "DE", f"Expected DE, got {result['geo_country_guess']}"
    assert result["geo_confidence"] > 0.60, f"Expected confidence > 0.60, got {result['geo_confidence']}"
    assert not result["geo_mixed"], "Should not be mixed signals"
    
    # Check evidence
    evidence_types = {e["type"] for e in result["geo_evidence"]}
    assert "postal_match" in evidence_types, "Should have postal match"
    assert "city_match" in evidence_types, "Should have city match"
    assert "tax_term" in evidence_types, "Should have tax term"


def test_us_receipt_with_zip():
    """Test US receipt with ZIP code and city."""
    text = """
    Joe's Diner
    123 Main Street
    New York, NY 10001
    
    Invoice #5678
    Date: 01/15/2024
    
    Burger: $12.99
    Fries: $4.99
    Sales Tax: $1.44
    Total: $19.42 USD
    """
    
    result = infer_geo(text)
    
    assert result["geo_country_guess"] == "US", f"Expected US, got {result['geo_country_guess']}"
    assert result["geo_confidence"] > 0.50, f"Expected confidence > 0.50, got {result['geo_confidence']}"


def test_ambiguous_5digit_no_other_signals():
    """Test ambiguous 5-digit code without other signals - should be low confidence or UNKNOWN."""
    text = """
    Store Name
    123 Street
    90210
    
    Item 1: 50.00
    Item 2: 30.00
    Total: 80.00
    """
    
    result = infer_geo(text)
    
    # Should have low confidence or be UNKNOWN since no other signals
    assert result["geo_confidence"] < 0.50, f"Expected low confidence, got {result['geo_confidence']}"


def test_mixed_signals_chennai_usd_berlin():
    """Test mixed signals with Chennai (IN), USD (US), and Berlin (DE)."""
    text = """
    International Store
    Chennai 600001
    Berlin Office
    
    Amount: $500 USD
    GSTIN: 29ABCDE1234F1Z5
    """
    
    result = infer_geo(text)
    
    # IN should win due to strong signals (postal + city + GSTIN)
    # Mixed signals may or may not be detected depending on score gap
    assert result["geo_country_guess"] == "IN", f"Expected IN, got {result['geo_country_guess']}"
    
    # Should have multiple candidates
    assert len(result["candidates"]) > 1, "Should have multiple country candidates"
    
    # IN should have significantly higher score than others
    assert result["candidates"][0]["country"] == "IN"
    assert result["candidates"][0]["score"] > 0.70, f"IN score should be > 0.70, got {result['candidates'][0]['score']}"


def test_uk_postcode():
    """Test UK receipt with postcode."""
    text = """
    London Shop Ltd
    123 High Street
    London SW1A 1AA
    United Kingdom
    
    Invoice #1234
    VAT Reg No: GB123456789
    
    Item 1: £25.00
    VAT 20%: £5.00
    Total: £30.00 GBP
    """
    
    result = infer_geo(text)
    
    assert result["geo_country_guess"] == "UK", f"Expected UK, got {result['geo_country_guess']}"
    assert result["geo_confidence"] > 0.60, f"Expected confidence > 0.60, got {result['geo_confidence']}"


def test_canada_postal_code():
    """Test Canadian receipt with postal code."""
    text = """
    Tim's Coffee Shop
    456 Maple Street
    Toronto, ON M5H 2N2
    Canada
    
    Receipt #7890
    GST/HST: 13%
    
    Coffee: $4.50 CAD
    Tax: $0.59
    Total: $5.09
    """
    
    result = infer_geo(text)
    
    assert result["geo_country_guess"] == "CA", f"Expected CA, got {result['geo_country_guess']}"
    assert result["geo_confidence"] > 0.55, f"Expected confidence > 0.55, got {result['geo_confidence']}"


def test_singapore_6digit():
    """Test Singapore receipt with 6-digit postal code."""
    text = """
    Singapore Store Pte Ltd
    123 Orchard Road
    Singapore 238858
    
    Invoice #4567
    UEN: 201234567D
    GST Reg No: M12345678X
    
    Item 1: S$50.00
    GST 8%: S$4.00
    Total: S$54.00 SGD
    """
    
    result = infer_geo(text)
    
    assert result["geo_country_guess"] == "SG", f"Expected SG, got {result['geo_country_guess']}"
    assert result["geo_confidence"] > 0.60, f"Expected confidence > 0.60, got {result['geo_confidence']}"


def test_uae_dubai():
    """Test UAE receipt with Dubai and AED."""
    text = """
    Dubai Mall Store
    Downtown Dubai
    Dubai, UAE
    
    TRN: 123456789012345
    
    Item 1: AED 200
    VAT 5%: AED 10
    Total: AED 210
    """
    
    result = infer_geo(text)
    
    assert result["geo_country_guess"] == "AE", f"Expected AE, got {result['geo_country_guess']}"
    assert result["geo_confidence"] > 0.40, f"Expected confidence > 0.40, got {result['geo_confidence']}"


def test_australia_postcode():
    """Test Australian receipt with 4-digit postcode."""
    text = """
    Sydney Shop Pty Ltd
    123 George Street
    Sydney NSW 2000
    Australia
    
    Invoice #3456
    ABN: 12 345 678 901
    
    Item 1: A$75.00
    GST 10%: A$7.50
    Total: A$82.50 AUD
    """
    
    result = infer_geo(text)
    
    assert result["geo_country_guess"] == "AU", f"Expected AU, got {result['geo_country_guess']}"
    assert result["geo_confidence"] > 0.60, f"Expected confidence > 0.60, got {result['geo_confidence']}"


def test_empty_text():
    """Test empty text returns UNKNOWN."""
    result = infer_geo("")
    
    assert result["geo_country_guess"] == "UNKNOWN"
    assert result["geo_confidence"] == 0.0
    assert len(result["geo_evidence"]) == 0


def test_no_geo_signals():
    """Test text with no geo signals returns UNKNOWN."""
    text = """
    Store Name
    Some Street
    
    Item 1: 50
    Item 2: 30
    Total: 80
    """
    
    result = infer_geo(text)
    
    assert result["geo_country_guess"] == "UNKNOWN"
    assert result["geo_confidence"] < 0.35


def test_evidence_structure():
    """Test that evidence has correct structure."""
    text = "Chennai 600001 GSTIN: 29ABCDE1234F1Z5"
    
    result = infer_geo(text)
    
    assert "geo_evidence" in result
    assert isinstance(result["geo_evidence"], list)
    
    if result["geo_evidence"]:
        evidence = result["geo_evidence"][0]
        assert "type" in evidence
        assert "country" in evidence
        assert "match" in evidence
        assert "weight" in evidence


def test_candidates_sorted():
    """Test that candidates are sorted by score descending."""
    text = "Chennai 600001 Berlin 10115 New York 10001"
    
    result = infer_geo(text)
    
    assert "candidates" in result
    candidates = result["candidates"]
    
    if len(candidates) > 1:
        for i in range(len(candidates) - 1):
            assert candidates[i]["score"] >= candidates[i + 1]["score"], \
                "Candidates should be sorted by score descending"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
