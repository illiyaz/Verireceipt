"""
Golden tests for multilingual document processing.

Tests real-world multilingual documents to ensure language packs
work correctly in end-to-end scenarios.
"""

import pytest
import sys
from pathlib import Path

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.pipelines.lang import LangPackLoader, ScriptDetector, LangPackRouter, TextNormalizer


class TestLangPackGolden:
    """Golden tests for multilingual document processing."""
    
    @pytest.fixture
    def lang_system(self):
        """Create complete language system for testing."""
        loader = LangPackLoader(strict=True)
        loader.load_all()
        detector = ScriptDetector()
        router = LangPackRouter(loader, detector)
        normalizer = TextNormalizer()
        
        return {
            'loader': loader,
            'detector': detector,
            'router': router,
            'normalizer': normalizer
        }
    
    def test_english_invoice_processing(self, lang_system):
        """Test processing of English invoice."""
        text = """
        INVOICE
        
        Bill To:
        ABC Corporation Ltd.
        123 Business Road
        New York, NY 10001
        United States
        
        Invoice Number: INV-2024-001
        Date: January 15, 2024
        
        Description        Quantity    Unit Price    Total
        Consulting Services    10        $150.00    $1,500.00
        Software License      1         $500.00    $500.00
        
        Subtotal: $2,000.00
        Tax (10%): $200.00
        TOTAL: $2,200.00
        """
        
        router = lang_system['router']
        result = router.route_document(text)
        
        # Should identify as English
        assert result.primary_pack.id == 'en'
        assert result.confidence > 0.8
        
        # Should have appropriate reasoning
        assert any('english' in reason.lower() or 'latin' in reason.lower() 
                  for reason in result.reasoning)
    
    def test_arabic_invoice_processing(self, lang_system):
        """Test processing of Arabic invoice."""
        text = """
        فاتورة ضريبية
        
        الفاتورة لـ:
        شركة التجارة المتحدة ذ.م.م
        شارع الملك فهد، الرياض
        المملكة العربية السعودية
        
        رقم الفاتورة: INV-2024-001
        التاريخ: 15 يناير 2024
        
        الوصف            الكمية    السعر الوحد    الإجمالي
        خدمات استشارية      10        500 ريال      5,000 ريال
        ترخيص برامج         1         2,000 ريال    2,000 ريال
        
        المجموع: 7,000 ريال
        الضريبة (15%): 1,050 ريال
        الإجمالي: 8,050 ريال
        """
        
        router = lang_system['router']
        result = router.route_document(text)
        
        # Should identify as Arabic
        assert result.primary_pack.id == 'ar'
        assert result.confidence > 0.8
        
        # Should detect Arabic script
        assert result.script == 'arabic'
    
    def test_chinese_invoice_processing(self, lang_system):
        """Test processing of Chinese invoice."""
        text = """
        发票
        
        客户：
        北京科技有限公司
        北京市朝阳区建国门外大街1号
        中国北京
        
        发票号码：INV-2024-001
        日期：2024年1月15日
        
        描述          数量    单价      总计
        咨询服务        10      1000元    10,000元
        软件许可        1       5000元    5,000元
        
        小计：15,000元
        税（13%）：1,950元
        总计：16,950元
        """
        
        router = lang_system['router']
        result = router.route_document(text)
        
        # Should identify as Chinese
        assert result.primary_pack.id == 'zh'
        assert result.confidence > 0.8
        
        # Should detect CJK script
        assert result.script == 'cjk'
    
    def test_japanese_receipt_processing(self, lang_system):
        """Test processing of Japanese receipt."""
        text = """
        領収書
        
        お客様：
        株式会社サンプル
        東京都渋谷区道玄坂1-2-3
        日本
        
        領収書番号：REC-2024-001
        日付：2024年1月15日
        
        商品名        数量    単価      合計
        コーヒー        2       500円     1,000円
        サンドイッチ      1       800円     800円
        
        小計：1,800円
        消費税（10%）：180円
        合計：1,980円
        """
        
        router = lang_system['router']
        result = router.route_document(text)
        
        # Should identify as Japanese
        assert result.primary_pack.id == 'ja'
        assert result.confidence > 0.8
    
    def test_korean_invoice_processing(self, lang_system):
        """Test processing of Korean invoice."""
        text = """
        청구서
        
        청구처:
        (주)샘플컴퍼니
        서울특별시 강남구 테헤란로 123
        대한민국
        
        청구서 번호: INV-2024-001
        날짜: 2024년 1월 15일
        
        품목          수량    단가      합계
        컨설팅 서비스      10      150,000원  1,500,000원
        소프트웨어 라이선스    1       500,000원  500,000원
        
        소계: 2,000,000원
        부가세(10%): 200,000원
        총계: 2,200,000원
        """
        
        router = lang_system['router']
        result = router.route_document(text)
        
        # Should identify as Korean
        assert result.primary_pack.id == 'ko'
        assert result.confidence > 0.8
    
    def test_thai_receipt_processing(self, lang_system):
        """Test processing of Thai receipt."""
        text = """
        ใบเสร็จรับเงิน
        
        ลูกค้า:
        บริษัท ตัวอย่าง จำกัด
        ถนนสุขุมวิท 1 กรุงเทพมหานคร
        ประเทศไทย
        
        เลขที่ใบเสร็จ: REC-2024-001
        วันที่: 15 มกราคม 2024
        
        รายการ       จำนวน   ราคาต่อหน่วย   รวม
        กาแฟ           2        50 บาท        100 บาท
        แซนด์วิช        1        80 บาท        80 บาท
        
        รวม: 180 บาท
        ภาษี (7%): 12.60 บาท
        สุทธิ: 192.60 บาท
        """
        
        router = lang_system['router']
        result = router.route_document(text)
        
        # Should identify as Thai
        assert result.primary_pack.id == 'th'
        assert result.confidence > 0.8
    
    def test_malay_invoice_processing(self, lang_system):
        """Test processing of Malay invoice."""
        text = """
        Invois
        
        Kepada:
        Syarikat Contoh Sdn Bhd
        Jalan Sultan Iskandar, Kuala Lumpur
        Malaysia
        
        No. Invois: INV-2024-001
        Tarikh: 15 Januari 2024
        
        Perihal       Kuantiti   Harga Seunit   Jumlah
        Perundingan      10        RM150         RM1,500
        Lesen Perisian    1         RM500         RM500
        
        Jumlah: RM2,000
        SST (6%): RM120
        Jumlah Keseluruhan: RM2,120
        """
        
        router = lang_system['router']
        result = router.route_document(text)
        
        # Should identify as Malay
        assert result.primary_pack.id == 'ms'
        assert result.confidence > 0.8
    
    def test_vietnamese_invoice_processing(self, lang_system):
        """Test processing of Vietnamese invoice."""
        text = """
        Hóa đơn
        
        Khách hàng:
        Công ty TNHH Ví dụ
        Đường Nguyễn Huệ, Quận 1, TP.HCM
        Việt Nam
        
        Số hóa đơn: INV-2024-001
        Ngày: 15 tháng 1 năm 2024
        
        Mô tả          Số lượng   Đơn giá     Thành tiền
        Dịch vụ tư vấn     10        500,000đ    5,000,000đ
        Giấy phép phần mềm   1         2,000,000đ  2,000,000đ
        
        Tạm tính: 7,000,000đ
        Thuế GTGT (10%): 700,000đ
        Tổng cộng: 7,700,000đ
        """
        
        router = lang_system['router']
        result = router.route_document(text)
        
        # Should identify as Vietnamese
        assert result.primary_pack.id == 'vi'
        assert result.confidence > 0.8
    
    def test_logistics_document_multilingual(self, lang_system):
        """Test processing of logistics documents with mixed languages."""
        text = """
        COMMERCIAL INVOICE
        
        Exporter:
        中国出口有限公司
        China Export Co., Ltd.
        
        Consignee:
        شركة الاستيراد العربية
        Arab Import Company
        
        Description: Electronic Components
        Total Amount: $50,000
        Port of Loading: Shanghai
        Port of Discharge: Dubai
        """
        
        router = lang_system['router']
        result = router.route_document(text, allow_multi_pack=True)
        
        # Should detect mixed script and provide appropriate packs
        assert result.is_mixed_script or len(result.fallback_packs) > 0
        assert result.primary_pack.id in ['en', 'zh', 'ar']
    
    def test_text_normalization_multilingual(self, lang_system):
        """Test text normalization across languages."""
        normalizer = lang_system['normalizer']
        
        # Test English normalization
        en_text = "Invoice, Total! Amount?"
        en_normalized = normalizer.normalize_text(en_text, 'latin')
        assert en_normalized == "invoice total amount"
        
        # Test Arabic normalization
        ar_text = "فاتورة، المبلغ! الإجمالي؟"
        ar_normalized = normalizer.normalize_text(ar_text, 'arabic')
        assert '،' not in ar_normalized
        assert '!' not in ar_normalized
        assert '؟' not in ar_normalized
        
        # Test Chinese normalization
        zh_text = "发票，总计！金额？"
        zh_normalized = normalizer.normalize_text(zh_text, 'cjk')
        assert '，' not in zh_normalized
        assert '！' not in zh_normalized
        assert '？' not in zh_normalized
    
    def test_keyword_matching_multilingual(self, lang_system):
        """Test keyword matching across languages."""
        loader = lang_system['loader']
        
        # Test English keywords
        en_pack = loader.get_pack('en')
        assert 'invoice' in en_pack.keywords.invoice
        assert 'total' in en_pack.keywords.total
        
        # Test Arabic keywords
        ar_pack = loader.get_pack('ar')
        assert 'فاتورة' in ar_pack.keywords.invoice
        assert 'الإجمالي' in ar_pack.keywords.total
        
        # Test Chinese keywords
        zh_pack = loader.get_pack('zh')
        assert '发票' in zh_pack.keywords.invoice
        assert '总计' in zh_pack.keywords.total
        
        # Test all packs have essential keywords
        for pack_id in loader.get_available_packs():
            pack = loader.get_pack(pack_id)
            assert pack.keywords.invoice, f"Pack {pack_id} missing invoice keywords"
            assert pack.keywords.total, f"Pack {pack_id} missing total keywords"
            assert pack.keywords.receipt, f"Pack {pack_id} missing receipt keywords"
    
    def test_structural_label_rejection(self, lang_system):
        """Test structural label rejection across languages."""
        loader = lang_system['loader']
        
        # Test English structural labels
        en_pack = loader.get_pack('en')
        assert 'invoice' in en_pack.labels.structural
        assert 'receipt' in en_pack.labels.structural
        assert 'total' in en_pack.labels.structural
        
        # Test Arabic structural labels
        ar_pack = loader.get_pack('ar')
        assert 'فاتورة' in ar_pack.labels.structural
        assert 'إيصال' in ar_pack.labels.structural
        assert 'الإجمالي' in ar_pack.labels.structural
        
        # Test Chinese structural labels
        zh_pack = loader.get_pack('zh')
        assert '发票' in zh_pack.labels.structural
        assert '收据' in zh_pack.labels.structural
        assert '总计' in zh_pack.labels.structural
    
    def test_currency_detection_multilingual(self, lang_system):
        """Test currency detection across languages."""
        loader = lang_system['loader']
        
        # Test English currency
        en_pack = loader.get_pack('en')
        assert '$' in en_pack.currency.symbols
        assert 'USD' in en_pack.currency.codes
        
        # Test Arabic currency
        ar_pack = loader.get_pack('ar')
        assert '﷼' in ar_pack.currency.symbols
        assert 'SAR' in ar_pack.currency.codes
        
        # Test Chinese currency
        zh_pack = loader.get_pack('zh')
        assert '¥' in zh_pack.currency.symbols
        assert 'CNY' in zh_pack.currency.codes
        
        # Test Thai currency
        th_pack = loader.get_pack('th')
        assert '฿' in th_pack.currency.symbols
        assert 'THB' in th_pack.currency.codes
    
    def test_company_suffix_detection_multilingual(self, lang_system):
        """Test company suffix detection across languages."""
        loader = lang_system['loader']
        
        # Test English company suffixes
        en_pack = loader.get_pack('en')
        assert 'ltd' in en_pack.company.suffixes
        assert 'inc' in en_pack.company.suffixes
        
        # Test Arabic company suffixes
        ar_pack = loader.get_pack('ar')
        assert 'ذ.م.م' in ar_pack.company.suffixes
        assert 'شركة' in ar_pack.company.suffixes
        
        # Test Chinese company suffixes
        zh_pack = loader.get_pack('zh')
        assert '有限公司' in zh_pack.company.suffixes
        assert '股份' in zh_pack.company.suffixes
        
        # Test Japanese company suffixes
        ja_pack = loader.get_pack('ja')
        assert '株式会社' in ja_pack.company.suffixes
        assert '有限会社' in ja_pack.company.suffixes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
