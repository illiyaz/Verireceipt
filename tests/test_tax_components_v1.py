"""
Unit tests for Tax Components V1 extraction.

Tests:
1. Single tax rate with inference (GST 18% -> amount inferred from subtotal)
2. Multi-component taxes (CGST 9% + SGST 9%)
3. Explicit tax amounts (no inference needed)
4. Mixed scenarios
"""
import pytest
from app.pipelines.features import extract_tax_components


class TestTaxComponentsV1:
    """Tests for extract_tax_components function."""
    
    def test_single_tax_rate_with_inference(self):
        """
        Given: Subtotal 11,396, GST 18%
        Expect: tax_total = 2051.28 (11396 * 0.18)
        """
        lines = [
            "Invoice",
            "Subtotal 11,396",
            "GST 18%",
            "Grand Total 13,447.28",
        ]
        
        result = extract_tax_components(lines, subtotal=11396.0)
        
        assert result["tax_total"] is not None, "tax_total should be computed"
        assert abs(result["tax_total"] - 2051.28) < 0.01, f"Expected ~2051.28, got {result['tax_total']}"
        assert result["tax_mode"] == "explicit_rate_inferred_amount"
        assert result["tax_inferred"] is True
        assert "GST" in result["tax_labels_seen"]
    
    def test_single_tax_rate_no_subtotal_no_inference(self):
        """
        Given: GST 18% but no subtotal
        Expect: tax_total = None (cannot infer without subtotal)
        """
        lines = [
            "Invoice",
            "GST 18%",
            "Grand Total 13,447.28",
        ]
        
        result = extract_tax_components(lines, subtotal=None)
        
        # Should have component with rate but no amount
        assert result["tax_total"] is None, "tax_total should be None without subtotal for inference"
        assert len(result["tax_components"]) == 1
        assert result["tax_components"][0]["rate"] == 18.0
        assert result["tax_components"][0]["amount"] is None
    
    def test_multi_component_cgst_sgst_with_rates(self):
        """
        Given: CGST 9% + SGST 9%, subtotal 10,000
        Expect: tax_total = 1800 (900 + 900)
        """
        lines = [
            "Invoice",
            "Subtotal: 10,000",
            "CGST @ 9%",
            "SGST @ 9%",
            "Grand Total: 11,800",
        ]
        
        result = extract_tax_components(lines, subtotal=10000.0)
        
        assert result["tax_total"] is not None
        assert abs(result["tax_total"] - 1800.0) < 0.01, f"Expected 1800, got {result['tax_total']}"
        assert result["tax_inferred"] is True
        assert "CGST" in result["tax_labels_seen"]
        assert "SGST" in result["tax_labels_seen"]
        assert len(result["tax_components"]) == 2
    
    def test_multi_component_cgst_sgst_with_explicit_amounts(self):
        """
        Given: CGST 9%: 900, SGST 9%: 900 (explicit amounts)
        Expect: tax_total = 1800, tax_mode = explicit_amounts
        """
        lines = [
            "Invoice",
            "Subtotal: 10,000",
            "CGST @ 9%: 900",
            "SGST @ 9%: 900",
            "Grand Total: 11,800",
        ]
        
        result = extract_tax_components(lines, subtotal=10000.0)
        
        assert result["tax_total"] == 1800.0, f"Expected 1800, got {result['tax_total']}"
        assert result["tax_mode"] == "explicit_amounts"
        assert result["tax_inferred"] is False
    
    def test_vat_explicit_amount(self):
        """
        Given: VAT: 50.00 (explicit)
        Expect: tax_total = 50.0
        """
        lines = [
            "Receipt",
            "Subtotal: 500.00",
            "VAT: 50.00",
            "Total: 550.00",
        ]
        
        result = extract_tax_components(lines, subtotal=500.0)
        
        assert result["tax_total"] == 50.0
        assert result["tax_mode"] == "explicit_amounts"
        assert result["tax_inferred"] is False
        assert "VAT" in result["tax_labels_seen"]
    
    def test_no_tax_found(self):
        """
        Given: No tax keywords in lines
        Expect: tax_total = None, empty components
        """
        lines = [
            "Receipt",
            "Item 1: 100.00",
            "Item 2: 200.00",
            "Total: 300.00",
        ]
        
        result = extract_tax_components(lines, subtotal=None)
        
        assert result["tax_total"] is None
        assert result["tax_components"] == []
        assert result["tax_mode"] == "unknown"
    
    def test_fee_keywords_excluded(self):
        """
        Given: Processing fee, shipping fee (should be excluded from tax)
        Expect: tax_total = None (fees are not taxes)
        """
        lines = [
            "Receipt",
            "Subtotal: 100.00",
            "Processing fee: 5.00",
            "Shipping fee: 10.00",
            "Total: 115.00",
        ]
        
        result = extract_tax_components(lines, subtotal=100.0)
        
        # Fees should not be counted as tax
        assert result["tax_total"] is None or result["tax_total"] == 0
    
    def test_82020_23_scenario(self):
        """
        Scenario from 82020-23.pdf:
        Subtotal = 11,396
        GST 18%
        Expected tax = 2051.28 (11396 * 0.18)
        """
        lines = [
            "INVOICE",
            "Item Description",
            "Amount: 11,396",
            "GST 18%",
            "GRAND TOTAL",
        ]
        
        result = extract_tax_components(lines, subtotal=11396.0)
        
        assert result["tax_inferred"] is True
        assert result["tax_total"] is not None
        # 11396 * 0.18 = 2051.28
        expected_tax = round(11396 * 0.18, 2)
        assert abs(result["tax_total"] - expected_tax) < 0.01, f"Expected {expected_tax}, got {result['tax_total']}"
    
    def test_sales_tax_extraction(self):
        """
        Given: Sales Tax 7%: 35.00
        Expect: tax_total = 35.0
        """
        lines = [
            "Receipt",
            "Subtotal: 500.00",
            "Sales Tax 7%: 35.00",
            "Total: 535.00",
        ]
        
        result = extract_tax_components(lines, subtotal=500.0)
        
        assert result["tax_total"] == 35.0
        assert "Sales Tax" in result["tax_labels_seen"]
    
    def test_igst_interstate(self):
        """
        Given: IGST 18%: 1800 (interstate GST)
        Expect: tax_total = 1800.0
        """
        lines = [
            "Tax Invoice",
            "Subtotal: 10,000",
            "IGST @ 18%: 1800",
            "Total: 11,800",
        ]
        
        result = extract_tax_components(lines, subtotal=10000.0)
        
        assert result["tax_total"] == 1800.0
        assert "IGST" in result["tax_labels_seen"]
        assert result["tax_mode"] == "explicit_amounts"


class TestTaxComponentsEdgeCases:
    """Edge cases and tricky scenarios."""
    
    def test_tax_in_total_line_ignored(self):
        """
        Given: "Total Tax Invoice" or "Grand Total" with "tax" in name
        Expect: Should not treat these as tax component lines
        """
        lines = [
            "TAX INVOICE",
            "Subtotal: 100.00",
            "Total: 100.00",
        ]
        
        result = extract_tax_components(lines, subtotal=100.0)
        
        # "TAX INVOICE" should not be treated as a tax line
        # Only explicit tax rates/amounts should be captured
        assert result["tax_total"] is None or len(result["tax_components"]) == 0
    
    def test_duplicate_tax_labels_merged(self):
        """
        Given: Two lines mentioning GST
        Expect: Only one component, taking the most informative data
        """
        lines = [
            "Invoice",
            "GST 18%",
            "GST: 180.00",
        ]
        
        result = extract_tax_components(lines, subtotal=1000.0)
        
        # Should have merged into one GST component
        gst_components = [c for c in result["tax_components"] if c["label"] == "GST"]
        assert len(gst_components) == 1, "Should merge duplicate GST labels"
        # Should have both rate and amount
        assert gst_components[0]["rate"] == 18.0
        assert gst_components[0]["amount"] == 180.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
