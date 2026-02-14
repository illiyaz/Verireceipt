"""
Template Fingerprinting

Creates structural fingerprints from receipt text to enable fast template matching.
Fingerprints capture:
- Line count ranges
- Structural patterns (header, body, footer)
- Keyword presence
- Amount patterns
- Date/time format patterns
"""

import re
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class TemplateFingerprint:
    """Structural fingerprint of a receipt template."""
    
    template_id: str
    template_name: str
    source: str  # "sroie", "custom", "learned"
    
    # Structural features
    line_count_range: Tuple[int, int]  # (min, max) lines
    header_line_count: int  # Lines before first amount
    footer_line_count: int  # Lines after last amount
    
    # Keyword patterns (normalized, lowercased)
    merchant_keywords: Set[str] = field(default_factory=set)
    header_keywords: Set[str] = field(default_factory=set)
    footer_keywords: Set[str] = field(default_factory=set)
    
    # Amount patterns
    amount_count_range: Tuple[int, int] = (1, 50)
    has_tax_line: bool = False
    has_subtotal_line: bool = False
    has_total_line: bool = True
    
    # Date/time patterns
    date_formats: List[str] = field(default_factory=list)
    has_time: bool = False
    
    # Layout features
    has_table_structure: bool = False
    has_separator_lines: bool = False
    typical_line_length: Tuple[int, int] = (10, 80)
    
    # Confidence threshold for this template
    match_threshold: float = 0.7
    
    # Extraction hints for this template
    extraction_hints: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "template_id": self.template_id,
            "template_name": self.template_name,
            "source": self.source,
            "line_count_range": list(self.line_count_range),
            "header_line_count": self.header_line_count,
            "footer_line_count": self.footer_line_count,
            "merchant_keywords": list(self.merchant_keywords),
            "header_keywords": list(self.header_keywords),
            "footer_keywords": list(self.footer_keywords),
            "amount_count_range": list(self.amount_count_range),
            "has_tax_line": self.has_tax_line,
            "has_subtotal_line": self.has_subtotal_line,
            "has_total_line": self.has_total_line,
            "date_formats": self.date_formats,
            "has_time": self.has_time,
            "has_table_structure": self.has_table_structure,
            "has_separator_lines": self.has_separator_lines,
            "typical_line_length": list(self.typical_line_length),
            "match_threshold": self.match_threshold,
            "extraction_hints": self.extraction_hints,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "TemplateFingerprint":
        """Create from dictionary."""
        return cls(
            template_id=data["template_id"],
            template_name=data["template_name"],
            source=data.get("source", "custom"),
            line_count_range=tuple(data.get("line_count_range", [5, 100])),
            header_line_count=data.get("header_line_count", 3),
            footer_line_count=data.get("footer_line_count", 2),
            merchant_keywords=set(data.get("merchant_keywords", [])),
            header_keywords=set(data.get("header_keywords", [])),
            footer_keywords=set(data.get("footer_keywords", [])),
            amount_count_range=tuple(data.get("amount_count_range", [1, 50])),
            has_tax_line=data.get("has_tax_line", False),
            has_subtotal_line=data.get("has_subtotal_line", False),
            has_total_line=data.get("has_total_line", True),
            date_formats=data.get("date_formats", []),
            has_time=data.get("has_time", False),
            has_table_structure=data.get("has_table_structure", False),
            has_separator_lines=data.get("has_separator_lines", False),
            typical_line_length=tuple(data.get("typical_line_length", [10, 80])),
            match_threshold=data.get("match_threshold", 0.7),
            extraction_hints=data.get("extraction_hints", {}),
        )


# Common patterns for fingerprinting
AMOUNT_PATTERN = re.compile(r'[\$€£¥₹]?\s*\d{1,3}(?:[,.\s]\d{3})*(?:[.,]\d{2})?\b')
DATE_PATTERNS = [
    (r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', "MM/DD/YYYY"),
    (r'\d{4}[/-]\d{1,2}[/-]\d{1,2}', "YYYY-MM-DD"),
    (r'\d{1,2}\s+\w{3,9}\s+\d{2,4}', "DD Mon YYYY"),
    (r'\w{3,9}\s+\d{1,2},?\s+\d{2,4}', "Mon DD, YYYY"),
]
TIME_PATTERN = re.compile(r'\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm)?\b')
SEPARATOR_PATTERN = re.compile(r'^[-=*_]{3,}$|^[-.]{5,}$')

TAX_KEYWORDS = {"tax", "vat", "gst", "hst", "pst", "sales tax", "service tax"}
SUBTOTAL_KEYWORDS = {"subtotal", "sub-total", "sub total", "before tax"}
TOTAL_KEYWORDS = {"total", "grand total", "amount due", "balance due", "total due"}
FOOTER_KEYWORDS = {"thank you", "thanks", "visit again", "have a nice day", "receipt"}


def compute_fingerprint(
    lines: List[str],
    template_id: Optional[str] = None,
    template_name: Optional[str] = None,
    source: str = "learned"
) -> TemplateFingerprint:
    """
    Compute a structural fingerprint from receipt text lines.
    
    Args:
        lines: OCR text lines from receipt
        template_id: Optional template ID (auto-generated if not provided)
        template_name: Optional template name
        source: Source of template ("sroie", "custom", "learned")
    
    Returns:
        TemplateFingerprint capturing structural features
    """
    if not lines:
        raise ValueError("Cannot compute fingerprint from empty lines")
    
    # Normalize lines
    normalized = [line.strip() for line in lines if line and line.strip()]
    line_count = len(normalized)
    
    # Auto-generate template_id if not provided
    if not template_id:
        content_hash = hashlib.md5("\n".join(normalized[:10]).encode()).hexdigest()[:8]
        template_id = f"{source}_{content_hash}"
    
    if not template_name:
        # Try to extract merchant name from first few lines
        template_name = _extract_merchant_name(normalized[:5]) or f"Template_{template_id}"
    
    # Find amount positions
    amount_positions = []
    for i, line in enumerate(normalized):
        if AMOUNT_PATTERN.search(line):
            amount_positions.append(i)
    
    # Calculate header/footer line counts
    header_lines = amount_positions[0] if amount_positions else 3
    footer_lines = line_count - amount_positions[-1] - 1 if amount_positions else 2
    
    # Extract keywords
    merchant_kw = _extract_merchant_keywords(normalized[:5])
    header_kw = _extract_header_keywords(normalized[:header_lines + 2])
    footer_kw = _extract_footer_keywords(normalized[-5:] if line_count > 5 else normalized)
    
    # Detect patterns
    has_tax = any(_contains_keywords(line, TAX_KEYWORDS) for line in normalized)
    has_subtotal = any(_contains_keywords(line, SUBTOTAL_KEYWORDS) for line in normalized)
    has_total = any(_contains_keywords(line, TOTAL_KEYWORDS) for line in normalized)
    
    # Detect date formats
    date_formats = _detect_date_formats(normalized)
    has_time = any(TIME_PATTERN.search(line) for line in normalized)
    
    # Detect layout features
    has_separator = any(SEPARATOR_PATTERN.match(line) for line in normalized)
    has_table = _detect_table_structure(normalized)
    
    # Line length statistics
    lengths = [len(line) for line in normalized]
    typical_length = (min(lengths), max(lengths)) if lengths else (10, 80)
    
    return TemplateFingerprint(
        template_id=template_id,
        template_name=template_name,
        source=source,
        line_count_range=(max(1, line_count - 10), line_count + 10),
        header_line_count=header_lines,
        footer_line_count=footer_lines,
        merchant_keywords=merchant_kw,
        header_keywords=header_kw,
        footer_keywords=footer_kw,
        amount_count_range=(max(1, len(amount_positions) - 5), len(amount_positions) + 10),
        has_tax_line=has_tax,
        has_subtotal_line=has_subtotal,
        has_total_line=has_total,
        date_formats=date_formats,
        has_time=has_time,
        has_table_structure=has_table,
        has_separator_lines=has_separator,
        typical_line_length=typical_length,
    )


def _extract_merchant_name(lines: List[str]) -> Optional[str]:
    """Try to extract merchant name from first few lines."""
    for line in lines:
        # Skip short lines, numbers-only, separators
        if len(line) < 3:
            continue
        if re.match(r'^[\d\s.,-]+$', line):
            continue
        if SEPARATOR_PATTERN.match(line):
            continue
        # First substantive line is likely merchant
        return line.strip()
    return None


def _extract_merchant_keywords(lines: List[str]) -> Set[str]:
    """Extract keywords from merchant/header area."""
    keywords = set()
    for line in lines:
        # Extract words (alpha only, 3+ chars)
        words = re.findall(r'\b[a-zA-Z]{3,}\b', line.lower())
        keywords.update(words)
    return keywords


def _extract_header_keywords(lines: List[str]) -> Set[str]:
    """Extract keywords from header area."""
    keywords = set()
    for line in lines:
        lower = line.lower()
        # Look for common header words
        for word in ["tel", "phone", "fax", "address", "store", "branch", "receipt"]:
            if word in lower:
                keywords.add(word)
        # Extract capitalized words (potential business names)
        caps = re.findall(r'\b[A-Z][A-Za-z]+\b', line)
        keywords.update(w.lower() for w in caps)
    return keywords


def _extract_footer_keywords(lines: List[str]) -> Set[str]:
    """Extract keywords from footer area."""
    keywords = set()
    for line in lines:
        lower = line.lower()
        for kw in FOOTER_KEYWORDS:
            if kw in lower:
                keywords.add(kw)
    return keywords


def _contains_keywords(line: str, keywords: Set[str]) -> bool:
    """Check if line contains any of the keywords."""
    lower = line.lower()
    return any(kw in lower for kw in keywords)


def _detect_date_formats(lines: List[str]) -> List[str]:
    """Detect date formats present in the text."""
    formats = []
    text = "\n".join(lines)
    for pattern, fmt in DATE_PATTERNS:
        if re.search(pattern, text):
            formats.append(fmt)
    return formats


def _detect_table_structure(lines: List[str]) -> bool:
    """Detect if receipt has table-like structure (aligned columns)."""
    # Look for consistent spacing patterns
    space_patterns = []
    for line in lines:
        # Find positions of multiple spaces
        spaces = [m.start() for m in re.finditer(r'\s{2,}', line)]
        if spaces:
            space_patterns.append(tuple(spaces[:3]))  # First 3 space positions
    
    if len(space_patterns) < 3:
        return False
    
    # Check if space positions are consistent across multiple lines
    from collections import Counter
    pattern_counts = Counter(space_patterns)
    most_common = pattern_counts.most_common(1)
    if most_common and most_common[0][1] >= 3:
        return True
    
    return False
