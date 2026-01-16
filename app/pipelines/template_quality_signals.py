"""
Template Quality Cluster (TQC) - Signal Detectors

This module contains isolated signal detectors for template quality anomalies.
Each signal returns (score_delta, evidence) and NEVER emits events directly.

CLUSTER_ID: TQC_TEMPLATE_QUALITY
RULE_ID: R10_TEMPLATE_QUALITY
"""

import unicodedata
from typing import Dict, List, Tuple, Optional, Any


# =============================================================================
# Multilingual Keyword Dictionaries
# =============================================================================

SEMANTIC_KEYWORDS_BY_LANG = {
    # Latin script languages (fastText detection)
    "en": {
        "invoice", "total", "subtotal", "tax", "amount", "due", 
        "maximum", "minimum", "quantity", "price", "discount", 
        "balance", "payment", "receipt", "date", "customer",
        "merchant", "description", "item", "number", "address"
    },
    "es": {
        "factura", "total", "subtotal", "impuesto", "iva", "importe", 
        "vencimiento", "máximo", "mínimo", "cantidad", "precio", 
        "descuento", "saldo", "pago", "recibo", "fecha", "cliente",
        "comerciante", "descripción", "artículo", "número", "dirección"
    },
    "fr": {
        "facture", "total", "sous-total", "taxe", "tva", "montant", 
        "dû", "maximum", "minimum", "quantité", "prix", "remise", 
        "solde", "paiement", "reçu", "date", "client",
        "commerçant", "description", "article", "numéro", "adresse"
    },
    "de": {
        "rechnung", "gesamt", "zwischensumme", "steuer", "mwst", 
        "betrag", "fällig", "maximum", "minimum", "menge", "preis", 
        "rabatt", "saldo", "zahlung", "quittung", "datum", "kunde",
        "händler", "beschreibung", "artikel", "nummer", "adresse"
    },
    "pt": {
        "fatura", "total", "subtotal", "imposto", "iva", "valor",
        "vencimento", "máximo", "mínimo", "quantidade", "preço",
        "desconto", "saldo", "pagamento", "recibo", "data", "cliente",
        "comerciante", "descrição", "item", "número", "endereço"
    },
    "it": {
        "fattura", "totale", "subtotale", "tassa", "iva", "importo",
        "scadenza", "massimo", "minimo", "quantità", "prezzo",
        "sconto", "saldo", "pagamento", "ricevuta", "data", "cliente",
        "commerciante", "descrizione", "articolo", "numero", "indirizzo"
    },
    "nl": {
        "factuur", "totaal", "subtotaal", "belasting", "btw", "bedrag",
        "vervaldatum", "maximum", "minimum", "hoeveelheid", "prijs",
        "korting", "saldo", "betaling", "ontvangst", "datum", "klant",
        "handelaar", "beschrijving", "artikel", "nummer", "adres"
    },
    
    # Non-Latin script languages (script-based detection)
    # Note: These use transliterated/romanized keywords for OCR that may
    # produce Latin characters, but primary detection is script-based
    "ar": {
        # Arabic keywords (common OCR may produce these)
        "فاتورة", "المجموع", "الإجمالي", "ضريبة", "المبلغ",
        "الاستحقاق", "الحد الأقصى", "الحد الأدنى", "الكمية", "السعر",
        "الخصم", "الرصيد", "الدفع", "إيصال", "التاريخ", "العميل",
        "التاجر", "الوصف", "البند", "الرقم", "العنوان"
    },
    "he": {
        # Hebrew keywords
        "חשבונית", "סכום", "סכום ביניים", "מס", "סכום",
        "תאריך פירעון", "מקסימום", "מינימום", "כמות", "מחיר",
        "הנחה", "יתרה", "תשלום", "קבלה", "תאריך", "לקוח",
        "סוחר", "תיאור", "פריט", "מספר", "כתובת"
    },
    "ru": {
        # Russian keywords (Cyrillic)
        "счет", "итого", "промежуточный итог", "налог", "сумма",
        "срок оплаты", "максимум", "минимум", "количество", "цена",
        "скидка", "баланс", "оплата", "квитанция", "дата", "клиент",
        "продавец", "описание", "товар", "номер", "адрес"
    },
    "zh": {
        # Chinese keywords (Simplified Chinese - Han script)
        "发票", "总计", "小计", "税", "金额",
        "到期", "最大", "最小", "数量", "价格",
        "折扣", "余额", "付款", "收据", "日期", "客户",
        "商家", "描述", "项目", "编号", "地址"
    },
    "ja": {
        # Japanese keywords (Hiragana/Katakana/Kanji mix)
        "請求書", "合計", "小計", "税", "金額",
        "期日", "最大", "最小", "数量", "価格",
        "割引", "残高", "支払い", "領収書", "日付", "顧客",
        "商人", "説明", "項目", "番号", "住所"
    },
    "ko": {
        # Korean keywords (Hangul)
        "송장", "합계", "소계", "세금", "금액",
        "만기일", "최대", "최소", "수량", "가격",
        "할인", "잔액", "지불", "영수증", "날짜", "고객",
        "상인", "설명", "항목", "번호", "주소"
    },
}


# =============================================================================
# Language-Specific Typo Patterns
# =============================================================================
# Common OCR errors and keyboard mistakes by language

COMMON_TYPO_PATTERNS = {
    "en": {
        # Common OCR confusions
        ("maximum", "maximun"),  # m/n confusion
        ("minimum", "minimun"),
        ("receipt", "reciept"),  # ie/ei confusion
        ("payment", "payrnent"),  # m/rn confusion
        ("amount", "arnount"),
        ("invoice", "lnvoice"),  # I/l confusion
        ("total", "tota1"),      # l/1 confusion
        ("customer", "custorner"), # m/rn confusion
        ("balance", "ba1ance"),  # l/1 confusion
    },
    "es": {
        # Spanish-specific OCR errors
        ("factura", "factnra"),  # u/n confusion
        ("máximo", "rnaximo"),   # m/rn confusion
        ("mínimo", "rninimo"),
        ("cantidad", "cantldad"), # i/l confusion
        ("descripción", "descrlpción"),
    },
    "fr": {
        # French-specific OCR errors
        ("facture", "factnre"),
        ("quantité", "quantlté"),
        ("reçu", "recu"),  # accent dropped
        ("dû", "du"),
    },
    "de": {
        # German-specific OCR errors
        ("rechnung", "rechnurig"), # n/ri confusion
        ("betrag", "betmg"),       # ra/m confusion
        ("fällig", "fallig"),      # accent dropped
    },
}


def normalize_text(text: str) -> str:
    """
    Normalize text by removing accents and diacritics.
    
    OCR often drops accents, so we normalize both keywords and text
    to ensure consistent matching across languages.
    
    Examples:
        "máximo" → "maximo"
        "reçu" → "recu"
        "dû" → "du"
    
    Args:
        text: Input text with potential accents
    
    Returns:
        Normalized text without accents
    """
    # Decompose unicode characters (e.g., é → e + ´)
    nfkd = unicodedata.normalize("NFKD", text)
    
    # Filter out combining characters (accents, diacritics)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calculate Levenshtein (edit) distance between two strings.
    
    Args:
        s1: First string
        s2: Second string
    
    Returns:
        Edit distance (number of single-character edits)
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost of insertions, deletions, or substitutions
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


# =============================================================================
# S1: Keyword Typo Detector (Language-Gated)
# =============================================================================

def detect_keyword_typos(tf: Dict[str, Any], lang: Optional[str]) -> Tuple[float, Optional[List[Dict]]]:
    """
    S1: Detect typos in semantic keywords (e.g., "maximun" instead of "maximum").
    
    NO LLM. NO INFERENCE. Only checks present words against known keywords.
    Uses accent normalization for OCR-safe multilingual matching.
    Enhanced with language-specific typo patterns for faster detection.
    
    Args:
        tf: Feature dictionary
        lang: Language code (e.g., "en", "es")
    
    Returns:
        (score_delta, evidence) where score_delta is 0.0-0.4, evidence is list of typos
    """
    if not lang or lang not in SEMANTIC_KEYWORDS_BY_LANG:
        return 0.0, None
    
    keywords = SEMANTIC_KEYWORDS_BY_LANG[lang]
    text = tf.get("full_text", "").lower()
    
    if not text:
        return 0.0, None
    
    # Normalize text for OCR-safe matching (strips accents)
    text_normalized = normalize_text(text)
    
    # Tokenize (simple split on whitespace and common punctuation)
    import re
    tokens = re.findall(r'\b\w+\b', text_normalized)
    tokens_set = set(tokens)  # For faster lookup
    
    typos = []
    
    # Phase 1: Check known typo patterns (fast path)
    if lang in COMMON_TYPO_PATTERNS:
        for correct, typo_variant in COMMON_TYPO_PATTERNS[lang]:
            correct_normalized = normalize_text(correct)
            typo_normalized = normalize_text(typo_variant)
            
            # If typo variant is present but correct form is not
            if typo_normalized in tokens_set and correct_normalized not in text_normalized:
                typos.append({
                    "expected": correct,
                    "found": typo_variant,
                    "edit_distance": levenshtein_distance(typo_normalized, correct_normalized),
                    "pattern_match": True,  # Known typo pattern
                })
    
    # Phase 2: Levenshtein distance for unknown typos (slower path)
    for keyword in keywords:
        # Normalize keyword for comparison
        keyword_normalized = normalize_text(keyword)
        
        # Skip if exact keyword is present (normalized comparison)
        if keyword_normalized in text_normalized:
            continue
        
        # Skip if already found via pattern matching
        if any(t["expected"] == keyword for t in typos):
            continue
        
        # Check if prefix matches (potential typo)
        prefix_len = min(4, len(keyword_normalized))
        if keyword_normalized[:prefix_len] not in text_normalized:
            continue
        
        # Look for near-matches in tokens
        for token in tokens:
            # Only check tokens of similar length
            if abs(len(token) - len(keyword_normalized)) > 2:
                continue
            
            distance = levenshtein_distance(token, keyword_normalized)
            
            # Edit distance of 1 or 2 = likely typo
            if distance in (1, 2):
                typos.append({
                    "expected": keyword,  # Show original keyword with accents
                    "found": token,
                    "edit_distance": distance,
                    "pattern_match": False,  # Discovered via Levenshtein
                })
    
    if not typos:
        return 0.0, None
    
    # Score: 0.2 per typo, capped at 0.4 total for this signal
    # Known patterns get slightly higher weight (0.25 vs 0.2)
    score_delta = 0.0
    for typo in typos:
        weight = 0.25 if typo.get("pattern_match") else 0.2
        score_delta += weight
    
    score_delta = min(0.4, score_delta)
    
    return score_delta, typos[:5]  # Return max 5 examples


# =============================================================================
# S2: Spacing Anomaly Detector (Language-Agnostic)
# =============================================================================

def detect_spacing_anomaly(tf: Dict[str, Any]) -> Tuple[float, Optional[List[str]]]:
    """
    S2: Detect unusual spacing patterns (multiple spaces, tabs, misalignment).
    
    LANGUAGE-AGNOSTIC. Works for Arabic, Chinese, English, etc.
    
    Args:
        tf: Feature dictionary
    
    Returns:
        (score_delta, evidence) where score_delta is 0.0-0.4, evidence is list of suspicious lines
    """
    text_lines = tf.get("text_lines")
    
    if not text_lines:
        # Fallback: split full_text by newlines
        full_text = tf.get("full_text", "")
        if not full_text:
            return 0.0, None
        text_lines = full_text.split("\n")
    
    suspicious = []
    
    for line in text_lines:
        # Skip empty lines
        if not line.strip():
            continue
        
        # Check for multiple consecutive spaces (likely alignment issue)
        if "  " in line:
            suspicious.append(line.strip()[:80])  # Truncate long lines
        
        # Check for tabs (unusual in OCR output)
        elif "\t" in line:
            suspicious.append(line.strip()[:80])
    
    # Need at least 2 suspicious lines to be significant
    if len(suspicious) < 2:
        return 0.0, None
    
    # Score: 0.4 if many lines affected
    score_delta = min(0.4, len(suspicious) * 0.1)
    
    return score_delta, suspicious[:3]  # Return max 3 examples


# =============================================================================
# S3: Date Format Mismatch Detector (Geo-Gated, Weak)
# =============================================================================

def detect_date_format_anomaly(tf: Dict[str, Any]) -> Tuple[float, Optional[List[str]]]:
    """
    S3: Detect ambiguous or mismatched date formats (e.g., DD/MM/YYYY vs MM/DD/YYYY).
    
    VERY WEAK SIGNAL. Only fires when unambiguous (day > 12).
    
    Args:
        tf: Feature dictionary
    
    Returns:
        (score_delta, evidence) where score_delta is 0.0-0.2, evidence is list of anomalous dates
    """
    dates_detected = tf.get("dates_detected")
    
    if not dates_detected:
        return 0.0, None
    
    anomalies = []
    
    for date_str in dates_detected:
        # Look for DD/MM/YYYY pattern where DD > 12 (unambiguous)
        # Example: "25/03/2024" is clearly DD/MM, but "03/25/2024" is ambiguous
        
        import re
        match = re.match(r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})', str(date_str))
        
        if match:
            first, second, year = match.groups()
            first_int = int(first)
            second_int = int(second)
            
            # If first part > 12, it's definitely day-first format
            # If second part > 12, it's definitely month-first format
            # Only flag if there's a mismatch with expected regional format
            
            # For now, just flag dates with day > 12 in first position
            # (This is a placeholder - real implementation would check geo_hint)
            if first_int > 12:
                anomalies.append(date_str)
    
    if not anomalies:
        return 0.0, None
    
    # Very weak signal: 0.2 max
    score_delta = min(0.2, len(anomalies) * 0.1)
    
    return score_delta, anomalies[:3]  # Return max 3 examples
