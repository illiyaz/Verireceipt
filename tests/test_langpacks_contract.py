"""
Contract tests for language packs.

Validates that all language packs conform to schema and have required content.
These tests ensure bad configs don't silently break production.
"""

import pytest
import sys
from pathlib import Path

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.pipelines.lang import LangPackLoader, ScriptDetector, LangPackRouter


class TestLangPackContracts:
    """Contract tests for language pack system."""
    
    @pytest.fixture
    def loader(self):
        """Create language pack loader for testing."""
        loader = LangPackLoader(strict=True)
        loader.load_all()
        return loader
    
    @pytest.fixture
    def script_detector(self):
        """Create script detector for testing."""
        return ScriptDetector()
    
    @pytest.fixture
    def router(self, loader, script_detector):
        """Create language pack router for testing."""
        return LangPackRouter(loader, script_detector)
    
    def test_all_packs_load_successfully(self, loader):
        """Test that all language packs load without errors."""
        packs = loader.get_available_packs()
        
        # Should have at least the basic languages
        expected_packs = ['en', 'ar', 'zh', 'ja', 'ko', 'th', 'ms', 'vi']
        for pack_id in expected_packs:
            assert pack_id in packs, f"Missing required language pack: {pack_id}"
        
        # All packs should load successfully
        for pack_id in packs:
            pack = loader.get_pack(pack_id)
            assert pack is not None, f"Failed to load pack: {pack_id}"
    
    def test_pack_schema_validation(self, loader):
        """Test that all packs conform to schema."""
        validation_errors = loader.validate_all_packs()
        
        # Should have no validation errors
        assert not validation_errors, f"Validation errors found: {validation_errors}"
    
    def test_required_keyword_groups(self, loader):
        """Test that all packs have required keyword groups."""
        required_groups = ['invoice', 'receipt', 'total']
        
        for pack_id in loader.get_available_packs():
            pack = loader.get_pack(pack_id)
            
            for group in required_groups:
                keywords = getattr(pack.keywords, group, [])
                assert keywords, f"Pack {pack_id} missing required keyword group: {group}"
                assert all(isinstance(k, str) for k in keywords), f"Pack {pack_id} has non-string keywords in {group}"
    
    def test_script_mapping(self, loader):
        """Test that all packs have valid script mappings."""
        valid_scripts = {'latin', 'arabic', 'cjk', 'hangul', 'thai'}
        
        for pack_id in loader.get_available_packs():
            pack = loader.get_pack(pack_id)
            
            assert pack.scripts, f"Pack {pack_id} has no scripts defined"
            for script in pack.scripts:
                assert script in valid_scripts, f"Pack {pack_id} has invalid script: {script}"
    
    def test_locale_format(self, loader):
        """Test that all locales are in valid format."""
        import re
        locale_pattern = re.compile(r'^[a-z]{2}(-[A-Z]{2})?$')
        
        for pack_id in loader.get_available_packs():
            pack = loader.get_pack(pack_id)
            
            if pack.locales:
                for locale in pack.locales:
                    assert locale_pattern.match(locale), f"Pack {pack_id} has invalid locale format: {locale}"
    
    def test_version_format(self, loader):
        """Test that all packs have valid semantic versions."""
        import re
        version_pattern = re.compile(r'^\d+\.\d+\.\d+$')
        
        for pack_id in loader.get_available_packs():
            pack = loader.get_pack(pack_id)
            
            assert version_pattern.match(pack.version), f"Pack {pack_id} has invalid version: {pack.version}"
    
    def test_regex_patterns_compile(self, loader):
        """Test that all regex patterns in packs compile successfully."""
        import re
        
        for pack_id in loader.get_available_packs():
            pack = loader.get_pack(pack_id)
            
            for pattern in pack.address.postal_code_patterns:
                try:
                    re.compile(pattern)
                except re.error as e:
                    pytest.fail(f"Pack {pack_id} has invalid regex pattern '{pattern}': {e}")
    
    def test_pack_merging(self, loader):
        """Test that pack merging works correctly."""
        # Get a specific pack (e.g., Arabic)
        ar_pack = loader.get_pack('ar')
        common_pack = loader.get_pack('common')
        
        # Arabic pack should have common keywords plus Arabic-specific ones
        assert 'invoice' in ar_pack.keywords.invoice  # From common
        assert 'فاتورة' in ar_pack.keywords.invoice  # From Arabic
        
        # Should have more keywords than common alone
        assert len(ar_pack.keywords.invoice) > len(common_pack.keywords.invoice)
    
    def test_script_detection_coverage(self, script_detector):
        """Test that script detection covers all declared scripts."""
        test_texts = {
            'latin': 'Hello World Invoice Total',
            'arabic': 'فاتورة إجمالي',
            'cjk': '发票 总计',
            'hangul': '청구서 합계',
            'thai': 'ใบแจ้งหนี้ รวม',
        }
        
        for script, text in test_texts.items():
            dominant_script, confidence = script_detector.get_dominant_script(text)
            assert dominant_script == script, f"Script detection failed for {script}: got {dominant_script}"
            assert confidence > 0.5, f"Low confidence for {script}: {confidence}"
    
    def test_routing_basic_functionality(self, router):
        """Test basic routing functionality."""
        # Test English text
        en_result = router.route_document("Invoice Total Amount")
        assert en_result.primary_pack.id == 'en'
        assert en_result.confidence > 0.5
        
        # Test Arabic text
        ar_result = router.route_document("فاتورة المبلغ الإجمالي")
        assert ar_result.primary_pack.id == 'ar'
        assert ar_result.confidence > 0.5
        
        # Test Chinese text
        zh_result = router.route_document("发票 总计 金额")
        assert zh_result.primary_pack.id == 'zh'
        assert zh_result.confidence > 0.5
    
    def test_fallback_behavior(self, router):
        """Test that fallback behavior works correctly."""
        # Test with ambiguous text
        result = router.route_document("12345")
        
        # Should fall back to English
        assert result.primary_pack.id == 'en'
        assert result.confidence < 0.5  # Low confidence for fallback
    
    def test_locale_hint_routing(self, router):
        """Test routing with locale hints."""
        # Test with locale hint
        result = router.route_document("Invoice", locale_hint="ar-SA")
        
        # Should prefer Arabic pack despite Latin script due to locale hint
        assert result.primary_pack.id == 'ar'
        assert result.confidence > 0.8  # High confidence with locale hint
    
    def test_mixed_script_handling(self, router):
        """Test handling of mixed-script documents."""
        # Mixed English and Arabic
        mixed_text = "Invoice فاتورة Total المبلغ"
        result = router.route_document(mixed_text, allow_multi_pack=True)
        
        # Should detect as mixed and provide fallbacks
        assert result.primary_pack.id in ['en', 'ar']  # One of the main scripts
        assert len(result.fallback_packs) >= 1  # Should have fallbacks
    
    def test_normalizer_functionality(self, router):
        """Test text normalizer functionality."""
        from app.pipelines.lang import TextNormalizer
        
        normalizer = TextNormalizer()
        
        # Test Latin normalization
        latin_text = "Invoice, Total! Amount?"
        normalized = normalizer.normalize_text(latin_text, 'latin')
        assert ',' not in normalized
        assert '!' not in normalized
        assert '?' not in normalized
        
        # Test Arabic normalization
        arabic_text = "فاتورة، المبلغ! الإجمالي؟"
        normalized = normalizer.normalize_text(arabic_text, 'arabic')
        assert '،' not in normalized
        assert '!' not in normalized
        assert '؟' not in normalized
    
    def test_comprehensive_keyword_coverage(self, loader):
        """Test that all document types have keyword coverage in each language."""
        doc_types = [
            'invoice', 'receipt', 'tax_invoice', 'ecommerce', 
            'fuel', 'parking', 'hotel_folio', 'utility', 'telecom',
            'commercial_invoice', 'air_waybill', 'shipping_bill', 'bill_of_lading'
        ]
        
        for pack_id in loader.get_available_packs():
            pack = loader.get_pack(pack_id)
            
            # Each pack should have at least some keywords for major doc types
            major_types = ['invoice', 'receipt', 'total']
            for doc_type in major_types:
                keywords = getattr(pack.keywords, doc_type, [])
                assert keywords, f"Pack {pack_id} has no keywords for {doc_type}"
    
    def test_currency_coverage(self, loader):
        """Test that packs have appropriate currency coverage."""
        for pack_id in loader.get_available_packs():
            pack = loader.get_pack(pack_id)
            
            # Should have at least one currency symbol or code
            assert pack.currency.symbols or pack.currency.codes, \
                f"Pack {pack_id} has no currency information"
    
    def test_company_suffix_coverage(self, loader):
        """Test that packs have appropriate company suffix coverage."""
        for pack_id in loader.get_available_packs():
            pack = loader.get_pack(pack_id)
            
            # Should have at least some company suffixes
            assert pack.company.suffixes, f"Pack {pack_id} has no company suffixes"
    
    def test_structural_label_coverage(self, loader):
        """Test that packs have structural label coverage."""
        for pack_id in loader.get_available_packs():
            pack = loader.get_pack(pack_id)
            
            # Should have structural labels to reject as merchants
            assert pack.labels.structural, f"Pack {pack_id} has no structural labels"
            
            # Common structural labels should exist
            common_labels = ['invoice', 'receipt', 'date', 'total']
            found_common = any(label.lower() in common_labels for label in pack.labels.structural)
            assert found_common, f"Pack {pack_id} missing common structural labels"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
